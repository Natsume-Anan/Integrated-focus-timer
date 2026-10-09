# -*- coding: utf-8 -*-
"""整点记录页：只记录今天"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta

from config import COLORS, FILL_WINDOW, AUTO_TEXT, LOG_HOURS


class HourLogPage(tk.Frame):
    """只记录今天:每行以该小时的结束时间命名(1:00 表示 0:00–1:00),不含 23:00–24:00"""

    def __init__(self, master, data_manager, on_text_changed=None):
        super().__init__(master, bg=COLORS["bg"])
        self.dm = data_manager
        self.on_text_changed = on_text_changed  # 回调，用于更新 badge
        self.view_date = data_manager.today_date
        self.rows = {}          # hour -> (label, entry, var)
        self._build()

    def _build(self):
        bg, card = COLORS["bg"], COLORS["bg_card"]

        hdr = tk.Frame(self, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(22, 4))
        tk.Label(
            hdr, text="📝  Hour Log", bg=bg, fg=COLORS["text"],
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w")
        tk.Label(
            hdr,
            text=(f"Today only. After each chime, note what you did in the last hour.  "
                  f"Left blank for {int(FILL_WINDOW.total_seconds() // 3600)} h → \"{AUTO_TEXT}\"."),
            bg=bg, fg=COLORS["text_dim"], font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(4, 0))

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

    def refresh(self):
        now = datetime.now()
        self.view_date = self.dm.today_date
        d0 = datetime.strptime(self.view_date, '%Y-%m-%d')
        self.lbl_date.config(text=f"{self.view_date}  (today)")

        awaiting = self.dm.awaiting_slot()
        focused = self.focus_get()
        for h, (lbl, ent, var) in self.rows.items():
            start = d0 + timedelta(hours=h)
            end = start + timedelta(hours=1)
            ended = end <= now
            text = self.dm.get_hour_text(self.view_date, h)
            if focused is not ent and var.get() != text:
                var.set(text)
            ent.config(state="normal" if ended else "disabled")

            is_wait = awaiting is not None and awaiting == start
            is_now = start <= now < end
            label = f"{h + 1}:00"                 # 只显示结束时间
            if is_now:
                label += "   ◂ now"
            elif is_wait:
                label += "   ◂ fill me"
            lbl.config(
                text=label,
                fg=COLORS["accent"] if (is_wait or is_now) else
                   (COLORS["text"] if ended else COLORS["text_dim"])
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
