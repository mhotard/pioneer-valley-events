# Pioneer Valley Events — Maintainer Guide

Community event aggregator for the Pioneer Valley (Amherst, Northampton, etc.).
Scrapes ~20 sources weekly, writes `docs/data/events.json`, served as a static
site via GitHub Pages. There is no backend — `pipeline.py` is the only
"server-side" logic, run weekly by GitHub Actions.

## Commands

```bash
# Run everything (ALWAYS source ~/.zshrc first — the API key lives there)
source ~/.zshrc && python3 pipeline.py

# Preview without writing events.json
source ~/.zshrc && python3 pipeline.py --dry-run

# Run a single scraper by name (names = scraper .name attrs / sources.json names)
source ~/.zshrc && python3 pipeline.py --source umass

# Tests and lint (no API key needed — Claude calls are mocked)
python3 -m pytest -q
python3 -m ruff check .

# Dump raw HTML from a source to inspect its structure
python3 debug_scraper.py amherst-cinema
```

The Anthropic key is read from `ANTHROPIC_API_KEY_PIONEER` (falls back to
`ANTHROPIC_API_KEY`). Claude Code's Bash tool starts a fresh shell, so the env
var is NOT set unless you `source ~/.zshrc` first. In GitHub Actions the secret
is named `ANTHROPIC_API_KEY`.

## Architecture

```
pipeline.py            entry point: run scrapers → date filter → dedupe → sort → write
sources.json           config for Claude-powered scrapers (most sources live here)
scrapers/
  base.py              Event dataclass + BaseScraper (fetch() catches all exceptions)
  claude_scraper.py    ClaudeHTMLScraper / ClaudePlaywrightScraper — generic, config-driven
  ical.py              ICalScraper base for .ics feeds
  umass_athletics.py   iCal (subclasses ICalScraper)
  amherst_athletics.py iCal (subclasses ICalScraper)
  umass.py             JSON-LD from events.umass.edu
  mtholyoke.py         Localist JSON API (events.mtholyoke.edu/api/2/events)
  tribe_events.py      TribeEventsScraper base for WordPress "The Events Calendar"
                       REST API (/wp-json/tribe/events/v1/events) —
                       springfield-museums and hawks-reed subclass it
  amherst_cinema.py    custom HTML parsing (Drupal)
  jones_library.py     RSS feed
  forbes_library.py    LibCal RSS feed (brittle escaping — see regexes there)
  nepm_culture.py      finds latest newsletter edition, reuses claude_scraper helpers
  harriers.py          reads harriers.org race_calendar.json directly
  community.py         manually-curated events from community_events.json (supports recurrence)
  __init__.py          get_all_scrapers() — register new static scrapers here
docs/                  static frontend (vanilla JS) + docs/data/events.json
tests/                 pytest; test_schema.py validates the committed events.json
logs/                  timestamped log per pipeline run (gitignored)
```

## Rules

- **Adding a source: edit `sources.json`, don't write Python.** Only write a
  static scraper (.py) when the site offers structured data (iCal → subclass
  `ICalScraper`; JSON-LD/RSS/JSON → small custom scraper). Plain HTML pages go
  in `sources.json` with `"type": "html"`; JavaScript-rendered pages or sites
  that block plain requests (Cloudflare 403s) use `"type": "playwright"`.
- New static scrapers must be registered in `scrapers/__init__.py`
  (`STATIC_SCRAPERS` list) and set `name`, `url`, `town` class attributes.
- A scraper must never crash the pipeline: `BaseScraper.fetch()` catches all
  exceptions and records them in `last_error`. Raise freely inside `_fetch()`.
- Events must use the fixed category set (see `VALID_CATEGORIES` in
  `scrapers/claude_scraper.py` and `tests/test_schema.py`):
  music, arts, film, comedy, community, academia, family, food, outdoor, festival.
- Dates are `YYYY-MM-DD` strings; times are `H:MM AM/PM`. The pipeline keeps
  events from 3 days past to 90 days out.
- The user (Michael) is new to terminal work — give exact copy-paste commands
  and explain what they do.

## How Claude scrapers work (claude_scraper.py)

fetch HTML (requests or Playwright) → `_clean_html` strips scripts/nav/attrs
and truncates to 20k chars → `_extract_events` sends it to Haiku
(claude-haiku-4-5, max_tokens 8192) → `_parse_json_array` parses the reply,
**salvaging complete objects if the output was truncated at max_tokens** →
`_dicts_to_events` validates (skips missing title/bad date, coerces unknown
categories to "community").

## Debugging a scraper

1. Run it alone: `source ~/.zshrc && python3 pipeline.py --source <name> --dry-run`
2. Check the newest file in `logs/` — every run ends with a per-scraper summary
   table (OK / ZERO / ERROR).
3. `ZERO` with no error usually means the page is JS-rendered (try
   `"type": "playwright"`) or the URL/structure changed
   (`python3 debug_scraper.py <name>` to inspect raw HTML).
4. Verify URLs with curl before editing code: a 404 means the site reorganized;
   a 403 with requests but 200 with curl means TLS fingerprint blocking → use
   playwright.

## Known source quirks

- `gateway-city-arts` was removed 2026-06-11: the venue closed and the domain
  is now squatted by a spam site. Do not re-add it.
- `explore-western-mass` was removed 2026-06-11: it 403s both plain requests
  and headless Chrome (hard bot blocking). Do not re-add without a new approach.
- `hawks-reed` returning ZERO is normal when the venue has nothing scheduled —
  confirm via their REST API:
  `curl 'https://www.hawksandreed.com/wp-json/tribe/events/v1/events?per_page=5'`
- Playwright sources are slow (~25s each) — that's normal.
- Dead ends checked 2026-06-12, don't re-investigate: Hampshire College and
  Springfield Symphony hard-block even headless Chrome (403/Access denied);
  recorder.com/events is an empty shell even rendered; iheg.com,
  calvintheatre.com, pleasantstreettheater.com, ironhorsemusic.com are all
  parked/squatted domains. The real Iron Horse is `ironhorse.org` (Parlor Room
  collective). The Drake is `thedrakeamherst.org` (server-rendered, html type).
