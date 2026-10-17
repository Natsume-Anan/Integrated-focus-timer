

import threading

import config

LANGUAGES = [("zh", "中文"), ("en", "English")]
DEFAULT_LANGUAGE = "zh"

_lock = threading.RLock()
_current = DEFAULT_LANGUAGE


EN = {
    "确定": "OK",
    "取消": "Cancel",
    "当前": "Current",
    "立即生效中…": "applying…",
    "正在加载…": "Loading…",
    "正在重新加载界面…": "Reloading the interface…",
    "切换语言 / 字号 / 主题需要重建所有页面,请稍候": "Changing language / font size / theme rebuilds every page, one moment",
    "开启": "ON",
    "关闭_状态": "OFF",
    "⏱  Timer": "⏱  Timer",
    "🌐  Network": "🌐  Network",
    "🛡  Rules": "🛡  Rules",
    "📝  Hour Log": "📝  Hour Log",
    "📅  Calendar": "📅  Calendar",
    "📊  Statistics": "📊  Statistics",
    "⚙  Settings": "⚙  Settings",
    "🗑  Uninstall": "🗑  Uninstall",
    "⏱  Focus Timer": "⏱  Focus Timer",
    "准备就绪": "Ready",
    "专注中…": "Focusing…",
    "本次专注结束": "Work session done",
    "休息中 ☕": "On break ☕",
    "开始专注时按 [开始].": "Press [Start] when you begin focusing.",
    "计时中 —— 结束时按 [结束].": "Clock is running — click [Finish] when done.",
    "休息吧,倒计时中…": "Relax. Timer counting down…",
    "今日: {h:.1f} h": "Today: {h:.1f} h",
    "昨日: {h:.1f} h": "Yesterday: {h:.1f} h",
    "▶  开始": "▶  Start",
    "■  结束": "■  Finish",
    "☕  去休息": "☕  Have a break",
    "已工作 {m:.2f} 分钟 → 上方是建议休息时长": "Worked {m:.2f} min  →  suggested rest above",
    "剩余时间为 0,已重置.": "Remaining time is 0. Resetting.",
    "休息结束,可以开始下一轮了!": "Break finished. Ready for next round!",
    "预计停止时的休息时长:  {m:.2f} 分钟": "Projected break when you stop:  {m:.2f} min",
    "预计休息时长: 0.00 分钟": "Projected break: 0.00 min",
    "休息剩余 {m} 分 {s:02d} 秒": "Break ends in {m}m {s:02d}s",
    "⏸  暂停休息": "⏸  Pause break",
    "网络正在使用,不能暂停休息.": "The network is in use; the break can't be paused.",
    "(含之前暂停休息结转的 {c})": "(includes {c} carried over from paused breaks)",
    "休息已暂停.\n剩余 {left} 按 ×{r:g} 计入下次休息: +{add}": "Break paused.\n{left} left × {r:g} goes to your next break: +{add}",
    "下次休息额外 +{c}": "Next break: +{c} extra",
    "🌐  联网申请": "🌐  Network Access",
    "离线": "Offline",
    "⚡  快速访问(×{a:g})": "⚡  Quick access ({a:g}x)",
    "💳  紧急借贷": "💳  Emergency loan",
    "⚡  改为快速访问(×{a:g})": "⚡  Switch to quick access ({a:g}x)",
    "快速访问": "Quick access",
    "紧急借贷": "Emergency loan",
    "快速访问跳过冷静期立刻联网,额度按 ×{a:g} 消耗.\n\n联网: {m} 分钟\n消耗: {cost} 今日额度\n\n确定吗?": "Quick access skips the cooldown and goes online now; quota is used at {a:g}x.\n\nOnline: {m} min\nCost: {cost} of today's quota\n\nContinue?",
    "紧急借贷不会联网,只会给今天加额度;明天扣 {b:g} 倍.": "An emergency loan does not go online; it only adds quota for today, and tomorrow pays {b:g}x.",
    "今天额度 +{add}.": "Today's quota +{add}.",
    "立刻结束冷静期并联网?\n\n联网: {m} 分钟\n消耗: {cost} 今日额度(×{a:g})\n\n确定吗?": "End the cooldown and go online now?\n\nOnline: {m} min\nCost: {cost} of today's quota ({a:g}x)\n\nContinue?",
    "⚡ 快速访问 —— 额度按 ×{a:g} 消耗,归零自动断网.": "⚡ Quick access — quota is used at {a:g}x. Network is cut automatically at zero.",
    "今日已用: {used} / {total}     今日剩余: {left}     可快速访问: {quick}": "Used today: {used} / {total}     Left today: {left}     Quick access: {quick}",
    "今天已借 {bonus},明天将扣 {cost}(明天剩余 {left})": "Borrowed today: {bonus}; tomorrow pays {cost} (tomorrow left: {left})",
    "今天要先还昨天借的 {debt}": "Repaying yesterday's loan today: {debt}",
    "联网中": "Online",
    "冷静期中 —— 仍可取消": "Cooldown — you can still cancel",
    "今天的额度已用完.": "Today's quota is used up.",
    "已申请 {m} 分钟 · {at} 联网": "Requested {m} min · goes online at {at}",
    "分钟": "Minutes",
    "理由": "Reason",
    "📨  提交申请(需冷静期)": "📨  Request (cooldown)",
    "分钟数必须是整数.": "Minutes must be an integer.",
    "请写一个申请理由.": "Please write a reason for this request.",
    "✕  取消申请": "✕  Cancel request",
    "■  结束本次会话": "■  End session",
    "📝  整点记录": "📝  Hour Log",
    "本月 ›": "This month ›",
    "‹ 上月": "‹ Last month",
    "📊  统计": "📊  Statistics",
    "🌐  联网理由": "🌐  Network reasons",
    "总时间": "Total time",
    "占比": "Share",
    "显示:": "Show:",
    "上月": "Last month",
    "本月": "This month",
    "其他": "Other",
    "暂无数据": "No data",
    "合计 {t} · {n} 项": "Total {t} · {n} item(s)",
    "当前: {state}": "Current: {state}",
    "{date}(今天)": "{date}  (today)",
    "   ·  记录已关闭": "   ·  logging disabled",
    "   ◂ 现在": "   ◂ now",
    "   ◂ 待填写": "   ◂ fill me",
    "合计: {h:.1f} h": "Total: {h:.1f} h",
    "{year} 年 {month}": "{month} {year}",
    "周一": "Mon",
    "周二": "Tue",
    "周三": "Wed",
    "周四": "Thu",
    "周五": "Fri",
    "周六": "Sat",
    "周日": "Sun",
    "所有文件": "All files",
    "待生效修改 {n} 项 · 最近一项 {h} 小时 {m} 分后生效": "{n} change(s) pending · the next one applies in {h} h {m} min",
    "网络已开启.": "Network is on.",
    "时间到,网络已断开.": "Time is up — network cut off.",
    "hosts: {err}": "hosts: {err}",
    "⚙  设置": "⚙  Settings",
    "每日联网额度": "Daily network quota",
    "联网冷静期": "Network cooldown",
    "整点记录开关": "Hour log switch",
    "超时自动记录内容": "Auto text when a slot is missed",
    "断网复查间隔": "Network re-check interval",
    "整点提示音": "Hourly chime",
    "界面字号": "UI scale",
    "开发者模式": "Developer mode",
    "🛠  开发者模式": "🛠  Developer mode",
    "提交修改": "Submit change",
    "✕ 取消这项修改": "✕ Cancel this change",
    "↩ 取消全部待生效修改": "↩ Cancel all pending changes",
    "💾 保存全部修改": "💾 Save all changes",
    "取消待生效修改": "Cancel pending changes",
    "确定取消全部 {n} 项待生效修改吗?": "Cancel all {n} pending change(s)?",
    "{n} 项即时生效项已保存": "{n} instant item(s) saved",
    "{n} 项已提交,48 小时后生效": "{n} item(s) submitted, applying in 48 h",
    "没有需要保存的修改": "Nothing to save",
    "{n} 项即时生效项已保存\n{m} 项已提交,48 小时后生效": "{n} instant item(s) saved\n{m} item(s) submitted, applying in 48 h",
    "待生效: {value}   ·   {when}": "Pending: {value}   ·   {when}",
    "{at} 生效 (还有 {d} 天 {h} 小时)": "applies {at} (in {d}d {h}h)",
    "{at} 生效 (还有 {h} 小时 {m} 分)": "applies {at} (in {h}h {m}m)",
    "{at} 生效 (还有 {m} 分)": "applies {at} (in {m}m)",
    "当前没有待生效的修改.": "No pending changes.",
    "48 小时冷静期已结束,以下配置从现在开始生效:": "The 48 h cooling-off period is over; these settings are now active:",
    "已关闭(正常模式)": "Off (normal mode)",
    "已开启 —— 网络不受限制": "ON — network unrestricted",
    "开发者模式开关:开启后本程序不再以任何方式断网.调试完成后请关掉.确定开启吗?": "Developer mode: this app will no longer cut the network in any way (rule blocking stays). Turn it off when done. Continue?",
    "即时生效.可粘贴本地 .wav / .mp3 的完整路径.": "Instant. You can paste the full path of a local .wav / .mp3 file.",
    "偏小 (90%)": "Smaller (90%)",
    "标准 (100%)": "Default (100%)",
    "偏大 (115%)": "Larger (115%)",
    "很大 (130%)": "Big (130%)",
    "极大 (150%)": "Huge (150%)",
    "中文": "中文",
    "Sleeping(睡觉)": "Sleeping",
    "Idle(发呆)": "Idle",
    "Break(休息)": "Break",
    "Distracted(分心)": "Distracted",
    "未知配置项 {key}": "Unknown setting: {key}",
    "{label} 已立即生效.": "{label} applied immediately.",
    "{label} 已恢复到当前生效值,排队中的改动已取消.": "{label} reverted to the active value; the queued change was cancelled.",
    "{label} 与当前生效值相同.": "{label} already matches the active value.",
    "{label} 已提交,将于 {at}.": "{label} submitted; applies at {at}.",
    "选择提示音": "Choose a chime",
    "WAV 音频": "WAV audio",
    "选择音频…": "Choose audio…",
    "音频文件": "Audio files",
    "MP3 音频": "MP3 audio",
    "▶ 试听": "▶ Test",
    "内置三音提示音 (推荐)": "Built-in 3-tone chime (recommended)",
    "Windows 蜂鸣声 (Beep)": "Windows beep",
    "内置三音提示音": "Built-in 3-tone chime",
    "Windows 蜂鸣声": "Windows beep",
    "今天最多能联网多久.改动要 48 小时后才生效,期间仍按旧额度计算.": "How long you may be online today. Changes apply after 48 h; the old quota keeps running meanwhile.",
    "提出申请后等多久才真的联网.想立刻联网请用 Network 页的快速访问(额度 2 倍消耗).": "How long to wait after requesting before you actually go online. To go online at once, use quick access on the Network page (quota used at 2x).",
    "程序启动时整点记录的初始状态;启动后仍可在 Hour Log 页直接切换.": "Initial state of the hour log when the app starts; you can still toggle it on the Hour Log page.",
    "整点后一小时内没填写,就自动记成这段文字.这一项可以立即修改.": "If a slot is left blank for an hour, this text is recorded. This item can be changed immediately.",
    "离线状态下每隔多久强制复查并重新断网(越小越难被绕开,代价是更频繁调用系统命令).": "How often, while offline, the app force-checks and cuts the network again (smaller is harder to bypass, at the cost of running system commands more often).",
    "即时生效.界面语言(中文 / English).": "Instant. Interface language (中文 / English).",
    "即时生效.整体缩放界面字号,适配不同分辨率.": "Instant. Scales all UI text for different resolutions.",
    "界面主题": "Theme",
    "经典 (蓝白)": "Classic (blue & white)",
    "Claude (浅色)": "Claude (light)",
    "Claude (深色)": "Claude (dark)",
    "即时生效.界面配色:经典蓝白,或参考 Claude 的米白 / 炭灰配色.": "Instant. Color scheme: classic blue & white, or the Claude-style cream / charcoal look.",
    "开启 (ON)": "ON",
    "关闭 (OFF)": "OFF",
    "⚠  警告:这会永久删除全部数据": "⚠  Warning: this permanently erases ALL data",
    "提示": "Notice",
    "断网方式": "Cut-off method",
    "禁用网卡 (Adapter)": "Disable adapters (Adapter)",
    "本地代理过滤 (Proxy)": "Local filtering proxy (Proxy)",
    "🛡  规则": "🛡  Rules",
    "黑名单任何时候都拦;离线时只放行白名单;联网时除黑名单外全部放行.": "Blacklist is always blocked; offline only the whitelist passes; online everything except the blacklist passes.",
    "去设置里切换断网方式": "Switch cut-off method in Settings",
    "运行中": "running",
    "未运行": "not running",
    "联网中:除黑名单外全部放行.": "Online: everything except the blacklist passes.",
    "当前是 Adapter 模式 —— 规则已保存,但暂未启用.": "Adapter mode is active — rules are saved but not enforced.",
    "Proxy 模式 · 本地代理 127.0.0.1:{port} · {run}": "Proxy mode · local proxy 127.0.0.1:{port} · {run}",
    "已放行 {a} 次 · 已拦截 {b} 次(本次运行)": "Allowed {a} · Blocked {b} (this run)",
    "✅  白名单 · 网站": "✅  Whitelist · Sites",
    "✅  白名单 · 应用": "✅  Whitelist · Apps",
    "⛔  黑名单 · 网站": "⛔  Blacklist · Sites",
    "⛔  黑名单 · 应用": "⛔  Blacklist · Apps",
    "任何时候都拦截,联网会话中也一样.": "Always blocked, including during online sessions.",
    "任何时候都拦截这个程序的联网.": "Always blocks this program's traffic.",
    "添加": "Add",
    "删除选中": "Delete selected",
    "从本机选择…": "Pick from this PC…",
    "从本机选择": "Pick from this PC",
    "添加选中": "Add selected",
    "读取浏览器记录": "Read browser history",
    "将读取本机浏览器历史,只统计「域名 + 访问次数」,不读网址,标题和搜索词,也不保存,不上传.\n\n继续吗?": "This reads local browser history and only counts \"domain + visits\" — no URLs, titles or search terms, nothing is saved or uploaded.\n\nContinue?",
    "没有读到可选项.": "Nothing to choose from.",
    "⏳  等待生效的改动": "⏳  Pending changes",
    "✕ 取消选中": "✕ Cancel selected",
    "🚫  最近被拦截的请求": "🚫  Recently blocked requests",
    "已生效.": "Applied.",
    "这项改动要等冷静期,将于 {at} 生效.": "This change waits for the cooldown; it takes effect at {at}.",
    "已取消排队中的改动,名单保持原样.": "The queued change was cancelled; the list stays as it was.",
    "已经在名单里了.": "Already in the list.",
    "名单里没有这一项.": "Not in the list.",
    "格式不对,请检查后重试.": "Invalid format, please check and retry.",
    "先在列表里选中要删除的项.": "Select the items to delete first.",
    "白名单·网站": "Whitelist·Sites",
    "白名单·应用": "Whitelist·Apps",
    "黑名单·网站": "Blacklist·Sites",
    "黑名单·应用": "Blacklist·Apps",
    "应用黑名单": "app blacklist",
    "网站黑名单": "site blacklist",
    "回环": "loopback",
    "过滤名单模式": "Filter list mode",
    "黑名单模式": "Blacklist mode",
    "白名单模式": "Whitelist mode",
    "⛔  黑名单模式": "⛔  Blacklist mode",
    "✅  白名单模式": "✅  Whitelist mode",
    "待生效: 切换到{mode}   ·   {when}": "Pending: switch to {mode}   ·   {when}",
    "⚙ 模型": "⚙ Model",
    "🤖 AI 建议": "🤖 AI suggestions",
    "AI 模型设置": "AI model settings",
    "Base URL": "Base URL",
    "模型": "Model",
    "接口协议": "API protocol",
    "API Key": "API Key",
    "显示 Key": "Show key",
    "API Key 加密后保存在本机,只有当前 Windows 账户能解开;只经 https 发往所选服务商,不会随名单或日志输出.": "The API key is stored encrypted on this computer and only your Windows account can decrypt it; it is sent only over https to the chosen provider and never written to lists or logs.",
    "为防止 Key 泄露,预设服务商的 Key 只会发往它的官方地址 {host}.要用其他地址(如中转),请选择「自定义供应商」.": "To protect your key, a preset provider's key is only sent to its official address {host}. To use another address (such as a relay), choose \"Custom provider\".",
    "服务商要求跳转到别的地址({code}),为保护 API Key 已拒绝.请检查 Base URL 是否填对.": "The provider asked to redirect to another address ({code}); this was refused to protect your API key. Please check the Base URL.",
    "已保存.": "Saved.",
    "保存失败,请检查应用数据目录的写入权限.": "Save failed. Check write permission on the app data folder.",
    "保存": "Save",
    "请先到「模型设置」里配置.": "Configure it under Model first.",
    "AI 建议 · 黑名单": "AI suggestions · Blacklist",
    "AI 建议 · 白名单": "AI suggestions · Whitelist",
    "先说清楚会发生什么": "What will happen",
    "· 只有你勾选的内容会被读取;读取后先给你预览,你点「发送」之后才会联网.": "· Only what you tick is read; you get a preview first and nothing goes online until you click Send.",
    "· 浏览器记录只取「域名 + 访问次数」,不读网址,标题,搜索词;应用清单只含应用名与 exe 名.": "· Browser history is reduced to domain + visit count (no URLs, titles or searches); the app list has names and exe names only.",
    "· 黑名单模式下,模型只给候选条目,不会给出理由或评价.": "· In blacklist mode the model returns candidate entries only, with no reasons or judgements.",
    "· 模型给出的只是候选,由你勾选后才会加入名单.": "· The model only proposes candidates; nothing is added until you tick it.",
    "发送给: {t}": "Send to: {t}",
    "已安装的应用(名称 + exe 名)": "Installed apps (name + exe name)",
    "浏览器常访问的网站(仅域名与次数),回看": "Frequently visited sites (domain and count only), looking back",
    "天": "days",
    "补充说明(可选,会随请求一起发送)": "Extra note (optional, sent with the request)",
    "采集并预览": "Collect & preview",
    "至少勾选一项.": "Tick at least one item.",
    "正在读取本机信息…": "Reading local information…",
    "读取失败.": "Read failed.",
    "没有读到可用的内容.": "Nothing usable was found.",
    "【补充说明】": "[Extra note]",
    "发送": "Send",
    "返回": "Back",
    "正在请求 {p}…": "Asking {p}…",
    "请求失败.": "Request failed.",
    "模型没有给出可采纳的条目.": "The model returned nothing to adopt.",
    "关闭": "Close",
    "黑名单": "blacklist",
    "白名单": "whitelist",
    "勾选要加入{name}的条目(默认全选):": "Tick the entries to add to the {name} (all selected by default):",
    "(推荐,不在本机记录中)": "(suggested; not in local records)",
    "加入名单要等 48 小时的冷静期才生效.": "Items added to a list take effect after a 48-hour cool-down.",
    "没有选中任何条目.": "Nothing selected.",
    "已提交,要等 48 小时的冷静期后生效.": "Submitted; takes effect after the 48-hour cool-down.",
    "已加入名单.": "Added to the list.",
    "没有新增项(可能已在名单里).": "Nothing new (maybe already in the list).",
    "加入名单": "Add to list",
    "全选": "Select all",
    "Base URL 为空": "Base URL is empty",
    "Base URL 必须是 https:// 开头(本机模型可用 http://localhost)": "Base URL must start with https:// (http://localhost is allowed for local models)",
    "模型名为空": "Model name is empty",
    "还没有填 API Key": "API key not filled in",
    "请求被本程序的过滤代理拦截(该服务商的域名不在白名单中)": "The request was blocked by this program's filter proxy (the provider's domain is not whitelisted)",
    "服务商返回了无法识别的内容": "The provider returned something unrecognisable",
    "模型没有返回内容": "The model returned no content",
    "模型没有按要求返回 JSON": "The model did not return JSON as required",
    "型号": "Model ID",
    "自定义供应商": "Custom provider",
    "自定义供应商:Base URL 与型号请自行填写,协议选 openai(兼容接口)或 anthropic.": "Custom provider: fill in Base URL and model ID yourself; pick openai (compatible API) or anthropic as the protocol.",
    "已自动填入 {name} 的 Base URL,型号可自行修改.": "Base URL for {name} filled in automatically; you can edit the model ID.",
    "· 预览框里的文字可以直接修改:不想让模型看到的网站或应用,删掉那一行即可;也可以自己补充.": "· The preview text is editable: delete the line of any site or app you don't want the model to see, or add your own.",
    "· 内容只发给下面这一家模型服务商,本程序不保存这些内容.": "· The content goes only to the provider below and is not stored by this program.",
    "以下就是将要发送的全部内容(加上固定的提示词).可以直接编辑:删掉不想发送的行,或自行补充.": "This is everything that will be sent (plus the fixed prompt). You can edit it: delete lines you don't want to send, or add your own.",
    "内容是空的,没有可发送的信息.": "The content is empty; there is nothing to send.",
    "内容太长了,请删减到 {n} 字以内.": "Too long; please trim it to {n} characters or fewer.",
    "开发者模式确认": "Confirm developer mode",
    "开发者模式已开启:本程序不会断网,也不会申请/计时.\n调试完成后请到 Settings 页关掉它.": "Developer mode is on: this app won't cut the network, and requests / timing are paused.\nTurn it off in Settings when you're done.",
    "【本机已安装的应用(来自开始菜单与注册表)】\n{list}": "[Apps installed on this computer (from the Start menu and registry)]\n{list}",
    "{domain} —— {visits} 次": "{domain} — {visits} visits",
    "【最近 {days} 天浏览器访问最多的网站(只有域名与次数,无具体网址)】\n{list}": "[Most-visited websites in the last {days} days (domains and counts only, no full URLs)]\n{list}",
    "Adapter:离线时直接禁用物理网卡.Proxy:网卡保持开启,由本地代理按 Rules 页的黑白名单放行 / 拦截.": "Adapter: disables the physical network adapters while offline. Proxy: adapters stay on and a local proxy allows / blocks by the lists on the Rules page.",
    "仅 Proxy 断网方式下有效.黑名单模式:默认放行,只拦名单内.白名单模式:默认拦截,离线只放行名单内,联网会话中全放行.": "Only applies to the Proxy method. Blacklist: allow by default, block only listed items. Whitelist: block by default; while offline only listed items pass, and everything passes during an online session.",
    # ---- Statistics: 专注计时 ----
    "⏱  专注计时": "⏱  Focus timer",
    "专注": "Focus",
    "休息": "Break",
    "空白": "Idle",
    "今天": "Today",
    "尚未到来": "Not yet",
    "专注 {s} 分 · 休息 {b} 分 · 空白 {e} 分": "Focus {s} min · Break {b} min · Idle {e} min",
    "本次专注 {m:.1f} 分钟,开始休息 {t}.": "Focused for {m:.1f} min; your {t} break starts now.",
    # ---- 休息时间倍率 / 借贷过多的提醒 ----
    "休息时间倍率": "Break time multiplier",
    "计时器给出的建议休息时长乘以这个倍率;之前暂停休息结转的时间不受影响.": "The suggested break length from the timer is multiplied by this; time carried over from paused breaks is not affected.",
    "⚡ 这一次修改免等待": "⚡ next change is instant",
    "{label} 已立即生效(这一次免等待已用掉).": "{label} applied immediately (the one-time instant change is now used).",
    "💳  借得有点多了": "💳  That's a lot of borrowing",
    "明天的联网额度已经借掉了 {pct} ({used} / {limit}).": "You have already borrowed {pct} of tomorrow's network quota ({used} / {limit}).",
    "借得这么多,也许是休息不够.不妨在 设置 → 计时器 里调高「休息时间倍率」.": "Borrowing this much may mean you're not resting enough. Consider raising the \"Break time multiplier\" in Settings → Timer.",
    "另外,下一次修改「每日联网额度」会立即生效,不必等 48 小时.": "Also, your next change to the daily network quota will apply immediately, without the 48-hour wait.",
    "去设置": "Open settings",
    # ---- Timer: 两个按钮 / 连点领休息时间 ----
    "☕  开始休息": "☕  Start break",
    "■  结束专注": "■  End focus",
    "积攒的休息时间 {c}:下次休息时自动加上,也可以按 [开始休息] 直接使用.": "Saved break time {c}: added to your next break automatically, or click [Start break] to use it now.",
    "还没有积攒的休息时间.先专注一轮吧.": "No saved break time yet. Do a focus round first.",
    "开始休息 {t}(用的是积攒的休息时间).": "Starting a {t} break (from your saved break time).",
    "这一周的 {h} 已经领完了,下周一再来.": "You've already claimed this week's {h}. Come back next Monday.",
    "已加到这次休息里.": " Added to the current break.",
    "已存入积攒的休息时间,可以按 [开始休息] 使用.": " Saved to your break time; click [Start break] to use it.",
    "获得 {t} 休息时间.": "You got {t} of break time.",
    "☕  我累了": "☕  I'm tired",
    "☕  我累了 ({i})": "☕  I'm tired ({i})",
    "☕  本周已领完": "☕  Used up this week",
    "本周还能领 {left}.": "{left} left to claim this week.",
    "这么想休息,也许是真的累了.休息不需要理由.": "If you want a break this badly, you may really be tired. Rest doesn't need a reason.",
    "休息已暂停.\n这次不打折,剩余 {left} 全部留给下次休息.": "Break paused.\nNo reduction this time: all {left} left goes to your next break.",
    "这次休息含领到的时间:可以随时暂停(联网时也可以),剩余时间不打折.": "This break includes claimed time: you can pause it any time (even while online), and the rest is kept in full.",
    "这次休息可以随时暂停(联网时也可以),剩余时间不打折.": "You can pause this break any time (even while online); the rest is kept in full.",
    "下一次休息可以随时暂停(联网时也可以),剩余时间不打折.": "Your next break can be paused any time (even while online); the rest is kept in full.",
    # ---- 第一次打开 / 配置期 / 重置 ----
    "🔄  Reset": "🔄  Reset",
    "🔄  重置": "🔄  Reset",
    "输入 RESET 以确认": "Type RESET to confirm",
    "🔄  重置并清除数据": "🔄  Reset & erase data",
    "这将永久删除全部数据,所有设置恢复默认值,程序会重新打开.\n\n不可撤销.继续吗?": "This will permanently erase ALL data, restore every setting to its default and reopen OIT.\n\nThis cannot be undone. Continue?",
    "重置确认": "Confirm reset",
    "👋  欢迎使用 OIT": "👋  Welcome to OIT",
    "OIT帮你把上网集中起来:联网要先申请,等过冷静期才连上,每天有额度.": "OIT helps you batch your time online: you request network access, it connects after a cooldown, and there's a daily quota.",
    "另有专注计时器、整点记录和统计,帮你看清时间花在哪里.": "There's also a focus timer, an hourly log and statistics to show where your time goes.",
    "接下来{h}小时是配置期:所有设置和名单的修改都立即生效,请趁这段时间按自己的习惯调好.": "The next {h} hours are a setup period: every change to settings and lists applies immediately, so use this time to tune things to your habits.",
    "配置期结束后,每次修改都要等 48 小时才生效.": "After the setup period, each change takes 48 hours to apply.",
    "调好了,可以在 设置 → 基本设置 里提前结束配置期.": "Once you're done, you can end the setup period early in Settings → Basic.",
    "开始使用": "Get started",
    "配置期已结束.之后的修改都要等 48 小时才生效.": "The setup period has ended. From now on, changes take 48 hours to apply.",
    "⏳  配置期结束了": "⏳  Setup period is over",
    "从现在起,设置和名单的修改都要等 48 小时才生效.": "From now on, changes to settings and lists take 48 hours to apply.",
    "配置期内:名单的所有改动立即生效.": "Setup period: all list changes apply immediately.",
    "⏳  配置期": "⏳  Setup period",
    "结束配置期": "End setup period",
    "还剩 {h} 小时 {m} 分.": "{h} h {m} min left.",
    "结束配置期后,设置和名单的每次修改都要等 48 小时才生效.\n不能撤销.确定结束吗?": "After the setup period ends, each change to settings and lists takes 48 hours to apply.\nThis can't be undone. End it now?",
    "⚡ 配置期内即时": "⚡ instant (setup period)",
    # ---- Timer: 休息结束后的提醒 ----
    "⏱  该开始下一轮了": "⏱  Time for the next round",
    "休息结束已经 {t} 了,还没有开始下一轮专注.": "Your break ended {t} ago and the next focus round hasn't started yet.",
    # ---- 作者的话 (MECHANICS.md 里的风味文本) ----
    "在设计预期上 只要不是有绝对的正当理由 应该很少有改变能坚持过48h的等待期.\n这是一个理智与本能的抗争的常见结果.\n这个软件的一个理念就是放大理智优势,保留本能空间.":
        "By design, unless there's a truly good reason, few changes should survive a 48-hour wait.\nThat's the usual outcome when reason wrestles with impulse.\nOne idea behind this app: amplify reason's advantage, and leave room for impulse.",
    "'放松'方向的改变会被限制,是在希望未来的某一刻,理智只需要占据短暂的上风,就能阻止这个进程.\n为什么'收紧'也需要限制?作者希望用户不要竭泽而渔.你可能想到多的一个小时学习时间有多有价值 但是可能想不到少的一个小时休息时间会对心理健康有多大的压力.所以请在这一段时间好好考虑少的时间/禁用某些关键网站会对你的生活有什么影响.":
        "Loosening changes are held back in the hope that, at some future moment, reason only needs to win for a short while to stop the process.\nWhy hold back tightening too? The author hopes you won't drain the pond to catch the fish. You may see how valuable one more hour of study is, but not how much pressure one less hour of rest puts on your mental health. So use this time to think about how less time, or blocking certain key sites, would affect your life.",
    "你们贴心的作者已经考虑到了戒断反应和设置参数的资料查询需要,所以默认是放行的.\n在完成初始设置后,各项设置的修改限制才会生效.\n不过作者更喜欢用Adapter模式.":
        "Your thoughtful author has already considered withdrawal symptoms and the need to look things up while configuring, so everything is allowed by default.\nThe limits on changing settings only take effect after the initial setup.\nThat said, the author prefers Adapter mode.",
    "学的时间越长得到的休息时间越长.请尽量长时间地专注.": "The longer you study, the more break time you earn. Try to stay focused as long as you can.",
    "不要勉强.": "Don't push yourself.",
    "就这样回到一切之初,修正错误的抉择.": "And so, back to the very beginning, to correct the wrong choice.",
    # ---- 专注中: 还在吗 / 异常退出后恢复 ----
    "⏱  还在专注吗?": "⏱  Still focusing?",
    "已经专注 {t} 了.": "You've been focusing for {t}.",
    "请在{at}之前关掉这个窗口.否则专注会自动结束,没有确认的这一段只按×{p:g}计入.": "Close this window before {at}. Otherwise focus ends automatically and the unconfirmed stretch only counts at ×{p:g}.",
    "还在,继续专注": "Still here, keep going",
    "⏹  专注已自动结束": "⏹  Focus ended automatically",
    "提醒窗{n}分钟内没有被关掉,专注已在{at}自动结束.": "The reminder wasn't closed within {n} minutes, so focus ended automatically at {at}.",
    "从{since}起没有确认的{seg}只按×{p:g}计入,这次专注共计入{m:.1f}分钟.": "The unconfirmed {seg} since {since} only counts at ×{p:g}; this session counts {m:.1f} minutes in total.",
    "对应的休息时间 {t} 已存入积攒的休息时间.": "The matching break time {t} has been added to your saved break time.",
    "上次专注时程序退出了.已接着计时(从 {at} 开始).": "OIT closed during your last focus session. The timer has resumed (started at {at}).",
    "上次专注时程序退出了,专注记到 {at} 为止: 计入 {m:.1f} 分钟.": "OIT closed during your last focus session. It was recorded up to {at}: {m:.1f} minutes.",
    "上次专注时程序退出了,当时\"还在吗\"提醒已经过了期限,专注按{at}自动结束计算.": "OIT closed during your last focus session after the \"still focusing?\" deadline had passed, so it counts as ending automatically at {at}.",
    "⏱  上次的专注已记录": "⏱  Last focus session recorded",
    "▶  开始专注": "▶  Start focusing",
    "知道了": "Got it",
    # ---- Settings: 星期倍率 ----
    "星期倍率": "Weekdays",
    "周一联网倍率": "Monday quota multiplier",
    "周二联网倍率": "Tuesday quota multiplier",
    "周三联网倍率": "Wednesday quota multiplier",
    "周四联网倍率": "Thursday quota multiplier",
    "周五联网倍率": "Friday quota multiplier",
    "周六联网倍率": "Saturday quota multiplier",
    "周日联网倍率": "Sunday quota multiplier",
    "今天的联网倍率 ×{m}: 每日额度 {base} → 今天 {quota}": "Today's quota multiplier ×{m}: daily quota {base} → today {quota}",
    # ---- Settings: 按模块分页 ----
    "基本设置": "Basic",
    "计时器": "Timer",
    "联网": "Network",
    "规则": "Rules",
    "整点记录": "Hour Log",
    "窗口": "Windows",
    "提交": "Submit",
    "💾 保存本页修改": "💾 Save this page",
    "⚡ 即时生效": "⚡ instant",
    "⚡ 开发者模式: 即时": "⚡ instant (developer mode)",
    "{label}: 请填写数字.": "{label}: please enter a number.",
    "{label} 允许的范围是 {rng}.": "{label} must be within {rng}.",
    "计时单步上限": "Max seconds per tick",
    "快速访问消耗倍率": "Quick access cost multiplier",
    "紧急借贷偿还倍率": "Loan repayment multiplier",
    "休息中冷静期倍率": "Cooldown multiplier on break",
    "暂停休息结转比例": "Paused-break carry-over rate",
    "整点记录补填时限": "Hour log fill-in window",
    "每天最多能联网多久.": "How long you can be online each day.",
    "提出申请后等多久才真的联网.想立刻联网请用快速访问.": "How long to wait after a request before going online. Use quick access to go online right away.",
    "离线时每隔多久强制复查并重新断网.越小越难绕开,但更频繁调用系统命令.": "How often to re-check and re-apply the cut-off while offline. Smaller is harder to bypass but calls system commands more often.",
    "联网计时每一步最多计入多少秒;电脑睡眠或卡顿后醒来,不会一次计入一大段.": "The most seconds counted per timer step, so waking from sleep or a freeze doesn't count a large chunk at once.",
    "快速访问免冷静期,每联网 1 分钟消耗多少分钟今日额度.": "Quick access skips the cooldown; each online minute costs this many minutes of today's quota.",
    "今天借 1 分钟额度,明天要扣多少分钟.": "For each minute borrowed today, this many minutes come off tomorrow.",
    "休息倒计时中提交的普通申请,若时长不超过剩余休息时间,冷静期乘以这个倍率.": "A normal request made during a break, if it fits within the break time left, has its cooldown multiplied by this.",
    "暂停休息(或关闭程序)时,剩余休息时间按这个比例计入下一次休息.": "When a break is paused (or the program closes), this share of the remaining break goes to the next one.",
    "整点过后多久之内还能补填;超时自动记为「超时自动记录内容」.": "How long after each hour you can still fill it in; after that it is filled with the auto-fill text.",
    # ---- window_guard (任务栏窗口数上限) ----
    "任务栏窗口数上限": "Taskbar window limit",
    "窗口数上限": "Max windows",
    "任务栏上最多同时开着几个窗口;超过时一次随机关掉多出来的.": "How many windows may be open on the taskbar at once; any extra are closed at random.",
    "每 30 秒数一次任务栏上的窗口,超过「窗口数上限」就随机关掉多出来的.": "Counts the taskbar windows every 30 seconds and closes random extras beyond \"Max windows\".",
    # ---- 窗口使用时间统计 ----
    "窗口使用时间统计": "Window time tracking",
    "每 10 秒看一次当前在前台的程序,把这 10 秒记给它;桌面,文件资源管理器和命令行窗口记为空白.结果在 Statistics 页的「窗口」.": "Every 10 seconds, checks which program is in the foreground and credits it with those 10 seconds; the desktop, File Explorer and command-line windows count as idle. See the \"Windows\" tab on the Statistics page.",
    "🪟  窗口": "🪟  Windows",
    "未知程序": "Unknown program",
    "…以及另外 {n} 项": "…and {n} more",
    "任务栏上有 {n} 个窗口,超过上限 {x} 个,随机关闭了 {k} 个:\n{titles}": "{n} windows on the taskbar, more than the limit of {x}. Closed {k} at random:\n{titles}",
    # ---- uninstall.py ----
    "PAC 脚本 {url}": "PAC script {url}",
    "未使用代理": "no proxy",
    "① 结束正在运行的 OIT…": "① Stopping running OIT instances…",
    "   结束失败: {name} (PID {pid})": "   Could not stop: {name} (PID {pid})",
    "   已结束: {name} (PID {pid})": "   Stopped: {name} (PID {pid})",
    "   没有正在运行的 OIT.": "   OIT is not running.",
    "② 还原系统代理…": "② Restoring the system proxy…",
    "   已按备份还原: {s}": "   Restored from backup: {s}",
    "   代理指向 OIT 但没有可用的备份,已关闭代理: {s}": "   The proxy pointed at OIT with no usable backup, so it was turned off: {s}",
    "   系统代理没有被 OIT 占用: {s}": "   The system proxy is not held by OIT: {s}",
    "   系统代理仍指向 OIT.": "   The system proxy still points at OIT.",
    "   还原失败: {e}": "   Restore failed: {e}",
    "③ 启用物理网卡…": "③ Enabling physical network adapters…",
    "   已启用: {name}": "   Enabled: {name}",
    "   启用失败: {name}": "   Could not enable: {name}",
    "   没有被禁用的物理网卡.": "   No physical adapter is disabled.",
    "④ 删除数据…": "④ Erasing data…",
    "   删不掉 (可能被占用): {p}": "   Could not delete (possibly in use): {p}",
    "   数据已全部删除.": "   All data erased.",
    "⑤ 删除程序文件夹…": "⑤ Removing the program folder…",
    "   关闭本窗口后自动删除: {p}": "   It will be deleted after this window closes: {p}",
    "   如果文件夹没有完全消失,关掉所有打开着它的窗口 (资源管理器 / 终端 / 编辑器) 后手动删除.": "   If the folder does not disappear completely, close every window using it (Explorer / terminal / editor) and delete it by hand.",
    "   这里看起来不是 OIT 的程序文件夹,没有删除: {p}": "   This does not look like the OIT program folder, so it was not deleted: {p}",
    "✔ 网络限制已全部解除.": "✔ All network restrictions removed.",
    "⚠ 有几项没能完成,见上方.可以再运行一次卸载程序.": "⚠ Some steps did not finish (see above). You can run the uninstaller again.",
    "卸载 {app}": "Uninstall {app}",
    "🗑  卸载": "🗑  Uninstall",
    "解除网络限制,并清除本程序在这台电脑上留下的东西.": "Remove the network restrictions and clean up what this program left on this computer.",
    "当前状态": "Current state",
    "正在检测…": "Checking…",
    "解除网络限制 (必做)": "Remove network restrictions (always)",
    "结束 OIT,还原系统代理,启用网卡.": "Stop OIT, restore the system proxy, enable network adapters.",
    "删除全部数据 (必做)": "Erase all data (always)",
    "学习记录,整点记录,统计,名单,设置,AI 配置等.无法撤销.": "Study log, hour log, statistics, lists, settings, AI config and so on. Cannot be undone.",
    "同时删除程序文件夹": "Also delete the program folder",
    "(这里看起来不是 OIT 的程序文件夹,不能删除)": "(This does not look like the OIT program folder; it cannot be deleted)",
    "输入 {w} 以确认": "Type {w} to confirm",
    "检测失败: {e}": "Check failed: {e}",
    "• 正在运行的 OIT: {s}": "• Running OIT: {s}",
    "• 正在运行的 OIT: 无": "• Running OIT: none",
    "• 系统代理: {s} (指向 OIT)": "• System proxy: {s} (points at OIT)",
    "• 系统代理: {s}": "• System proxy: {s}",
    "• 有 OIT 接管前的系统代理备份,卸载时按它还原": "• A backup of the proxy settings from before OIT exists; it will be restored",
    "• 被禁用的物理网卡: {s}": "• Disabled physical adapters: {s}",
    "• 被禁用的物理网卡: 无": "• Disabled physical adapters: none",
    "• 数据目录: {p} ({size})": "• Data folder: {p} ({size})",
    "• 数据目录: 不存在": "• Data folder: not present",
    "• 还有旧版本留下的文件,删除数据时一并删除": "• Files from an older version remain; they are erased with the data",
    "⚠ 这是一个 git 仓库: 没有推送的提交和修改会一起丢失.": "⚠ This is a git repository: unpushed commits and changes will be lost too.",
    "出错了: {e}": "Error: {e}",
}


def set_language(lang: str):
    global _current
    with _lock:
        _current = "en" if str(lang).lower().startswith("en") else "zh"


def get_language() -> str:
    return _current


def is_en() -> bool:
    return _current == "en"


def language_label(lang: str = None) -> str:
    target = lang or _current
    for code, label in LANGUAGES:
        if code == target:
            return label
    return target






_template_lock = threading.RLock()
_templates = []


def refresh_templates():
    import re
    compiled = []
    for zh_key, en_value in EN.items():
        m = re.search(r'\{(\w+)(?::[^}]*)?\}', zh_key)
        if not m:
            continue
        parts = re.split(r'\{(\w+)(?::[^}]*)?\}', zh_key)
        pattern, names = "", []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                pattern += re.escape(part)
            else:
                names.append(part)
                pattern += "(.+?)"
        compiled.append((re.compile("^" + pattern + "$"), names, zh_key, en_value))
    with _template_lock:
        _templates[:] = compiled


def _match_template(text: str):
    if not isinstance(text, str) or '{' in text:
        return None
    with _template_lock:
        candidates = list(_templates)
    for pattern, names, _zh_key, en_value in candidates:
        m = pattern.match(text)
        if not m:
            continue
        try:
            return en_value.format(**dict(zip(names, m.groups())))
        except (KeyError, IndexError, ValueError, AttributeError):
            continue
    return None


refresh_templates()


def tr(zh: str, **kwargs) -> str:
    if not is_en():
        text = zh
    elif zh in EN:
        text = EN[zh]
    else:
        matched = _match_template(zh)
        if matched is not None:
            return matched
        text = zh
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError, AttributeError):
            return text
    return text


def init_from_config():
    set_language(getattr(config, "LANGUAGE", DEFAULT_LANGUAGE))
