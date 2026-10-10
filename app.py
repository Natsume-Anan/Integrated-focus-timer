# -*- coding: utf-8 -*-
"""
主应用程序：页面编排、计时器、网络调度、卸载
"""

import sys
import os
import time
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime, timedelta, time as dt_time

from config import (
    COLORS, APP_NAME, IDLE, RUNNING, READY_BREAK, ON_BREAK,
    DAILY_LIMIT, COOLDOWN, LOG_HOURS, CHIME_WAV,
    compute_F, show_topmost_info, fmt_hm, fmt_ms
)
from net_guard import NetGuard
from data_manager import DataManager
from pages import CalendarPage, HourLogPage


class BreakTimerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_NAME)
        root.configure(bg=COLORS["bg"])
        root.resizable(False, False)

        # DPI 感知 (Windows)
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self._theme_ttk()

        # ── 状态 ──
        self.state = IDLE
        self.start_mono = None
        self.start_wall = None
        self.last_t_minutes = 0.0
        self.countdown_seconds = 0
        self.update_job = None
        self.midnight_job = None
        self.hourly_job = None
        self.net_job = None
        self.next_hour = None
        self.current_page = "timer"

        # ── 数据与网络 ──
        self.dm = DataManager()
        self.net = NetGuard(self.dm.data_dir)
        self._net_view = None
        self._net_last = time.monotonic()
        self.var_min = tk.StringVar(value="15")
        self.var_reason = tk.StringVar()
        self.var_confirm = tk.StringVar()
        self.var_del_self = tk.BooleanVar(value=False)

        self._build_layout(root)
        self.show_page("timer")

        self.refresh_display()
        self._start_midnight_timer()
        self._schedule_hourly()
        self._net_tick()

        self.root.bind("<Map>", self._on_window_map)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.var_confirm.trace_add("write", self._on_confirm_change)

    # ───────────── 主题 ─────────────
    def _theme_ttk(self):
        s = self.style
        bg, card = COLORS["bg"], COLORS["bg_card"]
        ac, tx = COLORS["accent"], COLORS["text"]
        td = COLORS["text_dim"]

        s.configure("Card.TFrame", background=card)
        s.configure("TopBar.TFrame", background=COLORS["accent"])

        s.configure("UI.TLabel", background=bg, foreground=td, font=("Segoe UI", 10))
        s.configure("UI.Bold.TLabel", background=bg, foreground=tx, font=("Segoe UI", 11, "bold"))
        s.configure("Card.TLabel", background=card, foreground=tx, font=("Segoe UI", 10))
        s.configure("Card.Bold.TLabel", background=card, foreground="#0f172a", font=("Segoe UI", 11, "bold"))

        s.configure(
            "Accent.TButton",
            background=ac, foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            borderwidth=0, focusthickness=0, padding=(18, 10)
        )
        s.map(
            "Accent.TButton",
            background=[("active", COLORS["accent_hover"]), ("disabled", "#94a3b8")],
            foreground=[("disabled", "#cbd5e1")]
        )

        s.configure("UI.TSeparator", background=COLORS["border"])
        s.configure(
            "Quota.Horizontal.TProgressbar",
            troughcolor=COLORS["border"], background=ac,
            borderwidth=0, thickness=8
        )
        s.configure(
            "Danger.TButton",
            background=COLORS["danger"], foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            borderwidth=0, focusthickness=0, padding=(18, 10)
        )
        s.map(
            "Danger.TButton",
            background=[("active", COLORS["danger_hover"]), ("disabled", "#fca5a5")],
            foreground=[("disabled", "#ffffff")]
        )

    # ───────────── 总布局 ─────────────
    def _build_layout(self, parent):
        bg, card = COLORS["bg"], COLORS["bg_card"]

        tk.Frame(parent, bg=COLORS["accent"], height=4).pack(fill="x")

        shell = tk.Frame(parent, bg=bg)
        shell.pack(fill="both", expand=True)

        # 侧栏
        side = tk.Frame(shell, bg=card, highlightbackground=COLORS["border"], highlightthickness=1)
        side.pack(side="left", fill="y")
        tk.Frame(side, bg=card, height=14).pack()

        self.nav_btns = {}
        self.nav_labels = {
            "cal": "📅  Calendar",
            "log": "📝  Hour Log",
            "net": "🌐  Network",
            "timer": "⏱  Timer",
            "uninstall": "🗑  Uninstall"
        }
        for key, label in self.nav_labels.items():
            b = tk.Button(
                side, text=label, anchor="w", width=15,
                font=("Segoe UI", 11), relief="flat", bd=0,
                padx=14, pady=12, cursor="hand2",
                command=lambda k=key: self.show_page(k)
            )
            b.pack(fill="x", pady=(0, 2))
            self.nav_btns[key] = b

        # 页面容器
        self.content = tk.Frame(shell, bg=bg)
        self.content.pack(side="left", fill="both", expand=True)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.pages["cal"] = CalendarPage(self.content, self.dm)
        self.pages["log"] = HourLogPage(
            self.content, self.dm,
            on_text_changed=self.update_log_badge,
            on_toggle=self.on_hour_log_toggle
        )
        self.pages["net"] = tk.Frame(self.content, bg=bg)
        self.pages["timer"] = tk.Frame(self.content, bg=bg)
        self.pages["uninstall"] = tk.Frame(self.content, bg=bg)
        for f in self.pages.values():
            f.grid(row=0, column=0, sticky="nsew")

        self._build_net_page(self.pages["net"])
        self._build_timer_page(self.pages["timer"])
        self._build_uninstall_page(self.pages["uninstall"])

    def show_page(self, key: str):
        self.current_page = key
        self.pages[key].tkraise()
        for k, b in self.nav_btns.items():
            if k == key:
                b.config(
                    bg=COLORS["accent"], fg="#ffffff",
                    activebackground=COLORS["accent_hover"], activeforeground="#ffffff"
                )
            else:
                b.config(
                    bg=COLORS["bg_card"], fg=COLORS["text"],
                    activebackground=COLORS["border"], activeforeground=COLORS["text"]
                )
        if key == "cal":
            self.pages["cal"].refresh()
        elif key == "net":
            self.refresh_net(force=True)
        elif key == "log":
            self.pages["log"].show()
        elif key == "uninstall":
            self.refresh_uninstall()
        self.update_log_badge()

    # ───────────── 计时器页 ─────────────
    def _build_timer_page(self, body):
        bg, card = COLORS["bg"], COLORS["bg_card"]

        hdr = tk.Frame(body, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(22, 8))
        tk.Label(
            hdr, text="⏱  Focus Timer", bg=bg, fg=COLORS["text"],
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w")
        tk.Label(
            hdr, text="Start working → finish → take a break",
            bg=bg, fg=COLORS["text_dim"], font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(4, 0))

        ttk.Separator(body, orient="horizontal", style="UI.TSeparator").pack(fill="x", padx=26)

        card_fr = tk.Frame(
            body, bg=card, highlightbackground=COLORS["border"],
            highlightthickness=1, relief="solid", bd=0
        )
        card_fr.pack(padx=26, pady=20, fill="x")
        inner = tk.Frame(card_fr, bg=card)
        inner.pack(padx=22, pady=18, fill="both")

        status_row = tk.Frame(inner, bg=card)
        status_row.pack(anchor="w", pady=(0, 12))
        self.dot_canvas = tk.Canvas(status_row, width=12, height=12, bg=card, highlightthickness=0)
        self.dot_canvas.pack(side="left", padx=(0, 8))
        self.dot_id = self.dot_canvas.create_oval(1, 1, 11, 11, fill=COLORS["text_dim"], outline="")
        self.lbl_status = tk.Label(
            status_row, text="Ready", bg=card, fg=COLORS["text_dim"],
            font=("Segoe UI", 10)
        )
        self.lbl_status.pack(side="left")

        self.lbl_time = tk.Label(
            inner, text="0.00 min", bg=card, fg=COLORS["text"],
            font=("Segoe UI", 36, "bold"), anchor="w"
        )
        self.lbl_time.pack(anchor="w", pady=(2, 6))

        self.lbl_sub = tk.Label(
            inner, text="Press [Start] when you begin focusing.",
            bg=card, fg=COLORS["text_dim"], font=("Segoe UI", 10), anchor="w"
        )
        self.lbl_sub.pack(anchor="w")

        stats_frame = tk.Frame(inner, bg=card)
        stats_frame.pack(anchor="w", pady=(14, 0), fill="x")
        self.lbl_today = tk.Label(
            stats_frame, text="Today: 0.0 h", bg=card, fg=COLORS["accent"],
            font=("Segoe UI", 10, "bold")
        )
        self.lbl_today.pack(side="left", padx=(0, 30))
        self.lbl_yesterday = tk.Label(
            stats_frame, text="Yesterday: 0.0 h", bg=card,
            fg=COLORS["text_dim"], font=("Segoe UI", 10)
        )
        self.lbl_yesterday.pack(side="left")

        btn_row = tk.Frame(body, bg=bg)
        btn_row.pack(fill="x", padx=26, pady=(6, 22))
        self.btn_action = ttk.Button(
            btn_row, text="▶  Start", style="Accent.TButton",
            command=self.on_action
        )
        self.btn_action.pack(ipadx=10)

        self._set_dot(COLORS["text_dim"])

    def _set_dot(self, color_hex: str):
        self.dot_canvas.itemconfig(self.dot_id, fill=color_hex)

    def _status(self, text: str, dot_color: str):
        self.lbl_status.config(text=text)
        self._set_dot(dot_color)

    def on_action(self):
        if self.state == IDLE:
            self.start_mono = time.monotonic()
            self.start_wall = datetime.now()
            self.state = RUNNING
            self.btn_action.config(text="■  Finish")
            self._status("Focusing…", COLORS["accent"])
            self.lbl_sub.config(text="Clock is running — click [Finish] when done.")
            self.schedule_update()

        elif self.state == RUNNING:
            end_wall = datetime.now()
            elapsed_minutes = (time.monotonic() - self.start_mono) / 60.0
            self.last_t_minutes = elapsed_minutes
            self.dm.add_study_session(self.start_wall, end_wall, elapsed_minutes)
            self.refresh_display()

            self.state = READY_BREAK
            self.btn_action.config(text="☕  Have a break")
            self.cancel_update()
            fval = compute_F(self.last_t_minutes)
            m = int(fval)
            s = int((fval - m) * 60)
            self.lbl_time.config(text=f"{m:02d}:{s:02d}")
            self.lbl_sub.config(text=f"Worked {self.last_t_minutes:.2f} min  →  suggested rest above")
            self._status("Work session done", COLORS["success"])

        elif self.state == READY_BREAK:
            fval = compute_F(self.last_t_minutes)
            if fval <= 0:
                show_topmost_info("Info", "Remaining time is 0. Resetting.", self.root)
                self.reset_to_idle()
                return
            self.countdown_seconds = max(1, int(round(fval * 60.0)))
            self.state = ON_BREAK
            self.btn_action.config(state="disabled")
            self._status("On break ☕", COLORS["warn"])
            self.lbl_sub.config(text="Relax. Timer counting down…")
            self.schedule_update()

    def schedule_update(self):
        self.cancel_update()
        self.update()

    def cancel_update(self):
        if self.update_job:
            self.root.after_cancel(self.update_job)
            self.update_job = None

    def update(self):
        if self.state == RUNNING:
            elapsed = time.monotonic() - self.start_mono
            cur_m = elapsed / 60.0
            self.lbl_time.config(text=f"{cur_m:.2f} min")
            rem = compute_F(cur_m)
            if rem > 0:
                self.lbl_sub.config(text=f"Projected break when you stop:  {rem:.2f} min")
            else:
                self.lbl_sub.config(text="Projected break: 0.00 min")
            self.update_job = self.root.after(200, self.update)

        elif self.state == ON_BREAK:
            if self.countdown_seconds > 0:
                m = self.countdown_seconds // 60
                s = self.countdown_seconds % 60
                self.lbl_time.config(text=f"{m:02d}:{s:02d}")
                self.lbl_sub.config(text=f"Break ends in {m}m {s:02d}s")
                self.countdown_seconds -= 1
                self.update_job = self.root.after(1000, self.update)
            else:
                show_topmost_info("Info", "Break finished. Ready for next round!", self.root)
                self.reset_to_idle()
        else:
            self.cancel_update()

    def reset_to_idle(self):
        self.cancel_update()
        self.state = IDLE
        self.start_mono = None
        self.start_wall = None
        self.last_t_minutes = 0.0
        self.countdown_seconds = 0
        self.btn_action.config(text="▶  Start", state="!disabled")
        self.lbl_time.config(text="0.00 min")
        self.lbl_sub.config(text="Press [Start] when you begin focusing.")
        self._status("Ready", COLORS["text_dim"])

    def refresh_display(self):
        self.lbl_today.config(text=f"Today: {self.dm.get_today_hours():.1f} h")
        self.lbl_yesterday.config(text=f"Yesterday: {self.dm.get_yesterday_hours():.1f} h")

    # ───────────── 定时任务 ─────────────
    def _start_midnight_timer(self):
        self._schedule_midnight()

    def _schedule_midnight(self):
        now = datetime.now()
        next_midnight = datetime.combine(now.date() + timedelta(days=1), dt_time.min)
        remaining = (next_midnight - now).total_seconds()
        if remaining <= 0:
            remaining = 86400.0
        delay_ms = int(remaining * 1000) + 100
        self.midnight_job = self.root.after(delay_ms, self._on_midnight)

    def _on_midnight(self):
        old_date = self.dm.today_date
        self.dm.today_date = datetime.now().strftime('%Y-%m-%d')
        if old_date[:7] != self.dm.today_date[:7]:
            self.dm.clear_last_month_except_yesterday()
        self.dm.prompt_slot = None
        self.dm.finalize_hours()
        self.dm.save_hour_log()
        self.update_log_badge()
        self.pages["log"].refresh()
        self.refresh_display()
        self._schedule_midnight()

    def _schedule_hourly(self):
        now = datetime.now()
        self.next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        remaining = (self.next_hour - now).total_seconds()
        if remaining <= 0:
            remaining = 3600.0
        delay_ms = int(remaining * 1000) + 100
        self.hourly_job = self.root.after(delay_ms, self._on_hour)

    def _on_hour(self):
        slot = self.next_hour - timedelta(hours=1)
        self._schedule_hourly()
        self.dm.finalize_hours()
        if not self.dm.hour_enabled:      # 开关关闭:不提示、不催填
            self.update_log_badge()
            return
        if slot.hour >= LOG_HOURS:
            return
        self._wait_chime(self._play_chime(), slot)

    def _play_chime(self):
        if sys.platform != "win32":
            self.root.bell()
            return None

        def run():
            try:
                import winsound
                if CHIME_WAV and os.path.exists(CHIME_WAV):
                    winsound.PlaySound(CHIME_WAV, winsound.SND_FILENAME)
                else:
                    for freq, ms in ((784, 200), (988, 200), (1319, 450)):
                        winsound.Beep(freq, ms)
            except Exception:
                pass
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t

    def _wait_chime(self, t, slot):
        if t is not None and t.is_alive():
            self.root.after(200, lambda: self._wait_chime(t, slot))
            return
        if not self.dm.hour_enabled:      # 提示音播放期间被关掉
            return
        self.dm.prompt_slot = slot
        self.update_log_badge()
        if self.current_page == "log":
            self.pages["log"].show()
        else:
            self.pages["log"].refresh()

    def _on_window_map(self, event):
        if hasattr(self, 'dm'):
            expected = datetime.now().strftime('%Y-%m-%d')
            if expected != self.dm.today_date:
                self._on_midnight()

    def on_close(self):
        for job in (self.midnight_job, self.hourly_job, self.update_job, self.net_job):
            if job:
                self.root.after_cancel(job)
        self.net.shutdown()
        self.root.destroy()

    def update_log_badge(self):
        b = self.nav_btns.get("log")
        if not b:
            return
        if not self.dm.hour_enabled:
            b.config(text=self.nav_labels["log"] + "  (off)")
        else:
            b.config(text=self.nav_labels["log"] + (" ●" if self.dm.awaiting_slot() else ""))

    def on_hour_log_toggle(self, enabled: bool):
        """整点记录开关变化:刷新侧栏标记与提示状态"""
        self.update_log_badge()
        self.pages["log"].refresh()

    # ───────────── 联网申请页 ─────────────
    def _build_net_page(self, page):
        bg, card = COLORS["bg"], COLORS["bg_card"]

        hdr = tk.Frame(page, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(22, 8))
        tk.Label(
            hdr, text="🌐  Network Access", bg=bg, fg=COLORS["text"],
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w")
        tk.Label(
            hdr, text=f"Request → {COOLDOWN // 60} min cooldown → online → auto cut-off",
            bg=bg, fg=COLORS["text_dim"], font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(4, 0))

        ttk.Separator(page, orient="horizontal", style="UI.TSeparator").pack(fill="x", padx=26)

        card_fr = tk.Frame(
            page, bg=card, highlightbackground=COLORS["border"],
            highlightthickness=1, relief="solid", bd=0
        )
        card_fr.pack(padx=26, pady=20, fill="x")
        inner = tk.Frame(card_fr, bg=card)
        inner.pack(padx=22, pady=18, fill="both")

        status_row = tk.Frame(inner, bg=card)
        status_row.pack(anchor="w", pady=(0, 12))
        self.net_dot_canvas = tk.Canvas(status_row, width=12, height=12, bg=card, highlightthickness=0)
        self.net_dot_canvas.pack(side="left", padx=(0, 8))
        self.net_dot_id = self.net_dot_canvas.create_oval(1, 1, 11, 11, fill=COLORS["text_dim"], outline="")
        self.net_lbl_status = tk.Label(
            status_row, text="Offline", bg=card, fg=COLORS["text_dim"],
            font=("Segoe UI", 10)
        )
        self.net_lbl_status.pack(side="left")

        self.net_lbl_time = tk.Label(
            inner, text="Offline", bg=card, fg=COLORS["text"],
            font=("Segoe UI", 36, "bold"), anchor="w"
        )
        self.net_lbl_time.pack(anchor="w", pady=(2, 6))

        self.net_lbl_sub = tk.Label(
            inner, text="", bg=card, fg=COLORS["text_dim"],
            font=("Segoe UI", 10), anchor="w"
        )
        self.net_lbl_sub.pack(anchor="w")

        self.net_bar = ttk.Progressbar(
            inner, maximum=DAILY_LIMIT, value=0,
            style="Quota.Horizontal.TProgressbar"
        )
        self.net_bar.pack(fill="x", pady=(16, 6))
        self.net_lbl_quota = tk.Label(
            inner, text="", bg=card, fg=COLORS["accent"],
            font=("Segoe UI", 10, "bold"), anchor="w"
        )
        self.net_lbl_quota.pack(anchor="w")

        area = tk.Frame(page, bg=bg)
        area.pack(fill="x", padx=26, pady=(0, 22))

        self.net_form = tk.Frame(area, bg=bg)
        row1 = tk.Frame(self.net_form, bg=bg)
        row1.pack(anchor="w", pady=(0, 8))
        ttk.Label(row1, text="Minutes", style="UI.TLabel", width=8).pack(side="left")
        ttk.Spinbox(
            row1, from_=1, to=DAILY_LIMIT // 60, width=6,
            textvariable=self.var_min
        ).pack(side="left")
        row2 = tk.Frame(self.net_form, bg=bg)
        row2.pack(anchor="w", pady=(0, 12))
        ttk.Label(row2, text="Reason", style="UI.TLabel", width=8).pack(side="left")
        ttk.Entry(row2, textvariable=self.var_reason, width=30).pack(side="left")
        self.btn_net_req = ttk.Button(
            self.net_form, text="📨  Request", style="Accent.TButton",
            command=self.on_net_request
        )
        self.btn_net_req.pack(anchor="w", ipadx=10)

        self.net_ctrl = tk.Frame(area, bg=bg)
        self.btn_net_ctrl = ttk.Button(
            self.net_ctrl, text="", style="Accent.TButton",
            command=self.on_net_ctrl
        )
        self.btn_net_ctrl.pack(anchor="w", ipadx=10)

    def on_net_request(self):
        try:
            minutes = int(self.var_min.get())
        except ValueError:
            messagebox.showwarning("Network", "Minutes must be an integer.", parent=self.root)
            return
        reason = self.var_reason.get().strip()
        if not reason:
            messagebox.showwarning("Network", "Please write a reason for this request.", parent=self.root)
            return
        ok, msg = self.net.request(minutes, reason)
        if not ok:
            messagebox.showwarning("Network", msg, parent=self.root)
            return
        self.var_reason.set("")
        self.refresh_net()

    def on_net_ctrl(self):
        if self.net.mode == "pending":
            self.net.cancel()
        elif self.net.mode == "online":
            self.net.end_early()
        self.refresh_net()

    def _net_set_status(self, text: str, color: str):
        self.net_lbl_status.config(text=text)
        self.net_dot_canvas.itemconfig(self.net_dot_id, fill=color)

    def refresh_net(self, force: bool = False):
        n = self.net
        mode = n.mode

        if mode != self._net_view or force:
            self._net_view = mode
            self.net_form.pack_forget()
            self.net_ctrl.pack_forget()
            if mode == "offline":
                self.net_form.pack(anchor="w")
            else:
                self.net_ctrl.pack(anchor="w")
                self.btn_net_ctrl.config(
                    text="✕  Cancel request" if mode == "pending" else "■  End session"
                )

        if mode == "offline":
            self._net_set_status("Offline", COLORS["text_dim"])
            self.net_lbl_time.config(text="Offline")
            if n.remaining < 60:
                self.net_lbl_sub.config(text="Today's quota is used up.")
                self.btn_net_req.config(state="disabled")
            else:
                self.net_lbl_sub.config(text="Submit a request below. It starts after the cooldown.")
                self.btn_net_req.config(state="!disabled")
        elif mode == "pending":
            p = n.pending
            self._net_set_status("Cooldown — you can still cancel", COLORS["warn"])
            self.net_lbl_time.config(text=fmt_ms(p["at"] - time.time()))
            start_at = datetime.fromtimestamp(p["at"]).strftime("%H:%M")
            self.net_lbl_sub.config(text=f"Requested {p['minutes']} min · goes online at {start_at}")
        else:
            self._net_set_status("Online", COLORS["success"])
            self.net_lbl_time.config(text=fmt_ms(n.grant_left))
            self.net_lbl_sub.config(text="Session time left. Network is cut automatically at zero.")

        self.net_bar["value"] = min(n.used, DAILY_LIMIT)
        self.net_lbl_quota.config(
            text=f"Used today: {fmt_hm(n.used)} / {fmt_hm(DAILY_LIMIT)}     Left: {fmt_hm(n.remaining)}"
        )

    def _net_tick(self):
        now = time.monotonic()
        dt = now - self._net_last
        self._net_last = now
        event = self.net.tick(dt)
        self.refresh_net()
        self.net_job = self.root.after(1000, self._net_tick)

        if event == "started":
            show_topmost_info("Network", "Network is now ON.", self.root)
        elif event == "ended":
            show_topmost_info("Network", "Time is up. Network is now OFF.", self.root)

    # ───────────── 卸载页 ─────────────
    def _build_uninstall_page(self, page):
        bg, card = COLORS["bg"], COLORS["bg_card"]
        danger = COLORS["danger"]

        hdr = tk.Frame(page, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(22, 8))
        tk.Label(
            hdr, text="🗑  Uninstall", bg=bg, fg=COLORS["text"],
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w")
        tk.Label(
            hdr, text="Restore your network and remove everything this program stored.",
            bg=bg, fg=COLORS["text_dim"], font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(4, 0))

        ttk.Separator(page, orient="horizontal", style="UI.TSeparator").pack(fill="x", padx=26)

        cnt_fr = tk.Frame(page, bg=card, highlightbackground=COLORS["border"], highlightthickness=1)
        cnt_fr.pack(padx=26, pady=(16, 10), fill="x")
        cin = tk.Frame(cnt_fr, bg=card)
        cin.pack(padx=22, pady=12, fill="x")
        tk.Label(
            cin, text="Times uninstalled", bg=card, fg=COLORS["text_dim"],
            font=("Segoe UI", 10)
        ).pack(anchor="w")
        self.uni_lbl_count = tk.Label(
            cin, text="0", bg=card, fg=COLORS["text"],
            font=("Segoe UI", 30, "bold"), anchor="w"
        )
        self.uni_lbl_count.pack(anchor="w")
        self.uni_lbl_last = tk.Label(
            cin, text="", bg=card, fg=COLORS["text_dim"],
            font=("Segoe UI", 9), anchor="w"
        )
        self.uni_lbl_last.pack(anchor="w")

        warn_fr = tk.Frame(page, bg="#fef2f2", highlightbackground=danger, highlightthickness=1)
        warn_fr.pack(padx=26, pady=(0, 10), fill="x")
        tk.Label(
            warn_fr, text="⚠  Warning: this permanently erases ALL data",
            bg="#fef2f2", fg=danger, font=("Segoe UI", 10, "bold"),
            anchor="w"
        ).pack(fill="x", padx=16, pady=(10, 2))
        tk.Label(
            warn_fr, justify="left", anchor="w", bg="#fef2f2", fg=COLORS["text"],
            font=("Segoe UI", 9),
            text=(
                "• Study history, calendar, hour log, network quota and request log are deleted.\n"
                "• Network is restored immediately (adapters re-enabled / firewall rule removed).\n"
                "• An unfinished focus session is NOT recorded.\n"
                "• Only this counter is kept. It cannot be undone."
            )
        ).pack(fill="x", padx=16, pady=(0, 10))

        form = tk.Frame(page, bg=bg)
        form.pack(fill="x", padx=26, pady=(0, 16))
        row = tk.Frame(form, bg=bg)
        row.pack(anchor="w", pady=(0, 6))
        ttk.Label(row, text="Type UNINSTALL to confirm", style="UI.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(row, textvariable=self.var_confirm, width=16).pack(side="left")
        tk.Checkbutton(
            form, text="Also delete this program file", variable=self.var_del_self,
            bg=bg, activebackground=bg, fg=COLORS["text_dim"],
            font=("Segoe UI", 9), anchor="w"
        ).pack(anchor="w", pady=(0, 8))
        self.btn_uninstall = ttk.Button(
            form, text="🗑  Uninstall & erase data",
            style="Danger.TButton", command=self.on_uninstall
        )
        self.btn_uninstall.pack(anchor="w", ipadx=10)
        self.btn_uninstall.state(["disabled"])

    def _on_confirm_change(self, *_):
        ok = self.var_confirm.get().strip() == "UNINSTALL"
        self.btn_uninstall.state(["!disabled" if ok else "disabled"])

    def refresh_uninstall(self):
        self.var_confirm.set("")
        self.uni_lbl_count.config(text=str(self.dm.uninstall_count))
        self.uni_lbl_last.config(
            text=f"Last uninstall: {self.dm.uninstall_last}" if self.dm.uninstall_last
            else "Never uninstalled before."
        )

    def on_uninstall(self):
        if self.var_confirm.get().strip() != "UNINSTALL":
            return
        if not messagebox.askyesno(
            "Uninstall",
            "This will permanently erase ALL data and restore your network.\n\n"
            "This cannot be undone. Continue?",
            icon="warning", default="no", parent=self.root
        ):
            return
        self.do_uninstall()

    def do_uninstall(self):
        self.dm.uninstalling = True
        for job in (self.midnight_job, self.hourly_job, self.update_job, self.net_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass

        self.net.release()                             # 1) 先恢复网络

        self.dm.uninstall_count += 1                   # 2) 计数
        self.dm.uninstall_last = datetime.now().strftime('%Y-%m-%d %H:%M')
        self.dm.save_uninstall_count()

        self.dm.erase_all_data()                       # 3) 清除所有数据

        removed_self = False
        if self.var_del_self.get():                    # 4) 可选删除程序文件
            try:
                # 注意：多文件结构下删除的是入口脚本，其他模块不会被自动删除
                os.remove(os.path.abspath(sys.argv[0]))
                removed_self = True
            except OSError:
                pass

        messagebox.showinfo(
            "Uninstall",
            f"All data erased and network restored.\n"
            f"Total uninstalls so far: {self.dm.uninstall_count}"
            + ("" if not self.var_del_self.get() else
               ("\nProgram file deleted." if removed_self else
                "\nCould not delete the program file; please remove it manually.")),
            parent=self.root
        )
        self.root.destroy()
