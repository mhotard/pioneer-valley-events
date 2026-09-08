# Handoff: separate pipeline collection, decisions, and publication

## Objective

Refactor `pipeline.py` so event collection/transformation, source-health decisions,
and publication are independently understandable and testable. Preserve the event
data contract and CLI behavior, except for the explicitly identified bug fix:
an unhealthy full run must exit unsuccessfully **before** modifying published
events or archives.

Execute this work, including tests and documentation updates. Do not stop at a
proposal. Keep the structural refactor and the publication-order fix separately
reviewable, preferably as separate commits when committing is authorized.

## Repository context and starting checks

- Repository: `/Users/michaelhotard/Documents/ClaudeTest/pioneer-valley-events`.
- Read applicable `AGENTS.md` files, `CLAUDE.md`, and `README.md` before editing.
- Read `pipeline.py`, `scrapers/base.py`, `scrapers/__init__.py`,
  `tests/test_pipeline.py`, `tests/test_archive.py`, `tests/test_schema.py`, and
  `.github/workflows/weekly-update.yml`.
- Inspect `git status --short`; preserve unrelated changes.
- The review baseline was 161 passing pytest tests and passing Ruff checks.
  Re-establish the baseline: the checkout may have changed.
- CI uses Python 3.12. The review's local run used Python 3.9, with a
  urllib3/LibreSSL warning. Prefer the existing Python 3.12 environment if
  available; report the interpreter actually used. Do not change dependencies
  or system Python just to silence that warning.

The pipeline runs weekly in GitHub Actions. Scrapers return `Event` objects;
the pipeline converts them to dictionaries, filters dates, deduplicates, sorts,
and writes `docs/data/events.json` plus yearly archives. GitHub Pages serves
the static frontend. There is no application server.

## Scope

Expected changes:

- `pipeline.py`.
- `tests/test_pipeline.py`, potentially a focused new
  `tests/test_pipeline_orchestration.py`, and small additions to archive tests.
- Targeted updates to `CLAUDE.md` and/or `README.md` describing the pipeline's
  actual behavior and new testing seams.

Do not change scraper extraction, source configuration, event IDs, deduplication
criteria, frontend code, email, podcast mining, dependencies, or workflow files.
Do not add concurrency, a service framework, a database, or a generic storage
layer. Keep the extracted functions in `pipeline.py` unless a concrete need
for another module emerges.

Archive corruption handling and atomic file replacement belong to a separate
refactor. This task guarantees that a rejected run does not start publication;
it does not make events-plus-archives an atomic multi-file transaction.

## Current behavior and confirmed defect

`run(scrapers, dry_run=False)` currently reads previous source counts, fetches
events, prepares data, calculates regressions, logs a summary, and writes files.
`main()` checks the unhealthy-source threshold only after `run()` returns.

An isolated reproduction with all sources failing showed:

1. The existing events file was overwritten with an empty event list.
2. The command then exited with status 1.

GitHub Actions stops before committing this output, but local files have already
changed. The final implementation must assess health before calling publication.

## Behavior contract to preserve

### Events and dates

- Payload remains `{"generated": "YYYY-MM-DD", "events": [...]}`.
- Retain all existing event fields and ID generation.
- Filter first, deduplicate second, sort last.
- Date boundaries are inclusive: run date minus `DAYS_PAST` through run date
  plus `DAYS_FUTURE` (currently 3 and 90).
- Preserve deduplication's `similarity > 0.82`, venue compatibility, richer
  description preference, first-event tie behavior, and source-order sensitivity.
- Sort using `(event["date"], event_time_key(event))`. Unknown/all-day times
  precede timed events; do not sort displayed times as strings.
- Source counts represent raw fetched events, before filtering and deduplication.
- Capture one date for the pipeline run and use it for date filtering,
  `generated`, and newly assigned archive `first_seen`. Existing `first_seen`
  values remain unchanged. Removing import-time date capture is intentional;
  scraper-internal clocks remain out of scope.

### Health and CLI

- A source with a truthy error is unhealthy.
- A zero-result source without an error is a regression only if its previous
  published count is at least `MIN_PREV_FOR_REGRESSION` (currently 5).
- Do not count an errored source again as a regression.
- Reject a full run only when:
  `unhealthy_count > source_count * MAX_ERROR_FRACTION` (currently 0.34).
- Preserve the strict `>` boundary, not `>=`.
- Empty source collections are not rejected by the existing threshold rule;
  preserve that behavior rather than introducing a new policy.
- Previous counts still come from the previous published events, with the
  existing missing/unreadable-file fallback. Do not change their interpretation.
- `--source NAME` fetches only that source and always behaves as a dry run.
  Single-source runs do not apply the full-run health rejection rule.
- Unknown sources exit 1 before fetching or publication.
- A selected source requiring an API key triggers the existing preflight check,
  including in dry runs. Missing keys exit 1 before fetching or publication.
- Preserve API key precedence: `ANTHROPIC_API_KEY_PIONEER`, then
  `ANTHROPIC_API_KEY`.
- Full dry runs still assess health and exit 1 when unhealthy. They never
  modify events or archives. Logs may still be written.
- Healthy full runs and permitted partial failures still publish and succeed.
- Preserve useful per-source OK/ZERO/ERROR/regression logs, count summaries,
  dry-run previews, and publication messages. Exact whitespace is not a contract.

### Publication

- Preserve `events.json` formatting: indent 2 and `ensure_ascii=False`.
- Preserve compact archive formatting and current event-year bucketing.
- Archive only the final filtered/deduplicated event set.
- Preserve existing archive records, refresh matching IDs, and retain original
  `first_seen` values. Do not rewrite the archive merge algorithm.
- Publication errors continue to propagate to an unsuccessful command; do not
  swallow them or claim that partially completed writes were rolled back.

## Suggested function boundaries

Use the smallest implementation satisfying these responsibilities. Names can
vary, but tests must exercise behavior rather than enforce internal naming.

1. **`prepare_payload(events, *, run_date)`**: pure transformation of event
   dictionaries into the existing payload. Uses explicit date filtering,
   existing deduplication, and chronological sorting. Does not modify its inputs.
2. **`run(scrapers, *, previous_counts, run_date)`**: invokes each scraper's
   existing `fetch()` boundary, gathers raw counts/errors, prepares the payload,
   and computes regressions. Returns a small `PipelineResult` dataclass with
   `payload`, `results`, and `regressions`. It may log; it must not read or write
   published data or archives. Keep the existing source-result tuples unless
   changing them has a concrete benefit. Additional count fields are optional
   only if needed to retain diagnostic logging.
3. **`is_unhealthy(results, regressions)`**: pure application of the existing
   full-run threshold, including the empty-results case. Whether a CLI run is
   full or single-source belongs to orchestration, not this helper.
4. **`publish_payload(payload, *, output_path, archive_dir)`**: writes the event
   file and calls `update_archive` with explicit directory and
   `today=payload["generated"]`. No scraping or health policy here.
5. **`main(...)`**: selects sources, checks credentials, captures the run date,
   reads previous counts, calls collection, checks health, and either previews
   or publishes. Supporting `main(argv=None)` is a useful test seam, not a
   requirement to redesign the command interface.

Allow explicit run dates in `filter_by_date` while preserving existing one-argument
callers if convenient. Compute a default date at call time, not import time.
Remove or replace stale `DATE_MIN`/`DATE_MAX` globals and their references.

Search all callers before changing `run()`; none outside `pipeline.py` were found
in the reviewed checkout. It is an internal API and may change. Keep established
helpers such as `deduplicate`, `find_regressions`, and `update_archive` usable by
their existing tests.

**Path pitfall:** current defaults such as `path=OUTPUT_PATH` and
`archive_dir=ARCHIVE_DIR` are captured at function definition time. Patching a
module constant does not change them. Orchestration must explicitly pass the
selected output/archive paths. If adding configurable defaults, resolve `None`
inside the function instead of capturing mutable configuration in signatures.

## Execution sequence and gates

### Phase 1 — characterize existing behavior

Add offline fixtures and orchestration tests before structural edits. Use fake
`BaseScraper` subclasses that return fixed `Event` objects or raise in `_fetch()`.
Exercise the real `BaseScraper.fetch()` error isolation; do not replace it with
a mock that accidentally hides contract differences.

Use `tmp_path` for published files and archives. Before extraction, explicitly
patch the old read/write helpers as necessary to prevent captured default paths
from reaching repository data. Patch `setup_logging()` in CLI tests to avoid
creating/pruning real logs. Clear both API-key variables with `monkeypatch` and
set only dummy values when a test needs a key.

Create a hand-authored expected payload from a small representative fixture:
multiple sources, an out-of-window event, cross-source duplicates with different
description lengths, different venues, and several times on one date. Do not
compute expected output using the production functions being tested.

Gate: existing tests and new characterization tests pass. Record the unhealthy
publication bug with a temporary characterization assertion or a narrowly scoped
strict expected-failure test. Do not leave either in its old form at completion.

### Phase 2 — extract responsibilities

Introduce the boundaries above, pass paths/date explicitly, and update callers.
Retain the existing publication/check order temporarily if needed to demonstrate
that structural changes alone preserve behavior. Keep this intermediate state
local; do not publish it as a completed fix.

Gate: representative payload and archive comparisons are unchanged. Collection
and pure transformations have no publication side effects. Existing tests pass.
Any intentional differences caused by using a single run date are documented.

### Phase 3 — fix publication ordering

Move full-run health rejection before publication. Healthy full runs publish;
unhealthy full runs exit 1 without touching either destination. Keep dry-run
and single-source behavior as specified above.

Replace the temporary defect characterization/expected failure with ordinary
passing regression tests. Do not leave an xfail for a defect this task fixes.

Gate: unhealthy-run tests fail against the original ordering and pass against
the new implementation. Test both errors and silent yield regressions.

### Phase 4 — verify and document

Run focused tests, then the complete suite and lint. Update only relevant
maintainer documentation. Inspect the final diff for accidental data changes,
unrelated cleanup, changed thresholds, or modified deduplication semantics.

## Required tests

Use parameterization where it improves clarity. Existing tests may satisfy a
case; extend them rather than creating redundant copies.

### Pure transformation and health

| Case | Required assertion |
| --- | --- |
| Date bounds | Keep days -3 and +90; exclude -4 and +91 for a fixed run date. |
| Repeated explicit dates | Two calls with different run dates use their own windows, without module reloads. |
| Payload date | `generated` equals the supplied date. |
| Order of processing | Fixture matches filter → deduplicate → chronological sort. |
| Deduplication | Richer description wins; equal-description ties keep the first; different venues remain separate. |
| Times | On the same date, missing time precedes 9 AM, noon, and 7 PM; midnight sorts before morning. Use distinct titles to avoid accidental deduplication. |
| Input preservation | Input list order and event dictionaries are unchanged after preparation. |
| Raw counts | Source counts include events later filtered or deduplicated away. |
| Regression boundaries | Previous count 4 plus zero results is permitted; count 5 is a regression; errored sources are counted only once. |
| Threshold | 1 unhealthy of 3 is permitted; 2 of 3 rejected; 17 of 50 permitted; 18 of 50 rejected. |
| Mixed failures | Error count plus regression count determines health, not either count alone. |
| No sources | No division error and no threshold rejection. |

### Collection and CLI orchestration

| Case | Required assertion |
| --- | --- |
| Collection boundary | Fake sources each fetch once; returned result contains payload/results/regressions; no event or archive files are written. |
| Healthy full run | Exit succeeds; expected events file and archive are written. |
| Permitted partial failure | One failed source of three does not prevent publishing the successful sources. |
| All sources fail | Exit 1; pre-existing events and archive files remain byte-for-byte unchanged. |
| Yield regressions | Seed previous counts of at least 5 for two of three zero-result sources; exit 1; both destinations unchanged. |
| Rejection with no prior files | Failed run creates neither events.json nor archives. |
| Healthy dry run | Exit succeeds; existing files unchanged; no files created in a separate first-run case. |
| Unhealthy full dry run | Exit 1; no publication. |
| Single source | Only selected scraper fetches; no publication with or without explicit `--dry-run`. A failing selected source still bypasses full-run health rejection. |
| Unknown source | Exit 1; no scraper fetch and no publication. |
| Missing API key | With selected key-requiring source, exit 1 before fetching; test full and dry-run modes. |
| Selected source key scope | An unselected key-requiring source does not block a selected source that needs no key. |
| Path isolation | Previous counts are read from the supplied temporary output path, and publication uses supplied temporary paths. |
| Diagnostics | Logs retain source status and counts, failure reason, dry-run indication, and successful publication indication as applicable. Avoid whitespace snapshots. |
| Write failure | Simulated publication error reaches an unsuccessful command; no false success is reported. Do not assert multi-file rollback. |

For unchanged-file cases, seed an archive containing a record that would be
updated by the proposed payload. Compare raw bytes before and after, and verify
that publication was not called. Merely checking the final event count is not
enough to prove writes were prevented.

### Publication and archives

- Verify `generated` and new archive `first_seen` share the supplied run date.
- Verify publication passes only the final event set into archive updating.
- Retain tests for repeat runs, refreshed descriptions with preserved
  `first_seen`, old records retained after leaving the publication window,
  event-year bucketing, and sorting.
- Exercise a December/January event set so two archive files are checked.
- Check representative serialization, including a non-ASCII event title,
  without introducing large generated snapshot files.

## Verification commands

Run from the repository root. These tests require no live scraping or API key.

```bash
python3 --version
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_pipeline.py tests/test_archive.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
python3 -m ruff check --no-cache .
git diff --check
git diff --stat
git status --short
```

Include any new orchestration test file in the focused command. Use the project's
existing Python 3.12 interpreter in place of `python3` when available.

Do not run `pipeline.py` against real sources, source shell files containing
credentials, send email, regenerate published JSON, or deploy. Offline fixtures
are sufficient for this task. If a test unexpectedly attempts network access,
fix its isolation rather than supplying credentials.

## Agent handoff and completion criteria

This work should be executed sequentially because implementation and tests touch
the same orchestration boundary. If different agents handle phases, each handoff
must include changed files, actual function signatures, tests run/results,
remaining failures, and whether the publication-order bug has been fixed yet.
Do not have multiple agents independently rewrite `pipeline.py`.

A final reviewer should inspect the complete diff and verify:

1. Pure transformation, collection, health evaluation, and publication are
   separate without unnecessary abstractions.
2. Health rejection precedes every full-run publication path.
3. CLI behavior and successful output remain compatible with the contract above.
4. All output/archive paths and the pipeline date are controllable in tests.
5. Both error-driven and regression-driven rejection have passing regression tests.
6. No temporary xfails remain for the fixed bug; the full suite and lint pass.
7. No scraped data, source configuration, credentials, dependencies, or unrelated
   files changed.

The executing agent's final report must state the changes, the intentional
behavior fixes, interpreter and verification results, and remaining limitations.
Explicitly retain the limitation that publication is not a multi-file transaction
and existing corrupt-archive handling was not repaired in this task.
