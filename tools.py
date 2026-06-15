"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    listings = load_listings()

    # Filter by price
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Filter by size (case-insensitive, partial match)
    if size is not None:
        size_lower = size.lower()
        listings = [
            l for l in listings
            if size_lower in l["size"].lower()
        ]

    # Tokenize description into keywords
    tokens = set(re.sub(r"[^\w\s]", " ", description.lower()).split())

    def score(listing):
        searchable = " ".join([
            listing["title"],
            listing.get("description", ""),
            listing["category"],
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
            listing.get("brand") or "",
        ]).lower()
        return sum(1 for token in tokens if token in searchable)

    scored = [(l, score(l)) for l in listings]
    scored = [(l, s) for l, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [l for l, _ in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions. If wardrobe is empty,
        returns general styling advice instead of crashing.
    """
    try:
        client = _get_groq_client()
        items = wardrobe.get("items", [])

        item_summary = (
            f"Title: {new_item.get('title')}\n"
            f"Description: {new_item.get('description')}\n"
            f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
            f"Colors: {', '.join(new_item.get('colors', []))}\n"
            f"Price: ${new_item.get('price')}\n"
            f"Platform: {new_item.get('platform')}"
        )

        if not items:
            prompt = (
                f"I'm considering buying this secondhand item:\n\n{item_summary}\n\n"
                "The user has no wardrobe saved yet. Give 1-2 general outfit ideas — "
                "describe what types of items pair well with this piece, what vibe it suits, "
                "and one specific way to wear it. Keep it casual and specific."
            )
        else:
            wardrobe_lines = "\n".join(
                f"- {it['name']} ({it['category']}): colors={', '.join(it.get('colors', []))}, "
                f"tags={', '.join(it.get('style_tags', []))}"
                + (f", notes: {it['notes']}" if it.get("notes") else "")
                for it in items
            )
            prompt = (
                f"I'm considering buying this secondhand item:\n\n{item_summary}\n\n"
                f"Here is the user's current wardrobe:\n{wardrobe_lines}\n\n"
                "Suggest 1-2 complete outfit combinations using the new item and specific "
                "named pieces from the wardrobe above. Reference the wardrobe items by name. "
                "Keep it casual, practical, and style-specific."
            )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip() or "No suggestion returned."

    except Exception as e:
        return (
            f"Could not generate outfit suggestion ({e}). "
            "As a general tip: this item pairs well with neutral basics and accessories "
            "that complement its color palette."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message string.
    """
    if not outfit or not outfit.strip():
        return (
            "Could not generate a fit card: the outfit suggestion was empty. "
            "Run suggest_outfit first and pass its result here."
        )

    try:
        client = _get_groq_client()

        title = new_item.get("title", "thrifted find")
        price = new_item.get("price", "")
        platform = new_item.get("platform", "a thrift platform")
        tags = ", ".join(new_item.get("style_tags", []))

        prompt = (
            f"Write a 2-4 sentence Instagram/TikTok OOTD caption for this outfit.\n\n"
            f"Thrifted item: {title} — ${price} on {platform}\n"
            f"Style tags: {tags}\n"
            f"Outfit idea: {outfit}\n\n"
            "Rules: all lowercase, casual and authentic tone (like a real person posting), "
            "mention the item name once, mention the price once, mention the platform once, "
            "end with exactly one emoji. No hashtags."
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.95,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip() or "No caption returned."

    except Exception as e:
        truncated = outfit[:150] + "..." if len(outfit) > 150 else outfit
        return (
            f"Could not generate fit card ({e}). "
            f"Outfit summary: {truncated}"
        )


# ── Tool 4 (stretch): compare_price ──────────────────────────────────────────

def compare_price(item: dict, all_listings: list[dict] | None = None) -> dict:
    """
    Estimate whether an item's price is fair relative to comparable listings.

    Args:
        item:         The listing dict to evaluate.
        all_listings: Full listings dataset. If None, loads from disk.

    Returns:
        A dict with keys: verdict, item_price, avg_comparable,
        comparable_count, reasoning.
    """
    try:
        if all_listings is None:
            all_listings = load_listings()

        item_id = item.get("id")
        item_price = item.get("price", 0)
        category = item.get("category")
        item_tags = set(item.get("style_tags", []))

        comparables = [
            l for l in all_listings
            if l.get("id") != item_id
            and l.get("category") == category
            and item_tags & set(l.get("style_tags", []))
        ]

        if not comparables:
            return {
                "verdict": "unknown",
                "item_price": item_price,
                "avg_comparable": None,
                "comparable_count": 0,
                "reasoning": f"No comparable listings found in category '{category}' with overlapping style tags.",
            }

        avg = sum(l["price"] for l in comparables) / len(comparables)
        ratio = item_price / avg

        if ratio < 0.80:
            verdict = "great deal"
        elif ratio <= 1.20:
            verdict = "fair"
        else:
            verdict = "pricey"

        return {
            "verdict": verdict,
            "item_price": item_price,
            "avg_comparable": round(avg, 2),
            "comparable_count": len(comparables),
            "reasoning": (
                f"${item_price:.2f} vs avg ${avg:.2f} across {len(comparables)} comparable item(s). "
                f"Ratio: {ratio:.0%}."
            ),
        }

    except Exception as e:
        return {
            "verdict": "unknown",
            "item_price": item.get("price"),
            "avg_comparable": None,
            "comparable_count": 0,
            "reasoning": f"Price comparison failed: {e}",
        }
