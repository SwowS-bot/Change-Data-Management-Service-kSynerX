from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict, AliasChoices

class VietfulProductInput(BaseModel):
    """
    Standard schema matching Vietful Inventory Service Product API.
    Accepts both camelCase (Vietful standard) and snake_case aliases.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    sku: str = Field(..., description="Unique product SKU")
    partnerSKU: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("partnerSKU", "partner_sku"),
        description="Partner SKU"
    )
    productName: str = Field(
        ...,
        validation_alias=AliasChoices("productName", "product_name"),
        description="Product Name"
    )
    assetType: Optional[str] = Field(
        default="Single",
        validation_alias=AliasChoices("assetType", "asset_type"),
        description="Single, Bundle, etc."
    )
    price: Optional[float] = Field(default=0.0, description="Product Price")
    stockQuantity: Optional[int] = Field(
        default=0,
        validation_alias=AliasChoices("stockQuantity", "stock_quantity"),
        description="Available stock quantity"
    )
    barcodes: Optional[List[str]] = Field(default_factory=list, description="Associated barcodes")
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom product attributes")


class DiffField(BaseModel):
    old: Any
    new: Any


class ProductChangeEventResponse(BaseModel):
    id: int
    sku: str
    change_type: str
    old_hash: Optional[str] = None
    new_hash: str
    diff_data: Dict[str, Any]
    source: str
    ingested_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductSnapshotResponse(BaseModel):
    id: int
    sku: str
    partner_sku: Optional[str] = None
    product_name: str
    asset_type: Optional[str] = "Single"
    price: Optional[float] = 0.0
    stock_quantity: Optional[int] = 0
    raw_payload: Dict[str, Any]
    content_hash: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestionSummary(BaseModel):
    batch_id: str
    source: str
    total_records: int
    inserted_count: int
    updated_count: int
    duplicate_count: int
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
