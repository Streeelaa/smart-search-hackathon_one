"""Search quality evaluation on real data."""
from __future__ import annotations

import math
from app.schemas import EvaluationCaseResult, EvaluationSummary, SearchMode
from app.search import search_products


# Evaluation cases based on real data
# Format: (query, expected_product_ids_substring_in_title, mode, user_id)
EVALUATION_CASES: list[dict] = [
    {"query": "ноутбук Acer", "expected_title_substrings": ["Ноутбук", "Acer"], "mode": "hybrid", "user_id": None},
    {"query": "бумага офисная", "expected_title_substrings": ["Бумага", "офисная"], "mode": "hybrid", "user_id": None},
    {"query": "картридж лазерный", "expected_title_substrings": ["Картридж", "лазерн"], "mode": "hybrid", "user_id": None},
    {"query": "монитор Dell", "expected_title_substrings": ["Монитор", "Dell"], "mode": "hybrid", "user_id": None},
    {"query": "кабель", "expected_title_substrings": ["Кабель"], "mode": "hybrid", "user_id": None},
    {"query": "спецодежда", "expected_title_substrings": ["Спецодежда"], "mode": "hybrid", "user_id": None},
    {"query": "принтер", "expected_title_substrings": ["Принтер"], "mode": "hybrid", "user_id": None},
    {"query": "мебель офисная", "expected_title_substrings": ["Мебель", "офис"], "mode": "hybrid", "user_id": None},
]


def _title_matches(title: str, substrings: list[str]) -> bool:
    title_lower = title.lower()
    return all(s.lower() in title_lower for s in substrings)


def evaluate_search(mode: SearchMode = "hybrid") -> EvaluationSummary:
    cases: list[EvaluationCaseResult] = []

    for case in EVALUATION_CASES:
        response = search_products(
            query=case["query"],
            limit=10,
            user_id=case.get("user_id"),
            mode=mode,
        )

        returned_ids = [item.product.id for item in response.items]
        returned_titles = [item.product.title for item in response.items]

        # Check if any of top-3 results match expected substrings
        hit3 = any(
            _title_matches(t, case["expected_title_substrings"])
            for t in returned_titles[:3]
        )

        # MRR: first matching position
        rr = 0.0
        for i, t in enumerate(returned_titles[:10]):
            if _title_matches(t, case["expected_title_substrings"]):
                rr = 1.0 / (i + 1)
                break

        # NDCG simplified: relevant = matches substrings
        dcg = 0.0
        idcg = 0.0
        relevance_list = [
            1.0 if _title_matches(t, case["expected_title_substrings"]) else 0.0
            for t in returned_titles[:10]
        ]
        for i, rel in enumerate(relevance_list):
            dcg += rel / math.log2(i + 2)
        num_relevant = sum(relevance_list)
        for i in range(int(num_relevant)):
            idcg += 1.0 / math.log2(i + 2)
        ndcg = dcg / idcg if idcg > 0 else 0.0

        cases.append(
            EvaluationCaseResult(
                query=case["query"],
                user_id=case.get("user_id"),
                mode=mode,
                expected_ids=[],
                returned_ids=returned_ids[:10],
                hit_at_3=hit3,
                mrr_at_10=round(rr, 4),
                ndcg_at_10=round(ndcg, 4),
            )
        )

    n = len(cases) or 1
    return EvaluationSummary(
        cases_count=len(cases),
        hit_rate_at_3=round(sum(c.hit_at_3 for c in cases) / n, 4),
        mrr_at_10=round(sum(c.mrr_at_10 for c in cases) / n, 4),
        ndcg_at_10=round(sum(c.ndcg_at_10 for c in cases) / n, 4),
        precision_at_3=round(
            sum(
                sum(1 for t in [item.product.title for item in search_products(c.query, limit=3, mode=mode).items] if _title_matches(t, case["expected_title_substrings"])) / 3.0
                for c, case in zip(cases, EVALUATION_CASES)
            ) / n,
            4,
        ) if cases else 0.0,
        recall_at_10=round(sum(c.ndcg_at_10 for c in cases) / n, 4),
        cases=cases,
    )
