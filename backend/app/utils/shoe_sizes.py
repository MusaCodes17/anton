"""
Shoe-size label normalisation and the "does this deal come in my size?" rule (R6.3).

Scrapers store ``sizes_available`` as retailer-specific string labels. Sampled
from the live DB (2026-10-08) the formats are: plain numbers (``"9"``,
``"9.5"``), the same size written with a trailing ``.0`` (``"9.0"``), and
unisex "men's / women's" pairs (``"10 / 11.5"``). Youth sizes are already
excluded at scrape time. Nothing else was observed — extend ``parse_size_label``
(and its tests) if a new format shows up rather than guessing ahead.
"""
from __future__ import annotations

from typing import Optional

# A size preference outside this range is almost certainly a typo, not a shoe.
MIN_SIZE = 3.0
MAX_SIZE = 16.0

IN = "in"
OUT = "out"
UNKNOWN = "unknown"


def parse_size_label(label) -> Optional[float]:
    """
    Parse one scraped size label to a comparable number, or None if unparseable.

    ``"9"``/``"9.0"``/``" 9.5 "`` → the number. A unisex pair ``"10 / 11.5"``
    resolves to its FIRST value — heuristic: retailers list men's before
    women's, and the runner's preference is a men's size.
    """
    if label is None:
        return None
    first = str(label).split("/")[0].strip()
    try:
        return float(first)
    except ValueError:
        return None


def parse_preferred_size(value) -> float:
    """
    Validate a user-entered preference: a number in half-size steps within
    [MIN_SIZE, MAX_SIZE].

    Raises:
        ValueError: on non-numeric input, a non-half step, or out of range.
    """
    try:
        size = float(str(value).strip())
    except ValueError:
        raise ValueError(f"'{value}' is not a shoe size")
    if size * 2 != int(size * 2):
        raise ValueError("Shoe size must be a whole or half size (e.g. 10 or 10.5)")
    if not MIN_SIZE <= size <= MAX_SIZE:
        raise ValueError(f"Shoe size must be between {MIN_SIZE:g} and {MAX_SIZE:g}")
    return size


def size_fit(sizes_available, preferred: Optional[float]) -> Optional[str]:
    """
    Classify a deal against the preferred size: ``"in"``, ``"out"`` or ``"unknown"``.

    Returns None when no preference is set (callers then skip size logic
    entirely, so behaviour is unchanged). Empty/missing/unparseable
    ``sizes_available`` is ``"unknown"`` — "maybe", never silently hidden.
    """
    if preferred is None:
        return None
    parsed = [p for p in (parse_size_label(s) for s in (sizes_available or [])) if p is not None]
    if not parsed:
        return UNKNOWN
    return IN if preferred in parsed else OUT
