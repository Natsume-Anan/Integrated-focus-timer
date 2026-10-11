

import sys
import tkinter as tk

from config import is_admin, elevate
from app import BreakTimerApp


def main():
    if sys.platform == "win32" and not is_admin():
        elevate()
        sys.exit(0)

    root = tk.Tk()
    app = BreakTimerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
