"""The shoe-type controlled vocabulary — the backend-owned source of truth
(R2.4). Pure: no app imports, so models, schemas, services, routers, and the MCP
layer can all import it, and the frontend receives the list from one endpoint
(`GET /api/shoe-types`) instead of keeping its own copy (`lib/shoeTypes.js` is
reduced to presentation-only badge colours).

`shoe_type` is **schema-grade**: it is the cross-domain join key between the two
deliberately-independent domains — a `Shoe` (wanting) and an `OwnedShoe` (owning)
meet only through this string (domain_model §4.3/§5.1). A typo used to fail
*silently* (the replacement-deals join simply found nothing). This vocabulary +
the write-schema validation closes that. Do NOT grow this list casually — a new
type is a data-model change, and both domains must agree on the exact strings.

Values are lowercase snake_case (the stored/served canonical form); display
labels are derived on the frontend by title-casing (a pure presentation concern),
so this module owns *which types exist*, not how they're spelled for humans.
"""
from __future__ import annotations

from typing import Optional

# Ordered for display. Canonical stored/served values.
SHOE_TYPES: tuple[str, ...] = (
    "long_distance_racer",
    "short_distance_racer",
    "long_run",
    "tempo",
    "intervals",
    "daily_trainer",
    "trail",
    "recovery",
)

_VALID = set(SHOE_TYPES)


def is_valid_shoe_type(shoe_type: Optional[str]) -> bool:
    """True iff `shoe_type` is a member of the vocabulary. `None` is not valid
    here — callers that allow clearing/omitting the type handle `None`/`""`
    explicitly (see `schemas.validate_optional_shoe_type`)."""
    return shoe_type in _VALID
