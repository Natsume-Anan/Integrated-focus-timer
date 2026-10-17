"""
从 GitHub 检查 / 安装更新 (MECHANICS.md 第 16 节)
──────────────────────────────────────────────
    检查   GET https://api.github.com/repos/<REPO>/releases/latest,
           发布的版本号取自名称或标签里的数字 (如 "1.2.0", "v1.2"), 和 config.APP_VERSION 比较
    安装   发布里有 windows / pc / python 字样的 .zip 附件就用它, 否则用这个标签的源码压缩包;
           解压后把程序文件覆盖到程序文件夹 (不删除多出来的文件, 不碰数据目录), 重启后生效.
           程序文件夹是 git 仓库 (开发者) 时只提示, 不覆盖.

只连 GitHub 的地址, 只走 https, 跳转也只能跳到 GitHub 的下载地址.
不经过系统代理 (OIT 自己的过滤代理), 所以 Proxy 断网方式下不管名单怎么写都能检查;
Adapter 方式离线时网卡是禁用的, 检查会失败, 下一次联网时再查.

    python updater.py       自检 (不联网)
"""

import json
import os
import re
import shutil
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import config

REPO = "Obliphur/Obliphur-s-Integrated-Terminal"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
ALLOWED_HOSTS = {"api.github.com", "github.com", "codeload.github.com",
                 "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
MAX_DOWNLOAD = 80 * 1024 * 1024
# 覆盖安装时跳过的东西: 安卓版, 版本库, 缓存
SKIP_DIRS = {"Android version", ".git", ".github", "__pycache__", ".vscode", ".idea"}


def parse_version(text):
    """'v1.2' / '1.2.0' / '1' → (1, 2, 0); 没有数字返回 None."""
    nums = re.findall(r"\d+", str(text or ""))
    if not nums:
        return None
    nums = [int(n) for n in nums[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def release_version(rel: dict):
    """发布的版本号: 名称里有就用名称的 (如标签 '1', 名称 '1.0.0'), 否则用标签的."""
    name, tag = rel.get("name") or "", rel.get("tag_name") or ""
    vn, vt = parse_version(name), parse_version(tag)
    if vn and re.search(r"\d+\.\d+", name):
        return vn
    return vt or vn


def vtext(v) -> str:
    return ".".join(str(x) for x in v) if v else "?"


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlsplit(newurl)
        if u.scheme != "https" or (u.hostname or "").lower() not in ALLOWED_HOSTS:
            raise urllib.error.HTTPError(newurl, code, "redirect to a non-GitHub address refused",
                                         headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, timeout: float):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or (u.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError("only GitHub https addresses are allowed")
    # ProxyHandler({}): 不走系统代理 (OIT 自己的过滤代理)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _CheckedRedirect())
    req = urllib.request.Request(url, headers={
        "User-Agent": f"OIT/{config.APP_VERSION}", "Accept": "application/vnd.github+json"})
    return opener.open(req, timeout=timeout)


def program_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def is_dev_checkout(target: str = None) -> bool:
    return os.path.isdir(os.path.join(target or program_dir(), ".git"))


def pick_download(rel: dict):
    """(下载地址, 是否是源码包). 优先用电脑版的 .zip 附件."""
    for a in rel.get("assets") or []:
        n = str(a.get("name") or "").lower()
        if n.endswith(".zip") and any(k in n for k in ("windows", "win", "pc", "python")):
            return a.get("browser_download_url"), False
    return rel.get("zipball_url"), True


def install_zip(zip_path: str, target: str) -> int:
    """把压缩包里的程序文件覆盖到 target. 返回覆盖的文件数. 找不到程序文件时抛 ValueError."""
    tmp = tempfile.mkdtemp(prefix="oit-update-")
    try:
        with zipfile.ZipFile(zip_path) as z:
            for info in z.infolist():
                p = os.path.normpath(info.filename)
                if p.startswith("..") or os.path.isabs(p):
                    raise ValueError("unsafe path in archive")
            z.extractall(tmp)
        root = None
        for dirpath, dirnames, filenames in os.walk(tmp):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            if "main.py" in filenames and "app.py" in filenames:
                root = dirpath
                break
        if root is None:
            raise ValueError("main.py / app.py not found in the archive")
        n = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            rel = os.path.relpath(dirpath, root)
            dest_dir = target if rel == "." else os.path.join(target, rel)
            os.makedirs(dest_dir, exist_ok=True)
            for f in filenames:
                if f.endswith((".pyc", ".pyo")):
                    continue
                shutil.copy2(os.path.join(dirpath, f), os.path.join(dest_dir, f))
                n += 1
        return n
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Updater:
    """state: idle / checking / latest / available / downloading / installed / dev / error"""

    def __init__(self):
        self.state = "idle"
        self.current = parse_version(config.APP_VERSION)
        self.latest = None
        self.release = None
        self.error = ""
        self._lock = threading.Lock()

    @property
    def latest_text(self) -> str:
        return vtext(self.latest)

    def check(self, done=None):
        """后台线程里检查; 完成后在那个线程里调用 done(self)."""
        with self._lock:
            if self.state in ("checking", "downloading"):
                return
            self.state = "checking"

        def run():
            try:
                with _open(API_LATEST, 20) as r:
                    rel = json.loads(r.read(2_000_000).decode("utf-8"))
                v = release_version(rel)
                if not v:
                    raise ValueError("no version number in the release")
                self.release, self.latest = rel, v
                self.state = "available" if v > self.current else "latest"
                self.error = ""
            except Exception as e:      # noqa: BLE001 —— 显示给用户
                self.state, self.error = "error", str(e) or type(e).__name__
            if done:
                done(self)
        threading.Thread(target=run, daemon=True).start()

    def install(self, done=None):
        """下载并覆盖程序文件; 完成后调用 done(self). 成功后 state = installed."""
        if self.state != "available" or not self.release:
            return
        if is_dev_checkout():
            self.state = "dev"
            if done:
                done(self)
            return
        self.state = "downloading"

        def run():
            path = None
            try:
                url, _src = pick_download(self.release)
                if not url:
                    raise ValueError("nothing to download")
                fd, path = tempfile.mkstemp(suffix=".zip", prefix="oit-")
                with os.fdopen(fd, "wb") as f, _open(url, 60) as r:
                    total = 0
                    while True:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_DOWNLOAD:
                            raise ValueError("download too large")
                        f.write(chunk)
                install_zip(path, program_dir())
                self.state, self.error = "installed", ""
            except Exception as e:      # noqa: BLE001
                self.state, self.error = "error", str(e) or type(e).__name__
            finally:
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            if done:
                done(self)
        threading.Thread(target=run, daemon=True).start()


def _selftest():
    assert parse_version("1") == (1, 0, 0) and parse_version("v1.2") == (1, 2, 0)
    assert parse_version("Python") is None and parse_version("1.2.3.4") == (1, 2, 3)
    assert release_version({"tag_name": "1", "name": "1.0.0"}) == (1, 0, 0)
    assert release_version({"tag_name": "v2.1", "name": "Spring update"}) == (2, 1, 0)
    assert (1, 1, 0) > (1, 0, 0) and parse_version(config.APP_VERSION)
    assert pick_download({"assets": [{"name": "OIT-android.apk", "browser_download_url": "a"},
                                     {"name": "OIT-windows.zip", "browser_download_url": "b"}],
                          "zipball_url": "z"}) == ("b", False)
    assert pick_download({"assets": [], "zipball_url": "z"}) == ("z", True)
    for bad in ("http://api.github.com/x", "https://evil.example.com/x"):
        try:
            _open(bad, 1)
            raise AssertionError(bad)
        except ValueError:
            pass

    # 覆盖安装: 源码包的顶层文件夹, 跳过安卓版, 不删多余文件
    src = tempfile.mkdtemp()
    zp = os.path.join(src, "a.zip")
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("Obliphur-OIT-abc/main.py", "print('new')")
        z.writestr("Obliphur-OIT-abc/app.py", "x = 1")
        z.writestr("Obliphur-OIT-abc/pages/settings_page.py", "y = 2")
        z.writestr("Obliphur-OIT-abc/Android version/build.gradle.kts", "no")
    target = tempfile.mkdtemp()
    with open(os.path.join(target, "keep.txt"), "w") as f:
        f.write("mine")
    assert install_zip(zp, target) == 3
    assert open(os.path.join(target, "main.py")).read() == "print('new')"
    assert os.path.exists(os.path.join(target, "pages", "settings_page.py"))
    assert not os.path.exists(os.path.join(target, "Android version"))
    assert os.path.exists(os.path.join(target, "keep.txt"))
    bad = os.path.join(src, "b.zip")
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("README.md", "no program")
    try:
        install_zip(bad, target)
        raise AssertionError("archive without program accepted")
    except ValueError:
        pass
    os.makedirs(os.path.join(target, ".git"))
    assert is_dev_checkout(target)
    return "updater selftest OK"


if __name__ == "__main__":
    print(_selftest())
