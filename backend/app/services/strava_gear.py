"""
Gear-name → owned-shoe auto-matching for the Strava import (§3).

Pure functions, no DB — the seed script (app/scripts/seed_gear_mappings.py)
wraps these. Matching is deliberately conservative: a gear string only
auto-matches when its normalized form is EXACTLY one owned shoe's normalized
model / nickname / brand+model / brand+nickname. Anything ambiguous (matches
more than one shoe) or unmatched is left for a human — cheaper than a wrong
auto-attribution that silently double-counts mileage later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

# Brand prefixes stripped before comparison, so "Adidas Evo SL Teal" and an
# owned shoe whose nickname is just "Evo SL Teal" line up.
_BRAND_PREFIXES = (
    "new balance",
    "under armour",
    "adidas",
    "nike",
    "mizuno",
    "puma",
    "asics",
    "hoka",
    "saucony",
    "brooks",
    "on",
)


def normalize_gear(text: Optional[str]) -> str:
    """lowercase → strip a known brand prefix → collapse whitespace."""
    if not text:
        return ""
    s = text.strip().lower()
    for brand in _BRAND_PREFIXES:
        if s.startswith(brand + " "):
            s = s[len(brand) + 1:]
            break
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class ShoeLike:
    """Minimal owned-shoe shape the matcher needs (kept DB-agnostic for tests)."""
    id: int
    brand: str
    model: str
    nickname: Optional[str] = None


def candidate_keys(shoe: ShoeLike) -> set[str]:
    """Every normalized string a gear name could legitimately equal for this shoe."""
    keys = {
        normalize_gear(shoe.model),
        normalize_gear(f"{shoe.brand} {shoe.model}"),
    }
    if shoe.nickname:
        keys.add(normalize_gear(shoe.nickname))
        keys.add(normalize_gear(f"{shoe.brand} {shoe.nickname}"))
    keys.discard("")
    return keys


@dataclass
class MatchResult:
    matched: dict[str, int]          # gear_name -> owned_shoe_id (unique match)
    ambiguous: dict[str, list[int]]  # gear_name -> [candidate shoe ids]
    unmatched: list[str]             # gear_name with no candidate


def auto_match(gear_names: Iterable[str], shoes: Iterable[ShoeLike]) -> MatchResult:
    """
    Match each gear name to at most one owned shoe by exact normalized-key
    equality. A gear that resolves to >1 shoe is 'ambiguous'; 0 shoes is
    'unmatched'. Neither gets written as a real mapping by the seeder.
    """
    shoe_list = list(shoes)
    matched: dict[str, int] = {}
    ambiguous: dict[str, list[int]] = {}
    unmatched: list[str] = []

    for gear in gear_names:
        norm = normalize_gear(gear)
        hits = [s.id for s in shoe_list if norm and norm in candidate_keys(s)]
        if len(hits) == 1:
            matched[gear] = hits[0]
        elif len(hits) > 1:
            ambiguous[gear] = hits
        else:
            unmatched.append(gear)

    return MatchResult(matched=matched, ambiguous=ambiguous, unmatched=unmatched)
