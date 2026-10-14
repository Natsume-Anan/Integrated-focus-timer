

import os
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import config
import toast
from config import COLORS
from i18n import tr
from netproxy import (
    WHITE_DOMAINS, WHITE_APPS, BLACK_DOMAINS, BLACK_APPS,
)
from netproxy.rules import MODE_BLACKLIST, MODE_WHITELIST, keys_for_mode
from .widgets import Modal, ScrollArea, wrap_label, smooth
from . import ai_dialogs

_WHY_TEXT = {
    "offline": "离线",
    "blacklist-app": "应用黑名单",
    "blacklist-domain": "网站黑名单",
    "self": "回环",
}

_PANELS = (
    (WHITE_DOMAINS, "✅  白名单 · 网站", "离线时也放行.写域名即可,子域名自动包含."),
    (WHITE_APPS, "✅  白名单 · 应用", "离线时也放行这个程序的全部联网.写 exe 名,如 code.exe."),
    (BLACK_DOMAINS, "⛔  黑名单 · 网站", "禁止访问.写域名即可,子域名自动包含."),
    (BLACK_APPS, "⛔  黑名单 · 应用", "禁止这个程序联网.写 exe 名,如 steam.exe."),
)

_MODE_TEXT = {
    MODE_BLACKLIST: "黑名单模式:默认放行,只拦名单里的网站 / 应用.",
    MODE_WHITELIST: "白名单模式:默认拦截,离线时只放行名单里的网站 / 应用;联网会话中全部放行.",
}


class RulesPage(tk.Frame):
    """🛡 Rules 页:proxy 屏蔽模式的名单.黑 / 白名单二选一,只显示当前模式的两张表."""

    def __init__(self, master, controller, settings=None, on_changed=None,
                 on_open_settings=None):
        super().__init__(master, bg=COLORS["bg"])
        self.ctrl = controller
        self.rules = controller.rules
        self.settings = settings
        self.on_changed = on_changed
        self.on_open_settings = on_open_settings
        self._lists = {}
        self._frames = {}
        self._pending_idx = []
        self._entries = {}
        self._shown = {}
        self._rules_version = -1
        self._ai_cfg = None
        self._build()


    def _build(self):
        bg, card = COLORS["bg"], COLORS["bg_card"]

        hdr = tk.Frame(self, bg=bg)
        hdr.pack(fill="x", padx=28, pady=(18, 6))
        tk.Label(hdr, text=tr("🛡  规则"), bg=bg, fg=COLORS["text"],
                 font=config.font("h1", bold=True)).pack(anchor="w")
        self.lbl_sub = tk.Label(hdr, bg=bg, fg=COLORS["text_dim"], font=config.font("body"),
                                anchor="w", justify="left", text="")
        self.lbl_sub.pack(anchor="w", pady=(4, 0), fill="x")
        wrap_label(self.lbl_sub, 24)

        self.area = ScrollArea(self, height=420, bg=bg)
        self.area.pack(fill="both", expand=True, padx=26, pady=(6, 4))
        body = self.area.inner

        st = tk.Frame(body, bg=card, highlightbackground=COLORS["border"], highlightthickness=1)
        st.pack(fill="x", pady=(0, 8))
        stin = tk.Frame(st, bg=card)
        stin.pack(fill="x", padx=14, pady=10)
        self.lbl_mode = tk.Label(stin, text="", bg=card, fg=COLORS["text"],
                                 font=config.font("body", bold=True), anchor="w",
                                 justify="left")
        self.lbl_mode.pack(fill="x")
        self.lbl_gate = tk.Label(stin, text="", bg=card, fg=COLORS["text_dim"],
                                 font=config.font("small"), anchor="w", justify="left")
        self.lbl_gate.pack(fill="x", pady=(2, 0))
        self.lbl_stats = tk.Label(stin, text="", bg=card, fg=COLORS["text_dim"],
                                  font=config.font("small"), anchor="w")
        self.lbl_stats.pack(fill="x")
        wrap_label(self.lbl_mode, 30)
        wrap_label(self.lbl_gate, 30)
        self.btn_settings = ttk.Button(
            stin, text=tr("去设置里切换断网方式"),
            command=lambda: self.on_open_settings and self.on_open_settings())

        mrow = tk.Frame(stin, bg=card)
        mrow.pack(fill="x", pady=(8, 0))
        self.btn_modes = {}
        for mode, label in ((MODE_BLACKLIST, "⛔  黑名单模式"), (MODE_WHITELIST, "✅  白名单模式")):
            b = ttk.Button(mrow, text=tr(label), command=lambda m=mode: self._set_mode(m))
            b.pack(side="left", padx=(0, 8))
            self.btn_modes[mode] = b
        ttk.Button(mrow, text=tr("⚙ 模型"), command=self._ai_settings).pack(side="right")
        ttk.Button(mrow, text=tr("🤖 AI 建议"), command=self._ai_suggest).pack(
            side="right", padx=(0, 8))
        self.lbl_pending_mode = tk.Label(stin, text="", bg=card, fg=COLORS["warn"],
                                         font=config.font("small"), anchor="w",
                                         justify="left")
        self.lbl_pending_mode.pack(fill="x", pady=(4, 0))
        wrap_label(self.lbl_pending_mode, 30)

        grid = tk.Frame(body, bg=bg)
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="col")
        grid.grid_columnconfigure(1, weight=1, uniform="col")
        for i, (key, title, hint) in enumerate(_PANELS):
            self._make_panel(grid, key, title, hint, row=0,
                             col=0 if key in (WHITE_DOMAINS, BLACK_DOMAINS) else 1)

        tk.Label(body, text=tr("⏳  等待生效的放宽"), bg=bg, fg=COLORS["text"],
                 font=config.font("body", bold=True)).pack(anchor="w", pady=(10, 2))
        self.lbl_setup = tk.Label(body, text="", bg=bg, fg=COLORS["text_dim"],
                                  font=config.font("small"), anchor="w", justify="left")
        self.lbl_setup.pack(fill="x")
        wrap_label(self.lbl_setup, 24)
        pf = tk.Frame(body, bg=bg)
        pf.pack(fill="x", pady=(2, 0))
        self.lb_pending = tk.Listbox(pf, height=4, activestyle="none",
                                     font=config.font("small"), exportselection=False,
                                     highlightbackground=COLORS["border"])
        self.lb_pending.pack(side="left", fill="x", expand=True)
        ttk.Button(pf, text=tr("✕ 取消选中"), command=self._cancel_pending).pack(
            side="left", padx=(8, 0))

        tk.Label(body, text=tr("🚫  最近被拦截的请求"), bg=bg, fg=COLORS["text"],
                 font=config.font("body", bold=True)).pack(anchor="w", pady=(12, 2))
        self.lb_events = tk.Listbox(body, height=7, activestyle="none",
                                    font=config.font("small"), exportselection=False,
                                    highlightbackground=COLORS["border"])
        self.lb_events.pack(fill="x", pady=(0, 14))
        self.area.bind_children()

    def _make_panel(self, parent, key, title, hint, row, col):
        card = COLORS["bg_card"]
        fr = tk.Frame(parent, bg=card, highlightbackground=COLORS["border"],
                      highlightthickness=1)
        fr.grid(row=row, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0),
                pady=(0, 8))
        self._frames[key] = fr
        tk.Label(fr, text=tr(title), bg=card, fg=COLORS["text"],
                 font=config.font("body", bold=True), anchor="w").pack(
            fill="x", padx=10, pady=(8, 0))
        h = tk.Label(fr, text=tr(hint), bg=card, fg=COLORS["text_dim"],
                     font=config.font("tiny"), anchor="w", justify="left")
        h.pack(fill="x", padx=10)
        wrap_label(h, 20)

        lf = tk.Frame(fr, bg=card)
        lf.pack(fill="both", expand=True, padx=10, pady=(6, 4))
        sb = ttk.Scrollbar(lf, orient="vertical")
        lb = tk.Listbox(lf, height=6, activestyle="none", exportselection=False,
                        font=config.font("small"), yscrollcommand=sb.set,
                        highlightbackground=COLORS["border"], selectmode="extended")
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        self._lists[key] = lb

        er = tk.Frame(fr, bg=card)
        er.pack(fill="x", padx=10, pady=(0, 4))
        var = tk.StringVar()
        ent = ttk.Entry(er, textvariable=var)
        ent.pack(side="left", fill="x", expand=True)
        ent.bind("<Return>", lambda _e, k=key: self._add(k))
        self._entries[key] = var
        ttk.Button(er, text=tr("添加"), style="Accent.TButton",
                   command=lambda k=key: self._add(k)).pack(side="left", padx=(6, 0))

        br = tk.Frame(fr, bg=card)
        br.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(br, text=tr("删除选中"),
                   command=lambda k=key: self._remove(k)).pack(side="left")
        ttk.Button(br, text=tr("从本机选择…"),
                   command=lambda k=key: self._pick(k)).pack(side="left", padx=(6, 0))


    def _toast_status(self, status: str, action: str = "add"):
        if status == "applied":
            toast.success(tr("已生效."))
        elif status == "staged":
            p = self.rules.pending[-1] if self.rules.pending else None
            at = f"{p['apply_at']:%Y-%m-%d %H:%M}" if p else ""
            toast.info(tr("放宽规则要等冷静期,将于 {at} 生效.").format(at=at))
        elif status == "exists":
            toast.info(tr("已经在名单里了."))
        elif status == "missing":
            toast.info(tr("名单里没有这一项."))
        else:
            toast.warn(tr("格式不对,请检查后重试."))

    def _add(self, key):
        text = self._entries[key].get().strip()
        if not text:
            return
        status, _item = self.rules.add(key, text)
        if status in ("applied", "staged"):
            self._entries[key].set("")
        self._toast_status(status)
        self.refresh(force=True)

    def _remove(self, key):
        lb = self._lists[key]
        picks = [self._shown[key][i] for i in lb.curselection()
                 if i < len(self._shown.get(key, ()))]
        if not picks:
            toast.info(tr("先在列表里选中要删除的项."))
            return
        last = None
        for item in picks:
            last, _ = self.rules.remove(key, item)
        self._toast_status(last, "remove")
        self.refresh(force=True)

    def _cancel_pending(self):
        sel = self.lb_pending.curselection()
        if not sel or sel[0] >= len(self._pending_idx):
            return
        if self.rules.cancel_pending(self._pending_idx[sel[0]]):
            self.refresh(force=True)

    def _mode(self) -> str:
        return MODE_WHITELIST if getattr(config, "FILTER_MODE", MODE_BLACKLIST) == MODE_WHITELIST \
            else MODE_BLACKLIST

    @smooth
    def _set_mode(self, mode: str):
        if self.settings is None:
            return
        status, msg = self.settings.stage("FILTER_MODE", mode)
        if status in ("instant", "staged", "nochange"):
            toast.info(tr(msg))
        if self.on_changed and status in ("instant", "staged"):
            self.on_changed(status, "FILTER_MODE")
        self.refresh(force=True)

    def _ai(self):
        if self._ai_cfg is None:
            import ai_assist
            self._ai_cfg = ai_assist.AIConfig(
                os.path.join(os.path.dirname(self.rules.path), "ai_config.json"),
                template=ai_assist.DEFAULT_TEMPLATE)
        return self._ai_cfg

    def _ai_settings(self):
        ai_dialogs.open_model_settings(self.winfo_toplevel(), self._ai())

    def _ai_suggest(self):
        ai_dialogs.open_suggest(self.winfo_toplevel(), self._ai(), self.rules, self._mode(),
                                on_done=lambda: self.refresh(force=True))

    def _pick(self, key):
        """从本机已装应用 / 浏览器常访问域名里多选;采集逻辑见 context_collect.py."""
        import context_collect
        is_app = key in (WHITE_APPS, BLACK_APPS)
        if is_app:
            try:
                apps = context_collect.collect_apps()
            except Exception:
                apps = []
            options = [(a["exe"], f"{a['name']}  ({a['exe']})") for a in apps]
        else:
            if not toast.ask(
                tr("将读取本机浏览器历史,只统计「域名 + 访问次数」,不读网址,标题和搜索词,"
                   "也不保存,不上传.\n\n继续吗?"),
                title=tr("读取浏览器记录")
            ):
                return
            try:
                domains, _src = context_collect.collect_browser_domains(days=90)
            except Exception:
                domains = []
            options = [(d["domain"], f"{d['domain']}  —  {d['visits']}") for d in domains]
        if not options:
            toast.info(tr("没有读到可选项."))
            return

        dlg = Modal(self.winfo_toplevel(), tr("从本机选择"), width=480, height=460)
        lf = tk.Frame(dlg.body, bg=COLORS["bg"])
        lf.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(lf, orient="vertical")
        lb = tk.Listbox(lf, selectmode="extended", activestyle="none", exportselection=False,
                        font=config.font("small"), yscrollcommand=sb.set)
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        for _v, label in options:
            lb.insert("end", label)
        ttk.Button(dlg.buttons, text=tr("添加选中"), style="Accent.TButton",
                   command=lambda: dlg.finish(list(lb.curselection()))).pack(side="right")
        ttk.Button(dlg.buttons, text=tr("取消"), command=dlg.cancel).pack(
            side="right", padx=(0, 8))
        picked = dlg.wait()
        if not picked:
            return
        statuses = [self.rules.add(key, options[i][0])[0] for i in picked]
        self._toast_status("staged" if "staged" in statuses else
                           ("applied" if "applied" in statuses else statuses[0]))
        self.refresh(force=True)


    def refresh(self, force: bool = False):
        r = self.rules
        r.promote_due()
        c = self.ctrl

        proxy_on = getattr(config, "NET_MODE", "adapter") == "proxy"
        mode = self._mode()
        active = keys_for_mode(mode)

        self.lbl_sub.config(text=tr(_MODE_TEXT[mode]))
        for key, fr in self._frames.items():
            if key in active:
                fr.grid()
            else:
                fr.grid_remove()
        for m, b in self.btn_modes.items():
            b.config(style="Accent.TButton" if m == mode else "TButton")
        staged = self.settings.staged("FILTER_MODE") if self.settings else None
        if staged:
            target = tr("白名单模式") if staged["value"] == MODE_WHITELIST else tr("黑名单模式")
            self.lbl_pending_mode.config(
                text=tr("待生效: 切换到{mode}   ·   {when}").format(
                    mode=target, when=self.settings.apply_at_text("FILTER_MODE")))
        else:
            self.lbl_pending_mode.config(text="")

        if proxy_on:
            self.btn_settings.pack_forget()
            run = tr("运行中") if c.running else tr("未运行")
            self.lbl_mode.config(
                text=tr("Proxy 模式 · 本地代理 127.0.0.1:{port} · {run}").format(
                    port=c.port, run=run),
                fg=COLORS["success"] if c.running else COLORS["warn"])
            if mode == MODE_WHITELIST:
                gate = (tr("联网中:全部放行.") if c.online
                        else tr("离线:只放行白名单,其余一律拦截."))
            else:
                gate = tr("只拦黑名单里的网站 / 应用,其余放行.")
        else:
            self.lbl_mode.config(
                text=tr("当前是 Adapter 模式 —— 规则已保存,但暂未启用."),
                fg=COLORS["warn"])
            self.btn_settings.pack(anchor="w", pady=(6, 0))
            gate = tr("在 Settings 里把「断网方式」改成 Proxy 后,这些规则才会生效.")
        self.lbl_gate.config(text=gate)
        self.lbl_stats.config(
            text=tr("已放行 {a} 次 · 已拦截 {b} 次(本次运行)").format(a=c.allowed, b=c.blocked))

        if force or self._rules_version != r.version:
            self._rules_version = r.version
            for key, lb in self._lists.items():
                items = r.items(key)
                if self._shown.get(key) != items:
                    self._shown[key] = items
                    lb.delete(0, "end")
                    for it in items:
                        lb.insert("end", it)

        self._pending_idx = [i for i, p in enumerate(r.pending) if p["list"] in active]
        pend = [f"{'+' if r.pending[i]['op'] == 'add' else '-'} "
                f"{self._list_label(r.pending[i]['list'])}: {r.pending[i]['item']}   →  "
                f"{r.pending[i]['apply_at']:%m-%d %H:%M}" for i in self._pending_idx]
        if self._shown.get("_pending") != pend:
            self._shown["_pending"] = pend
            self.lb_pending.delete(0, "end")
            for line in pend:
                self.lb_pending.insert("end", line)
        if r.in_setup_window():
            self.lbl_setup.config(text=tr("初始化窗口内:放宽也立即生效.之后加入白名单 / 移出黑名单要等冷静期."))
        else:
            self.lbl_setup.config(text=tr("加入白名单,移出黑名单要等冷静期;加入黑名单,移出白名单立即生效."))

        seq = (c.event_seq, sum(e["count"] for e in c.events))
        if force or self._shown.get("_events") != seq:
            self._shown["_events"] = seq
            self.lb_events.delete(0, "end")
            for e in reversed(list(c.events)[-30:]):
                t = datetime.fromtimestamp(e["ts"]).strftime("%H:%M:%S")
                who = f"  [{e['exe']}]" if e["exe"] else ""
                n = f"  ×{e['count']}" if e["count"] > 1 else ""
                self.lb_events.insert(
                    "end", f"{t}  {e['host']}{who}  ({tr(_WHY_TEXT.get(e['why'], e['why']))}){n}")

    @staticmethod
    def _list_label(key: str) -> str:
        return {
            WHITE_DOMAINS: tr("白名单·网站"), WHITE_APPS: tr("白名单·应用"),
            BLACK_DOMAINS: tr("黑名单·网站"), BLACK_APPS: tr("黑名单·应用"),
        }.get(key, key)
