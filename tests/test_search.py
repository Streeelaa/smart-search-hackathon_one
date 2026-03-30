"""Tests for the smart search pipeline."""
import json
from pathlib import Path

import pytest

from app.catalog_loader import load_catalog
from app.repository import InMemoryRepository
from app.schemas import EventCreate, Product, SearchMode
from app.search import (
    build_vocabulary,
    expand_terms,
    lexical_score,
    personalization_score,
    search_products,
)
from app.synonyms import expand_terms_with_synonyms, get_synonym_map
from app.text_processing import (
    correct_tokens,
    normalize_query,
    normalize_text,
    normalize_token,
    tokenize,
)


# ---------------------------------------------------------------------------
# text_processing
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_basic_latin(self):
        assert tokenize("Hello World") == ["hello", "world"]

    def test_cyrillic(self):
        assert tokenize("Ноутбук Lenovo") == ["ноутбук", "lenovo"]

    def test_mixed(self):
        tokens = tokenize("МФУ HP-2050, цена 12500₽")
        assert "мфу" in tokens
        assert "hp" in tokens
        assert "2050" in tokens
        assert "12500" in tokens

    def test_empty(self):
        assert tokenize("") == []
        assert tokenize("   !!!   ") == []


class TestNormalizeToken:
    def test_morph_normalization(self):
        # pymorphy3 should normalize to a base form
        result = normalize_token("ноутбуки")
        assert result in ("ноутбук", "ноутбуки", "ноутбука"), f"Unexpected: {result}"

    def test_latin_passthrough(self):
        assert normalize_token("lenovo") == "lenovo"

    def test_number_passthrough(self):
        assert normalize_token("12345") == "12345"

    def test_empty(self):
        assert normalize_token("") == ""


class TestNormalizeQuery:
    def test_basic(self):
        result = normalize_query("Ноутбуки для офиса")
        assert len(result) >= 2
        # check some form of the words exists
        joined = " ".join(result)
        assert "офис" in joined or "офиса" in joined

    def test_preserves_order(self):
        result = normalize_query("системный блок")
        assert len(result) == 2


class TestCorrectTokens:
    def test_known_word_unchanged(self):
        vocab = {"монитор", "ноутбук", "принтер"}
        corrected, changed = correct_tokens(["монитор"], vocab)
        assert corrected == ["монитор"]
        assert not changed

    def test_typo_correction(self):
        vocab = {"монитор", "ноутбук", "принтер"}
        corrected, changed = correct_tokens(["монитр"], vocab)
        assert "монитор" in corrected
        assert changed

    def test_short_words_skip(self):
        vocab = {"монитор"}
        corrected, changed = correct_tokens(["для"], vocab)
        assert corrected == ["для"]
        assert not changed


# ---------------------------------------------------------------------------
# synonyms
# ---------------------------------------------------------------------------

class TestSynonyms:
    def test_synonym_map_not_empty(self):
        syn_map = get_synonym_map()
        assert len(syn_map) > 50, "Expected at least 50 synonym groups"

    def test_expand_systemnik(self):
        expanded = expand_terms_with_synonyms(["системник"])
        lower = [t.lower() for t in expanded]
        assert any("системный" in t or "системн" in t for t in lower) or any("пк" in t for t in lower), \
            f"Expected 'системный блок' or 'пк' in expanded: {expanded}"

    def test_expand_unknown_word(self):
        expanded = expand_terms_with_synonyms(["xyzqwerty123"])
        assert len(expanded) == 1  # just the original

    def test_expand_mfu(self):
        expanded = expand_terms_with_synonyms(["мфу"])
        assert len(expanded) > 1, "МФУ should expand to multiple terms"


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------

class TestCatalog:
    def test_catalog_file_valid_json(self):
        catalog_path = Path(__file__).parent.parent / "data" / "catalog.json"
        with catalog_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) >= 100, f"Expected at least 100 products, got {len(data)}"

    def test_catalog_products_have_required_fields(self):
        catalog_path = Path(__file__).parent.parent / "data" / "catalog.json"
        with catalog_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            product = Product(**item)
            assert product.id > 0
            assert len(product.title) > 0
            assert len(product.category) > 0
            assert product.price >= 0

    def test_load_catalog(self):
        products = load_catalog()
        assert len(products) >= 100


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestBuildVocabulary:
    def test_vocabulary_nonempty(self):
        products = load_catalog()
        vocab = build_vocabulary(products)
        assert len(vocab) > 100

    def test_vocabulary_contains_common_terms(self):
        products = load_catalog()
        vocab = build_vocabulary(products)
        # at least one of these should be in the vocabulary
        assert any(t in vocab for t in ["ноутбук", "монитор", "принтер", "бумага"])


class TestLexicalScore:
    def test_matching_title(self):
        product = Product(id=1, sku="T001", title="Ноутбук Lenovo ThinkPad", category="ноутбуки", description="Ноутбук для офиса", price=50000.0, tags=["ноутбук", "lenovo"])
        score, reasons = lexical_score(product, ["ноутбук"])
        assert score > 0
        assert len(reasons) > 0

    def test_zero_for_unrelated(self):
        product = Product(id=1, sku="T001", title="Шкаф офисный", category="мебель", description="Мебель", price=10000.0)
        score, reasons = lexical_score(product, ["ноутбук"])
        assert score == 0.0


class TestSearchProducts:
    def test_basic_search_returns_results(self):
        response = search_products(query="ноутбук", limit=5, mode="keyword")
        assert response.total > 0
        assert len(response.items) <= 5

    def test_typo_search(self):
        response = search_products(query="монитр", limit=5, mode="hybrid")
        assert response.corrected_query != "монитр", "Expected correction of 'монитр'"
        assert response.total > 0

    def test_synonym_expansion(self):
        response = search_products(query="системник", limit=5, mode="hybrid")
        assert len(response.expanded_terms) > 1, "Expected synonym expansion for 'системник'"
        assert response.total > 0

    def test_empty_query_no_crash(self):
        response = search_products(query="", limit=5, mode="keyword")
        assert response.total == 0

    def test_hybrid_mode(self):
        response = search_products(query="принтер для офиса", limit=5, mode="hybrid")
        assert response.mode == "hybrid"

    def test_personalization_flag(self):
        # without user
        response_anon = search_products(query="ноутбук", limit=5, user_id=None, mode="keyword")
        assert not response_anon.personalized


# ---------------------------------------------------------------------------
# events & sample data
# ---------------------------------------------------------------------------

class TestSampleEvents:
    def test_events_file_valid_json(self):
        events_path = Path(__file__).parent.parent / "data" / "sample_events.json"
        with events_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) >= 100, f"Expected at least 100 events, got {len(data)}"

    def test_events_have_required_fields(self):
        events_path = Path(__file__).parent.parent / "data" / "sample_events.json"
        with events_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data[:20]:
            assert "user_id" in item
            assert "event_type" in item
            assert item["event_type"] in ("click", "search", "favorite", "purchase")


# ---------------------------------------------------------------------------
# evaluation cases
# ---------------------------------------------------------------------------

class TestEvaluationCases:
    def test_cases_count(self):
        from app.evaluation import EVALUATION_CASES
        assert len(EVALUATION_CASES) >= 15, f"Expected at least 15 cases, got {len(EVALUATION_CASES)}"

    def test_demo_scenarios_count(self):
        from app.demo_scenarios import get_demo_scenarios
        scenarios = get_demo_scenarios()
        assert len(scenarios) >= 5
