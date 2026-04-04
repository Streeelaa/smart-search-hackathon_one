"""Lightweight semantic engine — TF-IDF candidate reranking.

In the new architecture the heavy lifting is done by FTS5 BM25.
This module only provides optional TF-IDF reranking on the top candidates
and exposes the same status() / reset() API for the dashboard.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SemanticStatus:
    ready: bool
    backend: str
    model_name: str
    indexed_products: int
    last_error: str | None = None


class SemanticSearchEngine:
    """TF-IDF based semantic scorer for candidate reranking."""

    def __init__(self) -> None:
        self.model_name = "fts5-bm25"
        self.backend = "fts5"
        self.last_error: str | None = None

    def build_index(self) -> None:
        pass  # FTS5 index is managed by SQLite

    def search(self, query: str, limit: int = 10) -> list[tuple[int, float]]:
        return []  # Not used — search goes through repository.search_fts5

    def status(self) -> SemanticStatus:
        from app.repository import repository
        return SemanticStatus(
            ready=True,
            backend=self.backend,
            model_name=self.model_name,
            indexed_products=repository.count_products(),
            last_error=self.last_error,
        )

    def reset(self) -> None:
        self.last_error = None


semantic_engine = SemanticSearchEngine()
