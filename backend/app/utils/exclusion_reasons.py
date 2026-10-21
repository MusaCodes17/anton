"""The "excluded from analysis" reason vocabulary — backend-owned source of
truth (R11.4). Pure: no app imports, so the model layer, services and the
router (which builds its 422-validated `Literal` from it) can all import it.

`activities.exclude_reason` is a closed list on purpose: a run is excluded
because the *data* is wrong or doesn't belong (bad GPS, not a run, a double
import, a miscalibrated treadmill), and the reason is what lets a later
session audit "why did this estimate ignore that run?". Free text goes in
`exclude_note`, not here. Do NOT grow this list casually — like activity tags,
a new reason is a data-model change.
"""
from __future__ import annotations

# Ordered for display. The string values are the stored/served canonical form.
EXCLUDE_REASONS: tuple[str, ...] = (
    "gps_error",
    "wrong_sport",
    "duplicate",
    "treadmill_calibration",
    "other",
)
