from math import log2

from app.schemas import EvaluationCaseResult, EvaluationSummary, SearchMode
from app.search import search_products


EVALUATION_CASES = [
    # Базовый лексический поиск
    {"query": "ноут", "user_id": "user-1", "expected_ids": [1, 2, 3, 5, 6, 8]},
    {"query": "ноутбук lenovo", "user_id": "user-1", "expected_ids": [1, 6, 9]},
    {"query": "мфу hp", "user_id": "user-3", "expected_ids": [13]},
    # Опечатки
    {"query": "монитр", "user_id": None, "expected_ids": [28, 29, 30, 31, 32, 33, 34]},
    {"query": "притнер", "user_id": None, "expected_ids": [13, 14, 15, 16, 17, 18, 20, 21]},
    # Синонимы и жаргон
    {"query": "системник", "user_id": None, "expected_ids": [35, 36, 37, 38]},
    {"query": "бесперебойник", "user_id": None, "expected_ids": [92, 93]},
    {"query": "копир", "user_id": None, "expected_ids": [13, 14, 16, 18, 21]},
    # Канцелярия
    {"query": "офисная бумага", "user_id": None, "expected_ids": [68, 69, 70]},
    {"query": "бумага а4", "user_id": "user-2", "expected_ids": [68, 69]},
    # Мебель
    {"query": "эргономичный стул", "user_id": None, "expected_ids": [43, 45]},
    {"query": "стол для офиса", "user_id": None, "expected_ids": [46, 47, 48]},
    # Периферия
    {"query": "веб-камера", "user_id": None, "expected_ids": [60, 61]},
    {"query": "наушники с микрофоном", "user_id": None, "expected_ids": [62, 63]},
    # Безопасность
    {"query": "камера видеонаблюдения", "user_id": "user-5", "expected_ids": [133]},
    # ПО
    {"query": "антивирус", "user_id": "user-3", "expected_ids": [113]},
    {"query": "виндовс лицензия", "user_id": None, "expected_ids": [112]},
    # Сети
    {"query": "wifi роутер", "user_id": None, "expected_ids": [85, 86]},
    # Серверы
    {"query": "сервер dell", "user_id": "user-1", "expected_ids": [96]},
    # Импортозамещение
    {"query": "российский ноутбук", "user_id": None, "expected_ids": [166, 167]},
]


def precision_at_k(returned_ids: list[int], expected_ids: list[int], k: int) -> float:
    top_k = returned_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for item_id in top_k if item_id in expected_ids)
    return hits / len(top_k)


def recall_at_k(returned_ids: list[int], expected_ids: list[int], k: int) -> float:
    if not expected_ids:
        return 0.0
    hits = sum(1 for item_id in returned_ids[:k] if item_id in expected_ids)
    return hits / len(expected_ids)


def mrr_at_k(returned_ids: list[int], expected_ids: list[int], k: int) -> float:
    for index, item_id in enumerate(returned_ids[:k], start=1):
        if item_id in expected_ids:
            return 1.0 / index
    return 0.0


def ndcg_at_k(returned_ids: list[int], expected_ids: list[int], k: int) -> float:
    dcg = 0.0
    for index, item_id in enumerate(returned_ids[:k], start=1):
        if item_id in expected_ids:
            dcg += 1.0 / log2(index + 1)

    ideal_hits = min(len(expected_ids), k)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def evaluate_search(mode: SearchMode = "hybrid") -> EvaluationSummary:
    case_results: list[EvaluationCaseResult] = []
    precision_scores: list[float] = []
    recall_scores: list[float] = []
    mrr_scores: list[float] = []
    ndcg_scores: list[float] = []
    hit_scores: list[float] = []

    for case in EVALUATION_CASES:
        response = search_products(case["query"], limit=10, user_id=case["user_id"], mode=mode)
        returned_ids = [item.product.id for item in response.items]
        expected_ids = case["expected_ids"]
        precision = precision_at_k(returned_ids, expected_ids, 3)
        recall = recall_at_k(returned_ids, expected_ids, 10)
        mrr = mrr_at_k(returned_ids, expected_ids, 10)
        ndcg = ndcg_at_k(returned_ids, expected_ids, 10)
        hit = any(item_id in expected_ids for item_id in returned_ids[:3])

        precision_scores.append(precision)
        recall_scores.append(recall)
        mrr_scores.append(mrr)
        ndcg_scores.append(ndcg)
        hit_scores.append(1.0 if hit else 0.0)

        case_results.append(
            EvaluationCaseResult(
                query=case["query"],
                user_id=case["user_id"],
                mode=mode,
                expected_ids=expected_ids,
                returned_ids=returned_ids,
                hit_at_3=hit,
                mrr_at_10=round(mrr, 4),
                ndcg_at_10=round(ndcg, 4),
            )
        )

    count = len(case_results)
    return EvaluationSummary(
        cases_count=count,
        mode=mode,
        hit_rate_at_3=round(sum(hit_scores) / count, 4),
        mrr_at_10=round(sum(mrr_scores) / count, 4),
        ndcg_at_10=round(sum(ndcg_scores) / count, 4),
        precision_at_3=round(sum(precision_scores) / count, 4),
        recall_at_10=round(sum(recall_scores) / count, 4),
        cases=case_results,
    )