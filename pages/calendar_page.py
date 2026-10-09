# -*- coding: utf-8 -*-
"""日历页面：显示当月每天的学习时间"""

import tkinter as tk
import calendar
from datetime import datetime

from config import COLORS


class CalendarPage(tk.Frame):
    def __init__(self, master, data_manager):
        super().__init__(master, bg=COLORS["bg"])
        self.dm = data_manager
        self.display_year = datetime.now().year
        self.display_month = datetime.now().month
        self._build_ui()

    def _build_ui(self):
        nav_frame = tk.Frame(self, bg=COLORS["bg"])
        nav_frame.pack(fill="x", padx=18, pady=(20, 5))

        self.lbl_month_title = tk.Label(
            nav_frame, text="", font=("Segoe UI", 15, "bold"),
            bg=COLORS["bg"], fg=COLORS["text"], anchor="w"
        )
        self.lbl_month_title.pack(side="left", expand=True, fill="x")

        self.lbl_month_total = tk.Label(
            nav_frame, text="Total: 0.0 h",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["bg"], fg=COLORS["accent"]
        )
        self.lbl_month_total.pack(side="right", padx=(10, 5))

        days_header = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        header_frame = tk.Frame(self, bg=COLORS["bg"])
        header_frame.pack(fill="x", padx=18, pady=(5, 0))
        for i, day_name in enumerate(days_header):
            lbl = tk.Label(
                header_frame, text=day_name, font=("Segoe UI", 9, "bold"),
                bg=COLORS["bg_card"], fg=COLORS["text_dim"],
                width=8, height=1, anchor="center"
            )
            lbl.grid(row=0, column=i, padx=1, pady=1, sticky="nsew")
            header_frame.columnconfigure(i, weight=1)

        self.grid_frame = tk.Frame(self, bg=COLORS["bg"])
        self.grid_frame.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def refresh(self):
        """每次切到本页时重新读取数据并绘制"""
        self.display_year = datetime.now().year
        self.display_month = datetime.now().month

        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        self.lbl_month_title.config(
            text=f"{month_names[self.display_month - 1]} {self.display_year}"
        )

        cal = calendar.monthcalendar(self.display_year, self.display_month)
        today_str = datetime.now().strftime('%Y-%m-%d')

        prefix = f"{self.display_year}-{self.display_month:02d}"
        month_data = {}
        month_total = 0.0
        for date_str, hours in self.dm.study_data.items():
            if date_str.startswith(prefix):
                month_data[date_str] = hours
                month_total += hours
        self.lbl_month_total.config(text=f"Total: {month_total:.1f} h")

        for row_idx, week in enumerate(cal):
            for col_idx, day in enumerate(week):
                if day == 0:
                    lbl = tk.Label(
                        self.grid_frame, text="", bg=COLORS["bg"],
                        width=8, height=2, relief="flat", bd=0
                    )
                else:
                    date_str = f"{self.display_year}-{self.display_month:02d}-{day:02d}"
                    hours = month_data.get(date_str, 0.0)
                    bg_color = COLORS["accent"] if date_str == today_str else COLORS["bg_card"]
                    fg_color = "#ffffff" if date_str == today_str else COLORS["text"]
                    text = f"{day}\n{hours:.1f}h" if hours > 0 else str(day)
                    lbl = tk.Label(
                        self.grid_frame, text=text, bg=bg_color, fg=fg_color,
                        font=("Segoe UI", 9), width=8, height=2,
                        relief="flat", bd=0, anchor="center"
                    )
                lbl.grid(row=row_idx, column=col_idx, padx=1, pady=1, sticky="nsew")

        for i in range(7):
            self.grid_frame.columnconfigure(i, weight=1)
