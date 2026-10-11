

from datetime import datetime, timedelta

import config
from i18n import tr
from config import DEFAULT_SETTINGS, load_json_file, save_json_file, settings_file


APPLY_DELAY = "delay"
APPLY_INSTANT = "instant"


APPLY_DELAY_HOURS = 48


DEFAULT_SINCE = "2024-01-01 00:00"

MINUTES = 60


def _fmt_min(sec: int) -> str:
    sec = int(sec)
    if sec % 3600 == 0:
        return f"{sec // 3600} h"
    return f"{sec / 60:g} min"


def _fmt_sec(sec: int) -> str:
    sec = int(sec)
    return f"{sec} s" if sec < 180 else _fmt_min(sec)




SETTINGS_SCHEMA = [
    {
        "key": "DAILY_LIMIT", "label": "每日联网额度",
        "kind": "choice", "apply": APPLY_DELAY,
        "choices": [
            (str(h * 3600), f"{h:g} h") for h in (0.5, 1, 1.5, 2, 3, 4, 6, 8)
        ],
        "fmt": _fmt_min,
        "desc": "今天最多能联网多久。改动要 48 小时后才生效,期间仍按旧额度计算。",
    },
    {
        "key": "COOLDOWN", "label": "联网冷静期",
        "kind": "choice", "apply": APPLY_DELAY,
        "choices": [
            (str(m * 60), f"{m} min") for m in (1, 2, 5, 10, 15, 20, 30, 45, 60)
        ],
        "fmt": _fmt_min,
        "desc": "提出申请后等多久才真的联网。想立刻联网请用 Network 页的紧急贷款(今天 2 倍 / 预支明天 3 倍)。",
    },
    {
        "key": "HOUR_LOG_ENABLED", "label": "整点记录开关",
        "kind": "choice", "apply": APPLY_DELAY,
        "choices": [("1", "开启 (ON)"), ("0", "关闭 (OFF)")],
        "fmt": lambda v: "ON" if v else "OFF",
        "desc": "程序启动时整点记录的初始状态;启动后仍可在 Hour Log 页直接切换。",
    },
    {
        "key": "LOG_HOURS", "label": "整点记录截止小时",
        "kind": "choice", "apply": APPLY_DELAY,
        "choices": [("22", "22:00"), ("23", "23:00"), ("24", "24:00")],
        "fmt": lambda v: f"{int(v):02d}:00",
        "desc": "该小时之后不再提示填写(默认 23:00–24:00 不记录)。",
    },
    {
        "key": "AUTO_TEXT", "label": "超时自动记录内容",
        "kind": "instant", "apply": APPLY_INSTANT,
        "choices": [
            ("Sleeping", "Sleeping(睡觉)"),
            ("Idle", "Idle(发呆)"),
            ("Break", "Break(休息)"),
            ("Distracted", "Distracted(分心)"),
        ],
        "fmt": lambda v: str(v),
        "desc": "整点后一小时内没填写,就自动记成这段文字。这一项可以立即修改。",
    },
    {
        "key": "LANGUAGE", "label": "界面语言",
        "kind": "choice", "apply": APPLY_INSTANT,
        "choices": [("zh", "中文"), ("en", "English")],
        "fmt": lambda v: "中文" if str(v).startswith("zh") else "English",
        "desc": "即时生效.界面语言(中文 / English).",
    },
    {
        "key": "FONT_SCALE", "label": "界面字号",
        "kind": "choice", "apply": APPLY_INSTANT,
        "choices": [
            ("0.9", "偏小 (90%)"),
            ("1.0", "标准 (100%)"),
            ("1.15", "偏大 (115%)"),
            ("1.3", "很大 (130%)"),
            ("1.5", "极大 (150%)"),
        ],
        "fmt": lambda v: f"{float(v) * 100:.0f}%",
        "desc": "即时生效.整体缩放界面字号,适配不同分辨率.",
    },
    {
        "key": "ENFORCE_EVERY", "label": "断网复查间隔",
        "kind": "choice", "apply": APPLY_DELAY,
        "choices": [
            (str(s), f"{s} s") for s in (15, 30, 60, 120, 300)
        ],
        "fmt": _fmt_sec,
        "desc": "离线状态下每隔多久强制复查并重新断网(越小越难被绕开,代价是更频繁调用系统命令)。",
    },
    {
        "key": "CHIME_WAV", "label": "整点提示音",
        "kind": "combo", "apply": APPLY_INSTANT,
        "choices": [
            ("__builtin__", "内置三音提示音 (推荐)"),
            ("", "Windows 蜂鸣声 (Beep)"),
        ],
        "fmt": lambda v: "内置三音提示音" if str(v).strip() in ("", "__builtin__") else (
            "Windows 蜂鸣声" if str(v) == "__beep__" else str(v)),
        "desc": "即时生效。可粘贴本地 .wav 的完整路径。",
    },
]

SCHEMA_BY_KEY = {s["key"]: s for s in SETTINGS_SCHEMA}
DELAYED_KEYS = [s["key"] for s in SETTINGS_SCHEMA if s["apply"] == APPLY_DELAY]
INSTANT_KEYS = [s["key"] for s in SETTINGS_SCHEMA if s["apply"] == APPLY_INSTANT]


class SettingsManager:

    def __init__(self, path: str = None, delay_hours: int = APPLY_DELAY_HOURS):
        self.path = path or settings_file()
        self.delay = timedelta(hours=delay_hours)
        self.effective = {}
        self.pending = {}
        self.since = {}
        self.load()
        self.promote_due()
        self.apply_to_config()


    def load(self):
        raw = load_json_file(self.path, {})
        if not isinstance(raw, dict):
            raw = {}
        eff = raw.get("effective") if isinstance(raw.get("effective"), dict) else {}
        pen = raw.get("pending") if isinstance(raw.get("pending"), dict) else {}
        since = raw.get("since") if isinstance(raw.get("since"), dict) else {}

        for s in SETTINGS_SCHEMA:
            k = s["key"]
            if k in eff:
                self.effective[k] = self._coerce(k, eff[k])
            else:
                self.effective[k] = self._coerce(k, DEFAULT_SETTINGS.get(k))
            self.since[k] = str(since.get(k) or DEFAULT_SINCE)

        for k, item in pen.items():
            if k not in SCHEMA_BY_KEY or not isinstance(item, dict):
                continue
            at = self._parse_dt(item.get("apply_at"))
            if at is None:
                continue
            self.pending[k] = {
                "value": self._coerce(k, item.get("value")),
                "requested_at": str(item.get("requested_at") or ""),
                "apply_at": at,
            }

    def save(self):
        payload = {
            "effective": self.effective,
            "since": self.since,
            "pending": {
                k: {
                    "value": v["value"],
                    "requested_at": v["requested_at"],
                    "apply_at": v["apply_at"].isoformat(timespec="seconds"),
                }
                for k, v in self.pending.items()
            },
        }
        return save_json_file(self.path, payload)


    @staticmethod
    def _coerce(key: str, value):
        spec = SCHEMA_BY_KEY.get(key)
        if spec is None:
            return value
        if spec["kind"] in ("text", "combo", "instant"):
            return "" if value is None else str(value).strip()
        if spec["kind"] == "choice":

            if isinstance(value, bool):
                return int(value)
            text = str(value).strip()
            try:
                return int(text)
            except (TypeError, ValueError):
                pass
            try:
                return float(text)
            except (TypeError, ValueError):
                return value
        return value

    @staticmethod
    def _parse_dt(text):
        if not text:
            return None
        try:
            return datetime.fromisoformat(str(text))
        except ValueError:
            return None

    @staticmethod
    def _now() -> datetime:
        return datetime.now()


    def value(self, key: str):
        return self.effective.get(key, DEFAULT_SETTINGS.get(key))

    def staged(self, key: str):
        return self.pending.get(key)

    def is_staged(self, key: str) -> bool:
        return key in self.pending

    def staged_count(self) -> int:
        return len(self.pending)

    def apply_at(self, key: str):
        item = self.pending.get(key)
        return item["apply_at"] if item else None

    def apply_at_text(self, key: str) -> str:
        at = self.apply_at(key)
        if at is None:
            return ""
        left = at - self._now()
        secs = int(left.total_seconds())
        if secs <= 0:
            return tr("立即生效中…")
        d, rem = divmod(secs, 86400)
        h, rem = divmod(rem, 3600)
        m = rem // 60
        if d:
            return tr("{at} 生效 (还有 {d} 天 {h} 小时)").format(
                at=f"{at:%Y-%m-%d %H:%M}", d=d, h=h)
        if h:
            return tr("{at} 生效 (还有 {h} 小时 {m} 分)").format(
                at=f"{at:%H:%M}", h=h, m=m)
        return tr("{at} 生效 (还有 {m} 分)").format(at=f"{at:%H:%M}", m=m)

    def pending_left_seconds(self, key: str) -> int:
        at = self.apply_at(key)
        if at is None:
            return 0
        return max(0, int((at - self._now()).total_seconds()))


    def stage(self, key: str, value):
        spec = SCHEMA_BY_KEY.get(key)
        if spec is None:
            return "unknown", tr("未知配置项 {key}", key=key)
        value = self._coerce(key, value)

        if spec["apply"] == APPLY_INSTANT:
            self.effective[key] = value
            self.since[key] = f"{self._now():%Y-%m-%d %H:%M}"
            self.pending.pop(key, None)
            self.save()
            self.apply_to_config()
            return "instant", tr("{label} 已立即生效。", label=tr(spec['label']))

        if value == self.value(key):

            had = self.pending.pop(key, None) is not None
            if had:
                self.save()
                return "staged", tr("{label} 已恢复到当前生效值,排队中的改动已取消。",
                                    label=tr(spec['label']))
            return "nochange", tr("{label} 与当前生效值相同。", label=tr(spec['label']))

        now = self._now()
        self.pending[key] = {
            "value": value,
            "requested_at": f"{now:%Y-%m-%d %H:%M}",
            "apply_at": now + self.delay,
        }
        self.save()
        return "staged", tr("{label} 已提交,将于 {at}。",
                            label=tr(spec['label']), at=self.staged_apply_text(key))

    def staged_apply_text(self, key: str) -> str:
        at = self.apply_at(key)
        return f"{at:%Y-%m-%d %H:%M}" if at else ""

    def cancel(self, key: str) -> bool:
        if self.pending.pop(key, None) is None:
            return False
        self.save()
        return True

    def cancel_all(self) -> int:
        n = len(self.pending)
        if n:
            self.pending.clear()
            self.save()
        return n


    def promote_due(self) -> list:
        now = self._now()
        due = [k for k, v in self.pending.items() if v["apply_at"] <= now]
        for k in due:
            self.effective[k] = self.pending[k]["value"]
            self.since[k] = f"{now:%Y-%m-%d %H:%M}"
            del self.pending[k]
        if due:
            self.save()
            self.apply_to_config()
        return due

    def seconds_until_next(self):
        if not self.pending:
            return None
        return min(self.pending_left_seconds(k) for k in self.pending)


    def config_value(self, key: str):
        value = self.value(key)
        spec = SCHEMA_BY_KEY.get(key) or {}
        if spec.get("kind") == "choice":
            for raw, _label in spec.get("choices", []):
                if str(raw) == str(value):
                    if key == "FONT_SCALE":
                        return float(raw)
                    try:
                        return int(raw)
                    except (TypeError, ValueError):
                        return raw
        if key == "HOUR_LOG_ENABLED":
            return int(bool(value))
        if key == "FONT_SCALE":
            try:
                return max(0.75, min(2.0, float(value)))
            except (TypeError, ValueError):
                return 1.0
        if key in ("LANGUAGE", "AUTO_TEXT"):
            return str(value)
        if key == "CHIME_WAV":
            return "" if str(value).strip() in ("", "__builtin__") else str(value)
        return value

    def apply_to_config(self):
        for key in self.effective:
            setattr(config, key, self.config_value(key))


    def raw_ui_value(self, key: str) -> str:
        spec = SCHEMA_BY_KEY.get(key) or {}
        if spec.get("kind") in ("choice", "combo"):
            label = self.label_for(key, self.value(key))
            return label if label is not None else self.display(key)
        return str(self.value(key))

    def display(self, key: str) -> str:
        spec = SCHEMA_BY_KEY.get(key)
        if spec is None:
            return str(self.value(key))
        try:
            return spec["fmt"](self.value(key))
        except Exception:
            return str(self.value(key))

    def display_value(self, key: str, value) -> str:
        spec = SCHEMA_BY_KEY.get(key)
        if spec is None:
            return str(value)
        try:
            return spec["fmt"](value)
        except Exception:
            return str(value)

    def choices(self, key: str):
        spec = SCHEMA_BY_KEY.get(key) or {}
        return list(spec.get("choices") or [])

    def labeled_values(self, key: str, translate: bool = False):
        out = []
        for raw, label in self.choices(key):
            out.append((self._coerce(key, raw), tr(label) if translate else label))
        return out

    def label_for(self, key: str, value, translate: bool = False):
        for raw, label in self.choices(key):
            if self._coerce(key, raw) == self._coerce(key, value):
                return tr(label) if translate else label
        return None



def _selftest():
    import os
    import tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "settings.json")
    m = SettingsManager(tmp, delay_hours=48)
    assert m.value("DAILY_LIMIT") == DEFAULT_SETTINGS["DAILY_LIMIT"]
    assert not m.is_staged("DAILY_LIMIT")

    st, _ = m.stage("DAILY_LIMIT", 3600)
    assert st == "staged" and m.is_staged("DAILY_LIMIT")
    assert m.value("DAILY_LIMIT") == DEFAULT_SETTINGS["DAILY_LIMIT"], "延迟项不得立即生效"
    assert 47 * 3600 < m.pending_left_seconds("DAILY_LIMIT") <= 48 * 3600

    st, _ = m.stage("CHIME_WAV", "__builtin__")
    assert st == "instant" and not m.is_staged("CHIME_WAV")
    assert config.CHIME_WAV == ""

    assert m.cancel("DAILY_LIMIT") and not m.is_staged("DAILY_LIMIT")


    m.stage("COOLDOWN", 600)
    m.pending["COOLDOWN"]["apply_at"] = m._now() - timedelta(seconds=1)
    assert m.promote_due() == ["COOLDOWN"]
    assert m.value("COOLDOWN") == 600 and config.COOLDOWN == 600


    m.stage("LOG_HOURS", 24)
    m2 = SettingsManager(tmp, delay_hours=48)
    assert m2.is_staged("LOG_HOURS") and m2.value("LOG_HOURS") == DEFAULT_SETTINGS["LOG_HOURS"]
    assert m2.cancel_all() == 1
    return "settings_manager selftest OK"


if __name__ == "__main__":
    print(_selftest())
