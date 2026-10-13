import math
import tkinter as tk
from tkinter import ttk

import config
from config import COLORS, fmt_hm
from data_manager import month_prefixes, tally_items
from i18n import tr
from .widgets import ScrollArea, wrap_label


PALETTE = (
    "#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed",
    "#0891b2", "#db2777", "#65a30d", "#ea580c",
)
OTHER_COLOR = "#94a3b8"
EMPTY_COLOR = "#e2e8f0"


class StatsPage(tk.Frame):
    """📊 Statistics:上月 / 本月的整点记录活动与联网理由,饼状图 + 图例.

    第一页(整点记录)只在整点记录开启时出现;每一页可单独切换「占比 / 总时间」."""

    def __init__(self, master, data_manager, net_guard):
        super().__init__(master, bg=COLORS["bg"])
        self.dm = data_manager
        self.net = net_guard
        self.page = "log"
        self.mode = {"log": "pct", "net": "pct"}
        self._build()

    def _build(self):
        bg = COLORS["bg"]

        hdr = tk.Frame(self, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(18, 4))
        tk.Label(
            hdr, text=tr("📊  统计"), bg=bg, fg=COLORS["text"],
            font=config.font("h1", bold=True)
        ).pack(anchor="w")
        self.lbl_note = tk.Label(
            hdr, text="", bg=bg, fg=COLORS["text_dim"],
            font=config.font("body"), justify="left", anchor="w"
        )
        self.lbl_note.pack(anchor="w", fill="x", pady=(4, 0))
        wrap_label(self.lbl_note, 12)

        bar = tk.Frame(self, bg=bg)
        bar.pack(fill="x", padx=26, pady=(8, 8))
        self.tab_btns = {}
        for key, text in (("log", tr("📝  整点记录")), ("net", tr("🌐  联网理由"))):
            b = tk.Button(
                bar, text=text, relief="flat", bd=0, padx=14, pady=6,
                font=config.font("body", bold=True), cursor="hand2",
                command=lambda k=key: self._set_page(k)
            )
            self.tab_btns[key] = b
        self.mode_btns = {}
        for key, text in (("total", tr("总时间")), ("pct", tr("占比"))):
            b = tk.Button(
                bar, text=text, relief="flat", bd=0, padx=12, pady=6,
                font=config.font("small"), cursor="hand2",
                command=lambda k=key: self._set_mode(k)
            )
            b.pack(side="right", padx=(4, 0))
            self.mode_btns[key] = b
        tk.Label(bar, text=tr("显示:"), bg=bg, fg=COLORS["text_dim"],
                 font=config.font("small")).pack(side="right", padx=(0, 2))

        ttk.Separator(self, orient="horizontal", style="UI.TSeparator").pack(fill="x", padx=26)

        body = tk.Frame(self, bg=bg)
        body.pack(fill="both", expand=True, padx=20, pady=(10, 16))
        self.cols = []
        for i in range(2):
            body.columnconfigure(i, weight=1, uniform="col")
            col = tk.Frame(body, bg=COLORS["bg_card"],
                           highlightbackground=COLORS["border"], highlightthickness=1)
            col.grid(row=0, column=i, sticky="nsew", padx=6)
            title = tk.Label(col, text="", bg=COLORS["bg_card"], fg=COLORS["text"],
                             font=config.font("h2", bold=True), anchor="w")
            title.pack(fill="x", padx=14, pady=(10, 0))
            total = tk.Label(col, text="", bg=COLORS["bg_card"], fg=COLORS["accent"],
                             font=config.font("body", bold=True), anchor="w")
            total.pack(fill="x", padx=14)
            size = config.scaled(210)
            canvas = tk.Canvas(col, width=size, height=size, bg=COLORS["bg_card"],
                               highlightthickness=0)
            canvas.pack(pady=(6, 6))
            legend = ScrollArea(col, height=config.scaled(170), bg=COLORS["bg_card"])
            legend.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            self.cols.append({"title": title, "total": total, "canvas": canvas,
                              "size": size, "legend": legend})
        body.rowconfigure(0, weight=1)


    def _set_page(self, key: str):
        self.page = key
        self.refresh()

    def _set_mode(self, key: str):
        self.mode[self.page] = key
        self.refresh()

    def _style_buttons(self):
        for key, b in self.tab_btns.items():
            on = key == self.page
            b.config(bg=COLORS["accent"] if on else COLORS["bg_card"],
                     fg="#ffffff" if on else COLORS["text"],
                     activebackground=COLORS["accent_hover"] if on else COLORS["border"],
                     activeforeground="#ffffff" if on else COLORS["text"])
        cur = self.mode[self.page]
        for key, b in self.mode_btns.items():
            on = key == cur
            b.config(bg=COLORS["text"] if on else COLORS["bg_card"],
                     fg="#ffffff" if on else COLORS["text_dim"],
                     activebackground=COLORS["border"], activeforeground=COLORS["text"])


    def _data(self, prefix: str):
        if self.page == "log":
            return self.dm.hour_activity_seconds(prefix)
        return tally_items(self.net.usage_by_reason(prefix))

    def refresh(self):
        log_on = bool(self.dm.hour_enabled)
        for b in self.tab_btns.values():
            b.pack_forget()
        if log_on:
            self.tab_btns["log"].pack(side="left", padx=(0, 4))
        else:
            if self.page == "log":
                self.page = "net"
        self.tab_btns["net"].pack(side="left", padx=(0, 4))
        self._style_buttons()

        if self.page == "log":
            self.lbl_note.config(text=tr(
                "整点记录里每一项活动的总时间.一小时写了多项(用 / 连接)时,这一小时均分给每一项."))
        else:
            self.lbl_note.config(text=tr(
                "每个联网理由的实际联网时间,不计快速访问的倍数.一次申请写了多个理由(用 / 连接)时均分."))

        this, last = month_prefixes()
        for col, (name, prefix) in zip(self.cols, ((tr("上月"), last), (tr("本月"), this))):
            self._draw_column(col, f"{name} · {prefix}", self._data(prefix))

    def _draw_column(self, col, title: str, data: dict):
        pct_mode = self.mode[self.page] == "pct"
        items = sorted(data.items(), key=lambda kv: (-kv[1], kv[0]))
        total = sum(v for _, v in items)
        col["title"].config(text=title)
        col["total"].config(text=tr("合计 {t} · {n} 项").format(t=fmt_hm(total), n=len(items)))

        slices = [(k, v, PALETTE[i]) for i, (k, v) in enumerate(items[:len(PALETTE)])]
        rest = sum(v for _, v in items[len(PALETTE):])
        if rest > 0:
            slices.append((tr("其他"), rest, OTHER_COLOR))
        self._draw_pie(col["canvas"], col["size"], slices, total, pct_mode)

        inner = col["legend"].inner
        for w in inner.winfo_children():
            w.destroy()
        card = COLORS["bg_card"]
        if not items:
            tk.Label(inner, text=tr("暂无数据"), bg=card, fg=COLORS["text_dim"],
                     font=config.font("small")).pack(anchor="w", padx=6, pady=4)
        for i, (k, v) in enumerate(items):
            row = tk.Frame(inner, bg=card)
            row.pack(fill="x", padx=4, pady=1)
            color = PALETTE[i] if i < len(PALETTE) else OTHER_COLOR
            tk.Frame(row, bg=color, width=config.scaled(12),
                     height=config.scaled(12)).pack(side="left", padx=(2, 8))
            value = f"{v / total * 100:.1f}%" if pct_mode else fmt_hm(v)
            tk.Label(row, text=value, bg=card, fg=COLORS["text"], width=9, anchor="e",
                     font=config.font("small", bold=True)).pack(side="right")
            tk.Label(row, text=k, bg=card, fg=COLORS["text"], anchor="w",
                     font=config.font("small")).pack(side="left", fill="x", expand=True)
        col["legend"].bind_children()
        col["legend"].scroll_to_top()

    @staticmethod
    def _draw_pie(cv: tk.Canvas, size: int, slices, total: float, pct_mode: bool):
        cv.delete("all")
        pad = 6
        x0, y0, x1, y1 = pad, pad, size - pad, size - pad
        cx, cy, r = size / 2.0, size / 2.0, size / 2.0 - pad
        if total <= 0:
            cv.create_oval(x0, y0, x1, y1, fill=EMPTY_COLOR, outline="")
            cv.create_text(cx, cy, text=tr("暂无数据"), fill=COLORS["text_dim"],
                           font=config.font("small"))
            return
        if len(slices) == 1:
            cv.create_oval(x0, y0, x1, y1, fill=slices[0][2], outline="#ffffff")
        start = 90.0
        labels = []
        for name, v, color in slices:
            extent = -360.0 * v / total
            if len(slices) > 1:
                cv.create_arc(x0, y0, x1, y1, start=start, extent=extent,
                              fill=color, outline="#ffffff", width=2, style="pieslice")
            if v / total >= 0.06:
                mid = math.radians(start + extent / 2.0)
                rr = 0.62 * r if len(slices) > 1 else 0.0
                text = f"{v / total * 100:.0f}%" if pct_mode else fmt_hm(v)
                labels.append((cx + rr * math.cos(mid), cy - rr * math.sin(mid), text))
            start += extent
        for x, y, text in labels:
            cv.create_text(x, y, text=text, fill="#ffffff",
                           font=config.font("tiny", bold=True))

    def show(self):
        self.refresh()
