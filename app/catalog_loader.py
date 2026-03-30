import json
from functools import lru_cache
from pathlib import Path

from app.schemas import Product


BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> list[Product]:
    with CATALOG_FILE.open("r", encoding="utf-8") as file:
        items = json.load(file)
    return [Product.model_validate(item) for item in items]