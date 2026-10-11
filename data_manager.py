

import os
import json
import shutil
from datetime import datetime, timedelta
from typing import Optional, Dict

import config
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


        self.uninstall_file = os.path.join(low_dir, f"{APP_NAME}.uninstall.json")
        self.uninstalling = False
        self.uninstall_count, self.uninstall_last = self._load_uninstall_count()

        self.study_file = os.path.join(self.data_dir, 'study_log.json')
        self.hour_file = os.path.join(self.data_dir, 'hour_log.json')

        self.study_data: Dict[str, float] = {}
        self.hour_days: Dict[str, Dict[str, str]] = {}
        self.hour_cursor: Optional[datetime] = None

        self.hour_enabled = bool(getattr(config, "HOUR_LOG_ENABLED", HOUR_LOG_ENABLED))
        self.today_date = datetime.now().strftime('%Y-%m-%d')
        self.prompt_slot: Optional[datetime] = None

        self._migrate_old_data()
        self.load_study_data()
        self.load_hour_log()
        self.finalize_hours()


    @property
    def log_hours(self) -> int:
        try:
            return max(1, min(24, int(getattr(config, "LOG_HOURS", LOG_HOURS))))
        except (TypeError, ValueError):
            return LOG_HOURS

    @property
    def auto_text(self) -> str:
        return str(getattr(config, "AUTO_TEXT", AUTO_TEXT))


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


    def _migrate_old_data(self):
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


    def load_hour_log(self):
        try:
            with open(self.hour_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            self.hour_days = d.get("days", {})
            cur = d.get("cursor")
            self.hour_cursor = datetime.fromisoformat(cur) if cur else None
        except Exception:
            self.hour_days, self.hour_cursor = {}, None
        self._prune_hours()

    def _prune_hours(self):
        today = datetime.now().strftime('%Y-%m-%d')
        self.hour_days = {k: v for k, v in self.hour_days.items() if k == today}

    def save_hour_log(self):
        if self.uninstalling:
            return
        self._prune_hours()
        try:
            with open(self.hour_file, 'w', encoding='utf-8') as f:
                json.dump({

                    "enabled": bool(self.hour_enabled),
                    "cursor": self.hour_cursor.isoformat() if self.hour_cursor else None,
                    "days": self.hour_days
                }, f, ensure_ascii=False, indent=1)
        except IOError:
            pass

    def apply_hour_enabled(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self.hour_enabled:
            return
        self.hour_enabled = enabled
        if enabled:

            self.hour_cursor = datetime.now().replace(minute=0, second=0, microsecond=0)
        else:
            self.prompt_slot = None
        self.save_hour_log()

    def set_hour_enabled(self, enabled: bool):
        self.apply_hour_enabled(enabled)

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
        now = datetime.now()
        floor = now.replace(minute=0, second=0, microsecond=0)
        today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.hour_cursor is None:
            self.hour_cursor = floor
            self.save_hour_log()
            return
        self.hour_cursor = max(self.hour_cursor, today0)
        if not self.hour_enabled:

            if self.hour_cursor < floor:
                self.hour_cursor = floor
                self.save_hour_log()
            return
        changed = False
        while self.hour_cursor + timedelta(hours=1) + FILL_WINDOW <= now:
            ds, h = self.hour_cursor.strftime('%Y-%m-%d'), self.hour_cursor.hour

            if h < self.log_hours and not self.get_hour_text(ds, h):
                self.hour_days.setdefault(ds, {})[str(h)] = self.auto_text
            self.hour_cursor += timedelta(hours=1)
            changed = True
        if changed:
            self.save_hour_log()

    def awaiting_slot(self) -> Optional[datetime]:
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


    def erase_all_data(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.old_dir, ignore_errors=True)
