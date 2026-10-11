# Obliphur's Integrated Terminal (OIT)

> (并非集成终端...)

你可能遇到过:时间被无意义的琐事消耗/overwhelming的信息流让人感到疲惫/烦躁.本应用的核心功能即针对这一问题:

- 设定每日联网额度与联网前的冷静期,把上网压缩为集中处理,避免零散的时间浪费;
- 上网时间需提前规划,资源需及时收集;
- 附带的计时器定时提醒使用者回顾刚完成的工作,并给出建议休息时长.

如果正在准备中考 / 高考 / 考研或其他考试,该计时器搭配离线网课可较明显地降低分心的可能性.

长期使用可能改变你的生活习惯:'资源管理'的思路会逐步渗透到日常之中,稳定的本地图书馆会带来一种独特的安心感.

***

## 目录

- [⚠️ 警告](#️-警告)
- [功能一览](#功能一览)
- [配置项](#配置项)
- [运行](#运行)
- [开发](#开发)

---

## ⚠️ 警告

> 安装前请阅读本节。

- 本项目**包含 AI 生成的代码**,下文亦由 AI 生成并整理。
- 程序包含**关闭网卡等强制性断网措施**。
- **需要立即恢复网络时,请使用程序内置的 Uninstall 功能。** Uninstall 固定位于侧栏最底层。

---

## 功能一览

| 页面 | 作用 |
| --- | --- |
| **⏱ Timer** | 专注计时,实时显示建议休息时长,记录今日与昨日学习时长 |
| **🌐 Network** | 申请制联网:冷静期 → 自动放行 → 到点断网;额度不足时可用紧急贷款(今天 2 倍 / 明天 3 倍) |
| **📝 Hour Log** | 每整点提示并记录上一小时的工作内容;超时未填按设定文本补记 |
| **📅 Calendar** | 以日历形式查看每日学习时长 |
| **⚙ Settings** | 全部可调参数 |
| **🗑 Uninstall** | 恢复网络并清理数据 |

---

## 配置项

配置均在 **Settings 页**修改。**即时生效项**保存后立刻生效;**每个选项的第一次修改也立即生效**
(相当于免一次冷静期);此后的修改才进入 **48 小时冷静期**
(期间仍按旧配置运行,可随时取消;程序关闭期间照样倒计时)。

---

## 运行

- **系统**:Windows 10 / 11(断网依赖管理员权限与 PowerShell)
- **Python**:3.10 及以上
- **依赖**:仅使用标准库,无需安装第三方包

```bash
python main.py
```

程序启动时会自动申请管理员权限(断网需要)。非 Windows 平台可运行界面,但联网控制会自动跳过。

---

## 开发

```bash
python tests/test_features.py   # 功能与界面自检(系统命令全部 mock)
python tests/check_i18n.py      # i18n 静态检查
python tests/check_names.py     # 未定义名字静态检查
python tests/check_imports.py   # 未使用导入静态检查
```

各模块亦可单独自检:`python settings_manager.py`、`python net_guard.py`。

```text
Obliphur's Integrated Terminal/
├── main.py                  # 入口:申请管理员权限并启动界面
├── app.py                   # 页面编排、计时器、网络调度、界面重建、卸载
├── config.py                # 配置种子值、主题配色、DPI 与字体、设置文件读写
├── i18n.py                  # 双语对照表与 tr()
├── settings_manager.py      # 首次修改立即生效 + 之后 48 小时延后生效机制
├── net_guard.py             # 联网申请、额度账本、紧急贷款与断网
├── data_manager.py          # 学习时长、整点日志、卸载计数
├── toast.py                 # 右下角提示条与确认弹窗
├── context_collect.py       # 经用户同意后采集已安装应用与浏览器域名(供规则建议)
└── pages/                   # 各页面与共用控件
    ├── __init__.py          # 页面与控件的统一导出
    ├── widgets.py           # Switch / ScrollArea / Modal 等共用控件
    ├── calendar_page.py     # 📅 Calendar 页
    ├── hour_log_page.py     # 📝 Hour Log 页
    └── settings_page.py     # ⚙ Settings 页
```
