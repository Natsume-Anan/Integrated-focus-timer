# -*- coding: utf-8 -*-
"""
联网守卫：申请制联网控制
启动、退出、异常时一律断网
"""

import os
import sys
import json
import time
import queue
import threading
import subprocess
from datetime import datetime

from config import (
    DAILY_LIMIT, COOLDOWN, BLOCK_MODE, ENFORCE_EVERY, TICK_CLAMP,
    fmt_hm
)


class NetGuard:
    """
    申请制联网:
      request() → 冷静期(COOLDOWN) → 自动联网 → 额度耗尽/提前结束 → 断网
    设计原则 fail-closed:启动、退出、异常时一律断网;冷静期中的申请重启即作废。
    """

    def __init__(self, data_dir: str):
        self.dead = False            # 卸载后置 True:不再写盘、不再断网
        self.state_file = os.path.join(data_dir, "net_state.json")
        self.log_file = os.path.join(data_dir, "net_requests.log")
        self.q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

        self.date = datetime.now().strftime('%Y-%m-%d')
        self.used = 0.0              # 今日已联网秒数
        self.grant_left = 0.0        # 当前这次批准剩余秒数
        self.pending = None          # {"minutes", "at"(epoch), "reason"}
        self._load()
        self._last_save = time.monotonic()
        self._last_enforce = time.monotonic()
        self.block()                 # 启动即断网

    # ── 状态属性 ──
    @property
    def remaining(self) -> float:
        return max(0.0, DAILY_LIMIT - self.used)

    @property
    def online(self) -> bool:
        return self.grant_left > 0

    @property
    def mode(self) -> str:
        if self.online:
            return "online"
        if self.pending:
            return "pending"
        return "offline"

    # ── 持久化 ──
    def _load(self):
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if d.get("date") == self.date:
                self.used = float(d.get("used", 0.0))
        except Exception:
            pass

    def _save(self):
        if self.dead:
            return
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump({"date": self.date, "used": int(self.used)}, f)
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

    # ── 系统命令 ──
    def _cmd(self, online: bool) -> str:
        if BLOCK_MODE == "adapter":
            verb = "Enable" if online else "Disable"
            return f"Get-NetAdapter -Physical | {verb}-NetAdapter -Confirm:$false"
        rule = "FocusNet_BLOCK"
        if online:
            return f'netsh advfirewall firewall delete rule name="{rule}"'
        return (f'netsh advfirewall firewall delete rule name="{rule}" | Out-Null; '
                f'netsh advfirewall firewall add rule name="{rule}" dir=out action=block profile=any')

    @staticmethod
    def _run(cmd: str):
        if sys.platform != "win32":
            return
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
        except Exception:
            pass

    def _worker(self):
        # 单线程顺序执行,保证 block/unblock 不会乱序,也不阻塞界面
        while True:
            self._run(self.q.get())

    def block(self, sync: bool = False):
        if self.dead:
            return
        cmd = self._cmd(False)
        if sync:
            self._run(cmd)
        else:
            self.q.put(cmd)

    def unblock(self):
        self.q.put(self._cmd(True))

    # ── 用户操作 ──
    def request(self, minutes: int, reason: str):
        if self.online:
            return False, "Already online."
        if self.pending:
            return False, "A request is already pending."
        if minutes < 1:
            return False, "Minimum is 1 minute."
        if minutes * 60 > self.remaining:
            return False, f"Only {fmt_hm(self.remaining)} left today."
        self.pending = {
            "minutes": minutes,
            "at": time.time() + COOLDOWN,
            "reason": reason
        }
        self._log(f"REQUEST  {minutes} min  reason: {reason}")
        return True, ""

    def cancel(self):
        if self.pending:
            self._log(f"CANCEL   {self.pending['minutes']} min request")
        self.pending = None

    def end_early(self):
        if self.online:
            self._log(f"END      early, {int(self.grant_left)}s unused")
        self.grant_left = 0.0
        self.block()
        self._save()

    def shutdown(self):
        self.pending = None
        self.grant_left = 0.0
        self._save()
        self.block(sync=True)

    def release(self):
        """卸载专用:丢弃待执行命令,同步恢复联网,并停止一切写盘/断网"""
        self.dead = True
        self.pending = None
        self.grant_left = 0.0
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        self._run(self._cmd(True))     # 同步执行,确保卸载前网络已恢复

    # ── 每秒调用一次 ──
    def tick(self, dt: float):
        """返回 "started" / "ended" / None"""
        today = datetime.now().strftime('%Y-%m-%d')
        if today != self.date:
            self.date, self.used = today, 0.0
            self._save()

        event = None
        if self.pending and time.time() >= self.pending["at"]:
            p, self.pending = self.pending, None
            secs = min(p["minutes"] * 60, self.remaining)
            if secs > 0:
                self.grant_left = secs
                self.unblock()
                self._log(f"START    {int(secs // 60)} min granted")
                event = "started"

        now = time.monotonic()
        if self.online:
            dt = min(max(dt, 0.0), TICK_CLAMP)
            self.used += dt
            self.grant_left -= dt
            if self.grant_left <= 0 or self.remaining <= 0:
                self.grant_left = 0.0
                self.block()
                self._save()
                self._log("END      time is up")
                event = "ended"
            elif now - self._last_save >= 5:
                self._save()
        elif now - self._last_enforce >= ENFORCE_EVERY:
            self._last_enforce = now
            if self.q.empty():
                self.block()
        return event
