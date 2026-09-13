import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, func, delete
from app.db.base import Base
from app.models.product import ProductSnapshot, ProductChangeEvent
from app.schemas.product import VietfulProductInput
from app.services.change_detection import ChangeDetectionEngine
from app.core.config import settings

@pytest_asyncio.fixture
async def pg_session_factory():
    """Provides session factory connected to live PostgreSQL container."""
    engine = create_async_engine(settings.async_db_url, echo=False, pool_size=50, max_overflow=20)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_same_sku_spike_deduplication(pg_session_factory):
    """
    RACE CONDITION & EXACTLY-ONCE TEST:
    Simulates 30 concurrent coroutines attempting to insert the EXACT same SKU at the same millisecond.
    Result must be: EXACTLY 1 snapshot, EXACTLY 1 INSERT change event, and 29 DUPLICATES filtered.
    """
    test_sku = "SPIKE-RACE-001"

    # Clean up prior test state
    async with pg_session_factory() as session:
        await session.execute(delete(ProductChangeEvent).where(ProductChangeEvent.sku == test_sku))
        await session.execute(delete(ProductSnapshot).where(ProductSnapshot.sku == test_sku))
        await session.commit()

    product_payload = VietfulProductInput(
        sku=test_sku,
        partnerSKU="PTR-SPIKE-001",
        productName="Spike Test Mechanical Keyboard",
        price=1500000.0,
        stockQuantity=50
    )

    async def ingest_task():
        async with pg_session_factory() as session:
            try:
                status, event = await ChangeDetectionEngine.process_single_product(
                    session=session,
                    product=product_payload,
                    source="WEBHOOK"
                )
                await session.commit()
                return status
            except Exception as e:
                await session.rollback()
                # If unique constraint violation occurs during simultaneous INSERT, handle gracefully
                return "CONFLICT_HANDLED"

    # Fire 30 concurrent requests simultaneously
    results = await asyncio.gather(*[ingest_task() for _ in range(30)])

    # Verification in Database
    async with pg_session_factory() as session:
        snapshots_count = (await session.execute(
            select(func.count()).select_from(ProductSnapshot).where(ProductSnapshot.sku == test_sku)
        )).scalar()

        events_count = (await session.execute(
            select(func.count()).select_from(ProductChangeEvent).where(ProductChangeEvent.sku == test_sku)
        )).scalar()

    # EXACTLY-ONCE PROOF:
    assert snapshots_count == 1, "There must be exactly 1 snapshot record in PostgreSQL"
    assert events_count == 1, "There must be exactly 1 INSERT event in product_change_events"
    assert "INSERTED" in results, "At least one request must succeed with INSERTED"


@pytest.mark.asyncio
async def test_concurrent_multi_sku_burst(pg_session_factory):
    """
    BURST TEST:
    100 concurrent requests sending 10 distinct SKUs (10 requests per SKU).
    Result must be: Exactly 10 snapshots and exactly 10 change events in total.
    """
    sku_list = [f"BURST-SKU-{i:02d}" for i in range(10)]

    # Clean up
    async with pg_session_factory() as session:
        await session.execute(delete(ProductChangeEvent).where(ProductChangeEvent.sku.in_(sku_list)))
        await session.execute(delete(ProductSnapshot).where(ProductSnapshot.sku.in_(sku_list)))
        await session.commit()

    async def send_sku(sku_str: str):
        async with pg_session_factory() as session:
            prod = VietfulProductInput(
                sku=sku_str,
                productName=f"Product {sku_str}",
                price=200000.0,
                stockQuantity=100
            )
            try:
                status, _ = await ChangeDetectionEngine.process_single_product(
                    session=session, product=prod, source="POLLING"
                )
                await session.commit()
                return status
            except Exception:
                await session.rollback()
                return "RETRY_SAFE"

    # 10 SKUs x 10 concurrent requests each = 100 requests
    tasks = []
    for _ in range(10):
        for sku in sku_list:
            tasks.append(send_sku(sku))

    await asyncio.gather(*tasks)

    # Verification in Database
    async with pg_session_factory() as session:
        total_snapshots = (await session.execute(
            select(func.count()).select_from(ProductSnapshot).where(ProductSnapshot.sku.in_(sku_list))
        )).scalar()

        total_events = (await session.execute(
            select(func.count()).select_from(ProductChangeEvent).where(ProductChangeEvent.sku.in_(sku_list))
        )).scalar()

    assert total_snapshots == 10, "Must have exactly 10 unique product snapshots"
    assert total_events == 10, "Must have exactly 10 change events, 0 duplicates"
