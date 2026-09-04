"""Single source of truth for registration beneficiary/scheme categories."""

# (stable stored value, human-readable label) — order controls display order everywhere.
SELECTABLE_CATEGORIES: list[tuple[str, str]] = [
    ("CGHS", "Central Government Health Scheme (CGHS)"),
    ("ECHS", "Ex-Servicemen Contributory Health Scheme (ECHS)"),
    ("CAPF", "Central Armed Police Forces (CAPF)"),
    ("CISF", "Central Industrial Security Force (CISF)"),
    ("DU", "Delhi University (DU)"),
    ("NHAI", "National Highways Authority of India (NHAI)"),
    ("NOT_APPLICABLE", "No scheme/category applies"),
]

UNSPECIFIED_CATEGORY: tuple[str, str] = ("UNSPECIFIED", "Unspecified (legacy record)")

# All stored values, including the backfill-only legacy value, for analytics/CSV/constraints.
ALL_CATEGORIES: list[tuple[str, str]] = SELECTABLE_CATEGORIES + [UNSPECIFIED_CATEGORY]

SELECTABLE_VALUES: set[str] = {value for value, _ in SELECTABLE_CATEGORIES}
ALL_VALUES: set[str] = {value for value, _ in ALL_CATEGORIES}

CATEGORY_LABELS: dict[str, str] = dict(ALL_CATEGORIES)
