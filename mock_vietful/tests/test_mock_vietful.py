import pytest
from fastapi.testclient import TestClient
from mock_vietful.app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["catalog_size"] >= 50


def test_get_products_default_pagination():
    response = client.get("/api/v1/Products")
    assert response.status_code == 200
    products = response.json()
    assert len(products) == 10  # Default PageSize is 10
    first = products[0]
    assert "sku" in first
    assert "productName" in first
    assert "price" in first
    assert "stockQuantity" in first


def test_get_products_custom_pagination():
    response = client.get("/api/v1/Products?PageIndex=1&PageSize=5")
    assert response.status_code == 200
    products = response.json()
    assert len(products) == 5


def test_filter_products_by_sku():
    # First fetch a known product
    res1 = client.get("/api/v1/Products?PageSize=1")
    known_sku = res1.json()[0]["sku"]
    
    # Filter by this SKU
    res2 = client.get(f"/api/v1/Products?SKUs={known_sku}")
    assert res2.status_code == 200
    items = res2.json()
    assert len(items) == 1
    assert items[0]["sku"] == known_sku


def test_create_new_products():
    new_product_payload = [{
        "sku": "CUSTOM-VF-999",
        "productName": "Chuột Gaming Logitech G Pro",
        "price": 1890000.0,
        "stockQuantity": 45,
        "assetType": "Single"
    }]
    response = client.post("/api/v1/Products", json=new_product_payload)
    assert response.status_code == 201
    created = response.json()
    assert len(created) == 1
    assert created[0]["sku"] == "CUSTOM-VF-999"


def test_mutation_simulation():
    response = client.post("/api/v1/simulate/mutate?mutate_ratio=0.1")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert data["summary"]["mutated_count"] >= 1


def test_chaos_outage_simulation():
    # Turn chaos on
    res_chaos = client.post("/api/v1/simulate/chaos", json={"is_down": True})
    assert res_chaos.status_code == 200
    
    # Normal product request should now fail with 503
    res_fail = client.get("/api/v1/Products")
    assert res_fail.status_code == 503

    # Turn chaos off
    client.post("/api/v1/simulate/chaos", json={"is_down": False})
    res_ok = client.get("/api/v1/Products")
    assert res_ok.status_code == 200
