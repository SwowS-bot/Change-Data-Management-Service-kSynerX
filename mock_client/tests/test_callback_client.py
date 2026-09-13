import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from mock_client.callback_client import generate_webhook_product_payload, push_event

def test_generate_webhook_product_payload():
    payload = generate_webhook_product_payload(sku="TEST-SKU-001", price=150000.0, stock=20)
    assert payload["sku"] == "TEST-SKU-001"
    assert payload["price"] == 150000.0
    assert payload["stockQuantity"] == 20
    assert "productName" in payload
    assert "attributes" in payload
    assert payload["attributes"]["sourceEvent"] == "CDC_WEBHOOK"


@pytest.mark.asyncio
async def test_push_event_success():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "INSERTED", "sku": "TEST-SKU-001"}
    mock_response.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_response

    payload = {"sku": "TEST-SKU-001"}
    result = await push_event(mock_client, "http://localhost:8000/api/v1/cdc/webhook", payload)
    assert result["status"] == "INSERTED"


@pytest.mark.asyncio
async def test_push_event_network_failure_handling():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ConnectError("Connection refused")

    payload = {"sku": "TEST-SKU-001"}
    result = await push_event(mock_client, "http://localhost:8000/api/v1/cdc/webhook", payload)
    assert result["status"] == "failed"
    assert "Connection refused" in result["error"]
