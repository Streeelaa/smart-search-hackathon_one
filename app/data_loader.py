"""Load real hackathon CSV data (СТЕ + Контракты) into SQLite with FTS5 index."""
from __future__ import annotations

import csv
import logging
import pathlib
import sqlite3
import time
from typing import Iterator

from app.text_processing import normalize_query

logger = logging.getLogger(__name__)

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "smart_search.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT '',
    attributes  TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
    title,
    category,
    attributes,
    content='products',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS products_ai AFTER INSERT ON products BEGIN
    INSERT INTO products_fts(rowid, title, category, attributes)
    VALUES (new.id, new.title, new.category, new.attributes);
END;

CREATE TRIGGER IF NOT EXISTS products_ad AFTER DELETE ON products BEGIN
    INSERT INTO products_fts(products_fts, rowid, title, category, attributes)
    VALUES ('delete', old.id, old.title, old.category, old.attributes);
END;

CREATE TRIGGER IF NOT EXISTS products_au AFTER UPDATE ON products BEGIN
    INSERT INTO products_fts(products_fts, rowid, title, category, attributes)
    VALUES ('delete', old.id, old.title, old.category, old.attributes);
    INSERT INTO products_fts(rowid, title, category, attributes)
    VALUES (new.id, new.title, new.category, new.attributes);
END;

CREATE TABLE IF NOT EXISTS contracts (
    contract_id     INTEGER PRIMARY KEY,
    product_id      INTEGER NOT NULL,
    contract_name   TEXT NOT NULL DEFAULT '',
    contract_date   TEXT NOT NULL DEFAULT '',
    price           REAL NOT NULL DEFAULT 0,
    customer_inn    TEXT NOT NULL DEFAULT '',
    customer_name   TEXT NOT NULL DEFAULT '',
    customer_region TEXT NOT NULL DEFAULT '',
    supplier_inn    TEXT NOT NULL DEFAULT '',
    supplier_name   TEXT NOT NULL DEFAULT '',
    supplier_region TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_contracts_customer ON contracts(customer_inn);
CREATE INDEX IF NOT EXISTS idx_contracts_product ON contracts(product_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

CREATE TABLE IF NOT EXISTS user_profiles_cache (
    user_id             TEXT PRIMARY KEY,
    user_name           TEXT NOT NULL DEFAULT '',
    user_region         TEXT NOT NULL DEFAULT '',
    total_contracts     INTEGER NOT NULL DEFAULT 0,
    avg_price           REAL NOT NULL DEFAULT 0,
    category_affinity   TEXT NOT NULL DEFAULT '{}',
    recent_product_ids  TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    item_id     INTEGER,
    query       TEXT,
    metadata    TEXT NOT NULL DEFAULT '{}',
    timestamp   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
"""


# ---------------------------------------------------------------------------
# CSV Iterators
# ---------------------------------------------------------------------------

def _iter_ste_rows(path: pathlib.Path) -> Iterator[tuple[int, str, str, str]]:
    """Yield (id, title, category, attrs_text) from СТЕ CSV."""
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if len(row) < 4:
                continue
            raw_id = row[0].strip().lstrip("\ufeff")
            try:
                ste_id = int(raw_id)
            except ValueError:
                continue
            title = row[1].strip()
            category = row[2].strip()
            # Parse attrs: "key:val;key:val" → "key val key val" for FTS
            attrs_raw = row[3].strip()
            attrs_text = " ".join(
                part.split(":")[1].strip() if ":" in part else part.strip()
                for part in attrs_raw.split(";")
                if part.strip()
            )
            yield ste_id, title, category, attrs_text


def _iter_contract_rows(path: pathlib.Path) -> Iterator[tuple]:
    """Yield contract tuples from Контракты CSV."""
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if len(row) < 11:
                continue
            name = row[0].strip().lstrip("\ufeff").lstrip("\t").strip('"')
            try:
                contract_id = int(row[1].strip())
                ste_id = int(row[2].strip())
            except ValueError:
                continue
            date = row[3].strip()[:10]
            try:
                price = float(row[4].strip())
            except ValueError:
                price = 0.0
            yield (
                contract_id, ste_id, name, date, price,
                row[5].strip(), row[6].strip(), row[7].strip(),  # customer
                row[8].strip(), row[9].strip(), row[10].strip(),  # supplier
            )


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

def load_real_data(
    db_path: pathlib.Path = DB_PATH,
    ste_csv: pathlib.Path | None = None,
    contracts_csv: pathlib.Path | None = None,
    batch_size: int = 10_000,
) -> dict[str, int]:
    """Load СТЕ and contracts into SQLite. Returns counts."""
    if ste_csv is None:
        candidates = sorted(DATA_DIR.glob("*СТЕ*.csv"))
        ste_csv = candidates[0] if candidates else None
    if contracts_csv is None:
        candidates = sorted(DATA_DIR.glob("*Контракт*.csv"))
        contracts_csv = candidates[0] if candidates else None

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.executescript(SCHEMA_SQL)

    counts = {"products": 0, "contracts": 0, "profiles": 0}

    # --- Load products ---
    if ste_csv and ste_csv.exists():
        # Check if already loaded
        existing = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if existing > 0:
            logger.info("Products already loaded (%d), skipping.", existing)
            counts["products"] = existing
        else:
            logger.info("Loading products from %s ...", ste_csv.name)
            t0 = time.time()
            batch = []
            for ste_id, title, category, attrs_text in _iter_ste_rows(ste_csv):
                batch.append((ste_id, title, category, attrs_text))
                if len(batch) >= batch_size:
                    conn.executemany(
                        "INSERT OR IGNORE INTO products (id, title, category, attributes) VALUES (?, ?, ?, ?)",
                        batch,
                    )
                    counts["products"] += len(batch)
                    batch.clear()
            if batch:
                conn.executemany(
                    "INSERT OR IGNORE INTO products (id, title, category, attributes) VALUES (?, ?, ?, ?)",
                    batch,
                )
                counts["products"] += len(batch)
            conn.commit()
            logger.info("Loaded %d products in %.1fs", counts["products"], time.time() - t0)

    # --- Load contracts ---
    if contracts_csv and contracts_csv.exists():
        existing = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
        if existing > 0:
            logger.info("Contracts already loaded (%d), skipping.", existing)
            counts["contracts"] = existing
        else:
            logger.info("Loading contracts from %s ...", contracts_csv.name)
            t0 = time.time()
            batch = []
            for row in _iter_contract_rows(contracts_csv):
                batch.append(row)
                if len(batch) >= batch_size:
                    conn.executemany(
                        "INSERT OR IGNORE INTO contracts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        batch,
                    )
                    counts["contracts"] += len(batch)
                    batch.clear()
            if batch:
                conn.executemany(
                    "INSERT OR IGNORE INTO contracts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    batch,
                )
                counts["contracts"] += len(batch)
            conn.commit()
            logger.info("Loaded %d contracts in %.1fs", counts["contracts"], time.time() - t0)

    # --- Build user profiles cache from contracts ---
    existing_profiles = conn.execute("SELECT COUNT(*) FROM user_profiles_cache").fetchone()[0]
    if existing_profiles == 0 and counts["contracts"] > 0:
        logger.info("Building user profiles from contracts...")
        t0 = time.time()
        conn.execute("""
            INSERT OR REPLACE INTO user_profiles_cache (
                user_id, user_name, user_region, total_contracts, avg_price,
                category_affinity, recent_product_ids
            )
            SELECT
                c.customer_inn,
                MAX(c.customer_name),
                MAX(c.customer_region),
                COUNT(*),
                AVG(c.price),
                '{}',
                '[]'
            FROM contracts c
            GROUP BY c.customer_inn
        """)
        conn.commit()
        counts["profiles"] = conn.execute("SELECT COUNT(*) FROM user_profiles_cache").fetchone()[0]

        # Build category affinity per user
        _build_category_affinity(conn)
        logger.info("Built %d user profiles in %.1fs", counts["profiles"], time.time() - t0)
    else:
        counts["profiles"] = existing_profiles

    conn.close()
    return counts


def _build_category_affinity(conn: sqlite3.Connection) -> None:
    """Compute category affinity for each customer from their contract history."""
    import json

    cursor = conn.execute("""
        SELECT c.customer_inn, p.category, COUNT(*) as cnt
        FROM contracts c
        JOIN products p ON p.id = c.product_id
        GROUP BY c.customer_inn, p.category
        ORDER BY c.customer_inn, cnt DESC
    """)

    current_inn = None
    categories: dict[str, int] = {}
    total = 0

    for inn, category, cnt in cursor:
        if inn != current_inn:
            if current_inn is not None and categories:
                # Normalize to 0..1
                affinity = {cat: round(n / total, 4) for cat, n in categories.items()}
                top = dict(sorted(affinity.items(), key=lambda x: -x[1])[:30])
                conn.execute(
                    "UPDATE user_profiles_cache SET category_affinity = ? WHERE user_id = ?",
                    (json.dumps(top, ensure_ascii=False), current_inn),
                )
            current_inn = inn
            categories = {}
            total = 0
        categories[category] = cnt
        total += cnt

    # Last user
    if current_inn and categories:
        affinity = {cat: round(n / total, 4) for cat, n in categories.items()}
        top = dict(sorted(affinity.items(), key=lambda x: -x[1])[:30])
        conn.execute(
            "UPDATE user_profiles_cache SET category_affinity = ? WHERE user_id = ?",
            (json.dumps(top, ensure_ascii=False), current_inn),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Quick helpers
# ---------------------------------------------------------------------------

def get_db_connection(db_path: pathlib.Path = DB_PATH) -> sqlite3.Connection:
    """Get a read-optimized connection."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-32000")
    conn.row_factory = sqlite3.Row
    return conn


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    counts = load_real_data()
    print(f"\nLoaded: {counts}")
