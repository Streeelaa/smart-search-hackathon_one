import csv
import json
from pathlib import Path

from app.schemas import EventCreate, ImportResult, Product


BASE_DIR = Path(__file__).resolve().parent.parent

PRODUCT_FIELD_ALIASES = {
    "id": ["id", "item_id", "product_id"],
    "sku": ["sku", "vendor_code", "ste_id", "code"],
    "title": ["title", "name", "product_name"],
    "category": ["category", "group", "section"],
    "description": ["description", "desc", "details"],
    "price": ["price", "cost", "amount"],
    "tags": ["tags", "keywords"],
    "aliases": ["aliases", "synonyms"],
}

EVENT_FIELD_ALIASES = {
    "user_id": ["user_id", "user", "customer_id", "client_id"],
    "event_type": ["event_type", "event", "action", "interaction_type"],
    "item_id": ["item_id", "product_id", "id"],
    "query": ["query", "search_query", "request"],
}

RESERVED_PRODUCT_COLUMNS = {alias for values in PRODUCT_FIELD_ALIASES.values() for alias in values}
RESERVED_EVENT_COLUMNS = {alias for values in EVENT_FIELD_ALIASES.values() for alias in values}


def resolve_import_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = BASE_DIR / raw_path
    return path.resolve()


def import_catalog(path: str, replace_existing: bool = True) -> tuple[list[Product], ImportResult]:
    resolved_path = resolve_import_path(path)
    rows = _load_rows(resolved_path)
    products: list[Product] = []
    errors: list[str] = []

    for index, row in enumerate(rows, start=1):
        try:
            products.append(_product_from_row(row, index))
        except Exception as exc:
            errors.append(f"row {index}: {exc}")

    result = ImportResult(
        kind="catalog",
        path=str(resolved_path),
        imported_count=len(products),
        skipped_count=len(errors),
        replace_existing=replace_existing,
        errors=errors[:20],
        notes=["Поддерживаются JSON list и CSV.", "Неизвестные колонки в CSV сохраняются в attributes."],
    )
    return products, result


def import_events(path: str, replace_existing: bool = True) -> tuple[list[EventCreate], ImportResult]:
    resolved_path = resolve_import_path(path)
    rows = _load_rows(resolved_path)
    events: list[EventCreate] = []
    errors: list[str] = []

    for index, row in enumerate(rows, start=1):
        try:
            events.append(_event_from_row(row, index))
        except Exception as exc:
            errors.append(f"row {index}: {exc}")

    result = ImportResult(
        kind="events",
        path=str(resolved_path),
        imported_count=len(events),
        skipped_count=len(errors),
        replace_existing=replace_existing,
        errors=errors[:20],
        notes=["Для событий обязательны user_id и event_type.", "event_type: search, click, favorite, purchase."],
    )
    return events, result


def _load_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, list):
            raise ValueError("JSON file must contain a list of objects")
        return [dict(item) for item in payload]

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return [dict(row) for row in csv.DictReader(file)]

    raise ValueError("Supported file types: .json, .csv")


def _product_from_row(row: dict, index: int) -> Product:
    normalized = _normalize_row(row)
    mapped = {field: _pick_value(normalized, aliases) for field, aliases in PRODUCT_FIELD_ALIASES.items()}

    if mapped["id"] in (None, ""):
        mapped["id"] = index
    if mapped["sku"] in (None, ""):
        mapped["sku"] = f"IMPORTED-{index:05d}"
    if mapped["title"] in (None, ""):
        raise ValueError("missing title/name column")
    if mapped["category"] in (None, ""):
        mapped["category"] = "без категории"
    if mapped["description"] in (None, ""):
        mapped["description"] = ""
    if mapped["price"] in (None, ""):
        mapped["price"] = 0

    attributes = {}
    for key, value in normalized.items():
        if key not in RESERVED_PRODUCT_COLUMNS and value not in (None, ""):
            attributes[key] = str(value)

    return Product(
        id=int(mapped["id"]),
        sku=str(mapped["sku"]),
        title=str(mapped["title"]),
        category=str(mapped["category"]),
        description=str(mapped["description"]),
        price=float(mapped["price"]),
        tags=_parse_list_value(mapped["tags"]),
        aliases=_parse_list_value(mapped["aliases"]),
        attributes=attributes,
    )


def _event_from_row(row: dict, index: int) -> EventCreate:
    normalized = _normalize_row(row)
    mapped = {field: _pick_value(normalized, aliases) for field, aliases in EVENT_FIELD_ALIASES.items()}
    if mapped["user_id"] in (None, ""):
        raise ValueError("missing user_id column")
    if mapped["event_type"] in (None, ""):
        raise ValueError("missing event_type column")

    metadata = {}
    for key, value in normalized.items():
        if key not in RESERVED_EVENT_COLUMNS and value not in (None, ""):
            metadata[key] = str(value)

    item_id = mapped["item_id"]
    return EventCreate(
        user_id=str(mapped["user_id"]),
        event_type=str(mapped["event_type"]),
        item_id=int(item_id) if item_id not in (None, "") else None,
        query=str(mapped["query"]) if mapped["query"] not in (None, "") else None,
        metadata=metadata,
    )


def _normalize_row(row: dict) -> dict[str, object]:
    return {str(key).strip().lower(): value for key, value in row.items()}


def _pick_value(row: dict[str, object], aliases: list[str]) -> object | None:
    for alias in aliases:
        if alias in row:
            return row[alias]
    return None


def _parse_list_value(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
    if ";" in text:
        parts = text.split(";")
    else:
        parts = text.split(",")
    return [part.strip() for part in parts if part.strip()]