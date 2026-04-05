"""Two-stage search: FTS5 BM25 retrieval + personalization reranking."""
from __future__ import annotations

import logging
import re
import time
from collections import Counter
from functools import lru_cache

from app.repository import repository
from app.schemas import CategoryFacet, Product, SearchMode, SearchResponse, SearchResult, UserProfile
from app.synonyms import expand_terms_with_synonyms
from app.text_processing import correct_tokens, normalize_query, normalize_text, normalize_tokens, tokenize

logger = logging.getLogger(__name__)

PERSONALIZATION_WEIGHT = 5.0
AMBIGUOUS_QUERY_PERSONALIZATION_BONUS = 24.0
MAX_PERSONALIZATION_MULTIPLIER = 8.0
SHORT_QUERY_TOKEN_THRESHOLD = 2
SHORT_TOKEN_SYNONYM_THRESHOLD = 4
SEMANTIC_MIN_AMBIGUITY = 0.58
SEMANTIC_TOP_SCORE_REFERENCE = 12.0
SEMANTIC_BONUS_BASE = 1.2
SEMANTIC_BONUS_MAX = 4.5

# ---- Stop words — short/common words that slow FTS5 without adding value ----
_FTS_STOP_WORDS = frozenset([
    "для", "на", "по", "из", "при", "от", "до", "без", "под", "над",
    "и", "в", "с", "к", "у", "о", "а", "не", "но", "за", "или",
    "он", "она", "оно", "они", "это", "тот", "что", "как", "все",
])

# ---- Vocabulary (lazy-loaded once) ----
_vocabulary: set[str] | None = None


def _get_vocabulary() -> set[str]:
    global _vocabulary
    if _vocabulary is None:
        logger.info("Building vocabulary for typo correction (first time)...")
        _vocabulary = repository.build_vocabulary()
        logger.info("Vocabulary ready: %d terms", len(_vocabulary))
    return _vocabulary


def warm_up() -> None:
    """Pre-build vocabulary on startup so first search is fast."""
    _get_vocabulary()


@lru_cache(maxsize=1024)
def _cached_build_fts_query_terms(query: str, expand_synonyms: bool = True) -> tuple[str, ...]:
    """Cached version — returns tuple for hashability."""
    return tuple(build_fts_query_terms(query, expand_synonyms=expand_synonyms))


# ---- Search result cache ----
_search_cache: dict[tuple, SearchResponse] = {}
_SEARCH_CACHE_MAX = 256


def build_fts_query_terms(query: str, expand_synonyms: bool = True) -> list[str]:
    """Build diverse search terms for FTS5 from user query.

    Combines raw tokens (with inflections), lemmatised forms, synonym
    expansions, AND raw (un-normalized) synonym values for maximum recall.
    This ensures both singular and plural forms reach FTS5.
    """
    raw_tokens = tokenize(query)
    normalized = normalize_query(query)
    try:
        expanded = expand_terms_with_synonyms(normalized) if expand_synonyms else list(normalized)
    except Exception:
        expanded = list(normalized)

    # Also get raw synonym values (before normalization) to preserve plurals
    raw_synonym_tokens: list[str] = []
    if expand_synonyms:
        try:
            from app.synonyms import load_synonyms
            syn_map = load_synonyms()
            for token in normalized:
                norm_key = normalize_text(token)
                for syn_value in syn_map.get(norm_key, []):
                    for t in tokenize(syn_value):
                        raw_synonym_tokens.append(t)
        except Exception:
            pass

    all_terms: list[str] = []
    seen: set[str] = set()
    for term in raw_tokens + normalized + expanded + raw_synonym_tokens:
        if term and term not in seen and term not in _FTS_STOP_WORDS:
            seen.add(term)
            all_terms.append(term)
    # Cap at 15 terms to prevent slow FTS queries
    return all_terms[:15]


def _should_expand_synonyms(raw_tokens: list[str], normalized_tokens: list[str]) -> bool:
    """Expand synonyms aggressively only for confident or abbreviation-like queries."""
    if len(normalized_tokens) != 1:
        return True
    token = normalized_tokens[0]
    raw_token = raw_tokens[0] if raw_tokens else token
    if len(token) <= SHORT_TOKEN_SYNONYM_THRESHOLD:
        return True
    if any(ch.isdigit() for ch in raw_token):
        return True
    if any("a" <= ch <= "z" for ch in token):
        return True
    return False


def _query_ambiguity_score(
    raw_tokens: list[str],
    candidates: list[tuple[Product, float]],
) -> float:
    """Estimate how ambiguous the current query/result set is."""
    if not candidates:
        return 0.0

    top_candidates = candidates[:15]
    unique_categories = len({product.category for product, _ in top_candidates})
    diversity_score = min(1.0, unique_categories / 8.0)
    short_query_score = 1.0 if len(raw_tokens) <= SHORT_QUERY_TOKEN_THRESHOLD else 0.0

    top_scores = [score for _, score in top_candidates[:5]]
    flatness_score = 0.0
    if len(top_scores) >= 2:
        lead = max(top_scores)
        tail = min(top_scores)
        span_ratio = abs(lead - tail) / max(abs(lead), 1.0)
        flatness_score = 1.0 - min(1.0, span_ratio)

    ambiguity = (
        short_query_score * 0.45
        + diversity_score * 0.35
        + flatness_score * 0.20
    )
    return min(1.0, ambiguity)


def _keyword_confidence_score(candidates: list[tuple[Product, float]], limit: int) -> float:
    """Estimate how much we can trust lexical retrieval on its own."""
    if not candidates:
        return 0.0

    top_scores = [score for _, score in candidates[:5]]
    lead = top_scores[0]
    third = top_scores[min(2, len(top_scores) - 1)]
    coverage_score = min(1.0, len(candidates) / max(limit * 3, 1))
    strength_score = min(1.0, lead / SEMANTIC_TOP_SCORE_REFERENCE)
    dominance_score = min(1.0, max(0.0, (lead - third) / max(abs(lead), 1.0)))
    confidence = (
        coverage_score * 0.35
        + strength_score * 0.40
        + dominance_score * 0.25
    )
    return min(1.0, confidence)


def _should_use_semantic(
    mode: SearchMode,
    candidates: list[tuple[Product, float]],
    limit: int,
    ambiguity_score: float,
    keyword_confidence: float,
) -> bool:
    if mode == "semantic":
        return True
    if mode != "hybrid":
        return False
    if not candidates or len(candidates) < limit * 2:
        return True
    if ambiguity_score >= SEMANTIC_MIN_AMBIGUITY:
        return True
    return keyword_confidence < 0.45


def _should_inject_semantic_candidates(
    mode: SearchMode,
    candidates: list[tuple[Product, float]],
    limit: int,
    ambiguity_score: float,
    keyword_confidence: float,
) -> bool:
    if mode == "semantic":
        return True
    if not candidates or len(candidates) < limit:
        return True
    return ambiguity_score >= 0.75 and keyword_confidence < 0.65


def _semantic_bonus_weight(
    mode: SearchMode,
    ambiguity_score: float,
    keyword_confidence: float,
) -> float:
    if mode == "semantic":
        return SEMANTIC_BONUS_MAX
    weight = (
        SEMANTIC_BONUS_BASE
        + ambiguity_score * 1.8
        + max(0.0, 0.55 - keyword_confidence) * 2.5
    )
    return max(0.0, min(SEMANTIC_BONUS_MAX, weight))


def personalization_multiplier(
    product: Product,
    profile: UserProfile | None,
    ambiguity_score: float = 0.0,
) -> tuple[float, list[str]]:
    """Compute multiplicative personalization boost from contract history.

    Returns (multiplier, reasons) where multiplier >= 1.0.
    A product in the user's top category gets up to 2.5x boost.
    """
    if profile is None or profile.total_events == 0:
        return 1.0, []

    reasons: list[str] = []

    cat_score = profile.category_affinity.get(product.category, 0.0)
    if cat_score > 0:
        dynamic_weight = PERSONALIZATION_WEIGHT + ambiguity_score * AMBIGUOUS_QUERY_PERSONALIZATION_BONUS
        multiplier = min(
            1.0 + cat_score * dynamic_weight,
            MAX_PERSONALIZATION_MULTIPLIER,
        )
        pct = f"{cat_score:.0%}"
        reasons.append(f"Категория в {pct} закупок пользователя (+{multiplier - 1:.0%} буст)")
        if ambiguity_score >= 0.55:
            reasons.append("Короткий/неоднозначный запрос: персонализация усилена")
        return multiplier, reasons

    return 1.0, []


def _highlight_title(title: str, query_tokens: list[str]) -> str:
    """Add <mark> tags around query tokens in title for highlighting."""
    if not query_tokens:
        return title
    # Build pattern matching any token (word boundary for Cyrillic)
    escaped = [re.escape(t) for t in query_tokens if len(t) >= 2]
    if not escaped:
        return title
    pattern = re.compile(r"(" + "|".join(escaped) + r")", re.IGNORECASE)
    return pattern.sub(r"<mark>\1</mark>", title)


def _build_facets(scored: list[tuple[Product, float, list[str], int]], limit: int = 10) -> list[CategoryFacet]:
    """Build category facets from scored results."""
    counter: Counter[str] = Counter()
    for product, _, _, _ in scored:
        counter[product.category] += 1
    return [
        CategoryFacet(category=cat, count=cnt)
        for cat, cnt in counter.most_common(limit)
    ]


def search_products(
    query: str,
    limit: int = 10,
    user_id: str | None = None,
    mode: SearchMode = "hybrid",
    category_filter: str | None = None,
) -> SearchResponse:
    """Main search entry point — FTS5 BM25 + typo correction + personalization."""
    # Check cache first
    cache_key = (query, limit, user_id, mode, category_filter)
    if cache_key in _search_cache:
        cached = _search_cache[cache_key]
        # Return cached result with 0ms time to show it was cached
        return cached

    t0 = time.perf_counter()

    # 1. Tokenize raw
    raw_tokens = tokenize(query)

    # 2. Typo correction on RAW tokens (before normalization to avoid pymorphy3 mangling)
    typo_corrected = False
    corrected_raw = list(raw_tokens)
    try:
        vocab = _get_vocabulary()
        corrected_raw, changed = correct_tokens(list(raw_tokens), vocab)
        if changed:
            typo_corrected = True
    except Exception:
        pass
    corrected_query = " ".join(corrected_raw) if corrected_raw else query

    # 3. Normalize (after typo correction)
    normalized = normalize_tokens(corrected_raw)
    corrected_tokens = list(normalized)

    # 4. Expand with synonyms
    expand_synonyms = _should_expand_synonyms(raw_tokens, corrected_tokens)
    try:
        expanded_terms = expand_terms_with_synonyms(corrected_tokens) if expand_synonyms else list(corrected_tokens)
    except Exception:
        expanded_terms = list(corrected_tokens)

    # 4a. Load profile early so we can tune reranking for ambiguous queries
    profile = repository.get_user_profile(user_id) if user_id else None

    # 5. FTS5 BM25 retrieval (use both original and corrected tokens)
    fts_terms = list(_cached_build_fts_query_terms(query, expand_synonyms))
    if typo_corrected:
        fts_terms_corrected = list(_cached_build_fts_query_terms(corrected_query, expand_synonyms))
        fts_terms = list(dict.fromkeys(fts_terms + fts_terms_corrected))
    candidate_limit = max(limit * 10, 100)
    candidates = repository.search_fts5(fts_terms, limit=candidate_limit)
    ambiguity_score = _query_ambiguity_score(corrected_tokens or raw_tokens, candidates)
    keyword_confidence = _keyword_confidence_score(candidates, limit)

    # 4b. Semantic expansion: only when lexical evidence is weak or ambiguous
    semantic_categories: list[tuple[str, float]] = []
    semantic_category_scores: dict[str, float] = {}
    semantic_injected_ids: set[int] = set()
    needs_semantic = _should_use_semantic(
        mode,
        candidates,
        limit,
        ambiguity_score,
        keyword_confidence,
    )
    try:
        from app.semantic import semantic_engine
        if semantic_engine._ready and needs_semantic:
            sem_query = corrected_query if typo_corrected else query
            semantic_categories = list(
                semantic_engine.find_similar_categories_cached(sem_query, top_k=3)
            )
            if semantic_categories:
                semantic_category_scores = {
                    cat_name: cat_score for cat_name, cat_score in semantic_categories
                }
                seen_ids = {p.id for p, _ in candidates}
                if _should_inject_semantic_candidates(
                    mode,
                    candidates,
                    limit,
                    ambiguity_score,
                    keyword_confidence,
                ):
                    for cat_name, _cat_score in semantic_categories:
                        if category_filter and cat_name != category_filter:
                            continue
                        cat_products = repository.list_products(category=cat_name, limit=10)
                        for product in cat_products:
                            if product.id not in seen_ids:
                                seen_ids.add(product.id)
                                semantic_injected_ids.add(product.id)
                                candidates.append((product, 0.0))
    except Exception:
        pass

    # 6. Score candidates
    scored: list[tuple[Product, float, list[str]]] = []
    query_lower = query.lower().strip()
    highlight_tokens = raw_tokens + corrected_tokens
    semantic_bonus_weight = _semantic_bonus_weight(mode, ambiguity_score, keyword_confidence)

    for product, bm25_score in candidates:
        # Category filter
        if category_filter and product.category != category_filter:
            continue

        reasons: list[str] = []
        total_score = bm25_score

        # Title match bonuses
        title_lower = product.title.lower()
        if query_lower and query_lower in title_lower:
            total_score += 5.0
            reasons.append("Точное совпадение фразы в названии")
        else:
            hit_count = sum(1 for t in raw_tokens if t in title_lower)
            if hit_count > 0:
                total_score += hit_count * 0.5
                if hit_count == len(raw_tokens) and len(raw_tokens) > 1:
                    reasons.append("Все слова запроса в названии")

        # Category match
        cat_lower = product.category.lower()
        for t in raw_tokens:
            if t in cat_lower:
                total_score += 1.0
                reasons.append(f"Категория: {product.category}")
                break

        semantic_score = semantic_category_scores.get(product.category, 0.0)
        if semantic_score > 0 and semantic_bonus_weight > 0:
            total_score += semantic_score * semantic_bonus_weight
            reasons.append(f"Semantic category: {product.category}")

        if product.id in semantic_injected_ids:
            reasons.insert(0, f"SEM: {semantic_score:.2f}")
        else:
            reasons.insert(0, f"BM25: {bm25_score:.1f}")

        # Personalization: multiplicative boost (only in hybrid mode)
        is_personalized = 0
        if mode == "hybrid":
            mult, pers_reasons = personalization_multiplier(
                product,
                profile,
                ambiguity_score=ambiguity_score,
            )
            if mult > 1.0:
                total_score *= mult
                reasons.extend(pers_reasons)
                is_personalized = 1

        scored.append((product, total_score, reasons, is_personalized))

    # 6b. If we got semantic category matches but no FTS results, add semantic reason
    # (this helps for abstract queries like "канцтовары", "медикаменты")

    # 7. Sort: personalized first, then by total score
    scored.sort(key=lambda x: (x[3], x[1]), reverse=True)

    # 8. Build facets from ALL scored results (before slicing)
    facets = _build_facets(scored)

    # 9. Timing
    search_time_ms = round((time.perf_counter() - t0) * 1000, 1)

    # 10. Build response
    results = [
        SearchResult(
            product=product,
            score=round(score, 3),
            reasons=reasons[:5],
            highlight_title=_highlight_title(product.title, highlight_tokens),
        )
        for product, score, reasons, _pers in scored[:limit]
    ]

    response = SearchResponse(
        query=query,
        corrected_query=corrected_query,
        typo_corrected=typo_corrected,
        expanded_terms=expanded_terms[:10],
        total=len(results),
        personalized=bool(profile and profile.total_events > 0),
        mode=mode,
        semantic_backend="sentence-transformers" if semantic_categories else "fts5-bm25",
        reranker_backend="personalization" if profile and profile.total_events > 0 else "bm25",
        search_time_ms=search_time_ms,
        facets=facets,
        items=results,
    )

    # Store in cache (evict oldest if full)
    if len(_search_cache) >= _SEARCH_CACHE_MAX:
        oldest_key = next(iter(_search_cache))
        del _search_cache[oldest_key]
    _search_cache[cache_key] = response

    return response
