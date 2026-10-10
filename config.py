# -*- coding: utf-8 -*-
"""
配置常量、主题颜色与通用工具函数
"""

import sys
import os
import math
import threading
import tkinter as tk
from tkinter import messagebox
from datetime import timedelta

# ── 隐藏控制台窗口 (Windows)
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

# ══════════════ 状态常量 ══════════════
IDLE, RUNNING, READY_BREAK, ON_BREAK = range(4)

# ══════════════ 联网限制配置 ══════════════
DAILY_LIMIT = 2 * 3600       
COOLDOWN = 5 * 60            
BLOCK_MODE = "adapter"       # "adapter"=禁用物理网卡(彻底) / "firewall"=防火墙拦截出站(恢复快)
ENFORCE_EVERY = 60           
TICK_CLAMP = 30              

# ══════════════ 应用信息 / 整点记录配置 ══════════════
APP_NAME = "Obliphur's Integrated Terminal"   
OLD_APP_DIR = "mrsTimer"                      # 旧文件夹名(首次启动时自动迁移数据)
FILL_WINDOW = timedelta(hours=1)              
AUTO_TEXT = "Sleeping"
HOUR_LOG_ENABLED = True                       
CHIME_WAV = ""                                # 想用自己的提示音:填 .wav 路径;留空则用内置三音提示
LOG_HOURS = 23                                

# ── 白色主题配色
COLORS = {
    "bg":           "#ffffff",
    "bg_card":      "#f8f9fa",
    "accent":       "#2563eb",
    "accent_hover": "#1d4ed8",
    "text":         "#1e293b",
    "text_dim":     "#64748b",
    "success":      "#16a34a",
    "warn":         "#d97706",
    "border":       "#e2e8f0",
    "danger":       "#dc2626",
    "danger_hover": "#b91c1c",
}


def compute_F(t: float) -> float:
    """根据专注时长计算建议休息分钟数"""
    if t <= 15.0:
        return t / 6.0
    elif t < 150.0:
        return (7.0 / 14850.0) * t * t + (407.0 / 1485.0) * t - (170.0 / 99.0)
    else:
        return 50.0 + (5.0 / math.log(1.2)) * math.log(t / 150.0)


def show_topmost_info(title: str, message: str, parent=None):
    """显示始终置顶的提示框(非阻塞,避免卡住 Tk 主循环导致联网计时暂停)"""
    if sys.platform == "win32":
        # MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST
        flags = 0x00 | 0x40 | 0x10000 | 0x40000
        threading.Thread(
            target=lambda: ctypes.windll.user32.MessageBoxW(None, message, title, flags),
            daemon=True
        ).start()
    else:
        tmp = tk.Toplevel(parent)
        tmp.attributes("-topmost", True)
        tmp.geometry("1x1+-100+-100")
        try:
            messagebox.showinfo(title, message, parent=tmp)
        finally:
            tmp.destroy()


def fmt_hm(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600}h {(sec % 3600) // 60:02d}m"


def fmt_ms(sec: float) -> str:
    m, s = divmod(max(0, int(math.ceil(sec))), 60)
    return f"{m:02d}:{s:02d}"


def is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate():
    """以管理员身份重新启动自己"""
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]
    params = " ".join(f'"{a}"' for a in args)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
