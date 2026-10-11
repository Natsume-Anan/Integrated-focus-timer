

import sys
import os
import math
import threading
import tkinter as tk
from tkinter import messagebox
from datetime import timedelta


if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass


IDLE, RUNNING, READY_BREAK, ON_BREAK = range(4)


DAILY_LIMIT = 2 * 3600       
COOLDOWN = 5 * 60            
ENFORCE_EVERY = 60           
TICK_CLAMP = 30              






APP_NAME = "Obliphur's Integrated Terminal"   
OLD_APP_DIR = "mrsTimer"
FILL_WINDOW = timedelta(hours=1)              
AUTO_TEXT = "Sleeping"
HOUR_LOG_ENABLED = True                       
CHIME_WAV = ""
LOG_HOURS = 23                                
LANGUAGE = "zh"







WINDOW_W = 1180
WINDOW_H = 820
MIN_WINDOW_W = 980
MIN_WINDOW_H = 680

FONT_FAMILY = "Microsoft YaHei UI"
FONT_FAMILY_FALLBACK = "Microsoft YaHei"
FONT_MONO = "Consolas"


FONT_SIZE = {
    "h1": 22,
    "h2": 15,
    "big": 44,
    "body": 12,
    "small": 11,
    "tiny": 10,
    "nav": 13,
    "btn": 12,
    "log": 12,
}


def detect_ui_scale() -> float:
    if sys.platform != "win32":
        return 1.0
    if 'ctypes' not in globals():
        return 1.0
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        if dpi:
            return max(0.75, min(2.0, dpi / 96.0))
    except Exception:
        pass
    return 1.0


UI_SCALE = 1.0


def ui_scale() -> float:
    return UI_SCALE


def scaled(px: float) -> int:
    return int(round(px * ui_scale()))


def font(size_key: str = "body", bold: bool = False, family: str = None):
    size = FONT_SIZE.get(size_key, FONT_SIZE["body"])
    if family is None:
        family = FONT_FAMILY
    return (family, max(8, scaled(size)), "bold") if bold else (family, max(8, scaled(size)))



def dev_mode_defined() -> bool:
    if "config" not in sys.modules:
        return False
    return "DEV_MODE" in vars(sys.modules["config"])


def dev_mode_enabled() -> bool:
    if not dev_mode_defined():
        return False
    return bool(getattr(sys.modules["config"], "DEV_MODE", False))





DEFAULT_SETTINGS = {
    "DAILY_LIMIT": DAILY_LIMIT,
    "COOLDOWN": COOLDOWN,
    "HOUR_LOG_ENABLED": HOUR_LOG_ENABLED,
    "LOG_HOURS": LOG_HOURS,
    "AUTO_TEXT": AUTO_TEXT,
    "ENFORCE_EVERY": ENFORCE_EVERY,
    "CHIME_WAV": CHIME_WAV,
    "LANGUAGE": LANGUAGE,
    "FONT_SCALE": 1.0,
}


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
    if t <= 15.0:
        return t / 6.0
    elif t < 150.0:
        return (7.0 / 14850.0) * t * t + (407.0 / 1485.0) * t - (170.0 / 99.0)
    else:
        return 50.0 + (5.0 / math.log(1.2)) * math.log(t / 150.0)


def _topmost_win(title: str, message: str) -> bool:
    if 'ctypes' not in globals():
        return False
    try:
        flags = 0x00 | 0x40 | 0x10000 | 0x40000
        threading.Thread(
            target=lambda: ctypes.windll.user32.MessageBoxW(None, message, title, flags),
            daemon=True
        ).start()
        return True
    except Exception:
        return False


def show_topmost_info(title: str, message: str, parent=None):
    if sys.platform == "win32" and _topmost_win(title, message):
        return
    if parent is None:
        return
    try:
        tmp = tk.Toplevel(parent)
        tmp.attributes("-topmost", True)
        tmp.geometry("1x1+-100+-100")
        try:
            messagebox.showinfo(title, message, parent=tmp)
        finally:
            tmp.destroy()
    except Exception:
        pass


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
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]
    params = " ".join(f'"{a}"' for a in args)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)



def app_data_dir() -> str:
    root = os.path.join(
        os.environ.get('USERPROFILE', os.path.expanduser('~')),
        'AppData', 'LocalLow'
    )
    return os.path.join(root, APP_NAME)


def settings_file() -> str:
    return os.path.join(app_data_dir(), "app_settings.json")


def load_json_file(path: str, default):
    try:
        import json
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path: str, payload) -> bool:
    import json
    tmp = path + ".tmp"
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False




def ensure_builtin_chime(path: str) -> str:
    if os.path.exists(path) and os.path.getsize(path) > 44:
        return path
    try:
        import struct
        import wave
        rate = 44100
        frames = bytearray()
        for freq, ms in ((784, 200), (988, 200), (1319, 450)):
            n = int(rate * ms / 1000.0)
            for i in range(n):

                fade = min(1.0, i / (rate * 0.015), (n - 1 - i) / (rate * 0.015))
                amp = int(11000 * max(0.0, fade))
                frames += struct.pack('<h', int(amp * math.sin(2 * math.pi * freq * i / rate)))
            frames += b'\x00\x00' * int(rate * 0.04)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(frames))
        return path
    except Exception:
        return ""

