from datetime import datetime, timezone

from app.time_utils import format_clinic_time


def test_naive_utc_time_is_displayed_in_india_standard_time():
    value = datetime(2026, 9, 3, 6, 23)
    assert format_clinic_time(value) == "03 Sep 2026 11:53 AM"


def test_aware_utc_time_is_displayed_in_india_standard_time():
    value = datetime(2026, 9, 3, 6, 23, tzinfo=timezone.utc)
    assert format_clinic_time(value) == "03 Sep 2026 11:53 AM"
