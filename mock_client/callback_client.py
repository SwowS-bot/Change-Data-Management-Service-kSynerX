import asyncio
import random
import logging
import argparse
from typing import Dict, Any, List, Optional
import httpx
from faker import Faker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EmulatingCallbackClient")

fake = Faker(['vi_VN', 'en_US'])

CATEGORIES = [
    "Laptop", "Bàn phím cơ", "Chuột không dây", "Tai nghe chống ồn", "Màn hình 4K",
    "Ổ cứng SSD", "Cáp sạc Type-C", "Đồng hồ thông minh", "Loa Bluetooth", "Webcam HD"
]

def generate_webhook_product_payload(
    sku: Optional[str] = None,
    product_name: Optional[str] = None,
    price: Optional[float] = None,
    stock: Optional[int] = None
) -> Dict[str, Any]:
    """
    Generates a realistic product change event conforming to Vietful API schema.
    """
    category = random.choice(CATEGORIES)
    sku_val = sku or f"VF-WH-{random.randint(100, 999)}"
    name_val = product_name or f"{category} {fake.company()}"
    price_val = price if price is not None else round(random.uniform(100000, 15000000), 2)
    stock_val = stock if stock is not None else random.randint(5, 200)

    return {
        "sku": sku_val,
        "partnerSKU": f"PTR-{sku_val}",
        "productName": name_val,
        "assetType": "Single",
        "price": price_val,
        "stockQuantity": stock_val,
        "barcodes": [fake.ean13()],
        "attributes": {
            "sourceEvent": "CDC_WEBHOOK",
            "warehouse": fake.city(),
            "lastAudited": fake.iso8601()
        }
    }


async def push_event(
    client: httpx.AsyncClient,
    webhook_url: str,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Sends a POST request with product payload to CDMS Webhook endpoint.
    """
    try:
        response = await client.post(webhook_url, json=payload, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        logger.warning(f"Failed to push webhook to {webhook_url}: {exc}")
        return {"error": str(exc), "status": "failed"}


async def run_callback_client(
    webhook_url: str = "http://localhost:8000/api/v1/cdc/webhook",
    total_events: int = 10,
    interval_seconds: float = 1.0,
    duplicate_ratio: float = 0.3
):
    """
    Simulates real-world callback activity:
    - Periodically pushes product events to CDMS Webhook API.
    - Intermittently sends duplicate events to test Exactly-Once deduplication.
    """
    logger.info(f"Starting EmulatingCallbackClient -> Target: {webhook_url}")
    logger.info(f"Total events: {total_events}, Interval: {interval_seconds}s, Duplicate ratio: {duplicate_ratio * 100}%")

    history_payloads: List[Dict[str, Any]] = []

    async with httpx.AsyncClient() as client:
        for i in range(total_events):
            # Check if we should simulate a duplicate event
            is_duplicate = False
            if history_payloads and random.random() < duplicate_ratio:
                payload = random.choice(history_payloads)
                is_duplicate = True
                logger.info(f"[{i+1}/{total_events}] Simulating DUPLICATE event for SKU: {payload['sku']}")
            else:
                payload = generate_webhook_product_payload()
                history_payloads.append(payload)
                logger.info(f"[{i+1}/{total_events}] Generated NEW event for SKU: {payload['sku']} ({payload['productName']})")

            res = await push_event(client, webhook_url, payload)
            logger.info(f"Server response: {res}")

            if i < total_events - 1:
                await asyncio.sleep(interval_seconds)

    logger.info("Callback client finished sending events.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vietful CDC Emulating Callback Client")
    parser.add_argument("--url", default="http://localhost:8000/api/v1/cdc/webhook", help="CDMS Webhook URL")
    parser.add_argument("--count", type=int, default=5, help="Number of events to send")
    parser.add_argument("--interval", type=float, default=0.5, help="Delay between events (seconds)")
    parser.add_argument("--duplicate-ratio", type=float, default=0.3, help="Ratio of duplicate events (0.0 - 1.0)")
    args = parser.parse_args()

    asyncio.run(run_callback_client(
        webhook_url=args.url,
        total_events=args.count,
        interval_seconds=args.interval,
        duplicate_ratio=args.duplicate_ratio
    ))
