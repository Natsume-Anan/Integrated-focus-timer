# -*- coding: utf-8 -*-
"""
数据持久化管理：学习时长、整点日志、卸载计数、旧数据迁移
"""

import os
import json
import shutil
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from config import (
    APP_NAME, OLD_APP_DIR, FILL_WINDOW, AUTO_TEXT, LOG_HOURS, HOUR_LOG_ENABLED
)


class DataManager:
    def __init__(self):
        low_dir = os.path.join(
            os.environ.get('USERPROFILE', os.path.expanduser('~')),
            'AppData', 'LocalLow'
        )
        self.low_dir = low_dir
        self.data_dir = os.path.join(low_dir, APP_NAME)
        os.makedirs(self.data_dir, exist_ok=True)
        self.old_dir = os.path.join(low_dir, OLD_APP_DIR)

        # 卸载计数放在数据文件夹之外,卸载清数据时不会被删
        self.uninstall_file = os.path.join(low_dir, f"{APP_NAME}.uninstall.json")
        self.uninstalling = False
        self.uninstall_count, self.uninstall_last = self._load_uninstall_count()

        self.study_file = os.path.join(self.data_dir, 'study_log.json')
        self.hour_file = os.path.join(self.data_dir, 'hour_log.json')

        self.study_data: Dict[str, float] = {}
        self.hour_days: Dict[str, Dict[str, str]] = {}
        self.hour_cursor: Optional[datetime] = None
        self.hour_enabled: bool = HOUR_LOG_ENABLED   # 整点记录总开关
        self.today_date = datetime.now().strftime('%Y-%m-%d')
        self.prompt_slot: Optional[datetime] = None  # 最近一次提示音对应的“上一个小时”

        self._migrate_old_data()
        self.load_study_data()
        self.load_hour_log()
        self.finalize_hours()

    # ───────────── 卸载计数 ─────────────
    def _load_uninstall_count(self):
        try:
            with open(self.uninstall_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return int(d.get("count", 0)), d.get("last")
        except Exception:
            return 0, None

    def save_uninstall_count(self):
        try:
            with open(self.uninstall_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "count": self.uninstall_count,
                    "last": self.uninstall_last
                }, f)
        except IOError:
            pass

    # ───────────── 旧数据迁移 ─────────────
    def _migrate_old_data(self):
        """首次启动:把旧文件夹里的数据复制到新文件夹(不覆盖已有文件)"""
        if not os.path.isdir(self.old_dir):
            return
        for name in ("study_log.json", "net_state.json", "net_requests.log"):
            src = os.path.join(self.old_dir, name)
            dst = os.path.join(self.data_dir, name)
            if os.path.exists(src) and not os.path.exists(dst):
                try:
                    shutil.copy2(src, dst)
                except OSError:
                    pass

    # ───────────── 学习时长数据 ─────────────
    def load_study_data(self):
        if os.path.exists(self.study_file):
            try:
                with open(self.study_file, 'r', encoding='utf-8') as f:
                    self.study_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.study_data = {}
        else:
            self.study_data = {}
            self.save_study_data()

    def save_study_data(self):
        if self.uninstalling:
            return
        try:
            with open(self.study_file, 'w', encoding='utf-8') as f:
                json.dump(self.study_data, f, indent=2)
        except IOError:
            pass

    def get_today_hours(self) -> float:
        return self.study_data.get(self.today_date, 0.0)

    def get_yesterday_hours(self) -> float:
        yesterday = (datetime.strptime(self.today_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        return self.study_data.get(yesterday, 0.0)

    def add_study_session(self, wall_start: datetime, wall_end: datetime, duration_minutes: float):
        if duration_minutes <= 0:
            return

        start_date = wall_start.strftime('%Y-%m-%d')
        end_date = wall_end.strftime('%Y-%m-%d')

        if start_date == end_date:
            hours = duration_minutes / 60.0
            self.study_data[start_date] = self.study_data.get(start_date, 0.0) + hours
        else:
            midnight = wall_start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            first_part = (midnight - wall_start).total_seconds() / 60.0
            second_part = (wall_end - midnight).total_seconds() / 60.0
            total = first_part + second_part
            if total > 0:
                hours_first = duration_minutes * (first_part / total) / 60.0
                hours_second = duration_minutes * (second_part / total) / 60.0
                self.study_data[start_date] = self.study_data.get(start_date, 0.0) + hours_first
                self.study_data[end_date] = self.study_data.get(end_date, 0.0) + hours_second
            else:
                hours = duration_minutes / 60.0
                self.study_data[start_date] = self.study_data.get(start_date, 0.0) + hours

        self.save_study_data()

    def clear_last_month_except_yesterday(self):
        today = datetime.now()
        if today.month == 1:
            last_year, last_month = today.year - 1, 12
        else:
            last_year, last_month = today.year, today.month - 1
        last_month_prefix = f"{last_year}-{last_month:02d}"
        yesterday_str = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        keys_to_delete = [
            k for k in self.study_data
            if k.startswith(last_month_prefix) and k != yesterday_str
        ]
        for key in keys_to_delete:
            del self.study_data[key]
        self.save_study_data()

    # ───────────── 整点记录数据 ─────────────
    def load_hour_log(self):
        try:
            with open(self.hour_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            self.hour_days = d.get("days", {})
            self.hour_enabled = bool(d.get("enabled", self.hour_enabled))
            cur = d.get("cursor")
            self.hour_cursor = datetime.fromisoformat(cur) if cur else None
        except Exception:
            self.hour_days, self.hour_cursor = {}, None
        self._prune_hours()

    def _prune_hours(self):
        """只保留今天的记录"""
        today = datetime.now().strftime('%Y-%m-%d')
        self.hour_days = {k: v for k, v in self.hour_days.items() if k == today}

    def save_hour_log(self):
        if self.uninstalling:
            return
        self._prune_hours()
        try:
            with open(self.hour_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "enabled": self.hour_enabled,
                    "cursor": self.hour_cursor.isoformat() if self.hour_cursor else None,
                    "days": self.hour_days
                }, f, ensure_ascii=False, indent=1)
        except IOError:
            pass

    def set_hour_enabled(self, enabled: bool):
        """切换整点记录开关:关闭时不再提示/不再自动补记,重新开启从当前小时起记"""
        enabled = bool(enabled)
        if enabled == self.hour_enabled:
            return
        self.hour_enabled = enabled
        now = datetime.now()
        if enabled:
            # 关闭期间的时段保持空白,不做任何补记
            self.hour_cursor = now.replace(minute=0, second=0, microsecond=0)
        else:
            self.prompt_slot = None
        self.save_hour_log()

    def get_hour_text(self, date_str: str, hour: int) -> str:
        return self.hour_days.get(date_str, {}).get(str(hour), "")

    def set_hour_text(self, date_str: str, hour: int, text: str):
        day = self.hour_days.setdefault(date_str, {})
        if text:
            day[str(hour)] = text
        else:
            day.pop(str(hour), None)
        self.save_hour_log()

    def finalize_hours(self):
        """把已超过填写期限、仍为空白的小时填成 Sleeping(只处理今天,且跳过 23:00–24:00)"""
        now = datetime.now()
        floor = now.replace(minute=0, second=0, microsecond=0)
        today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.hour_cursor is None:
            self.hour_cursor = floor            # 首次运行:从当前小时开始记
            self.save_hour_log()
            return
        self.hour_cursor = max(self.hour_cursor, today0)   # 昨天及更早的不再处理
        if not self.hour_enabled:
            # 关闭状态下不写入任何自动记录,游标直接跟到当前小时
            if self.hour_cursor < floor:
                self.hour_cursor = floor
                self.save_hour_log()
            return
        changed = False
        while self.hour_cursor + timedelta(hours=1) + FILL_WINDOW <= now:
            ds, h = self.hour_cursor.strftime('%Y-%m-%d'), self.hour_cursor.hour
            if h < LOG_HOURS and not self.get_hour_text(ds, h):
                self.hour_days.setdefault(ds, {})[str(h)] = AUTO_TEXT
            self.hour_cursor += timedelta(hours=1)
            changed = True
        if changed:
            self.save_hour_log()

    def awaiting_slot(self) -> Optional[datetime]:
        """当前仍在等待填写的小时(datetime),没有则返回 None"""
        if not self.hour_enabled:
            return None
        s = self.prompt_slot
        if s is None:
            return None
        if (datetime.now() >= s + timedelta(hours=1) + FILL_WINDOW
                or self.get_hour_text(s.strftime('%Y-%m-%d'), s.hour)):
            self.prompt_slot = None
            return None
        return s

    # ───────────── 卸载清理 ─────────────
    def erase_all_data(self):
        """清除所有业务数据目录（卸载时调用）"""
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.old_dir, ignore_errors=True)
