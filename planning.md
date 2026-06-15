# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Searches the mock listings dataset and returns items that match the user's
description, optional size, and optional price ceiling. Matching is keyword-based:
the description is tokenized and scored against each listing's title, description,
category, style_tags, colors, and brand. Results are sorted by relevance score,
highest first.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): ...
- `size` (str): ...
- `max_price` (float): ...
  
- `description` (str): Free-text keywords describing the item the user wants
  (e.g., "vintage graphic tee", "90s track jacket"). Extracted from the natural
  language query after size and price tokens are removed.
- `size` (str | None): Size string to filter by, or None to skip size filtering.
  Matching is case-insensitive and partial — "M" matches "S/M", "M/L", and "M".
- `max_price` (float | None): Maximum price in dollars, inclusive. None means no
  price ceiling.
  
**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->

A `list[dict]` of matching listing dicts, sorted by relevance score descending.
Each dict contains:
- `id` (str): unique listing identifier
- `title` (str): listing title
- `description` (str): seller description
- `category` (str): one of tops, bottoms, outerwear, shoes, accessories
- `style_tags` (list[str]): style descriptors
- `size` (str): size as listed
- `condition` (str): excellent, good, or fair
- `price` (float): listed price in dollars
- `colors` (list[str]): colors present in the item
- `brand` (str | None): brand name or None
- `platform` (str): depop, thredUp, or poshmark

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
If the result list is empty and size or price filters were active, the agent
automatically retries with loosened constraints (removes size filter; raises
price ceiling by 50%). If still empty, retries with no filters at all. If still
empty, sets `session["error"]` to an actionable message and returns early. This way
`suggest_outfit` and `create_fit_card` are never called with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Given a thrifted item and the user's wardrobe, calls the LLM (Groq llama-3.3-70b)
to suggest 1–2 complete outfit combinations using the new item and named pieces
from the wardrobe. If the wardrobe is empty, returns general styling advice
(what pairs well with the item's aesthetic, what vibe it suits) instead of
crashing or returning empty.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): ...
- `wardrobe` (dict): ...

- `new_item` (dict): The listing dict for the item the user is considering —
  the same dict returned by `search_listings`. Must have at minimum `title`,
  `description`, `style_tags`, `colors`, `price`, and `platform`.
- `wardrobe` (dict): A wardrobe dict with an `'items'` key containing a list of
  wardrobe item dicts. Each wardrobe item has: `id`, `name`, `category`,
  `colors` (list), `style_tags` (list), `notes` (str | None).
  May have an empty `items` list.

**What it returns:**
<!-- Describe the return value -->
A non-empty `str` with outfit suggestions. When the wardrobe is populated,
suggestions reference specific named pieces ("Pair with your baggy straight-leg
jeans and black combat boots..."). When empty, returns general style advice
("This works well with wide-leg trousers, chunky sneakers...").

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
If the LLM call raises an exception (network error, API error), the function
catches it and returns a fallback string with the exception message and a brief
generic styling tip — never crashes the agent.
---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Generates a short, shareable Instagram/TikTok-style caption (2–4 sentences)
for the outfit. Calls the LLM with a higher temperature (0.95) so the output
varies meaningfully for different inputs. The caption is casual, lowercase,
mentions the item name / price / platform once each, and ends with one emoji.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (...): ...

- - `outfit` (str): The outfit suggestion string produced by `suggest_outfit`.
  Must be a non-empty, non-whitespace string for the tool to proceed.
- `new_item` (dict): The listing dict for the thrifted item. Used to pull
  `title`, `price`, `platform`, and `style_tags` for the caption context.

**What it returns:**
<!-- Describe the return value -->
A `str` of 2–4 sentences. If `outfit` is empty or whitespace-only, returns a
descriptive error string (explaining what failed and what to do instead) rather
than raising an exception.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
- Empty `outfit` input: immediately returns an error string without calling the LLM.
- LLM exception: catches and returns a fallback string with the error and a
  truncated version of the outfit text.

---

### Additional Tools (if any) Yes: stretch features

<!-- Copy the block above for any tools beyond the required three -->

### Tool 4: compare_price
**What it does:**
Estimates whether an item's price is fair relative to comparable listings in the
dataset. Comparables are defined as listings in the same category with at least
one overlapping style tag. Verdict is one of "great deal" (>20% below avg),
"fair" (within ±20%), "pricey" (>20% above avg), or "unknown" (no comparables).

**Input parameters:**
- `item` (dict): The listing dict to evaluate.
- `all_listings` (list[dict] | None): The full listings dataset. If None, loads
  from disk automatically.

**What it returns:**
A `dict` with keys:
- `verdict` (str): "great deal", "fair", "pricey", or "unknown"
- `item_price` (float): The item's listed price
- `avg_comparable` (float | None): Average price of comparable items, or None
- `comparable_count` (int): Number of comparables found
- `reasoning` (str): Human-readable explanation of the verdict

**What happens if it fails or returns nothing:**
If the listings can't be loaded or no comparables exist, returns a dict with
`verdict="unknown"` and a reasoning string explaining why — never raises.


---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->

The agent's decision logic in `run_agent()` follows these specific branches:

```
1. Parse query → description, size, max_price (regex extraction)

2. Call search_listings(description, size, max_price)
   → if results is empty AND (size is not None OR max_price is not None):
       retry: search_listings(description, size=None, max_price * 1.5)
       → if still empty:
           retry: search_listings(description, size=None, max_price=None)
           → if still empty:
               set session["error"] = actionable message
               RETURN EARLY — do NOT proceed
           → if results found: set session["retry_note"], continue
       → if results found: set session["retry_note"], continue
   → if results is empty AND no filters were set:
       set session["error"] = actionable message
       RETURN EARLY

3. selected_item = results[0]
   Store in session["selected_item"]

4. Call compare_price(selected_item)           [STRETCH]
   Store dict in session["price_assessment"]
   (non-fatal: if this fails, session["price_assessment"] = None, continue)

5. Call suggest_outfit(selected_item, wardrobe)
   Store string in session["outfit_suggestion"]

6. Call create_fit_card(outfit_suggestion, selected_item)
   Store string in session["fit_card"]

7. Update style profile on disk               [STRETCH]
   Append search to profile["past_searches"] (keep last 10)
   Save wardrobe snapshot for future "Remembered wardrobe" sessions

8. RETURN session
```
The key adaptive branches:
- **search returns empty + filters active** → retry with loosened constraints, inform user
- **search returns empty + no filters** → set error, stop
- **price_assessment fails** → non-fatal, continue with None
- **wardrobe is empty** → suggest_outfit gives general advice instead of crashing
---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

All state for one interaction lives in the `session` dict, initialized by
`_new_session(query, wardrobe)` and returned at the end of `run_agent()`.

| Field | Type | Set when | Passed to |
|---|---|---|---|
| `query` | str | Initialization | Parsing |
| `parsed` | dict | After parsing | search_listings args |
| `search_results` | list[dict] | After search_listings | selected_item selection |
| `selected_item` | dict | After selecting results[0] | suggest_outfit, compare_price, create_fit_card |
| `wardrobe` | dict | Initialization | suggest_outfit |
| `outfit_suggestion` | str | After suggest_outfit | create_fit_card |
| `fit_card` | str | After create_fit_card | Return to UI |
| `price_assessment` | dict | After compare_price | Return to UI |
| `retry_attempted` | bool | After retry | UI display |
| `retry_note` | str | After retry | UI display |
| `error` | str | On early exit | Return to UI |

No values are re-entered by the user between steps. The item dict that comes
out of `search_listings` is the same Python object that enters `suggest_outfit`
and `create_fit_card` — no copying or re-formatting.
---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results with size/price filters | Retry with loosened constraints; inform user what was adjusted; if still empty: "No listings matched '[query]'. Try different keywords, a broader size, or a higher price limit." |
| search_listings | No results even with no filters | Sets session["error"] with actionable message; returns early; suggest_outfit and create_fit_card are never called |
| suggest_outfit | Wardrobe is empty | Calls LLM with general styling prompt instead of wardrobe-specific one; returns useful style advice rather than error |
| suggest_outfit | LLM API exception | Catches exception; returns fallback string with error context + brief generic tip |
| create_fit_card | outfit arg is empty or whitespace | Returns descriptive error string immediately; never calls LLM; does not crash |
| create_fit_card | LLM API exception | Catches exception; returns fallback string with error and truncated outfit text |
| compare_price | No comparable listings | Returns dict with verdict="unknown" and reasoning explaining why |
| compare_price | Listings can't be loaded | Returns dict with verdict="unknown" and error context |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->
```
User query (natural language)
         │
         ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                      run_agent()                                │
   │                   Planning Loop                                 │
   │                                                                 │
   │  Step 1: _parse_query(query)                                    │
   │           → description, size, max_price                        │
   │           stored in session["parsed"]                           │
   │                       │                                         │
   │  Step 2: search_listings(description, size, max_price)          │
   │                       │                                         │
   │               results == [] ?                                   │
   │               AND filters set?                                  │
   │                 │         │                                      │
   │               YES        NO                                     │
   │                 │         │                                      │
   │    RETRY: loosen filters  │                                      │
   │    search_listings(...)   │                                      │
   │                 │         │                                      │
   │         still [] ?        │                                      │
   │           │      │        │                                      │
   │          YES     NO       │                                      │
   │           │      │        │                                      │
   │  session["error"]│        │  ◄── error path returns here        │
   │  RETURN EARLY    │        │                                      │
   │                  └────────┘                                      │
   │                       │                                         │
   │  Step 3: selected_item = results[0]                             │
   │          stored in session["selected_item"]                     │
   │                       │                                         │
   │  Step 4: compare_price(selected_item)        [STRETCH]          │
   │          stored in session["price_assessment"]                  │
   │          (non-fatal if fails → None, continue)                  │
   │                       │                                         │
   │  Step 5: suggest_outfit(selected_item, wardrobe)                │
   │           wardrobe empty? → general advice                      │
   │           wardrobe full?  → specific outfit combos              │
   │          stored in session["outfit_suggestion"]                 │
   │                       │                                         │
   │  Step 6: create_fit_card(outfit_suggestion, selected_item)      │
   │          stored in session["fit_card"]                          │
   │                       │                                         │
   │  Step 7: _save_profile(profile)              [STRETCH]          │
   │          appends search to past_searches                        │
   │          saves wardrobe snapshot                                │
   │                       │                                         │
   └───────────────────────┼─────────────────────────────────────────┘
                           │
                           ▼
                    Return session dict
                    → listing_text
                    → outfit_suggestion
                    → fit_card
                    → price_assessment
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**Tool 1 (search_listings):**
I plan to use Claude with the Tool 1 spec from this planning.md (inputs, return value, failure mode, scoring approach) and ask it to implement the function using load_listings() from the data loader. Before running the generated code, I will verify: (a) it filters by all three parameters, (b) handles empty results by returning [] rather than raising, and (c) sorts results by score descending. I will test it manually with at least 3 queries — a matching query, a deliberate no-results query, and a price-only filter — and review the tokenization logic to make sure keyword matching handles punctuation in style tags correctly.

**Tool 2 (suggest_outfit):**
I plan to use Claude with the Tool 2 spec. I will ask it to implement the empty vs. populated wardrobe branching explicitly, and to format wardrobe items as a readable bullet list in the LLM prompt so the model can reference specific pieces by name. Before using the output, I will review the system prompt framing and the temperature setting, and adjust both if the suggestions feel too generic or too repetitive across runs.

**Tool 3 (create_fit_card):**
I plan to use Claude with the Tool 3 spec. I will ask it to guard the empty-outfit case before making any API call, and to use a higher temperature (around 0.95) for output variety. I will run the generated function several times on the same input and compare outputs — if they are too similar, I will revise the prompt constraints (e.g., caption style, emoji usage, how to reference the price and platform) until the captions feel distinct and authentic across runs.

**Tool 4 (compare_price, STRETCH):**
I plan to use Claude with the Tool 4 spec from this planning.md. I will ask it to implement the comparable-filtering logic (same category + at least one overlapping style tag, excluding the item itself) and the ±20% verdict thresholds. Before using the output, I will verify the exclude-self logic is correct and write a test to confirm the item's own price is not included in its own average.


**Milestone 4 — Planning loop and state management:**
I plan to use Claude with the Architecture diagram and the Planning Loop and State Management sections from this planning.md as input. I will ask it to implement run_agent() following the numbered steps in the diagram, branching on search_results being empty before proceeding to suggest_outfit. Before running the generated code, I will check that: (a) it does not call all three tools unconditionally, (b) values are stored in the session dict between steps rather than passed as function arguments directly, and (c) the retry logic loosens constraints in stages rather than dropping all filters at once. I will revise anything that does not match the spec before testing end-to-end.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
`_parse_query()` extracts:
- `description` = "vintage graphic tee"
- `size` = None (no size mentioned)
- `max_price` = 30.0

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
`search_listings("vintage graphic tee", size=None, max_price=30.0)` is called.
The function loads all 40 listings, drops any priced above $30, then scores
remaining listings by keyword overlap with {"vintage", "graphic", "tee"}.
Results scored > 0 are sorted descending. Returns something like:
```
[
  {"id": "lst_006", "title": "Graphic Tee — 2003 Tour Bootleg Style", "price": 24.0, ...},
  {"id": "lst_033", "title": "Vintage Band Tee — Faded Grey", "price": 19.0, ...},
  {"id": "lst_002", "title": "Y2K Baby Tee — Butterfly Print", "price": 18.0, ...},
]
```
`session["search_results"]` = the full list.
Results are not empty → no error, continue.


**Step 3:**
<!-- Continue until the full interaction is complete -->

`session["selected_item"]` = `{"id": "lst_006", "title": "Graphic Tee — 2003 Tour Bootleg Style", "price": 24.0, "platform": "depop", ...}`

**Stretch: Price assessment**
`compare_price(selected_item, all_listings)` finds all other tops with
overlapping style tags (vintage, graphic tee, grunge, streetwear, band tee).
Calculates average price of comparables ~$21. Item is $24, ratio ~1.14, within
±20% → verdict "fair". Stored in `session["price_assessment"]`.

**Step 5 — Suggest outfit:**
`suggest_outfit(selected_item, get_example_wardrobe())` is called. Wardrobe
has 10 items, so the populated branch runs. Prompt includes the item details
and wardrobe list. LLM returns something like:
"Pair the bootleg tee with your baggy straight-leg jeans (dark wash) and
black combat boots — instant 90s grunge. Tuck the front corner slightly for
shape. Or layer it under the vintage black denim jacket over the wide-leg khakis
with chunky white sneakers for a more street-ready look."
Stored in `session["outfit_suggestion"]`.

**Step 6 — Create fit card:**
`create_fit_card(outfit_suggestion, selected_item)` is called. outfit is
non-empty → LLM called with temperature 0.95. Returns something like:
"found this graphic tee on depop for $24 and honestly it was sitting in a box
waiting for my dark wash jeans 🖤 full grunge moment"
Stored in `session["fit_card"]`.

**Step 7 — Save profile:**
Profile updated: search appended to `past_searches`, wardrobe snapshot saved.




**Final output to user:**
<!-- What does the user actually see at the end? -->

- Panel 1 (listing): Title, price, platform, size, condition, colors, tags, description
- Panel 2 (price): 🟡 FAIR — $24.00, avg comparable $21.00, 8 comparables
- Panel 3 (outfit): The 2-paragraph outfit suggestion
- Panel 4 (fit card): The 2-sentence OOTD caption

**Error path demonstration:**
If the query were "designer ballgown size XXS under $5":
- `search_listings("designer ballgown", size="XXS", max_price=5.0)` → `[]`
- Filters are active → retry with size=None, max_price=7.50 → `[]`
- Retry with size=None, max_price=None → `[]` (no ballgown in dataset)
- `session["error"]` = "No listings matched 'designer ballgown size XXS under $5'. Try different keywords, a broader size, or a higher price limit."
- `suggest_outfit` and `create_fit_card` are never called
- UI shows error in panel 1, empty panels 2–4
