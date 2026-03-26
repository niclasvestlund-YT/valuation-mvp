"""Tests for the crawler service."""

import json
from pathlib import Path

from backend.app.services.crawler_service import SeedProduct, load_seed_products


SEED_FILE = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "seed_products.json"


class TestSeedProducts:
    def test_seed_file_exists(self):
        assert SEED_FILE.exists()

    def test_seed_file_valid_json(self):
        data = json.loads(SEED_FILE.read_text())
        assert isinstance(data, list)
        assert len(data) >= 50

    def test_all_products_have_required_fields(self):
        data = json.loads(SEED_FILE.read_text())
        for item in data:
            assert "brand" in item, f"Missing brand: {item}"
            assert "model" in item, f"Missing model: {item}"
            assert "priority" in item, f"Missing priority: {item}"
            assert item["priority"] in {1, 2, 3}, f"Invalid priority: {item}"

    def test_priority_distribution(self):
        data = json.loads(SEED_FILE.read_text())
        p1 = [d for d in data if d["priority"] == 1]
        p2 = [d for d in data if d["priority"] == 2]
        p3 = [d for d in data if d["priority"] == 3]
        assert len(p1) >= 15, f"Too few priority 1 products: {len(p1)}"
        assert len(p2) >= 20, f"Too few priority 2 products: {len(p2)}"
        assert len(p3) >= 15, f"Too few priority 3 products: {len(p3)}"

    def test_load_seed_products(self):
        products = load_seed_products()
        assert len(products) >= 50
        assert all(isinstance(p, SeedProduct) for p in products)

    def test_load_seed_products_filter_priority(self):
        products = load_seed_products(priorities={1})
        assert all(p.priority == 1 for p in products)
        assert len(products) >= 15

    def test_seed_product_key(self):
        p = SeedProduct(brand="Sony", model="WH-1000XM5", category="headphones", priority=1)
        assert p.product_key == "sony_wh-1000xm5"

    def test_seed_product_search_query(self):
        p = SeedProduct(brand="Apple", model="iPhone 15 Pro", category="smartphone", priority=1)
        assert p.search_query == "Apple iPhone 15 Pro"

    def test_no_duplicate_products(self):
        products = load_seed_products()
        keys = [p.product_key for p in products]
        assert len(keys) == len(set(keys)), f"Duplicate product keys found: {[k for k in keys if keys.count(k) > 1]}"
