"""
Shared schema helpers used by more than one domain module under
`app.models.schemas`: the `shoe_type` and owned-shoe `status` write validators
and the owned-shoe status vocabulary. Read schemas deliberately do not validate.
"""
from typing import Optional

from app.utils.shoe_types import SHOE_TYPES, is_valid_shoe_type


def validate_optional_shoe_type(v: Optional[str]) -> Optional[str]:
    """Shared `shoe_type` validator for the write schemas (R2.4): `None`/`""`
    clears the type; any other value must be a member of the backend-owned
    vocabulary (`app.utils.shoe_types.SHOE_TYPES`). Rejects typos that used to
    fail silently at the cross-domain join. Read schemas deliberately do NOT
    validate — legacy data must never break a GET."""
    if v is None or v == "":
        return None
    if not is_valid_shoe_type(v):
        raise ValueError(
            f"Invalid shoe_type '{v}'. Use one of: {', '.join(SHOE_TYPES)} (or omit)."
        )
    return v


# Owned-shoe status vocabulary (T3) — the closed set for OwnedShoe.status.
# Kept here (its only consumer today) rather than a pure util, unlike SHOE_TYPES
# which several layers import; extract if a second consumer appears (A5).
OWNED_SHOE_STATUSES: tuple[str, ...] = ("active", "retired", "for_sale")


def validate_owned_shoe_status(v: Optional[str]) -> Optional[str]:
    """Shared `status` validator for the owned-shoe write schemas (T3): `None`
    means 'unchanged' on update; any provided value must be a member of
    OWNED_SHOE_STATUSES. Rejects off-vocab typos with a 422 instead of silently
    persisting an unknown status. Read schemas do NOT validate — legacy data
    must never break a GET (mirrors `validate_optional_shoe_type`)."""
    if v is None:
        return v
    if v not in OWNED_SHOE_STATUSES:
        raise ValueError(
            f"Invalid status '{v}'. Use one of: {', '.join(OWNED_SHOE_STATUSES)}."
        )
    return v
