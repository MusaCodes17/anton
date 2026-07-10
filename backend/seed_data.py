"""
Seed / sync script for retailers and shoes.

- `python seed_data.py`         → additive seed (insert anything missing; never deletes)
- `python seed_data.py --sync`  → reconcile the DB to match this file exactly
                                   (insert missing AND delete anything not listed here)

RETAILERS and SHOES below are the source of truth. Edit them, then run --sync.
"""
import sys

from app.database import SessionLocal, run_migrations
from app.models.models import Retailer, Shoe


# ─────────────────────────────── Source of truth ───────────────────────────────

RETAILERS = [
    {
        "name": "The Last Hunt",
        "base_url": "https://www.thelasthunt.com",
        "is_active": True,
        "scraping_enabled": True,  # Algolia scraper
        "scraper_config": {"notes": "Algolia (index PRODUCTS_TLH_en-CA). Great for clearance deals."},
    },
    {
        "name": "JD Sports Canada",
        "base_url": "https://www.jdsports.ca",
        "is_active": True,
        "scraping_enabled": True,  # Shopify scraper
        "scraper_config": {"notes": "Shopify. Good for Nike and Adidas."},
    },
    {
        "name": "Altitude Sports",
        "base_url": "https://www.altitude-sports.com",
        "is_active": True,
        "scraping_enabled": True,  # Algolia scraper
        "scraper_config": {"notes": "Algolia (index PRODUCTS_ALS_en-CA). Premium running gear."},
    },
    {
        "name": "Boutique Endurance",
        "base_url": "https://www.boutiqueendurance.ca/en",
        "is_active": True,
        "scraping_enabled": True,  # Shopify scraper
        "scraper_config": {"notes": "Shopify (Quebec running specialty). Uses /en locale."},
    },
    {
        "name": "Le Coureur",
        "base_url": "https://lecoureur.com/en",
        "is_active": True,
        "scraping_enabled": True,  # Shopify scraper
        "scraper_config": {"notes": "Shopify (Quebec running specialty). Uses /en locale; some titles stay French."},
    },
    {
        "name": "BlackToe Running",
        "base_url": "https://www.blacktoerunning.com",
        "is_active": True,
        "scraping_enabled": True,  # Shopify scraper
        "scraper_config": {"notes": "Shopify (Toronto running specialty)."},
    },
    {
        "name": "ForeRunners",
        "base_url": "https://shop.forerunners.ca",
        "is_active": True,
        "scraping_enabled": True,  # Shopify scraper
        "scraper_config": {"notes": "Shopify (Vancouver running specialty)."},
    },
    {
        "name": "SAIL",
        "base_url": "https://www.sail.ca/en/",
        "is_active": True,
        "scraping_enabled": True,  # SearchSpring scraper (site ID s8zq1c)
        "scraper_config": {"notes": "Magento 2 + SearchSpring (site s8zq1c). Public API, no auth. Good for clearance outdoor/running gear."},
    },
]


SHOES = [
    # Adidas Adizero line
    {"brand": "Adidas", "model": "Adizero Adios Pro 4", "target_price": 300.00, "notes": "Carbon-plated marathon racing shoe"},
    {"brand": "Adidas", "model": "Adizero Boston 13", "target_price": 190.00, "notes": "Versatile super trainer"},
    {"brand": "Adidas", "model": "Adizero Evo SL", "target_price": 180.00, "notes": "Lightweight daily trainer"},
    {"brand": "Adidas", "model": "Adizero Adios 9", "target_price": 180.00, "notes": "Lightweight road racer"},
    {"brand": "Adidas", "model": "Adizero Takumi Sen 11", "target_price": 230.00, "notes": "5K/10K carbon racing shoe"},

    # ASICS racing line
    {"brand": "Asics", "model": "Metaspeed Sky Tokyo", "target_price": 360.00, "notes": "Elite racing shoe"},
    {"brand": "Asics", "model": "Metaspeed Edge Tokyo", "target_price": 360.00, "notes": "Elite racing shoe"},
    {"brand": "Asics", "model": "Metaspeed Ray", "target_price": 400.00, "notes": "Ultra-light elite racing shoe"},
    {"brand": "Asics", "model": "Magic Speed 5", "target_price": 220.00, "notes": "Tempo/racing shoe"},
    {"brand": "Asics", "model": "Megablast", "target_price": 280.00, "notes": "Premium max-cushion trainer"},
    {"brand": "Asics", "model": "Superblast 2", "target_price": 270.00, "notes": "Premium super trainer"},
    {"brand": "Asics", "model": "Superblast 3", "target_price": 280.00, "notes": "Premium super trainer"},

    # Puma Deviate Nitro line
    {"brand": "Puma", "model": "Deviate Nitro Elite 4", "target_price": 310.00, "notes": "Carbon-plated racer"},
    {"brand": "Puma", "model": "Deviate Fast-R Nitro Elite 3", "target_price": 400.00, "notes": "Flagship carbon racer"},
    {"brand": "Puma", "model": "Deviate Nitro 4", "target_price": 230.00, "notes": "Performance trainer"},
    {"brand": "Puma", "model": "Deviate Nitro Pure", "target_price": 250.00, "notes": "Lightweight trainer"},

    # Nike racing shoes
    {"brand": "Nike", "model": "ZoomX Vaporfly Next% 4", "target_price": 360.00, "notes": "Elite marathon shoe"},
    {"brand": "Nike", "model": "Alphafly 3", "target_price": 385.00, "notes": "Top racing shoe"},
    {"brand": "Nike", "model": "Zoom Fly 6", "target_price": 225.00, "notes": "Tempo shoe"},

    # Mizuno shoes
    {"brand": "Mizuno", "model": "Hyperwarp Pure", "target_price": 400.00, "notes": "Ultra-light carbon racing shoe"},
    {"brand": "Mizuno", "model": "Hyperwarp Elite", "target_price": 365.00, "notes": "Carbon-plated marathon racer"},
    {"brand": "Mizuno", "model": "Neo Zen 2", "target_price": 190.00, "notes": "Lightweight daily trainer"},
    {"brand": "Mizuno", "model": "Neo Vista 2", "target_price": 230.00, "notes": "Super trainer with glass-fiber Wave Plate"},
    {"brand": "Mizuno", "model": "Neo Vista 3", "target_price": 230.00, "notes": "Estimated MSRP (not yet on Mizuno Canada)"},
    {"brand": "Mizuno", "model": "Hyperwarp Pro", "target_price": 310.00, "notes": "Performance trainer / speed workouts"},

    # HOKA
    {"brand": "Hoka", "model": "Cielo X1 2.0", "target_price": 375.00, "notes": "Elite marathon racer"},
    {"brand": "Hoka", "model": "Rocket X 3", "target_price": 340.00, "notes": "Carbon racing shoe"},
    {"brand": "Hoka", "model": "Mach X 3", "target_price": 260.00, "notes": "Tempo trainer"},
    {"brand": "Hoka", "model": "Mach 6", "target_price": 190.00, "notes": "Lightweight daily trainer"},
    {"brand": "Hoka", "model": "Skyward X", "target_price": 300.00, "notes": "Max-cushion super trainer"},

    # New Balance
    {"brand": "New Balance", "model": "FuelCell SuperComp Elite v5", "target_price": 340.00, "notes": "Carbon marathon racer"},
    {"brand": "New Balance", "model": "FuelCell Rebel v5", "target_price": 190.00, "notes": "Lightweight trainer"},
    {"brand": "New Balance", "model": "FuelCell Trainer", "target_price": 250.00, "notes": "Super trainer"},

    # Saucony
    {"brand": "Saucony", "model": "Endorphin Elite 3", "target_price": 375.00, "notes": "Flagship racer"},
    {"brand": "Saucony", "model": "Endorphin Pro 5", "target_price": 325.00, "notes": "Carbon marathon racer"},
    {"brand": "Saucony", "model": "Endorphin Speed 5", "target_price": 240.00, "notes": "Tempo trainer"},
    {"brand": "Saucony", "model": "Endorphin Azura", "target_price": 230.00, "notes": "Daily trainer"},

    # Brooks
    {"brand": "Brooks", "model": "Hyperion Elite 5", "target_price": 300.00, "notes": "Elite marathon racer"},
    {"brand": "Brooks", "model": "Hyperion Elite 5", "target_price": 300.00, "notes": "Elite marathon racer"},
    {"brand": "Brooks", "model": "Hyperion Max 3", "target_price": 270.00, "notes": "Super trainer"},
    {"brand": "Brooks", "model": "Hyperion 3", "target_price": 190.00, "notes": "Lightweight trainer"},

    # On
    {"brand": "On", "model": "Cloudboom Strike", "target_price": 390.00, "notes": "Elite marathon racer"},
]


# ─────────────────────────────── Seeding (additive) ───────────────────────────────

def seed_retailers():
    """Insert any retailers from RETAILERS that aren't already in the DB."""
    db = SessionLocal()
    for data in RETAILERS:
        existing = db.query(Retailer).filter(Retailer.name == data["name"]).first()
        if not existing:
            db.add(Retailer(**data))
            print(f"✅ Added retailer: {data['name']}")
        else:
            print(f"⏭️  Retailer already exists: {data['name']}")
    db.commit()
    db.close()


def seed_shoes():
    """Insert any shoes from SHOES that aren't already in the DB (matched by brand+model)."""
    db = SessionLocal()
    for data in SHOES:
        existing = db.query(Shoe).filter(
            Shoe.brand == data["brand"],
            Shoe.model == data["model"],
        ).first()
        if not existing:
            db.add(Shoe(**data))
            print(f"✅ Added shoe: {data['brand']} {data['model']}")
        else:
            print(f"⏭️  Shoe already exists: {data['brand']} {data['model']}")
    db.commit()
    db.close()


# ─────────────────────────── Sync (reconcile = add + remove) ───────────────────────────

def sync_retailers():
    """Make the retailers table match RETAILERS exactly (insert missing, delete extras)."""
    db = SessionLocal()
    wanted = {r["name"]: r for r in RETAILERS}

    for existing in db.query(Retailer).all():
        if existing.name not in wanted:
            print(f"🗑️  Removing retailer (no longer in seed): {existing.name}")
            db.delete(existing)

    for name, data in wanted.items():
        existing = db.query(Retailer).filter(Retailer.name == name).first()
        if existing:
            # Keep config in sync (e.g. scraping_enabled flips, base_url, notes).
            for key, value in data.items():
                setattr(existing, key, value)
        else:
            db.add(Retailer(**data))
            print(f"✅ Added retailer: {name}")
    db.commit()
    db.close()


def sync_shoes():
    """Make the shoes table match SHOES exactly (insert missing, delete extras)."""
    db = SessionLocal()
    wanted = {(s["brand"], s["model"]): s for s in SHOES}

    for existing in db.query(Shoe).all():
        if (existing.brand, existing.model) not in wanted:
            print(f"🗑️  Removing shoe (no longer in seed): {existing.brand} {existing.model}")
            db.delete(existing)

    for (brand, model), data in wanted.items():
        existing = db.query(Shoe).filter(Shoe.brand == brand, Shoe.model == model).first()
        if existing:
            # Refresh target_price / notes from seed.
            existing.target_price = data["target_price"]
            existing.notes = data.get("notes")
        else:
            db.add(Shoe(**data))
            print(f"✅ Added shoe: {brand} {model}")
    db.commit()
    db.close()


def sync_database():
    """Full reconcile of retailers + shoes to match this file."""
    sync_retailers()
    sync_shoes()


if __name__ == "__main__":
    do_sync = "--sync" in sys.argv
    print("🌱 Starting database " + ("sync" if do_sync else "seeding") + "...")
    print("\n📦 Migrating database to head...")
    run_migrations()

    if do_sync:
        print("\n🔁 Syncing retailers (add missing, remove absent)...")
        sync_retailers()
        print("\n🔁 Syncing shoes (add missing, remove absent)...")
        sync_shoes()
        print("\n✅ Sync complete!")
    else:
        print("\n🏪 Seeding retailers...")
        seed_retailers()
        print("\n👟 Seeding shoes...")
        seed_shoes()
        print("\n✅ Seeding complete!  (use --sync to also remove items not listed here)")
