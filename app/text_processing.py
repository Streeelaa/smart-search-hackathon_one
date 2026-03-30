from functools import lru_cache
import re
from difflib import get_close_matches

try:
    from rapidfuzz import process as rapidfuzz_process
except ImportError:  # pragma: no cover
    rapidfuzz_process = None

try:
    import pymorphy3
except ImportError:  # pragma: no cover
    pymorphy3 = None


TOKEN_PATTERN = re.compile(r"[a-zA-Zа-яА-Я0-9]+")


if pymorphy3 is not None:
    _morph = pymorphy3.MorphAnalyzer()
else:  # pragma: no cover
    _morph = None


def normalize_text(value: str) -> str:
    return " ".join(tokenize(value))


def tokenize(value: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(value)]


@lru_cache(maxsize=4096)
def normalize_token(token: str) -> str:
    if not token:
        return token
    if _morph is None or not token.isalpha():
        return token.lower()
    parsed = _morph.parse(token.lower())
    if not parsed:
        return token.lower()
    return parsed[0].normal_form


def normalize_tokens(tokens: list[str]) -> list[str]:
    return [normalize_token(token) for token in tokens if token]


def normalize_query(value: str) -> list[str]:
    return normalize_tokens(tokenize(value))


def correct_tokens(tokens: list[str], vocabulary: set[str]) -> tuple[list[str], bool]:
    corrected: list[str] = []
    changed = False
    for token in tokens:
        if token in vocabulary or len(token) < 4:
            corrected.append(token)
            continue

        match = find_best_match(token, vocabulary)
        if match and match != token:
            corrected.append(match)
            changed = True
        else:
            corrected.append(token)

    return corrected, changed


def find_best_match(token: str, vocabulary: set[str]) -> str | None:
    if rapidfuzz_process is not None:
        match = rapidfuzz_process.extractOne(token, list(vocabulary), score_cutoff=78)
        if match is not None:
            return str(match[0])

    fallback = get_close_matches(token, vocabulary, n=1, cutoff=0.75)
    return fallback[0] if fallback else None