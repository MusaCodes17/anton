"""
Database models using SQLAlchemy ORM
"""
from sqlalchemy import BigInteger, Column, Index, Integer, String, Float, Boolean, DateTime, Date, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.utils.pace import seconds_to_pace  # pure util (R1.5c) — no layer inversion


class Shoe(Base):
    """
    Model for tracking specific running shoes we want to monitor
    """
    __tablename__ = "shoes"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String(100), nullable=False, index=True)  # e.g., "Adidas", "Nike"
    model = Column(String(200), nullable=False, index=True)  # e.g., "Adizero Adios Pro 3"
    shoe_type = Column(String(50), nullable=True)  # e.g. "long_distance_racer"
    # Size intentionally removed: we track a model across ALL sizes so the
    # scraper isn't restricted to one exact size that may be out of stock.
    # MSRP drives deal qualification: a deal exists when a retailer's price is
    # below this list price, and savings % is measured against it (see
    # DealStore.upsert_deal / orchestrator). Nullable so a shoe can be tracked
    # before its MSRP is known — but such a shoe can't produce deals until set.
    msrp = Column(Float, nullable=True)  # Manufacturer's list price — the deal reference
    # target_price is now an optional personal "ping me at this price" threshold.
    # It no longer affects qualification or savings — MSRP does. Kept nullable so
    # it can be omitted entirely.
    target_price = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)  # Any additional notes
    is_active = Column(Boolean, default=True)  # Whether to actively monitor this shoe
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    price_records = relationship("PriceRecord", back_populates="shoe", cascade="all, delete-orphan")
    deals = relationship("Deal", back_populates="shoe", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Shoe {self.brand} {self.model}>"


class Retailer(Base):
    """
    Model for trusted Canadian retailers to scrape
    """
    __tablename__ = "retailers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)  # e.g., "The Last Hunt"
    base_url = Column(String(500), nullable=False)  # e.g., "https://www.thelasthunt.com"
    is_active = Column(Boolean, default=True)  # Whether this retailer is enabled
    scraping_enabled = Column(Boolean, default=True)  # Whether to scrape this retailer
    # Platform backing this retailer's storefront. "shopify"/"algolia" retailers get a
    # generic scraper built automatically (see registry.build_dynamic_scraper);
    # "custom" means no scraper exists yet and scraping stays disabled. Existing rows
    # default to "custom" — they keep working via their hardcoded subclass scrapers,
    # which are looked up by name first regardless of this column.
    platform = Column(String(20), nullable=False, default="custom", server_default="custom")
    last_scraped_at = Column(DateTime(timezone=True), nullable=True)
    # Store CSS selectors, patterns, AND (for platform="algolia") the credentials
    # algolia_app_id / algolia_api_key / algolia_index / algolia_product_path.
    scraper_config = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    price_records = relationship("PriceRecord", back_populates="retailer", cascade="all, delete-orphan")
    deals = relationship("Deal", back_populates="retailer", cascade="all, delete-orphan")
    promo_codes = relationship("PromoCode", back_populates="retailer", cascade="all, delete-orphan")
    scrape_runs = relationship("ScrapeRun", back_populates="retailer", cascade="all, delete-orphan")

    @property
    def active_promo_codes(self):
        """Active promo codes only, newest first — used in API responses."""
        return sorted(
            [c for c in self.promo_codes if c.is_active],
            key=lambda c: c.detected_at or 0,
            reverse=True,
        )

    def __repr__(self):
        return f"<Retailer {self.name}>"


class PriceRecord(Base):
    """
    Historical price records for shoes at different retailers
    """
    __tablename__ = "price_records"

    id = Column(Integer, primary_key=True, index=True)
    shoe_id = Column(Integer, ForeignKey("shoes.id"), nullable=False, index=True)
    retailer_id = Column(Integer, ForeignKey("retailers.id"), nullable=False, index=True)
    product_url = Column(Text, nullable=False)  # Direct link to the product
    price = Column(Float, nullable=False)
    original_price = Column(Float, nullable=True)  # Original price if on sale
    in_stock = Column(Boolean, default=True)
    size_available = Column(Boolean, default=True)  # Whether at least one size is in stock
    sizes_available = Column(JSON, nullable=True)  # e.g. ["8", "8.5", "9", "10"] — None for pre-migration rows
    image_url = Column(Text, nullable=True)  # Product image (direct CDN URL)
    colorway = Column(String(200), nullable=True)  # e.g. "Black / White - Grey"
    scraped_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    shoe = relationship("Shoe", back_populates="price_records")
    retailer = relationship("Retailer", back_populates="price_records")

    def __repr__(self):
        return f"<PriceRecord {self.shoe_id} @ {self.retailer_id}: ${self.price}>"


class Deal(Base):
    """
    Active deals when a retailer's price drops below the shoe's MSRP.

    savings_amount / savings_percent are measured against MSRP (msrp - price).
    target_price is a reference snapshot of the shoe's optional threshold at
    detection time; it no longer affects qualification or savings.
    """
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)
    shoe_id = Column(Integer, ForeignKey("shoes.id"), nullable=False, index=True)
    retailer_id = Column(Integer, ForeignKey("retailers.id"), nullable=False, index=True)
    current_price = Column(Float, nullable=False)
    target_price = Column(Float, nullable=True)  # optional threshold snapshot (not used in math)
    savings_amount = Column(Float, nullable=False)  # msrp - price
    savings_percent = Column(Float, nullable=False)  # (msrp - price) / msrp * 100
    product_url = Column(Text, nullable=False)
    in_stock = Column(Boolean, default=True)
    sizes_available = Column(JSON, nullable=True)  # e.g. ["8", "8.5", "9", "10"] — None for pre-migration rows
    image_url = Column(Text, nullable=True)  # Product image (direct CDN URL)
    colorway = Column(String(200), nullable=True)  # e.g. "Black / White - Grey"
    is_active = Column(Boolean, default=True, index=True)  # Whether deal is still valid
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiry

    # Relationships
    shoe = relationship("Shoe", back_populates="deals")
    retailer = relationship("Retailer", back_populates="deals")

    def __repr__(self):
        return f"<Deal {self.shoe_id} @ {self.retailer_id}: ${self.current_price} (Save {self.savings_percent}%)>"


class PromoCode(Base):
    """
    Discount / coupon codes for a retailer (e.g. "Extra 20% off with 20FOR200").

    Codes are either auto-detected from a retailer's site during scraping
    (source="scraped") or added manually by the user (source="manual").
    """
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    retailer_id = Column(Integer, ForeignKey("retailers.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)  # e.g. "20FOR200"
    description = Column(Text, nullable=True)  # e.g. "Extra 20% off orders over $200"
    discount_percent = Column(Float, nullable=True)  # e.g. 20.0
    discount_amount = Column(Float, nullable=True)  # flat dollar discount, if any
    source = Column(String(20), default="scraped")  # "scraped" | "manual"
    source_url = Column(Text, nullable=True)  # page the code was found on
    is_active = Column(Boolean, default=True, index=True)
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    retailer = relationship("Retailer", back_populates="promo_codes")

    def __repr__(self):
        return f"<PromoCode {self.code} @ {self.retailer_id}>"


class ScrapeRun(Base):
    """
    Observability record for a single retailer's scrape attempt (R2.5).

    Grain is **one row per retailer per full-catalog scrape attempt** — the
    unit that answers "is Altitude quietly broken?": a run that finishes
    `success` with `products_found == 0` is the tell-tale, distinct from one
    that finishes `error`. Written only by the orchestrator's
    `scrape_retailer()` (the single sanctioned write path); read by
    `services/scrape_history.py`.

    This is deals-domain telemetry — **disposable**, cascade-deleted with its
    retailer (CLAUDE.md §2.6: history is sacred in training, disposable in
    deals). It is *not* the SSE `scrape_state`, which is in-memory and dies on
    restart; this table is the durable trend R4.1/R4.5 will build on.
    """
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, index=True)
    retailer_id = Column(Integer, ForeignKey("retailers.id"), nullable=False, index=True)
    # A run is stamped "running" on creation and committed immediately so an
    # in-flight (or crashed-mid-scrape) attempt is visible, then finalized to
    # "success" | "error" when the retailer's shoe list is exhausted.
    status = Column(String(20), nullable=False, default="running", server_default="running")
    # How the scrape was triggered — "background" (POST /scrape/all),
    # "manual" (POST /scrape/retailer/{id}); "scheduled" arrives with R4.1.
    trigger = Column(String(20), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    shoes_scraped = Column(Integer, nullable=False, default=0)
    products_found = Column(Integer, nullable=False, default=0)
    prices_recorded = Column(Integer, nullable=False, default=0)
    deals_found = Column(Integer, nullable=False, default=0)
    # Joined per-item error strings (truncated) when status == "error"; NULL on
    # a clean run. Not a stack trace — a human-readable "what went wrong".
    error = Column(Text, nullable=True)

    # Relationships
    retailer = relationship("Retailer", back_populates="scrape_runs")

    def __repr__(self):
        return f"<ScrapeRun {self.retailer_id} {self.status} products={self.products_found}>"


class OwnedShoe(Base):
    """
    A shoe in the user's personal rotation — separate from `Shoe` (which is
    for deal-tracking). Owning a shoe and watching it for deals are
    independent: an owned shoe may have no corresponding tracked `Shoe` row,
    and vice versa.
    """
    __tablename__ = "owned_shoes"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String(100), nullable=False, index=True)
    model = Column(String(200), nullable=False, index=True)
    nickname = Column(String(100), nullable=True)  # e.g. "Race day Adios"
    shoe_type = Column(String(50), nullable=True)  # e.g. "Tempo shoe"
    purchase_date = Column(Date, nullable=True)
    starting_mileage = Column(Float, nullable=False, default=0)  # km already on the shoe when added
    current_mileage = Column(Float, nullable=False, default=0)  # starting_mileage + sum(runs)
    status = Column(String(20), nullable=False, default="active")  # active | retired | for_sale
    purchase_price = Column(Float, nullable=True)  # what was paid; cost-per-km is derived, not stored
    mileage_limit = Column(Float, nullable=True)   # km at which this shoe should be retired (user-set)
    image_url = Column(Text, nullable=True)  # manually-set product image; overrides any auto-matched image
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    runs = relationship("ShoeRun", back_populates="owned_shoe", cascade="all, delete-orphan")
    notes_entries = relationship("ShoeNote", back_populates="owned_shoe", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<OwnedShoe {self.brand} {self.model} ({self.current_mileage}km)>"


class Activity(Base):
    """
    Canonical record of a single physical activity — the one place every run
    lives (§3 Phase-5). Supersedes the old two-store split of
    `strava_activities` + data-bearing `shoe_runs`: a Strava-export run, a
    COROS-synced run, and a manually-logged run are all just Activity rows,
    distinguished by `source`. `shoe_runs` now merely *attributes* an activity
    to an owned shoe.

    Columns are a superset of the old `strava_activities` schema so the frozen
    bulk-export archive survives intact (raw_json, fit_filename, cadence, ...).
    External ids are the dedup/idempotency keys: `strava_activity_id` for
    re-imports, `coros_activity_id` for COROS sync. Pace is stored as
    seconds-per-km (int); formatting to "M:SS/km" happens at the boundary.
    """
    __tablename__ = "activities"
    # R2.3: composite index serving the unified_activities read path — every
    # feed query filters activity_type == "Run" and orders/ranges on run_date.
    __table_args__ = (
        Index("ix_activities_type_run_date", "activity_type", "run_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(20), nullable=False, index=True)  # strava | coros | manual
    activity_type = Column(String(50), nullable=True, index=True)  # Run / Ride / Walk / ...
    name = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)  # also holds per-run manual notes
    started_at_utc = Column(DateTime, nullable=True)
    started_at_local = Column(DateTime, nullable=True)
    run_date = Column(Date, nullable=True, index=True)  # local calendar date — dedup/match key
    distance_km = Column(Float, nullable=True)
    moving_time_s = Column(Integer, nullable=True)
    elapsed_time_s = Column(Integer, nullable=True)
    avg_hr = Column(Integer, nullable=True)
    max_hr = Column(Integer, nullable=True)
    avg_pace_s_per_km = Column(Integer, nullable=True)
    elevation_gain_m = Column(Float, nullable=True)
    avg_cadence = Column(Float, nullable=True)
    calories = Column(Float, nullable=True)
    # Training depth (R2.7 T1). All nullable — existing rows stay untagged/unscored.
    training_load = Column(Float, nullable=True)  # COROS training-load score; null if unavailable
    training_focus = Column(String(50), nullable=True)  # coaching label, e.g. "Aerobic base"
    # Controlled vocabulary (app/utils/activity_tags.py, ACTIVITY_TAGS) — the
    # governing input for PB eligibility (R2.7 T3), race promotion (T6), and the
    # weekly-summary agent (R3.1). Indexed: the PB query filters on it.
    activity_tag = Column(String(30), nullable=True, index=True)
    best_km_pace_s = Column(Integer, nullable=True)  # best consecutive-km pace within the run (s/km); null if <1km
    strava_activity_id = Column(BigInteger, nullable=True, unique=True, index=True)
    coros_activity_id = Column(String(100), nullable=True, index=True)
    gear_name = Column(String(200), nullable=True, index=True)
    fit_filename = Column(String(300), nullable=True)
    grade_adjusted_distance_m = Column(Float, nullable=True)
    raw_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # One attribution at most (a run is worn by one shoe).
    attribution = relationship(
        "ShoeRun", back_populates="activity", uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Activity {self.id} {self.source} {self.activity_type} {self.run_date}>"


class ShoeRun(Base):
    """
    Attribution row (§3 Phase-5): links a canonical `Activity` to the owned
    shoe it was run in. Run data (distance, date, pace, HR, source) lives on
    the Activity — this table answers only "which shoe ran it". `activity_id`
    is unique: an activity is attributed to at most one shoe.

    Retained as `shoe_runs` (not renamed) so the many owned-shoe relationships,
    mileage accounting, and response shapes keep working; readers join through
    to the activity for the run fields.
    """
    __tablename__ = "shoe_runs"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False, unique=True, index=True)
    owned_shoe_id = Column(Integer, ForeignKey("owned_shoes.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    owned_shoe = relationship("OwnedShoe", back_populates="runs")
    activity = relationship("Activity", back_populates="attribution")

    # Read-only proxies to the canonical activity — so response schemas
    # (ShoeRunResponse via from_attributes) and any run-field reader keep
    # working now that run data lives on `activities` (§3 Phase-5).
    #
    # WARNING: distance_km, run_date, source, avg_pace, avg_hr, notes,
    # coros_activity_id are property proxies onto self.activity.
    # They trigger a lazy load per row if activity is not eager-loaded.
    # Use joinedload/contains_eager(ShoeRun.activity) at every list query seam.
    # They also CANNOT be used in .filter() — query Activity columns instead.
    @property
    def distance_km(self):
        return self.activity.distance_km if self.activity else None

    @property
    def run_date(self):
        return self.activity.run_date if self.activity else None

    @property
    def source(self):
        return self.activity.source if self.activity else None

    @property
    def avg_hr(self):
        return self.activity.avg_hr if self.activity else None

    @property
    def coros_activity_id(self):
        return self.activity.coros_activity_id if self.activity else None

    @property
    def notes(self):
        return self.activity.description if self.activity else None

    @property
    def avg_pace(self):
        s = self.activity.avg_pace_s_per_km if self.activity else None
        return seconds_to_pace(s) if s is not None else None

    def __repr__(self):
        return f"<ShoeRun activity={self.activity_id} shoe={self.owned_shoe_id}>"


class ShoeNote(Base):
    """
    A journal entry about an owned shoe — replaces the old single `notes`
    free-text column with a timestamped, mileage-anchored history. Entries
    are either written by hand (`triggered_by="manual"`) or prompted by a
    100km mileage checkpoint (`triggered_by="checkpoint"`).
    """
    __tablename__ = "shoe_notes"

    id = Column(Integer, primary_key=True, index=True)
    owned_shoe_id = Column(Integer, ForeignKey("owned_shoes.id"), nullable=False, index=True)
    body = Column(Text, nullable=False)
    mileage_at_note = Column(Float, nullable=False)  # shoe's current_mileage when the note was written
    triggered_by = Column(String(20), nullable=False, default="manual")  # manual | checkpoint
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    owned_shoe = relationship("OwnedShoe", back_populates="notes_entries")

    def __repr__(self):
        return f"<ShoeNote shoe={self.owned_shoe_id} @ {self.mileage_at_note}km>"


class AppSettings(Base):
    """
    Simple key/value store for app-level state that doesn't belong in a
    dedicated table. Currently used to track `last_coros_sync_at`.
    """
    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AppSettings {self.key}={self.value!r}>"


class PlannedRace(Base):
    """
    A race the user is training toward (P3.4). The next upcoming race is the
    most time-sensitive thing on the Training page, so it sits above the
    trends. Derived fields (days/weeks remaining, target pace) are computed at
    the API boundary, never stored.
    """
    __tablename__ = "planned_races"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    race_date = Column(Date, nullable=False, index=True)
    distance_km = Column(Float, nullable=True)
    target_time_s = Column(Integer, nullable=True)   # goal finish time in seconds
    location = Column(String(200), nullable=True)
    planned_shoe_id = Column(Integer, ForeignKey("owned_shoes.id"), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="planned", server_default="planned")  # planned | completed | skipped
    result_time_s = Column(Integer, nullable=True)   # actual finish time, set on completion
    # R2.7 T7: the canonical run this race *was*, set on completion/promotion so the
    # past-race row deep-links to the activity's full stats. Nullable — planned and
    # manually-completed races have no linked Activity.
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships (no back_populates — neither owned_shoes nor activities needs to know)
    planned_shoe = relationship("OwnedShoe")
    activity = relationship("Activity")

    def __repr__(self):
        return f"<PlannedRace {self.name!r} @ {self.race_date}>"


class StravaGearMapping(Base):
    """
    Maps an exact (stripped) Strava gear string to an owned shoe.

    `owned_shoe_id` is nullable: NULL means "known but unmapped" — e.g. a shoe
    owned before the tracker existed, retired-and-deleted, or deliberately
    skipped. Unmapped gear still imports into strava_activities; it just
    doesn't backfill a shoe run.
    """
    __tablename__ = "strava_gear_mappings"

    id = Column(Integer, primary_key=True, index=True)
    gear_name = Column(String(200), nullable=False, unique=True)  # exact stripped Strava string
    owned_shoe_id = Column(Integer, ForeignKey("owned_shoes.id"), nullable=True)

    # Relationship (no back_populates — owned_shoes doesn't need to know)
    owned_shoe = relationship("OwnedShoe")

    def __repr__(self):
        return f"<StravaGearMapping {self.gear_name!r} -> shoe {self.owned_shoe_id}>"


class AthleteMetric(Base):
    """
    A periodic snapshot of COROS athlete-level fitness (R2.7 T5) — not per
    activity, but per sync. Append-only: each row is one point in time, so the
    Training-tab fitness card reads the newest and the history is preserved for
    future trend views. Written via the Claude-Desktop sync agent (design
    decisions C6 — server-side COROS is dormant), never computed by Anton.
    """
    __tablename__ = "athlete_metrics"

    id = Column(Integer, primary_key=True, index=True)
    vo2max = Column(Float, nullable=True)                        # ml/kg/min
    threshold_pace_s_per_km = Column(Integer, nullable=True)     # lactate threshold pace
    race_predictions = Column(JSON, nullable=True)               # {"5.0": 1234, "10.0": 2468, ...} distance_km → predicted_s
    running_level = Column(Float, nullable=True)                 # COROS running level score (F3)
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<AthleteMetric vo2max={self.vo2max} @ {self.captured_at}>"


class ChatConversation(Base):
    """
    A persisted Son of Anton conversation (R2.6) — memory moved off browser
    localStorage so it's device-independent and (later, R3) readable by
    server-side agents. The streaming endpoint stays stateless per request;
    this table is written by a separate CRUD surface on stream-end.

    The two message arrays are stored as JSON, not a normalized messages
    table: `display_messages` carries pure UI concerns (tool-call events, pill
    previews, dividers) that don't relationally model well, and at single-user
    scale (cap 50 conversations) normalizing would be speculative infra
    (CLAUDE.md §2.5). `id` is the client-generated UUID — keeping it preserves
    the frontend's in-memory-first / persist-on-first-message flow.
    """
    __tablename__ = "chat_conversations"

    id = Column(String(36), primary_key=True, index=True)  # client crypto.randomUUID()
    title = Column(String(200), nullable=True)
    model = Column(String(60), nullable=True)
    display_messages = Column(JSON, nullable=False, default=list)  # rich UI message array
    api_messages = Column(JSON, nullable=False, default=list)      # LLM-facing message array
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ChatConversation {self.id} {self.title!r}>"


class CheckpointPrompt(Base):
    """
    Records that the 100 km-checkpoint note prompt was already shown for a shoe
    (R2.6) — UI-state persistence moved off localStorage so it doesn't
    re-prompt on a second device. Not a mileage-ledger fact: the checkpoint
    itself is derived from `current_mileage`; this row only remembers that we
    asked. The (shoe, km) pair is unique — "mark prompted" is idempotent.
    """
    __tablename__ = "checkpoint_prompts"
    __table_args__ = (
        UniqueConstraint("owned_shoe_id", "checkpoint_km", name="uq_checkpoint_prompt_shoe_km"),
    )

    id = Column(Integer, primary_key=True, index=True)
    owned_shoe_id = Column(Integer, ForeignKey("owned_shoes.id"), nullable=False, index=True)
    checkpoint_km = Column(Integer, nullable=False)
    prompted_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<CheckpointPrompt shoe={self.owned_shoe_id} @ {self.checkpoint_km}km>"


class OAuthAuthCode(Base):
    """
    Short-lived PKCE authorization code issued by the OAuth 2.1 login flow (RA1.1b).

    The raw code is shown to the client once and never stored — only the
    SHA-256 hex digest is persisted here. `used` is set to True when
    `exchange_authorization_code` consumes it, preventing replay.
    """
    __tablename__ = "oauth_auth_codes"

    id = Column(Integer, primary_key=True)
    code_hash = Column(String(64), unique=True, nullable=False, index=True)
    client_id = Column(String(255), nullable=False)
    code_challenge = Column(String(255), nullable=False)  # PKCE S256 challenge
    redirect_uri = Column(String(2048), nullable=False)
    redirect_uri_provided_explicitly = Column(Boolean, nullable=False)
    scopes = Column(String(500), nullable=True)   # space-separated
    resource = Column(String(2048), nullable=True)
    expires_at = Column(Float, nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<OAuthAuthCode client={self.client_id} used={self.used}>"


class OAuthToken(Base):
    """
    OAuth 2.1 access and refresh tokens (RA1.1b).

    Only the SHA-256 hex digest of each token is stored; the raw value is
    returned to the client once. `pair_id` links an access+refresh pair so
    revoking either token deletes both.

    token_type: 'access' | 'refresh'
    expires_at: Unix timestamp (float); NULL for non-expiring refresh tokens.
    """
    __tablename__ = "oauth_tokens"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    token_type = Column(String(20), nullable=False)   # 'access' | 'refresh'
    client_id = Column(String(255), nullable=False)
    scopes = Column(String(500), nullable=True)
    expires_at = Column(Float, nullable=True)
    resource = Column(String(2048), nullable=True)
    subject = Column(String(255), nullable=True)
    pair_id = Column(String(32), nullable=True, index=True)  # random hex shared by access+refresh pair
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<OAuthToken type={self.token_type} client={self.client_id}>"
