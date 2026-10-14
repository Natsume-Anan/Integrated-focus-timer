

import os
import json
import shutil
from datetime import datetime, timedelta
from typing import Optional, Dict

import config
from config import (
    APP_NAME, OLD_APP_DIR, AUTO_TEXT, HOUR_LOG_ENABLED
)


def month_prefixes(now: datetime = None):
    """(本月, 上月) 的 'YYYY-MM' 前缀;数据只保留这两个月."""
    now = now or datetime.now()
    this = f"{now.year}-{now.month:02d}"
    if now.month == 1:
        last = f"{now.year - 1}-12"
    else:
        last = f"{now.year}-{now.month - 1:02d}"
    return this, last


def split_items(text: str):
    """标准语法: 一个小时 / 一次申请的多项活动用 / 连接, 如 '学习/吃饭'."""
    parts = str(text or "").replace("／", "/").split("/")
    return [p.strip() for p in parts if p.strip()]


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
        # 计时器的每一段专注 / 休息 (起止时刻), Statistics 页画每天的时间分布用; 只留最近 7 天
        self.focus_file = os.path.join(self.data_dir, 'focus_log.json')
        self.focus_sessions = []

        self.study_data: Dict[str, float] = {}
        self.hour_days: Dict[str, Dict[str, str]] = {}
        self.hour_cursor: Optional[datetime] = None

        self.hour_enabled = bool(getattr(config, "HOUR_LOG_ENABLED", HOUR_LOG_ENABLED))
        self.today_date = datetime.now().strftime('%Y-%m-%d')
        self.prompt_slot: Optional[datetime] = None

        self._migrate_old_data()
        self.load_study_data()
        self.prune_study_data()
        self.load_hour_log()
        self.finalize_hours()
        self.load_focus_log()


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

    def prune_study_data(self):
        """只保留本月与上月的学习时长(日历可查看这两个月)."""
        keep = month_prefixes()
        stale = [k for k in self.study_data if k[:7] not in keep]
        if stale:
            for key in stale:
                del self.study_data[key]
            self.save_study_data()

    def month_study(self, prefix: str) -> Dict[str, float]:
        return {k: v for k, v in self.study_data.items() if k.startswith(prefix)}


    # ---- 专注计时: 每一段专注 / 休息的起止时刻 ----

    FOCUS_DAYS = 7
    _TS = '%Y-%m-%d %H:%M:%S'

    def _focus_floor(self, now: datetime = None) -> datetime:
        now = now or datetime.now()
        return now.replace(hour=0, minute=0, second=0, microsecond=0) \
            - timedelta(days=self.FOCUS_DAYS - 1)

    def load_focus_log(self):
        try:
            with open(self.focus_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            recs = d.get("sessions", []) if isinstance(d, dict) else []
        except Exception:
            recs = []
        out = []
        for r in recs:
            try:
                st = datetime.strptime(r["s"], self._TS)
                en = datetime.strptime(r["e"], self._TS)
            except (KeyError, TypeError, ValueError):
                continue
            if r.get("k") in ("study", "break") and en > st:
                out.append({"k": r["k"], "s": r["s"], "e": r["e"]})
        self.focus_sessions = out
        self._prune_focus()

    def _prune_focus(self) -> bool:
        floor = self._focus_floor().strftime(self._TS)
        before = len(self.focus_sessions)
        self.focus_sessions = [r for r in self.focus_sessions if r["e"] > floor]
        return len(self.focus_sessions) != before

    def save_focus_log(self):
        if self.uninstalling:
            return
        self._prune_focus()
        try:
            tmp = self.focus_file + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({"sessions": self.focus_sessions}, f, indent=1)
            os.replace(tmp, self.focus_file)
        except (IOError, OSError):
            pass

    def add_focus_session(self, kind: str, start: datetime, end: datetime):
        """kind: 'study' 专注 / 'break' 休息."""
        if kind not in ("study", "break") or start is None or end is None:
            return
        if (end - start).total_seconds() < 1:
            return
        self.focus_sessions.append({
            "k": kind, "s": start.strftime(self._TS), "e": end.strftime(self._TS)})
        self.save_focus_log()

    def focus_hours(self, day: datetime, live=None):
        """某一天 24 个小时各自的 (专注秒数, 休息秒数).

        live: 正在进行的一段 (kind, start), 计到此刻为止."""
        day0 = day.replace(hour=0, minute=0, second=0, microsecond=0)
        study = [0.0] * 24
        rest = [0.0] * 24
        segs = []
        for r in self.focus_sessions:
            segs.append((r["k"], datetime.strptime(r["s"], self._TS),
                         datetime.strptime(r["e"], self._TS)))
        if live and live[1] is not None:
            segs.append((live[0], live[1], datetime.now()))
        for kind, st, en in segs:
            for h in range(24):
                h0 = day0 + timedelta(hours=h)
                h1 = h0 + timedelta(hours=1)
                sec = (min(en, h1) - max(st, h0)).total_seconds()
                if sec > 0:
                    (study if kind == "study" else rest)[h] += sec
        for h in range(24):
            # 理论上不会重叠; 万一重叠, 专注优先, 一小时最多 3600 秒
            study[h] = min(3600.0, study[h])
            rest[h] = min(3600.0 - study[h], rest[h])
        return list(zip(study, rest))

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
        keep = month_prefixes()
        self.hour_days = {k: v for k, v in self.hour_days.items() if k[:7] in keep}

    def hour_activity_seconds(self, prefix: str) -> Dict[str, float]:
        """某个月每项活动的总时长(秒).一小时有多项活动时均分."""
        return tally_items(
            (text, 3600.0)
            for ds, day in self.hour_days.items() if ds.startswith(prefix)
            for text in day.values()
        )

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
        # 00:00 那一格(昨天 23:00–24:00)显示在今天最上方,所以从昨天 23:00 起补记.
        self.hour_cursor = max(self.hour_cursor, today0 - timedelta(hours=1))
        if not self.hour_enabled:

            if self.hour_cursor < floor:
                self.hour_cursor = floor
                self.save_hour_log()
            return
        changed = False
        while self.hour_cursor + timedelta(hours=1) + config.FILL_WINDOW <= now:
            ds, h = self.hour_cursor.strftime('%Y-%m-%d'), self.hour_cursor.hour

            if not self.get_hour_text(ds, h):
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
        if (datetime.now() >= s + timedelta(hours=1) + config.FILL_WINDOW
                or self.get_hour_text(s.strftime('%Y-%m-%d'), s.hour)):
            self.prompt_slot = None
            return None
        return s


    def erase_all_data(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.old_dir, ignore_errors=True)


def tally_items(pairs) -> Dict[str, float]:
    """[(文本, 秒)] → {活动: 秒};按 / 拆分均分,同名(忽略大小写)合并."""
    totals: Dict[str, float] = {}
    names: Dict[str, str] = {}
    for text, secs in pairs:
        items = split_items(text)
        if not items or secs <= 0:
            continue
        share = float(secs) / len(items)
        for item in items:
            key = item.casefold()
            names.setdefault(key, item)
            totals[key] = totals.get(key, 0.0) + share
    return {names[k]: v for k, v in totals.items()}
