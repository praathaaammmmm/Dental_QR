from datetime import datetime, timezone
from zoneinfo import ZoneInfo


CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")


def utc_now() -> datetime:
    """Return a naive UTC timestamp for compatibility with the existing schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_clinic_time(value: datetime | None, pattern: str = "%d %b %Y %I:%M %p") -> str:
    if value is None:
        return "—"
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return utc_value.astimezone(CLINIC_TIMEZONE).strftime(pattern)