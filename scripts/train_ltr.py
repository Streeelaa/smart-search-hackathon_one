"""Train a LightGBM learned-to-rank model from evaluation cases + user events.

Usage:
    python scripts/train_ltr.py

Produces: models/ltr_model.txt
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.catalog_loader import load_catalog
from app.evaluation import EVALUATION_CASES
from app.ltr import build_training_data, train_model, MODEL_PATH, FEATURE_NAMES
from app.repository import repository
from app.search import semantic_scores_for_query


def main() -> None:
    # Ensure catalog is loaded
    if not repository.products:
        products = load_catalog()
        repository.replace_products(products)
    else:
        products = repository.products

    print(f"Catalog: {len(products)} products")
    print(f"Evaluation cases: {len(EVALUATION_CASES)}")

    # Build training queries from evaluation cases
    queries_with_labels = []
    for case in EVALUATION_CASES:
        queries_with_labels.append({
            "query": case["query"],
            "user_id": None,
            "relevant_ids": case["expected_ids"],
        })

    # Also add some synthetic negative-enriched queries
    # (same queries but from different user perspectives)
    for uid in ["user-1", "user-2", "user-3"]:
        for case in EVALUATION_CASES[:5]:
            queries_with_labels.append({
                "query": case["query"],
                "user_id": uid,
                "relevant_ids": case["expected_ids"],
            })

    print(f"Training queries: {len(queries_with_labels)}")

    def sem_fn(query: str) -> dict[int, float]:
        try:
            return semantic_scores_for_query(query, limit=50)
        except Exception:
            return {}

    def profile_fn(user_id: str):
        return repository.get_user_profile(user_id)

    X, y, group = build_training_data(
        queries_with_labels=queries_with_labels,
        products=products,
        semantic_scores_fn=sem_fn,
        profile_fn=profile_fn,
    )

    print(f"Features shape: {X.shape}")
    print(f"Labels: {int(y.sum())} relevant / {len(y)} total")
    print(f"Groups: {len(group)} queries")
    print(f"Feature names: {FEATURE_NAMES}")

    booster = train_model(X, y, group)
    print(f"\nModel saved to {MODEL_PATH}")
    print(f"Feature importance: {dict(zip(FEATURE_NAMES, booster.feature_importance().tolist()))}")


if __name__ == "__main__":
    main()
