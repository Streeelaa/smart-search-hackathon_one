"""SQLite-backed repository for 542K real products with FTS5."""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache

from app.data_loader import get_db_connection, load_real_data
from app.schemas import Event, EventCreate, Product, UserProfile

logger = logging.getLogger(__name__)


class RealDataRepository:
    """Repository backed by SQLite + FTS5 for real hackathon data."""

    def __init__(self) -> None:
        load_real_data()
        self._conn = get_db_connection()

    # ---- Products ----

    @property
    def products(self) -> list[Product]:
        """Backward compat — returns first 100 products."""
        return self.list_products(limit=100)

    def list_products(self, category: str | None = None, limit: int = 20) -> list[Product]:
        if category:
            rows = self._conn.execute(
                "SELECT * FROM products WHERE category = ? LIMIT ?",
                (category.strip(), limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM products LIMIT ?", (limit,)
            ).fetchall()
        return [self._product_from_row(r) for r in rows]

    def get_product(self, item_id: int) -> Product | None:
        row = self._conn.execute(
            "SELECT * FROM products WHERE id = ?", (item_id,)
        ).fetchone()
        return self._product_from_row(row) if row else None

    def get_products_by_ids(self, ids: list[int]) -> dict[int, Product]:
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        rows = self._conn.execute(
            f"SELECT * FROM products WHERE id IN ({placeholders})", ids
        ).fetchall()
        return {r["id"]: self._product_from_row(r) for r in rows}

    def search_fts5(
        self, query_terms: list[str], limit: int = 200
    ) -> list[tuple[Product, float]]:
        """FTS5 BM25 search. Returns (product, score) pairs sorted by relevance."""
        if not query_terms:
            return []

        fts_parts: list[str] = []
        for term in query_terms:
            term = term.strip().replace('"', "").replace("'", "")
            if not term:
                continue
            # Sanitize: only allow alphanumeric + Cyrillic
            clean = "".join(ch for ch in term if ch.isalnum() or ch in " -")
            if not clean:
                continue
            if " " in clean:
                fts_parts.append(f'"{clean}"')
            else:
                fts_parts.append(f"{clean}*")

        if not fts_parts:
            return []

        fts_query = " OR ".join(fts_parts)
        try:
            rows = self._conn.execute(
                """
                SELECT p.id, p.title, p.category, p.attributes,
                       -bm25(products_fts, 10.0, 5.0, 1.0) AS score
                FROM products_fts fts
                JOIN products p ON p.id = fts.rowid
                WHERE products_fts MATCH ?
                ORDER BY score DESC
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            # Fallback: simpler OR query without prefix
            simple_parts = []
            for term in query_terms:
                clean = "".join(ch for ch in term if ch.isalnum() or ch in " -").strip()
                if clean:
                    simple_parts.append(f'"{clean}"')
            if not simple_parts:
                return []
            try:
                rows = self._conn.execute(
                    """
                    SELECT p.id, p.title, p.category, p.attributes,
                           -bm25(products_fts, 10.0, 5.0, 1.0) AS score
                    FROM products_fts fts
                    JOIN products p ON p.id = fts.rowid
                    WHERE products_fts MATCH ?
                    ORDER BY score DESC
                    LIMIT ?
                    """,
                    (" OR ".join(simple_parts), limit),
                ).fetchall()
            except sqlite3.OperationalError:
                return []

        return [(self._product_from_row(r), r["score"]) for r in rows]

    # ---- User profiles ----

    def get_user_profile(self, user_id: str) -> UserProfile:
        row = self._conn.execute(
            "SELECT * FROM user_profiles_cache WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return UserProfile(user_id=user_id)
        cat_affinity = json.loads(row["category_affinity"]) if row["category_affinity"] else {}
        return UserProfile(
            user_id=user_id,
            total_events=row["total_contracts"],
            category_affinity=cat_affinity,
            average_price=row["avg_price"],
        )

    def list_users(self, limit: int = 50) -> list[dict]:
        """List top users by contract count for demo UI."""
        rows = self._conn.execute(
            """
            SELECT user_id, user_name, user_region, total_contracts,
                   CAST(avg_price AS INTEGER) AS avg_price, category_affinity
            FROM user_profiles_cache
            ORDER BY total_contracts DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            ca = json.loads(r["category_affinity"]) if r["category_affinity"] else {}
            top_cat = next(iter(ca), "")
            result.append({
                "user_id": r["user_id"],
                "user_name": r["user_name"],
                "user_region": r["user_region"],
                "total_contracts": r["total_contracts"],
                "avg_price": r["avg_price"],
                "top_category": top_cat,
            })
        return result

    # ---- Events ----

    def add_event(self, payload: EventCreate) -> Event:
        cursor = self._conn.execute(
            "INSERT INTO events (user_id, event_type, item_id, query, metadata) VALUES (?, ?, ?, ?, ?)",
            (
                payload.user_id,
                payload.event_type,
                payload.item_id,
                payload.query,
                json.dumps(payload.metadata, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return Event(
            event_id=cursor.lastrowid,
            timestamp=datetime.now(timezone.utc),
            **payload.model_dump(),
        )

    def list_user_events(self, user_id: str) -> list[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE user_id = ? ORDER BY timestamp DESC LIMIT 100",
            (user_id,),
        ).fetchall()
        events = []
        for r in rows:
            try:
                ts = datetime.fromisoformat(r["timestamp"])
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
            events.append(
                Event(
                    event_id=r["event_id"],
                    user_id=r["user_id"],
                    event_type=r["event_type"],
                    item_id=r["item_id"],
                    query=r["query"],
                    metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                    timestamp=ts,
                )
            )
        return events

    # ---- Counts ----

    def count_products(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM products").fetchone()
        return row[0] if row else 0

    def count_events(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return row[0] if row else 0

    def count_profiles(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM user_profiles_cache").fetchone()
        return row[0] if row else 0

    def count_categories(self) -> int:
        row = self._conn.execute("SELECT COUNT(DISTINCT category) FROM products").fetchone()
        return row[0] if row else 0

    def backend_name(self) -> str:
        return "sqlite-fts5"

    # ---- Vocabulary for typo correction ----

    @lru_cache(maxsize=1)
    def build_vocabulary(self) -> set[str]:
        """Build vocabulary set from product titles + categories for typo correction.
        
        Uses a separate connection to avoid blocking the main one.
        """
        from app.text_processing import normalize_token
        conn = get_db_connection()  # separate connection for thread safety
        vocab: set[str] = set()
        # Fetch distinct category names (fast — only 6506 rows)
        for row in conn.execute("SELECT DISTINCT category FROM products"):
            cat = row["category"]
            for word in cat.lower().split():
                clean = "".join(ch for ch in word if ch.isalnum())
                if clean and len(clean) >= 2:
                    vocab.add(clean)
                    norm = normalize_token(clean)
                    if norm and norm != clean:
                        vocab.add(norm)
        # Fetch sample of titles (50K is enough for vocabulary)
        for row in conn.execute("SELECT title FROM products ORDER BY RANDOM() LIMIT 50000"):
            title = row["title"]
            for word in title.lower().split():
                clean = "".join(ch for ch in word if ch.isalnum())
                if clean and len(clean) >= 2:
                    vocab.add(clean)
                    norm = normalize_token(clean)
                    if norm and norm != clean:
                        vocab.add(norm)
        conn.close()
        logger.info("Built vocabulary: %d terms", len(vocab))
        return vocab

    # ---- Category facets & suggestions ----

    def get_all_categories(self, limit: int = 200) -> list[tuple[str, int]]:
        """Return (category, product_count) sorted by count descending."""
        rows = self._conn.execute(
            "SELECT category, COUNT(*) as cnt FROM products GROUP BY category ORDER BY cnt DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(r["category"], r["cnt"]) for r in rows]

    def search_categories(self, query: str, limit: int = 20) -> list[tuple[str, int]]:
        """Search categories matching query substring."""
        rows = self._conn.execute(
            "SELECT category, COUNT(*) as cnt FROM products WHERE category LIKE ? GROUP BY category ORDER BY cnt DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [(r["category"], r["cnt"]) for r in rows]

    def suggest_products(self, prefix: str, limit: int = 8) -> list[dict]:
        """Fast autocomplete: find products + categories matching prefix."""
        if not prefix or len(prefix) < 2:
            return []
        results = []
        # 1) Category suggestions
        cat_rows = self._conn.execute(
            "SELECT category, COUNT(*) as cnt FROM products WHERE category LIKE ? GROUP BY category ORDER BY cnt DESC LIMIT 4",
            (f"%{prefix}%",),
        ).fetchall()
        for r in cat_rows:
            results.append({"type": "category", "title": r["category"], "count": r["cnt"]})
        # 2) Product title suggestions (fast LIKE on title)
        prod_rows = self._conn.execute(
            "SELECT id, title, category FROM products WHERE title LIKE ? LIMIT ?",
            (f"%{prefix}%", limit - len(results)),
        ).fetchall()
        for r in prod_rows:
            results.append({"type": "product", "title": r["title"], "category": r["category"], "id": r["id"]})
        return results[:limit]

    def get_product_contract_count(self, product_id: int) -> int:
        """Get number of contracts for a product (popularity)."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM contracts WHERE product_id = ?", (product_id,)
        ).fetchone()
        return row[0] if row else 0

    def get_product_avg_price(self, product_id: int) -> float | None:
        """Get average contract price for a product."""
        row = self._conn.execute(
            "SELECT AVG(price) FROM contracts WHERE product_id = ?", (product_id,)
        ).fetchone()
        return row[0] if row and row[0] else None

    def get_products_popularity(self, product_ids: list[int]) -> dict[int, int]:
        """Get contract counts for multiple products at once."""
        if not product_ids:
            return {}
        placeholders = ",".join("?" * len(product_ids))
        rows = self._conn.execute(
            f"SELECT product_id, COUNT(*) as cnt FROM contracts WHERE product_id IN ({placeholders}) GROUP BY product_id",
            product_ids,
        ).fetchall()
        return {r["product_id"]: r["cnt"] for r in rows}

    def get_products_prices(self, product_ids: list[int]) -> dict[int, float]:
        """Get average prices for multiple products at once."""
        if not product_ids:
            return {}
        placeholders = ",".join("?" * len(product_ids))
        rows = self._conn.execute(
            f"SELECT product_id, AVG(price) as avg_price FROM contracts WHERE product_id IN ({placeholders}) GROUP BY product_id",
            product_ids,
        ).fetchall()
        return {r["product_id"]: r["avg_price"] for r in rows}

    # ---- Backward compat stubs ----

    def replace_products(self, products: list[Product]) -> None:
        pass  # noop for real data

    def replace_events(self, payloads: list[EventCreate]) -> None:
        self._conn.execute("DELETE FROM events")
        self._conn.commit()
        for p in payloads:
            self.add_event(p)

    def append_events(self, payloads: list[EventCreate]) -> None:
        for p in payloads:
            self.add_event(p)

    def reset_demo_state(self) -> None:
        self._conn.execute("DELETE FROM events")
        self._conn.commit()

    # ---- Internal ----

    def _product_from_row(self, row) -> Product:
        attrs_raw = row["attributes"] if row["attributes"] else ""
        return Product(
            id=row["id"],
            title=row["title"],
            category=row["category"],
            attributes={"raw": attrs_raw} if attrs_raw else {},
        )


repository = RealDataRepository()
