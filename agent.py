"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card, compare_price


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "price_assessment": None,
        "retry_attempted": False,
        "retry_note": None,
        "error": None,
    }


def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.

    Uses regex to pull out:
    - max_price: "under $30", "less than $40", "$25 max"
    - size: "size M", "in size S", "XS", "XL", "size 8", etc.
    - description: everything remaining after removing price/size tokens
    """
    text = query

    # Extract max_price
    max_price = None
    price_match = re.search(
        r"(?:under|less than|below|max|up to)?\s*\$(\d+(?:\.\d+)?)",
        text, re.IGNORECASE
    )
    if price_match:
        max_price = float(price_match.group(1))
        text = text[:price_match.start()] + text[price_match.end():]

    # Extract size
    size = None
    size_match = re.search(
        r"\b(?:size\s+)?([Xx]{1,2}[Ss]|[Xx]{1,2}[Ll]|[Xx][Ll]{2}|[Ss]\/[Mm]|[Mm]\/[Ll]|[Ss]|[Mm]|[Ll]|size\s+\d+|\d+)\b",
        text, re.IGNORECASE
    )
    if size_match:
        size = size_match.group(1).strip()
        text = text[:size_match.start()] + text[size_match.end():]

    # Clean up description
    description = re.sub(r"\s+", " ", text).strip(" ,.-")

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        Session dict. Check session["error"] first — if set, interaction ended
        early and outfit_suggestion / fit_card will be None.
    """
    session = _new_session(query, wardrobe)

    # Step 1: Parse query
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 2: Search listings with retry logic
    results = search_listings(description, size, max_price)
    session["search_results"] = results

    if not results and (size is not None or max_price is not None):
        # Retry 1: remove size filter, raise price ceiling 50%
        relaxed_price = (max_price * 1.5) if max_price else None
        results = search_listings(description, size=None, max_price=relaxed_price)
        if results:
            session["retry_attempted"] = True
            parts = []
            if size:
                parts.append("removed size filter")
            if max_price:
                parts.append(f"raised price to ${relaxed_price:.0f}")
            session["retry_note"] = "Loosened search constraints: " + " and ".join(parts) + "."
            session["search_results"] = results
        else:
            # Retry 2: no filters
            results = search_listings(description, size=None, max_price=None)
            if results:
                session["retry_attempted"] = True
                session["retry_note"] = "No exact match found — showing closest results with filters removed."
                session["search_results"] = results

    if not results:
        session["error"] = (
            f"No listings matched '{query}'. "
            "Try different keywords, a broader size, or a higher price limit."
        )
        return session

    # Step 3: Select top result
    session["selected_item"] = results[0]

    # Step 4: Price assessment (stretch, non-fatal)
    try:
        session["price_assessment"] = compare_price(session["selected_item"])
    except Exception:
        session["price_assessment"] = None

    # Step 5: Outfit suggestion
    session["outfit_suggestion"] = suggest_outfit(session["selected_item"], wardrobe)

    # Step 6: Fit card
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        if session["retry_note"]:
            print(f"Note: {session['retry_note']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")
        if session["price_assessment"]:
            pa = session["price_assessment"]
            print(f"\nPrice: {pa['verdict'].upper()} — ${pa['item_price']}, avg ${pa['avg_comparable']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
