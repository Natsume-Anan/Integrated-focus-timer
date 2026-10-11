"""端到端自检:python -m netproxy.selftest

起一个本地「假网站」和一个本地「假上游代理」,让过滤代理真的转发 / 拦截一遍.
不碰系统代理,不联网.
"""

import socket
import threading

from .rules import RuleStore, WHITE_DOMAINS, BLACK_DOMAINS
from .server import FilterProxy, split_hostport


def _serve_once(handler):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)

    def loop():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=handler, args=(c,), daemon=True).start()

    threading.Thread(target=loop, daemon=True).start()
    return srv, srv.getsockname()[1]


def _web(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return
        data += chunk
    first = data.split(b"\r\n", 1)[0]
    body = b"hello " + first
    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s"
                 % (len(body), body))
    conn.close()


def _echo(conn):
    while True:
        d = conn.recv(4096)
        if not d:
            break
        conn.sendall(d.upper())
    conn.close()


def _read_all(s):
    out = b""
    while True:
        d = s.recv(65536)
        if not d:
            return out
        out += d


class _Proxy(FilterProxy):
    """把所有「外网」主机重定向到本地假服务器."""

    def __init__(self, *a, targets=None, **kw):
        super().__init__(*a, **kw)
        self.targets = targets or {}

    def _dial(self, host, port):
        if host in self.targets:
            return super()._dial("127.0.0.1", self.targets[host])
        return super()._dial(host, port)


def _http_get(proxy_port, url):
    s = socket.create_connection(("127.0.0.1", proxy_port), timeout=5)
    host = url.split("//", 1)[1].split("/", 1)[0]
    s.sendall(f"GET {url} HTTP/1.1\r\nHost: {host}\r\nProxy-Connection: keep-alive\r\n\r\n".encode())
    return _read_all(s)


def _connect(proxy_port, hostport, payload=b"ping"):
    s = socket.create_connection(("127.0.0.1", proxy_port), timeout=5)
    s.sendall(f"CONNECT {hostport} HTTP/1.1\r\nHost: {hostport}\r\n\r\n".encode())
    head = b""
    while b"\r\n\r\n" not in head:
        d = s.recv(4096)
        if not d:
            break
        head += d
    status = head.split(b"\r\n", 1)[0]
    if b" 200" not in status:
        return status, head
    s.sendall(payload)
    s.shutdown(socket.SHUT_WR)
    return status, _read_all(s)


def run():
    import os
    import tempfile
    assert split_hostport("a.com:8443", 443) == ("a.com", 8443)
    assert split_hostport("[::1]:80", 443) == ("::1", 80)
    assert split_hostport("a.com", 443) == ("a.com", 443)

    web, web_port = _serve_once(_web)
    echo, echo_port = _serve_once(_echo)

    rules = RuleStore(os.path.join(tempfile.mkdtemp(), "r.json"))
    rules.add(WHITE_DOMAINS, "school.example")
    rules.add(BLACK_DOMAINS, "bad.example")
    state = {"online": False, "mode": "whitelist"}
    events = []

    def decide(host, exe):
        return rules.decide(host, exe, state["online"], state["mode"])

    p = _Proxy(decide, port=0, targets={"school.example": web_port, "bad.example": web_port,
                                         "other.example": web_port, "tls.school.example": echo_port},
               on_event=lambda h, e, a, w: events.append((h, a, w)))
    port = p.start()
    try:
        # 离线:白名单放行,其它拦截
        r = _http_get(port, "http://school.example/x?y=1")
        assert r.startswith(b"HTTP/1.1 200") and b"hello GET /x?y=1 HTTP/1.1" in r, r
        r = _http_get(port, "http://other.example/")
        assert r.startswith(b"HTTP/1.1 403") and b"offline" in r, r
        st, body = _connect(port, "tls.school.example:443")
        assert b" 200" in st and body == b"PING", (st, body)
        st, head = _connect(port, "other.example:443")
        assert b" 403" in st, st

        # 黑名单模式:默认放行,离线也只拦黑名单
        state["mode"] = "blacklist"
        r = _http_get(port, "http://other.example/")
        assert r.startswith(b"HTTP/1.1 200"), r
        r = _http_get(port, "http://bad.example/")
        assert r.startswith(b"HTTP/1.1 403") and b"blacklist-domain" in r, r

        # 联网会话中同样
        state["online"] = True
        r = _http_get(port, "http://other.example/")
        assert r.startswith(b"HTTP/1.1 200"), r
        r = _http_get(port, "http://bad.example/")
        assert r.startswith(b"HTTP/1.1 403") and b"blacklist-domain" in r, r
        st, _ = _connect(port, "bad.example:443")
        assert b" 403" in st
        st, _ = _connect(port, f"127.0.0.1:{port}")
        assert b" 403" in st, "不允许经代理回环到代理自身"

        # 解析失败 → 502 而不是挂死
        st, _ = _connect(port, "nonexistent.invalid:443")
        assert b" 502" in st or b" 403" in st, st

        # 大块数据完整转发
        big = os.urandom(200_000).replace(b"\r", b"x")
        st, body = _connect(port, "tls.school.example:443", big)
        assert body == big.upper(), "大数据转发被截断"

        assert any(e[0] == "bad.example" and not e[1] for e in events)

        # 已建立的隧道:规则一变就必须被掐断(浏览器会复用连接,不能只在建立时检查)
        import time
        state["online"], state["mode"] = False, "blacklist"
        rules.remove(BLACK_DOMAINS, "later.example")
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        s.sendall(b"CONNECT later.example:443 HTTP/1.1\r\nHost: later.example:443\r\n\r\n")
        p.targets["later.example"] = echo_port
        head = b""
        while b"\r\n\r\n" not in head:
            head += s.recv(4096)
        assert b" 200" in head.split(b"\r\n", 1)[0]
        s.sendall(b"hi")
        assert s.recv(16) == b"HI"
        rules.add(BLACK_DOMAINS, "later.example")          # 现在加入黑名单
        t0 = time.monotonic()
        s.settimeout(5)
        cut = False
        try:
            while True:
                d = s.recv(16)
                if not d:
                    cut = True
                    break
        except OSError:
            cut = True
        assert cut and time.monotonic() - t0 < 4, "新加入黑名单后,已打开的连接没有被掐断"
        s.close()
    finally:
        p.stop()

    # ── 上游代理链:放行的流量必须穿过「用户原来的代理」
    seen = []

    def fake_up(conn):
        head = b""
        while b"\r\n\r\n" not in head:
            d = conn.recv(4096)
            if not d:
                return
            head += d
        first = head.split(b"\r\n", 1)[0]
        seen.append(first)
        if first.startswith(b"CONNECT"):
            conn.sendall(b"HTTP/1.1 200 OK\r\n\r\n")
            _echo(conn)
        else:
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nUP")
            conn.close()

    up, up_port = _serve_once(fake_up)
    state["online"] = True
    p2 = _Proxy(decide, port=0, upstream=lambda: ("127.0.0.1", up_port),
                targets={"other.example": up_port})
    port2 = p2.start()
    try:
        r = _http_get(port2, "http://other.example/a")
        assert r.endswith(b"UP") and seen[-1].startswith(b"GET http://other.example/a"), (r, seen)
        st, body = _connect(port2, "other.example:443")
        assert b" 200" in st and body == b"PING" and seen[-1].startswith(b"CONNECT other.example:443")
    finally:
        p2.stop()

    # ── 端口被占用 → 顺延
    hold = socket.socket()
    hold.bind(("127.0.0.1", 0))
    hold.listen(1)
    taken = hold.getsockname()[1]
    p3 = FilterProxy(decide, port=taken)
    got = p3.start()
    assert got != taken
    p3.stop()
    hold.close()
    web.close()
    echo.close()
    up.close()
    return "netproxy end-to-end selftest OK"


if __name__ == "__main__":
    print(run())
