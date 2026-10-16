

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, ttk

import config
import toast
from config import COLORS
from i18n import tr
from settings_manager import (APPLY_INSTANT, SCHEMA_BY_KEY, BASIC_SPECS, DETAIL_SPECS,
                              WEEKDAY_SPECS)
from .widgets import (ScrollArea, Switch, wrap_label, frozen, smooth, cfg, set_var,
                      show_pack, hide_pack, show_grid, hide_grid)


class SettingsPage(tk.Frame):
    def __init__(self, master, settings, on_changed=None, on_sound=None,
                 on_dev_mode=None, on_language=None, on_font_scale=None,
                 on_theme=None):
        super().__init__(master, bg=COLORS["bg"])
        self.sm = settings
        self.on_changed = on_changed
        self.on_sound = on_sound
        self.on_dev_mode = on_dev_mode
        self.on_language = on_language
        self.on_font_scale = on_font_scale
        self.on_theme = on_theme
        self._rows = {}          # 基本设置页的行
        self._num_rows = {}      # 具体设置页 / 星期倍率页的行
        self._tab = "basic"
        self._syncing = False
        self.sw_dev = None
        self.lbl_dev_state = None

        self._i18n_widgets = []
        self._choices_widgets = []
        self._build()


    def _track(self, widget, key=None, *, translate: bool = True):
        self._i18n_widgets.append((widget, key, translate))
        return widget

    def _retranslate(self):
        for widget, key, translate in self._i18n_widgets:
            try:
                if callable(key):
                    widget.config(text=key())
                else:
                    widget.config(text=tr(key) if translate else key)
            except Exception:
                continue

        for key, widget in self._choices_widgets:
            try:
                widget.config(values=[lab for _v, lab in
                                      self.sm.labeled_values(key, translate=True)])
            except Exception:
                continue

    def _build(self):
        bg = COLORS["bg"]

        hdr = tk.Frame(self, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(18, 6))
        self._track(tk.Label(
            hdr, text=tr("⚙  设置"), bg=bg, fg=COLORS["text"],
            font=config.font("h1", bold=True)
        ), "⚙  设置").pack(side="left")

        tabs = tk.Frame(hdr, bg=bg)
        tabs.pack(side="left", padx=(24, 0))
        self._tab_btns = {}
        for key, text in (("basic", "基本设置"), ("detail", "具体设置"),
                          ("weekday", "星期倍率")):
            b = self._track(tk.Label(
                tabs, text=tr(text), font=config.font("body", bold=True),
                padx=14, pady=4, cursor="hand2"), text)
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, k=key: self._click_tab(k))
            self._tab_btns[key] = b

        self.stack = tk.Frame(self, bg=bg)
        self.stack.pack(fill="both", expand=True, padx=26, pady=(6, 0))

        # ---- 基本设置 ----
        self.area = ScrollArea(self.stack, height=420, bg=bg)
        body = self.area.inner
        self._build_dev_mode(body)
        for spec in BASIC_SPECS:
            self._build_row(body, spec)

        # ---- 具体设置 ----
        self.area_num = ScrollArea(self.stack, height=420, bg=bg)
        self._build_num_page(self.area_num.inner, DETAIL_SPECS, self.area_num)

        # ---- 星期倍率 ----
        self.area_week = ScrollArea(self.stack, height=420, bg=bg)
        intro = self._track(tk.Label(
            self.area_week.inner, text=tr(
                "当天的联网额度 = 每日联网额度 × 当天的倍率.例如每日额度 2 h,周六倍率 ×1.5,"
                "周六就能联网 3 h;倍率 ×0 表示当天不能联网."),
            bg=bg, fg=COLORS["text_dim"], font=config.font("small"), anchor="w",
            justify="left"),
            "当天的联网额度 = 每日联网额度 × 当天的倍率.例如每日额度 2 h,周六倍率 ×1.5,"
            "周六就能联网 3 h;倍率 ×0 表示当天不能联网.")
        intro.pack(fill="x", pady=(2, 6))
        wrap_label(intro, 12)
        self._build_num_page(self.area_week.inner, WEEKDAY_SPECS, self.area_week)

        # ---- 两页共用的底栏 ----
        foot = tk.Frame(self, bg=bg)
        foot.pack(fill="x", padx=28, pady=(4, 10))
        self.lbl_global = tk.Label(
            foot, text="", bg=bg, fg=COLORS["text_dim"],
            font=config.font("small"), anchor="w", justify="left"
        )
        self.lbl_global.pack(fill="x", pady=(0, 6))
        btns = tk.Frame(foot, bg=bg)
        btns.pack(fill="x")
        self._track(ttk.Button(btns, text=tr("💾 保存本页修改"), style="Accent.TButton",
                               command=self._save_all),
                    "💾 保存本页修改").pack(side="left")
        self.btn_cancel_all = self._track(
            ttk.Button(btns, text=tr("↩ 取消全部待生效修改"), command=self._cancel_all),
            "↩ 取消全部待生效修改")
        self.btn_cancel_all.pack(side="left", padx=(8, 0))
        self._track(tk.Label(
            foot, text=tr("带 ⚡ 标记的项修改后立即生效;其余需等待 48 小时."),
            bg=bg, fg=COLORS["text_dim"], font=config.font("small"), anchor="w"),
            "带 ⚡ 标记的项修改后立即生效;其余需等待 48 小时.").pack(fill="x", pady=(6, 0))

        self.show_tab(self._tab)

    @smooth
    def _click_tab(self, key: str):
        self.show_tab(key)

    def show_tab(self, key: str):
        self._tab = key
        areas = {"basic": self.area, "detail": self.area_num, "weekday": self.area_week}
        for k, a in areas.items():
            if k != key:
                hide_pack(a)
        show_pack(areas.get(key, self.area), fill="both", expand=True)
        for k, b in self._tab_btns.items():
            if k == key:
                cfg(b, bg=COLORS["accent"], fg=COLORS["on_accent"])
            else:
                cfg(b, bg=COLORS["bg_card"], fg=COLORS["text"])

    # ---- 标记: 不需要等待的设置项 ----

    def _badge(self, key: str):
        tag = self.sm.wait_tag(key)
        if tag == "instant":
            return tr("⚡ 即时生效"), COLORS["success"]
        if tag == "first":
            return tr("⚡ 首次修改免等待"), COLORS["success"]
        if tag == "free":
            return tr("⚡ 这一次修改免等待"), COLORS["success"]
        if tag == "dev":
            return tr("⚡ 开发者模式: 即时"), COLORS["warn"]
        return "", COLORS["text_dim"]

    # ---- 具体设置页: 数值直接填写, 一项一行 ----

    def _build_num_page(self, body, specs, area):
        card = COLORS["bg_card"]
        grid = tk.Frame(body, bg=card, highlightbackground=COLORS["border"],
                        highlightthickness=1)
        grid.pack(fill="x", pady=(2, 8))
        grid.grid_columnconfigure(6, weight=1)
        small = config.font("small")
        r = 0
        for i, spec in enumerate(specs):
            key = spec["key"]
            if i:
                tk.Frame(grid, bg=COLORS["border"], height=1).grid(
                    row=r, column=0, columnspan=7, sticky="ew", padx=8)
                r += 1
            py_top = (8, 0)
            name = self._track(tk.Label(
                grid, text=tr(spec["short"]), bg=card, fg=COLORS["text"],
                font=config.font("body", bold=True), anchor="w"), spec["short"])
            name.grid(row=r, column=0, sticky="w", padx=(12, 6), pady=py_top)
            badge = tk.Label(grid, text="", bg=card, font=small, anchor="w")
            badge.grid(row=r, column=1, sticky="w", padx=(0, 8), pady=py_top)

            var = tk.StringVar()
            ent = ttk.Entry(grid, textvariable=var, width=9, justify="right")
            ent.grid(row=r, column=2, sticky="w", pady=py_top)
            ent.bind("<Return>", lambda e, k=key: self._stage_num(k))
            tk.Label(grid, text=spec["unit"], bg=card, fg=COLORS["text_dim"],
                     font=small, width=4, anchor="w").grid(
                row=r, column=3, sticky="w", padx=(4, 4), pady=py_top)
            self._track(ttk.Button(grid, text=tr("提交"), width=6,
                                   command=lambda k=key: self._stage_num(k)), "提交"
                        ).grid(row=r, column=4, sticky="w", pady=py_top)
            lbl_cur = tk.Label(grid, text="", bg=card, fg=COLORS["text_dim"],
                               font=small, anchor="w")
            lbl_cur.grid(row=r, column=5, columnspan=2, sticky="w", padx=(10, 6),
                         pady=py_top)
            r += 1

            # 待生效的改动单独占一行, 只在有改动排队时显示
            pend = tk.Frame(grid, bg=card)
            pend.grid(row=r, column=0, columnspan=7, sticky="w", padx=12, pady=(2, 0))
            lbl_pending = tk.Label(pend, text="", bg=card, fg=COLORS["warn"],
                                   font=small, anchor="w")
            lbl_pending.pack(side="left")
            btn_cancel = self._track(tk.Label(
                pend, text="✕ " + tr("取消"), bg=card, fg=COLORS["danger"],
                font=small, cursor="hand2"), lambda: "✕ " + tr("取消"))
            btn_cancel.pack(side="left", padx=(8, 0))
            btn_cancel.bind("<Button-1>", lambda e, k=key: self._cancel(k))
            pend.grid_remove()
            r += 1

            if spec["desc"]:
                desc = self._track(tk.Label(
                    grid, text=tr(spec["desc"]), bg=card, fg=COLORS["text_dim"],
                    font=small, anchor="w", justify="left"), spec["desc"])
                desc.grid(row=r, column=0, columnspan=7, sticky="ew", padx=12, pady=(1, 7))
                wrap_label(desc, 24)
            else:
                tk.Frame(grid, bg=card, height=6).grid(row=r, column=0, columnspan=7)
            r += 1

            self._num_rows[key] = {
                "spec": spec, "var": var, "entry": ent, "badge": badge, "name": name,
                "lbl_current": lbl_cur, "lbl_pending": lbl_pending,
                "btn_cancel": btn_cancel, "pend": pend, "synced": None,
            }
        area.bind_children()

    def _sync_num(self, key: str, force: bool = False):
        """把填写框同步成当前生效值; 用户改过但还没提交的框不动 (除非 force)."""
        row = self._num_rows[key]
        text = self.sm.ui_number(key)
        if force or row["synced"] is None or row["var"].get().strip() == row["synced"]:
            set_var(row["var"], text)
        row["synced"] = text

    def _num_edited(self, key: str) -> bool:
        row = self._num_rows[key]
        return row["var"].get().strip() != (row["synced"] or "")

    def _stage_num(self, key: str, quiet: bool = False):
        row = self._num_rows[key]
        value = self.sm.from_ui_number(key, row["var"].get())
        status, msg = self.sm.stage(key, value)
        if status == "invalid":
            if not quiet:
                toast.warn(msg)
            return status, msg
        self._sync_num(key, force=True)
        self.refresh()
        if status in ("instant", "staged") and self.on_changed:
            self.on_changed(status, key)
        if not quiet and status in ("instant", "staged", "nochange"):
            toast.info(tr(msg))
        return status, msg

    def _build_dev_mode(self, body):
        if not config.dev_mode_defined():
            return
        card = COLORS["bg_card"]
        fr = tk.Frame(body, bg=card, highlightbackground=COLORS["border"],
                      highlightthickness=1)
        fr.pack(fill="x", pady=(2, 8))
        row = tk.Frame(fr, bg=card)
        row.pack(fill="x", padx=12, pady=(10, 2))
        self._track(tk.Label(
            row, text=tr("🛠  开发者模式"), bg=card, fg=COLORS["text"],
            font=config.font("body", bold=True)), "🛠  开发者模式").pack(side="left")
        self.sw_dev = Switch(row, value=bool(getattr(config, "DEV_MODE", False)),
                             command=self._on_dev_switch, bg=card)
        self.sw_dev.pack(side="right")
        self.lbl_dev_state = tk.Label(
            fr, text="", bg=card, fg=COLORS["text_dim"],
            font=config.font("small"), anchor="w"
        )
        self.lbl_dev_state.pack(fill="x", padx=12, pady=(0, 10))
        self.area.bind_children()

    def _on_dev_switch(self, enabled):
        enabled = bool(enabled)
        if enabled and not toast.ask(
            tr("开发者模式开关:开启后本程序不再以任何方式断网.调试完成后请关掉.确定开启吗?"),
            title=tr("开发者模式确认")
        ):
            self.sw_dev.set(False)
            return
        config.DEV_MODE = enabled
        if self.on_dev_mode:
            self.on_dev_mode(enabled)
        self.refresh()

    def _build_row(self, body, spec):
        key, kind = spec["key"], spec["kind"]
        card = COLORS["bg_card"]

        inner = tk.Frame(body, bg=card, highlightbackground=COLORS["border"],
                         highlightthickness=1)
        inner.pack(fill="x", pady=(0, 6))

        head = tk.Frame(inner, bg=card)
        head.pack(fill="x", padx=12, pady=(10, 0))
        self._track(tk.Label(
            head, text=tr(spec["label"]), bg=card, fg=COLORS["text"],
            font=config.font("body", bold=True)), spec["label"]).pack(side="left")
        badge = tk.Label(head, text="", bg=card, font=config.font("small"))
        badge.pack(side="left", padx=(10, 0))
        lbl_cur = tk.Label(head, text="", bg=card, fg=COLORS["text_dim"],
                           font=config.font("small"))
        lbl_cur.pack(side="right")

        ctrl = tk.Frame(inner, bg=card)
        ctrl.pack(fill="x", padx=12, pady=(6, 4))

        custom_var = None
        if kind in ("choice", "combo", "float"):
            var = tk.StringVar()
            widget = ttk.Combobox(
                ctrl, textvariable=var, state="readonly", width=30,
                values=[lab for _v, lab in self.sm.labeled_values(key, translate=True)]
            )
            widget.pack(side="left")
            if kind == "combo":
                custom_var = tk.StringVar()
                ttk.Entry(ctrl, textvariable=custom_var, width=24).pack(
                    side="left", padx=(8, 0))
        else:
            var = tk.StringVar()
            widget = ttk.Entry(ctrl, textvariable=var, width=30)
            widget.pack(side="left")
            custom_var = tk.StringVar()
            ttk.Entry(ctrl, textvariable=custom_var, width=18).pack(
                side="left", padx=(8, 0))

        btn = self._track(ttk.Button(ctrl, text=tr("提交修改"), style="Accent.TButton",
                                     command=lambda k=key: self._stage(k)), "提交修改")
        btn.pack(side="left", padx=(8, 0))
        if key == "CHIME_WAV":
            self._track(ttk.Button(ctrl, text=tr("选择音频…"),
                                   command=lambda: self._pick_wav(widget, custom_var)),
                        "选择音频…").pack(side="left", padx=(8, 0))
            self._track(ttk.Button(ctrl, text=tr("▶ 试听"),
                                   command=lambda: (self.on_sound and self.on_sound())),
                        "▶ 试听").pack(side="left", padx=(8, 0))

        pending = tk.Frame(inner, bg=card)
        pending.pack(fill="x", padx=12, pady=(0, 8))
        lbl_pending = tk.Label(
            pending, text="", bg=card, fg=COLORS["warn"],
            font=config.font("small"), anchor="w", justify="left"
        )
        lbl_pending.pack(side="left")
        btn_cancel = self._track(
            ttk.Button(pending, text=tr("✕ 取消这项修改"),
                       command=lambda k=key: self._cancel(k)), "✕ 取消这项修改")

        self._rows[key] = {
            "spec": spec, "var": var, "widget": widget, "lbl_current": lbl_cur,
            "lbl_pending": lbl_pending, "btn_cancel": btn_cancel,
            "frame": inner, "custom": custom_var, "badge": badge,
        }

        self._choices_widgets.append((key, widget))

        self.area.bind_children()

    def _widget_value(self, key: str):
        spec = SCHEMA_BY_KEY[key]
        row = self._rows[key]
        raw = row["var"].get().strip()
        custom = (row["custom"].get().strip() if row.get("custom") else "")

        if spec["kind"] in ("choice", "combo", "instant"):

            if custom:
                return self.sm._coerce(key, custom)
            for value, label in self.sm.labeled_values(key, translate=True):
                if label == raw:
                    return value
            if key == "CHIME_WAV" and not raw:
                return "__builtin__"
            return self.sm._coerce(key, raw)
        if spec["kind"] == "float":
            for value, label in self.sm.labeled_values(key, translate=True):
                if label == raw:
                    return value
            return self.sm._coerce(key, raw)
        return self.sm._coerce(key, raw)

    def _sync_widget(self, key: str):
        spec = SCHEMA_BY_KEY[key]
        row = self._rows[key]
        current = self.sm.value(key)

        if spec["kind"] in ("choice", "combo", "instant", "float"):
            label = self.sm.label_for(key, current, translate=True)
            set_var(row["var"], label if label is not None else self.sm.display(key))
        else:
            set_var(row["var"], str(current))


    def _stage(self, key: str):
        if key in ("LANGUAGE", "FONT_SCALE", "THEME"):
            # 这几项会重建整个界面, 由 rebuild_ui 自己显示加载页
            return self._stage_now(key)
        with frozen(self):
            return self._stage_now(key)

    def _stage_now(self, key: str):
        value = self._widget_value(key)
        status, msg = self.sm.stage(key, value)
        if status == "invalid":
            toast.warn(msg)
            return
        self.refresh()
        if status in ("instant", "staged"):
            if self.on_changed:
                self.on_changed(status, key)

            if self._run_ui_hooks([key]):
                return
        if status in ("instant", "staged", "nochange"):
            toast.info(tr(msg))

    def _run_ui_hooks(self, keys) -> bool:
        """语言 / 字号 / 主题改动后需要重建整个界面. 重建会销毁本页,
        所以调用之后不要再碰本页的控件. 返回是否触发了重建."""
        if "LANGUAGE" in keys and self.on_language:
            self.on_language()
            return True
        if "FONT_SCALE" in keys and self.on_font_scale:
            self.on_font_scale()
            return True
        if "THEME" in keys and self.on_theme:
            self.on_theme()
            return True
        return False

    def _cancel(self, key: str):
        if self.sm.cancel(key):
            self.refresh()
            if self.on_changed:
                self.on_changed("cancel", key)

    def _cancel_all(self):
        n = self.sm.staged_count()
        if not n:
            return
        if not toast.ask(
            tr("确定取消全部 {n} 项待生效修改吗?").format(n=n),
            title=tr("取消待生效修改")
        ):
            return
        self.sm.cancel_all()
        self.refresh()
        if self.on_changed:
            self.on_changed("cancel", None)

    def _save_all(self):
        if self._tab in ("detail", "weekday"):
            self._save_all_num(DETAIL_SPECS if self._tab == "detail" else WEEKDAY_SPECS)
            return
        staged, instant, same = 0, 0, 0
        ui_keys = []
        for spec in BASIC_SPECS:
            key = spec["key"]
            try:
                value = self._widget_value(key)
            except Exception:
                continue
            if spec["apply"] == APPLY_INSTANT:
                if value != self.sm.value(key):
                    self.sm.stage(key, value)
                    instant += 1
                    ui_keys.append(key)
                continue
            if value == self.sm.value(key):
                same += 1
                continue
            status, _ = self.sm.stage(key, value)
            if status == "staged":
                staged += 1
            elif status == "instant":
                instant += 1
        self._report_saved(staged, instant)
        self._run_ui_hooks(ui_keys)

    def _save_all_num(self, specs):
        staged, instant, errors = 0, 0, []
        for spec in specs:
            key = spec["key"]
            if not self._num_edited(key):
                continue
            status, msg = self._stage_num(key, quiet=True)
            if status == "invalid":
                errors.append(msg)
            elif status == "staged":
                staged += 1
            elif status == "instant":
                instant += 1
        if errors:
            toast.warn("\n".join(errors))
        self._report_saved(staged, instant, silent_if_none=bool(errors))

    def _report_saved(self, staged: int, instant: int, silent_if_none: bool = False):
        self.refresh()
        if self.on_changed and (staged or instant):
            self.on_changed("staged" if staged else "instant", None)
        if instant and staged:
            toast.success(tr("{n} 项即时生效项已保存\n{m} 项已提交,48 小时后生效").format(
                n=instant, m=staged))
        elif instant:
            toast.success(tr("{n} 项即时生效项已保存").format(n=instant))
        elif staged:
            toast.info(tr("{n} 项已提交,48 小时后生效").format(n=staged))
        elif not silent_if_none:
            toast.info(tr("没有需要保存的修改"))

    def _pick_wav(self, widget, custom_var=None):
        path = filedialog.askopenfilename(
            title=tr("选择提示音"),
            filetypes=[(tr("音频文件"), "*.wav *.mp3"), (tr("WAV 音频"), "*.wav"),
                       (tr("MP3 音频"), "*.mp3"), (tr("所有文件"), "*.*")],
            parent=self.winfo_toplevel()
        )
        if not path:
            return
        if custom_var is not None:
            custom_var.set(path)
        else:
            widget.set(path)


    def refresh(self):
        # 文字翻译不用每次刷新都重设: 换语言时整个界面会重建.
        # 下面只改真正变了的属性 (cfg), 避免每次刷新把几十个控件全部重画一遍.
        if self.sw_dev is not None:
            dev = bool(getattr(config, "DEV_MODE", False))
            if self.sw_dev.get() != dev:
                self.sw_dev.set(dev)
            cfg(self.lbl_dev_state,
                text=tr("已开启 —— 网络不受限制") if dev else tr("已关闭(正常模式)"),
                fg=COLORS["danger"] if dev else COLORS["text_dim"]
            )

        self._syncing = True
        try:
            for spec in BASIC_SPECS:
                key = spec["key"]
                row = self._rows[key]
                self._sync_widget(key)
                cfg(row["lbl_current"],
                    text=f"{tr('当前')}: {tr(self.sm.display(key))}")
                text, color = self._badge(key)
                cfg(row["badge"], text=text, fg=color)

                if self.sm.is_staged(key):
                    cfg(row["lbl_pending"],
                        text=tr("待生效: {value}   ·   {when}").format(
                            value=tr(self.sm.display_value(key, self.sm.staged(key)['value'])),
                            when=self.sm.apply_at_text(key))
                    )
                    show_pack(row["btn_cancel"], side="left", padx=(10, 0))
                else:
                    cfg(row["lbl_pending"], text="")
                    hide_pack(row["btn_cancel"])

            today = datetime.now().weekday()
            for spec in DETAIL_SPECS + WEEKDAY_SPECS:
                key = spec["key"]
                row = self._num_rows[key]
                self._sync_num(key)
                cur = f"{tr('当前')}: {self.sm.display(key)}"
                if key in config.WEEKDAY_KEYS:
                    # 星期倍率: 顺带显示这一天实际能联网多久, 并标出今天
                    quota = float(config.DAILY_LIMIT) * float(self.sm.value(key))
                    cur += f"  →  {config.fmt_hm(quota)}"
                    is_today = config.WEEKDAY_KEYS.index(key) == today
                    cfg(row["name"], text=tr(spec["short"]) + (
                        f"  ({tr('今天')})" if is_today else ""),
                        fg=COLORS["accent"] if is_today else COLORS["text"])
                cfg(row["lbl_current"], text=cur)
                text, color = self._badge(key)
                cfg(row["badge"], text=text, fg=color)
                if self.sm.is_staged(key):
                    cfg(row["lbl_pending"],
                        text=tr("待生效: {value}   ·   {when}").format(
                            value=self.sm.display_value(key, self.sm.staged(key)['value']),
                            when=self.sm.apply_at_text(key)))
                    show_grid(row["pend"])
                else:
                    cfg(row["lbl_pending"], text="")
                    hide_grid(row["pend"])
        finally:
            self._syncing = False

        n = self.sm.staged_count()
        nxt = self.sm.seconds_until_next()
        if n and nxt is not None:
            h, rem = divmod(int(nxt), 3600)
            m = rem // 60
            cfg(self.lbl_global,
                text=tr("待生效修改 {n} 项 · 最近一项 {h} 小时 {m} 分后生效").format(
                    n=n, h=h, m=m),
                fg=COLORS["warn"]
            )
            if self.btn_cancel_all.instate(["disabled"]):
                self.btn_cancel_all.state(["!disabled"])
        else:
            cfg(self.lbl_global, text=tr("当前没有待生效的修改."), fg=COLORS["text_dim"])
            if not self.btn_cancel_all.instate(["disabled"]):
                self.btn_cancel_all.state(["disabled"])
