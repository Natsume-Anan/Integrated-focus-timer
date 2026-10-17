"""
设备同步 (MECHANICS.md 第 15 节)
────────────────────────────────
同一个局域网里的 OIT (Windows / Android) 互相绑定, 同步设置, 名单, 数据和状态. 不经过任何服务器.

    发现   UDP 17931 广播 {"oit": "discover"}, 收到的回 {"oit": "here", id, name, port …}
    传输   HTTP (TCP 17930 起), 绑定之后的每个请求都加密并签名
    绑定   Diffie-Hellman (RFC 3526 第 14 组) 交换密钥, 两边显示同一个 6 位配对码, 被请求的一方确认
    加密   密钥 K 派生出 enc / mac 两把密钥; 密钥流 = HMAC-SHA256(enc, nonce ‖ 计数器), 再 HMAC 签名
          (只用标准库; Android 版 sync/SyncCrypto.kt 是同一套算法)

同步的内容分三类 (见 snapshot()):
    docs     共享文档: 设置, 整点记录, 计时器 (此刻的专注 / 休息, 积攒的休息时间). 每一项单独记修改时间,
             新的覆盖旧的. 规则页的名单和过滤模式不同步
    ledgers  各设备自己的账: 今天的联网额度用量 / 借贷, 学习时长, 专注时间段, 联网理由, 窗口时间.
             互相转交, 每台设备显示的是所有设备的合计
    status   各设备此刻的状态 (专注 / 休息 / 联网) 和最后一次操作的时间 (整点提示音只在最后操作的设备上响)

同步由母端发起: 每 30 秒向每台子端发一次请求, 双方合并后回复; 子端只在第一次初始化和按"立即同步"时主动发.

第一次绑定时选一端作为母端: 另一端清掉自己的历史数据, 用母端的文档和账初始化 (今天已用的联网额度保留).

本模块不依赖 tkinter; 和本机数据打交道的部分由 local (见 sync_local.py) 提供.
所有改动本机数据的操作都通过 run_main 交给界面线程执行.

    python devsync.py       自检 (两个实例在本机互相绑定, 同步)
"""

import base64
import hashlib
import hmac
import http.client
import json
import os
import queue
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROTO = 1
HTTP_PORT = 17930          # 被占用时依次尝试到 17939
UDP_PORT = 17931
SYNC_EVERY = 30            # 秒: 母端每隔这么久向每台子端发一次同步请求
FRESH_MS = 120_000         # 毫秒: 这么久之内同步过的设备才算"在线" (比较最后操作时间用)
PAIR_TIMEOUT = 120         # 秒: 等对方确认绑定
TS_SKEW = 300              # 秒: 请求里的时间戳允许和本机相差多少

# RFC 3526, 2048-bit MODP Group 14
P = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A0879"
    "8E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B"
    "0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA4836"
    "1C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804"
    "F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6"
    "955817183995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF", 16)
G = 2

# 设置里每台设备各自决定的项, 不同步
LOCAL_SETTINGS = {"NET_MODE", "FILTER_MODE", "FONT_SCALE", "CHIME_WAV",
                  "WINDOW_LIMIT_ENABLED", "WINDOW_LIMIT", "WINDOW_FOCUS_ENABLED",
                  "UPDATE_CHECK", "UPDATE_AUTO"}


# ═══════════════════════ 密码学 ═══════════════════════

def _h(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def dh_keypair():
    x = secrets.randbits(256) | (1 << 255)
    return x, pow(G, x, P)


def dh_shared(x: int, peer_pub_hex: str) -> bytes:
    y = int(peer_pub_hex, 16)
    if not 1 < y < P - 1:
        raise ValueError("bad public key")
    s = pow(y, x, P)
    return hashlib.sha256(s.to_bytes(256, "big")).digest()


def pair_code(k: bytes) -> str:
    n = int.from_bytes(hashlib.sha256(k + b"code").digest()[:4], "big") % 1000000
    return f"{n:06d}"


def accept_proof(k: bytes, token: str) -> str:
    return _h(k, b"accepted:" + token.encode()).hex()


def _keystream_xor(enc: bytes, nonce: bytes, data: bytes) -> bytes:
    out = bytearray(len(data))
    for i in range(0, len(data), 32):
        block = _h(enc, nonce + (i // 32).to_bytes(4, "big"))
        for j in range(min(32, len(data) - i)):
            out[i + j] = data[i + j] ^ block[j]
    return bytes(out)


def seal(k: bytes, sender: str, obj, nonce: bytes = None, ts: int = None) -> dict:
    nonce = nonce or secrets.token_bytes(16)
    ts = int(time.time() * 1000) if ts is None else ts
    pt = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ct = _keystream_xor(_h(k, b"enc"), nonce, pt)
    mac = _h(_h(k, b"mac"), nonce + ts.to_bytes(8, "big") + ct).hex()
    return {"from": sender, "nonce": base64.b64encode(nonce).decode(), "ts": ts,
            "ct": base64.b64encode(ct).decode(), "mac": mac}


class SealError(Exception):
    pass


_seen_nonces = {}
_seen_lock = threading.Lock()


def unseal(k: bytes, env: dict, replay: bool = True):
    try:
        nonce = base64.b64decode(env["nonce"])
        ct = base64.b64decode(env["ct"])
        ts = int(env["ts"])
        mac = str(env["mac"])
    except Exception:
        raise SealError("malformed")
    want = _h(_h(k, b"mac"), nonce + ts.to_bytes(8, "big") + ct).hex()
    if not hmac.compare_digest(want, mac):
        raise SealError("bad mac")
    if abs(time.time() * 1000 - ts) > TS_SKEW * 1000:
        raise SealError("clock")
    if replay:
        with _seen_lock:
            now = time.time()
            for n, t in list(_seen_nonces.items()):
                if now - t > 2 * TS_SKEW:
                    del _seen_nonces[n]
            if mac in _seen_nonces:
                raise SealError("replay")
            _seen_nonces[mac] = now
    return json.loads(_keystream_xor(_h(k, b"enc"), nonce, ct).decode("utf-8"))


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


H_NONE = _hash(None)


# ═══════════════════════ 交给界面线程执行 ═══════════════════════

class MainRunner:
    """其他线程把要改本机数据的操作排进来, 界面线程定期 pump() 执行 (tk 不是线程安全的)."""

    def __init__(self):
        self.q = queue.Queue()

    def call(self, fn, timeout: float = 8.0):
        box, ev = {}, threading.Event()
        self.q.put((fn, box, ev))
        if not ev.wait(timeout):
            raise TimeoutError("main thread busy")
        if "err" in box:
            raise box["err"]
        return box.get("ok")

    def pump(self, limit: int = 20):
        for _ in range(limit):
            try:
                fn, box, ev = self.q.get_nowait()
            except queue.Empty:
                return
            try:
                box["ok"] = fn()
            except Exception as e:      # noqa: BLE001 —— 原样交回调用的线程
                box["err"] = e
            ev.set()


# ═══════════════════════ 同步服务 ═══════════════════════

def _now_ms() -> int:
    return int(time.time() * 1000)


class SyncService:

    def __init__(self, data_dir: str, local, runner: MainRunner, platform: str = "windows",
                 name: str = None, http_port: int = HTTP_PORT, udp_port: int = UDP_PORT):
        self.file = os.path.join(data_dir, "sync_state.json")
        self.local = local
        self.runner = runner
        self.platform = platform
        self.http_port0 = http_port
        self.udp_port = udp_port
        self.port = None
        self.lock = threading.RLock()
        self.dead = False
        self.incoming = {}        # token -> 别人发来的绑定请求
        self.outgoing = None      # 本机发起的绑定 {state, code, name, …}
        self.found = {}           # id -> 广播找到的设备
        self._httpd = None
        self._udp = None
        self._wake = threading.Event()
        self._busy = set()        # 正在和哪些设备同步 (同一台设备不同时跑两轮)
        self.firewall = None      # 本机防火墙检查的结果 (firewall.check, 由 app 在后台填)
        self.state = self._load()
        if not self.state.get("device"):
            self.state["device"] = {"id": secrets.token_hex(6),
                                    "name": name or socket.gethostname() or "OIT"}
            self._save()
        elif name and not self.state["device"].get("name"):
            self.state["device"]["name"] = name

    # ---- 存档 ----

    def _load(self) -> dict:
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                for k in ("peers", "track", "ledgers", "status"):
                    if not isinstance(d.get(k), dict):
                        d[k] = {}
                return d
        except Exception:
            pass
        return {"device": None, "peers": {}, "track": {}, "ledgers": {}, "status": {}}

    def _save(self):
        if self.dead:
            return
        with self.lock:
            tmp = self.file + ".tmp"
            try:
                os.makedirs(os.path.dirname(self.file) or ".", exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.state, f, ensure_ascii=False)
                os.replace(tmp, self.file)
            except OSError:
                pass

    @property
    def my_id(self) -> str:
        return self.state["device"]["id"]

    @property
    def my_name(self) -> str:
        return self.state["device"]["name"]

    def peers(self) -> dict:
        with self.lock:
            return {k: dict(v) for k, v in self.state["peers"].items()}

    def proxy_ok(self) -> bool:
        try:
            return self.local.net_mode() == "proxy"
        except Exception:
            return False

    def device_info(self) -> dict:
        return {"id": self.my_id, "name": self.my_name, "platform": self.platform,
                "port": self.port, "net_mode": self.local.net_mode(), "v": PROTO}

    # ---- 启动 / 停止 ----

    def start(self):
        for port in range(self.http_port0, self.http_port0 + 10):
            try:
                self._httpd = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(self))
                self._httpd.daemon_threads = True
                self.port = port
                break
            except OSError:
                continue
        if self._httpd:
            threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        try:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            u.bind(("0.0.0.0", self.udp_port))
            u.settimeout(1.0)
            self._udp = u
            threading.Thread(target=self._udp_loop, daemon=True).start()
        except OSError:
            self._udp = None
        threading.Thread(target=self._sync_loop, daemon=True).start()
        return self.port

    def stop(self):
        self.dead = True
        self._wake.set()
        try:
            if self._httpd:
                self._httpd.shutdown()
                self._httpd.server_close()
        except Exception:
            pass
        try:
            if self._udp:
                self._udp.close()
        except Exception:
            pass

    # ---- 发现 ----

    def _udp_loop(self):
        while not self.dead:
            try:
                data, addr = self._udp.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                if self.dead:
                    return
                time.sleep(1)
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if not isinstance(msg, dict) or msg.get("id") == self.my_id:
                continue
            if msg.get("oit") == "discover":
                reply = dict(self.device_info(), oit="here")
                try:
                    self._udp.sendto(json.dumps(reply).encode("utf-8"), addr)
                except OSError:
                    pass
            elif msg.get("oit") == "here":
                self._note_found(msg, addr[0])

    def _note_found(self, msg: dict, ip: str):
        info = {"id": str(msg.get("id")), "name": str(msg.get("name") or "?"),
                "platform": str(msg.get("platform") or "?"), "addr": ip,
                "port": int(msg.get("port") or HTTP_PORT),
                "net_mode": str(msg.get("net_mode") or ""), "ts": time.time()}
        with self.lock:
            self.found[info["id"]] = info
            p = self.state["peers"].get(info["id"])
            if p and (p.get("addr") != ip or p.get("port") != info["port"]):
                p["addr"], p["port"] = ip, info["port"]

    def _broadcast_targets(self):
        """255.255.255.255 加上每块网卡所在网段的广播地址.
        Windows 只把 255.255.255.255 从一块网卡发出去 (装了虚拟网卡 / VPN 时常常不是 Wi-Fi 那块),
        所以每个网段还要单独发一次. 以前一律按 /24 猜, 10.x / 172.x 这类更大的局域网里找不到对方."""
        targets = {"255.255.255.255"}
        for addr, mask in _ipv4_nets():
            if addr.startswith("127.") or addr.startswith("169.254.") or mask == "255.255.255.255":
                continue
            try:
                a = int.from_bytes(socket.inet_aton(addr), "big")
                m = int.from_bytes(socket.inet_aton(mask), "big")
            except OSError:
                continue
            targets.add(socket.inet_ntoa(((a & m) | (~m & 0xFFFFFFFF)).to_bytes(4, "big")))
        return targets

    def discover(self, wait: float = 2.0) -> list:
        """广播找一下同一局域网里的 OIT, 返回找到的设备 (不含本机)."""
        msg = json.dumps({"oit": "discover", "id": self.my_id, "v": PROTO}).encode("utf-8")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(0.3)
            for t in self._broadcast_targets():
                try:
                    s.sendto(msg, (t, self.udp_port))
                except OSError:
                    pass
            end = time.time() + wait
            while time.time() < end:
                try:
                    data, addr = s.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    m = json.loads(data.decode("utf-8"))
                except Exception:
                    continue
                if isinstance(m, dict) and m.get("oit") == "here" and m.get("id") != self.my_id:
                    self._note_found(m, addr[0])
        finally:
            s.close()
        with self.lock:
            return [dict(v) for v in self.found.values() if time.time() - v["ts"] < 60]

    # ---- HTTP 客户端 ----

    @staticmethod
    def _http(addr: str, port: int, method: str, path: str, body=None, timeout: float = 6.0):
        conn = http.client.HTTPConnection(addr, int(port), timeout=timeout)
        try:
            data = json.dumps(body).encode("utf-8") if body is not None else None
            conn.request(method, path, body=data,
                         headers={"Content-Type": "application/json", "Connection": "close"})
            r = conn.getresponse()
            raw = r.read(8_000_000)
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                payload = {}
            return r.status, payload
        finally:
            conn.close()

    def hello(self, addr: str, port: int = HTTP_PORT) -> dict:
        st, d = self._http(addr, port, "GET", "/oit/v1/hello", timeout=3.0)
        if st != 200:
            raise OSError(f"HTTP {st}")
        return d

    # ---- 绑定: 发起方 ----

    def start_pairing(self, addr: str, port: int, mother_is_me: bool):
        """在后台线程里发起绑定; 进度看 self.outgoing."""
        self.outgoing = {"state": "connecting", "addr": addr, "port": int(port), "code": "",
                         "name": "", "error": ""}
        threading.Thread(target=self._pair_worker, args=(addr, int(port), mother_is_me),
                         daemon=True).start()

    def cancel_pairing(self):
        o = self.outgoing
        if o:
            o["state"] = "cancelled"

    def _pair_worker(self, addr, port, mother_is_me):
        o = self.outgoing
        try:
            if not self.proxy_ok():
                raise RuntimeError("not-proxy")
            x, pub = dh_keypair()
            st, d = self._http(addr, port, "POST", "/oit/v1/pair", dict(
                self.device_info(), pub=format(pub, "x"), mother="me" if mother_is_me else "you"))
            if st != 200:
                raise RuntimeError(d.get("error") or f"HTTP {st}")
            k = dh_shared(x, d["pub"])
            token = str(d["token"])
            o.update(state="waiting", code=pair_code(k), name=str(d.get("name") or "?"))
            deadline = time.time() + PAIR_TIMEOUT
            misses = 0
            while time.time() < deadline and o["state"] == "waiting" and not self.dead:
                time.sleep(1.5)
                try:
                    st, r = self._http(addr, port, "GET", f"/oit/v1/pair/{token}", timeout=4.0)
                    misses = 0
                except OSError:
                    # Wi-Fi 偶尔丢一两个包: 等对方确认的这两分钟里, 连续几次连不上才算失败
                    misses += 1
                    if misses >= 5:
                        raise
                    continue
                state = r.get("state")
                if state == "rejected":
                    o["state"] = "rejected"
                    return
                if state == "accepted":
                    if not hmac.compare_digest(str(r.get("proof")), accept_proof(k, token)):
                        raise RuntimeError("bad proof")
                    peer_id = str(d["id"])
                    mother = self.my_id if mother_is_me else peer_id
                    self.runner.call(lambda: self._add_peer(peer_id, d, addr, port, k, mother))
                    o["state"] = "accepted"
                    if mother != self.my_id:
                        self._init_after_accept(peer_id)
                    return
            if o["state"] == "waiting":
                o["state"] = "timeout"
        except Exception as e:      # noqa: BLE001 —— 显示给用户
            o.update(state="error", error=str(e) or type(e).__name__)

    def _add_peer(self, peer_id, info, addr, port, k, mother):
        with self.lock:
            self.state["peers"][peer_id] = {
                "name": str(info.get("name") or "?"), "platform": str(info.get("platform") or "?"),
                "addr": addr, "port": int(port), "key": k.hex(), "mother": mother,
                "paired_at": _now_ms(), "last_ok": 0, "last_err": "",
                # 本机是子端: 用母端的内容初始化之前不参加普通同步, 免得自己的旧数据传给母端
                "init": mother != self.my_id}
        self._save()
        self.local.changed()

    # ---- 绑定: 被请求方 ----

    def _on_pair(self, body: dict, client_ip: str):
        if not self.proxy_ok():
            return 409, {"error": "not-proxy"}
        if body.get("net_mode") != "proxy":
            return 409, {"error": "peer-not-proxy"}
        try:
            peer_id = str(body["id"])
            x, pub = dh_keypair()
            k = dh_shared(x, str(body["pub"]))
        except Exception:
            return 400, {"error": "bad request"}
        token = secrets.token_hex(8)
        mother = peer_id if body.get("mother") == "me" else self.my_id
        req = {"token": token, "id": peer_id, "name": str(body.get("name") or "?"),
               "platform": str(body.get("platform") or "?"), "addr": client_ip,
               "port": int(body.get("port") or HTTP_PORT), "key": k, "code": pair_code(k),
               "mother": mother, "state": "pending", "ts": time.time()}
        with self.lock:
            for t, r in list(self.incoming.items()):
                if time.time() - r["ts"] > PAIR_TIMEOUT + 30:
                    del self.incoming[t]
            self.incoming[token] = req
        try:
            self.runner.call(lambda: self.local.pair_request(dict(req, key=None)), timeout=3.0)
        except Exception:
            pass
        return 200, {"id": self.my_id, "name": self.my_name, "platform": self.platform,
                     "pub": format(pub, "x"), "token": token}

    def _pair_status(self, token: str):
        r = self.incoming.get(token)
        if not r:
            return 404, {"state": "unknown"}
        out = {"state": r["state"]}
        if r["state"] == "accepted":
            out["proof"] = accept_proof(r["key"], token)
        return 200, out

    def answer_pairing(self, token: str, accept: bool):
        """界面线程: 用户在提示窗里接受 / 拒绝了绑定请求."""
        r = self.incoming.get(token)
        if not r or r["state"] != "pending":
            return False
        if not accept:
            r["state"] = "rejected"
            return True
        self._add_peer(r["id"], r, r["addr"], r["port"], r["key"], r["mother"])
        r["state"] = "accepted"
        # 本机是子端: 主动向母端要初始化的内容. 本机是母端: 等子端来要 —— 这时发起方 (子端) 可能还没
        # 查到"已接受", 马上同步过去只会得到 401 (以前会显示"同步失败: unpaired")
        if r["mother"] != self.my_id:
            threading.Thread(target=self._init_after_accept, args=(r["id"],), daemon=True).start()
        return True

    def _init_after_accept(self, peer_id: str):
        """本机是子端, 刚接受了绑定: 向母端要初始化的内容.
        发起方要等下一次查询 (每 1.5 秒) 才知道已经接受, 在那之前它还不认识本机, 会回 401 ——
        以前只试一次, 失败后要等 30 秒的下一轮, 这期间一直显示"同步失败: unpaired"."""
        for _ in range(12):
            if self.dead or peer_id not in self.peers():
                return
            if self._sync_with(peer_id, init=True, quiet=True):
                return
            time.sleep(1.5)
        self._sync_with(peer_id, init=True)          # 还不行就照常记下原因, 交给定时同步

    # ---- 解除绑定 ----

    def unpair(self, peer_id: str, notify: bool = True):
        with self.lock:
            p = self.state["peers"].pop(peer_id, None)
            self.state["ledgers"].pop(peer_id, None)
            self.state["status"].pop(peer_id, None)
        self._save()
        self.local.changed()
        if p and notify:
            def go():
                try:
                    env = seal(bytes.fromhex(p["key"]), self.my_id, {"unpair": True})
                    self._http(p["addr"], p["port"], "POST", "/oit/v1/unpair", env, timeout=3.0)
                except Exception:
                    pass
            threading.Thread(target=go, daemon=True).start()

    # ---- 文档 (每一项单独记修改时间) ----

    def _stamp(self, local_docs: dict) -> dict:
        """本机文档 + 每一项的修改时间. 和上一次相比变了的项, 修改时间记为现在."""
        now = _now_ms()
        out = {}
        track = self.state["track"]
        for doc, kv in local_docs.items():
            t = track.setdefault(doc, {})
            for key, val in kv.items():
                h = _hash(val)
                if key not in t or t[key][0] != h:
                    t[key] = [h, now]
            for key in list(t):
                if key not in kv and t[key][0] != H_NONE:
                    t[key] = [H_NONE, now]
            out[doc] = {key: [t[key][1], kv.get(key)] for key in t}
        return out

    def _wins(self, doc, mt, val, cur) -> bool:
        cur_mt, cur_val = cur
        if doc == "hours":
            # 超时自动记录的内容永远让位给自己填写的内容
            auto = self.local.auto_text()
            r_auto, l_auto = val == auto, cur_val == auto
            if r_auto and cur_val and not l_auto:
                return False
            if l_auto and val and not r_auto:
                return True
        return int(mt) > int(cur_mt)

    def snapshot(self) -> dict:
        """界面线程: 要发给别人的全部内容."""
        own = self.local.ledger()
        own["rev"] = _now_ms()
        own["name"], own["platform"] = self.my_name, self.platform
        st = self.local.status()
        st["ts"] = _now_ms()
        docs = self._stamp(self.local.docs())
        self._save()
        with self.lock:
            ledgers = dict(self.state["ledgers"])
            status = dict(self.state["status"])
        ledgers[self.my_id] = own
        status[self.my_id] = st
        return {"v": PROTO, "device": self.device_info(), "ledgers": ledgers,
                "docs": docs, "status": status}

    def merge(self, snap: dict, init: bool = False):
        """界面线程: 并入别人发来的内容. init=True: 本机是子端, 第一次用母端的内容整体初始化."""
        if not isinstance(snap, dict):
            return
        my = self.my_id
        if init:
            self.local.clear_history()
        with self.lock:
            for did, led in (snap.get("ledgers") or {}).items():
                if did == my or not isinstance(led, dict):
                    continue
                if int(led.get("rev", 0)) > int((self.state["ledgers"].get(did) or {}).get("rev", -1)):
                    self.state["ledgers"][did] = led
            for did, st in (snap.get("status") or {}).items():
                if did == my or not isinstance(st, dict):
                    continue
                if int(st.get("ts", 0)) > int((self.state["status"].get(did) or {}).get("ts", -1)):
                    self.state["status"][did] = st
        local = self.local.docs()
        stamped = self._stamp(local)
        track = self.state["track"]
        now = _now_ms()
        for doc, entries in (snap.get("docs") or {}).items():
            if doc not in local or not isinstance(entries, dict):
                continue
            mine = stamped.get(doc, {})
            changes = {}
            for key, ent in entries.items():
                try:
                    mt, val = int(ent[0]), ent[1]
                except Exception:
                    continue
                cur = mine.get(key)
                if init or cur is None or self._wins(doc, mt, val, cur):
                    if cur is None or cur[1] != val:
                        changes[key] = val
                    track.setdefault(doc, {})[key] = [_hash(val), mt]
            if init:
                for key, cur in mine.items():
                    if key not in entries and cur[1] is not None:
                        changes[key] = None
                        track[doc][key] = [H_NONE, now]
            if changes:
                try:
                    self.local.apply(doc, changes)
                except Exception:
                    pass
        self._save()
        self.local.changed()

    # ---- 同步 ----

    def _sync_with(self, peer_id: str, init: bool = False, quiet: bool = False):
        """True 成功 / False 失败 / None 这次不用算 (正在同步, 或对方子端还在初始化).
        quiet: 失败了也不记原因 (绑定刚完成时的重试)."""
        p = self.peers().get(peer_id)
        if not p:
            return False
        if p.get("init") and not init:
            init = True
        with self.lock:
            if peer_id in self._busy:
                return None
            self._busy.add(peer_id)
        try:
            return self._sync_once(peer_id, p, init, quiet)
        finally:
            with self.lock:
                self._busy.discard(peer_id)

    def _sync_once(self, peer_id: str, p: dict, init: bool, quiet: bool):
        k = bytes.fromhex(p["key"])
        try:
            if init:
                # 子端第一次: 只要母端的内容, 自己的文档不发过去
                snap = self.runner.call(lambda: dict(self.snapshot(), docs={}, ledgers={}))
            else:
                snap = self.runner.call(self.snapshot)
            env = seal(k, self.my_id, {"snap": snap, "init": init})
            st, reply = self._http(p["addr"], p["port"], "POST", "/oit/v1/sync", env, timeout=10.0)
            if st == 401:
                raise RuntimeError("unpaired")
            if st == 409 and reply.get("error") == "initializing":
                return None             # 对方是子端, 正在向本机要初始化的内容: 不是出错
            if st != 200:
                raise RuntimeError(reply.get("error") or f"HTTP {st}")
            body = unseal(k, reply)
            self.runner.call(lambda: self.merge(body.get("snap"), init=init))
            with self.lock:
                q = self.state["peers"].get(peer_id)
                if q:
                    q["last_ok"], q["last_err"] = _now_ms(), ""
                    if init:
                        q["init"] = False
                    dev = (body.get("snap") or {}).get("device") or {}
                    if dev.get("name"):
                        q["name"] = str(dev["name"])
            self._save()
            return True
        except Exception as e:      # noqa: BLE001 —— 记下来显示
            if not quiet:
                with self.lock:
                    q = self.state["peers"].get(peer_id)
                    if q:
                        q["last_err"] = str(e) or type(e).__name__
            return False

    def _on_sync(self, env: dict):
        if not self.proxy_ok():
            return 409, {"error": "not-proxy"}
        if not env.get("from"):
            # 请求体读不出来 (例如超过大小上限): 以前当成"没绑定"回 401, 对方会显示 unpaired
            return 400, {"error": "bad-request"}
        p = self.peers().get(str(env.get("from")))
        if not p:
            return 401, {"error": "unpaired"}
        if p.get("init"):
            return 409, {"error": "initializing"}
        k = bytes.fromhex(p["key"])
        try:
            body = unseal(k, env)
        except SealError as e:
            return 403, {"error": str(e)}
        snap = body.get("snap") or {}
        if (snap.get("device") or {}).get("net_mode") != "proxy":
            return 409, {"error": "peer-not-proxy"}
        try:
            self.runner.call(lambda: self.merge(snap))
            mine = self.runner.call(self.snapshot)
        except Exception as e:      # noqa: BLE001
            return 503, {"error": str(e)}
        with self.lock:
            q = self.state["peers"].get(str(env.get("from")))
            if q:
                q["last_ok"], q["last_err"] = _now_ms(), ""
        return 200, seal(k, self.my_id, {"snap": mine})

    def _on_unpair(self, env: dict):
        p = self.peers().get(str(env.get("from")))
        if not p:
            return 200, {}
        try:
            unseal(bytes.fromhex(p["key"]), env)
        except SealError as e:
            return 403, {"error": str(e)}
        self.runner.call(lambda: self.unpair(str(env.get("from")), notify=False))
        return 200, {}

    def push_final(self, timeout: float = 3.0):
        """界面线程, 程序关闭前: 把本机此刻的内容发给每台设备 (不等回复里的内容, 最多等 timeout 秒).
        例如共享的专注因为本机关闭而结束了, 其他设备要马上照着结束 (MECHANICS 8.2)."""
        if not self.proxy_ok():
            return
        peers = {pid: p for pid, p in self.peers().items() if not p.get("init")}
        if not peers:
            return
        snap = self.snapshot()

        def send(p):
            try:
                env = seal(bytes.fromhex(p["key"]), self.my_id, {"snap": snap, "init": False})
                self._http(p["addr"], p["port"], "POST", "/oit/v1/sync", env, timeout=timeout)
            except Exception:
                pass
        threads = [threading.Thread(target=send, args=(p,), daemon=True) for p in peers.values()]
        for t in threads:
            t.start()
        end = time.time() + timeout
        for t in threads:
            t.join(max(0.0, end - time.time()))

    def synced_since(self, ms: int) -> bool:
        """绑定的设备里有没有哪台在 ms (毫秒时间戳) 之后同步成功过."""
        return any(int(p.get("last_ok") or 0) >= ms for p in self.peers().values())

    def sync_now(self):
        """立即同步一轮; 子端也会主动向母端发一次."""
        self._manual = True
        self._wake.set()

    def _sync_loop(self):
        last_discover = 0.0
        while not self.dead:
            self._wake.wait(SYNC_EVERY)
            self._wake.clear()
            manual, self._manual = getattr(self, "_manual", False), False
            if self.dead:
                return
            if not self.proxy_ok():
                continue
            # 母端向子端发请求; 子端只在还没初始化或按了"立即同步"时向母端发
            peers = {pid: p for pid, p in self.peers().items()
                     if p.get("mother") == self.my_id or p.get("init") or manual}
            failed = [pid for pid in peers if self._sync_with(pid) is False]
            # 有设备连不上: 地址可能变了 (DHCP), 广播找一下再试一次
            if failed and time.time() - last_discover > 60:
                last_discover = time.time()
                try:
                    self.discover(1.5)
                except OSError:
                    pass
                for pid in failed:
                    self._sync_with(pid)

    # ---- 给本机其他部分用: 其他设备的账 ----

    def peer_ledgers_by_id(self) -> dict:
        with self.lock:
            return {k: v for k, v in self.state["ledgers"].items() if k != self.my_id}

    def mother_id(self):
        """母端的设备 id: 本机是任何一次绑定的母端就是本机, 否则是绑定时选的那台."""
        peers = self.peers()
        if any(p.get("mother") == self.my_id for p in peers.values()):
            return self.my_id
        for p in peers.values():
            if p.get("mother"):
                return p["mother"]
        return None

    def peer_ledgers(self) -> list:
        with self.lock:
            return [v for k, v in self.state["ledgers"].items() if k != self.my_id]

    def is_latest_active(self) -> bool:
        """本机是不是最后有人操作的设备 (只比较最近 2 分钟内同步过的设备)."""
        try:
            mine = float(self.local.status().get("last_op", 0))
        except Exception:
            return True
        now = _now_ms()
        with self.lock:
            for k, st in self.state["status"].items():
                if k == self.my_id or now - float(st.get("ts", 0)) > FRESH_MS:
                    continue
                if float(st.get("last_op", 0)) > mine:
                    return False
        return True

    def peer_status(self) -> list:
        with self.lock:
            return [dict(v, id=k, name=(self.state["ledgers"].get(k) or {}).get("name", "?"))
                    for k, v in self.state["status"].items() if k != self.my_id]


def _ipv4_nets() -> list:
    """[(地址, 掩码)] 本机各网卡的 IPv4. Windows 用 GetIpAddrTable 取真实掩码; 其他平台按 /24 猜."""
    out = []
    if os.name == "nt":
        try:
            import ctypes
            import struct

            class Row(ctypes.Structure):
                _fields_ = [("addr", ctypes.c_uint32), ("index", ctypes.c_uint32),
                            ("mask", ctypes.c_uint32), ("bcast", ctypes.c_uint32),
                            ("reasm", ctypes.c_uint32), ("unused", ctypes.c_ushort),
                            ("type", ctypes.c_ushort)]
            iphlpapi = ctypes.WinDLL("iphlpapi")
            size = ctypes.c_ulong(0)
            iphlpapi.GetIpAddrTable(None, ctypes.byref(size), False)
            buf = ctypes.create_string_buffer(size.value + 64)
            if iphlpapi.GetIpAddrTable(buf, ctypes.byref(size), False) == 0:
                n = ctypes.c_ulong.from_buffer(buf).value
                rows = (Row * n).from_buffer(buf, ctypes.sizeof(ctypes.c_ulong))
                for r in rows:
                    if r.type & (0x0008 | 0x0040):         # 已断开 / 已删除的地址
                        continue
                    out.append((socket.inet_ntoa(struct.pack("<I", r.addr)),
                                socket.inet_ntoa(struct.pack("<I", r.mask))))
            if out:
                return out
        except Exception:
            out = []
    try:
        for _f, _t, _p, _c, sa in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            out.append((sa[0], "255.255.255.0"))
    except OSError:
        pass
    return out


def peer_net(ledgers, date: str) -> dict:
    """其他设备今天的联网额度用量之和 (只算日期是今天的)."""
    out = {"used": 0.0, "bonus": 0.0, "tomorrow_used": 0.0, "debt": 0.0}
    for led in ledgers:
        n = led.get("net") or {}
        if n.get("date") != date:
            continue
        for k in out:
            try:
                out[k] += max(0.0, float(n.get(k, 0)))
            except (TypeError, ValueError):
                pass
    return out


def _make_handler(svc: SyncService):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code: int, obj):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > 8_000_000:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:
                return {}

        def do_GET(self):
            if self.path == "/oit/v1/hello":
                return self._send(200, svc.device_info())
            if self.path.startswith("/oit/v1/pair/"):
                return self._send(*svc._pair_status(self.path.rsplit("/", 1)[-1]))
            self._send(404, {"error": "not found"})

        def do_POST(self):
            body = self._body()
            if self.path == "/oit/v1/pair":
                return self._send(*svc._on_pair(body, self.client_address[0]))
            if self.path == "/oit/v1/sync":
                return self._send(*svc._on_sync(body))
            if self.path == "/oit/v1/unpair":
                return self._send(*svc._on_unpair(body))
            self._send(404, {"error": "not found"})
    return H


# ═══════════════════════ 自检 ═══════════════════════

class _FakeLocal:
    """测试用的本机数据: 一份设置, 一份整点记录, 一本账."""

    def __init__(self, name):
        self.name = name
        self.mode = "proxy"
        self.docs_ = {"settings": {"DAILY_LIMIT": {"value": 7200.0, "pending": None}},
                      "hours": {}, "rules": {"black_domains": []}, "timer": {"break_carry": 0}}
        self.used = 0.0
        self.study = {}
        self.requests = []
        self.cleared = 0

    def net_mode(self):
        return self.mode

    def ledger(self):
        return {"net": {"date": "2026-01-01", "used": self.used, "bonus": 0, "tomorrow_used": 0,
                        "debt": 0}, "study": dict(self.study), "focus": [], "usage": [], "window": {}}

    def docs(self):
        return json.loads(json.dumps(self.docs_))

    def apply(self, doc, changes):
        for k, v in changes.items():
            if v is None:
                self.docs_[doc].pop(k, None)
            else:
                self.docs_[doc][k] = v

    def clear_history(self):
        self.cleared += 1
        self.study = {}

    def auto_text(self):
        return "Sleeping"

    def status(self):
        return {"timer": "idle", "net": "offline"}

    def pair_request(self, req):
        self.requests.append(req)

    def changed(self):
        pass


def _selftest():
    # 密码学: 双方算出同一把密钥和配对码; 篡改 / 重放 / 时钟差都拒绝
    xa, pa = dh_keypair()
    xb, pb = dh_keypair()
    ka, kb = dh_shared(xa, format(pb, "x")), dh_shared(xb, format(pa, "x"))
    assert ka == kb and len(pair_code(ka)) == 6
    env = seal(ka, "a", {"x": "你好", "n": [1, 2]})
    assert unseal(kb, env) == {"x": "你好", "n": [1, 2]}
    for bad in (dict(env, mac="0" * 64), dict(env, ct=base64.b64encode(b"zz").decode())):
        try:
            unseal(kb, bad)
            raise AssertionError("tampered message accepted")
        except SealError:
            pass
    try:
        unseal(kb, env)
        raise AssertionError("replay accepted")
    except SealError:
        pass
    try:
        unseal(kb, seal(ka, "a", {}, ts=_now_ms() - 3600_000))
        raise AssertionError("old message accepted")
    except SealError:
        pass
    # 固定输入的输出, Android 版的单元测试用同样的数字核对
    fixed = seal(bytes(range(32)), "dev", {"a": 1}, nonce=bytes(16), ts=1700000000000)
    assert fixed["ct"] == "pHEJdtrTcg==", fixed["ct"]
    assert fixed["mac"] == "a9ee146998cf5a913f1e5d4756f3b151789ed6e8e0b04b367bf1712d19ff8b24"
    assert pair_code(bytes(range(32))) == "338005"
    assert dh_shared(5, format(pow(2, 7, P), "x")).hex() ==         "0d2c6ab660f97893d7b57f47872f0ac4b773568d34c7596a216691d2ed4dcc93"
    assert pow(2, P - 1, P) == 1
    nets = _ipv4_nets()
    assert all(socket.inet_aton(a) and socket.inet_aton(m) for a, m in nets), nets

    # 两个实例在本机互相绑定 (A 是母端), 然后同步
    import tempfile
    runner = MainRunner()
    stop = threading.Event()

    def pump():
        while not stop.is_set():
            runner.pump()
            time.sleep(0.02)
    threading.Thread(target=pump, daemon=True).start()
    la, lb = _FakeLocal("A"), _FakeLocal("B")
    la.docs_["settings"]["DAILY_LIMIT"]["value"] = 3600.0
    la.docs_["hours"]["2026-01-01/9"] = "学习"
    lb.docs_["hours"]["2026-01-01/10"] = "游戏"
    lb.study = {"2025-12-31": 3.0}
    sa = SyncService(tempfile.mkdtemp(), la, runner, name="A", http_port=17950, udp_port=17951)
    sb = SyncService(tempfile.mkdtemp(), lb, runner, name="B", http_port=17960, udp_port=17961)
    try:
        sa.start()
        sb.start()
        assert sa.hello("127.0.0.1", sb.port)["id"] == sb.my_id

        # B 不是 Proxy 模式: 拒绝
        lb.mode = "adapter"
        sa.start_pairing("127.0.0.1", sb.port, mother_is_me=True)
        for _ in range(100):
            if sa.outgoing["state"] in ("error", "waiting"):
                break
            time.sleep(0.05)
        assert sa.outgoing["state"] == "error" and "not-proxy" in sa.outgoing["error"]
        lb.mode = "proxy"

        sa.start_pairing("127.0.0.1", sb.port, mother_is_me=True)
        for _ in range(100):
            if lb.requests and sa.outgoing["state"] == "waiting":
                break
            time.sleep(0.05)
        req = lb.requests[-1]
        assert req["code"] == sa.outgoing["code"], "两边显示同一个配对码"
        assert req["mother"] == sa.my_id
        runner.call(lambda: sb.answer_pairing(req["token"], True))
        for _ in range(200):
            if sa.outgoing["state"] == "accepted" and lb.cleared:
                break
            time.sleep(0.05)
        assert sa.outgoing["state"] == "accepted", sa.outgoing
        for _ in range(200):
            if lb.cleared and not sb.peers()[sa.my_id].get("init"):
                break
            time.sleep(0.05)
        # B 是子端: 用 A 的内容初始化 —— 自己的整点记录和历史被换掉
        assert lb.cleared == 1 and la.cleared == 0, (lb.cleared, la.cleared)
        assert "2026-01-01/10" not in la.docs_["hours"], "子端的旧数据不能传给母端"
        assert lb.docs_["settings"]["DAILY_LIMIT"]["value"] == 3600.0
        assert lb.docs_["hours"] == {"2026-01-01/9": "学习"}, lb.docs_["hours"]
        assert sa.my_id in sb.peers() and sb.my_id in sa.peers()
        # 绑定刚完成时的先后顺序不能变成"同步失败" (以前子端先同步过去会得到 401 unpaired)
        assert not sb.peers()[sa.my_id]["last_err"], sb.peers()[sa.my_id]
        assert not sa.peers()[sb.my_id]["last_err"], sa.peers()[sb.my_id]
        # 母端向还在初始化的子端同步: 不算出错
        assert sa._sync_with(sb.my_id) in (True, None)

        # 之后: 新的修改覆盖旧的, 账互相转交
        time.sleep(0.01)
        lb.docs_["hours"]["2026-01-01/11"] = "吃饭"
        lb.used = 600.0
        la.docs_["rules"]["black_domains"] = ["bilibili.com"]
        assert sb._sync_with(sa.my_id)
        assert la.docs_["hours"]["2026-01-01/11"] == "吃饭"
        assert lb.docs_["rules"]["black_domains"] == ["bilibili.com"]
        assert peer_net(sa.peer_ledgers(), "2026-01-01")["used"] == 600.0
        # 自动记录让位给自己填写的
        la.docs_["hours"]["2026-01-01/12"] = "写作业"
        lb.docs_["hours"]["2026-01-01/12"] = "Sleeping"
        assert sa._sync_with(sb.my_id)
        assert lb.docs_["hours"]["2026-01-01/12"] == "写作业"
        assert la.docs_["hours"]["2026-01-01/12"] == "写作业"
        # 删除也同步
        del la.docs_["hours"]["2026-01-01/9"]
        assert sa._sync_with(sb.my_id)
        assert "2026-01-01/9" not in lb.docs_["hours"]

        # 关闭前推送 (push_final): 不等回复里的内容, 对方照样并入
        la.docs_["timer"]["live"] = {"state": "idle", "owner": sa.my_id}
        assert sb.synced_since(0) and not sb.synced_since(_now_ms() + 60_000)
        sa.push_final(timeout=3.0)
        for _ in range(100):
            if lb.docs_["timer"].get("live") == {"state": "idle", "owner": sa.my_id}:
                break
            time.sleep(0.05)
        assert lb.docs_["timer"].get("live") == {"state": "idle", "owner": sa.my_id}, lb.docs_["timer"]

        # 解除绑定: 对方也解除
        runner.call(lambda: sa.unpair(sb.my_id))
        for _ in range(100):
            if not sb.peers():
                break
            time.sleep(0.05)
        assert not sa.peers() and not sb.peers()

        # 反过来: B 发起, 选 A 为母端 —— 发起方是子端, 拿到"已接受"后马上初始化
        lb.cleared = 0
        sb.start_pairing("127.0.0.1", sa.port, mother_is_me=False)
        for _ in range(100):
            if la.requests and sb.outgoing["state"] == "waiting":
                break
            time.sleep(0.05)
        req = la.requests[-1]
        assert req["mother"] == sa.my_id and req["code"] == sb.outgoing["code"]
        runner.call(lambda: sa.answer_pairing(req["token"], True))
        for _ in range(200):
            if sb.outgoing["state"] == "accepted" and not sb.peers().get(sa.my_id, {}).get("init", True):
                break
            time.sleep(0.05)
        assert sb.outgoing["state"] == "accepted" and lb.cleared == 1, (sb.outgoing, lb.cleared)
        assert not sb.peers()[sa.my_id]["last_err"] and not sa.peers()[sb.my_id]["last_err"]
        assert sa.peers()[sb.my_id]["last_ok"], "子端初始化时母端也记下了这次同步"
        runner.call(lambda: sa.unpair(sb.my_id))
        # 请求体读不出来 (例如太大): 回 400, 不再冒充"没绑定"
        assert sa._on_sync({})[0] == 400
    finally:
        stop.set()
        sa.stop()
        sb.stop()
    return "devsync selftest OK"


if __name__ == "__main__":
    print(_selftest())
