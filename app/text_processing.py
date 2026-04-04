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
        # Also check normalized form
        normed = normalize_token(token)
        if normed in vocabulary:
            corrected.append(normed)
            if normed != token:
                changed = True
            continue

        # Check manual corrections for common misspellings
        if normed in _MANUAL_CORRECTIONS:
            corrected.append(_MANUAL_CORRECTIONS[normed])
            changed = True
            continue

        # If pymorphy3 recognizes the word with good confidence, keep it
        # (prevents correcting valid words like "шпиц" that aren't in product vocab)
        if _morph is not None and token.isalpha():
            parsed = _morph.parse(token)
            if parsed and parsed[0].score >= 0.3:
                corrected.append(token)
                continue

        match = find_best_match(token, vocabulary)
        if match and match != token:
            corrected.append(match)
            changed = True
        else:
            corrected.append(token)

    return corrected, changed


# Manual corrections for common misspellings that fuzzy matching cannot handle
_MANUAL_CORRECTIONS: dict[str, str] = {
    "мантор": "монитор",
    "маниор": "монитор",
    "минотор": "монитор",
    "нотубук": "ноутбук",
    "натубук": "ноутбук",
    "картрдж": "картридж",
    "картирдж": "картридж",
    "клвиатура": "клавиатура",
    "корпьютер": "компьютер",
    "компютер": "компьютер",
}


# Pre-filtered vocabulary caches for fast lookup
_vocab_by_prefix: dict[str, list[str]] = {}
_find_best_match_cache: dict[str, str | None] = {}


def _get_prefix_vocab(prefix: str, vocabulary: set[str]) -> list[str]:
    """Get vocabulary subset with same first 2 chars for faster fuzzy matching."""
    if prefix not in _vocab_by_prefix:
        _vocab_by_prefix[prefix] = [w for w in vocabulary if w.startswith(prefix)]
    return _vocab_by_prefix[prefix]


def find_best_match(token: str, vocabulary: set[str]) -> str | None:
    if len(token) < 3:
        return None

    # Check cache first (vocabulary is stable at runtime)
    if token in _find_best_match_cache:
        return _find_best_match_cache[token]
    
    # Build candidate set from multiple prefix strategies
    candidates_set: set[str] = set()
    
    # Strategy 1: same first 2 chars (covers most typos)
    prefix = token[:2]
    candidates_set.update(_get_prefix_vocab(prefix, vocabulary))
    
    # Strategy 2: same first char (covers typos in second char, e.g. "мантор"→"монитор")
    prefix1 = token[:1]
    for w in _get_prefix_vocab(prefix1, vocabulary):
        candidates_set.add(w)
    
    # Filter by similar length (±3 chars to be more generous)
    tlen = len(token)
    candidates = [w for w in candidates_set if abs(len(w) - tlen) <= 3]
    
    if not candidates:
        _find_best_match_cache[token] = None
        return None

    if rapidfuzz_process is not None:
        match = rapidfuzz_process.extractOne(token, candidates, score_cutoff=70)
        if match is not None:
            result = str(match[0])
            _find_best_match_cache[token] = result
            return result

    fallback = get_close_matches(token, candidates, n=1, cutoff=0.75)
    result = fallback[0] if fallback else None
    _find_best_match_cache[token] = result
    return result