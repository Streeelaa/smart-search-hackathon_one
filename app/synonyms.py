import json
from functools import lru_cache
from pathlib import Path

from app.text_processing import normalize_query, normalize_text


BASE_DIR = Path(__file__).resolve().parent.parent
SYNONYMS_FILE = BASE_DIR / "data" / "synonyms.json"


@lru_cache(maxsize=1)
def load_synonyms() -> dict[str, list[str]]:
    with SYNONYMS_FILE.open("r", encoding="utf-8") as file:
        raw_synonyms = json.load(file)

    normalized_map: dict[str, list[str]] = {}
    for key, values in raw_synonyms.items():
        normalized_key = normalize_text(key)
        ordered_values: list[str] = []
        seen: set[str] = {normalized_key}
        for value in values:
            normalized_value = normalize_text(value)
            if not normalized_value or normalized_value in seen:
                continue
            seen.add(normalized_value)
            ordered_values.append(normalized_value)
        normalized_map[normalized_key] = ordered_values

    return normalized_map


def expand_terms_with_synonyms(tokens: list[str]) -> list[str]:
    synonyms = load_synonyms()
    expanded: list[str] = []
    for token in tokens:
        normalized_token = normalize_text(token)
        if not normalized_token:
            continue
        expanded.append(normalized_token)
        expanded.extend(synonyms.get(normalized_token, []))

    ordered_terms: list[str] = []
    seen: set[str] = set()
    for term in expanded:
        normalized_terms = normalize_query(term)
        if not normalized_terms:
            continue
        normalized_term = " ".join(normalized_terms)
        if normalized_term in seen:
            continue
        seen.add(normalized_term)
        ordered_terms.append(normalized_term)

    return ordered_terms


def get_synonym_map() -> dict[str, list[str]]:
    return load_synonyms()