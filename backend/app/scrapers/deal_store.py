"""
DealStore — all PriceRecord/Deal/PromoCode persistence.

Each method owns its own commit/rollback. The orchestrator calls these
after making deal-qualification decisions — qualification logic stays in
the orchestrator, not here.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Deal, PriceRecord, PromoCode, Retailer, Shoe

logger = logging.getLogger(__name__)


class DealStore:
    def __init__(self, db: Session):
        self.db = db

    def record_price(
        self,
        shoe: Shoe,
        retailer: Retailer,
        *,
        product_url: str,
        price: Optional[float],
        original_price: Optional[float],
        in_stock: bool,
        size_available: bool,
        sizes_available: Optional[list] = None,
        image_url: Optional[str] = None,
        colorway: Optional[str] = None,
    ) -> bool:
        if not price:
            logger.warning(f"No price found for {product_url}")
            return False

        try:
            price_record = PriceRecord(
                shoe_id=shoe.id,
                retailer_id=retailer.id,
                product_url=product_url,
                price=price,
                original_price=original_price,
                in_stock=in_stock,
                size_available=size_available,
                sizes_available=sizes_available,
                image_url=image_url,
                colorway=colorway,
            )
            self.db.add(price_record)
            self.db.commit()
            logger.info(f"Recorded price: ${price} for {shoe.brand} {shoe.model} at {retailer.name}")
            return True
        except Exception as e:
            logger.error(f"Error recording price: {e}")
            self.db.rollback()
            return False

    def upsert_deal(
        self,
        shoe: Shoe,
        retailer: Retailer,
        *,
        price: float,
        product_url: str,
        in_stock: bool,
        sizes_available: Optional[list] = None,
        image_url: Optional[str] = None,
        colorway: Optional[str] = None,
    ) -> bool:
        """
        Create or refresh a deal. Returns True only for net-new deals.

        Always refreshes image/colorway/sizes when available (older deals
        predate this data and would otherwise stay blank/stale). Refreshes
        price/savings when the scraped price OR the shoe's target_price changed
        since the deal was created — this makes target edits "stick" on
        existing deals.
        """
        try:
            savings_amount = shoe.target_price - price
            savings_percent = (savings_amount / shoe.target_price) * 100

            existing_deal = self.db.query(Deal).filter(
                Deal.shoe_id == shoe.id,
                Deal.retailer_id == retailer.id,
                Deal.is_active == True,
                Deal.product_url == product_url,
            ).first()

            if existing_deal:
                if image_url:
                    existing_deal.image_url = image_url
                if colorway:
                    existing_deal.colorway = colorway
                existing_deal.sizes_available = sizes_available
                # Refresh price/savings if the scraped price OR the shoe's
                # target_price changed since the deal was created.
                if (existing_deal.current_price != price
                        or existing_deal.target_price != shoe.target_price):
                    existing_deal.current_price = price
                    existing_deal.target_price = shoe.target_price
                    existing_deal.savings_amount = savings_amount
                    existing_deal.savings_percent = savings_percent
                    existing_deal.in_stock = in_stock
                    logger.info(f"Updated existing deal (price ${price}, target ${shoe.target_price})")
                self.db.commit()
                return False  # Not a new deal

            deal = Deal(
                shoe_id=shoe.id,
                retailer_id=retailer.id,
                current_price=price,
                target_price=shoe.target_price,
                savings_amount=savings_amount,
                savings_percent=savings_percent,
                product_url=product_url,
                in_stock=in_stock,
                sizes_available=sizes_available,
                image_url=image_url,
                colorway=colorway,
                is_active=True,
            )
            self.db.add(deal)
            self.db.commit()
            logger.info(
                f"Created deal: {shoe.brand} {shoe.model} at {retailer.name} - "
                f"${price} (save {savings_percent:.1f}%)"
            )
            return True
        except Exception as e:
            logger.error(f"Error creating deal: {e}")
            self.db.rollback()
            return False

    def deactivate_deal(self, shoe: Shoe, retailer: Retailer, product_url: str) -> bool:
        """
        Retire an active deal that no longer qualifies (price rose above target,
        or the target_price was lowered below the current price).

        Returns True if a deal was deactivated.
        """
        try:
            deal = self.db.query(Deal).filter(
                Deal.shoe_id == shoe.id,
                Deal.retailer_id == retailer.id,
                Deal.product_url == product_url,
                Deal.is_active == True,
            ).first()

            if not deal:
                return False

            deal.is_active = False
            self.db.commit()
            logger.info(
                f"Deactivated stale deal: {shoe.brand} {shoe.model} at {retailer.name} "
                f"(no longer <= target ${shoe.target_price})"
            )
            return True
        except Exception as e:
            logger.error(f"Error deactivating deal: {e}")
            self.db.rollback()
            return False

    def deactivate_orphaned_deals(self, shoe: Shoe, retailer: Retailer, seen_urls: set) -> int:
        """
        Retire active deals for this shoe+retailer whose product_url wasn't
        among the URLs just scraped. Called once per retailer after a
        successful (non-empty) search, so a transient empty response can't
        wipe out deals — only a real search that came back with different
        URLs than what's on file (most commonly: the shoe's brand/model was
        edited, so the search now resolves a different product page).

        Returns the number of deals deactivated.
        """
        if not seen_urls:
            return 0

        try:
            stale = self.db.query(Deal).filter(
                Deal.shoe_id == shoe.id,
                Deal.retailer_id == retailer.id,
                Deal.is_active == True,
                ~Deal.product_url.in_(seen_urls),
            ).all()

            for deal in stale:
                deal.is_active = False
                logger.info(
                    f"Deactivated orphaned deal: {shoe.brand} {shoe.model} at {retailer.name} "
                    f"({deal.product_url} no longer matches this shoe's search)"
                )

            if stale:
                self.db.commit()
            return len(stale)
        except Exception as e:
            logger.error(f"Error deactivating orphaned deals: {e}")
            self.db.rollback()
            return 0

    def upsert_promo_code(self, retailer: Retailer, data: dict) -> bool:
        """
        Insert a newly-detected code, or refresh an existing one.

        Returns True if a new code row was created. Manually-added codes are
        never overwritten by scraped data.
        """
        try:
            existing = self.db.query(PromoCode).filter(
                PromoCode.retailer_id == retailer.id,
                PromoCode.code == data['code'],
            ).first()

            now = datetime.now(timezone.utc)
            if existing:
                existing.last_seen_at = now
                existing.is_active = True
                if existing.source != 'manual':
                    existing.description = data.get('description') or existing.description
                    if data.get('discount_percent') is not None:
                        existing.discount_percent = data['discount_percent']
                    existing.source_url = data.get('source_url') or existing.source_url
                self.db.commit()
                return False

            promo = PromoCode(
                retailer_id=retailer.id,
                code=data['code'],
                description=data.get('description'),
                discount_percent=data.get('discount_percent'),
                discount_amount=data.get('discount_amount'),
                source='scraped',
                source_url=data.get('source_url'),
                is_active=True,
                last_seen_at=now,
            )
            self.db.add(promo)
            self.db.commit()
            logger.info(f"🏷️  New promo code for {retailer.name}: {data['code']}")
            return True
        except Exception as e:
            logger.error(f"Error upserting promo code: {e}")
            self.db.rollback()
            return False
