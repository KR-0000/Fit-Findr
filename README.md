# FitFindr

A thrift-shopping assistant agent that searches secondhand listings, suggests outfit combinations, and generates shareable OOTD captions — all from a single natural language query.

---

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash)
pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit this):
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```

Open the URL shown in your terminal (usually `http://localhost:7860`).

Run tests:
```bash
.venv/Scripts/python.exe -m pytest tests/
```

---

## Tool Inventory

### Tool 1: `search_listings`

**Function:** `search_listings(description: str, size: str | None, max_price: float | None) -> list[dict]`

**Purpose:** Searches the 40-item mock listings dataset for secondhand clothing matching the user's description, optional size, and optional price ceiling. Keyword-based: the description is tokenized and scored against each listing's title, description, category, style_tags, colors, and brand. Returns results sorted by relevance, highest first.

**Inputs:**
- `description` (str): Free-text keywords extracted from the user's query (e.g., `"vintage graphic tee"`)
- `size` (str | None): Size filter — case-insensitive partial match (`"M"` matches `"S/M"`, `"M/L"`, `"M"`). `None` skips size filtering.
- `max_price` (float | None): Maximum price in dollars, inclusive. `None` means no price ceiling.

**Returns:** `list[dict]` — each dict contains:
- `id` (str): unique listing identifier
- `title` (str): listing title
- `description` (str): seller's description
- `category` (str): `tops`, `bottoms`, `outerwear`, `shoes`, or `accessories`
- `style_tags` (list[str]): style descriptors (e.g., `["vintage", "grunge", "streetwear"]`)
- `size` (str): size as listed by the seller
- `condition` (str): `excellent`, `good`, or `fair`
- `price` (float): listed price in dollars
- `colors` (list[str]): colors present in the item
- `brand` (str | None): brand name, or `None`
- `platform` (str): `depop`, `thredUp`, or `poshmark`

Returns `[]` (empty list) if nothing matches — never raises an exception.

---

### Tool 2: `suggest_outfit`

**Function:** `suggest_outfit(new_item: dict, wardrobe: dict) -> str`

**Purpose:** Calls the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 complete outfit combinations using the thrifted item and the user's saved wardrobe pieces. If the wardrobe is empty, returns general styling advice instead of crashing.

**Inputs:**
- `new_item` (dict): A listing dict returned by `search_listings`. Must include at minimum `title`, `description`, `style_tags`, `colors`, `price`, and `platform`.
- `wardrobe` (dict): A wardrobe dict with an `'items'` key containing a list of wardrobe item dicts. Each wardrobe item has: `id`, `name`, `category`, `colors` (list), `style_tags` (list), `notes` (str | None). May have an empty `items` list.

**Returns:** A non-empty `str` with outfit suggestions. When the wardrobe is populated, suggestions reference specific named pieces ("Pair with your baggy straight-leg jeans…"). When empty, returns general style advice ("This works well with wide-leg trousers…").

---

### Tool 3: `create_fit_card`

**Function:** `create_fit_card(outfit: str, new_item: dict) -> str`

**Purpose:** Generates a 2–4 sentence casual Instagram/TikTok-style OOTD caption. Uses a high LLM temperature (0.95) so output varies across runs. Mentions the item name, price, and platform once each, and ends with exactly one emoji.

**Inputs:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit`. Must be non-empty and non-whitespace for the tool to proceed.
- `new_item` (dict): The listing dict — used to pull `title`, `price`, `platform`, and `style_tags` for caption context.

**Returns:** A `str` of 2–4 sentences in casual lowercase. If `outfit` is empty or whitespace-only, returns a descriptive error string immediately without calling the LLM.

---

### Stretch Tool: `compare_price`

**Function:** `compare_price(item: dict, all_listings: list[dict] | None) -> dict`

**Purpose:** Estimates whether a listing's price is fair by comparing it to similar listings in the dataset. Comparables are defined as listings in the same category with at least one overlapping style tag (the item itself is excluded from its own average).

**Inputs:**
- `item` (dict): The listing dict to evaluate.
- `all_listings` (list[dict] | None): Full dataset. If `None`, loads from disk automatically.

**Returns:** `dict` with:
- `verdict` (str): `"great deal"` (>20% below avg), `"fair"` (within ±20%), `"pricey"` (>20% above avg), or `"unknown"` (no comparables found)
- `item_price` (float): The item's listed price
- `avg_comparable` (float | None): Average price of comparable items, or `None`
- `comparable_count` (int): Number of comparable listings found
- `reasoning` (str): Human-readable explanation of the verdict

---

## How the Planning Loop Works

The agent's `run_agent()` function follows a fixed conditional sequence — not a free-choice loop. Here is the exact logic:

**Step 1 — Parse query.**
`_parse_query()` uses regex to extract three things from the natural language query:
- `description`: everything remaining after size and price tokens are removed
- `size`: patterns like `"size M"`, `"XL"`, `"XXS"`, `"S/M"` — removed from description
- `max_price`: patterns like `"under $30"`, `"less than $40"` — removed from description

These are stored in `session["parsed"]`.

**Step 2 — Search, with retry logic.**
`search_listings(description, size, max_price)` is called and results stored in `session["search_results"]`.

- If results are empty **and** filters (size or price) were active:
  - **Retry 1:** Remove size filter, raise price ceiling 50% → call `search_listings` again
  - **Retry 2:** If still empty, remove all filters → call `search_listings` again
  - If still empty: set `session["error"]` to an actionable message and **return early** — `suggest_outfit` and `create_fit_card` are never called with empty input
- If results are empty **and** no filters were set: set `session["error"]` and return early immediately

This is the key adaptive branch: the agent does not call all three tools unconditionally. It only proceeds to `suggest_outfit` when there is a valid item to pass.

**Step 3 — Select item.**
`session["selected_item"] = results[0]` — the highest-relevance listing becomes the item used for the rest of the interaction.

**Step 4 — Price assessment (stretch, non-fatal).**
`compare_price(selected_item)` is called. If it fails for any reason, `session["price_assessment"]` is set to `None` and the agent continues — this step never blocks the interaction.

**Step 5 — Outfit suggestion.**
`suggest_outfit(selected_item, wardrobe)` is called. The wardrobe is passed directly from `session["wardrobe"]` — the user does not re-enter anything. Result stored in `session["outfit_suggestion"]`.

**Step 6 — Fit card.**
`create_fit_card(session["outfit_suggestion"], session["selected_item"])` is called. The outfit string from step 5 passes directly into this call. Result stored in `session["fit_card"]`.

**Step 7 — Return session.**
The completed session dict is returned to `handle_query()` in `app.py`, which formats the results into the three Gradio output panels.

---

## State Management

All state for one interaction lives in the `session` dict, initialized by `_new_session(query, wardrobe)` and returned at the end of `run_agent()`. No values are re-entered by the user between steps.

| Field | Type | Set when | Consumed by |
|---|---|---|---|
| `query` | str | Initialization | `_parse_query()` |
| `parsed` | dict | After parsing | `search_listings()` args |
| `search_results` | list[dict] | After `search_listings` | `selected_item` selection |
| `selected_item` | dict | After `results[0]` selection | `suggest_outfit`, `compare_price`, `create_fit_card` |
| `wardrobe` | dict | Initialization | `suggest_outfit()` |
| `outfit_suggestion` | str | After `suggest_outfit` | `create_fit_card()` |
| `fit_card` | str | After `create_fit_card` | Returned to UI |
| `price_assessment` | dict | After `compare_price` | Returned to UI |
| `retry_attempted` | bool | After retry | UI display note |
| `retry_note` | str | After retry | Displayed in listing panel |
| `error` | str | On early exit | Returned to UI as panel 1 text |

The dict returned by `search_listings` is the **same Python object** passed into `suggest_outfit` and `create_fit_card` — no copying or reformatting between steps. The outfit string from `suggest_outfit` is passed directly into `create_fit_card` without any user re-entry.

---

## Error Handling

| Tool | Failure mode | Agent response |
|---|---|---|
| `search_listings` | No results with size/price filters | Retries automatically: first removes size filter and raises price ceiling 50%, then retries with no filters. If still empty: `session["error"]` = `"No listings matched '[query]'. Try different keywords, a broader size, or a higher price limit."` — returns early, never calls `suggest_outfit` or `create_fit_card` |
| `search_listings` | No results with no filters | Sets `session["error"]` with the same actionable message, returns early immediately |
| `suggest_outfit` | Wardrobe is empty | Branches to a general styling prompt instead of the wardrobe-specific one — returns useful advice like "This works well with wide-leg trousers, chunky sneakers…" rather than crashing |
| `suggest_outfit` | LLM API exception | Catches the exception, returns a fallback string: `"Could not generate outfit suggestion ([error]). As a general tip: this item pairs well with neutral basics…"` — never crashes the agent |
| `create_fit_card` | `outfit` is empty or whitespace | Returns `"Could not generate a fit card: the outfit suggestion was empty. Run suggest_outfit first…"` immediately, without calling the LLM |
| `create_fit_card` | LLM API exception | Catches the exception, returns a fallback string with the error message and a truncated version of the outfit text |
| `compare_price` | No comparable listings | Returns `{"verdict": "unknown", …, "reasoning": "No comparable listings found…"}` — never raises |
| `compare_price` | Listings can't be loaded / any exception | Returns `{"verdict": "unknown", …, "reasoning": "Price comparison failed: [error]"}` — never raises |

**Concrete example from testing:**

Running `search_listings("designer ballgown", size="XXS", max_price=5)` returns `[]`. When this query is run through `run_agent()`:
1. Stage 1: `search_listings("designer ballgown", size="XXS", max_price=5.0)` → `[]`
2. Filters are active → Stage 2: `search_listings("designer ballgown", size=None, max_price=7.5)` → `[]`
3. Stage 3: `search_listings("designer ballgown", size=None, max_price=None)` → `[]`
4. `session["error"]` = `"No listings matched 'designer ballgown size XXS under $5'. Try different keywords, a broader size, or a higher price limit."`
5. `suggest_outfit` and `create_fit_card` are never called — confirmed by `session["outfit_suggestion"] is None` and `session["fit_card"] is None`

Running `create_fit_card("", some_item)` directly returns: `"Could not generate a fit card: the outfit suggestion was empty. Run suggest_outfit first and pass its result here."` — no exception raised.

---

## Spec Reflection

**One way the spec helped:** Writing out the retry logic in the Planning Loop section before any code forced a decision about the exact order of constraint loosening (first remove size, then raise price 50%, then remove price entirely). Without that spec, it would have been easy to write a vague "retry with looser filters" that dropped all constraints at once and skipped the staged approach. The spec made the three stages explicit, which translated directly to the three `if not results` branches in `run_agent()`.

**One divergence from spec and why:** The spec described step 7 as saving a style profile to disk (appending past searches and wardrobe snapshots). This was not implemented — the stretch feature scope was limited to `compare_price` only, and the profile persistence would have added disk I/O, a file format to define, and edge cases around concurrent writes that were out of scope for this project. The rest of the interaction (steps 1–6) was implemented exactly as specced.

---

## AI Usage

**Instance 1 — Implementing `search_listings` and the planning loop.**

I gave Claude the Tool 1 spec from `planning.md` (input parameters with types, return value fields, failure mode, and the scoring approach) plus the Architecture diagram and Planning Loop section. I asked it to implement `search_listings()` using `load_listings()` from the data loader, and `run_agent()` following the numbered steps in the diagram.

Before using the generated code I reviewed three things: (a) whether the retry logic loosened constraints in stages (remove size first, then raise price, then remove price) rather than dropping all filters at once — the initial output dropped all filters in one step, which I revised to match the spec's staged approach; (b) whether the size regex matched multi-character sizes like `XXS` and `XL` — it only matched `XS` and `L`, so I expanded the regex pattern to cover `XXS`, `XXL`, and `S/M`/`M/L`; (c) whether `search_listings` returned `[]` rather than raising when nothing matched — it did.

**Instance 2 — Implementing `suggest_outfit` and `create_fit_card`.**

I gave Claude the Tool 2 and Tool 3 specs from `planning.md`, including the explicit wardrobe branching requirement (empty vs. populated) and the instruction to use temperature 0.95 for `create_fit_card`. I asked it to implement both functions with the LLM prompt text included.

Before using the output I checked: (a) that the wardrobe branch was explicit — the initial output used a single prompt with an `if` inside an f-string, which I restructured into two clearly separate prompt strings for the empty and populated cases; (b) that `create_fit_card` guarded against empty `outfit` before making any API call — it did; (c) that the `suggest_outfit` fallback caught all exceptions and returned a non-empty string rather than re-raising — it did. I also ran `create_fit_card` three times on the same input to confirm the captions varied meaningfully (they did, given temperature 0.95).

---

## Price Comparison (Stretch Feature)

`compare_price` finds all listings in the same `category` with at least one overlapping style tag, excludes the item being evaluated from its own average, and returns a verdict based on ±20% thresholds:

- **great deal**: item price is more than 20% below the comparable average
- **fair**: item price is within ±20% of the average
- **pricey**: item price is more than 20% above the average
- **unknown**: no comparable listings found (different category or no shared style tags)

The result is displayed in the listing panel of the UI alongside the item details.

---

## Retry Logic (Stretch Feature)

When `search_listings` returns zero results and size or price filters were active, `run_agent()` automatically retries in stages:

1. Remove size filter, raise price ceiling by 50%
2. Remove all filters

If results are found after retrying, a `retry_note` is displayed at the top of the listing panel explaining what was adjusted (e.g., `"Loosened search constraints: removed size filter and raised price to $45"`). If all three stages return empty, the agent sets an error message and stops — `suggest_outfit` and `create_fit_card` are never called.
