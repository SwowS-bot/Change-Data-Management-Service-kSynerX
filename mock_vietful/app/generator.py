import random
from typing import List, Dict, Any
from faker import Faker

fake = Faker(['vi_VN', 'en_US'])

CATEGORIES = [
    "Laptop", "Bàn phím cơ", "Chuột không dây", "Tai nghe chống ồn", "Màn hình 4K",
    "Ổ cứng SSD", "Cáp sạc Type-C", "Đồng hồ thông minh", "Loa Bluetooth", "Webcam HD"
]

ASSET_TYPES = ["Single", "Bundle", "MultipleBarcodes"]

def generate_product(product_id: int, sku: str = None) -> Dict[str, Any]:
    """
    Generates a single realistic product conforming to Vietful Product API schema.
    """
    category = random.choice(CATEGORIES)
    product_name = f"{category} {fake.company()} {fake.word().capitalize()}"
    sku_val = sku or f"VF-{category[:3].upper()}-{product_id:04d}"
    partner_sku = f"PTR-{sku_val}"
    
    return {
        "productId": product_id,
        "sku": sku_val,
        "partnerSKU": partner_sku,
        "productName": product_name,
        "assetType": random.choice(ASSET_TYPES),
        "price": round(random.uniform(50000, 25000000), 2),  # VND price range
        "stockQuantity": random.randint(0, 500),
        "barcodes": [fake.ean13() for _ in range(random.randint(1, 2))],
        "attributes": {
            "brand": fake.company(),
            "color": fake.color_name(),
            "weightGrams": random.randint(100, 3000),
            "origin": random.choice(["Vietnam", "Japan", "Korea", "USA", "China"]),
        },
        "conditionType": "New"
    }

def generate_initial_catalog(count: int = 50) -> List[Dict[str, Any]]:
    """
    Generates the initial product catalog for the mock inventory.
    """
    return [generate_product(product_id=i + 1) for i in range(count)]

def mutate_catalog(catalog: List[Dict[str, Any]], mutate_ratio: float = 0.2) -> Dict[str, Any]:
    """
    Simulates real-world inventory changes:
    - Randomly updates prices (e.g. flash sales / price hikes)
    - Randomly updates stock quantities (sales / replenishment)
    - Occasionally adds a brand-new product
    Returns summary of mutations applied.
    """
    mutated_items = []
    num_to_mutate = max(1, int(len(catalog) * mutate_ratio))
    
    # Pick random products to mutate
    targets = random.sample(catalog, min(num_to_mutate, len(catalog)))
    for item in targets:
        change_type = random.choice(["price", "stock", "both"])
        old_price = item["price"]
        old_stock = item["stockQuantity"]
        
        if change_type in ["price", "both"]:
            # Adjust price by +/- 5% to 20%
            factor = random.uniform(0.85, 1.20)
            item["price"] = round(item["price"] * factor, 2)
            
        if change_type in ["stock", "both"]:
            # Adjust stock
            item["stockQuantity"] = max(0, item["stockQuantity"] + random.randint(-20, 50))
            
        mutated_items.append({
            "sku": item["sku"],
            "old": {"price": old_price, "stockQuantity": old_stock},
            "new": {"price": item["price"], "stockQuantity": item["stockQuantity"]}
        })

    # 30% chance to insert a brand-new product to catalog
    new_product = None
    if random.random() < 0.3:
        new_id = len(catalog) + 1
        new_product = generate_product(product_id=new_id)
        catalog.append(new_product)

    return {
        "mutated_count": len(mutated_items),
        "mutated_items": mutated_items,
        "new_product": new_product["sku"] if new_product else None,
        "total_catalog_size": len(catalog)
    }
