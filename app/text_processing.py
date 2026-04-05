from functools import lru_cache
import re
from difflib import SequenceMatcher, get_close_matches

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
        if token in vocabulary or len(token) < 3:
            corrected.append(token)
            continue
        if _looks_like_catalog_prefix(token, vocabulary):
            corrected.append(token)
            continue
        # Also check normalized form
        normed = normalize_token(token)
        if normed in vocabulary:
            corrected.append(normed)
            if normed != token:
                changed = True
            continue

        # Check manual corrections for common misspellings — check BOTH original and normed
        if token in _MANUAL_CORRECTIONS:
            corrected.append(_MANUAL_CORRECTIONS[token])
            changed = True
            continue
        if normed in _MANUAL_CORRECTIONS:
            corrected.append(_MANUAL_CORRECTIONS[normed])
            changed = True
            continue

        direct_match = _find_transposition_match(token, vocabulary)
        if direct_match is None and normed != token:
            direct_match = _find_transposition_match(normed, vocabulary)
        if direct_match is not None:
            corrected.append(direct_match)
            changed = direct_match != token or changed
            continue

        # If pymorphy3 recognizes the word with HIGH confidence AND it's in a real
        # dictionary (not just guessing), keep it. Use stricter threshold to avoid
        # blocking legitimate typo corrections.
        if _morph is not None and token.isalpha():
            parsed = _morph.parse(token)
            # Only trust pymorphy3 if the word is actually known (not just hypothesized)
            # Check that best parse has high score AND a known lexeme
            if parsed and parsed[0].score >= 0.7 and 'UNKN' not in str(parsed[0].tag):
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
    "мониор": "монитор",
    "нотубук": "ноутбук",
    "натубук": "ноутбук",
    "нотбук": "ноутбук",
    "ноутук": "ноутбук",
    "картрдж": "картридж",
    "картирдж": "картридж",
    "картрридж": "картридж",
    "клвиатура": "клавиатура",
    "клавитура": "клавиатура",
    "корпьютер": "компьютер",
    "компютер": "компьютер",
    "кампьютер": "компьютер",
    "компютор": "компьютер",
    "принтр": "принтер",
    "прнтер": "принтер",
    "пинтер": "принтер",
    "перчтки": "перчатки",
    "перчатка": "перчатки",
    "пречатки": "перчатки",
    "маслр": "масло",
    "масла": "масло",
    "шпиц": "шприц",
    "шрпиц": "шприц",
    "филтр": "фильтр",
    "фльтр": "фильтр",
    "бмага": "бумага",
    "бумга": "бумага",
    "тарелка": "тарелка",
    "скнер": "сканер",
    "сканнер": "сканер",
    "кртридж": "картридж",
    "тонир": "тонер",
    "тоннер": "тонер",
    "маркр": "маркер",
    "степлр": "степлер",
    "калькулятр": "калькулятор",
    "дыракол": "дырокол",
    "антисиптик": "антисептик",
    "антиспетик": "антисептик",
    "стетаскоп": "стетоскоп",
    "тармометр": "термометр",
    "тонометор": "тонометр",
    "полатенце": "полотенце",
    "палатенце": "полотенце",
    "салветка": "салфетка",
    "салфтка": "салфетка",
    "ватрушка": "ватрушка",
    # Protected words — should NOT be corrected
    "канцтовары": "канцтовары",
    "канцелярия": "канцелярия",
    "автозапчасти": "автозапчасти",
    "медикаменты": "медикаменты",
    "стройматериалы": "стройматериалы",
    "спецодежда": "спецодежда",
    "хозтовары": "хозтовары",
    "лэптоп": "лэптоп",
    "оргтехника": "оргтехника",
}


# Pre-filtered vocabulary caches for fast lookup
_vocab_by_prefix: dict[str, list[str]] = {}
_find_best_match_cache: dict[str, str | None] = {}
_prefix_intent_cache: dict[str, bool] = {}


def _is_reasonable_correction(token: str, candidate: str) -> bool:
    """Reject fuzzy matches that collapse a full token into a short fragment."""
    if not candidate or candidate == token:
        return bool(candidate)
    if len(token) >= 4 and len(candidate) < 3:
        return False
    if len(candidate) + 2 < len(token):
        return False
    if token[:1] != candidate[:1]:
        return False

    similarity = SequenceMatcher(None, token, candidate).ratio()
    min_similarity = 0.72 if len(token) <= 4 else 0.76
    if len(candidate) < len(token):
        min_similarity += 0.05
    return similarity >= min_similarity


def _looks_like_catalog_prefix(token: str, vocabulary: set[str]) -> bool:
    """Treat short catalog prefixes as valid user intent, not as typos."""
    if len(token) < 4:
        return False
    if token in _prefix_intent_cache:
        return _prefix_intent_cache[token]

    prefix_pool = _get_prefix_vocab(token[:2], vocabulary)
    matches = 0
    for word in prefix_pool:
        if len(word) <= len(token):
            continue
        if word.startswith(token):
            matches += 1
            if matches >= 2:
                _prefix_intent_cache[token] = True
                return True

    _prefix_intent_cache[token] = False
    return False


def _get_prefix_vocab(prefix: str, vocabulary: set[str]) -> list[str]:
    """Get vocabulary subset with same first 2 chars for faster fuzzy matching."""
    if prefix not in _vocab_by_prefix:
        _vocab_by_prefix[prefix] = [w for w in vocabulary if w.startswith(prefix)]
    return _vocab_by_prefix[prefix]


def _find_transposition_match(token: str, vocabulary: set[str]) -> str | None:
    """Fix one adjacent swap directly before falling back to fuzzy matching."""
    if len(token) < 4:
        return None
    for i in range(len(token) - 1):
        if token[i] == token[i + 1]:
            continue
        swapped = token[:i] + token[i + 1] + token[i] + token[i + 2:]
        if swapped in vocabulary:
            return swapped
        swapped_norm = normalize_token(swapped)
        if swapped_norm in vocabulary:
            return swapped_norm
    return None


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

    # Strategy 3: try swapping first two chars (covers transposition typos)
    if len(token) >= 2:
        swapped = token[1] + token[0] + token[2:]
        candidates_set.update(_get_prefix_vocab(swapped[:2], vocabulary))
    
    # Filter by similar length (±3 chars to be more generous)
    tlen = len(token)
    candidates = [
        w
        for w in candidates_set
        if abs(len(w) - tlen) <= 3
        and not (tlen >= 4 and len(w) < 3)
    ]
    
    if not candidates:
        _find_best_match_cache[token] = None
        return None

    if rapidfuzz_process is not None:
        match = rapidfuzz_process.extractOne(token, candidates, score_cutoff=65)
        if match is not None:
            result = str(match[0])
            if _is_reasonable_correction(token, result):
                _find_best_match_cache[token] = result
                return result

    fallback = get_close_matches(token, candidates, n=1, cutoff=0.70)
    result = fallback[0] if fallback else None
    if result is not None and not _is_reasonable_correction(token, result):
        result = None
    _find_best_match_cache[token] = result
    return result
