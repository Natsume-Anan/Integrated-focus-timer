WARNING:Including AI generated codes.

# Obliphur's Integrated Terminal

一个面向专注学习的 Windows 桌面工具，集成了：

- **专注计时器**（根据专注时长智能建议休息时间）
- **申请制联网控制**（默认断网，需申请并经过冷静期才能短暂联网）
- **整点日志**（每小时提醒并记录该时段做了什么）
- **学习时长日历**（可视化每日专注时长）

程序启动时自动以管理员权限运行（断网功能需要），并以 fail-closed 原则设计：启动、退出、异常时一律断网。

---

## 功能概览

| 模块 | 功能 |
|------|------|
| **⏱ Timer** | 开始/结束专注，实时显示建议休息时长，记录今日/昨日学习时长 |
| **🌐 Network** | 申请联网（需填写时长与原因）→ 冷静期 → 自动放行 → 额度耗尽或手动结束即断网 |
| **📝 Hour Log** | 每整点发出提示音，记录过去一小时做了什么；超时未填自动记为 `Sleeping` |
| **📅 Calendar** | 以日历形式查看每日学习时长 |
| **🗑 Uninstall** | 安全卸载：恢复网络、清理数据 |

---

## 系统要求

- **操作系统**：Windows 10 / 11（断网功能依赖 Windows 管理员权限与 PowerShell）
- **Python**：3.10+（推荐 3.11 / 3.12 / 3.13）
- **依赖**：仅使用 Python 标准库（`tkinter`、`ctypes`、`subprocess` 等），无需额外安装第三方包

> 非 Windows 平台可运行界面，但联网控制功能会自动跳过。

---

## 安装与运行

1. 解压本项目到任意目录。
2. 确保已安装 Python，并且 `python` / `pythonw` 可在命令行中使用。
3. 双击或在终端中运行：

```bash
python main.py


English version

A Windows desktop productivity tool designed for focused study sessions. It integrates:

- **Focus Timer** — tracks focus time and suggests break duration based on a smart formula
- **Request-based Network Control** — offline by default; internet access requires a request and a cooldown period
- **Hourly Log** — chimes at every hour and lets you record what you did in the past hour
- **Study Calendar** — visual overview of daily focus hours

The program always runs with administrator privileges on Windows (required for network blocking) and follows a **fail-closed** design: network is blocked on startup, exit, and any abnormal termination.

---

## Features

| Module | Description |
|--------|-------------|
| **⏱ Timer** | Start / stop focus sessions, live suggested break time, today's & yesterday's study hours |
| **🌐 Network** | Request internet access (duration + reason) → cooldown → auto-grant → auto-block when quota runs out or ended early |
| **📝 Hour Log** | Hourly chime; note what you did in the past hour. Blank entries auto-fill as `Sleeping` after the fill window |
| **📅 Calendar** | Monthly calendar view of daily study hours |
| **🗑 Uninstall** | Clean uninstall: restores network, stops all blocking/writing, optionally deletes data, records uninstall count |

---

## Requirements

- **OS**: Windows 10 / 11 (network control relies on administrator rights and PowerShell)
- **Python**: 3.10+ (recommended 3.11 / 3.12 / 3.13)
- **Dependencies**: Standard library only (`tkinter`, `ctypes`, `subprocess`, etc.). No third-party packages required.

> On non-Windows platforms the UI runs normally, but network control features are skipped.

---

## Installation & Running

1. Extract the project to any folder.
2. Make sure Python is installed and available in PATH.
3. Run:

```bash
python main.py