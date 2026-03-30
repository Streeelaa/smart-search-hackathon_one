from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.repository import repository

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = os.getenv("SEMANTIC_MODEL_NAME", "intfloat/multilingual-e5-large")
DEFAULT_BACKEND = os.getenv("SEMANTIC_BACKEND", "auto").lower()
CACHE_DIR = Path(os.getenv("EMBEDDING_CACHE_DIR", Path(__file__).resolve().parent.parent / ".cache"))


@dataclass
class SemanticStatus:
    ready: bool
    backend: str
    model_name: str
    indexed_products: int
    last_error: str | None = None


class SemanticSearchEngine:
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, backend_preference: str = DEFAULT_BACKEND) -> None:
        self.model_name = model_name
        self.backend_preference = backend_preference
        self.backend = "not-initialized"
        self.last_error: str | None = None
        self._model = None
        self._vectorizer: TfidfVectorizer | None = None
        self._product_ids: list[int] = []
        self._semantic_texts: list[str] = []
        self._matrix = None

    def build_index(self) -> None:
        products = repository.products
        product_ids = [product.id for product in products]
        if self._product_ids == product_ids and self._matrix is not None:
            return

        self._product_ids = product_ids
        self._semantic_texts = [self._product_text(product) for product in products]

        if self.backend_preference == "tfidf":
            self.last_error = None
            self._build_tfidf_index()
            return

        try:
            self._build_transformer_index()
        except Exception as exc:  # pragma: no cover
            self.last_error = str(exc)
            self._build_tfidf_index()

    def search(self, query: str, limit: int = 10) -> list[tuple[int, float]]:
        self.build_index()
        if not query.strip() or self._matrix is None:
            return []

        if self.backend == "transformer":
            # E5 models require "query: " prefix for queries
            encoded_query = f"query: {query}" if "e5" in self.model_name.lower() else query
            query_vector = self._model.encode(
                [encoded_query],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            scores = np.dot(query_vector, self._matrix.T)[0]
        else:
            query_vector = self._vectorizer.transform([query])
            scores = cosine_similarity(query_vector, self._matrix)[0]

        ranked = sorted(zip(self._product_ids, scores.tolist()), key=lambda item: item[1], reverse=True)
        min_score = 0.2 if self.backend == "transformer" else 0.08
        return [(product_id, round(score, 4)) for product_id, score in ranked[: max(limit * 4, 10)] if score >= min_score]

    def status(self) -> SemanticStatus:
        return SemanticStatus(
            ready=self._matrix is not None,
            backend=self.backend,
            model_name=self.model_name,
            indexed_products=len(self._product_ids),
            last_error=self.last_error,
        )

    def reset(self) -> None:
        self.backend = "not-initialized"
        self.last_error = None
        self._model = None
        self._vectorizer = None
        self._product_ids = []
        self._semantic_texts = []
        self._matrix = None

    # --- Embedding cache ---

    def _cache_key(self) -> str:
        content = json.dumps(self._semantic_texts, ensure_ascii=False, sort_keys=True)
        data_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        model_slug = self.model_name.replace("/", "_")
        return f"{model_slug}_{data_hash}"

    def _load_cached_embeddings(self) -> np.ndarray | None:
        cache_path = CACHE_DIR / f"{self._cache_key()}.npy"
        if cache_path.exists():
            try:
                matrix = np.load(cache_path)
                if matrix.shape[0] == len(self._semantic_texts):
                    logger.info("Loaded cached embeddings from %s", cache_path)
                    return matrix
            except Exception:
                pass
        return None

    def _save_cached_embeddings(self, matrix: np.ndarray) -> None:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path = CACHE_DIR / f"{self._cache_key()}.npy"
            np.save(cache_path, matrix)
            logger.info("Saved embeddings cache to %s", cache_path)
        except Exception:
            pass

    def _build_transformer_index(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)

        cached = self._load_cached_embeddings()
        if cached is not None:
            self._matrix = cached
        else:
            # E5 models require "passage: " prefix for documents
            texts = [f"passage: {t}" for t in self._semantic_texts] if "e5" in self.model_name.lower() else self._semantic_texts
            self._matrix = self._model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            self._save_cached_embeddings(self._matrix)

        self._vectorizer = None
        self.backend = "transformer"
        self.last_error = None

    def _build_tfidf_index(self) -> None:
        self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        self._matrix = self._vectorizer.fit_transform(self._semantic_texts)
        self._model = None
        self.backend = "tfidf"

    def _product_text(self, product) -> str:
        weighted_title = f"{product.title} {product.title}"
        aliases = " ".join(product.aliases)
        tags = " ".join(product.tags)
        attributes = " ".join(f"{key} {value}" for key, value in product.attributes.items())
        return " ".join([weighted_title, product.category, product.description, aliases, tags, attributes])


semantic_engine = SemanticSearchEngine()