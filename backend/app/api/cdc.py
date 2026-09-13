from typing import List, Optional, Union
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.db.session import get_async_db
from app.models.product import ProductSnapshot, ProductChangeEvent, IngestionBatch
from app.schemas.product import (
    VietfulProductInput,
    ProductSnapshotResponse,
    ProductChangeEventResponse,
    IngestionSummary,
)
from app.services.change_detection import ChangeDetectionEngine
from app.services.excel_service import parse_excel_products, generate_sample_excel
from app.services.poller import poller

router = APIRouter(prefix="/cdc", tags=["Change Data Capture"])


@router.post("/webhook", response_model=Union[IngestionSummary, dict])
async def receive_webhook(
    payload: Union[VietfulProductInput, List[VietfulProductInput]],
    db: AsyncSession = Depends(get_async_db),
):
    """
    Kênh 2: Webhook Callback
    Tiếp nhận push dữ liệu từ EmulatingCallbackClient hoặc các webhook bên ngoài.
    Hỗ trợ cả 1 sản phẩm hoặc một mảng nhiều sản phẩm.
    """
    if isinstance(payload, list):
        if not payload:
            raise HTTPException(status_code=400, detail="Payload list cannot be empty")
        summary = await ChangeDetectionEngine.process_batch(
            session=db,
            products=payload,
            source="WEBHOOK"
        )
        return summary
    else:
        status_code, event = await ChangeDetectionEngine.process_single_product(
            session=db,
            product=payload,
            source="WEBHOOK"
        )
        await db.commit()
        return {
            "status": status_code,
            "sku": payload.sku,
            "change_type": event.change_type if event else None,
            "message": "Processed successfully with exactly-once guarantee"
        }


@router.post("/upload-excel", response_model=IngestionSummary)
async def upload_excel_file(
    file: UploadFile = File(..., description="Excel (.xlsx) file containing product inventory data"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Kênh 3: Excel File Upload
    Tiếp nhận file Excel tải lên qua REST API từ REST-based Client.
    Parse và đối soát thay đổi với Exactly-Once semantics.
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only .xlsx files are supported."
        )

    try:
        content = await file.read()
        products = parse_excel_products(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse Excel file: {str(e)}"
        )

    if not products:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid product records found in the uploaded Excel file"
        )

    summary = await ChangeDetectionEngine.process_batch(
        session=db,
        products=products,
        source="EXCEL"
    )
    return summary


@router.post("/trigger-poll")
async def trigger_manual_poll():
    """
    Kích hoạt Scheduled Poller quét Vietful Inventory Service ngay lập tức.
    """
    summary = await poller.poll_once()
    return {
        "message": "Manual poll executed",
        "result": summary or "Vietful unreachable or no new data",
        "poller_status": poller.get_status()
    }


@router.get("/download-sample-excel")
def download_sample_excel():
    """
    Tải về file Excel mẫu chuẩn cấu trúc để kiểm thử chức năng upload.
    """
    excel_bytes = generate_sample_excel()
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=vietful_sample_products.xlsx"}
    )


@router.get("/events", response_model=List[ProductChangeEventResponse])
async def get_change_events(
    sku: Optional[str] = Query(None, description="Filter by SKU"),
    change_type: Optional[str] = Query(None, description="INSERT or UPDATE"),
    source: Optional[str] = Query(None, description="POLLING, WEBHOOK, or EXCEL"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Lấy danh sách các sự kiện thay đổi dữ liệu (Audit/Change events).
    """
    stmt = select(ProductChangeEvent)
    if sku:
        stmt = stmt.where(ProductChangeEvent.sku == sku)
    if change_type:
        stmt = stmt.where(ProductChangeEvent.change_type == change_type.upper())
    if source:
        stmt = stmt.where(ProductChangeEvent.source == source.upper())

    stmt = stmt.order_by(desc(ProductChangeEvent.ingested_at)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/products", response_model=List[ProductSnapshotResponse])
async def get_products_snapshot(
    keyword: Optional[str] = Query(None, description="Search by SKU or name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Lấy danh sách trạng thái snapshot hiện tại của các sản phẩm.
    """
    stmt = select(ProductSnapshot)
    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(
            (ProductSnapshot.sku.ilike(kw)) | (ProductSnapshot.product_name.ilike(kw))
        )
    stmt = stmt.order_by(desc(ProductSnapshot.updated_at)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/batches")
async def get_batches(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Lấy lịch sử các đợt nạp dữ liệu.
    """
    stmt = (
        select(IngestionBatch)
        .order_by(desc(IngestionBatch.created_at))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    batches = result.scalars().all()
    return [
        {
            "id": b.id,
            "batch_id": b.batch_id,
            "source": b.source,
            "total_records": b.total_records,
            "inserted_count": b.inserted_count,
            "updated_count": b.updated_count,
            "duplicate_count": b.duplicate_count,
            "status": b.status,
            "created_at": b.created_at
        }
        for b in batches
    ]


@router.get("/stats")
async def get_overview_stats(db: AsyncSession = Depends(get_async_db)):
    """
    Tổng hợp thống kê toàn diện cho Dashboard và báo cáo kiểm thử.
    """
    total_products = (await db.execute(select(func.count(ProductSnapshot.id)))).scalar() or 0
    total_events = (await db.execute(select(func.count(ProductChangeEvent.id)))).scalar() or 0
    total_inserts = (
        await db.execute(
            select(func.count(ProductChangeEvent.id)).where(ProductChangeEvent.change_type == "INSERT")
        )
    ).scalar() or 0
    total_updates = (
        await db.execute(
            select(func.count(ProductChangeEvent.id)).where(ProductChangeEvent.change_type == "UPDATE")
        )
    ).scalar() or 0
    
    # Calculate duplicates prevented from batch logs
    total_duplicates_prevented = (
        await db.execute(select(func.sum(IngestionBatch.duplicate_count)))
    ).scalar() or 0

    return {
        "total_active_products": total_products,
        "total_change_events": total_events,
        "total_inserts": total_inserts,
        "total_updates": total_updates,
        "total_duplicates_prevented": total_duplicates_prevented,
        "poller_status": poller.get_status()
    }
