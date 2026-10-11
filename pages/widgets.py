

import tkinter as tk
from tkinter import ttk

import config
from config import COLORS


class Switch(tk.Canvas):

    W, H = 46, 24

    def __init__(self, master, value: bool = True, command=None, bg: str = None):
        super().__init__(
            master, width=self.W, height=self.H, bg=bg or COLORS["bg"],
            highlightthickness=0, bd=0, cursor="hand2"
        )
        self._cmd = command
        self._on = bool(value)
        r = self.H / 2.0
        self._track = [
            self.create_oval(1, 1, self.H - 1, self.H - 1, outline=""),
            self.create_oval(self.W - self.H + 1, 1, self.W - 1, self.H - 1, outline=""),
            self.create_rectangle(r, 1, self.W - r, self.H - 1, outline=""),
        ]
        self._knob = self.create_oval(0, 0, 0, 0, fill="#ffffff", outline="")
        self.bind("<Button-1>", self._on_click)
        self._draw()

    def _on_click(self, _event=None):
        self.set(not self._on, notify=True)

    def get(self) -> bool:
        return self._on

    def set(self, value: bool, notify: bool = False):
        value = bool(value)
        changed = value != self._on
        self._on = value
        self._draw()
        if notify and changed and self._cmd:
            self._cmd(self._on)

    def _draw(self):
        for item in self._track:
            self.itemconfig(item, fill=COLORS["accent"] if self._on else "#cbd5e1")
        pad = 3
        d = self.H - 2 * pad
        x = (self.W - self.H + pad) if self._on else pad
        self.coords(self._knob, x, pad, x + d, pad + d)


class ScrollArea(tk.Frame):

    def __init__(self, master, height: int = 300, bg: str = None, **kw):
        bg = bg or COLORS["bg"]
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, height=height)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._win, width=e.width)
        )
        self._wheel_bound = set()
        self.bind_children()
        self.canvas.bind("<MouseWheel>", self._wheel)

    def bind_children(self):
        def walk(w):
            try:
                key = w.winfo_id()
            except Exception:
                return
            if key not in self._wheel_bound:
                self._wheel_bound.add(key)
                w.bind("<MouseWheel>", self._wheel, add="+")
            for c in w.winfo_children():
                walk(c)
        walk(self.inner)

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def scroll_to_top(self):
        self.canvas.yview_moveto(0.0)


class Modal(tk.Toplevel):

    def __init__(self, parent, title: str, width: int = 460, height: int = 260):
        super().__init__(parent, bg=COLORS["bg"])
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.result = None

        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=20, pady=16)
        self.body = body

        self.buttons = tk.Frame(self, bg=COLORS["bg"])
        self.buttons.pack(fill="x", padx=20, pady=(0, 16))

        self.bind("<Escape>", lambda e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self._center(parent, width, height)
        self.grab_set()

    def _center(self, parent, width, height):
        self.update_idletasks()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x = px + max(0, (pw - width) // 2)
            y = py + max(0, (ph - height) // 3)
        except Exception:
            x = y = 200
        self.geometry(f"{width}x{height}+{x}+{y}")

    def cancel(self):
        self.result = None
        self.destroy()

    def finish(self, result):
        self.result = result
        self.destroy()

    def wait(self):
        self.wait_window(self)
        return self.result


def wrap_label(widget, pad: int = 16):
    def on_configure(event):
        width = max(120, event.width - pad)
        if widget.cget("wraplength") != width:
            widget.configure(wraplength=width)
    widget.bind("<Configure>", on_configure, add="+")
    return widget


def section_title(parent, text: str, bg: str = None, sub: str = None):
    bg = bg or COLORS["bg"]
    wrap = tk.Frame(parent, bg=bg)
    lbl = tk.Label(
        wrap, text=text, bg=bg, fg=COLORS["text"],
        font=config.font("h2", bold=True), anchor="w"
    )
    lbl.pack(anchor="w")
    sub_lbl = None
    if sub:
        sub_lbl = tk.Label(
            wrap, text=sub, bg=bg, fg=COLORS["text_dim"],
            font=config.font("small"), anchor="w", justify="left"
        )
        sub_lbl.pack(anchor="w", pady=(2, 0))

    wrap.title_label = lbl
    wrap.sub_label = sub_lbl
    return wrap
