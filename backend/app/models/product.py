import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    JSON,
    ForeignKey,
    Index,
    func
)
from app.db.base import Base

class ProductSnapshot(Base):
    """
    Stores the CURRENT latest state of each unique product SKU.
    Only updated when content_hash changes.
    """
    __tablename__ = "products_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String(100), unique=True, nullable=False, index=True)
    partner_sku = Column(String(100), nullable=True, index=True)
    product_name = Column(String(255), nullable=False)
    asset_type = Column(String(50), nullable=True, default="Single")
    price = Column(Float, nullable=True, default=0.0)
    stock_quantity = Column(Integer, nullable=True, default=0)
    raw_payload = Column(JSON, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)  # SHA-256
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<ProductSnapshot(sku='{self.sku}', version={self.version}, hash='{self.content_hash[:8]}...')>"


class ProductChangeEvent(Base):
    """
    Audit log / Change Capture table:
    STRICT REQUIREMENT: Stores ONLY new and changed data.
    Never stores unchanged/duplicate data.
    """
    __tablename__ = "product_change_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String(100), nullable=False, index=True)
    change_type = Column(String(10), nullable=False)  # 'INSERT' or 'UPDATE'
    old_hash = Column(String(64), nullable=True)
    new_hash = Column(String(64), nullable=False)
    diff_data = Column(JSON, nullable=False)  # Stores {"field": {"old": ..., "new": ...}}
    source = Column(String(20), nullable=False)  # 'POLLING', 'WEBHOOK', 'EXCEL'
    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<ProductChangeEvent(id={self.id}, sku='{self.sku}', type='{self.change_type}', source='{self.source}')>"


class IngestionBatch(Base):
    """
    Tracks metadata and metrics of each ingestion run from POLLING, WEBHOOK, or EXCEL.
    """
    __tablename__ = "ingestion_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(36), unique=True, nullable=False, index=True)
    source = Column(String(20), nullable=False)  # 'POLLING', 'WEBHOOK', 'EXCEL'
    total_records = Column(Integer, default=0, nullable=False)
    inserted_count = Column(Integer, default=0, nullable=False)
    updated_count = Column(Integer, default=0, nullable=False)
    duplicate_count = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="COMPLETED", nullable=False)  # 'RUNNING', 'COMPLETED', 'FAILED'
    error_message = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return (
            f"<IngestionBatch(id='{self.batch_id}', source='{self.source}', "
            f"ins={self.inserted_count}, upd={self.updated_count}, dup={self.duplicate_count})>"
        )
