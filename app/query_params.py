def optional_int(value: str | None) -> int | None:
    """Treat a blank query-string value (e.g. an unselected 'All ...' filter dropdown) as absent."""
    if value is None:
        return None
    value = value.strip()
    return int(value) if value.isdigit() else None
