"""
Database models using SQLAlchemy ORM
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Shoe(Base):
    """
    Model for tracking specific running shoes we want to monitor
    """
    __tablename__ = "shoes"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String(100), nullable=False, index=True)  # e.g., "Adidas", "Nike"
    model = Column(String(200), nullable=False, index=True)  # e.g., "Adizero Adios Pro 3"
    # Size intentionally removed: we track a model across ALL sizes so the
    # scraper isn't restricted to one exact size that may be out of stock.
    target_price = Column(Float, nullable=False)  # Price we want to pay
    msrp = Column(Float, nullable=True)  # Manufacturer's list price — kept separate
    # from target_price so "at target" and "actually below MSRP" can't be confused.
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
    # generic scraper built automatically (see scraper_manager.build_dynamic_scraper);
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
    Active deals when price drops below target
    """
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)
    shoe_id = Column(Integer, ForeignKey("shoes.id"), nullable=False, index=True)
    retailer_id = Column(Integer, ForeignKey("retailers.id"), nullable=False, index=True)
    current_price = Column(Float, nullable=False)
    target_price = Column(Float, nullable=False)
    savings_amount = Column(Float, nullable=False)  # How much we save
    savings_percent = Column(Float, nullable=False)  # Percentage discount
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
