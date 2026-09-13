import asyncio
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mock_vietful.app.generator import (
    generate_initial_catalog,
    generate_product,
    mutate_catalog
)

app = FastAPI(
    title="Emulating Vietful Inventory Service",
    description="Mock implementation of Vietful External API (https://ext.stg.vnfai.com/doc/index.html#tag/Products)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory product database
CATALOG: List[Dict[str, Any]] = generate_initial_catalog(count=50)

# Chaos / Failure simulation state
CHAOS_STATE = {
    "error_rate": 0.0,       # 0.0 to 1.0 (probability of 500 error)
    "latency_seconds": 0.0,  # Simulated network latency
    "is_down": False         # Complete outage simulation
}

class CreateProductDto(BaseModel):
    sku: str
    partnerSKU: Optional[str] = None
    productName: str
    assetType: Optional[str] = "Single"
    price: Optional[float] = 0.0
    stockQuantity: Optional[int] = 0
    barcodes: Optional[List[str]] = Field(default_factory=list)
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ChaosConfigRequest(BaseModel):
    is_down: Optional[bool] = None
    latency_seconds: Optional[float] = None
    error_rate: Optional[float] = None

@app.middleware("http")
async def chaos_middleware(request, call_next):
    """Simulates service downtime or latency for resilience testing."""
    if request.url.path.startswith("/api/v1/simulate"):
        # Don't block simulation control endpoints
        return await call_next(request)
        
    if CHAOS_STATE["is_down"]:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Vietful Inventory Service is currently DOWN (Simulated Outage)"}
        )
    if CHAOS_STATE["latency_seconds"] > 0:
        await asyncio.sleep(CHAOS_STATE["latency_seconds"])
        
    return await call_next(request)


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy" if not CHAOS_STATE["is_down"] else "outage",
        "service": "Vietful Inventory Service Emulator",
        "catalog_size": len(CATALOG),
        "chaos_state": CHAOS_STATE
    }


@app.get("/api/v1/Products", tags=["Products"], response_model=List[Dict[str, Any]])
def get_products(
    Keyword: Optional[str] = Query(None, description="SKU or product name search"),
    PartnerSKUs: Optional[str] = Query(None, description="Comma-separated PartnerSKUs"),
    SKUs: Optional[str] = Query(None, description="Comma-separated SKUs"),
    PageIndex: int = Query(0, ge=0, description="Page index (0-based)"),
    PageSize: int = Query(10, ge=1, le=100, description="Page size")
):
    """
    Get product list ordered by product identity number.
    Conforms to Vietful API spec: GET /api/v1/Products
    """
    results = CATALOG

    # Filter by SKUs
    if SKUs:
        sku_set = {s.strip() for s in SKUs.split(",") if s.strip()}
        results = [p for p in results if p.get("sku") in sku_set]

    # Filter by PartnerSKUs
    if PartnerSKUs:
        partner_set = {s.strip() for s in PartnerSKUs.split(",") if s.strip()}
        results = [p for p in results if p.get("partnerSKU") in partner_set]

    # Filter by Keyword
    if Keyword:
        kw = Keyword.lower().strip()
        results = [
            p for p in results
            if kw in p.get("sku", "").lower() or kw in p.get("productName", "").lower()
        ]

    # Pagination
    start_idx = PageIndex * PageSize
    end_idx = start_idx + PageSize
    return results[start_idx:end_idx]


@app.get("/api/v1/Products/{partnerSKU}", tags=["Products"])
def get_product_detail(partnerSKU: str):
    """
    Get single product details by PartnerSKU.
    Conforms to Vietful API spec: GET /api/v1/Products/{partnerSKU}
    """
    for p in CATALOG:
        if p.get("partnerSKU") == partnerSKU:
            return p
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Product with PartnerSKU '{partnerSKU}' not found"
    )


@app.post("/api/v1/Products", tags=["Products"], status_code=status.HTTP_201_CREATED)
def create_products(products: List[CreateProductDto]):
    """
    Create a group of products.
    Conforms to Vietful API spec: POST /api/v1/Products
    """
    created_items = []
    for item in products:
        new_id = len(CATALOG) + 1
        product_dict = {
            "productId": new_id,
            "sku": item.sku,
            "partnerSKU": item.partnerSKU or f"PTR-{item.sku}",
            "productName": item.productName,
            "assetType": item.assetType or "Single",
            "price": item.price,
            "stockQuantity": item.stockQuantity,
            "barcodes": item.barcodes or [],
            "attributes": item.attributes or {},
            "conditionType": "New"
        }
        CATALOG.append(product_dict)
        created_items.append(product_dict)
    return created_items


# ==========================================
# Simulation & Testing Controls
# ==========================================

@app.post("/api/v1/simulate/mutate", tags=["Simulation"])
def trigger_mutation(mutate_ratio: float = Query(0.2, ge=0.01, le=1.0)):
    """
    Trigger real-time inventory changes (price/stock adjustments)
    so CDMS polling can detect changes.
    """
    summary = mutate_catalog(CATALOG, mutate_ratio=mutate_ratio)
    return {
        "message": "Inventory catalog mutated successfully",
        "summary": summary
    }


@app.post("/api/v1/simulate/chaos", tags=["Simulation"])
def configure_chaos(config: ChaosConfigRequest):
    """
    Toggle simulated network latency or outage.
    Used for CDMS fault-tolerance & resilience verification.
    """
    if config.is_down is not None:
        CHAOS_STATE["is_down"] = config.is_down
    if config.latency_seconds is not None:
        CHAOS_STATE["latency_seconds"] = config.latency_seconds
    if config.error_rate is not None:
        CHAOS_STATE["error_rate"] = config.error_rate
    return {
        "message": "Chaos state updated",
        "current_state": CHAOS_STATE
    }


@app.post("/api/v1/simulate/reset", tags=["Simulation"])
def reset_catalog(count: int = 50):
    """Reset catalog to a fresh set of products."""
    global CATALOG
    CATALOG = generate_initial_catalog(count=count)
    CHAOS_STATE["is_down"] = False
    CHAOS_STATE["latency_seconds"] = 0.0
    CHAOS_STATE["error_rate"] = 0.0
    return {
        "message": f"Catalog reset with {count} products",
        "catalog_size": len(CATALOG)
    }
