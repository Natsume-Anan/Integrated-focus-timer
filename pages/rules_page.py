

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
from .widgets import (Modal, ScrollArea, wrap_label, smooth, cfg, flavor,
                      show_pack, hide_pack, show_grid, hide_grid)
from . import ai_dialogs

_WHY_TEXT = {
    "offline": "离线",
    "blacklist-app": "应用黑名单",
    "blacklist-domain": "网站黑名单",
    "self": "回环",
    "not-whitelisted": "不在白名单",
    "blockall": "屏蔽全部",
}

_PANELS = (
    (WHITE_DOMAINS, "✅  白名单 · 网站"),
    (WHITE_APPS, "✅  白名单 · 应用"),
    (BLACK_DOMAINS, "⛔  黑名单 · 网站"),
    (BLACK_APPS, "⛔  黑名单 · 应用"),
)


class RulesPage(tk.Frame):
    """🛡 Rules 页:proxy 屏蔽模式的名单.黑 / 白名单二选一,只显示当前模式的两张表."""

    def __init__(self, master, controller, settings=None, on_changed=None,
                 on_open_settings=None, sync=None):
        super().__init__(master, bg=COLORS["bg"])
        self.sync = sync
        self._found_ids = []
        self._peer_ids = []
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
        self.lbl_stats = tk.Label(stin, text="", bg=card, fg=COLORS["text_dim"],
                                  font=config.font("small"), anchor="w")
        self.lbl_stats.pack(fill="x", pady=(2, 0))
        wrap_label(self.lbl_mode, 30)
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

        # 作者的话: 为什么默认放行 (MECHANICS.md 4.1)
        flavor(body, tr(
            "你们贴心的作者已经考虑到了戒断反应和设置参数的资料查询需要,所以默认是放行的.\n在完成初始设置后,各项设置的修改限制才会生效.\n作者比较喜欢用proxy block-all."), bg=bg).pack(fill="x", pady=(0, 10))

        grid = tk.Frame(body, bg=bg)
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="col")
        grid.grid_columnconfigure(1, weight=1, uniform="col")
        for key, title in _PANELS:
            self._make_panel(grid, key, title, row=0,
                             col=0 if key in (WHITE_DOMAINS, BLACK_DOMAINS) else 1)

        tk.Label(body, text=tr("⏳  等待生效的改动"), bg=bg, fg=COLORS["text"],
                 font=config.font("body", bold=True)).pack(anchor="w", pady=(10, 2))
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
        if self.sync is not None:
            self._build_sync(body)
        self.area.bind_children()

    def _make_panel(self, parent, key, title, row, col):
        card = COLORS["bg_card"]
        fr = tk.Frame(parent, bg=card, highlightbackground=COLORS["border"],
                      highlightthickness=1)
        fr.grid(row=row, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0),
                pady=(0, 8))
        self._frames[key] = fr
        tk.Label(fr, text=tr(title), bg=card, fg=COLORS["text"],
                 font=config.font("body", bold=True), anchor="w").pack(
            fill="x", padx=10, pady=(8, 0))

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


    def _toast_status(self, status: str, key: str = None, item: str = None):
        if status == "applied":
            toast.success(tr("已生效."))
        elif status == "staged":
            p = self.rules.pending_for(key, item) if key and item else None
            p = p or (self.rules.pending[-1] if self.rules.pending else None)
            at = f"{p['apply_at']:%Y-%m-%d %H:%M}" if p else ""
            toast.info(tr("将于 {at} 生效.").format(at=at))
        elif status == "cancelled":
            toast.info(tr("已取消排队中的改动,名单保持原样."))
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
        status, item = self.rules.add(key, text)
        if status in ("applied", "staged", "cancelled"):
            self._entries[key].set("")
        self._toast_status(status, key, item)
        self.refresh(force=True)

    def _remove(self, key):
        lb = self._lists[key]
        picks = [self._shown[key][i] for i in lb.curselection()
                 if i < len(self._shown.get(key, ()))]
        if not picks:
            toast.info(tr("先在列表里选中要删除的项."))
            return
        statuses = [self.rules.remove(key, item)[0] for item in picks]
        for st in ("staged", "applied", "cancelled"):
            if st in statuses:
                self._toast_status(st, key, picks[-1] if len(picks) == 1 else None)
                break
        else:
            self._toast_status(statuses[-1])
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
                tr("只读取浏览器历史里的域名和访问次数,不保存,不上传."),
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

        net_mode = getattr(config, "NET_MODE", "adapter")
        proxy_on = net_mode in ("proxy", "proxy_all")
        mode = self._mode()
        active = keys_for_mode(mode)

        for key, fr in self._frames.items():
            if key in active:
                show_grid(fr)
            else:
                hide_grid(fr)
        for m, b in self.btn_modes.items():
            cfg(b, style="Accent.TButton" if m == mode else "TButton")
        staged = self.settings.staged("FILTER_MODE") if self.settings else None
        if staged:
            target = tr("白名单模式") if staged["value"] == MODE_WHITELIST else tr("黑名单模式")
            cfg(self.lbl_pending_mode,
                text=tr("待生效: 切换到{mode}   ·   {when}").format(
                    mode=target, when=self.settings.apply_at_text("FILTER_MODE")))
        else:
            cfg(self.lbl_pending_mode, text="")

        if proxy_on:
            hide_pack(self.btn_settings)
            run = tr("运行中") if c.running else tr("未运行")
            text = tr("Proxy 模式 · 本地代理 127.0.0.1:{port} · {run}").format(port=c.port, run=run)
            if net_mode == "proxy_all":
                text += "\n" + tr("代理 - 屏蔽全部: 离线时全部拦截, 名单不起作用.")
            cfg(self.lbl_mode, text=text,
                fg=COLORS["success"] if c.running else COLORS["warn"])
        else:
            cfg(self.lbl_mode,
                text=tr("Adapter 模式 · 规则未启用"),
                fg=COLORS["warn"])
            show_pack(self.btn_settings, anchor="w", pady=(6, 0))
        cfg(self.lbl_stats,
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
        self._sync_refresh()

    # ---- 设备同步 (MECHANICS 15) ----

    def _build_sync(self, body):
        bg, card = COLORS["bg"], COLORS["bg_card"]
        tk.Label(body, text=tr("🔗  设备同步"), bg=bg, fg=COLORS["text"],
                 font=config.font("body", bold=True)).pack(anchor="w", pady=(4, 2))
        fr = tk.Frame(body, bg=card, highlightbackground=COLORS["border"], highlightthickness=1)
        fr.pack(fill="x", pady=(0, 14))
        inner = tk.Frame(fr, bg=card)
        inner.pack(fill="x", padx=14, pady=10)
        self.lbl_sync_me = tk.Label(inner, text="", bg=card, fg=COLORS["text_dim"],
                                    font=config.font("small"), anchor="w", justify="left")
        self.lbl_sync_me.pack(fill="x")

        row = tk.Frame(inner, bg=card)
        row.pack(fill="x", pady=(8, 4))
        ttk.Button(row, text=tr("🔍 寻找设备"), command=self._sync_discover).pack(side="left")
        self.var_sync_addr = tk.StringVar()
        ent = ttk.Entry(row, textvariable=self.var_sync_addr, width=22)
        ent.pack(side="left", padx=(8, 0))
        ent.bind("<Return>", lambda _e: self._sync_connect())
        ttk.Button(row, text=tr("按地址连接"), command=self._sync_connect).pack(side="left", padx=(6, 0))

        self.lb_found = tk.Listbox(inner, height=3, activestyle="none", exportselection=False,
                                   font=config.font("small"), highlightbackground=COLORS["border"])
        self.lb_found.pack(fill="x", pady=(4, 4))
        row2 = tk.Frame(inner, bg=card)
        row2.pack(fill="x")
        ttk.Button(row2, text=tr("绑定 · 本机为母端"), style="Accent.TButton",
                   command=lambda: self._sync_pair(True)).pack(side="left")
        ttk.Button(row2, text=tr("绑定 · 对方为母端"),
                   command=lambda: self._sync_pair(False)).pack(side="left", padx=(6, 0))
        self.btn_pair_cancel = ttk.Button(row2, text=tr("取消"), command=self._sync_cancel)
        self.lbl_pair = tk.Label(inner, text="", bg=card, fg=COLORS["accent"],
                                 font=config.font("body", bold=True), anchor="w", justify="left")
        self.lbl_pair.pack(fill="x", pady=(6, 0))

        tk.Label(inner, text=tr("已绑定的设备"), bg=card, fg=COLORS["text"],
                 font=config.font("small", bold=True), anchor="w").pack(fill="x", pady=(10, 2))
        self.lb_peers = tk.Listbox(inner, height=3, activestyle="none", exportselection=False,
                                   font=config.font("small"), highlightbackground=COLORS["border"])
        self.lb_peers.pack(fill="x")
        row3 = tk.Frame(inner, bg=card)
        row3.pack(fill="x", pady=(4, 0))
        ttk.Button(row3, text=tr("立即同步"), command=self.sync.sync_now).pack(side="left")
        ttk.Button(row3, text=tr("解除绑定"), command=self._sync_unpair).pack(side="left", padx=(6, 0))

    def _sync_discover(self):
        import threading

        def go():
            try:
                self.sync.discover(2.5)
            except OSError:
                pass
        threading.Thread(target=go, daemon=True).start()
        toast.info(tr("正在寻找同一局域网里的 OIT…"))

    def _sync_connect(self):
        import threading
        text = self.var_sync_addr.get().strip()
        if not text:
            return
        host, _, port = text.partition(":")
        try:
            port = int(port) if port else 17930
        except ValueError:
            toast.warn(tr("地址格式: 192.168.1.5 或 192.168.1.5:17930"))
            return

        def go():
            try:
                d = self.sync.hello(host, port)
                self.sync._note_found(d, host)
            except Exception as e:
                self.after(0, lambda: toast.warn(tr("连接失败: {e}", e=e)))
        threading.Thread(target=go, daemon=True).start()

    def _sync_pair(self, mother_is_me: bool):
        sel = self.lb_found.curselection()
        if not sel or sel[0] >= len(self._found_ids):
            toast.warn(tr("先在上面选一台设备."))
            return
        if getattr(config, "NET_MODE", "adapter") not in ("proxy", "proxy_all"):
            toast.warn(tr("两端都使用 Proxy 断网方式时才能同步."))
            return
        d = self.sync.found.get(self._found_ids[sel[0]])
        if not d:
            return
        if not mother_is_me and not toast.ask(
                tr("本机的设置, 名单和记录将被对方的数据替换."), title=tr("绑定"), danger=True):
            return
        self.sync.start_pairing(d["addr"], d["port"], mother_is_me)

    def _sync_cancel(self):
        self.sync.cancel_pairing()

    def _sync_unpair(self):
        sel = self.lb_peers.curselection()
        if not sel or sel[0] >= len(self._peer_ids):
            toast.warn(tr("先在上面选一台设备."))
            return
        pid = self._peer_ids[sel[0]]
        name = self.sync.peers().get(pid, {}).get("name", "?")
        if toast.ask(tr("解除和 {name} 的绑定?", name=name), title=tr("解除绑定"), danger=True):
            self.sync.unpair(pid)

    def _sync_refresh(self):
        s = self.sync
        if s is None or not hasattr(self, "lbl_sync_me"):
            return
        proxy_on = getattr(config, "NET_MODE", "adapter") in ("proxy", "proxy_all")
        me = tr("本机: {name} · 端口 {port}", name=s.my_name, port=s.port or "-")
        if not proxy_on:
            me += "\n" + tr("两端都使用 Proxy 断网方式时才能同步.")
        cfg(self.lbl_sync_me, text=me, fg=COLORS["text_dim"] if proxy_on else COLORS["warn"])

        peers = s.peers()
        found = [d for d in s.found.values() if d["id"] not in peers]
        ids = [d["id"] for d in found]
        rows = [f"{d['name']}  ({d['platform']})  {d['addr']}:{d['port']}"
                + ("" if d.get("net_mode") == "proxy" else "  · " + tr("不是 Proxy 模式")) for d in found]
        if self._shown.get("_found") != rows:
            self._shown["_found"] = rows
            self._found_ids = ids
            self.lb_found.delete(0, "end")
            for r in rows:
                self.lb_found.insert("end", r)

        o = s.outgoing or {}
        st = o.get("state")
        text = {
            "connecting": tr("正在连接…"),
            "waiting": tr("配对码 {code} · 请在 {name} 上确认", code=o.get("code"), name=o.get("name")),
            "accepted": tr("已绑定 {name}.", name=o.get("name")),
            "rejected": tr("对方拒绝了绑定."),
            "timeout": tr("对方没有在 2 分钟内确认."),
            "cancelled": tr("已取消."),
            "error": tr("绑定失败: {e}", e=tr({"not-proxy": "本机不是 Proxy 断网方式",
                                                "peer-not-proxy": "对方不是 Proxy 断网方式"}
                                               .get(o.get("error"), o.get("error") or ""))),
        }.get(st, "")
        cfg(self.lbl_pair, text=text)
        if st in ("connecting", "waiting"):
            show_pack(self.btn_pair_cancel, side="left", padx=(6, 0))
        else:
            hide_pack(self.btn_pair_cancel)

        now = datetime.now().timestamp() * 1000
        status = {st_["id"]: st_ for st_ in s.peer_status()}
        prow, pids = [], []
        for pid, p in peers.items():
            role = tr("母端") if p.get("mother") == pid else (
                tr("本机是母端") if p.get("mother") == s.my_id else "")
            if p.get("last_err"):
                when = tr("同步失败: {e}", e=p["last_err"])
            elif p.get("last_ok"):
                when = tr("上次同步 {t}", t=datetime.fromtimestamp(p["last_ok"] / 1000).strftime("%H:%M:%S"))
            else:
                when = tr("还没同步过")
            live = ""
            stt = status.get(pid)
            if stt and now - float(stt.get("ts", 0)) < 60_000:
                live = {"running": tr("专注中…"), "break": tr("休息中 ☕")}.get(stt.get("timer"), "")
            prow.append("  ·  ".join(x for x in (f"{p['name']} ({p['platform']})", role, when, live) if x))
            pids.append(pid)
        if self._shown.get("_peers") != prow:
            self._shown["_peers"] = prow
            self._peer_ids = pids
            self.lb_peers.delete(0, "end")
            for r in prow:
                self.lb_peers.insert("end", r)

    @staticmethod
    def _list_label(key: str) -> str:
        return {
            WHITE_DOMAINS: tr("白名单·网站"), WHITE_APPS: tr("白名单·应用"),
            BLACK_DOMAINS: tr("黑名单·网站"), BLACK_APPS: tr("黑名单·应用"),
        }.get(key, key)
