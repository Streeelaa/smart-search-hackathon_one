from app.ltr import extract_features, ltr_ranker
from app.repository import repository
from app.reranker import reranker
from app.schemas import Product, SearchMode, SearchResponse, SearchResult, UserProfile
from app.semantic import semantic_engine
from app.synonyms import expand_terms_with_synonyms
from app.text_processing import correct_tokens, normalize_query, normalize_text, normalize_tokens


def build_vocabulary(products: list[Product]) -> set[str]:
    vocabulary: set[str] = set()
    for product in products:
        chunks = [
            product.title,
            product.category,
            product.description,
            *product.tags,
            *product.aliases,
            *product.attributes.values(),
        ]
        for chunk in chunks:
            vocabulary.update(normalize_query(chunk))
    return vocabulary


def expand_terms(tokens: list[str]) -> list[str]:
    return expand_terms_with_synonyms(tokens)


def product_fields(product: Product) -> dict[str, list[str]]:
    return {
        "title": normalize_query(product.title),
        "category": normalize_query(product.category),
        "description": normalize_query(product.description),
        "tags": normalize_tokens(product.tags),
        "aliases": normalize_tokens(product.aliases),
        "attributes": normalize_tokens(list(product.attributes.values())),
    }


def lexical_score(product: Product, terms: list[str]) -> tuple[float, list[str]]:
    fields = product_fields(product)
    text = set(
        fields["title"]
        + fields["category"]
        + fields["description"]
        + fields["tags"]
        + fields["aliases"]
        + fields["attributes"]
    )
    reasons: list[str] = []
    score = 0.0

    for term in terms:
        if term in fields["title"]:
            score += 3.0
            reasons.append(f"Совпадение в названии: {term}")
        elif term in fields["aliases"]:
            score += 2.7
            reasons.append(f"Совпадение по синониму: {term}")
        elif term in fields["category"]:
            score += 2.5
            reasons.append(f"Совпадение по категории: {term}")
        elif term in fields["tags"]:
            score += 2.0
            reasons.append(f"Совпадение по тегу: {term}")
        elif term in fields["attributes"]:
            score += 1.7
            reasons.append(f"Совпадение по атрибуту: {term}")
        elif term in text:
            score += 1.0
            reasons.append(f"Совпадение в описании: {term}")

    if terms:
        title_phrase = normalize_text(product.title)
        query_phrase = " ".join(terms)
        if query_phrase and query_phrase in title_phrase:
            score += 2.0
            reasons.append("Совпадение фразы в названии")

    return score, reasons


def personalization_score(product: Product, profile: UserProfile | None) -> tuple[float, list[str]]:
    if profile is None or profile.total_events == 0:
        return 0.0, []

    score = 0.0
    reasons: list[str] = []

    category_score = profile.category_affinity.get(product.category, 0.0)
    if category_score:
        score += category_score
        reasons.append(f"Категория релевантна истории пользователя: {product.category}")

    shared_tags = [tag for tag in product.tags if tag in profile.tag_affinity]
    if shared_tags:
        tag_score = sum(profile.tag_affinity[tag] for tag in shared_tags) * 0.25
        score += tag_score
        reasons.append(f"Теги совпадают с интересами пользователя: {', '.join(shared_tags[:3])}")

    if profile.recent_queries:
        recent_terms = set(normalize_query(" ".join(profile.recent_queries[-3:])))
        product_terms = set(product_fields(product)["title"] + product_fields(product)["tags"])
        overlap = recent_terms & product_terms
        if overlap:
            score += min(1.5, len(overlap) * 0.5)
            reasons.append(f"Похоже на недавние запросы пользователя: {', '.join(sorted(overlap)[:3])}")

    if profile.average_price is not None:
        distance = abs(product.price - profile.average_price)
        price_score = max(0.0, 2.0 - distance / max(profile.average_price, 1.0))
        if price_score > 0:
            score += price_score
            reasons.append("Цена близка к историческим закупкам")

    return score, reasons


def semantic_scores_for_query(query: str, limit: int) -> dict[int, float]:
    return dict(semantic_engine.search(query=query, limit=limit))


def apply_result_cutoff(reranked: list[tuple[Product, float, list[str]]], mode: SearchMode) -> list[tuple[Product, float, list[str]]]:
    if not reranked:
        return []

    top_score = reranked[0][1]
    if mode == "keyword":
        threshold = max(1.0, top_score * 0.15)
    elif mode == "semantic":
        threshold = max(0.9, top_score * 0.3)
    else:
        threshold = max(1.2, top_score * 0.25)

    filtered = [item for item in reranked if item[1] >= threshold]
    return filtered


def search_products(query: str, limit: int = 10, user_id: str | None = None, mode: SearchMode = "hybrid") -> SearchResponse:
    tokens = normalize_query(query)
    vocabulary = build_vocabulary(repository.products)
    corrected_tokens, _ = correct_tokens(tokens, vocabulary)
    corrected_query = " ".join(corrected_tokens)
    expanded_terms = expand_terms(corrected_tokens)
    semantic_query = corrected_query or query
    semantic_scores = semantic_scores_for_query(semantic_query, limit=limit) if mode in {"semantic", "hybrid"} else {}

    profile = repository.get_user_profile(user_id) if user_id else None
    lexical_candidates: dict[int, tuple[float, list[str]]] = {}
    if mode in {"keyword", "hybrid"}:
        for product in repository.products:
            base_score, base_reasons = lexical_score(product, expanded_terms)
            if base_score > 0:
                lexical_candidates[product.id] = (base_score, base_reasons)

    candidate_ids = set(lexical_candidates) | set(semantic_scores)
    candidates_for_rerank: list[tuple[Product, float, list[str]]] = []
    for product in repository.products:
        if product.id not in candidate_ids:
            continue

        base_score, base_reasons = lexical_candidates.get(product.id, (0.0, []))
        dense_score = semantic_scores.get(product.id, 0.0)
        if mode == "keyword" and base_score <= 0:
            continue
        if mode == "semantic" and dense_score <= 0:
            continue
        if mode == "hybrid" and base_score <= 0 and dense_score <= 0:
            continue

        personal_score, personal_reasons = personalization_score(product, profile)
        semantic_component = 0.0
        semantic_reasons: list[str] = []
        if dense_score > 0:
            semantic_component = dense_score * 4.0
            semantic_reasons.append(f"Семантическая близость запроса и товара: {dense_score:.3f}")

        if mode == "keyword":
            final_score = base_score + personal_score
        elif mode == "semantic":
            final_score = semantic_component + personal_score
        else:
            final_score = base_score + semantic_component + personal_score

        deduped_reasons = list(dict.fromkeys(base_reasons + semantic_reasons + personal_reasons))
        candidates_for_rerank.append((product, final_score, deduped_reasons[:6]))

    reranked = reranker.rerank(query=semantic_query, candidates=candidates_for_rerank, top_k=limit)

    # LightGBM learned-to-rank boost (if model is available)
    if ltr_ranker.ready and reranked:
        import numpy as np
        query_tokens = normalize_query(corrected_query or query)
        features_list = []
        for product, score, reasons in reranked:
            lex_sc = lexical_candidates.get(product.id, (0.0, []))[0]
            sem_sc = semantic_scores.get(product.id, 0.0)
            pers_sc, _ = personalization_score(product, profile)
            feat = extract_features(product, query_tokens, lex_sc, sem_sc, pers_sc, profile)
            features_list.append(feat)
        ltr_scores = ltr_ranker.predict(np.array(features_list, dtype=np.float32))
        reranked_with_ltr = []
        for (product, base_score, reasons), ltr_sc in zip(reranked, ltr_scores, strict=True):
            boosted = base_score + float(ltr_sc) * 2.0
            updated_reasons = reasons + [f"LTR boost: {float(ltr_sc):.2f}"]
            reranked_with_ltr.append((product, boosted, updated_reasons))
        reranked_with_ltr.sort(key=lambda item: item[1], reverse=True)
        reranked = reranked_with_ltr

    reranked = apply_result_cutoff(reranked, mode=mode)
    results: list[SearchResult] = [
        SearchResult(product=product, score=round(score, 3), reasons=reasons[:5])
        for product, score, reasons in reranked
    ]

    return SearchResponse(
        query=query,
        corrected_query=corrected_query,
        expanded_terms=expanded_terms,
        total=len(results),
        personalized=bool(profile and profile.total_events > 0),
        mode=mode,
        semantic_backend=semantic_engine.status().backend if mode in {"semantic", "hybrid"} else None,
        reranker_backend=reranker.status().backend,
        items=results,
    )