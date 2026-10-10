# -*- coding: utf-8 -*-
"""整点记录页：只记录今天"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta

from config import COLORS, FILL_WINDOW, AUTO_TEXT, LOG_HOURS


class Switch(tk.Canvas):
    """纯 Canvas 滑动开关(配合白色主题,不依赖 ttk 主题外观)"""

    W, H = 46, 24

    def __init__(self, master, value: bool = True, command=None, bg: str = None):
        super().__init__(
            master, width=self.W, height=self.H, bg=bg or COLORS["bg"],
            highlightthickness=0, bd=0, cursor="hand2"
        )
        self._cmd = command
        self._on = bool(value)
        r = self.H / 2.0
        self._track = [
            self.create_oval(1, 1, self.H - 1, self.H - 1, outline=""),
            self.create_oval(self.W - self.H + 1, 1, self.W - 1, self.H - 1, outline=""),
            self.create_rectangle(r, 1, self.W - r, self.H - 1, outline=""),
        ]
        self._knob = self.create_oval(0, 0, 0, 0, fill="#ffffff", outline="")
        self.bind("<Button-1>", self._on_click)
        self._draw()

    def _on_click(self, _event=None):
        self.set(not self._on, notify=True)

    def get(self) -> bool:
        return self._on

    def set(self, value: bool, notify: bool = False):
        value = bool(value)
        changed = value != self._on
        self._on = value
        self._draw()
        if notify and changed and self._cmd:
            self._cmd(self._on)

    def _draw(self):
        for item in self._track:
            self.itemconfig(item, fill=COLORS["accent"] if self._on else "#cbd5e1")
        pad = 3
        d = self.H - 2 * pad
        x = (self.W - self.H + pad) if self._on else pad
        self.coords(self._knob, x, pad, x + d, pad + d)


class HourLogPage(tk.Frame):
    """只记录今天:每行以该小时的结束时间命名(1:00 表示 0:00–1:00),不含 23:00–24:00"""

    def __init__(self, master, data_manager, on_text_changed=None, on_toggle=None):
        super().__init__(master, bg=COLORS["bg"])
        self.dm = data_manager
        self.on_text_changed = on_text_changed  # 回调，用于更新 badge
        self.on_toggle = on_toggle              # 回调，开关变化时通知主程序
        self.view_date = data_manager.today_date
        self.rows = {}          # hour -> (label, entry, var)
        self._build()

    def _build(self):
        bg, card = COLORS["bg"], COLORS["bg_card"]

        hdr = tk.Frame(self, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(22, 4))

        left = tk.Frame(hdr, bg=bg)
        left.pack(side="left", anchor="nw")
        tk.Label(
            left, text="📝  Hour Log", bg=bg, fg=COLORS["text"],
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w")
        self.lbl_hint = tk.Label(
            left, text="", bg=bg, fg=COLORS["text_dim"], font=("Segoe UI", 10),
            justify="left"
        )
        self.lbl_hint.pack(anchor="w", pady=(4, 0))

        right = tk.Frame(hdr, bg=bg)
        right.pack(side="right", anchor="ne", pady=(4, 0))
        self.lbl_switch = tk.Label(
            right, text="", bg=bg, font=("Segoe UI", 10, "bold"), width=0
        )
        self.lbl_switch.pack(side="right", padx=(8, 0))
        self.switch = Switch(right, value=self.dm.hour_enabled, command=self._on_switch)
        self.switch.pack(side="right")

        self.lbl_date = tk.Label(
            self, text="", bg=bg, fg=COLORS["accent"],
            font=("Segoe UI", 10, "bold"), anchor="w"
        )
        self.lbl_date.pack(fill="x", padx=28, pady=(8, 6))

        body = tk.Frame(self, bg=bg, highlightbackground=COLORS["border"], highlightthickness=1)
        body.pack(fill="both", expand=True, padx=26, pady=(0, 18))
        self.canvas = tk.Canvas(body, bg=bg, highlightthickness=0, height=270, yscrollincrement=30)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.win, width=e.width)
        )
        # 只在本页面可见时响应滚轮（由主程序控制绑定）
        self.canvas.bind("<MouseWheel>", self._on_wheel)

        for h in range(LOG_HOURS):
            row = tk.Frame(self.inner, bg=bg)
            row.pack(fill="x", padx=10, pady=2)
            lbl = tk.Label(
                row, text="", width=16, anchor="w", bg=bg, fg=COLORS["text_dim"],
                font=("Segoe UI", 10, "bold")
            )
            lbl.pack(side="left")
            var = tk.StringVar()
            ent = tk.Entry(
                row, textvariable=var, font=("Segoe UI", 10), relief="flat",
                bg=card, fg=COLORS["text"], insertbackground=COLORS["text"],
                disabledbackground=bg, disabledforeground=COLORS["text_dim"],
                highlightthickness=1, highlightbackground=COLORS["border"],
                highlightcolor=COLORS["accent"]
            )
            ent.pack(side="left", fill="x", expand=True, ipady=4)
            ent.bind("<Return>", lambda e, h=h: self._on_return(h))
            ent.bind("<FocusOut>", lambda e, h=h: self._commit(h))
            self.rows[h] = (lbl, ent, var)

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _scroll_to(self, hour: int):
        self.update_idletasks()
        hour = min(max(hour, 0), LOG_HOURS - 1)
        self.canvas.yview_moveto(max(0, hour - 2) / float(LOG_HOURS))

    def _on_return(self, h: int):
        self._commit(h)
        self.canvas.focus_set()

    def _commit(self, h: int):
        _, ent, var = self.rows[h]
        if str(ent.cget("state")) == "disabled":
            return
        text = var.get().strip()
        if text != self.dm.get_hour_text(self.view_date, h):
            self.dm.set_hour_text(self.view_date, h, text)
            if self.on_text_changed:
                self.on_text_changed()
            self.refresh()

    def _on_switch(self, enabled: bool):
        """开关被点击:写入配置并通知主程序"""
        self.dm.set_hour_enabled(enabled)
        if self.on_toggle:
            self.on_toggle(self.dm.hour_enabled)
        self.refresh()

    def _refresh_switch(self):
        on = self.dm.hour_enabled
        if self.switch.get() != on:
            self.switch.set(on)
        self.lbl_switch.config(
            text="ON" if on else "OFF",
            fg=COLORS["success"] if on else COLORS["text_dim"]
        )
        if on:
            self.lbl_hint.config(
                text=(f"Today only. After each chime, note what you did in the last hour.  "
                      f"Left blank for {int(FILL_WINDOW.total_seconds() // 3600)} h → \"{AUTO_TEXT}\".")
            )
        else:
            self.lbl_hint.config(
                text=("Hour log is OFF — no chime, no auto fill, nothing is recorded. "
                      "Turn it back on to start logging again from the current hour.")
            )

    def refresh(self):
        now = datetime.now()
        self.view_date = self.dm.today_date
        d0 = datetime.strptime(self.view_date, '%Y-%m-%d')
        self._refresh_switch()
        self.lbl_date.config(
            text=f"{self.view_date}  (today)"
                 + ("" if self.dm.hour_enabled else "   ·  logging disabled")
        )

        enabled = self.dm.hour_enabled

        awaiting = self.dm.awaiting_slot()
        focused = self.focus_get()
        for h, (lbl, ent, var) in self.rows.items():
            start = d0 + timedelta(hours=h)
            end = start + timedelta(hours=1)
            ended = end <= now
            text = self.dm.get_hour_text(self.view_date, h)
            if focused is not ent and var.get() != text:
                var.set(text)
            ent.config(state="normal" if (enabled and ended) else "disabled")

            is_wait = awaiting is not None and awaiting == start
            is_now = enabled and start <= now < end
            label = f"{h + 1}:00"                 # 只显示结束时间
            if is_now:
                label += "   ◂ now"
            elif is_wait:
                label += "   ◂ fill me"
            lbl.config(
                text=label,
                fg=COLORS["accent"] if (is_wait or is_now) else
                   (COLORS["text"] if (enabled and ended) else COLORS["text_dim"])
            )
            ent.config(
                highlightbackground=COLORS["accent"] if is_wait else COLORS["border"]
            )

    def show(self):
        """切到本页:如果有待填写的小时,直接滚动到那一行并聚焦"""
        aw = self.dm.awaiting_slot()
        self.refresh()
        self._scroll_to(aw.hour if aw else datetime.now().hour)
        if aw and aw.hour < LOG_HOURS:
            self.rows[aw.hour][1].focus_set()
