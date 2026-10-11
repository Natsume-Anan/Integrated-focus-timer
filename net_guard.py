

import os
import sys
import json
import time
import queue
import threading
import subprocess
from datetime import datetime

import config
from config import fmt_hm
from netproxy import ProxyController


QUICK_MULTIPLIER = 2.0   # 快速访问: 免冷静期, 每联网 1 秒消耗 2 秒今日额度
LOAN_RATE = 2.0          # 紧急借贷: 今日额度 +1 秒, 明天额度 -2 秒


class NetGuard:

    def __init__(self, data_dir: str):
        self.dead = False
        self.state_file = os.path.join(data_dir, "net_state.json")
        self.log_file = os.path.join(data_dir, "net_requests.log")
        self.q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

        self.date = datetime.now().strftime('%Y-%m-%d')
        self.used = 0.0
        self.bonus = 0.0
        self.tomorrow_used = 0.0
        self.debt = 0.0
        self.grant_left = 0.0
        self.grant_rate = 1.0
        self.pending = None
        self.proxy = ProxyController(
            data_dir, mode_getter=lambda: getattr(config, "FILTER_MODE", "blacklist"),
            dev_getter=config.dev_mode_enabled)
        self._nic_off_by_fallback = False
        self._applied_mode = self.net_mode
        self._load()
        self._last_save = time.monotonic()
        self._last_enforce = time.monotonic()
        if self.dev_mode:
            self.ensure_online()
        else:
            self.block()


    @property
    def limit(self) -> float:
        return float(config.DAILY_LIMIT)

    @property
    def cooldown(self) -> float:
        return float(config.COOLDOWN)

    @property
    def enforce_every(self) -> float:
        return max(5.0, float(config.ENFORCE_EVERY))

    @property
    def tick_clamp(self) -> float:
        return float(config.TICK_CLAMP)

    @property
    def today_total(self) -> float:
        """今天的总额度 = 每日额度 + 今天借到的."""
        return self.limit + self.bonus

    @property
    def remaining(self) -> float:
        return max(0.0, self.today_total - self.used - self.debt)

    @property
    def tomorrow_remaining(self) -> float:
        return max(0.0, self.limit - self.tomorrow_used)

    @property
    def quick_left(self) -> float:
        """剩余额度按快速访问能换到多少联网时间."""
        return self.remaining / QUICK_MULTIPLIER

    @property
    def loan_left(self) -> float:
        """还能借多少今日额度."""
        return self.tomorrow_remaining / LOAN_RATE

    @property
    def grant_quick(self) -> bool:
        return self.grant_rate > 1.0

    @property
    def dev_mode(self) -> bool:
        return config.dev_mode_enabled()

    @property
    def net_mode(self) -> str:
        return "proxy" if getattr(config, "NET_MODE", "adapter") == "proxy" else "adapter"

    @property
    def online(self) -> bool:
        if self.dev_mode:
            return True
        return self.grant_left > 0

    @property
    def mode(self) -> str:
        if self.dev_mode:
            return "dev"
        if self.online:
            return "online"
        if self.pending:
            return "pending"
        return "offline"

    @property
    def quota_used(self) -> float:
        return min(self.today_total, self.used + self.debt)


    def _load(self):
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if d.get("date") == self.date:
                self.used = max(0.0, float(d.get("used", 0.0)))
                self.bonus = max(0.0, float(d.get("bonus", 0.0)))
                self.tomorrow_used = max(0.0, float(d.get("tomorrow_used", 0.0)))
                self.debt = max(0.0, float(d.get("debt", 0.0)))
        except Exception:
            pass

    def _save(self):
        if self.dead:
            return
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "date": self.date,
                    "used": int(self.used),
                    "bonus": int(self.bonus),
                    "tomorrow_used": int(self.tomorrow_used),
                    "debt": int(self.debt),
                }, f)
        except IOError:
            pass
        self._last_save = time.monotonic()

    def _log(self, text: str):
        if self.dead:
            return
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
        except IOError:
            pass


    def _cmd(self, online: bool) -> str:
        verb = "Enable" if online else "Disable"
        return f"Get-NetAdapter -Physical | {verb}-NetAdapter -Confirm:$false"

    @staticmethod
    def _run(cmd):
        if callable(cmd):
            try:
                cmd()
            except Exception:
                pass
            return
        if sys.platform != "win32":
            return
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True,
                creationflags=0x08000000
            )
        except Exception:
            pass

    def _worker(self):

        while True:
            self._run(self.q.get())

    def _proxy_apply(self, online: bool):
        """proxy 模式的「联网 / 断网」:网卡保持开着,只切换过滤代理的放行策略.

        任何一步失败都不能留下「没有任何限制」的状态 —— 离线时退回禁用网卡."""
        try:
            self.proxy.start()
            self.proxy.set_online(online)
            if self._nic_off_by_fallback:
                self._nic_off_by_fallback = False
                self._run(self._cmd(True))
        except Exception as e:
            self._log(f"PROXY    failed ({e}); falling back to adapter cut-off")
            if not online:
                self._nic_off_by_fallback = True
                self._run(self._cmd(False))

    def _enter_proxy(self):
        """先让过滤代理就位,再放开网卡 —— 切换瞬间不留空窗."""
        self._proxy_apply(self.online)
        if not self._nic_off_by_fallback:
            self._run(self._cmd(True))

    def _backend_set(self, online: bool, sync: bool = False):
        job = (lambda: self._proxy_apply(online)) if self.net_mode == "proxy" \
            else self._cmd(online)
        if sync:
            self._run(job)
        else:
            self.q.put(job)

    def block(self, sync: bool = False):

        if self.dead or self.dev_mode:
            return
        self._backend_set(False, sync)

    def unblock(self):
        self._backend_set(True)

    def ensure_online(self):
        """彻底解除限制:网卡全开 + 过滤代理关闭并还原系统代理."""
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self._nic_off_by_fallback = False
        self._run(self._cmd(True))
        self._run(lambda: self.proxy.stop(restore=True))

    def sync_mode(self):
        """设置里的 NET_MODE 变了(立即生效或冷静期到期)就切换后端;没变则什么都不做."""
        if self.dead or self._applied_mode == self.net_mode:
            return False
        self._applied_mode = self.net_mode
        if self.dev_mode:
            return True
        if self.net_mode == "proxy":
            self.q.put(self._enter_proxy)
        else:
            self.q.put(self._cmd(self.online))
            self.q.put(lambda: self.proxy.stop(restore=True))
        self._log(f"MODE     switched to {self.net_mode}")
        return True


    def can_borrow(self, minutes: float):
        add = max(0.0, float(minutes)) * 60.0
        if add <= 0:
            return False, "Minimum is 1 minute."
        if add > self.loan_left + 1e-6:
            if self.loan_left < 60:
                return False, "Tomorrow's quota is already fully borrowed."
            return False, (f"You can borrow at most {fmt_hm(self.loan_left)} today "
                           f"(tomorrow has {fmt_hm(self.tomorrow_remaining)} left, "
                           f"{LOAN_RATE:g}x per minute borrowed).")
        return True, ""

    def borrow(self, minutes: int, reason: str):
        """紧急借贷: 立即给今天加额度, 代价是明天扣两倍. 不联网, 联网仍需申请."""
        if self.dev_mode:
            return False, "Developer mode is ON — the network is already unrestricted."
        minutes = int(minutes)
        ok, msg = self.can_borrow(minutes)
        if not ok:
            return False, msg
        add = minutes * 60.0
        self.bonus += add
        self.tomorrow_used += add * LOAN_RATE
        self._save()
        self._log(f"LOAN     +{minutes} min today, -{int(minutes * LOAN_RATE)} min tomorrow"
                  f"  reason: {reason}")
        return True, ""

    def can_quick(self, minutes: float):
        need = max(0.0, float(minutes)) * 60.0
        if need <= 0:
            return False, "Minimum is 1 minute."
        if need * QUICK_MULTIPLIER > self.remaining + 1e-6:
            if self.quick_left < 60:
                return False, "Not enough quota left today for quick access."
            return False, (f"Quick access can cover at most {fmt_hm(self.quick_left)} "
                           f"({fmt_hm(self.remaining)} left today, {QUICK_MULTIPLIER:g}x cost).")
        return True, ""


    def request(self, minutes: int, reason: str, quick: bool = False):
        if self.dev_mode:
            return False, "Developer mode is ON — the network is already unrestricted."
        if self.online:
            return False, "Already online."
        if self.pending:
            return False, "A request is already pending."
        minutes = int(minutes)
        if minutes < 1:
            return False, "Minimum is 1 minute."

        if quick:
            ok, msg = self.can_quick(minutes)
            if not ok:
                return False, msg
            self.pending = {"minutes": minutes, "at": time.time(),
                            "reason": reason, "quick": True}
            self._log(f"QUICK    {minutes} min (cost {int(minutes * QUICK_MULTIPLIER)} min quota)"
                      f"  reason: {reason}")
            return True, ""

        if minutes * 60 > self.remaining:
            extra = ""
            if self.loan_left >= 60:
                extra = f" An emergency loan can add up to {fmt_hm(self.loan_left)}."
            return False, f"Only {fmt_hm(self.remaining)} left today.{extra}"
        self.pending = {
            "minutes": minutes,
            "at": time.time() + self.cooldown,
            "reason": reason,
            "quick": False,
        }
        self._log(f"REQUEST  {minutes} min  reason: {reason}")
        return True, ""

    def convert_to_quick(self):
        if not self.pending:
            return False, "No pending request."
        if self.pending.get("quick"):
            return False, "This request is already quick access."
        p = self.pending
        ok, msg = self.can_quick(p["minutes"])
        if not ok:
            return False, msg
        self.pending = {"minutes": p["minutes"], "at": time.time(),
                        "reason": p.get("reason", ""), "quick": True}
        self._log(f"QUICK    upgrade {p['minutes']} min "
                  f"(cost {int(p['minutes'] * QUICK_MULTIPLIER)} min quota)")
        return True, ""

    def cancel(self):
        if self.pending:
            p = self.pending
            self._log(f"CANCEL   {p['minutes']} min {'quick ' if p.get('quick') else ''}request")
        self.pending = None

    def end_early(self):
        if self.dev_mode:
            return
        if self.online:
            self._log(f"END      early, {int(self.grant_left)}s unused")
        self._reset_grant()
        self.block()
        self._save()

    def _reset_grant(self):
        self.grant_left = 0.0
        self.grant_rate = 1.0

    def shutdown(self):
        self.pending = None
        self._reset_grant()
        self._save()
        if not self.dev_mode:
            self.block(sync=True)

    def release(self):
        self.dead = True
        self.pending = None
        self._reset_grant()
        self.ensure_online()


    def release_restrictions(self):
        self.pending = None
        self._reset_grant()
        self._last_enforce = time.monotonic()
        self.ensure_online()
        self._log("DEV      network restrictions released")


    def _rollover(self, today: str):
        self.date = today
        self.debt = max(0.0, self.tomorrow_used)
        self.tomorrow_used = 0.0
        self.bonus = 0.0
        self.used = 0.0
        self._save()


    def tick(self, dt: float):
        if self.dev_mode:

            if self.pending:
                self.pending = None
                self._log("DEV      pending request dropped (developer mode)")
            return None

        today = datetime.now().strftime('%Y-%m-%d')
        if today != self.date:
            self._rollover(today)

        event = None
        if self.pending and time.time() >= self.pending["at"]:
            p, self.pending = self.pending, None
            self._reset_grant()
            rate = QUICK_MULTIPLIER if p.get("quick") else 1.0
            secs = min(p["minutes"] * 60.0, self.remaining / rate)
            if secs > 0:
                self.grant_left = secs
                self.grant_rate = rate
                self.unblock()
                self._save()
                self._log(f"START    {int(secs // 60)} min granted"
                          + (f" (quick, {rate:g}x)" if rate > 1.0 else ""))
                event = "started"

        now = time.monotonic()
        if self.online:
            dt = min(max(dt, 0.0), self.tick_clamp, self.grant_left)
            self.grant_left -= dt

            self.used += dt * self.grant_rate

            if self.grant_left <= 1e-6:
                self._reset_grant()
                self.block()
                self._save()
                self._log("END      time is up")
                event = "ended"
            elif now - self._last_save >= 5:
                self._save()
            if self.net_mode == "proxy" and now - self._last_enforce >= self.enforce_every:
                self._last_enforce = now
                if self.q.empty():
                    self.q.put(lambda: self._proxy_apply(self.online))
        elif now - self._last_enforce >= self.enforce_every:
            self._last_enforce = now
            if self.q.empty():
                self.block()
        return event



def _selftest():
    import tempfile
    import datetime as _dt
    import config

    had_dev = hasattr(config, "DEV_MODE")
    saved = (config.DAILY_LIMIT, config.COOLDOWN,
             config.TICK_CLAMP, getattr(config, "DEV_MODE", False))
    saved_mode = getattr(config, "NET_MODE", "adapter")
    config.DAILY_LIMIT, config.COOLDOWN = 3600, 300
    config.TICK_CLAMP = 10 ** 6
    config.DEV_MODE = False
    config.NET_MODE = "adapter"
    try:
        n = NetGuard(tempfile.mkdtemp())
        n.dead = True
        n.date = _dt.datetime.now().strftime('%Y-%m-%d')
        assert n.remaining == 3600 and not n.online
        assert abs(n.quick_left - 1800) < 1e-6 and abs(n.loan_left - 1800) < 1e-6

        # 普通申请: 走冷静期, 1x 计费
        ok, msg = n.request(30, "查资料")
        assert ok and n.mode == "pending" and n.pending["at"] > time.time() + 200
        assert not n.pending["quick"]
        n.pending["at"] = time.time() - 1
        n.tick(0.0)
        assert n.online and not n.grant_quick and abs(n.grant_left - 1800) < 1e-6
        n.tick(600.0)
        assert abs(n.used - 600) < 1e-6, n.used
        n.end_early()
        assert not n.online and abs(n.used - 600) < 1e-6

        # 快速访问: 立刻联网, 2x 计费, 没有冷静期
        ok, msg = n.request(10, "快", quick=True)
        assert ok and n.pending["quick"] and n.pending["at"] <= time.time() + 1, msg
        n.tick(0.0)
        assert n.online and n.grant_quick and abs(n.grant_left - 600) < 1e-6
        n.tick(60.0)
        assert abs(n.used - 720) < 1e-6, n.used
        n.end_early()
        assert abs(n.used - 720) < 1e-6, "提前结束不再额外扣费"

        # 快速访问上限 = 剩余 / 2
        n.used = 3000.0
        ok, msg = n.can_quick(6)
        assert not ok and "at most" in msg, msg
        ok, msg = n.request(5, "快", quick=True)
        assert ok, msg
        n.tick(0.0)
        n.tick(10 ** 6)
        assert abs(n.used - 3600) < 1e-6 and not n.online, n.used

        # 冷静期中可升级为快速访问
        n.used = 0.0
        ok, msg = n.request(20, "x")
        assert ok
        ok, msg = n.convert_to_quick()
        assert ok and n.pending["quick"] and n.pending["at"] <= time.time() + 1, msg
        ok, msg = n.convert_to_quick()
        assert not ok and "already" in msg
        n.cancel()
        assert n.pending is None
        n.used = 3000.0
        ok, msg = n.request(5, "x")
        assert ok
        ok, msg = n.convert_to_quick()
        assert ok, msg
        n.cancel()
        ok, msg = n.request(6, "x")
        assert ok
        ok, msg = n.convert_to_quick()
        assert not ok and "at most" in msg, msg
        n.cancel()
        ok, msg = n.convert_to_quick()
        assert not ok and "No pending request" in msg

        # 紧急借贷: 今天 +X, 明天 -2X, 不联网
        n.used = 3600.0
        assert n.remaining == 0.0
        ok, msg = n.request(10, "x")
        assert not ok and "emergency loan" in msg, msg
        ok, msg = n.borrow(20, "急")
        assert ok, msg
        assert not n.online and n.pending is None, "借贷本身不联网"
        assert abs(n.bonus - 1200) < 1e-6 and abs(n.remaining - 1200) < 1e-6
        assert abs(n.tomorrow_used - 2400) < 1e-6 and abs(n.tomorrow_remaining - 1200) < 1e-6
        assert abs(n.today_total - 4800) < 1e-6 and abs(n.quota_used - 3600) < 1e-6
        assert abs(n.loan_left - 600) < 1e-6
        ok, msg = n.can_borrow(11)
        assert not ok and "at most" in msg, msg
        ok, msg = n.borrow(10, "急")
        assert ok and abs(n.tomorrow_remaining) < 1e-6 and abs(n.remaining - 1800) < 1e-6
        ok, msg = n.borrow(1, "急")
        assert not ok and "fully borrowed" in msg, msg

        # 借来的额度既可走冷静期, 也可走快速访问
        ok, msg = n.request(10, "x", quick=True)
        assert ok, msg
        n.tick(0.0)
        n.tick(300.0)
        assert abs(n.used - 4200) < 1e-6, n.used
        n.end_early()

        # 跨日: 明天的 2x 变成欠款, 借到的额度清零
        n._rollover("2099-01-01")
        assert n.used == 0.0 and n.bonus == 0.0 and n.tomorrow_used == 0.0
        assert abs(n.debt - 3600) < 1e-6 and n.remaining == 0.0
        n._rollover("2099-01-02")
        assert n.debt == 0.0 and n.remaining == 3600, "欠款只扣一天, 不会滚雪球"

        # 存档往返
        n.dead = False
        n.date = _dt.datetime.now().strftime('%Y-%m-%d')
        n.used, n.bonus, n.tomorrow_used, n.debt = 100.0, 600.0, 1200.0, 300.0
        n._save()
        m = NetGuard.__new__(NetGuard)
        m.state_file, m.date = n.state_file, n.date
        m.used = m.bonus = m.tomorrow_used = m.debt = 0.0
        m._load()
        assert (m.used, m.bonus, m.tomorrow_used, m.debt) == (100.0, 600.0, 1200.0, 300.0)
        n.dead = True

        n.used, n.bonus, n.tomorrow_used, n.debt = 0.0, 0.0, 0.0, 0.0
        n._reset_grant()
        ok, msg = n.request(10, "x")
        assert ok and n.pending["at"] > time.time() + 200
        n.cancel()
        assert n.mode == "offline"


        config.DEV_MODE = True
        assert n.mode == "dev" and n.online, "开发者模式下网络应视为一直可用"
        assert n.block() is None
        ok, msg = n.request(30, "x")
        assert not ok and "Developer mode" in msg, msg
        assert n.tick(100.0) is None and n.used == 0.0, "开发者模式不计时"
        n.pending = {"minutes": 5, "at": time.time() - 1, "reason": "x", "loan": False}
        n.tick(0.0)
        assert n.pending is None, "开发者模式下挂起的申请应被丢弃"
        config.DEV_MODE = False
        assert n.mode == "offline" and not n.online


        class _FakeProxy:
            def __init__(self):
                self.calls = []
                self.fail = False
                self.online = None

            def start(self):
                self.calls.append("start")
                if self.fail:
                    raise OSError("boom")

            def set_online(self, v):
                self.calls.append(("online", v))
                self.online = v

            def stop(self, restore=True):
                self.calls.append(("stop", restore))

        fp = _FakeProxy()
        n.proxy = fp
        n.dead = False
        ran = []
        n._run = lambda cmd: ran.append(cmd if isinstance(cmd, str) else "<fn>") \
            or (cmd() if callable(cmd) else None)
        config.NET_MODE = "proxy"
        assert n.net_mode == "proxy" and n.sync_mode() and not n.sync_mode()
        while not n.q.empty():
            n._run(n.q.get_nowait())
        assert fp.online is False and "start" in fp.calls, fp.calls
        assert any("Enable-NetAdapter" in str(c) for c in ran), "进入 proxy 模式后网卡必须是开的"

        fp.calls.clear()
        n.block(sync=True)
        assert fp.online is False
        n.unblock()
        n._run(n.q.get_nowait())
        assert fp.online is True and not any("Disable-NetAdapter" in str(c) for c in ran[-3:])

        ran.clear()
        fp.fail = True
        n.block(sync=True)
        assert any("Disable-NetAdapter" in str(c) for c in ran), "代理起不来时必须退回禁用网卡"
        assert n._nic_off_by_fallback
        fp.fail = False
        n.block(sync=True)
        assert not n._nic_off_by_fallback and any("Enable-NetAdapter" in str(c) for c in ran)

        fp.calls.clear()
        config.NET_MODE = "adapter"
        assert n.sync_mode()
        while not n.q.empty():
            n._run(n.q.get_nowait())
        assert ("stop", True) in fp.calls

        fp.calls.clear()
        n.ensure_online()
        assert ("stop", True) in fp.calls
        config.NET_MODE = "adapter"
        return "net_guard selftest OK"
    finally:
        (config.DAILY_LIMIT, config.COOLDOWN,
         config.TICK_CLAMP, config.DEV_MODE) = saved
        config.NET_MODE = saved_mode
        if not had_dev and hasattr(config, "DEV_MODE"):
            del config.DEV_MODE


if __name__ == "__main__":
    print(_selftest())
