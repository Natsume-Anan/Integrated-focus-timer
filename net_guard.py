

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


LOAN_MULTIPLIER = 2.0
LOAN_MULTIPLIER_TOMORROW = 3.0


class NetGuard:

    def __init__(self, data_dir: str):
        self.dead = False
        self.state_file = os.path.join(data_dir, "net_state.json")
        self.log_file = os.path.join(data_dir, "net_requests.log")
        self.q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

        self.date = datetime.now().strftime('%Y-%m-%d')
        self.used = 0.0
        self.tomorrow_used = 0.0
        self.debt = 0.0
        self.grant_left = 0.0
        self.bucket_today = 0.0
        self.bucket_loan_q = 0.0
        self.bucket_loan_t = 0.0
        self.grant_loan = False
        self.pending = None
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
    def remaining(self) -> float:
        return max(0.0, self.limit - self.used - self.debt)

    @property
    def tomorrow_remaining(self) -> float:
        return max(0.0, self.limit - self.tomorrow_used)

    @property
    def quota_left(self) -> float:
        return (self.remaining / LOAN_MULTIPLIER
                + self.tomorrow_remaining / LOAN_MULTIPLIER_TOMORROW)

    @property
    def available(self) -> float:
        return self.quota_left

    @property
    def loan_quota_left(self) -> float:
        return self.tomorrow_remaining

    @property
    def dev_mode(self) -> bool:
        return bool(getattr(config, "DEV_MODE", False))

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
        return min(self.limit, self.used + self.debt)


    def _load(self):
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if d.get("date") == self.date:
                self.used = max(0.0, float(d.get("used", 0.0)))
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
    def _run(cmd: str):
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

    def block(self, sync: bool = False):

        if self.dead or self.dev_mode:
            return
        cmd = self._cmd(False)
        if sync:
            self._run(cmd)
        else:
            self.q.put(cmd)

    def unblock(self):
        self.q.put(self._cmd(True))

    def ensure_online(self):
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self._run(self._cmd(True))


    def loan_plan(self, minutes: float):
        need = max(0.0, float(minutes)) * 60.0

        today_time = min(need, self.remaining / LOAN_MULTIPLIER)
        today_cost = today_time * LOAN_MULTIPLIER

        rest = max(0.0, need - today_time)
        loan_cost = rest * LOAN_MULTIPLIER_TOMORROW
        total_cost = today_cost + loan_cost
        grant = today_time + rest
        return today_cost, loan_cost, total_cost, grant

    def max_grant(self) -> float:
        return (self.remaining / LOAN_MULTIPLIER
                + self.tomorrow_remaining / LOAN_MULTIPLIER_TOMORROW)

    def can_loan(self, minutes: float):
        need = max(0.0, float(minutes)) * 60.0
        if need <= 0:
            return False, "Minimum is 1 minute."
        if need <= self.remaining:
            return False, (f"{fmt_hm(need)} still fits in today's quota — no need to borrow. "
                           f"Use a normal request (or cancel and re-request).")
        if need > self.max_grant():
            left = self.max_grant()
            if left <= 0:
                return False, "No quota left today, and there is nothing to borrow."
            return False, (f"Loan can cover at most {fmt_hm(left)}: today "
                           f"{fmt_hm(self.remaining / LOAN_MULTIPLIER)} (2x) + borrowed "
                           f"{fmt_hm(self.tomorrow_remaining / LOAN_MULTIPLIER_TOMORROW)} (3x).")
        return True, ""


    def request(self, minutes: int, reason: str, loan: bool = False):
        if self.dev_mode:
            return False, "Developer mode is ON — the network is already unrestricted."
        if self.online:
            return False, "Already online."
        if self.pending:
            return False, "A request is already pending."
        minutes = int(minutes)
        if minutes < 1:
            return False, "Minimum is 1 minute."

        if loan:
            ok, msg = self.can_loan(minutes)
            if not ok:
                return False, msg
            _today, loan_cost, total_cost, grant = self.loan_plan(minutes)
            self.pending = {
                "minutes": minutes,
                "at": time.time(),
                "reason": reason,
                "loan": True,
                "today_cost": _today,
                "loan_cost": loan_cost,
                "total_cost": total_cost,
                "grant": grant,
            }
            self._log(
                f"LOAN     {minutes} min (grant {int(grant // 60)} min, "
                f"cost {int(total_cost // 60)} min quota, reason: {reason})"
            )
            return True, ""

        if minutes * 60 > self.remaining:
            extra = ""
            if self.available > self.remaining:
                extra = f" Emergency loan could cover up to {fmt_hm(self.available)} (2x cost)."
            return False, f"Only {fmt_hm(self.remaining)} left today.{extra}"
        self.pending = {
            "minutes": minutes,
            "at": time.time() + self.cooldown,
            "reason": reason,
            "loan": False,
        }
        self._log(f"REQUEST  {minutes} min  reason: {reason}")
        return True, ""

    def convert_to_loan(self):
        if not self.pending:
            return False, "No pending request."
        if self.pending.get("loan"):
            return False, "This request is already a loan."
        p = self.pending
        minutes = p["minutes"]
        ok, msg = self.can_loan(minutes)
        if not ok:
            return False, msg
        _today, loan_cost, total_cost, grant = self.loan_plan(minutes)
        self.pending = {
            "minutes": minutes, "at": time.time(), "reason": p.get("reason", ""),
            "loan": True, "today_cost": _today, "loan_cost": loan_cost,
            "total_cost": total_cost, "grant": grant,
        }
        self._log(f"LOAN     upgrade {minutes} min (cost {int(total_cost // 60)} min quota)")
        return True, ""

    def cancel(self):
        if self.pending:
            p = self.pending
            self._log(f"CANCEL   {p['minutes']} min {'loan ' if p.get('loan') else ''}request")
        self.pending = None

    def end_early(self):
        if self.dev_mode:
            return
        if self.online:
            self._refund()
            self._log(f"END      early, {int(self.grant_left)}s unused")
        self._reset_grant()
        self.block()
        self._save()

    def _reset_grant(self):
        self.grant_left = 0.0
        self.bucket_today = 0.0
        self.bucket_loan_q = 0.0
        self.bucket_loan_t = 0.0
        self.grant_loan = False

    def unused_loan_quota(self) -> float:
        return max(0.0, self.bucket_loan_q)

    def _refund(self):
        self.tomorrow_used = max(0.0, self.tomorrow_used - self.unused_loan_quota())

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
        self.debt = max(0.0, self.debt + self.tomorrow_used)
        self.tomorrow_used = 0.0
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
            if p.get("loan"):


                want = min(p["minutes"] * 60.0,
                           self.remaining / LOAN_MULTIPLIER
                           + self.tomorrow_remaining / LOAN_MULTIPLIER_TOMORROW)
                today_cost, loan_cost, _total, grant = self.loan_plan(want / 60.0)
                self.tomorrow_used += loan_cost
                self.bucket_today = today_cost
                self.bucket_loan_q = loan_cost
                self.bucket_loan_t = loan_cost / LOAN_MULTIPLIER_TOMORROW
                self.grant_loan = True
                secs = grant
            else:
                secs = min(p["minutes"] * 60, self.remaining)
                self.bucket_today = secs
                self.bucket_loan_q = 0.0
                self.bucket_loan_t = 0.0
                self.grant_loan = False
            if secs > 0:
                self.grant_left = secs
                self.unblock()
                self._save()
                self._log(f"START    {int(secs // 60)} min granted"
                          + (f" (loan, {int(self.bucket_loan_t // 60)} min borrowed)"
                             if self.grant_loan else ""))
                event = "started"

        now = time.monotonic()
        if self.online:
            dt = min(max(dt, 0.0), self.tick_clamp, self.grant_left)
            self.grant_left -= dt

            today_rate = LOAN_MULTIPLIER if self.grant_loan else 1.0
            take_today_time = min(dt, self.bucket_today / today_rate)
            self.bucket_today -= take_today_time * today_rate
            self.used += take_today_time * today_rate
            rest = dt - take_today_time
            if rest > 0:

                self.bucket_loan_t = max(0.0, self.bucket_loan_t - rest)
                charge = rest * LOAN_MULTIPLIER_TOMORROW
                self.bucket_loan_q = max(0.0, self.bucket_loan_q - charge)
                self.used += charge

            if self.grant_left <= 1e-6:
                self._reset_grant()
                self.block()
                self._save()
                self._log("END      time is up")
                event = "ended"
            elif now - self._last_save >= 5:
                self._save()
        elif now - self._last_enforce >= self.enforce_every:
            self._last_enforce = now
            if self.q.empty():
                self.block()
        return event



def _selftest():
    import tempfile
    import datetime as _dt
    import config

    saved = (config.DAILY_LIMIT, config.COOLDOWN,
             config.TICK_CLAMP, config.DEV_MODE)
    config.DAILY_LIMIT, config.COOLDOWN = 3600, 300
    config.TICK_CLAMP = 10 ** 6
    config.DEV_MODE = False
    try:
        n = NetGuard(tempfile.mkdtemp())
        n.dead = True
        n.date = _dt.datetime.now().strftime('%Y-%m-%d')
        assert n.remaining == 3600 and not n.online

        assert abs(n.max_grant() - (3600 / 2 + 3600 / 3)) < 1e-6, n.max_grant()
        assert abs(n.quota_left - n.max_grant()) < 1e-6


        ok, msg = n.can_loan(30)
        assert not ok and "no need to borrow" in msg, msg


        ok, msg = n.request(30, "查资料")
        assert ok and n.mode == "pending" and n.pending["at"] > time.time() + 200
        assert not n.pending["loan"]
        ok, msg = n.convert_to_loan()
        assert not ok, "今天额度足够时不该允许升级成贷款"


        n.cancel()
        n.used = 3000.0
        ok, msg = n.request(24, "查资料")
        assert not ok and "Emergency loan" in msg, msg
        ok, msg = n.request(24, "紧急", loan=True)
        assert ok and n.pending["loan"] and n.pending["at"] <= time.time() + 1, msg

        assert abs(n.pending["loan_cost"] - 3420) < 1e-6, n.pending["loan_cost"]

        n.tick(0.0)
        assert n.online, "贷款应当立刻联网"
        assert abs(n.bucket_today - 600) < 1e-6, n.bucket_today
        assert abs(n.bucket_loan_q - 3420) < 1e-6, n.bucket_loan_q
        assert abs(n.bucket_loan_t - 1140) < 1e-6, n.bucket_loan_t
        assert abs(n.grant_left - 1440) < 1e-6, n.grant_left
        assert abs(n.tomorrow_used - 3420) < 1e-6
        assert abs(n.tomorrow_remaining - 180) < 1e-6


        n.end_early()
        n._reset_grant()
        n.used, n.tomorrow_used, n.debt = 2400.0, 0.0, 0.0
        ok, msg = n.convert_to_loan()
        assert not ok and "No pending request" in msg, "没有申请时不能凭空贷款"

        ok, msg = n.request(5, "查资料")
        assert ok and not n.pending["loan"], msg
        ok, msg = n.convert_to_loan()
        assert not ok and "no need to borrow" in msg, msg
        n.cancel()

        ok, msg = n.request(25, "查资料")
        assert not ok and "Emergency loan" in msg, msg
        ok, msg = n.can_loan(25)
        assert ok, msg
        today_cost, loan_cost, _t, grant = n.loan_plan(25)
        assert abs(today_cost - 1200) < 1e-6, today_cost
        assert abs(loan_cost - 2700) < 1e-6, loan_cost
        assert abs(grant - 1500) < 1e-6, grant

        n.cancel()
        n._reset_grant()
        n.used = 2400.0
        ok, msg = n.request(25, "查资料")
        assert not ok and "Emergency loan" in msg, msg
        ok, msg = n.request(25, "紧急", loan=True)
        assert ok and n.pending["loan"], msg
        today_cost, loan_cost, _t, grant = n.loan_plan(25)
        assert abs(today_cost - 1200) < 1e-6, today_cost
        assert abs(loan_cost - 2700) < 1e-6, loan_cost
        assert abs(grant - 1500) < 1e-6, grant
        n.cancel()

        ok, msg = n.request(15, "查资料")
        assert ok and not n.pending["loan"], msg
        ok, msg = n.convert_to_loan()
        assert not ok and "no need to borrow" in msg, msg
        n.cancel()

        ok, msg = n.request(25, "查资料")
        assert not ok and "Emergency loan" in msg, msg
        ok, msg = n.request(25, "紧急", loan=True)
        assert ok and n.pending["loan"], msg
        n.cancel()


        n.cancel()
        n._reset_grant()
        n.used = 3000.0
        ok, msg = n.request(25, "紧急", loan=True)
        assert ok and n.pending["loan"], msg
        n.tick(0.0)
        assert abs(n.bucket_today - 600) < 1e-6, n.bucket_today
        assert abs(n.bucket_loan_q - 3600) < 1e-6, n.bucket_loan_q
        assert abs(n.bucket_loan_t - 1200) < 1e-6, n.bucket_loan_t
        assert abs(n.grant_left - 1500) < 1e-6, n.grant_left

        n.tick(30.0)
        assert abs(n.used - 3060) < 1e-6, n.used
        n.tick(10 ** 6)

        assert abs(n.used - 7200) < 1e-6, n.used
        assert not n.online, "本次批准用完后应当断网"
        assert abs(n.tomorrow_used - 3600) < 1e-6, n.tomorrow_used

        n.used, n.tomorrow_used, n.debt = 0.0, 0.0, 0.0
        n._reset_grant()


        n.used, n.tomorrow_used, n.debt = 3600.0, 0.0, 0.0
        n._reset_grant()
        assert abs(n.max_grant() - 1200) < 1e-6, n.max_grant()
        ok, msg = n.can_loan(20)
        assert ok, msg
        _t, loan_cost, total, grant = n.loan_plan(20)
        assert _t == 0.0 and abs(loan_cost - 3600) < 1e-6, loan_cost
        assert abs(total - 3600) < 1e-6 and abs(grant - 1200) < 1e-6
        ok, msg = n.can_loan(30)
        assert not ok and "Loan can cover at most" in msg, msg
        ok, msg = n.request(30, "x")
        assert not ok and "Only" in msg and "Emergency loan" in msg
        ok, msg = n.request(20, "紧急", loan=True)
        assert ok, msg
        n.tick(0.0)
        assert abs(n.grant_left - 1200) < 1e-6 and n.bucket_today == 0.0
        assert abs(n.bucket_loan_q - 3600) < 1e-6 and abs(n.bucket_loan_t - 1200) < 1e-6
        n.tick(60.0)
        assert abs(n.used - 3780) < 1e-6, n.used
        n.end_early()

        assert abs(n.tomorrow_used - 180) < 1e-6, n.tomorrow_used

        n.used, n.tomorrow_used, n.debt = 3600.0, 0.0, 0.0
        n._reset_grant()


        n.used, n.tomorrow_used, n.debt = 0.0, 0.0, 3000.0
        assert abs(n.remaining - 600) < 1e-6, n.remaining
        assert abs(n.quota_left - (600 / 2 + 3600 / 3)) < 1e-6, n.quota_left
        ok, msg = n.can_loan(200)
        assert not ok and "Loan can cover at most" in msg, msg
        ok, msg = n.request(70, "x", loan=True)
        assert not ok and "Loan can cover at most" in msg, msg


        n.debt = 0.0
        n.used = 3600.0
        ok, msg = n.request(20, "x", loan=True)
        assert ok and abs(n.pending["loan_cost"] - 3600) < 1e-6, n.pending["loan_cost"]
        n.cancel()
        assert n.pending is None and n.tomorrow_used == 0.0 and n.used == 3600.0


        n.cancel()
        n._reset_grant()
        n.used, n.tomorrow_used, n.debt = 3000.0, 0.0, 0.0
        ok, msg = n.request(24, "紧急", loan=True)
        assert ok, msg
        n.tick(0.0)
        assert abs(n.tomorrow_used - 3420) < 1e-6, n.tomorrow_used
        n._rollover("2099-01-01")
        assert n.used == 0.0 and n.date == "2099-01-01"
        assert n.tomorrow_used == 0.0
        assert abs(n.debt - 3420) < 1e-6, n.debt
        assert abs(n.remaining - (3600 - 3420)) < 1e-6, n.remaining


        n.debt, n.tomorrow_used, n.used = 0.0, 0.0, 0.0
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
        return "net_guard selftest OK"
    finally:
        (config.DAILY_LIMIT, config.COOLDOWN,
         config.TICK_CLAMP, config.DEV_MODE) = saved


if __name__ == "__main__":
    print(_selftest())
