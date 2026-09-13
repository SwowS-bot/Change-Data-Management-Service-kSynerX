import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, func, delete
from app.db.base import Base
from app.models.product import ProductSnapshot, ProductChangeEvent, IngestionBatch
from app.schemas.product import VietfulProductInput
from app.services.change_detection import ChangeDetectionEngine
from app.core.config import settings

@pytest_asyncio.fixture
async def pg_session():
    """Connects to the REAL PostgreSQL database running in Docker container."""
    engine = create_async_engine(settings.async_db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_live_exactly_once(pg_session: AsyncSession):
    """
    Integration test with live PostgreSQL:
    1. Insert product
    2. Try to insert exact same product again (ensure deduplication)
    3. Update product price
    4. Verify Postgres tables
    """
    test_sku = "PG-TEST-001"
    
    # Cleanup any prior test run in both tables
    await pg_session.execute(delete(ProductChangeEvent).where(ProductChangeEvent.sku == test_sku))
    await pg_session.execute(delete(ProductSnapshot).where(ProductSnapshot.sku == test_sku))
    await pg_session.commit()

    product = VietfulProductInput(
        sku=test_sku,
        partnerSKU="PARTNER-PG-1",
        productName="PostgreSQL Enterprise Server",
        price=1200.0,
        stockQuantity=5,
    )

    # 1. First Ingestion -> INSERT
    status_1, event_1 = await ChangeDetectionEngine.process_single_product(
        session=pg_session, product=product, source="POLLING"
    )
    await pg_session.commit()
    assert status_1 == "INSERTED"
    assert event_1.change_type == "INSERT"

    # 2. Duplicate Ingestion -> DUPLICATE (Exactly-Once)
    status_2, event_2 = await ChangeDetectionEngine.process_single_product(
        session=pg_session, product=product, source="WEBHOOK"
    )
    await pg_session.commit()
    assert status_2 == "DUPLICATE"
    assert event_2 is None

    # 3. Update Ingestion -> UPDATE
    updated_product = VietfulProductInput(
        sku=test_sku,
        partnerSKU="PARTNER-PG-1",
        productName="PostgreSQL Enterprise Server v16",
        price=1250.0,
        stockQuantity=4,
    )
    status_3, event_3 = await ChangeDetectionEngine.process_single_product(
        session=pg_session, product=updated_product, source="EXCEL"
    )
    await pg_session.commit()
    assert status_3 == "UPDATED"
    assert event_3.change_type == "UPDATE"
    assert "price" in event_3.diff_data

    # Verify counts in Postgres
    events_count = await pg_session.execute(
        select(func.count()).select_from(ProductChangeEvent).where(ProductChangeEvent.sku == test_sku)
    )
    assert events_count.scalar() == 2  # Exactly 1 INSERT + 1 UPDATE, 0 DUPLICATES!
