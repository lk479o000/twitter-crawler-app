from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Tuple


def _to_iso(dt: datetime) -> str:
    # Twitter API 需要 UTC ISO8601，简化处理为日期边界
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def today_range() -> Tuple[str, str]:
    d = datetime.utcnow().date()
    start = datetime.combine(d, datetime.min.time())
    end = datetime.combine(d, datetime.max.time())
    return _to_iso(start), _to_iso(end)


def this_week_range() -> Tuple[str, str]:
    today = datetime.utcnow().date()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return _to_iso(datetime.combine(start, datetime.min.time())), _to_iso(datetime.combine(end, datetime.max.time()))


def this_month_range() -> Tuple[str, str]:
    today = datetime.utcnow().date()
    start = today.replace(day=1)
    if start.month == 12:
        next_month_start = start.replace(year=start.year + 1, month=1, day=1)
    else:
        next_month_start = start.replace(month=start.month + 1, day=1)
    end = next_month_start - timedelta(days=1)
    return _to_iso(datetime.combine(start, datetime.min.time())), _to_iso(datetime.combine(end, datetime.max.time()))


def this_quarter_range() -> Tuple[str, str]:
    today = datetime.utcnow().date()
    q = (today.month - 1) // 3
    start_month = q * 3 + 1
    start = date(today.year, start_month, 1)
    end_month = start_month + 2
    # 找到季度最后一天
    if end_month in (1, 3, 5, 7, 8, 10, 12):
        end_day = 31
    elif end_month == 2:
        is_leap = (today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0))
        end_day = 29 if is_leap else 28
    else:
        end_day = 30
    end = date(today.year, end_month, end_day)
    return _to_iso(datetime.combine(start, datetime.min.time())), _to_iso(datetime.combine(end, datetime.max.time()))


def this_half_year_range() -> Tuple[str, str]:
    today = datetime.utcnow().date()
    if today.month <= 6:
        start = date(today.year, 1, 1)
        end = date(today.year, 6, 30)
    else:
        start = date(today.year, 7, 1)
        end = date(today.year, 12, 31)
    return _to_iso(datetime.combine(start, datetime.min.time())), _to_iso(datetime.combine(end, datetime.max.time()))


def this_year_range() -> Tuple[str, str]:
    today = datetime.utcnow().date()
    start = date(today.year, 1, 1)
    end = date(today.year, 12, 31)
    return _to_iso(datetime.combine(start, datetime.min.time())), _to_iso(datetime.combine(end, datetime.max.time()))


def recent_days_range(days: int) -> Tuple[str, str]:
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    return _to_iso(start), _to_iso(end)



