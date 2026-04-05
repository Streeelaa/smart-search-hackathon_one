"""Category-level semantic search using sentence-transformers.

Encodes all ~6500 category names into dense vectors. Given a user query,
finds the most semantically similar categories and returns product IDs
from those categories — enabling "meaning-based" search beyond keyword matching.

Example: query "канцтовары" -> finds categories "Ручки", "Скрепки", "Папки"
even though the word "канцтовары" doesn't appear in product titles.
"""
from __future__ import annotations

import logging
import os
import pickle
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data"
EMBEDDINGS_CACHE = CACHE_DIR / "category_embeddings.pkl"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


@dataclass
class SemanticStatus:
    ready: bool
    backend: str
    model_name: str
    indexed_products: int
    categories_indexed: int = 0
    last_error: str | None = None


class SemanticSearchEngine:
    """Category-level semantic search using sentence-transformers."""

    def __init__(self) -> None:
        self.model_name = MODEL_NAME
        self.backend = "sentence-transformers"
        self.last_error: str | None = None
        self._model = None
        self._model_load_attempted = False
        self._category_names: list[str] = []
        self._category_embeddings: np.ndarray | None = None
        self._fallback_vectorizer: TfidfVectorizer | None = None
        self._fallback_matrix = None
        self._ready = False

    def _load_model(self):
        """Lazy-load the sentence-transformer model."""
        if self._model is not None or self._model_load_attempted:
            return
        self._model_load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading sentence-transformer model: %s", MODEL_NAME)
            t0 = time.time()
            self._model = SentenceTransformer(MODEL_NAME, local_files_only=True)
            logger.info("Model loaded in %.1fs", time.time() - t0)
        except Exception as e:
            self.last_error = str(e)
            logger.error("Failed to load model: %s", e)

    def build_index(self) -> None:
        """Build category embeddings index from all categories in DB."""
        # Try loading from cache first
        if self._load_from_cache():
            self._build_fallback_index(self._category_names)
            self._ready = True
            # Model loaded lazily on first query — no need to pre-load here
            return

        self._load_model()

        from app.repository import repository
        logger.info("Building enriched category embeddings index...")
        t0 = time.time()

        # Get all categories with product counts
        categories = repository.get_all_categories(limit=10000)
        self._category_names = [name for name, _count in categories]

        if not self._category_names:
            self.last_error = "No categories found"
            return

        # Enrich category names with sample product titles for better embeddings
        enriched_texts = self._enrich_categories(self._category_names)
        self._build_fallback_index(enriched_texts)

        if self._model is not None:
            # Encode enriched category descriptions in batches
            self._category_embeddings = self._model.encode(
                enriched_texts,
                batch_size=128,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            self.backend = "sentence-transformers"
            self._save_to_cache()
        else:
            self.backend = "tfidf-char-ngrams"
            logger.warning("Sentence-transformer model unavailable, using TF-IDF fallback")

        elapsed = time.time() - t0
        logger.info(
            "Indexed %d categories in %.1fs", len(self._category_names), elapsed
        )
        self._ready = True

    def _enrich_categories(self, category_names: list[str]) -> list[str]:
        """Enrich category names with sample product titles for richer embeddings."""
        from app.db import SessionLocal
        from sqlalchemy import text as sql_text

        enriched: list[str] = []
        try:
            with SessionLocal() as session:
                # One query: get 3 sample titles per category using GROUP_CONCAT
                rows = session.execute(
                    sql_text(
                        "SELECT category, GROUP_CONCAT(title, ', ') as samples FROM "
                        "(SELECT category, SUBSTR(title, 1, 50) as title, "
                        "ROW_NUMBER() OVER (PARTITION BY category ORDER BY ROWID) as rn "
                        "FROM products) WHERE rn <= 3 GROUP BY category"
                    )
                ).fetchall()
                cat_samples = {r[0]: r[1] for r in rows}

            for cat_name in category_names:
                samples = cat_samples.get(cat_name)
                if samples:
                    enriched.append(f"{cat_name}: {samples}")
                else:
                    enriched.append(cat_name)
        except Exception as e:
            logger.warning("Failed to enrich categories: %s, using raw names", e)
            enriched = list(category_names)

        return enriched

    def _build_fallback_index(self, texts: list[str]) -> None:
        """Build a lightweight local semantic index that works without downloads."""
        if not texts:
            self._fallback_vectorizer = None
            self._fallback_matrix = None
            return
        self._fallback_vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            lowercase=True,
        )
        self._fallback_matrix = self._fallback_vectorizer.fit_transform(texts)

    # Meta-category mapping: abstract terms → known categories in the DB
    _META_CATEGORIES: dict[str, list[str]] = {
        "канцтовары": ["Ручки канцелярские", "Карандаши чернографитные", "Карандаши цветные", "Папки пластиковые", "Папки картонные", "Маркеры", "Стержни для ручек канцелярских", "Клеи канцелярские", "Ластики", "Точилки канцелярские", "Линейки", "Ножницы канцелярские", "Скрепки канцелярские", "Степлеры", "Дыроколы", "Корректоры жидкие"],
        "канцелярия": ["Ручки канцелярские", "Карандаши чернографитные", "Папки пластиковые", "Маркеры", "Клеи канцелярские", "Ластики"],
        "медикаменты": ["Прочие лекарственные средства", "ПРОТИВОМИКРОБНЫЕ ПРЕПАРАТЫ ДЛЯ СИСТЕМНОГО ИСПОЛЬЗОВАНИЯ,J01", "Средства дезинфицирующие", "Медицинские шприцы", "Вспомогательные материалы для стоматологии"],
        "лекарства": ["Прочие лекарственные средства", "ПРОТИВОМИКРОБНЫЕ ПРЕПАРАТЫ ДЛЯ СИСТЕМНОГО ИСПОЛЬЗОВАНИЯ,J01", "Обеспечение лекарственными препаратами"],
        "стройматериалы": ["Шурупы металлические", "Эмали", "Замки дверные", "Детали трубопроводов из черных металлов", "Краны общепромышленного назначения", "Смесители водоразборные", "Комплектующие для кабельных изделий"],
        "бытовая химия": ["Средства моющие для поверхностей в помещениях", "Средства моющие для стекол и зеркал", "Средства моющие для туалетов и ванных комнат", "Средства дезинфицирующие", "Мыло туалетное жидкое", "Мыло хозяйственное твердое"],
        "автозапчасти": ["Запасные части для легковых автомобилей", "Масла моторные"],
        "продукты питания": ["Масло подсолнечное рафинированное", "Сахар белый кристаллический", "Молоко питьевое пастеризованное", "Крупа гречневая"],
        "еда": ["Масло подсолнечное рафинированное", "Сахар белый кристаллический", "Молоко питьевое пастеризованное"],
        "мебель": ["Столы рабочие офисные", "Стулья для посетителей", "Стеллажи металлические", "Шкафы для одежды"],
        "хозтовары": ["Инвентарь уборочный", "Мешки полимерные", "Салфетки, насадки для уборки, полотна технические, ветошь", "Полотенца бумажные"],
        "уборка": ["Инвентарь уборочный", "Средства моющие для поверхностей в помещениях", "Салфетки, насадки для уборки, полотна технические, ветошь"],
        "оргтехника": ["Расходные материалы и комплектующие для лазерных принтеров и МФУ", "Комплектующие и запасные части для устройств ввода и вывода информации"],
        "спецодежда": ["Одежда специальная для защиты от общих производственных загрязнений и механических воздействий", "Каска строительная"],
    }

    def find_similar_categories(
        self, query: str, top_k: int = 5, threshold: float = 0.50
    ) -> list[tuple[str, float]]:
        """Find categories semantically similar to query.

        Returns list of (category_name, similarity_score) pairs.
        First checks meta-category mapping for known abstract terms,
        then falls back to embedding similarity.
        """
        # Check meta-categories first — exact match on abstract terms
        query_lower = query.lower().strip()
        if query_lower in self._META_CATEGORIES:
            return [(cat, 0.95) for cat in self._META_CATEGORIES[query_lower][:top_k]]

        if not self._ready:
            return []

        similarities = None
        active_threshold = threshold

        if self._category_embeddings is not None:
            self._load_model()
            if self._model is not None:
                # Encode query
                query_vec = self._model.encode(
                    [query], normalize_embeddings=True
                )[0]

                # Cosine similarity (embeddings are already normalized)
                similarities = self._category_embeddings @ query_vec
                self.backend = "sentence-transformers"

        if similarities is None and self._fallback_vectorizer is not None and self._fallback_matrix is not None:
            query_vec = self._fallback_vectorizer.transform([query])
            similarities = (self._fallback_matrix @ query_vec.T).toarray().ravel()
            active_threshold = max(0.12, threshold * 0.4)
            self.backend = "tfidf-char-ngrams"

        if similarities is None:
            return []

        # Get top-k above threshold
        top_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score >= active_threshold:
                results.append((self._category_names[idx], score))

        return results

    @lru_cache(maxsize=256)
    def find_similar_categories_cached(
        self, query: str, top_k: int = 5
    ) -> tuple[tuple[str, float], ...]:
        """Cached version for search pipeline."""
        return tuple(self.find_similar_categories(query, top_k=top_k))

    def search(self, query: str, limit: int = 10) -> list[tuple[int, float]]:
        """Semantic search: find products in semantically similar categories."""
        if not self._ready:
            return []

        similar_cats = self.find_similar_categories(query, top_k=5)
        if not similar_cats:
            return []

        from app.repository import repository
        results = []
        for cat_name, cat_score in similar_cats:
            products = repository.list_products(category=cat_name, limit=limit)
            for product in products:
                results.append((product.id, cat_score))

        return results[:limit]

    def status(self) -> SemanticStatus:
        from app.repository import repository
        return SemanticStatus(
            ready=self._ready,
            backend=self.backend,
            model_name=self.model_name,
            indexed_products=repository.count_products(),
            categories_indexed=len(self._category_names),
            last_error=self.last_error,
        )

    def reset(self) -> None:
        self.last_error = None
        self.backend = "sentence-transformers"
        self._model = None
        self._model_load_attempted = False
        self._category_names = []
        self._category_embeddings = None
        self._fallback_vectorizer = None
        self._fallback_matrix = None
        self._ready = False
        if EMBEDDINGS_CACHE.exists():
            try:
                EMBEDDINGS_CACHE.unlink()
            except PermissionError:
                logger.warning("Could not remove embeddings cache because it is in use")

    def _save_to_cache(self) -> None:
        """Save embeddings to disk cache."""
        try:
            data = {
                "categories": self._category_names,
                "embeddings": self._category_embeddings,
                "model": MODEL_NAME,
            }
            with open(EMBEDDINGS_CACHE, "wb") as f:
                pickle.dump(data, f)
            logger.info("Saved category embeddings cache to %s", EMBEDDINGS_CACHE)
        except Exception as e:
            logger.warning("Failed to save embeddings cache: %s", e)

    def _load_from_cache(self) -> bool:
        """Load embeddings from disk cache."""
        if not EMBEDDINGS_CACHE.exists():
            return False
        try:
            with open(EMBEDDINGS_CACHE, "rb") as f:
                data = pickle.load(f)
            if data.get("model") != MODEL_NAME:
                return False
            self._category_names = data["categories"]
            self._category_embeddings = data["embeddings"]
            self.backend = "sentence-transformers"
            logger.info(
                "Loaded %d category embeddings from cache",
                len(self._category_names),
            )
            return True
        except Exception as e:
            logger.warning("Failed to load embeddings cache: %s", e)
            return False


semantic_engine = SemanticSearchEngine()
