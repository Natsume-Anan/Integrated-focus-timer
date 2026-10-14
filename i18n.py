

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
    "开始工作 → 结束 → 休息": "Start working → finish → take a break",
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
    "☕ 休息中提交申请,冷静期 ×{r:g}: 只需 {t}": "☕ On break: requests use a {r:g}x cooldown (only {t})",
    "(申请时长不超过剩余休息 {left} 时生效)": " (only if the requested time fits within the {left} of break left)",
    "🌐  联网申请": "🌐  Network Access",
    "申请 → {min} 分钟冷静期 → 联网 → 到点自动断网": "Request → {min} min cooldown → online → auto cut-off",
    "离线": "Offline",
    "⚡ 快速访问免冷静期(×{a:g})  ·  💳 借 1 分钟扣明天 {b:g} 分钟": "⚡ quick access skips the wait ({a:g}x)  ·  💳 borrow 1 min, repay {b:g} min tomorrow",
    "⚡  快速访问(×{a:g})": "⚡  Quick access ({a:g}x)",
    "💳  紧急借贷": "💳  Emergency loan",
    "⚡  改为快速访问(×{a:g})": "⚡  Switch to quick access ({a:g}x)",
    "快速访问": "Quick access",
    "紧急借贷": "Emergency loan",
    "快速访问跳过冷静期立刻联网,额度按 ×{a:g} 消耗.\n\n联网: {m} 分钟\n消耗: {cost} 今日额度\n\n确定吗?": "Quick access skips the cooldown and goes online now; quota is used at {a:g}x.\n\nOnline: {m} min\nCost: {cost} of today's quota\n\nContinue?",
    "紧急借贷不会联网,只会给今天加额度;代价是明天扣 {b:g} 倍.\n借到的额度今天用不完也不退.\n\n今天额度: +{add}\n明天额度: -{cost}\n\n确定吗?": "An emergency loan does not go online; it only adds quota for today, and tomorrow pays {b:g}x.\nBorrowed quota left unused today is not refunded.\n\nToday's quota: +{add}\nTomorrow's quota: -{cost}\n\nContinue?",
    "今天额度 +{add}.": "Today's quota +{add}.",
    "立刻结束冷静期并联网?\n\n联网: {m} 分钟\n消耗: {cost} 今日额度(×{a:g})\n\n确定吗?": "End the cooldown and go online now?\n\nOnline: {m} min\nCost: {cost} of today's quota ({a:g}x)\n\nContinue?",
    "⚡ 可改为快速访问立刻联网:消耗 {cost} 今日额度(×{a:g}).": "⚡ Switch to quick access to go online now: costs {cost} of today's quota ({a:g}x).",
    "⚡ 快速访问 —— 额度按 ×{a:g} 消耗,归零自动断网.": "⚡ Quick access — quota is used at {a:g}x. Network is cut automatically at zero.",
    "⚡ 快速访问 {m} 分钟:立刻联网,消耗 {cost} 今日额度.": "⚡ Quick access for {m} min: online now, costs {cost} of today's quota.",
    "⚡ 快速访问:跳过冷静期,额度按 ×{a:g} 消耗;最多 {cap}.": "⚡ Quick access: skips the cooldown, quota used at {a:g}x; up to {cap}.",
    "💳 明天的额度已经借完了.": "💳 Tomorrow's quota is already fully borrowed.",
    "💳 借 {m} 分钟:今天额度 +{add},明天额度 -{cost}.最多可借 {cap}.": "💳 Borrow {m} min: today's quota +{add}, tomorrow's quota -{cost}. You can borrow up to {cap}.",
    "💳 紧急借贷:今天额度 +1 分钟,明天额度 -{b:g} 分钟;最多可借 {cap}.": "💳 Emergency loan: +1 min today costs {b:g} min tomorrow; up to {cap}.",
    "今日已用: {used} / {total}     今日剩余: {left}     可快速访问: {quick}": "Used today: {used} / {total}     Left today: {left}     Quick access: {quick}",
    "今天已借 {bonus},明天将扣 {cost}(明天剩余 {left})": "Borrowed today: {bonus}; tomorrow pays {cost} (tomorrow left: {left})",
    "今天要先还昨天借的 {debt}": "Repaying yesterday's loan today: {debt}",
    "联网中": "Online",
    "冷静期中 —— 仍可取消": "Cooldown — you can still cancel",
    "今天的额度已用完.": "Today's quota is used up.",
    "在下面提交申请,冷静期结束后自动联网.": "Submit a request below. It starts after the cooldown.",
    "已申请 {m} 分钟 · {at} 联网": "Requested {m} min · goes online at {at}",
    "本次会话剩余时间,归零自动断网.": "Session time left. Network is cut automatically at zero.",
    "分钟": "Minutes",
    "理由": "Reason",
    "📨  提交申请(需冷静期)": "📨  Request (cooldown)",
    "分钟数必须是整数.": "Minutes must be an integer.",
    "请写一个申请理由.": "Please write a reason for this request.",
    "✕  取消申请": "✕  Cancel request",
    "■  结束本次会话": "■  End session",
    "📝  整点记录": "📝  Hour Log",
    "整点记录已关闭 —— 不响铃,不自动补记,也不记录任何内容.": "Hour log is OFF — no chime, no auto fill, nothing is recorded.",
    "每次提示音后填写上一小时做了什么;每行时间是该小时的结束时刻(00:00 = 昨天 23:00–24:00);": "After each chime, note what you did in the last hour. Each row is labelled by the hour it ends (00:00 = yesterday 23:00–24:00).",
    "✎ 填写格式:一小时内做了多项活动时用 / 连接,如「学习/吃饭」(统计时均分这一小时).": "✎ Format: join several activities in one hour with /, e.g. \"study/lunch\" (the hour is split evenly in Statistics).",
    "多个理由用 / 连接,如「查资料/下载课件」": "Join several reasons with /, e.g. \"research/download slides\"",
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
    "整点记录里每一项活动的总时间.一小时写了多项(用 / 连接)时,这一小时均分给每一项.": "Total time of each activity in the hour log. An hour with several activities (joined by /) is split evenly among them.",
    "每个联网理由的实际联网时间,不计快速访问的倍数.一次申请写了多个理由(用 / 连接)时均分.": "Actual online time per request reason, ignoring the quick-access multiplier. A request with several reasons (joined by /) is split evenly.",
    "留空 {h} 小时 → 自动记为「{text}」.": "Left blank for {h} h → \"{text}\".",
    "(开关在 Settings 页,改动 48 小时后生效)": "(the switch lives on the Settings page; changes apply after 48 h)",
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
    "界面语言": "Language",
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
    "即时生效.可粘贴本地 .wav 的完整路径.": "Instant. You can paste the full path of a local .wav file.",
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
    "{label} 首次修改,已立即生效;以后的修改需要等待冷静期.": "{label}: first change applied immediately; later changes must wait out the cooling-off period.",
    "{label} 已恢复到当前生效值,排队中的改动已取消.": "{label} reverted to the active value; the queued change was cancelled.",
    "{label} 与当前生效值相同.": "{label} already matches the active value.",
    "{label} 已提交,将于 {at}.": "{label} submitted; applies at {at}.",
    "选择提示音": "Choose a chime",
    "WAV 音频": "WAV audio",
    "选择 .wav…": "Choose .wav…",
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
    "🗑  卸载": "🗑  Uninstall",
    "恢复网络并删除本程序留下的全部内容.": "Restore your network and remove everything this app stored.",
    "卸载次数": "Times uninstalled",
    "从未卸载过.": "Never uninstalled before.",
    "上次卸载: {when}": "Last uninstall: {when}",
    "⚠  警告:这会永久删除全部数据": "⚠  Warning: this permanently erases ALL data",
    "输入 UNINSTALL 以确认": "Type UNINSTALL to confirm",
    "同时删除本程序文件": "Also delete this program file",
    "🗑  卸载并清除数据": "🗑  Uninstall & erase data",
    "这将永久删除全部数据并恢复网络.\n\n不可撤销.继续吗?": "This will permanently erase ALL data and restore your network.\n\nThis cannot be undone. Continue?",
    "\n程序文件已删除.": "\nProgram file deleted.",
    "\n无法删除程序文件,请手动移除.": "\nCould not delete the program file; please remove it manually.",
    "提示": "Notice",
    "卸载确认": "Confirm uninstall",
    "断网方式": "Cut-off method",
    "禁用网卡 (Adapter)": "Disable adapters (Adapter)",
    "本地代理过滤 (Proxy)": "Local filtering proxy (Proxy)",
    "🛡  规则": "🛡  Rules",
    "黑名单任何时候都拦;离线时只放行白名单;联网时除黑名单外全部放行.": "Blacklist is always blocked; offline only the whitelist passes; online everything except the blacklist passes.",
    "去设置里切换断网方式": "Switch cut-off method in Settings",
    "运行中": "running",
    "未运行": "not running",
    "联网中:除黑名单外全部放行.": "Online: everything except the blacklist passes.",
    "离线:只放行白名单,其余一律拦截.": "Offline: only the whitelist passes, everything else is blocked.",
    "当前是 Adapter 模式 —— 规则已保存,但暂未启用.": "Adapter mode is active — rules are saved but not enforced.",
    "在 Settings 里把「断网方式」改成 Proxy 后,这些规则才会生效.": "Set \"Cut-off method\" to Proxy in Settings to enforce these rules.",
    "Proxy 模式 · 本地代理 127.0.0.1:{port} · {run}": "Proxy mode · local proxy 127.0.0.1:{port} · {run}",
    "已放行 {a} 次 · 已拦截 {b} 次(本次运行)": "Allowed {a} · Blocked {b} (this run)",
    "✅  白名单 · 网站": "✅  Whitelist · Sites",
    "✅  白名单 · 应用": "✅  Whitelist · Apps",
    "⛔  黑名单 · 网站": "⛔  Blacklist · Sites",
    "⛔  黑名单 · 应用": "⛔  Blacklist · Apps",
    "离线时也放行.写域名即可,子域名自动包含.": "Passes while offline. Enter a domain; subdomains are included.",
    "离线时也放行这个程序的全部联网.写 exe 名,如 code.exe.": "Passes this program's traffic while offline. Enter an exe name, e.g. code.exe.",
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
    "开发者模式:名单改动立即生效.": "Developer mode: list changes apply immediately.",
    "第一次加入名单的网站 / 应用立即生效;删除,以及删掉后再次加入,都要等 48 小时.": "A site / app added to a list for the first time applies immediately; removing, and adding back something removed before, both wait 48 hours.",
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
    "黑名单模式:默认放行,只拦名单里的网站 / 应用.": "Blacklist mode: allowed by default; only the listed sites / apps are blocked.",
    "白名单模式:默认拦截,离线时只放行名单里的网站 / 应用;联网会话中全部放行.": "Whitelist mode: blocked by default; offline only the listed sites / apps pass; during an online session everything passes.",
    "只拦黑名单里的网站 / 应用,其余放行.": "Only blacklisted sites / apps are blocked; the rest passes.",
    "禁止访问.写域名即可,子域名自动包含.": "Forbidden. Enter a domain; subdomains are included.",
    "禁止这个程序联网.写 exe 名,如 steam.exe.": "Forbids this program's traffic. Enter an exe name, e.g. steam.exe.",
    "待生效: 切换到{mode}   ·   {when}": "Pending: switch to {mode}   ·   {when}",
    "联网中:全部放行.": "Online: everything passes.",
    "⚙ 模型": "⚙ Model",
    "🤖 AI 建议": "🤖 AI suggestions",
    "AI 模型设置": "AI model settings",
    "Base URL": "Base URL",
    "模型": "Model",
    "接口协议": "API protocol",
    "API Key": "API Key",
    "显示 Key": "Show key",
    "API Key 以明文保存在本机应用数据目录,不会随名单或日志输出.": "The API key is stored as plain text in the local app data folder and is never written to lists or logs.",
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
    "第一次加入名单的条目立即生效;曾经加入过又删掉的,再次加入要等冷静期.": "Items added to a list for the first time apply immediately; anything that was on it before and got removed waits out the cool-down.",
    "没有选中任何条目.": "Nothing selected.",
    "已提交;其中曾经加入过的条目要等冷静期后生效.": "Submitted; items that were on the list before take effect after the cool-down.",
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
    "全部数据已清除,网络已恢复.\n累计卸载次数: {n}": "All data cleared; network restored.\nTimes uninstalled: {n}",
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
    "最近 7 天计时器的专注与休息.每根条是一个小时,按比例分成专注、休息与空白;鼠标停在条上可查看分钟数.": "Focus and break time from the timer over the last 7 days. Each bar is one hour, split into focus, break and idle time; hover over a bar to see the minutes.",
    # ---- Settings: 基本设置 / 具体设置 ----
    "基本设置": "Basic",
    "具体设置": "Details",
    "提交": "Submit",
    "💾 保存本页修改": "💾 Save this page",
    "带 ⚡ 标记的项修改后立即生效;其余需等待 48 小时.": "Items marked ⚡ apply immediately; the rest take 48 hours.",
    "⚡ 即时生效": "⚡ instant",
    "⚡ 首次修改免等待": "⚡ first change is instant",
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
