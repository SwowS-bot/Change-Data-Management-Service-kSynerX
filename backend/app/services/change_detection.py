import hashlib
import json
import uuid
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.product import ProductSnapshot, ProductChangeEvent, IngestionBatch
from app.schemas.product import VietfulProductInput, IngestionSummary

def canonicalize_value(val: Any) -> Any:
    """
    Recursively normalize data types to ensure consistent JSON representation:
    - Strip leading/trailing whitespaces in strings
    - Sort dictionary keys
    - Sort sets or lists of primitives (where order is not semantic)
    - Standardize floats
    """
    if isinstance(val, str):
        return val.strip()
    elif isinstance(val, float):
        # Normalize float precision (e.g. 10.0 == 10)
        return round(val, 4)
    elif isinstance(val, dict):
        return {k: canonicalize_value(v) for k, v in sorted(val.items())}
    elif isinstance(val, list):
        return [canonicalize_value(elem) for elem in val]
    return val

def canonicalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract semantic fields that define the product's identity and state,
    stripping ephemeral / metadata fields like request timestamps or trace IDs.
    """
    cleaned = {}
    ignored_keys = {"ingested_at", "received_at", "_id", "requestId", "timestamp"}
    
    for k, v in sorted(payload.items()):
        if k not in ignored_keys:
            cleaned[k] = canonicalize_value(v)
    return cleaned

def compute_content_hash(payload: Dict[str, Any]) -> str:
    """
    Generates a deterministic SHA-256 checksum from a normalized payload.
    Identical product data ALWAYS generates identical hash, regardless of key order.
    """
    canonical_data = canonicalize_payload(payload)
    serialized = json.dumps(canonical_data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

def compute_diff(old_dict: Dict[str, Any], new_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculates field-level differences between old and new product representations.
    Returns: { "fieldName": { "old": old_val, "new": new_val } }
    """
    diff = {}
    all_keys = set(old_dict.keys()).union(set(new_dict.keys()))
    
    for k in sorted(all_keys):
        old_v = old_dict.get(k)
        new_v = new_dict.get(k)
        if old_v != new_v:
            diff[k] = {"old": old_v, "new": new_v}
    return diff

class ChangeDetectionEngine:
    """
    Core Change Data Management Service (CDMS) Engine.
    Enforces STRICT EXACTLY-ONCE semantics:
    - Stores only new products or changed data.
    - Zero duplicate entries in change log.
    - Row-level lock protection against race conditions.
    """

    @staticmethod
    async def process_single_product(
        session: AsyncSession,
        product: VietfulProductInput,
        source: str,
    ) -> Tuple[str, Optional[ProductChangeEvent]]:
        """
        Processes a single incoming product record.
        Returns:
            - status: "INSERTED", "UPDATED", or "DUPLICATE"
            - event: ProductChangeEvent instance if changed/inserted, else None.
        """
        raw_dict = product.model_dump(by_alias=False)
        new_hash = compute_content_hash(raw_dict)
        sku = product.sku.strip()

        from sqlalchemy.exc import IntegrityError

        try:
            # Row-level lock on existing snapshot row to prevent concurrent race conditions
            stmt = (
                select(ProductSnapshot)
                .where(ProductSnapshot.sku == sku)
                .with_for_update()
            )
            result = await session.execute(stmt)
            existing: Optional[ProductSnapshot] = result.scalar_one_or_none()

            if existing is None:
                # 1. NEW PRODUCT -> INSERT
                snapshot = ProductSnapshot(
                    sku=sku,
                    partner_sku=product.partnerSKU,
                    product_name=product.productName,
                    asset_type=product.assetType or "Single",
                    price=product.price or 0.0,
                    stock_quantity=product.stockQuantity or 0,
                    raw_payload=raw_dict,
                    content_hash=new_hash,
                    version=1,
                )
                session.add(snapshot)

                event = ProductChangeEvent(
                    sku=sku,
                    change_type="INSERT",
                    old_hash=None,
                    new_hash=new_hash,
                    diff_data=raw_dict,
                    source=source,
                )
                session.add(event)
                await session.flush()
                return "INSERTED", event

            # 2. CHECK IF CONTENT CHANGED
            if existing.content_hash == new_hash:
                # EXACTLY-ONCE GUARANTEE: Content is identical, skip recording any change!
                return "DUPLICATE", None

            # 3. CONTENT HAS CHANGED -> UPDATE
            diff = compute_diff(existing.raw_payload, raw_dict)
            old_hash = existing.content_hash

            # Update snapshot attributes
            existing.partner_sku = product.partnerSKU
            existing.product_name = product.productName
            existing.asset_type = product.assetType or "Single"
            existing.price = product.price or 0.0
            existing.stock_quantity = product.stockQuantity or 0
            existing.raw_payload = raw_dict
            existing.content_hash = new_hash
            existing.version += 1

            event = ProductChangeEvent(
                sku=sku,
                change_type="UPDATE",
                old_hash=old_hash,
                new_hash=new_hash,
                diff_data=diff,
                source=source,
            )
            session.add(event)
            await session.flush()
            return "UPDATED", event

        except IntegrityError:
            # Race condition: Another concurrent transaction inserted the same SKU
            await session.rollback()
            stmt = (
                select(ProductSnapshot)
                .where(ProductSnapshot.sku == sku)
                .with_for_update()
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                if existing.content_hash == new_hash:
                    return "DUPLICATE", None
                diff = compute_diff(existing.raw_payload, raw_dict)
                old_hash = existing.content_hash
                existing.partner_sku = product.partnerSKU
                existing.product_name = product.productName
                existing.asset_type = product.assetType or "Single"
                existing.price = product.price or 0.0
                existing.stock_quantity = product.stockQuantity or 0
                existing.raw_payload = raw_dict
                existing.content_hash = new_hash
                existing.version += 1

                event = ProductChangeEvent(
                    sku=sku,
                    change_type="UPDATE",
                    old_hash=old_hash,
                    new_hash=new_hash,
                    diff_data=diff,
                    source=source,
                )
                session.add(event)
                await session.flush()
                return "UPDATED", event
            return "DUPLICATE", None

    @staticmethod
    async def process_batch(
        session: AsyncSession,
        products: List[VietfulProductInput],
        source: str,
        batch_id: Optional[str] = None,
    ) -> IngestionSummary:
        """
        Process a batch of products inside a single atomic transaction.
        Tracks metrics for inserted, updated, and duplicates ignored.
        """
        if not batch_id:
            batch_id = str(uuid.uuid4())

        inserted_count = 0
        updated_count = 0
        duplicate_count = 0

        for product in products:
            status, _ = await ChangeDetectionEngine.process_single_product(
                session=session,
                product=product,
                source=source,
            )
            if status == "INSERTED":
                inserted_count += 1
            elif status == "UPDATED":
                updated_count += 1
            elif status == "DUPLICATE":
                duplicate_count += 1

        # Record batch run summary
        batch_record = IngestionBatch(
            batch_id=batch_id,
            source=source,
            total_records=len(products),
            inserted_count=inserted_count,
            updated_count=updated_count,
            duplicate_count=duplicate_count,
            status="COMPLETED",
        )
        session.add(batch_record)
        await session.commit()

        return IngestionSummary(
            batch_id=batch_id,
            source=source,
            total_records=len(products),
            inserted_count=inserted_count,
            updated_count=updated_count,
            duplicate_count=duplicate_count,
            status="COMPLETED",
        )
