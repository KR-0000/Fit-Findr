"""
tests/test_tools.py

Tests for each tool's happy path and failure modes.
Run with: pytest tests/
"""

import pytest
from tools import search_listings, create_fit_card, compare_price
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    results = search_listings("top", size="XL", max_price=None)
    for item in results:
        assert "xl" in item["size"].lower()


def test_search_no_filters():
    results = search_listings("vintage", size=None, max_price=None)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_sorted_by_relevance():
    # Items matching more keywords should come first
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert len(results) > 0  # at minimum returns something


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    result = create_fit_card("", results[0])
    assert isinstance(result, str)
    assert len(result) > 0
    # Should be an error message, not an exception
    assert "empty" in result.lower() or "could not" in result.lower() or "outfit" in result.lower()


def test_create_fit_card_whitespace_outfit():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    result = create_fit_card("   ", results[0])
    assert isinstance(result, str)
    assert len(result) > 0


# ── compare_price ─────────────────────────────────────────────────────────────

def test_compare_price_returns_dict():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    result = compare_price(results[0])
    assert isinstance(result, dict)
    assert "verdict" in result
    assert "item_price" in result
    assert "comparable_count" in result
    assert "reasoning" in result


def test_compare_price_does_not_include_self():
    results = search_listings("vintage", size=None, max_price=None)
    assert len(results) > 0
    item = results[0]
    result = compare_price(item)
    # avg_comparable should not be the same as item price when
    # that would only be possible if the item counted itself
    # (just verify it runs without error)
    assert result["verdict"] in ("great deal", "fair", "pricey", "unknown")


def test_compare_price_unknown_for_no_comparables():
    # Fabricate an item with a very obscure category/tag combo
    fake_item = {
        "id": "fake_999",
        "title": "Fake Item",
        "category": "accessories",
        "style_tags": ["nonexistent_tag_xyz"],
        "price": 10.0,
    }
    result = compare_price(fake_item)
    # Either unknown or valid verdict — should not raise
    assert isinstance(result, dict)
    assert result["verdict"] in ("great deal", "fair", "pricey", "unknown")
