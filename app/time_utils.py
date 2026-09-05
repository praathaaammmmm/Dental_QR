from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")


def utc_now() -> datetime:
    """Return a naive UTC timestamp for compatibility with the existing schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clinic_local_day_start_utc(day: date) -> datetime:
    """Return the naive UTC instant matching 00:00 Asia/Kolkata on ``day``.

    All stored timestamps in this app (``utc_now()``) are naive UTC. Whenever a
    user-facing date filter needs to be compared against one of those timestamps, the
    date must first be interpreted as a clinic-local (Asia/Kolkata) calendar date and
    converted to the equivalent UTC instant here — comparing a raw local date directly
    against a UTC timestamp silently drifts by the IST offset (+5:30) and misclassifies
    records near local midnight.
    """
    local_midnight = datetime.combine(day, time.min, tzinfo=CLINIC_TIMEZONE)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def clinic_date_range_to_utc(start: date | None, end: date | None) -> tuple[datetime | None, datetime | None]:
    """Convert an inclusive [start, end] Asia/Kolkata calendar-date range into naive UTC
    [start_utc, end_utc) bounds suitable for a ``>= start_utc`` / ``< end_utc`` filter
    against a naive-UTC timestamp column.

    This is the one documented rule for interpreting user-entered date filters:
    - ``start``/``end`` are clinic-local (Asia/Kolkata) calendar dates, never UTC dates.
    - ``end`` is inclusive of its entire local calendar day (through 23:59:59.999... IST).
    - The comparison is always performed in UTC, since that is how timestamps are stored.
    """
    start_utc = clinic_local_day_start_utc(start) if start else None
    end_utc = clinic_local_day_start_utc(end + timedelta(days=1)) if end else None
    return start_utc, end_utc


def format_clinic_time(value: datetime | None, pattern: str = "%d %b %Y %I:%M %p") -> str:
    if value is None:
        return "—"
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return utc_value.astimezone(CLINIC_TIMEZONE).strftime(pattern)