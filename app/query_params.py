def optional_int(value: str | None) -> int | None:
    """Treat a blank query-string value (e.g. an unselected 'All ...' filter dropdown) as absent."""
    if value is None:
        return None
    value = value.strip()
    return int(value) if value.isdigit() else None


def optional_date(value: str | None):
    """Treat a blank or malformed query-string date (e.g. a hand-edited URL) as absent rather than raising."""
    from datetime import date
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
