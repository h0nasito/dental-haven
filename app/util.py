"""Small shared helpers: clinic time, money, parsing."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def tz():
    try:
        return ZoneInfo(current_app.config.get("CLINIC_TIMEZONE", "Asia/Manila"))
    except RuntimeError:
        return ZoneInfo("Asia/Manila")


def now() -> datetime:
    """Current clinic-local time, naive (all stored times are clinic-local)."""
    return datetime.now(tz()).replace(tzinfo=None, microsecond=0)


def now_str() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> date:
    return now().date()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def hm_to_min(hm: str) -> int:
    h, m = hm.split(":")[:2]
    return int(h) * 60 + int(m)


def min_to_hm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return a_start < b_end and b_start < a_end


def peso(cents: int | None) -> str:
    if cents is None:
        return "—"
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}₱{cents // 100:,}.{cents % 100:02d}"


_MONEY_RE = re.compile(r"^\d{1,9}(\.\d{1,2})?$")


def parse_money(value: str | None) -> int | None:
    """'1,250.50' -> 125050 centavos. Returns None for blank/invalid."""
    if value is None:
        return None
    value = value.strip().replace(",", "").replace("₱", "")
    if not value or not _MONEY_RE.match(value):
        return None
    whole, _, frac = value.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def clean(value: str | None, max_len: int = 500) -> str:
    return (value or "").strip()[:max_len]


def to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
