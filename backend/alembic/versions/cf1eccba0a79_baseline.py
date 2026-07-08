"""baseline

Revision ID: cf1eccba0a79
Revises:
Create Date: 2026-07-02

Baseline schema (R2.2 — Alembic is the sole schema authority).

History: the live DB was originally bootstrapped by `init_db()` (create_all) +
the nine `migrate_add_*.py` scripts, and this revision was first written *empty*
(just `pass`) and stamped onto that already-populated DB. That left fresh setups
still dependent on `create_all` — the "dual schema authority" trap (design
decisions A6).

R2.2 closes it: this `upgrade()` now recreates the exact schema as it stood at
this revision, so `alembic upgrade head` builds a brand-new DB from nothing. The
DDL below was captured by taking the current models, `create_all`-ing them, then
downgrading every later migration back to this point — i.e. it is provably the
schema the later migrations expect to build on. The live DB (already stamped past
this revision) never re-runs this, so populating it is safe.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'cf1eccba0a79'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Captured from the real schema at this revision (see module docstring). Kept as
# raw SQL rather than op.create_table because it is a faithful transcript, not a
# thing to hand-maintain — later migrations own every subsequent change.
_UPGRADE_DDL = [
    """
    CREATE TABLE retailers (
        id INTEGER NOT NULL,
        name VARCHAR(200) NOT NULL,
        base_url VARCHAR(500) NOT NULL,
        is_active BOOLEAN,
        scraping_enabled BOOLEAN,
        platform VARCHAR(20) DEFAULT 'custom' NOT NULL,
        last_scraped_at DATETIME,
        scraper_config JSON,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
        updated_at DATETIME,
        PRIMARY KEY (id),
        UNIQUE (name)
    )
    """,
    "CREATE INDEX ix_retailers_id ON retailers (id)",
    """
    CREATE TABLE app_settings (
        "key" VARCHAR(100) NOT NULL,
        value TEXT,
        PRIMARY KEY ("key")
    )
    """,
    """
    CREATE TABLE shoes (
        id INTEGER NOT NULL,
        brand VARCHAR(100) NOT NULL,
        model VARCHAR(200) NOT NULL,
        shoe_type VARCHAR(50),
        msrp FLOAT,
        target_price FLOAT NOT NULL,
        notes TEXT,
        is_active BOOLEAN,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
        updated_at DATETIME,
        PRIMARY KEY (id)
    )
    """,
    "CREATE INDEX ix_shoes_model ON shoes (model)",
    "CREATE INDEX ix_shoes_id ON shoes (id)",
    "CREATE INDEX ix_shoes_brand ON shoes (brand)",
    """
    CREATE TABLE owned_shoes (
        id INTEGER NOT NULL,
        brand VARCHAR(100) NOT NULL,
        model VARCHAR(200) NOT NULL,
        nickname VARCHAR(100),
        shoe_type VARCHAR(50),
        purchase_date DATE,
        starting_mileage FLOAT NOT NULL,
        current_mileage FLOAT NOT NULL,
        status VARCHAR(20) NOT NULL,
        purchase_price FLOAT,
        image_url TEXT,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
        updated_at DATETIME,
        PRIMARY KEY (id)
    )
    """,
    "CREATE INDEX ix_owned_shoes_id ON owned_shoes (id)",
    "CREATE INDEX ix_owned_shoes_model ON owned_shoes (model)",
    "CREATE INDEX ix_owned_shoes_brand ON owned_shoes (brand)",
    """
    CREATE TABLE price_records (
        id INTEGER NOT NULL,
        shoe_id INTEGER NOT NULL,
        retailer_id INTEGER NOT NULL,
        product_url TEXT NOT NULL,
        price FLOAT NOT NULL,
        original_price FLOAT,
        in_stock BOOLEAN,
        size_available BOOLEAN,
        sizes_available JSON,
        image_url TEXT,
        colorway VARCHAR(200),
        scraped_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
        PRIMARY KEY (id),
        FOREIGN KEY(shoe_id) REFERENCES shoes (id),
        FOREIGN KEY(retailer_id) REFERENCES retailers (id)
    )
    """,
    "CREATE INDEX ix_price_records_scraped_at ON price_records (scraped_at)",
    "CREATE INDEX ix_price_records_id ON price_records (id)",
    "CREATE INDEX ix_price_records_shoe_id ON price_records (shoe_id)",
    "CREATE INDEX ix_price_records_retailer_id ON price_records (retailer_id)",
    """
    CREATE TABLE promo_codes (
        id INTEGER NOT NULL,
        retailer_id INTEGER NOT NULL,
        code VARCHAR(50) NOT NULL,
        description TEXT,
        discount_percent FLOAT,
        discount_amount FLOAT,
        source VARCHAR(20),
        source_url TEXT,
        is_active BOOLEAN,
        detected_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
        last_seen_at DATETIME,
        PRIMARY KEY (id),
        FOREIGN KEY(retailer_id) REFERENCES retailers (id)
    )
    """,
    "CREATE INDEX ix_promo_codes_retailer_id ON promo_codes (retailer_id)",
    "CREATE INDEX ix_promo_codes_id ON promo_codes (id)",
    "CREATE INDEX ix_promo_codes_is_active ON promo_codes (is_active)",
    """
    CREATE TABLE deals (
        id INTEGER NOT NULL,
        shoe_id INTEGER NOT NULL,
        retailer_id INTEGER NOT NULL,
        current_price FLOAT NOT NULL,
        target_price FLOAT NOT NULL,
        savings_amount FLOAT NOT NULL,
        savings_percent FLOAT NOT NULL,
        product_url TEXT NOT NULL,
        in_stock BOOLEAN,
        sizes_available JSON,
        image_url TEXT,
        colorway VARCHAR(200),
        is_active BOOLEAN,
        detected_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
        expires_at DATETIME,
        PRIMARY KEY (id),
        FOREIGN KEY(retailer_id) REFERENCES retailers (id),
        FOREIGN KEY(shoe_id) REFERENCES shoes (id)
    )
    """,
    "CREATE INDEX ix_deals_is_active ON deals (is_active)",
    "CREATE INDEX ix_deals_retailer_id ON deals (retailer_id)",
    "CREATE INDEX ix_deals_id ON deals (id)",
    "CREATE INDEX ix_deals_shoe_id ON deals (shoe_id)",
    """
    CREATE TABLE shoe_runs (
        id INTEGER NOT NULL,
        owned_shoe_id INTEGER NOT NULL,
        distance_km FLOAT NOT NULL,
        run_date DATE NOT NULL,
        source VARCHAR(20) NOT NULL,
        coros_activity_id VARCHAR(100),
        avg_pace VARCHAR(20),
        avg_hr INTEGER,
        notes TEXT,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
        PRIMARY KEY (id),
        FOREIGN KEY(owned_shoe_id) REFERENCES owned_shoes (id)
    )
    """,
    "CREATE INDEX ix_shoe_runs_id ON shoe_runs (id)",
    "CREATE INDEX ix_shoe_runs_coros_activity_id ON shoe_runs (coros_activity_id)",
    "CREATE INDEX ix_shoe_runs_owned_shoe_id ON shoe_runs (owned_shoe_id)",
    """
    CREATE TABLE shoe_notes (
        id INTEGER NOT NULL,
        owned_shoe_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        mileage_at_note FLOAT NOT NULL,
        triggered_by VARCHAR(20) NOT NULL,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
        PRIMARY KEY (id),
        FOREIGN KEY(owned_shoe_id) REFERENCES owned_shoes (id)
    )
    """,
    "CREATE INDEX ix_shoe_notes_id ON shoe_notes (id)",
    "CREATE INDEX ix_shoe_notes_owned_shoe_id ON shoe_notes (owned_shoe_id)",
]

# Drop in reverse dependency order (children before parents).
_DOWNGRADE_TABLES = [
    "shoe_notes",
    "shoe_runs",
    "deals",
    "promo_codes",
    "price_records",
    "owned_shoes",
    "shoes",
    "app_settings",
    "retailers",
]


def upgrade() -> None:
    for stmt in _UPGRADE_DDL:
        op.execute(stmt)


def downgrade() -> None:
    for table in _DOWNGRADE_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")
