

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
    ensure_builtin_chime, load_json_file, save_json_file,
    compute_F, fmt_hm, fmt_ms
)
from i18n import tr
from net_guard import NetGuard
from data_manager import DataManager
from settings_manager import SettingsManager
from pages import CalendarPage, HourLogPage, SettingsPage, RulesPage, StatsPage
from pages.widgets import (wrap_label, frozen, LoadingCover, cfg,
                           show_pack, hide_pack)


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
        root.resizable(False, False)
        self.style = ttk.Style(root)


        self.state = IDLE
        self.start_mono = None
        self.start_wall = None
        self.break_start_wall = None
        self.last_t_minutes = 0.0
        self.countdown_seconds = 0
        self.update_job = None
        self.midnight_job = None
        self.hourly_job = None
        self.net_job = None
        self.next_hour = None
        self.current_page = "timer"



        self.dm = DataManager()
        self.timer_file = os.path.join(self.dm.data_dir, "timer_state.json")
        self.break_carry = self._load_break_carry()
        self.settings = SettingsManager()
        i18n.init_from_config()
        config.UI_SCALE = self.ui_scale * float(self.settings.value("FONT_SCALE") or 1.0)
        self._apply_theme()
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
        # 先定好窗口大小, 再在加载页后面一页一页地建界面
        self._apply_geometry()
        cover = LoadingCover(root, tr("正在加载…"), "", steps=self.LAYOUT_STEPS).show()
        try:
            self._build_layout(root, cover)
            self.show_page("timer")
            self.refresh_display()
            self.update_log_badge()
            self.update_settings_badge()
        finally:
            with frozen(root):
                cover.close()

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


    def _apply_theme(self):
        """按设置里的 THEME 换色: 根窗口底色, tk 控件默认色, ttk 样式, 标题栏."""
        config.apply_theme(getattr(config, "THEME", config.DEFAULT_THEME))
        self.root.configure(bg=COLORS["bg"])
        self._apply_tk_options()
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self._theme_ttk()
        self._apply_titlebar()

    def _apply_tk_options(self):
        """没有单独指定颜色的 tk 控件 (列表框, 多行文本, 下拉框弹出列表) 的默认色."""
        t, r = config.TTK_COLORS, self.root
        for cls in ("Listbox", "Text"):
            r.option_add(f"*{cls}.background", t["list_bg"], "interactive")
            r.option_add(f"*{cls}.foreground", t["list_fg"], "interactive")
            r.option_add(f"*{cls}.selectBackground", t["list_select"], "interactive")
            r.option_add(f"*{cls}.selectForeground", t["list_on_select"], "interactive")
            r.option_add(f"*{cls}.highlightColor", COLORS["accent"], "interactive")
        r.option_add("*Text.insertBackground", t["list_fg"], "interactive")
        r.option_add("*Button.highlightThickness", 0, "interactive")
        r.option_add("*TCombobox*Listbox.background", t["list_bg"], "interactive")
        r.option_add("*TCombobox*Listbox.foreground", t["list_fg"], "interactive")
        r.option_add("*TCombobox*Listbox.selectBackground", t["list_select"], "interactive")
        r.option_add("*TCombobox*Listbox.selectForeground", t["list_on_select"], "interactive")

    def _apply_titlebar(self):
        """Windows 10/11: 深色主题时让标题栏也变成深色."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            dark = ctypes.c_int(1 if config.THEME.endswith("_dark") else 0)
            for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (新 / 旧版本号)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                    break
        except Exception:
            pass

    def _theme_ttk(self):
        s = self.style
        bg, card = COLORS["bg"], COLORS["bg_card"]
        ac, tx = COLORS["accent"], COLORS["text"]
        td = COLORS["text_dim"]
        on_ac = COLORS["on_accent"]
        t = config.TTK_COLORS

        # clam 的基础色: 普通按钮 / 输入框 / 滚动条 / 下拉框等都从这里取色
        s.configure(
            ".", background=t["frame"], foreground=t["fg"],
            bordercolor=t["border"], lightcolor=t["light"], darkcolor=t["dark"],
            troughcolor=t["trough"], fieldbackground=t["field"],
            selectbackground=t["select"], selectforeground=t["on_select"],
            insertcolor=t["fg"], arrowcolor=t["fg"], focuscolor=t["border"]
        )
        s.map(".", foreground=[("disabled", t["disabled_fg"])],
              background=[("disabled", t["frame"]), ("active", t["frame_hover"])])
        s.map("TButton",
              background=[("disabled", t["frame"]), ("pressed", t["dark"]),
                          ("active", t["frame_hover"])],
              foreground=[("disabled", t["disabled_fg"])])
        s.map("TCombobox",
              fieldbackground=[("readonly", "focus", t["select"]),
                               ("readonly", t["frame"]), ("disabled", t["frame"])],
              foreground=[("readonly", "focus", t["on_select"]),
                          ("disabled", t["disabled_fg"])],
              background=[("active", t["frame_hover"]), ("pressed", t["frame_hover"])])
        s.map("TEntry", fieldbackground=[("readonly", t["frame"]),
                                         ("disabled", t["frame"])])
        s.map("TSpinbox", fieldbackground=[("readonly", t["frame"]),
                                           ("disabled", t["frame"])])
        s.map("TScrollbar", background=[("active", t["frame_hover"]),
                                        ("pressed", t["frame_hover"])])
        s.configure("TCheckbutton", background=bg, foreground=tx,
                    indicatorbackground=t["field"], indicatorforeground=t["fg"],
                    upperbordercolor=t["border"], lowerbordercolor=t["border"])
        s.map("TCheckbutton",
              background=[("active", bg)],
              indicatorbackground=[("pressed", t["frame"]), ("selected", t["field"])])
        s.configure("TLabel", background=bg, foreground=tx)
        s.configure("TFrame", background=bg)

        s.configure("Card.TFrame", background=card)
        s.configure("TopBar.TFrame", background=COLORS["accent"])

        s.configure("UI.TLabel", background=bg, foreground=td, font=config.font("body"))
        s.configure("UI.Bold.TLabel", background=bg, foreground=tx, font=config.font("body", bold=True))
        s.configure("Card.TLabel", background=card, foreground=tx, font=config.font("body"))
        s.configure("Card.Bold.TLabel", background=card, foreground=COLORS["text_strong"],
                    font=config.font("body", bold=True))
        s.configure("UI.TCheckbutton", background=bg, foreground=td, font=config.font("small"))
        s.map("UI.TCheckbutton", background=[("active", bg)],
              foreground=[("active", tx)])

        s.configure(
            "Accent.TButton",
            background=ac, foreground=on_ac,
            bordercolor=ac, lightcolor=ac, darkcolor=ac,
            font=config.font("body", bold=True),
            borderwidth=0, focusthickness=0, padding=(18, 10)
        )
        s.map(
            "Accent.TButton",
            background=[("disabled", COLORS["accent_disabled"]),
                        ("active", COLORS["accent_hover"])],
            foreground=[("disabled", COLORS["on_accent_disabled"])],
            bordercolor=[("disabled", COLORS["accent_disabled"]),
                         ("active", COLORS["accent_hover"])],
            lightcolor=[("disabled", COLORS["accent_disabled"]),
                        ("active", COLORS["accent_hover"])],
            darkcolor=[("disabled", COLORS["accent_disabled"]),
                       ("active", COLORS["accent_hover"])]
        )

        s.configure("UI.TSeparator", background=COLORS["border"])
        s.configure(
            "Quota.Horizontal.TProgressbar",
            troughcolor=COLORS["border"], background=ac,
            bordercolor=COLORS["border"], lightcolor=ac, darkcolor=ac,
            borderwidth=0, thickness=8
        )
        dg = COLORS["danger"]
        s.configure(
            "Danger.TButton",
            background=dg, foreground=on_ac,
            bordercolor=dg, lightcolor=dg, darkcolor=dg,
            font=config.font("body", bold=True),
            borderwidth=0, focusthickness=0, padding=(18, 10)
        )
        s.map(
            "Danger.TButton",
            background=[("disabled", COLORS["danger_disabled"]),
                        ("active", COLORS["danger_hover"])],
            foreground=[("disabled", on_ac)],
            bordercolor=[("disabled", COLORS["danger_disabled"]),
                         ("active", COLORS["danger_hover"])],
            lightcolor=[("disabled", COLORS["danger_disabled"]),
                        ("active", COLORS["danger_hover"])],
            darkcolor=[("disabled", COLORS["danger_disabled"]),
                       ("active", COLORS["danger_hover"])]
        )


    # _layout_steps 每建好一部分 yield 一次 (供加载页前进进度条); 次数 = LAYOUT_STEPS
    LAYOUT_STEPS = 9

    def _build_layout(self, parent, cover=None):
        for _ in self._layout_steps(parent):
            if cover is not None:
                cover.step()

    def _prepare_page(self, page):
        """在加载页后面把页面先排一次版 (创建好所有子窗口), 再收起来.
        这样第一次切到这页时不用再从头创建, 切换更快."""
        page.grid(row=0, column=0, sticky="nsew")
        try:
            page.update_idletasks()
        except Exception:
            pass
        page.grid_remove()

    def _layout_steps(self, parent):
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
            "rules": tr("🛡  Rules"),
            "log": tr("📝  Hour Log"),
            "cal": tr("📅  Calendar"),
            "stats": tr("📊  Statistics"),
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
        yield

        # 只有当前页挂在界面上 (grid), 其余页 grid_remove:
        # 看不见的页面不参与布局和重画, 每秒的刷新也不会去画它们.
        self.pages["cal"] = CalendarPage(self.content, self.dm)
        self._prepare_page(self.pages["cal"])
        yield
        self.pages["stats"] = StatsPage(self.content, self.dm, self.net,
                                        focus_live=self._focus_live)
        self._prepare_page(self.pages["stats"])
        yield
        self.pages["log"] = HourLogPage(
            self.content, self.dm,
            on_text_changed=self.update_log_badge,
            on_toggle=self.on_hour_log_toggle,
            on_open_settings=lambda: self.show_page("settings")
        )
        self._prepare_page(self.pages["log"])
        yield
        self.pages["settings"] = SettingsPage(
            self.content, self.settings,
            on_changed=self.on_settings_changed, on_sound=self.play_chime,
            on_dev_mode=self.on_dev_mode_changed,
            on_language=self.on_language_changed,
            on_font_scale=self.on_font_scale_changed,
            on_theme=self.on_theme_changed
        )
        self._prepare_page(self.pages["settings"])
        yield
        self.pages["rules"] = RulesPage(
            self.content, self.net.proxy, settings=self.settings,
            on_changed=self.on_settings_changed,
            on_open_settings=lambda: self.show_page("settings")
        )
        self._prepare_page(self.pages["rules"])
        yield
        self.pages["net"] = tk.Frame(self.content, bg=bg)
        self._build_net_page(self.pages["net"])
        self._prepare_page(self.pages["net"])
        yield
        self.pages["timer"] = tk.Frame(self.content, bg=bg)
        self._build_timer_page(self.pages["timer"])
        self._prepare_page(self.pages["timer"])
        yield
        self.pages["uninstall"] = tk.Frame(self.content, bg=bg)
        self._build_uninstall_page(self.pages["uninstall"])
        self._prepare_page(self.pages["uninstall"])
        yield


    def rebuild_ui(self):
        if self._rebuilding or self.shutting_down:
            return
        self._rebuilding = True
        # 加载页盖住整个窗口; 旧界面在它后面拆掉, 新界面在它后面一页一页建好
        # (进度条随之前进), 最后在冻结中撤掉加载页, 新界面整窗一次显示.
        cover = LoadingCover(self.root, tr("正在重新加载界面…"),
                             tr("切换语言 / 字号 / 主题需要重建所有页面,请稍候"),
                             steps=self.LAYOUT_STEPS + 1).show()
        try:
            self._rebuild_ui(cover)
        finally:
            try:
                with frozen(self.root):
                    cover.close()
            finally:
                self._rebuilding = False

    def _rebuild_ui(self, cover=None):
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
        self._apply_theme()
        if cover is not None:
            cover.recolor()
            cover.step()
        self.pages = {}
        self.nav_btns = {}
        self._apply_geometry()
        self._build_layout(self.root, cover)
        self.show_page(self.current_page or "timer")

        self.refresh_display()
        self.update_log_badge()
        self.update_settings_badge()
        self._start_midnight_timer()
        self._schedule_hourly()
        self._restore_timer_view()
        self._schedule_apply_check()
        self._net_tick()

    def on_language_changed(self):
        i18n.init_from_config()
        self.rebuild_ui()

    def on_theme_changed(self):
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
        # 先在冻结状态下刷新目标页、再置顶, 最后整窗一次性显示 —— 避免切换时的撕裂
        with frozen(self.root):
            self._show_page(key)

    def _show_page(self, key: str):
        self.current_page = key
        for k, b in self.nav_btns.items():
            if k == key:
                cfg(b,
                    bg=COLORS["accent"], fg=COLORS["on_accent"],
                    activebackground=COLORS["accent_hover"],
                    activeforeground=COLORS["on_accent"]
                )
            else:
                cfg(b,
                    bg=COLORS["bg_card"], fg=COLORS["text"],
                    activebackground=COLORS["border"], activeforeground=COLORS["text"]
                )
        # 只把目标页挂到界面上, 其余页收起 (不参与布局 / 重画)
        target = self.pages[key]
        if target.winfo_manager() != "grid":
            target.grid(row=0, column=0, sticky="nsew")
        for k, f in self.pages.items():
            if k != key and f.winfo_manager() == "grid":
                f.grid_remove()
        if key == "cal":
            self.pages["cal"].show()
        elif key == "stats":
            self.pages["stats"].show()
        elif key == "net":
            self.refresh_net(force=True)
        elif key == "rules":
            self.pages["rules"].refresh(force=True)
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
            inner, text=self._idle_sub_text(),
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
            self.dm.add_focus_session("study", self.start_wall, end_wall)
            self.refresh_display()

            self.state = READY_BREAK
            self.cancel_update()
            self._show_ready_break()

        elif self.state == READY_BREAK:
            total = self._break_seconds()
            if total <= 0:
                toast.info(tr("剩余时间为 0,已重置."))
                self.reset_to_idle()
                return
            if self.break_carry > 0:
                self._set_break_carry(0)
            self.countdown_seconds = total
            self.state = ON_BREAK
            self.break_start_wall = datetime.now()
            self._show_on_break()
            self.schedule_update()

        elif self.state == ON_BREAK:
            self.end_break_early()

    # ---- 休息: 建议时长 + 之前暂停休息结转的时间 ----

    def _break_seconds(self) -> int:
        """本次休息总秒数 = 建议休息时长 + 结余."""
        fval = max(0.0, compute_F(self.last_t_minutes))
        base = int(round(fval * 60.0))
        total = base + int(self.break_carry)
        return max(1, total) if total > 0 else 0

    def _show_ready_break(self):
        self.btn_action.config(text=tr("☕  去休息"), state="!disabled")
        total = self._break_seconds()
        self.lbl_time.config(text=fmt_ms(total))
        sub = tr("已工作 {m:.2f} 分钟 → 上方是建议休息时长").format(m=self.last_t_minutes)
        if self.break_carry > 0:
            sub += "\n" + tr("(含之前暂停休息结转的 {c})").format(c=fmt_ms(self.break_carry))
        self.lbl_sub.config(text=sub)
        self._status(tr("本次专注结束"), COLORS["success"])

    def _show_on_break(self):
        self.btn_action.config(text=tr("⏸  暂停休息"))
        self._status(tr("休息中 ☕"), COLORS["warn"])
        self.lbl_sub.config(text=tr("休息吧,倒计时中…"))
        self._sync_break_lock()

    def _break_locked(self) -> bool:
        """网络正在使用时不允许暂停休息."""
        return self.state == ON_BREAK and self.net.mode == "online"

    def _sync_break_lock(self):
        if self.state == ON_BREAK:
            self.btn_action.config(state="disabled" if self._break_locked() else "!disabled")

    def end_break_early(self, silent: bool = False):
        """暂停休息(关闭程序也算):剩余时间 ×BREAK_CARRY_RATE 计入下一次休息."""
        if self.state != ON_BREAK:
            return
        if not silent and self._break_locked():
            toast.warn(tr("网络正在使用,不能暂停休息."))
            return
        self._record_break_end()
        left = max(0, int(self.countdown_seconds))
        add = int(round(left * config.BREAK_CARRY_RATE))
        if add > 0:
            self._set_break_carry(self.break_carry + add)
            if not silent:
                toast.info(tr("休息已暂停.\n剩余 {left} 按 ×{r:g} 计入下次休息: +{add}").format(
                    left=fmt_ms(left), r=config.BREAK_CARRY_RATE, add=fmt_ms(add)))
        if silent:
            self.state = IDLE
            self.countdown_seconds = 0
        else:
            self.reset_to_idle()

    def _record_break_end(self):
        """一段休息结束 (自然结束 / 暂停 / 关闭程序): 记入专注计时统计."""
        if self.break_start_wall is not None:
            self.dm.add_focus_session("break", self.break_start_wall, datetime.now())
            self.break_start_wall = None

    def _focus_live(self):
        """正在进行的一段, 供 Statistics 页画到此刻: (kind, 开始时刻) 或 None."""
        if self.state == RUNNING and self.start_wall is not None:
            return ("study", self.start_wall)
        if self.state == ON_BREAK and self.break_start_wall is not None:
            return ("break", self.break_start_wall)
        return None

    def _idle_sub_text(self) -> str:
        text = tr("开始专注时按 [开始].")
        if self.break_carry > 0:
            text += "\n" + tr("下次休息额外 +{c}").format(c=fmt_ms(self.break_carry))
        return text

    def _load_break_carry(self) -> int:
        d = load_json_file(self.timer_file, {})
        try:
            return max(0, int(d.get("break_carry", 0))) if isinstance(d, dict) else 0
        except (TypeError, ValueError):
            return 0

    def _set_break_carry(self, seconds: int):
        self.break_carry = max(0, int(seconds))
        if not self.dm.uninstalling:
            save_json_file(self.timer_file, {"break_carry": self.break_carry})

    def _restore_timer_view(self):
        """界面重建 (换语言 / 字号) 后按当前状态恢复计时器页."""
        if self.state == RUNNING:
            self.btn_action.config(text=tr("■  结束"))
            self._status(tr("专注中…"), COLORS["accent"])
            self.schedule_update()
        elif self.state == READY_BREAK:
            self._show_ready_break()
        elif self.state == ON_BREAK:
            self._show_on_break()
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
                sub = tr("休息剩余 {m} 分 {s:02d} 秒").format(m=m, s=s)
                if self._break_locked():
                    sub += "\n" + tr("网络正在使用,不能暂停休息.")
                self.lbl_sub.config(text=sub)
                self.countdown_seconds -= 1
                self.update_job = self.root.after(1000, self.update)
            else:
                self._record_break_end()
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
        self.lbl_sub.config(text=self._idle_sub_text())
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
            self.dm.prune_study_data()
        # 不清 prompt_slot:昨天 23:00 那格现在显示在今天最上方,仍可填写.
        self.dm.finalize_hours()
        self.dm.save_hour_log()
        self.update_log_badge()
        self.pages["log"].refresh()
        self.refresh_display()
        self._refresh_if_visible("cal", "stats")
        self._schedule_midnight()

    def _refresh_if_visible(self, *keys):
        for key in keys:
            if self.current_page == key and key in self.pages:
                self.pages[key].refresh()

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
        if "NET_MODE" in due:
            self.net.sync_mode()
        if "rules" in self.pages:
            self.pages["rules"].refresh(force=True)
        self.pages["settings"].refresh()
        self.update_settings_badge()
        self.refresh_net(force=True)
        labels = ",".join(tr(self.settings.display(k)) for k in due)
        toast.success(tr("48 小时冷静期已结束,以下配置从现在开始生效:") + "\n" + labels)
        self._log_notice(f"SETTINGS applied: {', '.join(due)}")
        return due

    def _sync_hour_log_setting(self):
        want = bool(self.settings.value("HOUR_LOG_ENABLED"))
        if want != self.dm.hour_enabled:
            self.dm.apply_hour_enabled(want)
        if "log" in self.pages:
            self.pages["log"].refresh()
        self._refresh_if_visible("stats")
        self.update_log_badge()

    def _log_notice(self, text: str):
        try:
            with open(os.path.join(self.dm.data_dir, "settings_changes.log"),
                      'a', encoding='utf-8') as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
        except IOError:
            pass






    def on_close(self):
        self.end_break_early(silent=True)
        self._cancel_jobs()
        self.net.shutdown()
        self.root.destroy()

    def update_log_badge(self):
        b = self.nav_btns.get("log")
        if not b:
            return
        if not self.dm.hour_enabled:
            cfg(b, text=self.nav_labels["log"] + "  (off)")
        else:
            cfg(b, text=self.nav_labels["log"] + (" ●" if self.dm.awaiting_slot() else ""))

    def on_hour_log_toggle(self, enabled: bool):
        self.update_log_badge()
        if "log" in self.pages:
            self.pages["log"].refresh()

    def on_settings_changed(self, status: str = "", key: str = None):
        self.update_settings_badge()
        if "rules" in self.pages and key in ("FILTER_MODE", "NET_MODE", None):
            self.pages["rules"].refresh(force=True)
        if key in ("NET_MODE", None) and self.net.sync_mode():
            self.refresh_net(force=True)
            self._log_notice(f"NET_MODE -> {self.net.net_mode}")
        if status != "instant":
            return
        if key in ("HOUR_LOG_ENABLED", "AUTO_TEXT", "FILL_WINDOW", None):

            if key in ("AUTO_TEXT", "FILL_WINDOW", None):
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
        if config.dev_mode_enabled():
            mark += "  🛠"
        cfg(b, text=self.nav_labels["settings"] + mark)


    def on_dev_mode_changed(self, enabled: bool):
        if not config.dev_mode_defined():
            return
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
            hdr, text="", bg=bg, fg=COLORS["text_dim"], font=config.font("body"),
            anchor="w", justify="left"
        )
        self.net_lbl_header.pack(anchor="w", fill="x", pady=(4, 0))
        wrap_label(self.net_lbl_header, 8)

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
        tk.Label(
            row2, text=tr("多个理由用 / 连接,如「查资料/下载课件」"),
            bg=bg, fg=COLORS["text_dim"], font=config.font("small")
        ).pack(side="left", padx=(10, 0))

        btns = tk.Frame(self.net_form, bg=bg)
        btns.pack(anchor="w")
        self.btn_net_req = ttk.Button(
            btns, text=tr("📨  提交申请(需冷静期)"), style="Accent.TButton",
            command=self.on_net_request
        )
        self.btn_net_req.pack(side="left")
        self.btn_net_quick = ttk.Button(
            btns, text=tr("⚡  快速访问(×{a:g})").format(a=config.QUICK_MULTIPLIER),
            style="Danger.TButton", command=self.on_net_quick
        )
        self.btn_net_quick.pack(side="left", padx=(8, 0))
        self.btn_net_loan = ttk.Button(
            btns, text=tr("💳  紧急借贷"), style="Danger.TButton",
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
            self.net_ctrl, text=tr("⚡  改为快速访问(×{a:g})").format(a=config.QUICK_MULTIPLIER),
            style="Danger.TButton",
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
        rate = 1.0
        if self.state == ON_BREAK and minutes * 60 <= self.countdown_seconds:
            # 休息中, 且申请时长不超过剩余休息时间 → 冷静期 ×BREAK_COOLDOWN_RATE
            rate = config.BREAK_COOLDOWN_RATE
        ok, msg = self.net.request(minutes, reason, cooldown_rate=rate)
        if not ok:
            toast.warn(tr(msg))
            return
        self.var_reason.set("")
        self.refresh_net(force=True)

    def on_net_quick(self):
        ok, minutes, reason = self._read_net_form()
        if not ok:
            return
        ok2, msg2 = self.net.can_quick(minutes)
        if not ok2:
            toast.warn(tr(msg2))
            return
        if not toast.ask(
            tr("快速访问跳过冷静期立刻联网,额度按 ×{a:g} 消耗.\n\n联网: {m} 分钟\n消耗: {cost} 今日额度\n\n确定吗?").format(
                a=config.QUICK_MULTIPLIER, m=minutes,
                cost=fmt_hm(minutes * 60 * config.QUICK_MULTIPLIER)),
            title=tr("快速访问"), danger=True
        ):
            return
        ok, msg = self.net.request(minutes, reason, quick=True)
        if not ok:
            toast.warn(tr(msg))
            return
        self.var_reason.set("")
        self.refresh_net(force=True)

    def on_net_loan(self):
        ok, minutes, reason = self._read_net_form()
        if not ok:
            return
        ok2, msg2 = self.net.can_borrow(minutes)
        if not ok2:
            toast.warn(tr(msg2))
            return
        if not toast.ask(
            tr("紧急借贷不会联网,只会给今天加额度;代价是明天扣 {b:g} 倍.\n借到的额度今天用不完也不退.\n\n今天额度: +{add}\n明天额度: -{cost}\n\n确定吗?").format(
                b=config.LOAN_RATE, add=fmt_hm(minutes * 60),
                cost=fmt_hm(minutes * 60 * config.LOAN_RATE)),
            title=tr("紧急借贷"), danger=True
        ):
            return
        ok, msg = self.net.borrow(minutes, reason)
        if not ok:
            toast.warn(tr(msg))
            return
        self.var_reason.set("")
        toast.success(tr("今天额度 +{add}.").format(add=fmt_hm(minutes * 60)))
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
        ok2, msg2 = self.net.can_quick(minutes)
        if not ok2:
            toast.warn(tr(msg2))
            return
        if not toast.ask(
            tr("立刻结束冷静期并联网?\n\n联网: {m} 分钟\n消耗: {cost} 今日额度(×{a:g})\n\n确定吗?").format(
                m=minutes, cost=fmt_hm(minutes * 60 * config.QUICK_MULTIPLIER), a=config.QUICK_MULTIPLIER),
            title=tr("快速访问"), danger=True
        ):
            return
        ok, msg = self.net.convert_to_quick()
        if not ok:
            toast.warn(tr(msg))
            return
        self.refresh_net(force=True)

    def _net_set_status(self, text: str, color: str):
        cfg(self.net_lbl_status, text=text)
        if self.net_dot_canvas.itemcget(self.net_dot_id, "fill") != color:
            self.net_dot_canvas.itemconfig(self.net_dot_id, fill=color)

    def _net_bar_set(self, n):
        mx, val = max(1.0, n.today_total), float(n.quota_used)
        try:
            if float(self.net_bar["maximum"]) != mx:
                self.net_bar["maximum"] = mx
            if abs(float(self.net_bar["value"]) - val) >= 0.5:
                self.net_bar["value"] = val
        except Exception:
            self.net_bar["maximum"] = mx
            self.net_bar["value"] = val

    def refresh_net(self, force: bool = False):
        n = self.net
        mode = n.mode
        cooldown = int(self.settings.value("COOLDOWN"))
        cooldown_m = f"{cooldown / 60:g}"

        header = (tr("申请 → {min} 分钟冷静期 → 联网 → 到点自动断网").format(min=cooldown_m)
                  + "    ·    " + tr("⚡ 快速访问免冷静期(×{a:g})  ·  💳 借 1 分钟扣明天 {b:g} 分钟").format(
                      a=config.QUICK_MULTIPLIER, b=config.LOAN_RATE))
        if self.state == ON_BREAK:
            header += "\n" + tr("☕ 休息中提交申请,冷静期 ×{r:g}: 只需 {t}").format(
                r=config.BREAK_COOLDOWN_RATE, t=fmt_ms(cooldown * config.BREAK_COOLDOWN_RATE)) \
                + tr("(申请时长不超过剩余休息 {left} 时生效)").format(
                    left=fmt_ms(self.countdown_seconds))
        cfg(self.net_lbl_header, text=header, justify="left")

        if mode == "dev":


            self._net_set_status("Developer mode — network unrestricted", COLORS["warn"])
            cfg(self.net_lbl_time, text="DEV")
            cfg(self.net_lbl_sub, 
                text=tr("开发者模式已开启:本程序不会断网,也不会申请/计时.\n"
                        "调试完成后请到 Settings 页关掉它.")
            )
            hide_pack(self.net_form)
            hide_pack(self.net_ctrl)
            self._net_bar_set(n)
            cfg(self.net_lbl_quota, 
                text=f"Used today: {fmt_hm(n.quota_used)} / {fmt_hm(n.today_total)}"
                     f"     (developer mode — not counting)"
            )
            cfg(self.net_lbl_debt, text="")
            return

        if mode != self._net_view or force:
            self._net_view = mode
            # 只在需要时才收起 / 显示 (重复 pack 会触发整页重新布局)
            if mode == "offline":
                hide_pack(self.net_ctrl)
                show_pack(self.net_form, anchor="w", fill="x")
            else:
                hide_pack(self.net_form)
                show_pack(self.net_ctrl, anchor="w")
                cfg(self.btn_net_ctrl, 
                    text=tr("✕  取消申请") if mode == "pending" else tr("■  结束本次会话")
                )
                if mode == "pending":
                    cfg(self.btn_net_upgrade, 
                        text=tr("⚡  改为快速访问(×{a:g})").format(a=config.QUICK_MULTIPLIER))
                    show_pack(self.btn_net_upgrade, side="left", padx=(8, 0))
                    show_pack(self.net_ctrl_hint, anchor="w", pady=(8, 0))
                else:
                    hide_pack(self.btn_net_upgrade)
                    hide_pack(self.net_ctrl_hint)

        if mode == "offline":
            self._net_set_status(tr("离线"), COLORS["text_dim"])
            cfg(self.net_lbl_time, text=tr("离线"))
            if n.remaining < 60:
                cfg(self.net_lbl_sub, text=tr("今天的额度已用完."))
                cfg(self.btn_net_req, state="disabled")
            else:
                cfg(self.net_lbl_sub, 
                    text=tr("在下面提交申请,冷静期结束后自动联网.")
                )
                cfg(self.btn_net_req, state="!disabled")
            cfg(self.btn_net_quick, 
                text=tr("⚡  快速访问(×{a:g})").format(a=config.QUICK_MULTIPLIER),
                state="!disabled" if n.quick_left >= 60 else "disabled")
            cfg(self.btn_net_loan, 
                state="!disabled" if n.loan_left >= 60 else "disabled")
        elif mode == "pending":
            p = n.pending
            self._net_set_status(tr("冷静期中 —— 仍可取消"), COLORS["warn"])
            cfg(self.net_lbl_time, text=fmt_ms(p["at"] - time.time()))
            start_at = datetime.fromtimestamp(p["at"]).strftime("%H:%M")
            cfg(self.net_lbl_sub, 
                text=tr("已申请 {m} 分钟 · {at} 联网").format(m=p['minutes'], at=start_at)
            )
            ok, msg = n.can_quick(p["minutes"])
            if ok:
                cfg(self.net_ctrl_hint, 
                    text=tr("⚡ 可改为快速访问立刻联网:消耗 {cost} 今日额度(×{a:g}).").format(
                        cost=fmt_hm(p["minutes"] * 60 * config.QUICK_MULTIPLIER), a=config.QUICK_MULTIPLIER),
                    fg=COLORS["text_dim"]
                )
            else:
                cfg(self.net_ctrl_hint, text="⚡ " + msg, fg=COLORS["text_dim"])
        else:
            self._net_set_status(tr("联网中"), COLORS["success"])
            cfg(self.net_lbl_time, text=fmt_ms(n.grant_left))
            if n.grant_quick:
                cfg(self.net_lbl_sub, 
                    text=tr("⚡ 快速访问 —— 额度按 ×{a:g} 消耗,归零自动断网.").format(
                        a=n.grant_rate)
                )
            else:
                cfg(self.net_lbl_sub, 
                    text=tr("本次会话剩余时间,归零自动断网.")
                )


        if mode == "offline":
            usermin = self._safe_minutes()
            parts = []
            if usermin and n.can_quick(usermin)[0]:
                parts.append(tr("⚡ 快速访问 {m} 分钟:立刻联网,消耗 {cost} 今日额度.").format(
                    m=usermin, cost=fmt_hm(usermin * 60 * config.QUICK_MULTIPLIER)))
            else:
                parts.append(tr("⚡ 快速访问:跳过冷静期,额度按 ×{a:g} 消耗;最多 {cap}.").format(
                    a=config.QUICK_MULTIPLIER, cap=fmt_hm(n.quick_left)))
            if n.loan_left < 60:
                parts.append(tr("💳 明天的额度已经借完了."))
            elif usermin and n.can_borrow(usermin)[0]:
                parts.append(tr("💳 借 {m} 分钟:今天额度 +{add},明天额度 -{cost}.最多可借 {cap}.").format(
                    m=usermin, add=fmt_hm(usermin * 60),
                    cost=fmt_hm(usermin * 60 * config.LOAN_RATE), cap=fmt_hm(n.loan_left)))
            else:
                parts.append(tr("💳 紧急借贷:今天额度 +1 分钟,明天额度 -{b:g} 分钟;最多可借 {cap}.").format(
                    b=config.LOAN_RATE, cap=fmt_hm(n.loan_left)))
            cfg(self.net_loan_hint, text="\n".join(parts), fg=COLORS["text_dim"])

        self._net_bar_set(n)
        cfg(self.net_lbl_quota, 
            text=tr("今日已用: {used} / {total}     今日剩余: {left}     可快速访问: {quick}").format(
                used=fmt_hm(n.quota_used), total=fmt_hm(n.today_total),
                left=fmt_hm(n.remaining), quick=fmt_hm(n.quick_left))
        )
        bits = []
        mult = n.quota_multiplier
        if abs(mult - 1.0) > 1e-9:
            bits.append(tr("今天的联网倍率 ×{m}: 每日额度 {base} → 今天 {quota}").format(
                m=f"{mult:g}", base=fmt_hm(float(config.DAILY_LIMIT)), quota=fmt_hm(n.limit)))
        if n.bonus > 0:
            bits.append(tr("今天已借 {bonus},明天将扣 {cost}(明天剩余 {left})").format(
                bonus=fmt_hm(n.bonus), cost=fmt_hm(n.tomorrow_used),
                left=fmt_hm(n.tomorrow_remaining)))
        if n.debt > 0:
            bits.append(tr("今天要先还昨天借的 {debt}").format(debt=fmt_hm(n.debt)))
        cfg(self.net_lbl_debt, text="\n".join(bits))

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
        self._sync_break_lock()
        if self.current_page == "rules" and "rules" in self.pages:
            self.pages["rules"].refresh()
        self.net_job = self.root.after(1000, self._net_tick)

        if event:
            self._refresh_if_visible("stats")
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

        warn_fr = tk.Frame(page, bg=COLORS["danger_bg"], highlightbackground=danger, highlightthickness=1)
        warn_fr.pack(padx=26, pady=(0, 10), fill="x")
        tk.Label(
            warn_fr, text=tr("⚠  警告:这会永久删除全部数据"),
            bg=COLORS["danger_bg"], fg=danger, font=config.font("body", bold=True),
            anchor="w"
        ).pack(fill="x", padx=16, pady=(10, 2))
        tk.Label(
            warn_fr, justify="left", anchor="w", bg=COLORS["danger_bg"], fg=COLORS["text"],
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
        ttk.Checkbutton(
            form, text=tr("同时删除本程序文件"), variable=self.var_del_self,
            style="UI.TCheckbutton"
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
            tr("全部数据已清除,网络已恢复.\n累计卸载次数: {n}").format(
                n=self.dm.uninstall_count)
            + ("" if not self.var_del_self.get() else
               (tr("\n程序文件已删除.") if removed_self else
                tr("\n无法删除程序文件,请手动移除.")))
        )
        self.root.destroy()
