"""
Deal alert service — detects new deal events since a given timestamp (R3.2).

Three event types:
  - NewDealAlert: a tracked shoe's price fell below its MSRP for the first
    time (or re-qualified) after the reference timestamp.
  - PriceDropAlert: an existing active deal got cheaper since the reference
    timestamp — subsequent scrape found a lower price.
  - ReplacementDealAlert: a shoe in the retirement pipeline (≥ 75% mileage)
    has new type-matching deals detected since the reference timestamp.

The caller (the MCP tool `get_deal_alerts`) owns the high-water mark in
`AppSettings`; this service is purely functional so tests inject `since`
directly without touching the settings table. All datetimes are naive UTC
(SQLite stores all timestamps without timezone info).

Cross-domain note: replacement alerts bridge the deals domain (Shoe + Deal)
and the rotation domain (OwnedShoe) via the shoe_type string heuristic —
the same join the home service uses for shoe alerts (CLAUDE.md §1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.models import Deal, PriceRecord, Shoe
from app.services import rotation


@dataclass
class NewDealAlert:
    """A tracked shoe became an active deal since the last check."""
    deal_id: int
    brand: str
    model: str
    shoe_type: Optional[str]
    retailer: str
    current_price: float
    msrp: float
    savings_percent: float
    savings_amount: float
    detected_at: str   # naive UTC ISO
    product_url: str


@dataclass
class PriceDropAlert:
    """An existing active deal had its price lowered since the last check."""
    deal_id: int
    brand: str
    model: str
    retailer: str
    old_price: float
    new_price: float
    drop_amount: float
    drop_percent: float   # (old − new) / old * 100
    msrp: float
    savings_percent: float  # at the new (lower) price
    scraped_at: str         # naive UTC ISO — when the new lower price was first seen
    product_url: str


@dataclass
class ReplacementDealAlert:
    """A pipeline shoe (≥ 75% mileage) has new same-type deals available."""
    owned_shoe_id: int
    brand: str
    model: str
    nickname: Optional[str]
    pct: float           # current_mileage / mileage_limit (0..1+)
    shoe_type: str
    new_deals: list[dict]  # compact deal dicts for each new type-matching deal


@dataclass
class DealAlertDigest:
    """Structured alert digest returned by deal_alerts() and consumed by get_deal_alerts."""
    since: Optional[str]           # reference timestamp used (None = first run)
    checked_at: str                # naive UTC ISO — when this check ran
    first_run: bool                # True when since was None (7-day default applied)
    new_deals: list[NewDealAlert] = field(default_factory=list)
    price_drops: list[PriceDropAlert] = field(default_factory=list)
    replacement_alerts: list[ReplacementDealAlert] = field(default_factory=list)

    @property
    def has_alerts(self) -> bool:
        return bool(self.new_deals or self.price_drops or self.replacement_alerts)


# First-run default window when no high-water mark exists.
FIRST_RUN_DAYS = 7


def deal_alerts(
    db: Session,
    *,
    since: Optional[datetime] = None,
    _now: Optional[datetime] = None,   # injectable for clock-independent tests
) -> DealAlertDigest:
    """
    Compile deal alert events since `since` (naive UTC).

    If `since` is None (first run), defaults the window to the last
    FIRST_RUN_DAYS (7) days and sets first_run=True in the digest.

    All datetime comparisons are against naive UTC values because SQLite
    stores server-default timestamps without timezone information.
    """
    now = _now or datetime.utcnow()

    if since is None:
        effective_since = now - timedelta(days=FIRST_RUN_DAYS)
        first_run = True
    else:
        effective_since = since
        first_run = False

    # 1 — New active deals first detected since effective_since
    new_deal_rows = (
        db.query(Deal)
        .filter(Deal.is_active == True, Deal.detected_at > effective_since)  # noqa: E712
        .order_by(desc(Deal.savings_percent))
        .all()
    )
    new_deals = [
        NewDealAlert(
            deal_id=d.id,
            brand=d.shoe.brand,
            model=d.shoe.model,
            shoe_type=d.shoe.shoe_type,
            retailer=d.retailer.name,
            current_price=d.current_price,
            msrp=d.shoe.msrp,
            savings_percent=d.savings_percent,
            savings_amount=d.savings_amount,
            detected_at=d.detected_at.isoformat() if d.detected_at else "",
            product_url=d.product_url,
        )
        for d in new_deal_rows
    ]

    # 2 — Price drops on pre-existing active deals
    price_drops = _find_price_drops(db, effective_since)

    # 3 — Replacement alerts: pipeline shoes with new same-type deals
    replacement_alerts = _find_replacement_alerts(db, effective_since)

    return DealAlertDigest(
        since=since.isoformat() if since is not None else None,
        checked_at=now.isoformat(),
        first_run=first_run,
        new_deals=new_deals,
        price_drops=price_drops,
        replacement_alerts=replacement_alerts,
    )


def _find_price_drops(db: Session, effective_since: datetime) -> list[PriceDropAlert]:
    """
    Detect price drops on pre-existing active deals.

    A price drop exists when:
    - There is a PriceRecord scraped AFTER effective_since at a lower price
      than the most recent PriceRecord scraped AT OR BEFORE effective_since.
    - The deal for that (shoe, retailer) pair was detected BEFORE effective_since
      (newly detected deals are already in new_deals — no double-counting).

    Multiple new records per (shoe, retailer) pair are collapsed to the minimum
    new price. At most one drop is reported per deal. O(new_records) reference
    lookups — acceptable at personal scale (dozens of deals, pages of records).
    """
    new_recs = (
        db.query(PriceRecord)
        .filter(PriceRecord.scraped_at > effective_since)
        .all()
    )
    if not new_recs:
        return []

    # Index pre-existing active deals: (shoe_id, retailer_id) → Deal
    active_deals = {
        (d.shoe_id, d.retailer_id): d
        for d in (
            db.query(Deal)
            .filter(Deal.is_active == True, Deal.detected_at <= effective_since)  # noqa: E712
            .all()
        )
    }
    if not active_deals:
        return []

    # Collapse new records to min price per (shoe_id, retailer_id)
    min_new: dict[tuple[int, int], PriceRecord] = {}
    for rec in new_recs:
        key = (rec.shoe_id, rec.retailer_id)
        if key not in min_new or rec.price < min_new[key].price:
            min_new[key] = rec

    drops: list[PriceDropAlert] = []
    seen_deals: set[int] = set()

    for (shoe_id, retailer_id), new_rec in min_new.items():
        deal = active_deals.get((shoe_id, retailer_id))
        if deal is None or deal.id in seen_deals:
            continue

        # Reference price: most recent record at or before effective_since
        ref_rec = (
            db.query(PriceRecord)
            .filter(
                PriceRecord.shoe_id == shoe_id,
                PriceRecord.retailer_id == retailer_id,
                PriceRecord.scraped_at <= effective_since,
            )
            .order_by(desc(PriceRecord.scraped_at))
            .first()
        )
        if ref_rec is None or new_rec.price >= ref_rec.price:
            continue

        drop_amount = ref_rec.price - new_rec.price
        drop_percent = drop_amount / ref_rec.price * 100
        seen_deals.add(deal.id)
        drops.append(
            PriceDropAlert(
                deal_id=deal.id,
                brand=deal.shoe.brand,
                model=deal.shoe.model,
                retailer=deal.retailer.name,
                old_price=ref_rec.price,
                new_price=new_rec.price,
                drop_amount=drop_amount,
                drop_percent=drop_percent,
                msrp=deal.shoe.msrp,
                savings_percent=deal.savings_percent,
                scraped_at=new_rec.scraped_at.isoformat() if new_rec.scraped_at else "",
                product_url=deal.product_url,
            )
        )

    # Largest drop first
    return sorted(drops, key=lambda d: d.drop_amount, reverse=True)


def _find_replacement_alerts(
    db: Session,
    effective_since: datetime,
) -> list[ReplacementDealAlert]:
    """
    Find pipeline shoes with new type-matching deals.

    For each shoe in the retirement pipeline (≥ 75% of mileage_limit) that
    has a shoe_type set, report any active deals on tracked shoes of the same
    type that were first detected after effective_since. The cross-domain
    bridge (OwnedShoe ↔ Shoe via shoe_type string) is deliberate — see
    CLAUDE.md §1 and domain_model §4.3.
    """
    pipeline = rotation.retirement_pipeline(db)
    if not pipeline:
        return []

    alerts: list[ReplacementDealAlert] = []
    seen_owned: set[int] = set()

    for entry in pipeline:
        owned = entry.shoe
        if not owned.shoe_type or owned.id in seen_owned:
            continue

        new_type_deals = (
            db.query(Deal)
            .join(Shoe, Deal.shoe_id == Shoe.id)
            .filter(
                Deal.is_active == True,  # noqa: E712
                Shoe.shoe_type == owned.shoe_type,
                Deal.detected_at > effective_since,
            )
            .order_by(desc(Deal.savings_percent))
            .all()
        )
        if not new_type_deals:
            continue

        seen_owned.add(owned.id)
        alerts.append(
            ReplacementDealAlert(
                owned_shoe_id=owned.id,
                brand=owned.brand,
                model=owned.model,
                nickname=owned.nickname,
                pct=entry.pct,
                shoe_type=owned.shoe_type,
                new_deals=[
                    {
                        "deal_id": d.id,
                        "brand": d.shoe.brand,
                        "model": d.shoe.model,
                        "retailer": d.retailer.name,
                        "current_price": d.current_price,
                        "savings_percent": d.savings_percent,
                        "product_url": d.product_url,
                    }
                    for d in new_type_deals
                ],
            )
        )

    return alerts
