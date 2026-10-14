import math
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

import config
from config import COLORS, fmt_hm
from data_manager import month_prefixes, tally_items
from i18n import tr, is_en
from .widgets import ScrollArea, wrap_label


PALETTE = (
    "#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed",
    "#0891b2", "#db2777", "#65a30d", "#ea580c",
)
OTHER_COLOR = "#94a3b8"
EMPTY_COLOR = "#e2e8f0"

FOCUS_STUDY = "#2563eb"    # 专注: 蓝
FOCUS_BREAK = "#16a34a"    # 休息: 绿
FOCUS_BLANK = "#e2e8f0"    # 空白: 灰
FOCUS_FUTURE = "#f1f5f9"   # 今天还没到的小时
WEEKDAYS_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEEKDAYS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class StatsPage(tk.Frame):
    """📊 Statistics:上月 / 本月的整点记录活动与联网理由,饼状图 + 图例.

    第一页(整点记录)只在整点记录开启时出现;每一页可单独切换「占比 / 总时间」."""

    def __init__(self, master, data_manager, net_guard, focus_live=None):
        super().__init__(master, bg=COLORS["bg"])
        self.dm = data_manager
        self.net = net_guard
        self.focus_live = focus_live
        self.page = "log"
        self.mode = {"log": "pct", "net": "pct"}
        self._focus_days = []
        self._focus_geom = None
        self._build()
        self.after(60000, self._focus_tick)

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
        for key, text in (("log", tr("📝  整点记录")), ("net", tr("🌐  联网理由")),
                          ("focus", tr("⏱  专注计时"))):
            b = tk.Button(
                bar, text=text, relief="flat", bd=0, padx=14, pady=6,
                font=config.font("body", bold=True), cursor="hand2",
                command=lambda k=key: self._set_page(k)
            )
            self.tab_btns[key] = b
        self.mode_bar = tk.Frame(bar, bg=bg)
        self.mode_bar.pack(side="right")
        self.mode_btns = {}
        for key, text in (("total", tr("总时间")), ("pct", tr("占比"))):
            b = tk.Button(
                self.mode_bar, text=text, relief="flat", bd=0, padx=12, pady=6,
                font=config.font("small"), cursor="hand2",
                command=lambda k=key: self._set_mode(k)
            )
            b.pack(side="right", padx=(4, 0))
            self.mode_btns[key] = b
        tk.Label(self.mode_bar, text=tr("显示:"), bg=bg, fg=COLORS["text_dim"],
                 font=config.font("small")).pack(side="right", padx=(0, 2))

        # 专注计时页的图例
        self.focus_legend = tk.Frame(bar, bg=bg)
        for color, text in ((FOCUS_STUDY, tr("专注")), (FOCUS_BREAK, tr("休息")),
                            (FOCUS_BLANK, tr("空白"))):
            tk.Frame(self.focus_legend, bg=color, width=config.scaled(12),
                     height=config.scaled(12)).pack(side="left", padx=(10, 4))
            tk.Label(self.focus_legend, text=text, bg=bg, fg=COLORS["text_dim"],
                     font=config.font("small")).pack(side="left")

        ttk.Separator(self, orient="horizontal", style="UI.TSeparator").pack(fill="x", padx=26)

        body = tk.Frame(self, bg=bg)
        self.pie_body = body
        body.pack(fill="both", expand=True, padx=20, pady=(10, 16))

        # 专注计时页: 最近 7 天, 每天 24 根条, 每根按比例分成专注 / 休息 / 空白
        self.focus_body = tk.Frame(self, bg=COLORS["bg_card"],
                                   highlightbackground=COLORS["border"], highlightthickness=1)
        self.focus_cv = tk.Canvas(self.focus_body, bg=COLORS["bg_card"], highlightthickness=0)
        self.focus_cv.pack(fill="both", expand=True, padx=6, pady=6)
        self.focus_cv.bind("<Configure>", lambda e: self._draw_focus())
        self.focus_cv.bind("<Motion>", self._focus_hover)
        self.focus_cv.bind("<Leave>", lambda e: self.focus_cv.delete("tip"))

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
        cur = self.mode.get(self.page, "pct")
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
        self.tab_btns["focus"].pack(side="left", padx=(0, 4))
        self._style_buttons()

        if self.page == "focus":
            self.mode_bar.pack_forget()
            self.focus_legend.pack(side="right")
            self.pie_body.pack_forget()
            self.focus_body.pack(fill="both", expand=True, padx=26, pady=(10, 16))
            self.lbl_note.config(text=tr(
                "最近 7 天计时器的专注与休息.每根条是一个小时,按比例分成专注、休息与空白;鼠标停在条上可查看分钟数."))
            self._load_focus()
            self._draw_focus()
            return
        self.focus_legend.pack_forget()
        self.focus_body.pack_forget()
        self.mode_bar.pack(side="right")
        self.pie_body.pack(fill="both", expand=True, padx=20, pady=(10, 16))

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

    # ---- 专注计时 ----

    def _load_focus(self):
        live = self.focus_live() if self.focus_live else None
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self._focus_days = [
            (today - timedelta(days=i), self.dm.focus_hours(today - timedelta(days=i), live))
            for i in range(self.dm.FOCUS_DAYS)
        ]

    def _focus_tick(self):
        try:
            if self.page == "focus":
                self._load_focus()
                self._draw_focus()
        finally:
            self.after(60000, self._focus_tick)

    @staticmethod
    def _day_label(day: datetime, today: bool) -> str:
        wd = (WEEKDAYS_EN if is_en() else WEEKDAYS_ZH)[day.weekday()]
        return tr("今天") + f" {wd}" if today else f"{day:%m-%d} {wd}"

    def _draw_focus(self):
        cv = self.focus_cv
        cv.delete("all")
        self._focus_geom = None
        if not self._focus_days:
            return
        w = cv.winfo_width()
        if w < 50:
            return
        card = COLORS["bg_card"]
        left = config.scaled(118)
        right = config.scaled(128)
        top = config.scaled(24)
        gap = config.scaled(16)
        n = len(self._focus_days)
        # 行高随窗口高度伸缩
        avail = cv.winfo_height() - top - config.scaled(8) - gap * (n - 1)
        row_h = max(config.scaled(28), min(config.scaled(64), avail / n))
        x0, x1 = left, max(left + 240, w - right)
        slot = (x1 - x0) / 24.0
        bar_w = max(2.0, slot * 0.78)
        now = datetime.now()
        small = config.font("tiny")

        for h in range(0, 24, 3):
            cv.create_text(x0 + h * slot, top - config.scaled(8), text=f"{h:02d}",
                           anchor="w", fill=COLORS["text_dim"], font=small)
        cv.create_text(x1, top - config.scaled(8), text="24", anchor="e",
                       fill=COLORS["text_dim"], font=small)

        for i, (day, hours) in enumerate(self._focus_days):
            y0 = top + i * (row_h + gap)
            y1 = y0 + row_h
            cv.create_text(config.scaled(12), (y0 + y1) / 2, anchor="w",
                           text=self._day_label(day, i == 0),
                           fill=COLORS["text"] if i == 0 else COLORS["text_dim"],
                           font=config.font("small", bold=(i == 0)))
            for h, (st, br) in enumerate(hours):
                bx0 = x0 + h * slot + (slot - bar_w) / 2
                bx1 = bx0 + bar_w
                future = day + timedelta(hours=h) > now
                cv.create_rectangle(bx0, y0, bx1, y1, outline="",
                                    fill=FOCUS_FUTURE if future else FOCUS_BLANK)
                hs = row_h * st / 3600.0
                hb = row_h * br / 3600.0
                if hs > 0:
                    cv.create_rectangle(bx0, y1 - hs, bx1, y1, outline="", fill=FOCUS_STUDY)
                if hb > 0:
                    cv.create_rectangle(bx0, y1 - hs - hb, bx1, y1 - hs, outline="",
                                        fill=FOCUS_BREAK)
            tot_s = sum(st for st, _ in hours)
            tot_b = sum(br for _, br in hours)
            tx = x1 + config.scaled(12)
            cv.create_text(tx, y0 + row_h * 0.3, anchor="w", fill=FOCUS_STUDY,
                           font=config.font("small", bold=True),
                           text=f"{tr('专注')} {fmt_hm(tot_s)}")
            cv.create_text(tx, y0 + row_h * 0.75, anchor="w", fill=FOCUS_BREAK,
                           font=config.font("small"),
                           text=f"{tr('休息')} {fmt_hm(tot_b)}")
        self._focus_geom = (x0, slot, top, row_h, gap)

    @staticmethod
    def _fmt_min(sec: float) -> str:
        if 0 < sec < 30:
            return "<1"
        return str(int(round(sec / 60.0)))

    def _focus_hover(self, event):
        cv = self.focus_cv
        cv.delete("tip")
        g = self._focus_geom
        if not g:
            return
        x0, slot, top, row_h, gap = g
        h = int((event.x - x0) // slot)
        i = int((event.y - top) // (row_h + gap))
        if not (0 <= h < 24 and 0 <= i < len(self._focus_days)):
            return
        if event.y - top - i * (row_h + gap) > row_h:
            return
        day, hours = self._focus_days[i]
        st, br = hours[h]
        blank = max(0.0, 3600.0 - st - br)
        start = day + timedelta(hours=h)
        if start > datetime.now():
            body = tr("尚未到来")
        else:
            body = tr("专注 {s} 分 · 休息 {b} 分 · 空白 {e} 分").format(
                s=self._fmt_min(st), b=self._fmt_min(br), e=self._fmt_min(blank))
        text = f"{day:%m-%d}  {h:02d}:00–{(h + 1) % 24:02d}:00\n{body}"

        pad = config.scaled(6)
        tid = cv.create_text(0, 0, text=text, anchor="nw", fill="#ffffff",
                             font=config.font("small"), tags="tip", justify="left")
        bx = cv.bbox(tid)
        tw, th = bx[2] - bx[0], bx[3] - bx[1]
        x = event.x + config.scaled(14)
        y = event.y + config.scaled(14)
        if x + tw + pad * 2 > cv.winfo_width():
            x = event.x - tw - pad * 2 - config.scaled(8)
        if y + th + pad * 2 > cv.winfo_height():
            y = event.y - th - pad * 2 - config.scaled(8)
        cv.coords(tid, x + pad, y + pad)
        rect = cv.create_rectangle(x, y, x + tw + pad * 2, y + th + pad * 2,
                                   fill=COLORS["text"], outline="", tags="tip")
        cv.tag_raise(tid, rect)

    def show(self):
        self.refresh()
