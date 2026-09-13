import io
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import app
from app.db.base import Base
from app.db.session import get_async_db
from app.services.excel_service import generate_sample_excel
from app.services.poller import ScheduledPoller, CircuitState

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def override_db():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_test_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_db] = _get_test_db
    yield
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def client(override_db):
    return TestClient(app)


def test_webhook_single_product_lifecycle(client: TestClient):
    """
    Verifies full lifecycle over Webhook endpoint:
    1. First push -> INSERTED
    2. Same push -> DUPLICATE
    3. Modified push -> UPDATED
    """
    payload = {
        "sku": "WH-TEST-001",
        "productName": "Gaming Mouse RGB",
        "price": 500000.0,
        "stockQuantity": 20
    }

    # 1. First Ingestion
    res1 = client.post("/api/v1/cdc/webhook", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "INSERTED"
    assert data1["change_type"] == "INSERT"

    # 2. Duplicate Ingestion (Exactly-Once check)
    res2 = client.post("/api/v1/cdc/webhook", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "DUPLICATE"
    assert data2["change_type"] is None

    # 3. Update Price
    payload["price"] = 550000.0
    res3 = client.post("/api/v1/cdc/webhook", json=payload)
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["status"] == "UPDATED"
    assert data3["change_type"] == "UPDATE"


def test_webhook_batch_products(client: TestClient):
    """Verifies batch webhook ingestion."""
    batch = [
        {"sku": "WH-B-001", "productName": "Product A", "price": 100000.0, "stockQuantity": 10},
        {"sku": "WH-B-002", "productName": "Product B", "price": 200000.0, "stockQuantity": 20},
    ]
    res = client.post("/api/v1/cdc/webhook", json=batch)
    assert res.status_code == 200
    data = res.json()
    assert data["total_records"] == 2
    assert data["inserted_count"] == 2


def test_excel_upload_api(client: TestClient):
    """Verifies uploading an in-memory .xlsx file via REST API."""
    excel_bytes = generate_sample_excel()
    file_payload = {
        "file": ("test_catalog.xlsx", io.BytesIO(excel_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }

    res = client.post("/api/v1/cdc/upload-excel", files=file_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["total_records"] == 5
    assert data["inserted_count"] == 5
    assert data["duplicate_count"] == 0

    # Uploading the exact same Excel file again must result in 100% duplicates prevented
    res_dup = client.post("/api/v1/cdc/upload-excel", files={
        "file": ("test_catalog.xlsx", io.BytesIO(excel_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    })
    assert res_dup.status_code == 200
    data_dup = res_dup.json()
    assert data_dup["inserted_count"] == 0
    assert data_dup["duplicate_count"] == 5, "All 5 products must be detected as duplicates"


def test_cdc_query_endpoints_and_stats(client: TestClient):
    """Verifies query endpoints: events, products snapshot, and overall stats."""
    # Seed 1 product
    client.post("/api/v1/cdc/webhook", json={
        "sku": "QUERY-001", "productName": "Query Test Item", "price": 99000.0
    })

    # Query events
    res_events = client.get("/api/v1/cdc/events?sku=QUERY-001")
    assert res_events.status_code == 200
    events = res_events.json()
    assert len(events) >= 1
    assert events[0]["sku"] == "QUERY-001"

    # Query products snapshot
    res_products = client.get("/api/v1/cdc/products?keyword=Query")
    assert res_products.status_code == 200
    products = res_products.json()
    assert len(products) == 1
    assert products[0]["sku"] == "QUERY-001"

    # Query stats
    res_stats = client.get("/api/v1/cdc/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total_active_products"] >= 1
    assert stats["total_change_events"] >= 1


@pytest.mark.asyncio
async def test_poller_circuit_breaker_resilience():
    """
    Tests that the ScheduledPoller handles failures with circuit breaker
    without raising unhandled exceptions or crashing.
    """
    bad_poller = ScheduledPoller(base_url="http://non-existent-host:9999", interval_seconds=1)
    
    # 1st failure
    await bad_poller.poll_once()
    assert bad_poller.failed_polls == 1
    assert bad_poller.circuit_state == CircuitState.CLOSED

    # 2nd failure
    await bad_poller.poll_once()
    assert bad_poller.failed_polls == 2

    # 3rd failure (trips threshold)
    await bad_poller.poll_once()
    assert bad_poller.failed_polls == 3
    assert bad_poller.circuit_state == CircuitState.OPEN
    assert bad_poller.consecutive_errors == 3
