

import sys
import tkinter as tk

from config import is_admin, elevate, relaunch
from app import BreakTimerApp


def main():
    if sys.platform == "win32" and not is_admin():
        elevate()
        sys.exit(0)

    root = tk.Tk()
    app = BreakTimerApp(root)
    root.mainloop()
    if getattr(app, "restart_requested", False):   # 重置后: 以全新状态重新打开
        relaunch()


if __name__ == "__main__":
    main()
