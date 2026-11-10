"""
Application Timezone Management & Temporal Normalization Engine.

Centralizes IANA timezone handling across backend queries, balance anchor
calculations, statement intake, and calendar-day conversions.
"""

from datetime import datetime, date, time, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

DEFAULT_APP_TIMEZONE = "Europe/London"
APP_TIMEZONE_SETTING_KEY = "app_timezone"

def get_app_timezone(db: Optional[Session] = None) -> str:
    """
    Retrieves the authoritative IANA timezone configured in system_settings,
    defaulting to 'Europe/London' if not set or if db session is unavailable.
    """
    if db is not None:
        try:
            from app.models import SystemSetting
            setting = db.query(SystemSetting).filter(SystemSetting.key == APP_TIMEZONE_SETTING_KEY).first()
            if setting and setting.value and setting.value.strip():
                clean_tz = setting.value.strip()
                # Validate ZoneInfo accepts it
                ZoneInfo(clean_tz)
                return clean_tz
        except Exception:
            pass
    return DEFAULT_APP_TIMEZONE

def get_app_zoneinfo(db: Optional[Session] = None) -> ZoneInfo:
    """Returns the ZoneInfo instance for the configured application timezone."""
    return ZoneInfo(get_app_timezone(db))

def get_now_utc() -> datetime:
    """Returns current UTC timestamp with tzinfo=timezone.utc."""
    return datetime.now(timezone.utc)

def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures a datetime is timezone-aware in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def get_today_local(tz_str: Optional[Union[str, ZoneInfo]] = None) -> date:
    """Returns today's date in the specified or default timezone."""
    tz = tz_str if isinstance(tz_str, ZoneInfo) else ZoneInfo(tz_str or DEFAULT_APP_TIMEZONE)
    return datetime.now(tz).date()

def parse_date_input(d: Union[str, date, datetime]) -> date:
    """Parses string 'YYYY-MM-DD', date, or datetime into date object."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    clean = str(d).strip().split("T")[0]
    return date.fromisoformat(clean)

def get_end_of_day_utc(target_date: Union[str, date, datetime], tz_str: Optional[Union[str, ZoneInfo]] = None) -> datetime:
    """
    Computes closing time 23:59:59.999999 in the specified local timezone,
    converted to UTC.
    """
    d = parse_date_input(target_date)
    tz = tz_str if isinstance(tz_str, ZoneInfo) else ZoneInfo(tz_str or DEFAULT_APP_TIMEZONE)
    local_dt = datetime.combine(d, time(23, 59, 59, 999999), tzinfo=tz)
    return local_dt.astimezone(timezone.utc)

def get_midday_utc(target_date: Union[str, date, datetime], tz_str: Optional[Union[str, ZoneInfo]] = None) -> datetime:
    """
    Computes local midday 12:00:00 in the specified timezone, converted to UTC.
    Used for date-only backdated entries to prevent timezone edge shifts.
    """
    d = parse_date_input(target_date)
    tz = tz_str if isinstance(tz_str, ZoneInfo) else ZoneInfo(tz_str or DEFAULT_APP_TIMEZONE)
    local_dt = datetime.combine(d, time(12, 0, 0), tzinfo=tz)
    return local_dt.astimezone(timezone.utc)

def get_start_of_day_utc(target_date: Union[str, date, datetime], tz_str: Optional[Union[str, ZoneInfo]] = None) -> datetime:
    """Computes opening time 00:00:00 in the specified timezone, converted to UTC."""
    d = parse_date_input(target_date)
    tz = tz_str if isinstance(tz_str, ZoneInfo) else ZoneInfo(tz_str or DEFAULT_APP_TIMEZONE)
    local_dt = datetime.combine(d, time(0, 0, 0), tzinfo=tz)
    return local_dt.astimezone(timezone.utc)

def resolve_anchor_datetime(
    as_of_mode: str,
    as_of_date: Optional[Union[str, date, datetime]] = None,
    tz_str: Optional[str] = None
) -> datetime:
    """
    Resolves the exact UTC cutoff timestamp for a balance anchor:
    - If mode is 'now': exact current UTC timestamp.
    - If mode is 'date': end of that day (23:59:59.999999) in app timezone converted to UTC.
    """
    clean_mode = (as_of_mode or "now").strip().lower()
    if clean_mode == "now" or not as_of_date:
        return get_now_utc()
    return get_end_of_day_utc(as_of_date, tz_str=tz_str)
