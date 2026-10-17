import math
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

import config
import window_guard
from config import COLORS, fmt_hm
from data_manager import month_prefixes, tally_items
from i18n import tr, is_en
from .widgets import ScrollArea, smooth, cfg, show_pack, hide_pack


# 图表颜色都跟随当前主题 (config.CHART_PALETTE / COLORS 会在切换主题时原地更新)
PALETTE = config.CHART_PALETTE


def _c(key: str) -> str:
    return COLORS[key]


WEEKDAYS_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEEKDAYS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class StatsPage(tk.Frame):
    """📊 Statistics:上月 / 本月的整点记录活动, 联网理由与各程序的前台时间, 饼状图 + 图例.

    第一页(整点记录)只在整点记录开启时出现;每一页可单独切换「占比 / 总时间」."""

    def __init__(self, master, data_manager, net_guard, focus_live=None):
        super().__init__(master, bg=COLORS["bg"])
        self.dm = data_manager
        self.net = net_guard
        self.focus_live = focus_live
        self.page = "log"
        self.mode = {"log": "pct", "net": "pct", "window": "pct"}
        self._tabs_log_on = None
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

        bar = tk.Frame(self, bg=bg)
        bar.pack(fill="x", padx=26, pady=(8, 8))
        self.tab_btns = {}
        for key, text in (("log", tr("📝  整点记录")), ("net", tr("🌐  联网理由")),
                          ("focus", tr("⏱  专注计时")), ("window", tr("🪟  窗口"))):
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
        for color, text in ((_c("focus_study"), tr("专注")), (_c("focus_break"), tr("休息")),
                            (_c("chart_empty"), tr("空白"))):
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
                              "size": size, "legend": legend,
                              "rows": [], "empty": None, "sig": None, "keys": None})
        body.rowconfigure(0, weight=1)


    @smooth
    def _set_page(self, key: str):
        self.page = key
        self.refresh()

    @smooth
    def _set_mode(self, key: str):
        self.mode[self.page] = key
        self.refresh()

    def _style_buttons(self):
        for key, b in self.tab_btns.items():
            on = key == self.page
            cfg(b, bg=COLORS["accent"] if on else COLORS["bg_card"],
                     fg=COLORS["on_accent"] if on else COLORS["text"],
                     activebackground=COLORS["accent_hover"] if on else COLORS["border"],
                     activeforeground=COLORS["on_accent"] if on else COLORS["text"])
        cur = self.mode.get(self.page, "pct")
        for key, b in self.mode_btns.items():
            on = key == cur
            cfg(b, bg=COLORS["text"] if on else COLORS["bg_card"],
                     fg=COLORS["bg"] if on else COLORS["text_dim"],
                     activebackground=COLORS["border"], activeforeground=COLORS["text"])


    def _data(self, prefix: str):
        if self.page == "log":
            return self.dm.hour_activity_seconds(prefix)
        if self.page == "window":
            names = {window_guard.BLANK: tr("空白"), window_guard.UNKNOWN: tr("未知程序")}
            return {names.get(k, k): v for k, v in self.dm.window_seconds(prefix).items()}
        return tally_items(self.net.usage_by_reason(prefix))

    def _color(self, i: int, name: str) -> str:
        """第 i 项的颜色. 窗口页的「空白」和专注计时页一样用空白色, 不占调色板."""
        if self.page == "window" and name == tr("空白"):
            return _c("chart_empty")
        return PALETTE[i] if i < len(PALETTE) else _c("chart_other")

    def refresh(self):
        log_on = bool(self.dm.hour_enabled)
        if not log_on and self.page == "log":
            self.page = "net"
        # 标签按钮只在 "整点记录" 开关变化时才重新排列 (重复 pack 会触发整页重新布局)
        if self._tabs_log_on != log_on:
            self._tabs_log_on = log_on
            for b in self.tab_btns.values():
                b.pack_forget()
            if log_on:
                self.tab_btns["log"].pack(side="left", padx=(0, 4))
            self.tab_btns["net"].pack(side="left", padx=(0, 4))
            self.tab_btns["focus"].pack(side="left", padx=(0, 4))
            self.tab_btns["window"].pack(side="left", padx=(0, 4))
        self._style_buttons()

        if self.page == "focus":
            hide_pack(self.mode_bar)
            show_pack(self.focus_legend, side="right")
            hide_pack(self.pie_body)
            show_pack(self.focus_body, fill="both", expand=True, padx=26, pady=(10, 16))
            self._load_focus()
            self._draw_focus()
            return
        hide_pack(self.focus_legend)
        hide_pack(self.focus_body)
        show_pack(self.mode_bar, side="right")
        show_pack(self.pie_body, fill="both", expand=True, padx=20, pady=(10, 16))

        this, last = month_prefixes()
        for col, (name, prefix) in zip(self.cols, ((tr("上月"), last), (tr("本月"), this))):
            self._draw_column(col, f"{name} · {prefix}", self._data(prefix))

    def _draw_column(self, col, title: str, data: dict):
        pct_mode = self.mode[self.page] == "pct"
        items = sorted(data.items(), key=lambda kv: (-kv[1], kv[0]))
        # 数据和显示方式都没变 → 什么都不用画 (切回这页时几乎零开销)
        sig = (title, pct_mode, tuple(items))
        if col["sig"] == sig:
            return
        col["sig"] = sig

        total = sum(v for _, v in items)
        cfg(col["title"], text=title)
        cfg(col["total"], text=tr("合计 {t} · {n} 项").format(t=fmt_hm(total), n=len(items)))

        slices = [(k, v, self._color(i, k)) for i, (k, v) in enumerate(items[:len(PALETTE)])]
        rest = sum(v for _, v in items[len(PALETTE):])
        if rest > 0:
            slices.append((tr("其他"), rest, _c("chart_other")))
        self._draw_pie(col["canvas"], col["size"], slices, total, pct_mode)
        self._fill_legend(col, items, total, pct_mode)

    def _fill_legend(self, col, items, total, pct_mode):
        """图例的每一行控件循环使用: 只在行数不够时新建, 多出来的收起来."""
        inner = col["legend"].inner
        card = COLORS["bg_card"]
        if col["empty"] is None:
            col["empty"] = tk.Label(inner, text=tr("暂无数据"), bg=card,
                                    fg=COLORS["text_dim"], font=config.font("small"))
        if items:
            hide_pack(col["empty"])
        else:
            show_pack(col["empty"], anchor="w", padx=6, pady=4)

        rows = col["rows"]
        created = False
        while len(rows) < len(items):
            row = tk.Frame(inner, bg=card)
            sw = tk.Frame(row, bg=card, width=config.scaled(12), height=config.scaled(12))
            sw.pack(side="left", padx=(2, 8))
            val = tk.Label(row, text="", bg=card, fg=COLORS["text"], width=9, anchor="e",
                           font=config.font("small", bold=True))
            val.pack(side="right")
            name = tk.Label(row, text="", bg=card, fg=COLORS["text"], anchor="w",
                            font=config.font("small"))
            name.pack(side="left", fill="x", expand=True)
            rows.append((row, sw, val, name))
            created = True

        for i, (row, sw, val, name) in enumerate(rows):
            if i >= len(items):
                hide_pack(row)
                continue
            k, v = items[i]
            cfg(sw, bg=self._color(i, k))
            cfg(val, text=f"{v / total * 100:.1f}%" if pct_mode else fmt_hm(v))
            cfg(name, text=k)
            show_pack(row, fill="x", padx=4, pady=1)
        if created:
            col["legend"].bind_children()
        # 只有项目或顺序变了才滚回顶部; 窗口页每分钟刷新一次, 不要打断正在看的图例
        keys = tuple(k for k, _ in items)
        if col["keys"] != keys:
            col["keys"] = keys
            col["legend"].scroll_to_top()

    @staticmethod
    def _draw_pie(cv: tk.Canvas, size: int, slices, total: float, pct_mode: bool):
        cv.delete("all")
        pad = 6
        x0, y0, x1, y1 = pad, pad, size - pad, size - pad
        cx, cy, r = size / 2.0, size / 2.0, size / 2.0 - pad
        if total <= 0:
            cv.create_oval(x0, y0, x1, y1, fill=_c("chart_empty"), outline="")
            cv.create_text(cx, cy, text=tr("暂无数据"), fill=COLORS["text_dim"],
                           font=config.font("small"))
            return
        if len(slices) == 1:
            cv.create_oval(x0, y0, x1, y1, fill=slices[0][2], outline=COLORS["bg_card"])
        start = 90.0
        labels = []
        for name, v, color in slices:
            extent = -360.0 * v / total
            if len(slices) > 1:
                cv.create_arc(x0, y0, x1, y1, start=start, extent=extent,
                              fill=color, outline=COLORS["bg_card"], width=2, style="pieslice")
            if v / total >= 0.06:
                mid = math.radians(start + extent / 2.0)
                rr = 0.62 * r if len(slices) > 1 else 0.0
                text = f"{v / total * 100:.0f}%" if pct_mode else fmt_hm(v)
                # 空白色很浅, 上面的字用暗色
                fg = COLORS["text_dim"] if color == _c("chart_empty") else COLORS["on_accent"]
                labels.append((cx + rr * math.cos(mid), cy - rr * math.sin(mid), text, fg))
            start += extent
        for x, y, text, fg in labels:
            cv.create_text(x, y, text=text, fill=fg, font=config.font("tiny", bold=True))

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
            if not self.winfo_exists():
                return              # 界面重建后旧页面已销毁, 不再续约
        except Exception:
            return
        try:
            if self.page == "focus" and self.winfo_ismapped():
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
                                    fill=_c("chart_future") if future else _c("chart_empty"))
                hs = row_h * st / 3600.0
                hb = row_h * br / 3600.0
                if hs > 0:
                    cv.create_rectangle(bx0, y1 - hs, bx1, y1, outline="", fill=_c("focus_study"))
                if hb > 0:
                    cv.create_rectangle(bx0, y1 - hs - hb, bx1, y1 - hs, outline="",
                                        fill=_c("focus_break"))
            tot_s = sum(st for st, _ in hours)
            tot_b = sum(br for _, br in hours)
            tx = x1 + config.scaled(12)
            cv.create_text(tx, y0 + row_h * 0.3, anchor="w", fill=_c("focus_study"),
                           font=config.font("small", bold=True),
                           text=f"{tr('专注')} {fmt_hm(tot_s)}")
            cv.create_text(tx, y0 + row_h * 0.75, anchor="w", fill=_c("focus_break"),
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
        tid = cv.create_text(0, 0, text=text, anchor="nw", fill=COLORS["bg"],
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
