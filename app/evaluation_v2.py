"""Weighted search evaluation closer to real procurement scenarios."""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.schemas import EvaluationCaseResult, EvaluationSummary, SearchMode
from app.search import search_products

logger = logging.getLogger(__name__)

AUTO_CONTRACT_CASES = 40
AUTO_CONTRACT_WEIGHT = 0.35


@dataclass(frozen=True)
class EvalCaseSpec:
    query: str
    source: str
    weight: float = 1.0
    user_id: str | None = None
    expected_ids: tuple[int, ...] = field(default_factory=tuple)
    expected_categories: tuple[str, ...] = field(default_factory=tuple)
    expected_title_substrings: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None


_STOP_WORDS = frozenset([
    "для", "нужд", "на", "по", "из", "при", "от", "до", "без", "под", "над",
    "поставка", "оказание", "услуг", "услуги", "выполнение", "работ", "работы",
    "приобретение", "закупка", "обеспечение", "организация", "проведение",
    "предоставление", "товаров", "товара", "продукции", "материалов",
    "гбоу", "гбу", "гку", "гуп", "оао", "ооо", "зао", "пао",
    "города", "москвы", "московской", "области", "российской", "федерации",
    "государственного", "государственное", "бюджетного", "казенного",
])


MANUAL_CASES: tuple[EvalCaseSpec, ...] = (
    EvalCaseSpec(
        query="ноутбук Acer",
        expected_title_substrings=("ноутбук", "Acer"),
        source="lexical",
        notes="Точное лексическое совпадение по товару",
    ),
    EvalCaseSpec(
        query="бумага офисная",
        expected_title_substrings=("бумага", "офис"),
        source="lexical",
    ),
    EvalCaseSpec(
        query="картридж лазерный",
        expected_title_substrings=("картридж", "лазерн"),
        source="lexical",
    ),
    EvalCaseSpec(
        query="монитор Dell",
        expected_title_substrings=("монитор", "Dell"),
        source="lexical",
    ),
    EvalCaseSpec(
        query="кабель",
        expected_title_substrings=("кабель",),
        source="lexical",
    ),
    EvalCaseSpec(
        query="принтер",
        expected_title_substrings=("принтер",),
        source="lexical",
    ),
    EvalCaseSpec(
        query="канцтовары",
        expected_categories=(
            "Ручки канцелярские",
            "Карандаши цветные",
            "Маркеры",
            "Папки пластиковые",
        ),
        source="semantic",
        weight=1.35,
        notes="Абстрактная товарная группа, где keyword часто цепляется за шумные поставки",
    ),
    EvalCaseSpec(
        query="оргтехника",
        expected_categories=(
            "Расходные материалы и комплектующие для лазерных принтеров и МФУ",
            "Комплектующие и запасные части для устройств ввода и вывода информации",
        ),
        source="semantic",
        weight=1.25,
    ),
    EvalCaseSpec(
        query="уборка",
        expected_categories=(
            "Инвентарь уборочный",
            "Средства моющие для поверхностей в помещениях",
            "Салфетки, насадки для уборки, полотна технические, ветошь",
        ),
        source="semantic",
        weight=1.25,
    ),
    EvalCaseSpec(
        query="автозапчасти",
        expected_categories=(
            "Запасные части для легковых автомобилей",
            "Аксессуары для автотранспорта и спецтехники",
            "Масла моторные",
        ),
        source="semantic",
        weight=1.2,
    ),
    EvalCaseSpec(
        query="малсо",
        user_id="9701059930",
        expected_categories=("Масла моторные",),
        source="profile",
        weight=1.6,
        notes="Опечатка + персонализация автохозяйства",
    ),
    EvalCaseSpec(
        query="филтьр",
        user_id="9701059930",
        expected_categories=(
            "Запасные части для легковых автомобилей",
            "Запасные части для грузовых автомобилей",
        ),
        source="profile",
        weight=1.65,
        notes="Неоднозначный фильтр должен уйти в автозапчасти для авто-профиля",
    ),
    EvalCaseSpec(
        query="шина",
        user_id="9701059930",
        expected_categories=("Шины пневматические для легкового автомобиля",),
        source="profile",
        weight=1.45,
    ),
    EvalCaseSpec(
        query="краски",
        user_id="5051005670",
        expected_categories=("Краски для рисования",),
        source="profile",
        weight=1.35,
    ),
    EvalCaseSpec(
        query="экскаватор",
        user_id="9718062105",
        expected_categories=("Аренда экскаваторов с экипажем",),
        source="profile",
        weight=1.45,
    ),
)


def _extract_search_query(title: str, max_words: int = 3) -> str | None:
    tokens = re.findall(r"[а-яА-ЯёЁa-zA-Z]{3,}", title)
    meaningful: list[str] = []
    for token in tokens:
        token_lower = token.lower()
        if token_lower in _STOP_WORDS or len(token_lower) < 3:
            continue
        meaningful.append(token)
        if len(meaningful) >= max_words:
            break
    if not meaningful:
        return None
    return " ".join(meaningful)


@lru_cache(maxsize=1)
def _generate_contract_cases(target: int = AUTO_CONTRACT_CASES) -> tuple[EvalCaseSpec, ...]:
    from app.data_loader import get_db_connection

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT p.id, p.title, p.category, COUNT(*) as contract_count
        FROM contracts c
        JOIN products p ON p.id = c.product_id
        WHERE LENGTH(p.title) BETWEEN 10 AND 150
        GROUP BY p.category
        HAVING contract_count >= 3
        ORDER BY contract_count DESC
        LIMIT ?
        """,
        (target * 3,),
    ).fetchall()
    conn.close()

    cases: list[EvalCaseSpec] = []
    seen_queries: set[str] = set()
    for row in rows:
        if len(cases) >= target:
            break
        query = _extract_search_query(row["title"])
        if not query:
            continue
        normalized_query = query.lower().strip()
        if len(normalized_query) < 4 or normalized_query in seen_queries:
            continue
        seen_queries.add(normalized_query)
        cases.append(
            EvalCaseSpec(
                query=query,
                expected_ids=(row["id"],),
                expected_categories=(row["category"],),
                source="contracts",
                weight=AUTO_CONTRACT_WEIGHT,
                notes="Автогенерация из реальных контрактов",
            )
        )

    logger.info("Auto-generated %d contract evaluation cases", len(cases))
    return tuple(cases)


def _title_matches(title: str, substrings: tuple[str, ...]) -> bool:
    title_lower = title.lower()
    return all(sub.lower() in title_lower for sub in substrings)


def _category_matches(category: str, expected_categories: tuple[str, ...]) -> bool:
    if not expected_categories:
        return False
    category_lower = category.lower()
    for expected in expected_categories:
        expected_lower = expected.lower()
        if category_lower == expected_lower:
            return True
        if expected_lower in category_lower or category_lower in expected_lower:
            return True
    return False


def _item_relevance(item, spec: EvalCaseSpec) -> float:
    relevance = 0.0
    if spec.expected_ids and item.product.id in spec.expected_ids:
        relevance = max(relevance, 3.0)
    if spec.expected_title_substrings and _title_matches(item.product.title, spec.expected_title_substrings):
        relevance = max(relevance, 2.5)
    if spec.expected_categories and _category_matches(item.product.category, spec.expected_categories):
        category_gain = 2.2 if spec.source == "profile" else 1.8 if spec.source == "semantic" else 1.2
        relevance = max(relevance, category_gain)
    return relevance


def _evaluate_case(spec: EvalCaseSpec, mode: SearchMode) -> tuple[EvaluationCaseResult, float, float, float, float, float]:
    response = search_products(
        query=spec.query,
        limit=10,
        user_id=spec.user_id,
        mode=mode,
    )

    returned_ids = [item.product.id for item in response.items]
    relevances = [_item_relevance(item, spec) for item in response.items[:10]]
    hit_at_3 = any(rel >= 1.0 for rel in relevances[:3])

    reciprocal_rank = 0.0
    for index, relevance in enumerate(relevances):
        if relevance >= 1.0:
            reciprocal_rank = 1.0 / (index + 1)
            break

    dcg = 0.0
    for index, relevance in enumerate(relevances):
        dcg += relevance / math.log2(index + 2)
    ideal_relevances = sorted(relevances, reverse=True)
    idcg = 0.0
    for index, relevance in enumerate(ideal_relevances):
        idcg += relevance / math.log2(index + 2)
    ndcg = dcg / idcg if idcg > 0 else 0.0

    precision_at_3 = sum(1 for relevance in relevances[:3] if relevance >= 1.0) / 3.0
    recall_at_10 = 1.0 if any(relevance >= 1.0 for relevance in relevances) else 0.0

    case_result = EvaluationCaseResult(
        query=spec.query,
        user_id=spec.user_id,
        mode=mode,
        expected_ids=list(spec.expected_ids),
        expected_categories=list(spec.expected_categories),
        returned_ids=returned_ids[:10],
        hit_at_3=hit_at_3,
        mrr_at_10=round(reciprocal_rank, 4),
        ndcg_at_10=round(ndcg, 4),
        case_source=spec.source,
        case_weight=spec.weight,
        notes=spec.notes,
    )
    return case_result, float(hit_at_3), reciprocal_rank, ndcg, precision_at_3, recall_at_10


def _all_cases() -> tuple[EvalCaseSpec, ...]:
    return MANUAL_CASES + _generate_contract_cases()


def evaluate_search(mode: SearchMode = "hybrid") -> EvaluationSummary:
    try:
        from app.semantic import semantic_engine
        from app.search import _search_cache
        semantic_engine.build_index()
        _search_cache.clear()
    except Exception:
        pass

    cases_specs = _all_cases()
    if not cases_specs:
        return EvaluationSummary(
            cases_count=0,
            mode=mode,
            hit_rate_at_3=0.0,
            mrr_at_10=0.0,
            ndcg_at_10=0.0,
            precision_at_3=0.0,
            recall_at_10=0.0,
            cases=[],
        )

    case_results: list[EvaluationCaseResult] = []
    total_weight = 0.0
    weighted_hit3 = 0.0
    weighted_mrr = 0.0
    weighted_ndcg = 0.0
    weighted_precision3 = 0.0
    weighted_recall10 = 0.0

    for spec in cases_specs:
        case_result, hit3, reciprocal_rank, ndcg, precision_at_3, recall_at_10 = _evaluate_case(spec, mode)
        case_results.append(case_result)

        total_weight += spec.weight
        weighted_hit3 += hit3 * spec.weight
        weighted_mrr += reciprocal_rank * spec.weight
        weighted_ndcg += ndcg * spec.weight
        weighted_precision3 += precision_at_3 * spec.weight
        weighted_recall10 += recall_at_10 * spec.weight

    denominator = total_weight or 1.0
    return EvaluationSummary(
        cases_count=len(case_results),
        mode=mode,
        hit_rate_at_3=round(weighted_hit3 / denominator, 4),
        mrr_at_10=round(weighted_mrr / denominator, 4),
        ndcg_at_10=round(weighted_ndcg / denominator, 4),
        precision_at_3=round(weighted_precision3 / denominator, 4),
        recall_at_10=round(weighted_recall10 / denominator, 4),
        cases=case_results,
    )
