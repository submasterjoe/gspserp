"""Human-readable numeric display: thousands separators, max 4 decimal places."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jinja2 import Environment

_DEFAULT_PLACES = 4


def format_amount(value: Any, max_places: int | None = None) -> str:
    places = _DEFAULT_PLACES if max_places is None else max(0, min(int(max_places), 28))
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if places == 0:
        d = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        d = d.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
    neg = d.is_signed()
    d = abs(d)
    plain = format(d, "f")
    if "." in plain:
        int_part, frac_part = plain.split(".", 1)
    else:
        int_part, frac_part = plain, ""
    frac_part = frac_part.rstrip("0")
    try:
        int_part_int = int(int_part)
    except ValueError:
        return ("-" if neg else "") + plain
    body = f"{int_part_int:,}"
    if frac_part:
        body += "." + frac_part
    return ("-" if neg else "") + body


def register_amount_filter(env: Environment) -> None:
    env.filters["amount"] = format_amount


def format_local_datetime(value: Any, tz_name: str) -> str:
    """Format an aware UTC datetime for a display timezone (e.g. Malaysia MYT)."""
    if value is None:
        return "—"
    if not isinstance(value, datetime):
        return str(value)
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        tz = ZoneInfo(tz_name.strip() or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    local = dt.astimezone(tz)
    abbr = local.tzname() or ""
    if abbr:
        return f"{local:%Y-%m-%d %H:%M:%S} ({abbr})"
    return f"{local:%Y-%m-%d %H:%M:%S}"


def register_datetime_filters(env: Environment, tz_name: str) -> None:
    def localtime(value: Any) -> str:
        return format_local_datetime(value, tz_name)

    env.filters["localtime"] = localtime
