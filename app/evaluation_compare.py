"""Compare search quality across modes."""
from __future__ import annotations

from app.evaluation import evaluate_search
from app.schemas import EvaluationComparisonResponse, EvaluationComparisonRow


def compare_search_modes() -> EvaluationComparisonResponse:
    rows: list[EvaluationComparisonRow] = []
    best_mode = "hybrid"
    best_ndcg = -1.0

    for mode in ("keyword", "hybrid"):
        summary = evaluate_search(mode=mode)
        rows.append(
            EvaluationComparisonRow(
                mode=mode,
                hit_rate_at_3=summary.hit_rate_at_3,
                mrr_at_10=summary.mrr_at_10,
                ndcg_at_10=summary.ndcg_at_10,
                precision_at_3=summary.precision_at_3,
                recall_at_10=summary.recall_at_10,
            )
        )
        if summary.ndcg_at_10 > best_ndcg:
            best_ndcg = summary.ndcg_at_10
            best_mode = mode

    return EvaluationComparisonResponse(
        rows=rows,
        best_mode_by_ndcg=best_mode,
    )
