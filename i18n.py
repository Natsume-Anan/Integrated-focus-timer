

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
    "开启": "ON",
    "关闭_状态": "OFF",
    "⏱  Timer": "⏱  Timer",
    "🌐  Network": "🌐  Network",
    "🛡  Rules": "🛡  Rules",
    "📝  Hour Log": "📝  Hour Log",
    "📅  Calendar": "📅  Calendar",
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
    "🌐  联网申请": "🌐  Network Access",
    "申请 → {min} 分钟冷静期 → 联网 → 到点自动断网": "Request → {min} min cooldown → online → auto cut-off",
    "⚡ 紧急贷款免冷静期 (今天 ×{a:g} / 预支明天 ×{b:g})": "⚡ emergency loan skips the wait ({a:g}x today / {b:g}x borrowed)",
    "离线": "Offline",
    "联网中": "Online",
    "冷静期中 —— 仍可取消": "Cooldown — you can still cancel",
    "今天的额度已用完.": "Today's quota is used up.",
    "在下面提交申请,冷静期结束后自动联网.": "Submit a request below. It starts after the cooldown.",
    "已申请 {m} 分钟 · {at} 联网": "Requested {m} min · goes online at {at}",
    "本次会话剩余时间,归零自动断网.": "Session time left. Network is cut automatically at zero.",
    "分钟": "Minutes",
    "理由": "Reason",
    "📨  提交申请(需冷静期)": "📨  Request (cooldown)",
    "⚡  紧急贷款": "⚡  Emergency loan",
    "分钟数必须是整数.": "Minutes must be an integer.",
    "请写一个申请理由.": "Please write a reason for this request.",
    "✕  取消申请": "✕  Cancel request",
    "■  结束本次会话": "■  End session",
    "⚡  立刻联网(付费)": "⚡  Go now",
    "紧急贷款": "Emergency loan",
    "紧急贷款会跳过冷静期立刻联网,额度按「今天 ×{a:g}、预支明天 ×{b:g}」计费.\n\n申请: {m} 分钟\n实际放行: {grant}\n计费: {total} 额度(今天 {today} ×{a:g} + 预支明天 {borrowed} ×{b:g})\n\n确定吗?": "An emergency loan skips the cooldown and goes online immediately.\nQuota is billed at today ×{a:g} / borrowed ×{b:g}.\n\nRequested: {m} min\nActually granted: {grant}\nBilled: {total} quota (today {today} ×{a:g} + borrowed {borrowed} ×{b:g})\n\nContinue?",
    "立刻结束冷静期并联网?\n\n申请: {m} 分钟\n实际放行: {grant}  ·  计费 {total} 额度\n(今天 {today} ×{a:g} + 预支明天 {borrowed} ×{b:g})\n\n确定吗?": "End the cooldown now and go online?\n\nRequested: {m} min\nGranted: {grant}  ·  Billed {total} quota\n(today {today} ×{a:g} + borrowed {borrowed} ×{b:g})\n\nContinue?",
    "⚡ 紧急贷款可立刻联网:放行 {grant}(今天额度 {today} ×{a:g} + 预支明天 {borrowed} ×{b:g})": "⚡ Loan can go online now: {grant} (today {today} ×{a:g} + borrowed {borrowed} ×{b:g})",
    "今日已用: {used} / {total}     今日剩余: {left}     含贷款: {cap}  (今天 ×{a:g}, 预支 ×{b:g})": "Used today: {used} / {total}     Left today: {left}     With loan: {cap}  (today ×{a:g}, borrowed ×{b:g})",
    "⚡ 贷款会话 —— 今天 ×{a:g}、预支 ×{b:g}.可继续使用 {left};已预支 {borrowed}": "⚡ Loan session — today ×{a:g}, borrowed ×{b:g}.  Left: {left}  (borrowed {borrowed})",
    "⚡ {m} 分钟可走紧急贷款:放行 {grant},计费 {total}(今天额度 {today} ×{a:g} + 预支明天 {borrowed} ×{b:g}).贷款上限 {cap}.": "⚡ Emergency loan for {m} min: {grant} granted, {total} billed (today {today} ×{a:g} + borrowed {borrowed} ×{b:g}). Loan cap {cap}.",
    "⚡ 今天额度已用完.贷款上限 {cap},全部预支明天(×{b:g}).": "⚡ Today's quota is used up. Loan cap {cap}, all borrowed from tomorrow (×{b:g}).",
    "⚡ 紧急贷款:跳过冷静期立刻联网;今天剩余额度按 2 倍计费,不够的部分按 3 倍预支明天的额度.": "⚡ Emergency loan skips the cooldown; today's remaining quota is billed at 2x, the shortfall is borrowed from tomorrow at 3x.",
    "今天已预支明天的额度 {borrowed}(明天剩余 {left})": "Borrowed from tomorrow today: {borrowed} (tomorrow left: {left})",
    "今天要先还昨天预支的 {debt}": "Debt from yesterday to repay today: {debt}",
    "📝  整点记录": "📝  Hour Log",
    "整点记录已关闭 —— 不响铃、不自动补记、也不记录任何内容.": "Hour log is OFF — no chime, no auto fill, nothing is recorded.",
    "只记录今天.每次提示音后填写上一小时做了什么;": "Today only. After each chime, note what you did in the last hour.",
    "留空 {h} 小时 → 自动记为「{text}」.": "Left blank for {h} h → \"{text}\".",
    "（开关在 Settings 页,改动 48 小时后生效）": "(the switch lives on the Settings page; changes apply after 48 h)",
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
    "整点记录截止小时": "Hour log cut-off hour",
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
    "即时生效。可粘贴本地 .wav 的完整路径。": "Instant. You can paste the full path of a local .wav file.",
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
    "{label} 已立即生效。": "{label} applied immediately.",
    "{label} 已恢复到当前生效值,排队中的改动已取消。": "{label} reverted to the active value; the queued change was cancelled.",
    "{label} 与当前生效值相同。": "{label} already matches the active value.",
    "{label} 已提交,将于 {at}。": "{label} submitted; applies at {at}.",
    "选择提示音": "Choose a chime",
    "WAV 音频": "WAV audio",
    "选择 .wav…": "Choose .wav…",
    "▶ 试听": "▶ Test",
    "内置三音提示音 (推荐)": "Built-in 3-tone chime (recommended)",
    "Windows 蜂鸣声 (Beep)": "Windows beep",
    "内置三音提示音": "Built-in 3-tone chime",
    "Windows 蜂鸣声": "Windows beep",
    "今天最多能联网多久。改动要 48 小时后才生效,期间仍按旧额度计算。": "How long you may be online today. Changes apply after 48 h; the old quota keeps running meanwhile.",
    "提出申请后等多久才真的联网。想立刻联网请用 Network 页的紧急贷款(今天 2 倍 / 预支明天 3 倍)。": "How long to wait after requesting before you actually go online. To go online at once, use the emergency loan on the Network page (2x today / 3x borrowed).",
    "程序启动时整点记录的初始状态;启动后仍可在 Hour Log 页直接切换。": "Initial state of the hour log when the app starts; you can still toggle it on the Hour Log page.",
    "该小时之后不再提示填写(默认 23:00–24:00 不记录)。": "No more fill-in prompts after this hour (23:00–24:00 is not logged by default).",
    "整点后一小时内没填写,就自动记成这段文字。这一项可以立即修改。": "If a slot is left blank for an hour, this text is recorded. This item can be changed immediately.",
    "离线状态下每隔多久强制复查并重新断网(越小越难被绕开,代价是更频繁调用系统命令)。": "How often, while offline, the app force-checks and cuts the network again (smaller is harder to bypass, at the cost of running system commands more often).",
    "即时生效.界面语言(中文 / English).": "Instant. Interface language (中文 / English).",
    "即时生效.整体缩放界面字号,适配不同分辨率.": "Instant. Scales all UI text for different resolutions.",
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
