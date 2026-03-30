"""LightGBM Learning-to-Rank module.

Trains a lambdarank model on features extracted from the search pipeline
and user interaction signals.  Falls back gracefully when no trained model
exists — the rest of the pipeline keeps working.
"""

import json
import logging
import os
from pathlib import Path

import numpy as np

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover
    lgb = None

from app.schemas import Product, UserProfile
from app.text_processing import normalize_query, normalize_text

logger = logging.getLogger(__name__)

MODEL_PATH = Path(os.getenv("LTR_MODEL_PATH", "models/ltr_model.txt"))
FEATURE_NAMES = [
    "lexical_score",
    "semantic_score",
    "personalization_score",
    "title_match_ratio",
    "tag_overlap",
    "category_affinity",
    "price_distance_norm",
    "query_len",
    "desc_len",
]


def extract_features(
    product: Product,
    query_tokens: list[str],
    lexical_score: float,
    semantic_score: float,
    personalization_score: float,
    profile: UserProfile | None,
) -> np.ndarray:
    """Build a feature vector for a single (query, product) pair."""
    title_tokens = set(normalize_query(product.title))
    query_set = set(query_tokens)

    # title_match_ratio: fraction of query tokens found in title
    title_match_ratio = len(query_set & title_tokens) / max(len(query_set), 1)

    # tag_overlap: how many query tokens appear in product tags
    tag_tokens = {t.lower() for t in product.tags}
    tag_overlap = len(query_set & tag_tokens)

    # category_affinity from profile
    cat_affinity = 0.0
    if profile and profile.category_affinity:
        cat_affinity = profile.category_affinity.get(product.category, 0.0)

    # price_distance_norm: normalized distance from user's average price
    price_dist = 0.0
    if profile and profile.average_price and profile.average_price > 0:
        price_dist = abs(product.price - profile.average_price) / profile.average_price

    query_len = len(query_tokens)
    desc_len = len(normalize_query(product.description)) if product.description else 0

    return np.array(
        [
            lexical_score,
            semantic_score,
            personalization_score,
            title_match_ratio,
            tag_overlap,
            cat_affinity,
            price_dist,
            query_len,
            desc_len,
        ],
        dtype=np.float32,
    )


class LTRRanker:
    """LightGBM-based learned ranker with automatic fallback."""

    def __init__(self) -> None:
        self._model = None
        self._ready = False
        self._load_model()

    def _load_model(self) -> None:
        if lgb is None:
            logger.info("LightGBM not installed — LTR disabled")
            return
        if not MODEL_PATH.exists():
            logger.info("No LTR model at %s — using score-based ranking", MODEL_PATH)
            return
        try:
            self._model = lgb.Booster(model_file=str(MODEL_PATH))
            self._ready = True
            logger.info("LTR model loaded from %s", MODEL_PATH)
        except Exception as exc:
            logger.warning("Failed to load LTR model: %s", exc)

    @property
    def ready(self) -> bool:
        return self._ready

    def predict(self, features_matrix: np.ndarray) -> np.ndarray:
        """Return relevance scores for rows of features.  Falls back to zeros."""
        if not self._ready or self._model is None:
            return np.zeros(len(features_matrix), dtype=np.float32)
        return self._model.predict(features_matrix).astype(np.float32)

    def reload(self) -> None:
        """Hot-reload model from disk."""
        self._model = None
        self._ready = False
        self._load_model()


# ---------------------------------------------------------------------------
# Training helpers — called from scripts/train_ltr.py
# ---------------------------------------------------------------------------

def build_training_data(
    queries_with_labels: list[dict],
    products: list[Product],
    semantic_scores_fn,
    profile_fn,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build X, y, group arrays for LightGBM lambdarank.

    queries_with_labels: list of {
        "query": str,
        "user_id": str | None,
        "relevant_ids": list[int],    # product ids considered relevant
    }
    """
    from app.search import lexical_score as calc_lexical, personalization_score as calc_personal

    all_features = []
    all_labels = []
    group_sizes = []

    for entry in queries_with_labels:
        query = entry["query"]
        user_id = entry.get("user_id")
        relevant_set = set(entry.get("relevant_ids", []))
        query_tokens = normalize_query(query)
        profile = profile_fn(user_id) if user_id else None
        sem_scores = semantic_scores_fn(query)

        group_count = 0
        for product in products:
            lex, _ = calc_lexical(product, query_tokens)
            sem = sem_scores.get(product.id, 0.0)
            pers, _ = calc_personal(product, profile)

            feat = extract_features(product, query_tokens, lex, sem, pers, profile)
            label = 1.0 if product.id in relevant_set else 0.0
            all_features.append(feat)
            all_labels.append(label)
            group_count += 1

        group_sizes.append(group_count)

    return (
        np.array(all_features, dtype=np.float32),
        np.array(all_labels, dtype=np.float32),
        np.array(group_sizes, dtype=np.int32),
    )


def train_model(
    X: np.ndarray,
    y: np.ndarray,
    group: np.ndarray,
    save_path: Path | None = None,
) -> "lgb.Booster":
    """Train a LightGBM lambdarank model and save it."""
    if lgb is None:
        raise RuntimeError("LightGBM is not installed")

    train_data = lgb.Dataset(X, label=y, group=group, feature_name=FEATURE_NAMES, free_raw_data=False)

    params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "ndcg_eval_at": [3, 5, 10],
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 1,
        "verbose": -1,
    }

    booster = lgb.train(params, train_data, num_boost_round=100)

    out = save_path or MODEL_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out))
    logger.info("LTR model saved to %s", out)
    return booster


# Singleton
ltr_ranker = LTRRanker()
