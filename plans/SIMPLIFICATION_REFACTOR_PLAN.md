# Handoff: remove duplication across miners, Haiku calls, and scrapers

## Objective

Four small, independent simplifications that remove copy-pasted code without
changing what the project publishes. Each phase is its own commit and its own
review. The order below is the recommended order; phases 3 and 4 may be
skipped or deferred without affecting phases 1 and 2.

1. Collapse the two Fabulous 413 miners onto one shared incremental-mining
   loop, and make the remaining fab413 writers use the atomic JSON helper.
2. Route every Haiku call through one helper with one model constant, one
   retry policy, and one truncation check.
3. Give the hand-written scrapers a shared HTTP fetch and (optionally) one
   category-guessing function.
4. Small readability polish in `pipeline.py`, plus repository housekeeping.

This is a deletion-oriented refactor. Do not introduce a plugin system, a
generic "miner framework", a scraper registry rewrite, a config schema, new
dependencies, or new abstractions beyond the specific functions named here.
When in doubt, prefer the smaller change.

## Starting context

Repository: `/Users/michaelhotard/Documents/ClaudeTest/pioneer-valley-events`.

Read `CLAUDE.md` and `README.md` first. Inspect `git status --short` and
recent history. When this plan was written:

- `8c0f7a3`, `a0930bf`, and `972d552` had landed (pipeline seams, atomic JSON
  storage, frontend extraction). Build on `main` at or after `972d552`.
- Baseline: 288 passing tests, Ruff clean, under the project interpreter
  (Python 3.9 locally; CI uses 3.12). Re-establish the baseline yourself.
- Three untracked plan files sat at the repo root:
  `PIPELINE_REFACTOR_PLAN.md`, `JSON_STORAGE_REFACTOR_PLAN.md`,
  `FRONTEND_REFACTOR_PLAN.md`. Phase 4 decides what to do with them.

Read before editing: `fab413_miner.py`, `fab413_entities.py`,
`fab413_guide.py`, `fab413_stats.py`, `json_storage.py`,
`scrapers/claude_scraper.py`, `scrapers/base.py`, every file under
`scrapers/`, `pipeline.py`, `debug_scraper.py`, and the tests
`tests/test_fab413_storage.py`, `tests/test_fab413.py`,
`tests/test_claude_scraper.py`, `tests/test_localist.py`,
`tests/test_tribe_events.py`, `tests/test_pipeline.py`,
`tests/test_pipeline_orchestration.py`.

Do not run live scrapers, miners, the email digest, or anything that reaches
the network or the Anthropic API. Do not regenerate any file under
`docs/data/` or `docs/413/`. Do not source shell files containing credentials.

## Global behavior contract

Across all phases, the following must not change:

- The contents, key order, and formatting of every published JSON file
  (`events.json`, `archive-YYYY.json`, `fab413_*.json`, `seasonal.json`,
  `docs/413/data.json`). Compact separators stay compact; `events.json` keeps
  `indent=2`.
- Event IDs, the fixed category set, date/time string formats, the
  publication window, dedup criteria, and the health threshold.
- CLI flags and exit codes of every script.
- The guarantees from the two earlier refactors: a rejected run touches no
  publication file; damaged stores fail rather than being reset; every
  persistent write goes through `write_json_atomic`.
- Prompts sent to Haiku. Do not reword `EXTRACT_PROMPT` or `CURATE_PROMPT`
  in any file. Moving a prompt to a new location is fine; editing its text
  is not.

---

## Phase 1 — one incremental-mining loop for both fab413 miners

### What is duplicated today

`fab413_miner.py` and `fab413_entities.py` each carry their own copy of:

- `_validated_checkpoint(value, path)` — identical except the result key
  (`"mentions"` vs `"entities"`).
- `load_store(path)` / `save_store(store, path)` — identical except the
  default path and result key.
- The rendering line inside `mine_batch` that formats a batch as
  `[Episode i | date | title]\ntext`.
- The `main()` loop: slice `todo` by `BATCH_SIZE`, call `mine_batch`,
  extend the store, `save_store`, print progress.

The two loops have drifted. Only the entities miner aborts after
`MAX_CONSECUTIVE_FAILS = 3` consecutive batch failures; the events miner
still `continue`s forever on error, which is exactly the silent-partial-run
failure that guard was added to prevent (see `CLAUDE.md`, "The /413/
dashboard"). Applying the guard to both is the one intentional behavior
change in this phase.

### Target shape

Add a small module `fab413_common.py` at the repo root (or, if you prefer
fewer files, put it in `fab413_miner.py` and import from there in
`fab413_entities.py` — the existing `validated_episode_rows` import already
goes that direction; pick one and say which). It holds:

```python
def render_batch(batch: list[dict]) -> str
    # "[Episode i | date | title]\ntext" joined by blank lines. Unchanged output.

def validated_checkpoint(value, path, *, result_key: str) -> dict
    # The existing validator, parameterized by "mentions" | "entities".

def load_checkpoint(path, *, result_key) -> dict
def save_checkpoint(store, path, *, result_key) -> None
    # read_json with the empty-store default / validate / write_json_atomic.

def mine_incrementally(
    todo: list[dict], store: dict, *, result_key: str,
    mine_batch, save, batch_size: int, max_consecutive_fails: int,
    out=sys.stdout, err=sys.stderr,
) -> int
    # The shared loop. Returns the number of new rows added. Raises
    # SystemExit(1) (or a dedicated exception the caller turns into exit 1)
    # after max_consecutive_fails consecutive batch errors, after the last
    # successful checkpoint has been saved.
```

Each miner keeps its own: prompt constant, paths, `BATCH_SIZE`, the
row-shaping half of `mine_batch` (the loop that turns raw Haiku dicts into
mention/entity rows — these genuinely differ), `main()` argument parsing,
and its data-acquisition step (`fetch_feed` + `save_episodes` for the events
miner; `load_episodes` for the entities miner).

Keep module-level names that tests monkeypatch: `BATCH_SIZE`, `mine_batch`,
`fetch_feed`, `load_episodes`, `save_store`, `read_json`, `write_json_atomic`
must still be attributes of each miner module (thin wrappers around the
shared helpers are fine — `save_store = partial(...)` is not, because
`monkeypatch.setattr(module, "save_store", ...)` must still take effect
inside the loop; pass `save=module.save_store` late, at call time, not at
import time).

### Also in this phase

- `fab413_guide.py` `main()` and `fab413_stats.py` `main()` write their
  output with a bare `open(...)`/`json.dump`. Switch both to
  `write_json_atomic(path, payload, separators=(",", ":"))`. Their reads may
  stay as plain `json.load` (they are consumers, not stores) or move to
  `read_json`; either is acceptable, keep it consistent.
- Do not touch `fab413_stats.GAZETTEER` or any aggregation logic.

### Tests

`tests/test_fab413_storage.py` already parametrizes over `MINERS`. Extend it
rather than writing a new file:

- Consecutive-failure abort now applies to both modules: after
  `MAX_CONSECUTIVE_FAILS` failed batches, the run exits 1, the checkpoint on
  disk contains every batch that succeeded before the failures, and no guid
  from a failed batch is marked mined. (One such test exists for entities
  only — parametrize it.)
- A single failed batch followed by a successful one resets the counter and
  the run completes with exit 0.
- `render_batch` output is byte-identical to the previous inline f-string
  for a two-episode fixture (guards the prompt contract).
- `fab413_guide` and `fab413_stats` write through the atomic helper: a
  monkeypatched `write_json_atomic` is called with the expected path and
  compact separators (no network, no API — monkeypatch `curate` to return a
  fixed list).

### Gate

All of `tests/test_fab413_storage.py` and `tests/test_fab413.py` pass. Diff
of `fab413_miner.py` + `fab413_entities.py` is net-negative by at least 80
lines. `git diff --stat docs/` is empty.

---

## Phase 2 — one Haiku call path

### What is duplicated today

Three call sites build an Anthropic request independently, each hardcoding
`"claude-haiku-4-5-20251001"`:

| Caller | Retry | Truncation check | Logging |
|---|---|---|---|
| `claude_scraper._extract_events` | none | yes (`stop_reason == "max_tokens"` warning) | `logging` |
| `claude_scraper.call_haiku` (used by both miners) | 3 tries, 20s×3 backoff | none | `print(..., file=sys.stderr)` |
| `fab413_guide.curate` | none | none | none |

`_get_client()` and `pipeline.api_key_present()` both duplicate the
`ANTHROPIC_API_KEY_PIONEER` → `ANTHROPIC_API_KEY` lookup.

### Target shape

In `scrapers/claude_scraper.py`:

```python
HAIKU_MODEL = "claude-haiku-4-5-20251001"

def resolve_api_key() -> str | None
    # The single env lookup. _get_client() and pipeline.api_key_present()
    # both call this.

def call_haiku(
    prompt: str, *, label: str = "", max_tokens: int = 16384, retries: int = 3,
) -> str
    # One messages.create with the model constant. On stop_reason ==
    # "max_tokens", log a warning that names `label` and return the partial
    # text (callers already salvage via _parse_json_array). On exception,
    # retry with the existing backoff (20s, then ×3); re-raise on the last
    # attempt. Use the "pipeline" logger, not print.
```

Then:

- `_extract_events` calls `call_haiku(prompt, label=source_name or venue,
  retries=1)`. **Keep `retries=1` for scrapers** so a single-source failure
  costs the same wall-clock time as today (`BaseScraper.fetch` already
  isolates it). Note in the handoff that raising scraper retries is a
  one-line follow-up if rate limits start showing up in the weekly log.
- `fab413_guide.curate` calls `call_haiku(..., label="seasonal curation")`
  and drops its direct `_get_client()` import. It gains retry and the
  truncation warning; both are improvements, not regressions.
- Both miners keep calling `call_haiku` (no signature change for them other
  than optionally passing `label`).
- Delete the "Used by the fab413 miners; scrapers keep their own single-shot
  behavior" docstring — it will no longer be true.
- The `import sys` / `import time` inside `call_haiku` move to module level.

### Tests

`tests/test_claude_scraper.py` patches `scrapers.claude_scraper._get_client`
and sets `mock_client.messages.create.return_value`. That still works if
`call_haiku` goes through `_get_client()`; keep it that way so existing
mocks need no rewrite. Add:

- `call_haiku` returns the text and logs a warning containing `label` when
  the mock message has `stop_reason == "max_tokens"`.
- `call_haiku` with `retries=1` raises on the first exception with no
  sleep (monkeypatch `time.sleep` to assert it is not called).
- `call_haiku` with `retries=3` sleeps 20 then 60 and succeeds on the third
  attempt (monkeypatch `time.sleep` to record calls).
- `resolve_api_key` prefers `ANTHROPIC_API_KEY_PIONEER` over
  `ANTHROPIC_API_KEY` and returns `None` when neither is set (use
  `monkeypatch.delenv` / `setenv`).
- `pipeline.api_key_present()` behavior is unchanged (existing orchestration
  tests cover the pre-flight abort; confirm they still pass).
- `fab413_guide.curate` goes through `call_haiku`: monkeypatch
  `fab413_guide.call_haiku` to return a fixed JSON string and assert the
  kept list. If `tests/test_fab413.py` currently mocks `_get_client` for the
  guide, update that mock.

### Gate

`grep -rn "claude-haiku" --include='*.py' .` returns exactly one hit outside
`tests/`. `grep -rn "messages.create" --include='*.py' .` returns exactly one
hit outside `tests/`. Full suite passes.

---

## Phase 3 — shared scraper plumbing

This phase has two parts. Part A is a pure win; do it. Part B changes
category outputs at the margins and needs the offline replay check described
below; do it only if the replay shows zero or explainable differences.

### Part A — one HTTP fetch helper

Every hand-written scraper repeats:

```python
headers = {"User-Agent": ...}
resp = requests.get(url, headers=headers, timeout=20)
resp.raise_for_status()
```

with three different User-Agent strings across six files
(`BROWSER_UA` in `claude_scraper.py`, a byte-identical copy in `harriers.py`,
a shorter Mozilla string inline in `amherst_cinema.py`, and
`"PioneerValleyEvents/1.0 (community aggregator)"` in `ical.py`,
`localist.py`, `tribe_events.py`, `jones_library.py`, `forbes_library.py`).

Add to `scrapers/base.py`:

```python
POLITE_UA = "PioneerValleyEvents/1.0 (community aggregator)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."  # moved here

class BaseScraper:
    user_agent: str = POLITE_UA   # class attr; browser-imitating scrapers override

    def get(self, url: str, *, timeout: int = 20) -> requests.Response
        # requests.get(url, headers={"User-Agent": self.user_agent}, timeout=timeout)
        # then raise_for_status(); returns the response.
```

Then, per scraper:

- `ical.py`, `localist.py`, `tribe_events.py`, `jones_library.py`,
  `forbes_library.py`: replace the three lines with `resp = self.get(url)`.
  Keep `timeout=15` where a scraper currently uses 15 by passing it
  explicitly — or normalize everything to 20 and say so; either is fine,
  but be deliberate.
- `harriers.py`, `nepm_culture.py`, `claude_scraper.py`
  (`ClaudeHTMLScraper._get_html`): set `user_agent = BROWSER_UA` and use
  `self.get`. Delete the duplicate `BROWSER_UA` in `harriers.py`;
  `claude_scraper.py` re-exports `BROWSER_UA` from base (the miners and
  `nepm_culture.py` import it from there today — keep that import working
  or update the two importers).
- `amherst_cinema.py`: its inline UA is a shorter Mozilla string. Switch it
  to `BROWSER_UA`. This is the one place the exact UA changes; the site is
  server-rendered Drupal and has no reason to care, but note it in the
  handoff.
- `debug_scraper.py`: import `BROWSER_UA` from `scrapers.base` instead of
  redefining it.
- `ClaudePlaywrightScraper` keeps its own Playwright path; it already uses
  `BROWSER_UA` for the page context. No change beyond the import.

Tests that patch `scrapers.<module>.requests.get` (`test_localist.py`,
`test_tribe_events.py`, `test_ical.py`, `test_forbes_library.py`,
`test_claude_scraper.py`) will break if `requests.get` is no longer called
from that module's namespace. Two options; pick one and apply it uniformly:

1. Have `BaseScraper.get` call `requests.get` via the *calling* module — no,
   this is contortion. Don't.
2. Update those tests to patch `scrapers.base.requests.get` instead. This
   is the right fix. Mock response objects stay the same.

Also drop the per-scraper `seen = set()` / `key = f"{title}|{date}"` dedup
**only if** you can show it is redundant with the pipeline's `deduplicate`
for that source. It is not always redundant (`amherst_cinema` keys on
title|date|time, and pipeline dedup uses fuzzy title matching, which is
looser). Recommendation: leave the per-scraper dedup alone. It is five
lines each and it is doing slightly different things in each place.

### Part B — one `guess_category` (optional, gated)

Three keyword maps exist: `localist.CATEGORY_MAP` (default `"academia"`),
`tribe_events.CATEGORY_MAP` (default per subclass, matches against title +
category names), `jones_library.CATEGORY_MAP` (default `"community"`, also
imported by `forbes_library`). Dictionary insertion order decides which
keyword wins when several match, and the orders differ. Examples of
sensitivity:

- Jones checks `"book"`/`"reading"` → community *before* `"art"` → arts, so
  "Book Arts Workshop" is community at Jones but would be arts under the
  Localist ordering.
- Tribe has `"class"` → academia, which also matches "classical". It is safe
  today only because `"music"` is checked first.
- Localist has a long list of individual sport names → outdoor that no other
  map has; Jones has `"story"` → family and `"garden"` → outdoor that no
  other map has.

Target, if pursued:

```python
# scrapers/base.py
CATEGORY_KEYWORDS: list[tuple[str, str]] = [...]   # ordered, one merged list

def guess_category(text: str, default: str = "community") -> str
```

Build the merged list by concatenating the three maps in this order:
**music/film first, then arts, then family, then academia, then outdoor,
food, festival, then the Jones-only community words last**, so the more
specific signal wins over the more generic one. Each scraper keeps passing
its own default. `tribe_events` keeps joining title + category names before
calling it.

**Offline replay gate (required before committing Part B):** the committed
`docs/data/events.json` holds ~500 events from these sources (`umass`,
`mtholyoke`, `springfield-museums`, `historic-deerfield`, `hawks-reed`,
`jones-library`, `forbes-library`). Write a throwaway script in the
scratchpad (not the repo) that, for each such event, runs the *old*
per-scraper function and the *new* merged function on the same input (title
for Localist/Jones/Forbes; the Tribe API's category names are not in
`events.json`, so replay Tribe on title alone and note that limitation) and
prints every event whose category would change. Expected result: a handful
of changes at most, each one explainable by the ordering above and each one
arguably an improvement. If the list is long or contains regressions
(a concert becoming academia), stop, leave the three maps in place, and
record why in the handoff. Do not tune keywords to make the diff zero —
that is scope creep.

Delete the three per-module maps and their `guess_category` functions only
after the replay passes. `tests/test_localist.py` tests `guess_category`
directly; update its import.

### Gate

Part A: full suite passes; `grep -rn "User-Agent" scrapers/` shows exactly
one hit (in `base.py`). Part B: replay output is attached to the handoff and
the reviewer agrees with every listed change.

---

## Phase 4 — pipeline polish and housekeeping

Small, independent items. Each is optional; none should take more than a
few minutes. Do not re-architect `pipeline.py` — its seams were settled in
the first refactor.

### 4a. Named source results

`run()` builds `results` as a list of 4-tuples and the tuple is unpacked
positionally in `find_regressions`, `is_unhealthy`, the summary loop, and
`main()` (`item[3]`). Replace with:

```python
class SourceResult(NamedTuple):
    name: str
    url: str
    count: int
    error: str | None
```

and use attribute access everywhere. `PipelineResult.results` becomes
`list[SourceResult]`. Tests in `test_pipeline.py` that construct raw tuples
for `find_regressions` / `is_unhealthy` keep working (a NamedTuple accepts
positional construction and unpacks the same way), but update them to
construct `SourceResult` explicitly for readability.

### 4b. Extract the summary table

Move the block between `# ── Summary ──` and the closing rule in `run()`
into `log_summary(results, regressions, previous_counts, final_count)`.
`run()` should then fit on one screen: fetch loop, totals, prepare, summary
call, return. While there, drop the separate `date_filtered_count`
recomputation: `prepare_payload` already filters; if the "After date filter"
log line is worth keeping, have `prepare_payload` return the intermediate
count or log it there. Keep the log output text identical either way — the
handoff should show a before/after of one run's summary block from a
mocked-scrapers test.

### 4c. `previous_source_counts` uses the storage helper

It currently does its own `open`/`json.load` with a broad except. Use
`read_json(path, default_factory=dict)` and catch `JsonStorageError` as the
"treat as no history" case — but **be careful**: the existing behavior on a
corrupt `events.json` is to return `{}` (no regressions possible), not to
fail the run. Preserve that. A test in `test_pipeline_orchestration.py`
should pin it: corrupt `events.json` → run proceeds, no regression flagged.

### 4d. `debug_scraper.py` import-time side effect

`SOURCES = load_sources()` runs at import and calls `get_all_scrapers()`,
which reads `sources.json`. Move it under `if __name__ == "__main__":` with
a `main()` function. Nothing imports this module today, but the pattern is
the one wrong note in an otherwise consistent codebase.

### 4e. Plan files

The three earlier plan files are untracked and each is ~18 KB. Decide with
the owner: either commit them under a `docs/plans/` directory (they are
useful history of *why* the seams look the way they do) or delete them.
This plan file joins whichever fate they get. Do not leave them untracked
at the root.

### 4f. README / CLAUDE.md overlap

Not a code change. `README.md` ("Project structure", "How it works",
"Adding a new event source") and `CLAUDE.md` ("Architecture", "How Claude
scrapers work", "Rules") describe the same things. Leave both, but after
phases 1–3 land, make one pass to ensure neither describes deleted
functions (`_get_client` in the guide, `call_haiku`'s old docstring,
`BROWSER_UA`'s old home, the miners' separate loops). Update the
architecture tree if `fab413_common.py` was added.

### Gate

Full suite passes. `git diff --stat docs/data docs/413` is empty.

---

## Execution order and commit boundaries

One commit per phase (Phase 3 may be two: 3A and 3B). Suggested messages:

```
refactor: share the fab413 incremental mining loop
refactor: route every Haiku call through call_haiku
refactor: shared scraper fetch helper and user agents
refactor: merge scraper category keyword maps      (only if 3B passes its gate)
refactor: pipeline result names and summary extraction
chore: file the refactor plans under docs/plans     (or delete)
```

Phases 1 and 2 both touch `call_haiku` and the miners; if different agents
run them, run them sequentially, not in parallel. Phase 3 touches every
scraper file and their tests; nothing else in flight should edit
`scrapers/`. Phase 4 touches `pipeline.py` only.

## Verification commands

From the repository root, with the project interpreter:

```bash
python3 --version
python3 -m pytest -q
python3 -m ruff check .
git diff --check
git diff --stat docs/data docs/413        # must be empty after every phase
grep -rn "claude-haiku" --include='*.py' . | grep -v '^./tests'   # 1 hit after phase 2
grep -rn "messages.create" --include='*.py' . | grep -v '^./tests'  # 1 hit after phase 2
grep -rn "User-Agent" scrapers/           # 1 hit after phase 3A
```

The frontend browser tests (`test_frontend_ui.py`) need Chromium; if it is
not installed locally run `python3 -m playwright install chromium` once.
They are unaffected by this plan but are part of the full-suite gate.

## Final handoff and acceptance criteria

The executing agent's final report must list, per phase: files changed,
net line delta, the intentional behavior changes (expected: the events
miner now aborts after three consecutive failures; the guide's curation
call now retries and warns on truncation; `amherst-cinema` sends the shared
browser UA; any category changes from 3B with the replay output), test
results, and anything deferred with the reason.

The reviewer must verify:

1. No file under `docs/data/` or `docs/413/` changed.
2. No prompt text changed (diff the `EXTRACT_PROMPT` / `CURATE_PROMPT`
   constants against `main`).
3. Every test that previously monkeypatched a miner attribute still
   exercises the real loop (a test that passes because the patched name is
   no longer read is a silent regression — check `mine_batch`, `save_store`,
   `fetch_feed`, `load_episodes` are all still consulted at call time).
4. Scraper tests patch `requests.get` at the location it is actually called
   from after Phase 3A.
5. Net line count of Python outside `tests/` went down.
6. `CLAUDE.md` and `README.md` name no function that no longer exists.
