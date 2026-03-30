import os
from dataclasses import dataclass

from app.text_processing import normalize_query


DEFAULT_RERANKER_MODEL = os.getenv("RERANKER_MODEL_NAME", "BAAI/bge-reranker-v2-m3")
DEFAULT_RERANKER_BACKEND = os.getenv("RERANKER_BACKEND", "heuristic").lower()


@dataclass
class RerankerStatus:
    ready: bool
    backend: str
    model_name: str
    last_error: str | None = None


class QueryReranker:
    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL, backend_preference: str = DEFAULT_RERANKER_BACKEND) -> None:
        self.model_name = model_name
        self.backend_preference = backend_preference
        self.backend = "heuristic"
        self.last_error: str | None = None
        self._model = None

    def rerank(self, query: str, candidates: list[tuple[object, float, list[str]]], top_k: int) -> list[tuple[object, float, list[str]]]:
        if not candidates:
            return []

        if self.backend_preference == "cross-encoder":
            self._ensure_cross_encoder()
        elif self.backend_preference == "auto":
            try:
                self._ensure_cross_encoder()
            except Exception as exc:  # pragma: no cover
                self.backend = "heuristic"
                self.last_error = str(exc)

        if self.backend == "cross-encoder" and self._model is not None:
            pairs = [(query, self._candidate_text(product)) for product, _, _ in candidates]
            scores = self._model.predict(pairs).tolist()
            reranked: list[tuple[object, float, list[str]]] = []
            for (product, base_score, reasons), score in zip(candidates, scores, strict=True):
                final_score = base_score + float(score)
                updated_reasons = reasons + [f"Reranker score: {float(score):.3f}"]
                reranked.append((product, final_score, updated_reasons))
            reranked.sort(key=lambda item: item[1], reverse=True)
            return reranked[:top_k]

        reranked = []
        query_tokens = set(normalize_query(query))
        for product, base_score, reasons in candidates:
            product_tokens = set(normalize_query(self._candidate_text(product)))
            overlap = query_tokens & product_tokens
            overlap_score = len(overlap) * 0.75
            phrase_bonus = 1.0 if " ".join(normalize_query(query)) in " ".join(normalize_query(product.title)) else 0.0
            final_score = base_score + overlap_score + phrase_bonus
            updated_reasons = list(reasons)
            if overlap:
                updated_reasons.append(f"Reranker overlap: {', '.join(sorted(overlap)[:4])}")
            if phrase_bonus:
                updated_reasons.append("Reranker phrase bonus")
            reranked.append((product, final_score, updated_reasons))

        reranked.sort(key=lambda item: item[1], reverse=True)
        self.backend = "heuristic"
        return reranked[:top_k]

    def status(self) -> RerankerStatus:
        return RerankerStatus(
            ready=self.backend == "heuristic" or self._model is not None,
            backend=self.backend,
            model_name=self.model_name,
            last_error=self.last_error,
        )

    def _ensure_cross_encoder(self) -> None:
        if self._model is not None:
            self.backend = "cross-encoder"
            return
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self.model_name)
        self.backend = "cross-encoder"
        self.last_error = None

    def _candidate_text(self, product: object) -> str:
        return " ".join(
            [
                getattr(product, "title", ""),
                getattr(product, "category", ""),
                getattr(product, "description", ""),
                " ".join(getattr(product, "aliases", [])),
                " ".join(getattr(product, "tags", [])),
                " ".join(getattr(product, "attributes", {}).values()),
            ]
        )


reranker = QueryReranker()