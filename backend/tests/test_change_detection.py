import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, func
from app.db.base import Base
from app.models.product import ProductSnapshot, ProductChangeEvent, IngestionBatch
from app.schemas.product import VietfulProductInput
from app.services.change_detection import (
    compute_content_hash,
    compute_diff,
    ChangeDetectionEngine,
)

# Test DB in-memory SQLite for high-speed isolated tests
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_content_hash_deterministic():
    """Verify hash is independent of key order and strips redundant whitespace."""
    payload_1 = {
        "sku": "SKU-001",
        "productName": "Wireless Mouse",
        "price": 25.50,
        "stockQuantity": 100
    }
    # Different key ordering and trailing whitespace in string
    payload_2 = {
        "stockQuantity": 100,
        "price": 25.500,
        "productName": "Wireless Mouse  ",
        "sku": "  SKU-001",
    }
    hash_1 = compute_content_hash(payload_1)
    hash_2 = compute_content_hash(payload_2)
    assert hash_1 == hash_2, "Hashes must be identical regardless of key order or whitespace"


def test_compute_diff():
    """Verify field-level diff calculation."""
    old_data = {"price": 100.0, "stock": 50, "name": "Shirt"}
    new_data = {"price": 120.0, "stock": 50, "name": "Premium Shirt"}
    diff = compute_diff(old_data, new_data)
    
    assert "stock" not in diff, "Unchanged fields must not appear in diff"
    assert diff["price"] == {"old": 100.0, "new": 120.0}
    assert diff["name"] == {"old": "Shirt", "new": "Premium Shirt"}


@pytest.mark.asyncio
async def test_first_insert_creates_snapshot_and_change_event(async_session: AsyncSession):
    """Test 1: New product is inserted into snapshot and records an INSERT change event."""
    product = VietfulProductInput(
        sku="PROD-101",
        partnerSKU="VN-101",
        productName="Keyboard Mechanical RGB",
        assetType="Single",
        price=85.0,
        stockQuantity=30,
    )

    status, event = await ChangeDetectionEngine.process_single_product(
        session=async_session,
        product=product,
        source="POLLING",
    )
    await async_session.commit()

    assert status == "INSERTED"
    assert event is not None
    assert event.change_type == "INSERT"
    assert event.sku == "PROD-101"
    assert event.old_hash is None

    # Verify Snapshot in DB
    stmt = select(ProductSnapshot).where(ProductSnapshot.sku == "PROD-101")
    snapshot = (await async_session.execute(stmt)).scalar_one()
    assert snapshot.version == 1
    assert snapshot.product_name == "Keyboard Mechanical RGB"
    assert snapshot.price == 85.0


@pytest.mark.asyncio
async def test_idempotent_duplicate_ingestion(async_session: AsyncSession):
    """Test 2: EXACTLY-ONCE GUARANTEE: Ingesting the same product twice results in DUPLICATE (No-op)."""
    product = VietfulProductInput(
        sku="PROD-102",
        productName="Monitor 27 Inch 4K",
        price=350.0,
        stockQuantity=15,
    )

    # First ingestion
    status_1, _ = await ChangeDetectionEngine.process_single_product(
        session=async_session, product=product, source="POLLING"
    )
    await async_session.commit()
    assert status_1 == "INSERTED"

    # Second ingestion with identical data (from WEBHOOK)
    status_2, event_2 = await ChangeDetectionEngine.process_single_product(
        session=async_session, product=product, source="WEBHOOK"
    )
    await async_session.commit()
    assert status_2 == "DUPLICATE"
    assert event_2 is None

    # Verify event count is EXACTLY 1 (No duplicate audit logs allowed)
    count_stmt = select(func.count()).select_from(ProductChangeEvent).where(ProductChangeEvent.sku == "PROD-102")
    events_count = (await async_session.execute(count_stmt)).scalar()
    assert events_count == 1, "Duplicate data must NEVER be added to the change events table"


@pytest.mark.asyncio
async def test_product_update_records_diff_and_increments_version(async_session: AsyncSession):
    """Test 3: Changing a product price/stock records an UPDATE change event with diff."""
    initial_product = VietfulProductInput(
        sku="PROD-103",
        productName="USB-C Hub 7-in-1",
        price=45.0,
        stockQuantity=20,
    )
    await ChangeDetectionEngine.process_single_product(
        session=async_session, product=initial_product, source="POLLING"
    )
    await async_session.commit()

    # Update product price and stock
    updated_product = VietfulProductInput(
        sku="PROD-103",
        productName="USB-C Hub 7-in-1",
        price=39.99,  # Discounted
        stockQuantity=18,  # Sold 2
    )
    status, event = await ChangeDetectionEngine.process_single_product(
        session=async_session, product=updated_product, source="WEBHOOK"
    )
    await async_session.commit()

    assert status == "UPDATED"
    assert event is not None
    assert event.change_type == "UPDATE"
    assert "price" in event.diff_data
    assert event.diff_data["price"]["old"] == 45.0
    assert event.diff_data["price"]["new"] == 39.99
    assert event.diff_data["stockQuantity"]["old"] == 20
    assert event.diff_data["stockQuantity"]["new"] == 18

    # Verify Snapshot updated version
    stmt = select(ProductSnapshot).where(ProductSnapshot.sku == "PROD-103")
    snapshot = (await async_session.execute(stmt)).scalar_one()
    assert snapshot.version == 2
    assert snapshot.price == 39.99


@pytest.mark.asyncio
async def test_batch_processing_metrics(async_session: AsyncSession):
    """Test 4: Batch processing correctly calculates inserted, updated, and duplicate counts."""
    batch_1 = [
        VietfulProductInput(sku="B-001", productName="Item 1", price=10.0),
        VietfulProductInput(sku="B-002", productName="Item 2", price=20.0),
        VietfulProductInput(sku="B-003", productName="Item 3", price=30.0),
    ]
    summary_1 = await ChangeDetectionEngine.process_batch(
        session=async_session, products=batch_1, source="EXCEL"
    )
    assert summary_1.total_records == 3
    assert summary_1.inserted_count == 3
    assert summary_1.updated_count == 0
    assert summary_1.duplicate_count == 0

    # Batch 2: Item 1 unchanged, Item 2 updated, Item 4 brand new
    batch_2 = [
        VietfulProductInput(sku="B-001", productName="Item 1", price=10.0),  # Duplicate
        VietfulProductInput(sku="B-002", productName="Item 2", price=25.0),  # Updated
        VietfulProductInput(sku="B-004", productName="Item 4", price=40.0),  # New
    ]
    summary_2 = await ChangeDetectionEngine.process_batch(
        session=async_session, products=batch_2, source="POLLING"
    )
    assert summary_2.total_records == 3
    assert summary_2.inserted_count == 1
    assert summary_2.updated_count == 1
    assert summary_2.duplicate_count == 1
