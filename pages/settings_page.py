

import tkinter as tk
from tkinter import filedialog, ttk

import config
import toast
from config import COLORS
from i18n import tr
from settings_manager import APPLY_INSTANT, SCHEMA_BY_KEY, SETTINGS_SCHEMA
from .widgets import ScrollArea, Switch


class SettingsPage(tk.Frame):
    def __init__(self, master, settings, on_changed=None, on_sound=None,
                 on_dev_mode=None, on_language=None, on_font_scale=None):
        super().__init__(master, bg=COLORS["bg"])
        self.sm = settings
        self.on_changed = on_changed
        self.on_sound = on_sound
        self.on_dev_mode = on_dev_mode
        self.on_language = on_language
        self.on_font_scale = on_font_scale
        self._rows = {}
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
        ), "⚙  设置").pack(anchor="w")

        self.area = ScrollArea(self, height=420, bg=bg)
        self.area.pack(fill="both", expand=True, padx=26, pady=(6, 4))
        body = self.area.inner

        self._build_dev_mode(body)

        for spec in SETTINGS_SCHEMA:
            self._build_row(body, spec)

        self.lbl_global = tk.Label(
            body, text="", bg=bg, fg=COLORS["text_dim"],
            font=config.font("small"), anchor="w", justify="left"
        )
        self.lbl_global.pack(fill="x", pady=(6, 6))


        btns = tk.Frame(body, bg=bg)
        btns.pack(fill="x", pady=(10, 8))
        self._track(ttk.Button(btns, text=tr("💾 保存全部修改"), style="Accent.TButton",
                               command=self._save_all),
                    "💾 保存全部修改").pack(side="left")
        self.btn_cancel_all = self._track(
            ttk.Button(btns, text=tr("↩ 取消全部待生效修改"), command=self._cancel_all),
            "↩ 取消全部待生效修改")
        self.btn_cancel_all.pack(side="left", padx=(8, 0))

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
            self._track(ttk.Button(ctrl, text=tr("选择 .wav…"),
                                   command=lambda: self._pick_wav(widget, custom_var)),
                        "选择 .wav…").pack(side="left", padx=(8, 0))
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
            "frame": inner, "custom": custom_var,
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
            row["var"].set(label if label is not None else self.sm.display(key))
        else:
            row["var"].set(str(current))


    def _stage(self, key: str):
        value = self._widget_value(key)
        status, msg = self.sm.stage(key, value)
        self.refresh()
        if status in ("instant", "staged"):
            if self.on_changed:
                self.on_changed(status, key)

            if key == "LANGUAGE" and self.on_language:
                self.on_language()
                return
            if key == "FONT_SCALE" and self.on_font_scale:
                self.on_font_scale()
                return
        if status in ("instant", "staged", "nochange"):
            toast.info(tr(msg))

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
        staged, instant, same = 0, 0, 0
        for spec in SETTINGS_SCHEMA:
            key = spec["key"]
            try:
                value = self._widget_value(key)
            except Exception:
                continue
            if spec["apply"] == APPLY_INSTANT:
                if value != self.sm.value(key):
                    self.sm.stage(key, value)
                    instant += 1
                continue
            if value == self.sm.value(key):
                same += 1
                continue
            status, _ = self.sm.stage(key, value)
            if status == "staged":
                staged += 1
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
        else:
            toast.info(tr("没有需要保存的修改"))

    def _pick_wav(self, widget, custom_var=None):
        path = filedialog.askopenfilename(
            title=tr("选择提示音"),
            filetypes=[(tr("WAV 音频"), "*.wav"), (tr("所有文件"), "*.*")],
            parent=self.winfo_toplevel()
        )
        if not path:
            return
        if custom_var is not None:
            custom_var.set(path)
        else:
            widget.set(path)


    def refresh(self):
        self._retranslate()

        if self.sw_dev is not None:
            dev = bool(getattr(config, "DEV_MODE", False))
            if self.sw_dev.get() != dev:
                self.sw_dev.set(dev)
            self.lbl_dev_state.config(
                text=tr("已开启 —— 网络不受限制") if dev else tr("已关闭(正常模式)"),
                fg=COLORS["danger"] if dev else COLORS["text_dim"]
            )

        self._syncing = True
        try:
            for spec in SETTINGS_SCHEMA:
                key = spec["key"]
                row = self._rows[key]
                self._sync_widget(key)
                row["lbl_current"].config(
                    text=f"{tr('当前')}: {tr(self.sm.display(key))}")

                if self.sm.is_staged(key):
                    row["lbl_pending"].config(
                        text=tr("待生效: {value}   ·   {when}").format(
                            value=tr(self.sm.display_value(key, self.sm.staged(key)['value'])),
                            when=self.sm.apply_at_text(key))
                    )
                    row["btn_cancel"].pack(side="left", padx=(10, 0))
                else:
                    row["lbl_pending"].config(text="")
                    row["btn_cancel"].pack_forget()
        finally:
            self._syncing = False

        n = self.sm.staged_count()
        nxt = self.sm.seconds_until_next()
        if n and nxt is not None:
            h, rem = divmod(int(nxt), 3600)
            m = rem // 60
            self.lbl_global.config(
                text=tr("待生效修改 {n} 项 · 最近一项 {h} 小时 {m} 分后生效").format(
                    n=n, h=h, m=m),
                fg=COLORS["warn"]
            )
            self.btn_cancel_all.state(["!disabled"])
        else:
            self.lbl_global.config(text=tr("当前没有待生效的修改."), fg=COLORS["text_dim"])
            self.btn_cancel_all.state(["disabled"])
