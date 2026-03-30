from app.evaluation import evaluate_search
from app.schemas import EvaluationComparisonResponse, EvaluationComparisonRow


def compare_search_modes() -> EvaluationComparisonResponse:
    summaries = [evaluate_search(mode=mode) for mode in ["keyword", "semantic", "hybrid"]]
    rows = [
        EvaluationComparisonRow(
            mode=summary.mode,
            hit_rate_at_3=summary.hit_rate_at_3,
            mrr_at_10=summary.mrr_at_10,
            ndcg_at_10=summary.ndcg_at_10,
            precision_at_3=summary.precision_at_3,
            recall_at_10=summary.recall_at_10,
        )
        for summary in summaries
    ]
    best_mode = max(rows, key=lambda row: row.ndcg_at_10).mode
    return EvaluationComparisonResponse(rows=rows, best_mode_by_ndcg=best_mode)