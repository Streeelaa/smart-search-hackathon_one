from dataclasses import dataclass
import os

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.repository import repository


DEFAULT_MODEL_NAME = os.getenv("SEMANTIC_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
DEFAULT_BACKEND = os.getenv("SEMANTIC_BACKEND", "auto").lower()


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
            query_vector = self._model.encode(
                [query],
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

    def _build_transformer_index(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)
        self._matrix = self._model.encode(
            self._semantic_texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
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