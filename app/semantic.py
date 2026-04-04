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
        self._category_names: list[str] = []
        self._category_embeddings: np.ndarray | None = None
        self._ready = False

    def _load_model(self):
        """Lazy-load the sentence-transformer model."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading sentence-transformer model: %s", MODEL_NAME)
            t0 = time.time()
            self._model = SentenceTransformer(MODEL_NAME)
            logger.info("Model loaded in %.1fs", time.time() - t0)
        except Exception as e:
            self.last_error = str(e)
            logger.error("Failed to load model: %s", e)

    def build_index(self) -> None:
        """Build category embeddings index from all categories in DB."""
        # Try loading from cache first
        if self._load_from_cache():
            self._ready = True
            # Pre-load model so first query isn't slow
            self._load_model()
            return

        self._load_model()
        if self._model is None:
            return

        from app.repository import repository
        logger.info("Building category embeddings index...")
        t0 = time.time()

        # Get all categories with product counts
        categories = repository.get_all_categories(limit=10000)
        self._category_names = [name for name, _count in categories]

        if not self._category_names:
            self.last_error = "No categories found"
            return

        # Encode all category names in batches
        self._category_embeddings = self._model.encode(
            self._category_names,
            batch_size=128,
            show_progress_bar=False,
            normalize_embeddings=True,
        )

        elapsed = time.time() - t0
        logger.info(
            "Indexed %d categories in %.1fs", len(self._category_names), elapsed
        )

        # Save to cache
        self._save_to_cache()
        self._ready = True

    def find_similar_categories(
        self, query: str, top_k: int = 5, threshold: float = 0.50
    ) -> list[tuple[str, float]]:
        """Find categories semantically similar to query.

        Returns list of (category_name, similarity_score) pairs.
        """
        if not self._ready or self._category_embeddings is None:
            return []

        self._load_model()
        if self._model is None:
            return []

        # Encode query
        query_vec = self._model.encode(
            [query], normalize_embeddings=True
        )[0]

        # Cosine similarity (embeddings are already normalized)
        similarities = self._category_embeddings @ query_vec

        # Get top-k above threshold
        top_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score >= threshold:
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
        self._category_names = []
        self._category_embeddings = None
        self._ready = False
        if EMBEDDINGS_CACHE.exists():
            EMBEDDINGS_CACHE.unlink()

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
            logger.info(
                "Loaded %d category embeddings from cache",
                len(self._category_names),
            )
            return True
        except Exception as e:
            logger.warning("Failed to load embeddings cache: %s", e)
            return False


semantic_engine = SemanticSearchEngine()
