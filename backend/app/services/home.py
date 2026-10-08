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

from app.models.models import Deal, Retailer
from app.services import activities as activities_svc
from app.services import rotation as rotation_svc
from app.services import settings as settings_svc


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
    forecast_status: str = "idle"                 # on_track | idle | overdue (R6.2)
    weekly_km: float = 0.0
    weeks_to_limit: Optional[float] = None
    projected_limit_date: Optional[str] = None


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

    Thin projection over the shared ``rotation.retirement_pipeline`` — the same
    computation backs the /shoes lifecycle view, so Home and Shoes never
    disagree about which shoes are past the threshold or how many replacement
    deals exist."""
    return [
        ShoeAlert(
            id=e.shoe.id,
            brand=e.shoe.brand,
            model=e.shoe.model,
            nickname=e.shoe.nickname,
            current_mileage=e.current_mileage,
            mileage_limit=e.mileage_limit,
            pct=e.pct,
            replacement_deals=e.replacement_deals,
            forecast_status=e.forecast_status,
            weekly_km=e.weekly_km,
            weeks_to_limit=e.weeks_to_limit,
            projected_limit_date=e.projected_limit_date,
        )
        for e in rotation_svc.retirement_pipeline(db)
    ]


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
