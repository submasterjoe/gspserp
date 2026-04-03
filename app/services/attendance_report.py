"""Attendance grouping: local calendar days, leave coverage, weekday gaps."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from zoneinfo import ZoneInfo

from app.models import ClockEventType

if TYPE_CHECKING:
    from app.models import ClockEvent, LeaveRequest


def effective_time(ev: ClockEvent) -> datetime:
    t = ev.device_time or ev.event_at
    if t.tzinfo is None:
        return t.replace(tzinfo=timezone.utc)
    return t


def _tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo((tz_name or "UTC").strip() or "UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def to_local_date(dt: datetime, tz_name: str) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_tz(tz_name)).date()


def month_local_bounds(d: date) -> tuple[date, date]:
    first = date(d.year, d.month, 1)
    if d.month == 12:
        last = date(d.year, 12, 31)
    else:
        last = date(d.year, d.month + 1, 1) - timedelta(days=1)
    return first, last


def weekdays_between(d0: date, d1: date) -> list[date]:
    out: list[date] = []
    x = d0
    while x <= d1:
        if x.weekday() < 5:
            out.append(x)
        x += timedelta(days=1)
    return out


def utc_range_for_local_day(day: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = _tz(tz_name)
    start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz).astimezone(timezone.utc)
    end = datetime(day.year, day.month, day.day, 23, 59, 59, 999999, tzinfo=tz).astimezone(timezone.utc)
    return start, end


def month_utc_query_range(year: int, month: int, tz_name: str) -> tuple[datetime, datetime]:
    """UTC window spanning the full local calendar month."""
    tz = _tz(tz_name)
    start_l = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end_l = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_l = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    return start_l.astimezone(timezone.utc), end_l.astimezone(timezone.utc)


def leave_covers_day(lr: LeaveRequest, day: date) -> bool:
    from app.models import LeaveRequestStatus

    return bool(lr.status == LeaveRequestStatus.approved and lr.start_date <= day <= lr.end_date)


def group_events_by_user_local_day(
    events: list[ClockEvent], tz_name: str
) -> dict[int, dict[date, list[ClockEvent]]]:
    out: dict[int, dict[date, list[ClockEvent]]] = defaultdict(lambda: defaultdict(list))
    for ev in events:
        ld = to_local_date(effective_time(ev), tz_name)
        out[ev.user_id][ld].append(ev)
    for uid in out:
        for ld in out[uid]:
            out[uid][ld].sort(key=lambda e: effective_time(e))
    return out


def first_last_punch_for_day(day_events: list[ClockEvent]) -> tuple[datetime | None, datetime | None]:
    ins = [effective_time(e) for e in day_events if e.event_type == ClockEventType.clock_in]
    outs = [effective_time(e) for e in day_events if e.event_type == ClockEventType.clock_out]
    first_in = min(ins) if ins else None
    last_out = max(outs) if outs else None
    return first_in, last_out
