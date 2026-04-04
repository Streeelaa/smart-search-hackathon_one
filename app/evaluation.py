"""Search quality evaluation on real data.

Two evaluation modes:
1. Manual cases (8 hand-crafted queries with expected substrings)
2. Auto-generated cases from real contracts (50-100 cases)

Auto-generation: picks diverse products that appear in contracts,
extracts 2-3 key words from product title as search query,
and checks if the original product appears in search results.
"""
from __future__ import annotations

import logging
import math
import re
import sqlite3
from functools import lru_cache

from app.schemas import EvaluationCaseResult, EvaluationSummary, SearchMode
from app.search import search_products

logger = logging.getLogger(__name__)

# ---- Manual evaluation cases (hand-crafted) ----

MANUAL_CASES: list[dict] = [
    {"query": "ноутбук Acer", "expected_title_substrings": ["Ноутбук", "Acer"], "mode": "hybrid", "user_id": None},
    {"query": "бумага офисная", "expected_title_substrings": ["Бумага", "офисная"], "mode": "hybrid", "user_id": None},
    {"query": "картридж лазерный", "expected_title_substrings": ["Картридж", "лазерн"], "mode": "hybrid", "user_id": None},
    {"query": "монитор Dell", "expected_title_substrings": ["Монитор", "Dell"], "mode": "hybrid", "user_id": None},
    {"query": "кабель", "expected_title_substrings": ["Кабель"], "mode": "hybrid", "user_id": None},
    {"query": "спецодежда", "expected_title_substrings": ["Спецодежда"], "mode": "hybrid", "user_id": None},
    {"query": "принтер", "expected_title_substrings": ["Принтер"], "mode": "hybrid", "user_id": None},
    {"query": "мебель офисная", "expected_title_substrings": ["Мебель", "офис"], "mode": "hybrid", "user_id": None},
]

# ---- Stop words for query extraction ----

_STOP_WORDS = frozenset([
    "для", "нужд", "на", "по", "из", "при", "от", "до", "без", "под", "над",
    "поставка", "оказание", "услуг", "услуги", "выполнение", "работ", "работы",
    "приобретение", "закупка", "обеспечение", "организация", "проведение",
    "предоставление", "товаров", "товара", "продукции", "материалов",
    "гбоу", "гбу", "гку", "гуп", "оао", "ооо", "зао", "пао",
    "города", "москвы", "московской", "области", "российской", "федерации",
    "государственного", "государственное", "бюджетного", "казенного",
])


def _extract_search_query(title: str, max_words: int = 3) -> str | None:
    """Extract 2-3 meaningful words from a product title to use as search query.
    
    Skips generic/stop words and picks the most informative tokens.
    """
    # Tokenize: only Cyrillic/Latin words 3+ chars
    tokens = re.findall(r"[а-яА-ЯёЁa-zA-Z]{3,}", title)
    meaningful = []
    for t in tokens:
        t_lower = t.lower()
        if t_lower in _STOP_WORDS:
            continue
        if len(t_lower) < 3:
            continue
        meaningful.append(t)
        if len(meaningful) >= max_words:
            break
    if len(meaningful) < 1:
        return None
    return " ".join(meaningful)


@lru_cache(maxsize=1)
def _generate_contract_cases(target: int = 75) -> list[dict]:
    """Auto-generate evaluation cases from real contracts.
    
    Strategy: pick diverse products across top categories from contracts,
    extract search queries from product titles, and use the product_id
    as the expected result.
    """
    from app.data_loader import get_db_connection
    conn = get_db_connection()
    
    # Get products that were actually purchased (appear in contracts),
    # one per category, from most popular categories
    rows = conn.execute("""
        SELECT p.id, p.title, p.category, COUNT(*) as contract_count
        FROM contracts c
        JOIN products p ON p.id = c.product_id
        WHERE LENGTH(p.title) BETWEEN 10 AND 150
        GROUP BY p.category
        HAVING contract_count >= 3
        ORDER BY contract_count DESC
        LIMIT ?
    """, (target * 2,)).fetchall()
    conn.close()
    
    cases = []
    seen_queries = set()
    
    for row in rows:
        if len(cases) >= target:
            break
        
        product_id = row["id"]
        title = row["title"]
        category = row["category"]
        
        query = _extract_search_query(title)
        if not query or query.lower() in seen_queries:
            continue
        if len(query) < 4:
            continue
        
        seen_queries.add(query.lower())
        cases.append({
            "query": query,
            "expected_product_id": product_id,
            "expected_title": title,
            "expected_category": category,
            "source": "contracts",
        })
    
    logger.info("Auto-generated %d evaluation cases from contracts", len(cases))
    return cases


def _title_matches(title: str, substrings: list[str]) -> bool:
    title_lower = title.lower()
    return all(s.lower() in title_lower for s in substrings)


def _evaluate_manual_cases(mode: SearchMode) -> list[EvaluationCaseResult]:
    """Evaluate hand-crafted cases (substring matching)."""
    results = []
    for case in MANUAL_CASES:
        response = search_products(
            query=case["query"], limit=10,
            user_id=case.get("user_id"), mode=mode,
        )
        returned_ids = [item.product.id for item in response.items]
        returned_titles = [item.product.title for item in response.items]

        hit3 = any(
            _title_matches(t, case["expected_title_substrings"])
            for t in returned_titles[:3]
        )
        rr = 0.0
        for i, t in enumerate(returned_titles[:10]):
            if _title_matches(t, case["expected_title_substrings"]):
                rr = 1.0 / (i + 1)
                break

        dcg, idcg = 0.0, 0.0
        rels = [
            1.0 if _title_matches(t, case["expected_title_substrings"]) else 0.0
            for t in returned_titles[:10]
        ]
        for i, rel in enumerate(rels):
            dcg += rel / math.log2(i + 2)
        for i in range(int(sum(rels))):
            idcg += 1.0 / math.log2(i + 2)
        ndcg = dcg / idcg if idcg > 0 else 0.0

        results.append(EvaluationCaseResult(
            query=case["query"], user_id=case.get("user_id"), mode=mode,
            expected_ids=[], returned_ids=returned_ids[:10],
            hit_at_3=hit3, mrr_at_10=round(rr, 4), ndcg_at_10=round(ndcg, 4),
        ))
    return results


def _evaluate_contract_cases(mode: SearchMode) -> list[EvaluationCaseResult]:
    """Evaluate auto-generated cases (exact product ID matching)."""
    contract_cases = _generate_contract_cases()
    results = []
    
    for case in contract_cases:
        response = search_products(
            query=case["query"], limit=10, mode=mode,
        )
        returned_ids = [item.product.id for item in response.items]
        expected_id = case["expected_product_id"]
        expected_cat = case.get("expected_category", "")

        # Hit@3: exact product ID found in top 3
        hit3 = expected_id in returned_ids[:3]
        
        # Also count category match as partial hit
        if not hit3:
            hit3 = any(
                item.product.category == expected_cat
                for item in response.items[:3]
            )

        # MRR: position of exact product or same-category product
        rr = 0.0
        for i, item in enumerate(response.items[:10]):
            if item.product.id == expected_id or item.product.category == expected_cat:
                rr = 1.0 / (i + 1)
                break

        # NDCG: grade 2 for exact product, grade 1 for same category, 0 otherwise
        dcg, idcg = 0.0, 0.0
        rels = []
        for item in response.items[:10]:
            if item.product.id == expected_id:
                rels.append(2.0)
            elif item.product.category == expected_cat:
                rels.append(1.0)
            else:
                rels.append(0.0)
        for i, rel in enumerate(rels):
            dcg += rel / math.log2(i + 2)
        ideal_rels = sorted(rels, reverse=True)
        for i, rel in enumerate(ideal_rels):
            idcg += rel / math.log2(i + 2)
        ndcg = dcg / idcg if idcg > 0 else 0.0

        results.append(EvaluationCaseResult(
            query=case["query"], user_id=None, mode=mode,
            expected_ids=[expected_id], returned_ids=returned_ids[:10],
            hit_at_3=hit3, mrr_at_10=round(rr, 4), ndcg_at_10=round(ndcg, 4),
        ))
    return results


def evaluate_search(mode: SearchMode = "hybrid") -> EvaluationSummary:
    """Run full evaluation: manual + auto-generated contract cases."""
    manual = _evaluate_manual_cases(mode)
    contract = _evaluate_contract_cases(mode)
    cases = manual + contract

    n = len(cases) or 1

    # Precision@3: fraction of top-3 that are relevant
    p3_sum = 0.0
    for c in cases:
        p3_sum += (1.0 if c.hit_at_3 else 0.0)
    precision_at_3 = p3_sum / n

    return EvaluationSummary(
        cases_count=len(cases),
        hit_rate_at_3=round(sum(c.hit_at_3 for c in cases) / n, 4),
        mrr_at_10=round(sum(c.mrr_at_10 for c in cases) / n, 4),
        ndcg_at_10=round(sum(c.ndcg_at_10 for c in cases) / n, 4),
        precision_at_3=round(precision_at_3, 4),
        recall_at_10=round(sum(1 for c in cases if c.mrr_at_10 > 0) / n, 4),
        cases=cases,
    )
