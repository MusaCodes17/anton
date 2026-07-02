# Refactor Plan — Running Shoe Deal Finder

**Created:** 2026-07-02
**Scope:** Backend architecture consolidation. No behavior changes to REST response shapes or MCP tool signatures unless explicitly noted.

---

## Architecture read (current state)

- **FastAPI app** (`app/main.py`) mounts 10 routers + FastMCP at `/mcp` (Streamable HTTP, session manager merged into lifespan).
- **Persistence:** SQLAlchemy + SQLite, 8 models. Deal-tracking domain (`Shoe`/`Retailer`/`PriceRecord`/`Deal`/`PromoCode`) and rotation domain (`OwnedShoe`/`ShoeRun`/`ShoeNote`) are cleanly separated at the model level.
- **Scraping:** `BaseScraper` (HTTP/Playwright/price parsing/kids-filter/promo detection/Algolia rediscovery) → `ShopifyScraper`/`AlgoliaScraper` generics → thin per-retailer subclasses + one bespoke (`enroute_run`). `ScraperManager` does registry + orchestration + persistence. Parallel background path (`scrape_runner` + `scrape_state` pub/sub → SSE) exists only for `POST /scrape/all`.
- **MCP server:** 17 tools, 6 resources, 1 prompt in a single 45KB file.
- **Chat:** provider-strategy agentic loop (Anthropic/OpenAI/Gemini) discovering tools via MCP client, resources pre-loaded into system prompt.
- **Frontend:** React Query with centralized query keys, axios wrapper, SSE hook for scrape progress. Healthy — out of scope.

## Findings (what to fix)

### F1 — Business logic duplicated between routers and MCP tools (highest value)
`mcp_server.py` claims "exactly one place business logic lives" but reimplements:
- **Run logging + checkpoint math** exists 3×: `routers/owned_shoes.log_run`, `mcp.log_run_to_shoe`, `mcp.confirm_coros_run` (and near-identically in `routers/coros_sync.confirm_coros_runs`, which skips checkpoint detection entirely — a real inconsistency: syncing via REST never flags checkpoints). The router uses `CHECKPOINT_INTERVAL_KM`; MCP hardcodes `100`.
- **Run deletion** duplicated: `routers/owned_shoes.delete_shoe_run` vs `mcp.delete_shoe_run`.
- **cost_per_km** computed in `_attach_computed_fields` (router) and again in `_owned_shoe_to_dict` (MCP) and again in `shoe_detail_resource`.
- **COROS confirm** duplicated: `routers/coros_sync.confirm_coros_runs` vs `mcp.confirm_coros_run` (the REST path also batch-sets `last_coros_sync_at` once; MCP sets it per run).
- `mcp_server.py` imports private helpers from routers (`_compute_lifetime_stats`, `_get_setting`, `_is_already_logged`, `_set_setting`) — routers are acting as an accidental service layer.

**Fix:** extract `app/services/rotation.py`, `app/services/coros.py`, `app/services/settings.py`. Routers and MCP tools become thin adapters.

### F2 — `ScraperManager` has three responsibilities (29KB)
Registry/factory (`scrapers` dict + `_register_dynamic_scrapers` + `build_dynamic_scraper`), orchestration (`scrape_shoe`, `scrape_all_shoes`, `test_shoe_scrapability`), and persistence (`_record_price`, `_create_deal`, `_deactivate_deal`, `_deactivate_orphaned_deals`, `_upsert_promo_code`). `scrape_runner.py` reaches into the private `_scrape_retailer_for_shoe` — the missing public seam.

**Fix:** split into `registry.py`, `deal_store.py`, `orchestrator.py`. Make the per-(shoe, retailer) primitive public.

### F3 — MCP `trigger_scrape` is synchronous and times out (known pain point)
The background job + SSE infrastructure exists but the MCP tool doesn't use it. **Fix:** `trigger_scrape` starts the background job (reusing `try_acquire_scrape_lock` + `run_scrape_job`) and returns immediately; add `get_scrape_status` tool reading `scrape_state`. This makes scraping usable from Claude Desktop again. *Deliberate behavior change to one MCP tool's return shape.*

### F4 — Dead/latent `mileage_limit` code
`OwnedShoe` has no `mileage_limit` column, but `shoe_rotation_resource` and `shoe_detail_resource` probe for it via `hasattr`/`getattr`, and `_format_mileage_bar` supports a limit that can never exist (bar always renders as bare km). `claude.md`'s schema section also lists it. **Fix:** add the column properly (nullable float, default 800 suggested at UI level only) — it's clearly wanted (the chat system prompt says "flag when a shoe is approaching 700km or its mileage limit").

### F5 — Ad-hoc migrations
9 `migrate_add_*.py` scripts at backend root, each hand-rolling idempotent `ALTER TABLE`. **Fix:** adopt Alembic; keep old scripts in `backend/legacy_migrations/` for history.

### F6 — No test suite
`test_scraper.py` is a manual script. The service extraction (F1/F2) is exactly when pure business logic becomes unit-testable (checkpoint math, pace averaging, dedup matching, deal qualification rules). **Fix:** pytest + in-memory SQLite fixtures.

### F7 — Hygiene
- Two junk `{routers,scrapers,models}` / `{components,pages,services,lib}` empty dirs (failed brace-expansion `mkdir`).
- `.playwright-mcp/` logs, `.DS_Store`, `shoe_deals.db.bak*`, verification `.png`s tracked in the repo root.
- `datetime.utcnow()` (naive, deprecated) mixed with `datetime.now(timezone.utc)` across scraper manager / runner / MCP.

---

## Task breakdown

Dependency graph (A and B are independent of each other; C depends on B; D depends on A):

```
Interfaces (this doc) ──┬── Task A: rotation/coros/settings services ──── Task D: MCP+routers adapt to services
                        ├── Task B: scraper split (registry/store/orchestrator) ── Task C: async MCP trigger_scrape
                        ├── Task E: Alembic + mileage_limit column
                        └── Task F: tests + hygiene (after A–D merge)
```

Run A and B as parallel Opus agents in separate git worktrees. D and C follow. E can run any time (touches only migrations + model + the two resource functions' `hasattr` removal — coordinate with D on `mcp_server.py`; do E after D to avoid merge conflicts, or before A starts). F last.

---

## Interface designs

### `app/services/settings.py`
```python
def get_setting(db: Session, key: str) -> Optional[str]: ...
def set_setting(db: Session, key: str, value: str) -> None:
    """Upsert. Does NOT commit — caller owns the transaction."""
```

### `app/services/rotation.py`
```python
CHECKPOINT_INTERVAL_KM = 100

@dataclass
class LifetimeStats:
    lifetime_avg_pace: Optional[str]   # "M:SS/km"
    lifetime_avg_hr: Optional[int]
    total_runs: int

@dataclass
class RunLogResult:
    run: ShoeRun
    shoe: OwnedShoe                    # refreshed
    checkpoint_reached: bool
    checkpoint_km: Optional[int]

def pace_to_seconds(pace: str) -> Optional[float]: ...
def seconds_to_pace(seconds: float) -> str: ...
def crossed_checkpoint(old_km: float, new_km: float,
                       interval: int = CHECKPOINT_INTERVAL_KM) -> Optional[int]:
    """Return the checkpoint crossed (e.g. 300) or None."""

def compute_lifetime_stats(db: Session, owned_shoe_id: int) -> LifetimeStats: ...
def cost_per_km(shoe: OwnedShoe) -> Optional[float]: ...
def find_matched_image(db: Session, brand: str, model: str) -> Optional[str]: ...

def log_run(db: Session, owned_shoe_id: int, *, distance_km: float,
            run_date: date, source: str = "manual",
            coros_activity_id: Optional[str] = None,
            avg_pace: Optional[str] = None, avg_hr: Optional[int] = None,
            notes: Optional[str] = None) -> RunLogResult:
    """Creates the ShoeRun, increments mileage, commits, computes checkpoint.
    Raises LookupError if the shoe doesn't exist.
    THE only code path that writes a ShoeRun — manual, MCP, and COROS all route here."""

def delete_run(db: Session, run_id: int) -> OwnedShoe:
    """Deletes run, decrements mileage (floor 0), commits, returns refreshed shoe.
    Raises LookupError if run or shoe missing."""

def add_note(db: Session, owned_shoe_id: int, body: str,
             triggered_by: str = "manual") -> ShoeNote:
    """mileage_at_note set server-side. Raises LookupError."""
```
Adapters: routers convert `LookupError` → `HTTPException(404)`; MCP tools convert → `{"success": False, "error": ...}`. `_attach_computed_fields` stays in the router (it mutates ORM objects for Pydantic) but delegates every computation to this module.

### `app/services/coros.py`
```python
@dataclass
class CorosFetchResult:
    runs: list[dict]        # activity_to_run_dict shape
    already_synced: int
    coros_configured: bool

def is_already_logged(db, activity_id: str, act_date: str, dist_km: float) -> bool: ...
def fetch_unsynced(db, days_back: int = 30) -> CorosFetchResult:
    """Wraps coros_client.fetch_running_activities + dedup filter.
    Propagates requests/ValueError — adapters map to 502 or success:False."""

def confirm_run(db, *, coros_activity_id: str, owned_shoe_id: int,
                run_date: date, distance_km: float,
                avg_pace: Optional[str] = None, avg_hr: Optional[int] = None,
                notes: Optional[str] = None) -> Optional[RunLogResult]:
    """Idempotent: returns None if activity_id already logged.
    Delegates to rotation.log_run(source='coros'). Stamps last_coros_sync_at."""
```
The REST batch endpoint loops `confirm_run` — this **adds checkpoint detection to the REST COROS path** (previously missing); `CorosConfirmResponse` may optionally grow a `checkpoints` list (additive, non-breaking).

### `app/scrapers/registry.py`
```python
BESPOKE_SCRAPERS: dict[str, type[BaseScraper]]  # name → class (instantiated lazily)

def build_dynamic_scraper(retailer: Retailer) -> Optional[BaseScraper]: ...
def get_scraper(retailer: Retailer) -> Optional[BaseScraper]:
    """Bespoke subclass by name first, else dynamic by platform, else None."""
def build_registry(db: Session) -> dict[str, BaseScraper]:
    """Full name→scraper map for all scrapable retailers (used by orchestrator)."""
```

### `app/scrapers/deal_store.py`
```python
class DealStore:
    """All PriceRecord/Deal/PromoCode persistence. Owns commit/rollback per call."""
    def __init__(self, db: Session): ...
    def record_price(self, shoe, retailer, *, product_url, price, original_price,
                     in_stock, size_available, sizes_available=None,
                     image_url=None, colorway=None) -> bool: ...
    def upsert_deal(self, shoe, retailer, *, price, product_url, in_stock,
                    sizes_available=None, image_url=None, colorway=None) -> bool: ...
    def deactivate_deal(self, shoe, retailer, product_url) -> bool: ...
    def deactivate_orphaned_deals(self, shoe, retailer, seen_urls: set) -> int: ...
    def upsert_promo_code(self, retailer, data: dict) -> bool: ...
```
Deal-qualification rule (`on_sale and price <= target`) stays in the orchestrator — the store persists, it doesn't decide.

### `app/scrapers/orchestrator.py`
```python
class ScrapeOrchestrator:
    def __init__(self, db: Session,
                 registry: Optional[dict[str, BaseScraper]] = None,
                 store: Optional[DealStore] = None): ...
    def scrape_retailer_for_shoe(self, shoe, retailer) -> dict:   # PUBLIC now
    def scrape_shoe(self, shoe_id, retailer_ids=None) -> dict: ...
    def scrape_all_shoes(self, retailer_ids=None) -> dict: ...
    def test_shoe_scrapability(self, brand, model) -> dict: ...
    def detect_promo_codes_for_retailer(self, retailer) -> dict: ...
    def detect_all_promo_codes(self) -> dict: ...
```
Lock primitives (`scrape_guard`, `try_acquire_scrape_lock`, `release_scrape_lock`, `is_scrape_running`, `ScrapeInProgressError`) move to `app/scrapers/lock.py`. `scraper_manager.py` becomes a shim re-exporting `ScraperManager = ScrapeOrchestrator` + lock names, so every existing import keeps working until D lands, then delete the shim.

### MCP scrape tools (Task C)
```python
@mcp.tool()
def trigger_scrape(shoe_id: Optional[int] = None) -> dict:
    """Single-shoe: stays synchronous (fast enough).
    Full scrape (shoe_id=None): acquires lock, schedules run_scrape_job on the
    running event loop, returns {"started": True} immediately.
    Returns {"started": False, "reason": ...} if a scrape is already running."""

@mcp.tool()
def get_scrape_status() -> dict:
    """{"is_running", "started_at", "completed_at",
        "retailers_done": [...], "errors": [...], "total_deals": Optional[int]}
    — summarized from scrape_state.history."""
```

---

## Worker prompts (Opus agents)

Setup for parallel work:
```bash
git worktree add ../rsd-task-a refactor/services
git worktree add ../rsd-task-b refactor/scrapers
# run one Opus agent per worktree:  claude --model opus
```

---

### Task A prompt — service layer extraction

> Read REFACTOR_PLAN.md sections F1, "Interface designs" for `app/services/settings.py`, `app/services/rotation.py`, and `app/services/coros.py`. Implement exactly those three modules with those signatures.
>
> Source the logic from: `routers/owned_shoes.py` (`_pace_to_seconds`, `_seconds_to_pace`, `_compute_lifetime_stats`, `_find_matched_image`, checkpoint math in `log_run`, deletion in `delete_shoe_run`, cost_per_km in `_attach_computed_fields`), `routers/coros_sync.py` (`_get_setting`, `_set_setting`, `_is_already_logged`, confirm loop), and `coros_client.py` (unchanged — services call it).
>
> Constraints: pure extraction — do NOT change any REST endpoint's response shape or any MCP tool in this task; do NOT modify `mcp_server.py` (Task D does that). Refactor `routers/owned_shoes.py` and `routers/coros_sync.py` to call the new services, keeping `_attach_computed_fields` as a thin router-local adapter and re-exporting `CHECKPOINT_INTERVAL_KM`, `_compute_lifetime_stats`, `_get_setting`, `_set_setting`, `_is_already_logged` from their old locations (deprecated aliases) so `mcp_server.py` keeps importing them unchanged until Task D. `confirm_run` must delegate to `rotation.log_run(source="coros")`. Verify: start the backend, exercise POST /api/owned-shoes/{id}/log-run (checkpoint crossing at a 100km boundary), DELETE /api/owned-shoes/runs/{id}, GET /api/owned-shoes/ (lifetime stats + cost_per_km unchanged), and the COROS sync fetch/confirm flow via /docs. Commit in small chunks: settings → rotation → coros → router rewiring.

### Task B prompt — scraper split

> Read REFACTOR_PLAN.md sections F2 and "Interface designs" for `app/scrapers/registry.py`, `deal_store.py`, `orchestrator.py`, and `lock.py`. Split `app/scrapers/scraper_manager.py` (29KB) into those four modules with exactly those interfaces.
>
> Rules: `scrape_retailer_for_shoe` becomes public; deal-qualification logic (`on_sale and price <= shoe.target_price`, plus the orphaned-deal retirement and target-refresh semantics documented in the current code comments — preserve those comments) lives in the orchestrator; all DB writes live in DealStore. Replace every `datetime.utcnow()` in these files with `datetime.now(timezone.utc)`. Leave `scraper_manager.py` as a backward-compat shim: `from app.scrapers.orchestrator import ScrapeOrchestrator as ScraperManager` plus re-exports of the lock names and `build_dynamic_scraper`, so `routers/scraping.py`, `scrape_runner.py`, `mcp_server.py`, and `test_scraper.py` work untouched. Update `scrape_runner.py` to call the now-public `scrape_retailer_for_shoe` (drop the underscore access). Verify: POST /api/scrape/shoe/{id} for one shoe against one retailer, POST /api/scrape/all with the SSE stream reaching "completed", and the scrapability test endpoint. Commit per module.

### Task C prompt — async MCP scrape (after B merges)

> Read REFACTOR_PLAN.md section F3 and the "MCP scrape tools" interface. In `app/mcp_server.py`: rewrite `trigger_scrape` so a full scrape (no shoe_id) acquires the lock via `try_acquire_scrape_lock`, schedules `run_scrape_job(None)` with `asyncio.get_running_loop().create_task(...)` (the FastMCP tool runs inside the app's event loop; if the tool is sync, use `anyio.from_thread` or make the tool async — check how FastMCP dispatches and pick the correct mechanism, don't guess), and returns `{"started": True, "message": "Track progress with get_scrape_status"}`. Single-shoe scrapes stay synchronous under `scrape_guard()`. Add the `get_scrape_status` tool summarizing `scrape_state` (is_running, started_at, completed_at, retailer_done events collapsed to a name list, errors, total_deals from the completed event if present). Update the tool docstrings — they're read by LLM clients, so document the new started/status flow explicitly. Verify with MCP Inspector: trigger a full scrape, poll get_scrape_status until completed, confirm a second trigger while running returns started: False.

### Task D prompt — MCP adapts to services (after A merges)

> Read REFACTOR_PLAN.md section F1 and the service interfaces. In `app/mcp_server.py`: replace the bodies of `log_run_to_shoe`, `delete_shoe_run`, `add_shoe_note`, `confirm_coros_run`, `fetch_unsynced_coros_runs`, and `get_coros_sync_status` with thin calls to `app/services/rotation.py` and `app/services/coros.py`; replace `_owned_shoe_to_dict`'s inline cost_per_km with `rotation.cost_per_km`; import `compute_lifetime_stats`/settings helpers from services instead of routers. Then delete the deprecated re-export aliases Task A left in the routers, and fix `routers/coros_sync.py`'s confirm endpoint to surface checkpoint info from `RunLogResult` (additive `checkpoints` field on `CorosConfirmResponse`; do not change existing fields). Tool signatures and return shapes must stay byte-compatible except the documented additive change. Verify with MCP Inspector: log_run_to_shoe crossing a 100km checkpoint, delete_shoe_run, confirm_coros_run idempotency (second call with same activity id returns the already-logged error), get_owned_shoes output identical to before.

### Task E prompt — Alembic + mileage_limit

> Read REFACTOR_PLAN.md sections F4 and F5. (1) Add Alembic: init under `backend/alembic/`, configure `sqlalchemy.url` from the same DATABASE_URL env logic as `app/database.py`, and generate a baseline autogenerate revision stamped against the current DB (`alembic stamp head` workflow documented in `backend/README.md`). Move the nine `migrate_*.py` scripts to `backend/legacy_migrations/` with a README noting they're historical. Update `.claude/commands/migrate.md` to describe the Alembic workflow. (2) New revision adding `mileage_limit` (nullable Float) to `owned_shoes`; add it to the model, `OwnedShoeBase`/`OwnedShoeUpdate`/`OwnedShoeResponse` schemas, and `_owned_shoe_to_dict` in `mcp_server.py`; remove the `hasattr(s, "mileage_limit")`/`getattr` guards in `shoe_rotation_resource` and `shoe_detail_resource` (the column exists now, so `_format_mileage_bar` finally renders real bars when a limit is set). Do not add a default limit server-side. Verify: `alembic upgrade head` against a copy of shoe_deals.db, then GET /api/owned-shoes/ and the shoes://rotation resource.

### Task F prompt — tests + hygiene (after A–D merge)

> Read REFACTOR_PLAN.md sections F6 and F7. (1) Add pytest + a `backend/tests/` package with an in-memory SQLite fixture (create tables from `Base.metadata`). Unit-test: `rotation.crossed_checkpoint` (boundary cases: exact multiple, crossing two checkpoints in one run, starting at 0), `pace_to_seconds`/`seconds_to_pace` round-trips and garbage input, `compute_lifetime_stats` with mixed missing pace/HR, `rotation.log_run`/`delete_run` mileage accounting, `coros.is_already_logged` (id match, date+distance ±0.1km tolerance match, no match), `coros.confirm_run` idempotency, DealStore `upsert_deal` (new / refresh-on-target-change / no-op) and `deactivate_orphaned_deals`, and `BaseScraper.is_kids_shoe` + `find_promo_codes` heuristics. Target the services, not the routers — no HTTP tests needed. (2) Hygiene: delete the empty `backend/app/{routers,scrapers,models}` and `frontend/src/{components,pages,services,lib}` directories. Do not touch `shoe_deals.db` itself. Verify: `pytest -q` green, app still boots.

---

## Review checklist (run after each task's PR)

- [ ] No REST response-shape changes (diff `/docs` OpenAPI JSON before/after)
- [ ] MCP tool list + input schemas unchanged except Task C/D's documented deltas (MCP Inspector)
- [ ] `grep -rn "scraper_manager import" backend/` — shim removed only after C and D both landed
- [ ] No router imports inside `app/services/` and no service imports inside `app/scrapers/` (dependency direction: routers/mcp → services → models)
- [ ] Checkpoint math exists in exactly one place: `grep -rn "// 100" backend/app` returns only rotation.py
- [ ] `pytest -q` green; manual smoke: log run, delete run, COROS sync, one scrape
