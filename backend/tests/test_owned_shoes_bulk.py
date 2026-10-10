"""
Parity tests: rotation.attach_computed_fields_bulk must set exactly the same
attributes, with exactly the same values, as attach_computed_fields per shoe.
"""
from app.models.models import Activity, OwnedShoe, PriceRecord, Retailer, Shoe, ShoeRun
from app.services import rotation

ATTRS = [
    "matched_image_url", "lifetime_avg_pace", "lifetime_avg_hr",
    "total_runs", "cost_per_km", "recommended_limit_km",
]


def _run(db, shoe, *, pace, hr, km=10.0):
    a = Activity(source="manual", distance_km=km, avg_pace_s_per_km=pace, avg_hr=hr)
    db.add(a)
    db.flush()
    db.add(ShoeRun(owned_shoe_id=shoe.id, activity_id=a.id))


def _snapshot(shoes):
    return {s.id: {a: getattr(s, a) for a in ATTRS} for s in shoes}


def _seed(db):
    retailer = Retailer(name="R", base_url="https://r.example")
    tracked = Shoe(brand="Nike", model="Pegasus 41", shoe_type="daily_trainer")
    other = Shoe(brand="Hoka", model="Clifton 9")
    db.add_all([retailer, tracked, other])
    db.flush()
    db.add_all([
        # id order matters: earliest matching row must win.
        PriceRecord(shoe_id=other.id, retailer_id=retailer.id, product_url="u", price=1,
                    image_url="https://img/clifton-a.jpg", colorway="Black / White"),
        PriceRecord(shoe_id=tracked.id, retailer_id=retailer.id, product_url="u", price=1,
                    image_url="https://img/peg-1.jpg", colorway="Blue"),
        PriceRecord(shoe_id=tracked.id, retailer_id=retailer.id, product_url="u", price=1,
                    image_url="https://img/peg-2.jpg", colorway="Blue"),
        # colorway-text match on an untracked-by-name record
        PriceRecord(shoe_id=other.id, retailer_id=retailer.id, product_url="u", price=1,
                    image_url="https://img/vomero.jpg", colorway="Vomero 17 Grey"),
        PriceRecord(shoe_id=other.id, retailer_id=retailer.id, product_url="u", price=1,
                    image_url=None, colorway="Ghost 16"),
    ])
    shoes = [
        OwnedShoe(brand="Nike", model="pegasus 41", shoe_type="Daily trainer",
                  purchase_price=150.0, current_mileage=100.0),         # via tracked shoe
        OwnedShoe(brand="Nike", model="VOMERO 17", current_mileage=0),  # via colorway, case-insens.
        OwnedShoe(brand="Saucony", model="Endorphin Speed 4",
                  purchase_price=200.0, current_mileage=50.0),          # no match
        OwnedShoe(brand="Nike", model="Pegasus 41", image_url="https://manual/img.jpg"),  # manual image
        OwnedShoe(brand="Asics", model="Gel_100%", current_mileage=5.0),  # LIKE wildcards -> fallback
        OwnedShoe(brand="Brooks", model="Ghost 16"),                     # only image-less record
    ]
    db.add_all(shoes)
    db.flush()
    # shoe 0: mixed pace/HR; shoe 1: no HR; shoe 2: no runs; shoe 4: pace only partly
    _run(db, shoes[0], pace=300, hr=150)
    _run(db, shoes[0], pace=311, hr=156)
    _run(db, shoes[0], pace=None, hr=None)
    _run(db, shoes[1], pace=270, hr=None)
    _run(db, shoes[1], pace=275, hr=None)
    _run(db, shoes[4], pace=None, hr=161)
    db.commit()
    return shoes


def test_bulk_equals_per_shoe_for_every_attribute(db):
    shoes = _seed(db)
    per_shoe = {}
    for s in shoes:
        rotation.attach_computed_fields(db, s)
        per_shoe[s.id] = {a: getattr(s, a) for a in ATTRS}
    db.expire_all()
    shoes = db.query(OwnedShoe).all()
    rotation.attach_computed_fields_bulk(db, shoes)
    assert _snapshot(shoes) == per_shoe


def test_bulk_known_values(db):
    shoes = _seed(db)
    rotation.attach_computed_fields_bulk(db, shoes)
    by = {s.model: s for s in shoes}
    assert by["pegasus 41"].matched_image_url == "https://img/peg-1.jpg"  # earliest id wins
    assert by["VOMERO 17"].matched_image_url == "https://img/vomero.jpg"
    assert by["Endorphin Speed 4"].matched_image_url is None
    assert by["Ghost 16"].matched_image_url is None  # image-less rows never match
    manual = next(s for s in shoes if s.image_url)
    assert manual.matched_image_url is None
    assert by["Endorphin Speed 4"].total_runs == 0
    assert by["Endorphin Speed 4"].lifetime_avg_pace is None
    assert by["VOMERO 17"].lifetime_avg_hr is None and by["VOMERO 17"].total_runs == 2
    assert by["pegasus 41"].total_runs == 3  # run with no pace/HR still counts


def test_bulk_empty_list(db):
    assert rotation.attach_computed_fields_bulk(db, []) == []
