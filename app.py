

import sys
import os
import time
import threading
import tkinter as tk
from tkinter import font as tkfont, ttk
from datetime import datetime, timedelta, time as dt_time

import config
import i18n
import toast
from config import (
    COLORS, APP_NAME, IDLE, RUNNING, READY_BREAK, ON_BREAK,
    ensure_builtin_chime,
    compute_F, fmt_hm, fmt_ms
)
from i18n import tr
from net_guard import NetGuard, LOAN_MULTIPLIER, LOAN_MULTIPLIER_TOMORROW
from data_manager import DataManager
from settings_manager import SettingsManager
from pages import CalendarPage, HourLogPage, SettingsPage
from pages.widgets import wrap_label


def _enable_per_monitor_dpi():
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll
    except Exception:
        return
    try:

        windll.user32.SetProcessDpiAwarenessContext(-4)
        return
    except Exception:
        pass
    try:
        windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class BreakTimerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.shutting_down = False
        self._rebuilding = False

        _enable_per_monitor_dpi()
        self.ui_scale = config.detect_ui_scale()
        config.UI_SCALE = self.ui_scale
        if not (root.winfo_exists() and root.winfo_width() > 1):
            pass

        root.title(APP_NAME)
        root.configure(bg=COLORS["bg"])
        root.resizable(False, False)

        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self._theme_ttk()


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



        self.dm = DataManager()
        self.settings = SettingsManager()
        i18n.init_from_config()
        config.UI_SCALE = self.ui_scale * float(self.settings.value("FONT_SCALE") or 1.0)
        self.dm.hour_enabled = bool(self.settings.value("HOUR_LOG_ENABLED"))
        self.net = NetGuard(self.dm.data_dir)
        self._net_view = None
        self._net_last = time.monotonic()
        self._apply_notice = None
        self.var_min = tk.StringVar(value="15")
        self.var_reason = tk.StringVar()
        self.var_confirm = tk.StringVar()
        self.var_del_self = tk.BooleanVar(value=False)
        self.var_loan = tk.BooleanVar(value=False)

        toast.bind_root(root)
        self._build_layout(root)
        self.show_page("timer")
        self._apply_geometry()

        self.refresh_display()
        self.update_log_badge()
        self.update_settings_badge()
        self._start_midnight_timer()
        self._schedule_hourly()
        self._schedule_apply_check()
        self._net_tick()

        self.root.bind("<Map>", self._on_window_map)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.var_confirm.trace_add("write", self._on_confirm_change)


    def _apply_geometry(self):
        w = config.scaled(config.WINDOW_W)
        h = config.scaled(config.WINDOW_H)
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w = min(w, int(sw * 0.96))
            h = min(h, int(sh * 0.92) - 40)
        except Exception:
            pass
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(config.scaled(config.MIN_WINDOW_W), config.scaled(config.MIN_WINDOW_H))
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                f = tkfont.nametofont(name)
                f.configure(family=config.FONT_FAMILY, size=config.scaled(config.FONT_SIZE["body"]))
            except Exception:
                pass


    def _theme_ttk(self):
        s = self.style
        bg, card = COLORS["bg"], COLORS["bg_card"]
        ac, tx = COLORS["accent"], COLORS["text"]
        td = COLORS["text_dim"]

        s.configure("Card.TFrame", background=card)
        s.configure("TopBar.TFrame", background=COLORS["accent"])

        s.configure("UI.TLabel", background=bg, foreground=td, font=config.font("body"))
        s.configure("UI.Bold.TLabel", background=bg, foreground=tx, font=config.font("body", bold=True))
        s.configure("Card.TLabel", background=card, foreground=tx, font=config.font("body"))
        s.configure("Card.Bold.TLabel", background=card, foreground="#0f172a", font=config.font("body", bold=True))

        s.configure(
            "Accent.TButton",
            background=ac, foreground="#ffffff",
            font=config.font("body", bold=True),
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
            font=config.font("body", bold=True),
            borderwidth=0, focusthickness=0, padding=(18, 10)
        )
        s.map(
            "Danger.TButton",
            background=[("active", COLORS["danger_hover"]), ("disabled", "#fca5a5")],
            foreground=[("disabled", "#ffffff")]
        )


    def _build_layout(self, parent):
        bg, card = COLORS["bg"], COLORS["bg_card"]

        self.topbar = tk.Frame(parent, bg=COLORS["accent"], height=4)
        self.topbar.pack(fill="x")

        self.shell = tk.Frame(parent, bg=bg)
        self.shell.pack(fill="both", expand=True)


        side = tk.Frame(self.shell, bg=card, highlightbackground=COLORS["border"],
                        highlightthickness=1)
        side.pack(side="left", fill="y")
        self.sidebar = side
        tk.Frame(side, bg=card, height=14).pack()

        self.nav_btns = {}


        self.nav_labels = {
            "timer": tr("⏱  Timer"),
            "net": tr("🌐  Network"),
            "log": tr("📝  Hour Log"),
            "cal": tr("📅  Calendar"),
            "settings": tr("⚙  Settings"),
            "uninstall": tr("🗑  Uninstall")
        }
        for key, label in self.nav_labels.items():
            if key == "uninstall":

                tk.Frame(side, bg=card).pack(fill="both", expand=True)
            b = tk.Button(
                side, text=label, anchor="w", width=15,
                font=config.font("nav"), relief="flat", bd=0,
                padx=14, pady=12, cursor="hand2",
                command=lambda k=key: self.show_page(k)
            )
            b.pack(fill="x", pady=(0, 2))
            self.nav_btns[key] = b


        self.content = tk.Frame(self.shell, bg=bg)
        self.content.pack(side="left", fill="both", expand=True)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.pages["cal"] = CalendarPage(self.content, self.dm)
        self.pages["log"] = HourLogPage(
            self.content, self.dm,
            on_text_changed=self.update_log_badge,
            on_toggle=self.on_hour_log_toggle,
            on_open_settings=lambda: self.show_page("settings")
        )
        self.pages["settings"] = SettingsPage(
            self.content, self.settings,
            on_changed=self.on_settings_changed, on_sound=self.play_chime,
            on_dev_mode=self.on_dev_mode_changed,
            on_language=self.on_language_changed,
            on_font_scale=self.on_font_scale_changed
        )
        self.pages["net"] = tk.Frame(self.content, bg=bg)
        self.pages["timer"] = tk.Frame(self.content, bg=bg)
        self.pages["uninstall"] = tk.Frame(self.content, bg=bg)
        for f in self.pages.values():
            f.grid(row=0, column=0, sticky="nsew")

        self._build_net_page(self.pages["net"])
        self._build_timer_page(self.pages["timer"])
        self._build_uninstall_page(self.pages["uninstall"])


    def rebuild_ui(self):
        if self._rebuilding or self.shutting_down:
            return
        self._rebuilding = True
        try:
            for job in (self.midnight_job, self.hourly_job, self.update_job,
                        self.net_job, getattr(self, "apply_job", None)):
                if job:
                    try:
                        self.root.after_cancel(job)
                    except Exception:
                        pass
            self.midnight_job = self.hourly_job = self.update_job = None
            self.net_job = self.apply_job = None

            for w in (getattr(self, "topbar", None), getattr(self, "shell", None)):
                if w is not None:
                    try:
                        w.destroy()
                    except Exception:
                        pass
            self.style = ttk.Style(self.root)
            self.style.theme_use("clam")
            self._theme_ttk()
            self.pages = {}
            self.nav_btns = {}
            self._build_layout(self.root)
            self._apply_geometry()
            self.show_page(self.current_page or "timer")

            self.refresh_display()
            self.update_log_badge()
            self.update_settings_badge()
            self._start_midnight_timer()
            self._schedule_hourly()
            if self.state == RUNNING:
                self.schedule_update()
        finally:
            self._rebuilding = False

    def on_language_changed(self):
        i18n.init_from_config()
        self.rebuild_ui()

    def on_font_scale_changed(self):
        self.ui_scale = config.detect_ui_scale()
        base = float(self.settings.value("FONT_SCALE") or 1.0)
        config.UI_SCALE = self.ui_scale * base
        self.rebuild_ui()


    def _cancel_jobs(self):
        self.shutting_down = True
        for job in (self.midnight_job, self.hourly_job, self.update_job,
                    self.net_job, getattr(self, "apply_job", None)):
            if not job:
                continue
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.midnight_job = self.hourly_job = self.update_job = None
        self.net_job = self.apply_job = None

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
        elif key == "settings":
            self.pages["settings"].refresh()
        elif key == "uninstall":
            self.refresh_uninstall()
        self.update_log_badge()
        self.update_settings_badge()


    def _build_timer_page(self, body):
        bg, card = COLORS["bg"], COLORS["bg_card"]

        hdr = tk.Frame(body, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(22, 8))
        tk.Label(
            hdr, text=tr("⏱  Focus Timer"), bg=bg, fg=COLORS["text"],
            font=config.font("h1", bold=True)
        ).pack(anchor="w")
        tk.Label(
            hdr, text=tr("开始工作 → 结束 → 休息"),
            bg=bg, fg=COLORS["text_dim"], font=config.font("body")
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
            status_row, text=tr("准备就绪"), bg=card, fg=COLORS["text_dim"],
            font=config.font("body")
        )
        self.lbl_status.pack(side="left")

        self.lbl_time = tk.Label(
            inner, text="0.00 min", bg=card, fg=COLORS["text"],
            font=config.font("big", bold=True), anchor="w"
        )
        self.lbl_time.pack(anchor="w", pady=(2, 6))

        self.lbl_sub = tk.Label(
            inner, text=tr("开始专注时按 [开始]."),
            bg=card, fg=COLORS["text_dim"], font=config.font("body"), anchor="w"
        )
        self.lbl_sub.pack(anchor="w")

        stats_frame = tk.Frame(inner, bg=card)
        stats_frame.pack(anchor="w", pady=(14, 0), fill="x")
        self.lbl_today = tk.Label(
            stats_frame, text=tr("今日: {h:.1f} h").format(h=0.0), bg=card, fg=COLORS["accent"],
            font=config.font("body", bold=True)
        )
        self.lbl_today.pack(side="left", padx=(0, 30))
        self.lbl_yesterday = tk.Label(
            stats_frame, text=tr("昨日: {h:.1f} h").format(h=0.0), bg=card,
            fg=COLORS["text_dim"], font=config.font("body")
        )
        self.lbl_yesterday.pack(side="left")

        btn_row = tk.Frame(body, bg=bg)
        btn_row.pack(fill="x", padx=26, pady=(6, 22))
        self.btn_action = ttk.Button(
            btn_row, text=tr("▶  开始"), style="Accent.TButton",
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
            self.btn_action.config(text=tr("■  结束"))
            self._status(tr("专注中…"), COLORS["accent"])
            self.lbl_sub.config(text=tr("计时中 —— 结束时按 [结束]."))
            self.schedule_update()

        elif self.state == RUNNING:
            end_wall = datetime.now()
            elapsed_minutes = (time.monotonic() - self.start_mono) / 60.0
            self.last_t_minutes = elapsed_minutes
            self.dm.add_study_session(self.start_wall, end_wall, elapsed_minutes)
            self.refresh_display()

            self.state = READY_BREAK
            self.btn_action.config(text=tr("☕  去休息"))
            self.cancel_update()
            fval = compute_F(self.last_t_minutes)
            m = int(fval)
            s = int((fval - m) * 60)
            self.lbl_time.config(text=f"{m:02d}:{s:02d}")
            self.lbl_sub.config(text=tr("已工作 {m:.2f} 分钟 → 上方是建议休息时长").format(m=self.last_t_minutes))
            self._status(tr("本次专注结束"), COLORS["success"])

        elif self.state == READY_BREAK:
            fval = compute_F(self.last_t_minutes)
            if fval <= 0:
                toast.info(tr("剩余时间为 0,已重置."))
                self.reset_to_idle()
                return
            self.countdown_seconds = max(1, int(round(fval * 60.0)))
            self.state = ON_BREAK
            self.btn_action.config(state="disabled")
            self._status(tr("休息中 ☕"), COLORS["warn"])
            self.lbl_sub.config(text=tr("休息吧,倒计时中…"))
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
                self.lbl_sub.config(text=tr("预计停止时的休息时长:  {m:.2f} 分钟").format(m=rem))
            else:
                self.lbl_sub.config(text=tr("预计休息时长: 0.00 分钟"))
            self.update_job = self.root.after(200, self.update)

        elif self.state == ON_BREAK:
            if self.countdown_seconds > 0:
                m = self.countdown_seconds // 60
                s = self.countdown_seconds % 60
                self.lbl_time.config(text=f"{m:02d}:{s:02d}")
                self.lbl_sub.config(text=tr("休息剩余 {m} 分 {s:02d} 秒").format(m=m, s=s))
                self.countdown_seconds -= 1
                self.update_job = self.root.after(1000, self.update)
            else:
                toast.success(tr("休息结束,可以开始下一轮了!"))
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
        self.btn_action.config(text=tr("▶  开始"), state="!disabled")
        self.lbl_time.config(text="0.00 min")
        self.lbl_sub.config(text=tr("开始专注时按 [开始]."))
        self._status(tr("准备就绪"), COLORS["text_dim"])

    def refresh_display(self):
        self.lbl_today.config(text=tr("今日: {h:.1f} h").format(h=self.dm.get_today_hours()))
        self.lbl_yesterday.config(text=tr("昨日: {h:.1f} h").format(h=self.dm.get_yesterday_hours()))


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
        if not self.dm.hour_enabled:
            self.update_log_badge()
            return
        if slot.hour >= int(self.settings.value("LOG_HOURS")):
            return
        self._wait_chime(self._play_chime(), slot)

    def _play_chime(self):
        if sys.platform != "win32":
            try:
                self.root.bell()
            except Exception:
                pass
            return None

        path = self.settings.value("CHIME_WAV") or ""
        if path and not os.path.exists(path):
            path = ""
        if not path or path == "__builtin__":
            builtin = os.path.join(self.dm.data_dir, "chime.wav")
            path = ensure_builtin_chime(builtin) or ""

        def run():
            try:
                import winsound
                if path and os.path.exists(path):
                    winsound.PlaySound(path, winsound.SND_FILENAME)
                else:
                    for freq, ms in ((784, 200), (988, 200), (1319, 450)):
                        winsound.Beep(freq, ms)
            except Exception:
                pass
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t

    def play_chime(self):
        self._play_chime()

    def _wait_chime(self, t, slot):
        if t is not None and t.is_alive():
            self.root.after(200, lambda: self._wait_chime(t, slot))
            return
        if not self.dm.hour_enabled:
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
            self.check_pending_settings()


    def _schedule_apply_check(self):
        if self.shutting_down:
            return
        self.check_pending_settings()
        self.apply_job = self.root.after(5000, self._schedule_apply_check)

    def check_pending_settings(self):
        if self.shutting_down:
            return []
        due = self.settings.promote_due()
        if not due:
            return due

        self._sync_hour_log_setting()
        self.pages["settings"].refresh()
        self.update_settings_badge()
        self.refresh_net(force=True)
        labels = "、".join(tr(self.settings.display(k)) for k in due)
        toast.success(tr("48 小时冷静期已结束,以下配置从现在开始生效:") + "\n" + labels)
        self._log_notice(f"SETTINGS applied: {', '.join(due)}")
        return due

    def _sync_hour_log_setting(self):
        want = bool(self.settings.value("HOUR_LOG_ENABLED"))
        if want != self.dm.hour_enabled:
            self.dm.apply_hour_enabled(want)
        if "log" in self.pages:
            self.pages["log"].refresh()
        self.update_log_badge()

    def _log_notice(self, text: str):
        try:
            with open(os.path.join(self.dm.data_dir, "settings_changes.log"),
                      'a', encoding='utf-8') as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
        except IOError:
            pass






    def on_close(self):
        self._cancel_jobs()
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
        self.update_log_badge()
        if "log" in self.pages:
            self.pages["log"].refresh()

    def on_settings_changed(self, status: str = "", key: str = None):
        self.update_settings_badge()
        if status != "instant":
            return
        if key in ("HOUR_LOG_ENABLED", "AUTO_TEXT", "LOG_HOURS", None):

            if key in ("LOG_HOURS", "AUTO_TEXT", None):
                if "log" in self.pages:
                    self.pages["log"].refresh()
            if key == "HOUR_LOG_ENABLED":
                self._sync_hour_log_setting()

    def update_settings_badge(self):
        b = self.nav_btns.get("settings")
        if not b:
            return
        mark = ""
        staged = self.settings.staged_count()
        if staged:
            mark += f"  ⏳{staged}"
        if bool(getattr(config, "DEV_MODE", False)):
            mark += "  🛠"
        b.config(text=self.nav_labels["settings"] + mark)


    def on_dev_mode_changed(self, enabled: bool):
        if enabled:
            self.net.release_restrictions()
            self._log_notice("DEV_MODE on — network cut-off disabled")
        else:
            try:
                self.net.block(sync=True)
            except Exception:
                pass
            self._log_notice("DEV_MODE off — fail-closed restored")
        self.update_settings_badge()
        self.refresh_net(force=True)
        self.pages["settings"].refresh()


    def _build_net_page(self, page):
        bg, card = COLORS["bg"], COLORS["bg_card"]

        hdr = tk.Frame(page, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(22, 8))
        tk.Label(
            hdr, text=tr("🌐  联网申请"), bg=bg, fg=COLORS["text"],
            font=config.font("h1", bold=True)
        ).pack(anchor="w")
        self.net_lbl_header = tk.Label(
            hdr, text="", bg=bg, fg=COLORS["text_dim"], font=config.font("body")
        )
        self.net_lbl_header.pack(anchor="w", pady=(4, 0))

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
            font=config.font("body")
        )
        self.net_lbl_status.pack(side="left")

        self.net_lbl_time = tk.Label(
            inner, text="Offline", bg=card, fg=COLORS["text"],
            font=config.font("big", bold=True), anchor="w"
        )
        self.net_lbl_time.pack(anchor="w", pady=(2, 6))

        self.net_lbl_sub = tk.Label(
            inner, text="", bg=card, fg=COLORS["text_dim"],
            font=config.font("body"), anchor="w", justify="left"
        )
        self.net_lbl_sub.pack(anchor="w")

        self.net_bar = ttk.Progressbar(
            inner, maximum=float(self.settings.value("DAILY_LIMIT")), value=0,
            style="Quota.Horizontal.TProgressbar"
        )
        self.net_bar.pack(fill="x", pady=(16, 6))
        self.net_lbl_quota = tk.Label(
            inner, text="", bg=card, fg=COLORS["accent"],
            font=config.font("body", bold=True), anchor="w"
        )
        self.net_lbl_quota.pack(anchor="w")
        self.net_lbl_debt = tk.Label(
            inner, text="", bg=card, fg=COLORS["warn"],
            font=config.font("small"), anchor="w", justify="left"
        )
        self.net_lbl_debt.pack(anchor="w")

        area = tk.Frame(page, bg=bg)
        area.pack(fill="x", padx=26, pady=(0, 22))

        self.net_form = tk.Frame(area, bg=bg)
        row1 = tk.Frame(self.net_form, bg=bg)
        row1.pack(anchor="w", pady=(0, 8))
        ttk.Label(row1, text=tr("分钟"), style="UI.TLabel", width=8).pack(side="left")
        ttk.Spinbox(
            row1, from_=1, to=24 * 60, width=6,
            textvariable=self.var_min
        ).pack(side="left")
        row2 = tk.Frame(self.net_form, bg=bg)
        row2.pack(anchor="w", pady=(0, 12))
        ttk.Label(row2, text=tr("理由"), style="UI.TLabel", width=8).pack(side="left")
        ttk.Entry(row2, textvariable=self.var_reason, width=30).pack(side="left")

        btns = tk.Frame(self.net_form, bg=bg)
        btns.pack(anchor="w")
        self.btn_net_req = ttk.Button(
            btns, text=tr("📨  提交申请(需冷静期)"), style="Accent.TButton",
            command=self.on_net_request
        )
        self.btn_net_req.pack(side="left")
        self.btn_net_loan = ttk.Button(
            btns, text=tr("⚡  紧急贷款"), style="Danger.TButton",
            command=self.on_net_loan
        )
        self.btn_net_loan.pack(side="left", padx=(8, 0))

        self.net_loan_hint = tk.Label(
            self.net_form, text="", bg=bg, fg=COLORS["text_dim"],
            font=config.font("small"), anchor="w", justify="left", wraplength=520
        )
        self.net_loan_hint.pack(anchor="w", fill="x", pady=(8, 0))
        wrap_label(self.net_loan_hint, 24)
        self.net_form.pack_configure(anchor="w", fill="x")

        self.net_ctrl = tk.Frame(area, bg=bg)
        self.btn_net_ctrl = ttk.Button(
            self.net_ctrl, text="", style="Accent.TButton",
            command=self.on_net_ctrl
        )
        self.btn_net_ctrl.pack(side="left", ipadx=10)
        self.btn_net_upgrade = ttk.Button(
            self.net_ctrl, text=tr("⚡  立刻联网(付费)"), style="Danger.TButton",
            command=self.on_net_upgrade
        )
        self.net_ctrl_hint = tk.Label(
            self.net_ctrl, text="", bg=bg, fg=COLORS["text_dim"],
            font=config.font("small"), anchor="w", justify="left", wraplength=520
        )
        wrap_label(self.net_ctrl_hint, 24)

    def on_net_request(self):
        ok, minutes, reason = self._read_net_form()
        if not ok:
            return
        ok, msg = self.net.request(minutes, reason, loan=False)
        if not ok:
            toast.warn(tr(msg))
            return
        self.var_reason.set("")
        self.refresh_net(force=True)

    def on_net_loan(self):
        ok, minutes, reason = self._read_net_form()
        if not ok:
            return
        ok2, _msg = self.net.can_loan(minutes)
        if not ok2:
            toast.warn(tr(_msg))
            return
        today_cost, loan_cost, total, grant = self.net.loan_plan(minutes)
        if not toast.ask(
            tr("紧急贷款会跳过冷静期立刻联网,额度按「今天 ×{a:g}、预支明天 ×{b:g}」计费.\n\n申请: {m} 分钟\n实际放行: {grant}\n计费: {total} 额度(今天 {today} ×{a:g} + 预支明天 {borrowed} ×{b:g})\n\n确定吗?").format(
                a=LOAN_MULTIPLIER, b=LOAN_MULTIPLIER_TOMORROW, m=minutes,
                grant=fmt_hm(grant), total=fmt_hm(total),
                today=fmt_hm(today_cost), borrowed=fmt_hm(loan_cost)),
            title=tr("紧急贷款"), danger=True
        ):
            return
        ok, msg = self.net.request(minutes, reason, loan=True)
        if not ok:
            toast.warn(tr(msg))
            return
        self.var_reason.set("")
        self.refresh_net(force=True)

    def _read_net_form(self):
        try:
            minutes = int(self.var_min.get())
        except ValueError:
            toast.warn(tr("分钟数必须是整数."))
            return False, 0, ""
        reason = self.var_reason.get().strip()
        if not reason:
            toast.warn(tr("请写一个申请理由."))
            return False, 0, ""
        return True, minutes, reason

    def on_net_ctrl(self):
        if self.net.mode == "pending":
            self.net.cancel()
        elif self.net.mode == "online":
            self.net.end_early()
        self.refresh_net(force=True)

    def on_net_upgrade(self):
        p = self.net.pending or {}
        minutes = p.get("minutes", 0)
        ok2, msg2 = self.net.can_loan(minutes)
        if not ok2:
            toast.warn(tr(msg2))
            return
        today_cost, loan_cost, total, grant = self.net.loan_plan(minutes)
        if not toast.ask(
            tr("立刻结束冷静期并联网?\n\n申请: {m} 分钟\n实际放行: {grant}  ·  计费 {total} 额度\n(今天 {today} ×{a:g} + 预支明天 {borrowed} ×{b:g})\n\n确定吗?").format(
                m=minutes, grant=fmt_hm(grant), total=fmt_hm(total),
                today=fmt_hm(today_cost), borrowed=fmt_hm(loan_cost),
                a=LOAN_MULTIPLIER, b=LOAN_MULTIPLIER_TOMORROW),
            title=tr("紧急贷款"), danger=True
        ):
            return
        ok, msg = self.net.convert_to_loan()
        if not ok:
            toast.warn(tr(msg))
            return
        self.refresh_net(force=True)

    def _net_set_status(self, text: str, color: str):
        self.net_lbl_status.config(text=text)
        self.net_dot_canvas.itemconfig(self.net_dot_id, fill=color)

    def refresh_net(self, force: bool = False):
        n = self.net
        mode = n.mode
        limit = float(self.settings.value("DAILY_LIMIT"))
        cooldown = int(self.settings.value("COOLDOWN"))
        cooldown_m = cooldown // 60

        self.net_lbl_header.config(
            text=tr("申请 → {min} 分钟冷静期 → 联网 → 到点自动断网").format(min=cooldown_m)
                 + "    ·    " + tr("⚡ 紧急贷款免冷静期 (今天 ×{a:g} / 预支明天 ×{b:g})").format(
                     a=LOAN_MULTIPLIER, b=LOAN_MULTIPLIER_TOMORROW)
        )

        if mode == "dev":


            self._net_set_status("Developer mode — network unrestricted", COLORS["warn"])
            self.net_lbl_time.config(text="DEV")
            self.net_lbl_sub.config(
                text="开发者模式已开启:本程序不会断网,也不会申请/计时。\n"
                     "调试完成后请到 Settings 页关掉它。"
            )
            self.net_form.pack_forget()
            self.net_ctrl.pack_forget()
            self.net_bar["maximum"] = max(1.0, limit)
            self.net_bar["value"] = min(n.quota_used, limit)
            self.net_lbl_quota.config(
                text=f"Used today: {fmt_hm(n.quota_used)} / {fmt_hm(limit)}"
                     f"     (developer mode — not counting)"
            )
            self.net_lbl_debt.config(text="")
            return

        if mode != self._net_view or force:
            self._net_view = mode
            self.net_form.pack_forget()
            self.net_ctrl.pack_forget()
            if mode == "offline":
                self.net_form.pack(anchor="w")
            else:
                self.net_ctrl.pack(anchor="w")
                self.btn_net_ctrl.config(
                    text=tr("✕  取消申请") if mode == "pending" else tr("■  结束本次会话")
                )
                if mode == "pending":
                    self.btn_net_upgrade.pack(side="left", padx=(8, 0))
                    self.net_ctrl_hint.pack(anchor="w", pady=(8, 0))
                else:
                    self.btn_net_upgrade.pack_forget()
                    self.net_ctrl_hint.pack_forget()

        if mode == "offline":
            self._net_set_status(tr("离线"), COLORS["text_dim"])
            self.net_lbl_time.config(text=tr("离线"))
            if n.remaining < 60 and n.quota_left < 60:
                self.net_lbl_sub.config(text=tr("今天的额度已用完."))
                self.btn_net_req.config(state="disabled")
            else:
                self.net_lbl_sub.config(
                    text=tr("在下面提交申请,冷静期结束后自动联网.")
                )
                self.btn_net_req.config(state="!disabled")
        elif mode == "pending":
            p = n.pending
            self._net_set_status(tr("冷静期中 —— 仍可取消"), COLORS["warn"])
            self.net_lbl_time.config(text=fmt_ms(p["at"] - time.time()))
            start_at = datetime.fromtimestamp(p["at"]).strftime("%H:%M")
            self.net_lbl_sub.config(
                text=tr("已申请 {m} 分钟 · {at} 联网").format(m=p['minutes'], at=start_at)
            )
            ok, msg = n.can_loan(p["minutes"])
            if ok:
                today_cost, loan_cost, total, grant = n.loan_plan(p["minutes"])
                self.net_ctrl_hint.config(
                    text=tr("⚡ 紧急贷款可立刻联网:放行 {grant}(今天额度 {today} ×{a:g} + 预支明天 {borrowed} ×{b:g})").format(
                        grant=fmt_hm(grant), today=fmt_hm(today_cost),
                        borrowed=fmt_hm(loan_cost),
                        a=LOAN_MULTIPLIER, b=LOAN_MULTIPLIER_TOMORROW),
                    fg=COLORS["text_dim"]
                )
            else:
                self.net_ctrl_hint.config(text="⚡ " + msg, fg=COLORS["text_dim"])
        else:
            self._net_set_status(tr("联网中"), COLORS["success"])
            self.net_lbl_time.config(text=fmt_ms(n.grant_left))
            if n.grant_loan:
                self.net_lbl_sub.config(
                    text=tr("⚡ 贷款会话 —— 今天 ×{a:g}、预支 ×{b:g}.可继续使用 {left};已预支 {borrowed}").format(
                        a=LOAN_MULTIPLIER, b=LOAN_MULTIPLIER_TOMORROW,
                        left=fmt_hm(n.grant_left), borrowed=fmt_hm(n.bucket_loan_t))
                )
            else:
                self.net_lbl_sub.config(
                    text=tr("本次会话剩余时间,归零自动断网.")
                )


        if mode == "offline":
            usermin = self._safe_minutes()
            ok_any, msg_any = n.can_loan(usermin) if usermin else (False, "")
            if ok_any:
                today_cost, loan_cost, total, grant = n.loan_plan(usermin)
                self.net_loan_hint.config(
                    text=tr("⚡ {m} 分钟可走紧急贷款:放行 {grant},计费 {total}(今天额度 {today} ×{a:g} + 预支明天 {borrowed} ×{b:g}).贷款上限 {cap}.").format(
                        m=usermin, grant=fmt_hm(grant), total=fmt_hm(total),
                        today=fmt_hm(today_cost), borrowed=fmt_hm(loan_cost),
                        a=LOAN_MULTIPLIER, b=LOAN_MULTIPLIER_TOMORROW,
                        cap=fmt_hm(n.quota_left)),
                    fg=COLORS["text_dim"]
                )
            elif n.remaining < 60:
                self.net_loan_hint.config(
                    text=tr("⚡ 今天额度已用完.贷款上限 {cap},全部预支明天(×{b:g}).").format(
                        cap=fmt_hm(n.quota_left), b=LOAN_MULTIPLIER_TOMORROW),
                    fg=COLORS["text_dim"]
                )
            else:
                self.net_loan_hint.config(
                    text=tr("⚡ 紧急贷款:跳过冷静期立刻联网;今天剩余额度按 2 倍计费,不够的部分按 3 倍预支明天的额度."),
                    fg=COLORS["text_dim"]
                )

        self.net_bar["maximum"] = max(1.0, limit)
        self.net_bar["value"] = min(n.quota_used, limit)
        self.net_lbl_quota.config(
            text=tr("今日已用: {used} / {total}     今日剩余: {left}     含贷款: {cap}  (今天 ×{a:g}, 预支 ×{b:g})").format(
                used=fmt_hm(n.quota_used), total=fmt_hm(limit), left=fmt_hm(n.remaining),
                cap=fmt_hm(n.quota_left),
                a=LOAN_MULTIPLIER, b=LOAN_MULTIPLIER_TOMORROW)
        )
        bits = []
        if n.tomorrow_used > 0:
            bits.append(tr("今天已预支明天的额度 {borrowed}(明天剩余 {left})").format(
                borrowed=fmt_hm(n.tomorrow_used), left=fmt_hm(n.tomorrow_remaining)))
        if n.debt > 0:
            bits.append(tr("今天要先还昨天预支的 {debt}").format(debt=fmt_hm(n.debt)))
        self.net_lbl_debt.config(text="\n".join(bits))

    def _safe_minutes(self):
        try:
            return int(self.var_min.get())
        except (TypeError, ValueError):
            return 0

    def _net_tick(self):
        if self.shutting_down:
            return
        now = time.monotonic()
        dt = now - self._net_last
        self._net_last = now
        event = self.net.tick(dt)
        self.refresh_net()
        self.net_job = self.root.after(1000, self._net_tick)

        if event == "started":
            toast.success(tr("网络已开启."))
        elif event == "ended":
            toast.warn(tr("时间到,网络已断开."))


    def _build_uninstall_page(self, page):
        bg, card = COLORS["bg"], COLORS["bg_card"]
        danger = COLORS["danger"]

        hdr = tk.Frame(page, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(22, 8))
        tk.Label(
            hdr, text=tr("🗑  卸载"), bg=bg, fg=COLORS["text"],
            font=config.font("h1", bold=True)
        ).pack(anchor="w")
        tk.Label(
            hdr, text=tr("恢复网络并删除本程序留下的全部内容."),
            bg=bg, fg=COLORS["text_dim"], font=config.font("body")
        ).pack(anchor="w", pady=(4, 0))

        ttk.Separator(page, orient="horizontal", style="UI.TSeparator").pack(fill="x", padx=26)

        cnt_fr = tk.Frame(page, bg=card, highlightbackground=COLORS["border"], highlightthickness=1)
        cnt_fr.pack(padx=26, pady=(16, 10), fill="x")
        cin = tk.Frame(cnt_fr, bg=card)
        cin.pack(padx=22, pady=12, fill="x")
        tk.Label(
            cin, text=tr("卸载次数"), bg=card, fg=COLORS["text_dim"],
            font=config.font("body")
        ).pack(anchor="w")
        self.uni_lbl_count = tk.Label(
            cin, text="0", bg=card, fg=COLORS["text"],
            font=config.font("big", bold=True), anchor="w"
        )
        self.uni_lbl_count.pack(anchor="w")
        self.uni_lbl_last = tk.Label(
            cin, text="", bg=card, fg=COLORS["text_dim"],
            font=config.font("small"), anchor="w"
        )
        self.uni_lbl_last.pack(anchor="w")

        warn_fr = tk.Frame(page, bg="#fef2f2", highlightbackground=danger, highlightthickness=1)
        warn_fr.pack(padx=26, pady=(0, 10), fill="x")
        tk.Label(
            warn_fr, text=tr("⚠  警告:这会永久删除全部数据"),
            bg="#fef2f2", fg=danger, font=config.font("body", bold=True),
            anchor="w"
        ).pack(fill="x", padx=16, pady=(10, 2))
        tk.Label(
            warn_fr, justify="left", anchor="w", bg="#fef2f2", fg=COLORS["text"],
            font=config.font("small"),
            text=(
                "• Study history, calendar, hour log, network quota, request log\n"
                "  and settings changes are deleted.\n"
                "• Network is restored immediately (physical adapters re-enabled).\n"
                "• An unfinished focus session is NOT recorded.\n"
                "• Only this counter is kept. It cannot be undone."
            )
        ).pack(fill="x", padx=16, pady=(0, 10))

        form = tk.Frame(page, bg=bg)
        form.pack(fill="x", padx=26, pady=(0, 16))
        row = tk.Frame(form, bg=bg)
        row.pack(anchor="w", pady=(0, 6))
        ttk.Label(row, text=tr("输入 UNINSTALL 以确认"), style="UI.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(row, textvariable=self.var_confirm, width=16).pack(side="left")
        tk.Checkbutton(
            form, text=tr("同时删除本程序文件"), variable=self.var_del_self,
            bg=bg, activebackground=bg, fg=COLORS["text_dim"],
            font=config.font("small"), anchor="w"
        ).pack(anchor="w", pady=(0, 8))
        self.btn_uninstall = ttk.Button(
            form, text=tr("🗑  卸载并清除数据"),
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
            text=tr("上次卸载: {when}").format(when=self.dm.uninstall_last)
            if self.dm.uninstall_last else tr("从未卸载过.")
        )

    def on_uninstall(self):
        if self.var_confirm.get().strip() != "UNINSTALL":
            return
        if not toast.ask(
            tr("这将永久删除全部数据并恢复网络.\n\n不可撤销.继续吗?"),
            title=tr("卸载确认"), danger=True
        ):
            return
        self.do_uninstall()

    def do_uninstall(self):
        self.dm.uninstalling = True
        self._cancel_jobs()
        self.net.release()

        self.dm.uninstall_count += 1
        self.dm.uninstall_last = datetime.now().strftime('%Y-%m-%d %H:%M')
        self.dm.save_uninstall_count()

        self.dm.erase_all_data()

        removed_self = False
        if self.var_del_self.get():
            try:

                os.remove(os.path.abspath(sys.argv[0]))
                removed_self = True
            except OSError:
                pass

        toast.info(
            tr("全部数据已清除、网络已恢复.\n累计卸载次数: {n}").format(
                n=self.dm.uninstall_count)
            + ("" if not self.var_del_self.get() else
               (tr("\n程序文件已删除.") if removed_self else
                tr("\n无法删除程序文件,请手动移除.")))
        )
        self.root.destroy()
