"""
Home aggregation (§4 Phase 4).

Home is an attention surface: four questions, four modules, each a teaser that
deep-links into its domain tab. This service assembles all four in one pass so
`GET /api/home` is a single fast round trip — it is also the future mobile
app's launch screen, so it must stay cheap (target < 200ms locally).

Every number here is computed server-side; the frontend renders, it does not
recompute (API-first, §2.1). The modules:

- training_pulse : this-week vs last-week volume + the most recent run.
- shoe_alerts    : active rotation shoes past 75% of their mileage limit,
                   worst first, with a count of matching replacement deals.
- top_deals      : the 2-3 deepest active discounts.
- activity_strip : last COROS sync, last scrape, newest deal detected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models.models import Deal, OwnedShoe, Retailer, Shoe
from app.services import activities as activities_svc
from app.services import settings as settings_svc

# A shoe enters the "alerts" module once it has burned this fraction of its
# user-set mileage limit — the retirement pipeline threshold from §4.
ALERT_THRESHOLD = 0.75


@dataclass
class LastRun:
    date: str
    distance_km: float
    source: str
    avg_pace: Optional[str] = None
    avg_hr: Optional[int] = None
    name: Optional[str] = None
    shoe: Optional[dict] = None


@dataclass
class TrainingPulse:
    this_week_km: float
    last_week_km: float
    delta_km: float               # this - last (negative = down week)
    last_run: Optional[LastRun] = None


@dataclass
class ShoeAlert:
    id: int
    brand: str
    model: str
    nickname: Optional[str]
    current_mileage: float
    mileage_limit: float
    pct: float                    # current / limit, 0..1+ (may exceed 1)
    replacement_deals: int        # active deals matching this shoe's type


@dataclass
class TopDeal:
    id: int
    brand: str
    model: str
    retailer: str
    current_price: float
    savings_percent: float
    savings_amount: float
    product_url: str
    msrp: Optional[float] = None
    image_url: Optional[str] = None
    colorway: Optional[str] = None


@dataclass
class ActivityStrip:
    last_coros_sync_at: Optional[datetime] = None
    last_scrape_at: Optional[datetime] = None
    newest_deal_at: Optional[datetime] = None
    newest_deal_label: Optional[str] = None   # "Brand Model" of the newest deal


@dataclass
class HomeSummary:
    training_pulse: TrainingPulse
    shoe_alerts: List[ShoeAlert] = field(default_factory=list)
    top_deals: List[TopDeal] = field(default_factory=list)
    activity_strip: ActivityStrip = field(default_factory=ActivityStrip)


def _week_start(d: date) -> date:
    """Monday of the ISO week containing ``d``."""
    return d - timedelta(days=d.weekday())


def _training_pulse(db: Session, today: date) -> TrainingPulse:
    """This-week vs last-week km (Monday-anchored) plus the latest run.

    Computed straight off the unioned run feed rather than the sparse weekly
    summary buckets, so a week with zero runs correctly reads 0 instead of
    silently falling through to an older populated week.
    """
    this_start = _week_start(today)
    last_start = this_start - timedelta(days=7)

    runs = activities_svc.unified_activities(db)  # newest first

    this_km = 0.0
    last_km = 0.0
    for r in runs:
        if r.date >= this_start:
            this_km += r.distance_km or 0.0
        elif last_start <= r.date < this_start:
            last_km += r.distance_km or 0.0

    last_run = None
    if runs:
        r = runs[0]
        last_run = LastRun(
            date=r.date.isoformat(),
            distance_km=round(r.distance_km or 0.0, 2),
            source=r.source,
            avg_pace=r.avg_pace,
            avg_hr=r.avg_hr,
            name=r.name,
            shoe=(
                {"id": r.shoe.id, "brand": r.shoe.brand,
                 "model": r.shoe.model, "nickname": r.shoe.nickname}
                if r.shoe else None
            ),
        )

    this_km = round(this_km, 2)
    last_km = round(last_km, 2)
    return TrainingPulse(
        this_week_km=this_km,
        last_week_km=last_km,
        delta_km=round(this_km - last_km, 2),
        last_run=last_run,
    )


def _shoe_alerts(db: Session) -> List[ShoeAlert]:
    """Active rotation shoes at/over 75% of their mileage limit, worst first.

    Replacement-deal count is the number of active deals on a tracked `Shoe`
    of the same shoe_type — a heuristic bridge between the rotation domain and
    the deals domain (there is no FK between owned_shoes and shoes)."""
    shoes = (
        db.query(OwnedShoe)
        .filter(OwnedShoe.status == "active", OwnedShoe.mileage_limit.isnot(None))
        .all()
    )

    # Active-deal counts per tracked shoe_type, computed once.
    deals_by_type: dict[str, int] = {}
    for shoe_type, cnt in (
        db.query(Shoe.shoe_type, func.count(Deal.id))
        .join(Deal, Deal.shoe_id == Shoe.id)
        .filter(Deal.is_active == True, Shoe.shoe_type.isnot(None))  # noqa: E712
        .group_by(Shoe.shoe_type)
        .all()
    ):
        deals_by_type[shoe_type.lower()] = cnt

    alerts: List[ShoeAlert] = []
    for s in shoes:
        if not s.mileage_limit:
            continue
        pct = s.current_mileage / s.mileage_limit
        if pct < ALERT_THRESHOLD:
            continue
        replacements = deals_by_type.get(s.shoe_type.lower(), 0) if s.shoe_type else 0
        alerts.append(ShoeAlert(
            id=s.id,
            brand=s.brand,
            model=s.model,
            nickname=s.nickname,
            current_mileage=round(s.current_mileage, 1),
            mileage_limit=round(s.mileage_limit, 1),
            pct=round(pct, 4),
            replacement_deals=replacements,
        ))

    alerts.sort(key=lambda a: a.pct, reverse=True)  # closest to (or past) the limit first
    return alerts


def _top_deals(db: Session, limit: int = 3) -> List[TopDeal]:
    """The deepest active discounts, biggest savings % first."""
    rows = (
        db.query(Deal)
        .filter(Deal.is_active == True)  # noqa: E712
        .order_by(desc(Deal.savings_percent))
        .limit(limit)
        .all()
    )
    out = []
    for d in rows:
        out.append(TopDeal(
            id=d.id,
            brand=d.shoe.brand,
            model=d.shoe.model,
            retailer=d.retailer.name if d.retailer else "Unknown",
            current_price=d.current_price,
            savings_percent=d.savings_percent,
            savings_amount=d.savings_amount,
            product_url=d.product_url,
            msrp=d.shoe.msrp,
            image_url=d.image_url,
            colorway=d.colorway,
        ))
    return out


def _activity_strip(db: Session) -> ActivityStrip:
    """One-line-each freshness signals: last sync, last scrape, newest deal."""
    last_sync_str = settings_svc.get_setting(db, "last_coros_sync_at")
    last_coros_sync_at = datetime.fromisoformat(last_sync_str) if last_sync_str else None

    last_scrape_at = (
        db.query(func.max(Retailer.last_scraped_at)).scalar()
    )

    newest = (
        db.query(Deal)
        .filter(Deal.is_active == True)  # noqa: E712
        .order_by(desc(Deal.detected_at))
        .first()
    )
    newest_deal_at = newest.detected_at if newest else None
    newest_deal_label = (
        f"{newest.shoe.brand} {newest.shoe.model}" if newest and newest.shoe else None
    )

    return ActivityStrip(
        last_coros_sync_at=last_coros_sync_at,
        last_scrape_at=last_scrape_at,
        newest_deal_at=newest_deal_at,
        newest_deal_label=newest_deal_label,
    )


def home_summary(db: Session, today: Optional[date] = None) -> HomeSummary:
    """Assemble all four Home modules in one pass."""
    today = today or date.today()
    return HomeSummary(
        training_pulse=_training_pulse(db, today),
        shoe_alerts=_shoe_alerts(db),
        top_deals=_top_deals(db),
        activity_strip=_activity_strip(db),
    )
