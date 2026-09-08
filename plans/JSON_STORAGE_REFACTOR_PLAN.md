# Handoff: reliable JSON storage for archives and mining checkpoints

## Objective

Give persistent JSON files a small, shared storage boundary. Preserve successful
output and domain behavior while making two intentional reliability fixes:

1. An existing corrupt or unreadable historical store must not be treated as an
   empty store and overwritten.
2. A failed serialization or interrupted write must not truncate the previous
   destination file. Save through a temporary sibling file and atomic replacement.

Execute the implementation, tests, and documentation updates. Keep helper
extraction and intentional failure-behavior changes distinguishable in review.
Do not build a generic repository framework or rewrite domain merge logic.

## Starting context and dependency on the first refactor

Repository: `/Users/michaelhotard/Documents/ClaudeTest/pioneer-valley-events`.

Read applicable repository instructions, `CLAUDE.md`, `README.md`, and
`PIPELINE_REFACTOR_PLAN.md`. Inspect the current checkout and its diff before
editing. The first refactor is committed as `8c0f7a3`
(`refactor: separate pipeline publication from health checks`). A local review
found no blocking issue and verified 188 passing tests and passing Ruff checks
under Python 3.9.6. The existing urllib3/LibreSSL warning remained; Python 3.12
CI execution was not verified by that review.

Build on this commit or its descendants. The pipeline exposes `prepare_payload`,
`PipelineResult`, `run`, `is_unhealthy`, and `publish_payload`.
`main(argv=None, *, output_path=None, archive_dir=None, run_date=None)` returns
an integer status, and the script entry point uses `sys.exit(main())`.
Keep this status-returning test interface. Do not recreate the old pipeline.
Preserve any newer unrelated changes. If functions move, locate the equivalent
responsibilities rather than relying on old line numbers.

`publish_payload` already creates the output parent and archive directory. Keep
that caller-owned setup and replace its direct JSON write with the atomic helper.
`update_archive` remains responsible for archive merging and is the integration
point for strict historical reads and atomic archive writes. The checkpoint
and snapshot storage code was not changed by the first refactor.

Read:

- `pipeline.py`: `update_archive`, `publish_payload`, `previous_source_counts`.
- `fab413_miner.py`: `load_store`, `save_episodes`, and the checkpoint in `main`.
- `fab413_entities.py`: `load_store`, `load_episodes`, and its checkpoint loop.
- `tests/test_archive.py`, `tests/test_pipeline_orchestration.py`,
  `tests/test_fab413.py`, and `.github/workflows/weekly-update.yml`.
- Representative stored JSON structure, read-only. Do not regenerate data.

Establish a fresh test/lint baseline. CI targets Python 3.12; use the existing
project interpreter and report its version. Use 188 passing tests as the reviewed
starting point, not a fixed final count or the earlier 161-test baseline.

## Scope and file policy

Add a small root-level `json_storage.py` and focused tests. Modify only the
callers below, their tests, and relevant documentation.

| File or responsibility | Read policy | Write policy |
| --- | --- | --- |
| `archive-YYYY.json` in `update_archive` | Missing file starts an empty archive; existing invalid/unreadable file fails | Atomic compact JSON replacement |
| `fab413_episodes.json` in `save_episodes` | Missing file starts an empty snapshot; existing invalid/unreadable file fails | Atomic compact JSON replacement |
| `fab413_mentions.json` in event miner | Missing file starts a fresh checkpoint; existing invalid/unreadable file fails | Atomic compact JSON after each successful batch |
| `fab413_entities.json` in entity miner | Same checkpoint policy | Same checkpoint policy |
| `events.json` in `publish_payload` | No new read required for replacement | Atomic JSON with existing indentation |
| `fab413_entities.load_episodes` | Corpus is required; missing or invalid input fails | None |

Explicitly leave `previous_source_counts`' best-effort fallback unchanged: it is
an advisory health baseline, not a historical store being merged. Do not
mechanically replace every JSON read in the repository. Leave optional seasonal
reads, guide/dashboard writers, frontend files, email, source configuration,
and workflow files out of scope.

Do not change prompts, model/API behavior, retry limits, batch size, extraction
validation, event identity, deduplication, recurrence, or source health thresholds.
Do not combine the two mining loops into a generic processing engine.

## Storage API and implementation requirements

Suggested API; equivalent simple names are acceptable:

```python
read_json(path, *, default_factory=None)
write_json_atomic(path, value, *, indent=None, separators=None)
```

### Reading

- Read UTF-8 explicitly.
- Return a fresh default only on `FileNotFoundError` and only when the caller
  supplies a factory. Without a factory, propagate the missing-file error.
- Do not catch all `OSError` and return an empty store. Permission errors,
  directories passed as files, invalid encoding, and malformed JSON must fail.
- Failure diagnostics must identify the path. If wrapping exceptions, preserve
  the original exception as the cause and avoid logging full stored content.
- Keep domain defaults and domain validation with the callers. The shared
  helper should not know about events, episodes, or mining GUIDs.
- Factories must not reuse a mutable default between calls.

### Writing

1. Create a uniquely named temporary file in the destination's parent directory,
   so replacement stays on the same filesystem. Do not use a fixed `.tmp` name
   or the system temporary directory for this operation.
2. Serialize the entire new value to that file using UTF-8 and
   `ensure_ascii=False`. Preserve each caller's existing indent/separators and
   trailing-newline behavior; do not sort object keys as unsolicited cleanup.
3. Flush and `os.fsync` the temporary file, then close it.
4. Use `os.replace` to replace the destination only after serialization succeeds.
5. In a `finally` path, remove a remaining temporary file after ordinary failure.
   Cleanup must not hide the primary exception. A missing temporary file after
   successful replacement is normal.

The helper requires an existing parent directory. Keep directory creation with
the caller that already owns it; do not silently create arbitrary directory trees.
Accept `str` and `Path` inputs. Avoid new dependencies.

State the guarantee precisely: readers see the old complete file or the new
complete file; failures before replacement leave the old file intact. A hard
kill may leave an orphan temporary file, which subsequent reads must ignore.
Do not add a startup scan that deletes unknown files.

This is not a power-loss durability guarantee: directory fsync and cross-platform
crash guarantees are out of scope. It also does not prevent lost updates from
concurrent writers. Existing operations assume a single writer.

## Minimal domain validation

Malformed JSON is not the only unsafe input: a valid JSON value such as `null`,
`[]`, or `{}` can also be mistaken for an empty history or fail unpredictably.
Add narrow checks needed to merge/reuse each existing store safely:

- Archives: object containing an `events` list of objects with usable nonempty
  string IDs and date strings needed for existing sorting/year behavior. Reject
  duplicate stored IDs rather than silently collapsing historical rows.
- Episode snapshots: object containing an `episodes` list of objects with
  nonempty string GUIDs and the date/title/link/text fields used by the current
  miners. Reject duplicate stored GUIDs rather than silently dropping rows.
- Mining checkpoints: object containing `mined_guids` as a list of strings and
  `mentions` or `entities` as a list of objects. Do not attempt to establish
  one-to-one GUID/result relationships: successful episodes may yield zero or
  multiple results, and result rows currently do not store a GUID.
- Required corpus loading should use the same episode-shape expectations as
  snapshot merging; share a small episode validator if needed, not a schema
  framework.

Inspect committed data read-only before finalizing these checks. Accept optional
fields and harmless extras; preserve records' extra fields. Do not introduce
strict calendar-date validation, new category enums, or LLM result sanitization.
Do not silently repair existing data. If a proposed shape check rejects actual
committed data, report the specific shape mismatch without dumping the corpus,
and resolve compatibility before enabling the check.

Missing-file factories must return valid empty envelopes with the required keys.
An existing `{}` is not the same as an intentionally missing file. Validators
must raise before writing the affected destination.

## Domain behavior to preserve

### Event publication and archives

- Preserve the first refactor's health-before-publication gate and explicit run
  date/path handling. Never put file writes back inside collection.
- `events.json` remains indented by 2; archives remain compact.
- Archive records remain keyed by event ID and bucketed by the event date's year.
- Re-scraped records refresh details but preserve existing `first_seen`.
- Old records survive even when absent from this week's publication window.
- Keep existing sorting and the returned `{year: added_count}` result.
- Continue archiving only the final filtered/deduplicated event list.

Each destination is replaced independently. If `events.json` was replaced and a
later archive operation fails, the command fails but the earlier replacement is
not rolled back. Similarly, one year's archive may succeed before another fails.
Do not promise multi-file transactions or require them in tests.

### Raw episodes

- Snapshot merging retains stored episodes that disappeared from the RSS feed.
- New fetched details replace existing details for the same GUID.
- Preserve reverse-date ordering, count calculation, and output structure.
- `load_episodes` remains a required-input operation; a missing corpus must not
  look like a successful zero-work mining run.

### Mining checkpoints

- Load and validate the checkpoint before spending API calls on new work.
- Skip already mined GUIDs, preserving episode order and `--limit` behavior.
- A successful batch checkpoints its result rows and all its episode GUIDs
  together in the same replacement. Zero extracted rows still count as success.
- A failed extraction batch does not checkpoint its GUIDs.
- Preserve each miner's current extraction-failure policy: the event miner
  continues; the entity miner aborts after three consecutive failures and resets
  that counter after a successful batch.
- A storage failure must abort immediately, not enter the extraction-error
  skip/retry path. Keep checkpoint writing outside the extraction `try/except`.
- After a failed save, the last complete checkpoint remains readable. A fresh
  invocation resumes from that checkpoint; it may repeat an API call for the
  uncommitted batch. Do not promise exactly-once API execution.
- Do not report a batch as durably saved before replacement completes. Existing
  extraction progress messages can remain if clearly describing extraction.

## Execution phases and gates

### Phase 1 — baseline and fixtures

Coordinate with the first refactor owner, inspect the current diff, and run the
current suite/lint. Build tiny hand-authored fixtures for archives, snapshots,
and both mining checkpoints. All writes use `tmp_path`.

Read real store shapes only to check compatibility; never mutate repository
data during tests. Patch module paths or add optional path parameters resolved
at call time. Beware Python defaults such as `path=OUTPUT_PATH`, which capture
the old constant and defeat tests that only patch the constant afterward.

Gate: existing success behavior is represented by tests and baseline results
are recorded. Any pre-existing failures are clearly separated from new failures.

### Phase 2 — shared storage helper

Implement and test the narrow read/write API before moving callers. Use injected
failure via monkeypatching at the relevant operation, not real disk exhaustion,
permission changes, process termination, or network access.

Gate: failure at serialization, flush/fsync, or replacement leaves old bytes
unchanged, propagates the error, and cleans temporary files on ordinary failure.

### Phase 3 — migrate callers and protect history

Migrate archive reads/writes, episode snapshots, checkpoints, required corpus
loading, and the event publisher. Add caller-owned envelope checks. Preserve
successful merge/formatting behavior and explicitly test the intentional change
from silent empty fallback to failure for damaged existing stores.

Gate: success fixtures retain expected payloads; corrupt/unreadable affected
stores remain unchanged; the first refactor's orchestration tests still pass.

### Phase 4 — checkpoint recovery and final review

Exercise both miner entry points using deterministic fake feed/corpus and
`mine_batch` results. Include multi-batch interruptions and restart from disk.
Update documentation with exact guarantees and limitations.

Gate: complete suite/lint pass, generated JSON is unchanged, and the diff contains
only storage-related implementation, tests, and documentation.

## Required verification cases

Existing tests may cover a case; extend them rather than duplicate them.

### Shared helper tests — suggested `tests/test_json_storage.py`

| Case | Assertion |
| --- | --- |
| Missing optional file | Fresh default returned; separate calls do not share lists/dicts |
| Missing required file | Error propagated with identifiable path |
| Malformed JSON / invalid UTF-8 | Error propagated; file unchanged |
| Permission/read error | Simulated error propagated; no empty fallback |
| Successful replacement | New JSON fully readable; Unicode retained; formatting preserved |
| First write | Absent destination created with complete JSON |
| Serialization fails partway | Existing destination byte-identical; missing destination stays missing |
| Flush/fsync fails | Existing destination unchanged; error propagated |
| Replacement fails | Existing destination unchanged; temporary file cleaned |
| Temporary location | Unique temporary sibling used, not a fixed/shared filename |
| Cleanup | No leftover temporary files after success or ordinary failure |
| Cleanup itself fails | Original write error remains the primary reported error |
| Missing parent | Fails without creating an unexpected directory tree |

Do not test atomicity through a timing-sensitive concurrent reader loop. Verify
the old destination still exists with its original bytes immediately before the
replacement call, and that the temporary file already contains complete valid
JSON. The operating system's `os.replace` supplies the replacement primitive.

### Archive and publisher tests

- Strengthen the existing collection-no-I/O test: its empty `tmp_path` assertion
  does not intercept publication paths, because `run` never receives that path.
  Patch publication/read helpers to fail if called, and reject file opens during
  the fake-scraper collection call. This verifies the boundary without permitting
  a regression to write into repository data.
- Extend the existing missing-key CLI parameterization with `[]` and
  `["--dry-run"]`. The committed tests currently exercise only selected-source
  variants; full-run preflight should also remain covered.
- First archive creation, repeat upserts, refreshed details with original
  `first_seen`, old records retained, chronological ordering, year boundaries,
  and unchanged return counts.
- Corrupt JSON, invalid envelopes/rows, duplicate stored IDs, and unreadable
  archive all fail without replacing that archive.
- Inject a replacement failure; old archive remains readable and unchanged.
- Publisher uses atomic writing while preserving pretty JSON and its explicit
  run date. Existing health rejection/dry-run/single-source tests remain green.
- Test per-file guarantees only. Do not assert that an earlier successful file
  is rolled back when a later file fails.

### Episode snapshot tests

- Missing snapshot creates the correct envelope and count.
- Merging new episodes retains old GUIDs absent from the fetched feed.
- A repeated GUID refreshes details without creating another stored row.
- Reverse-date ordering and Unicode survive serialization.
- Corrupt or structurally unsafe existing snapshot fails before replacement.
- Replacement failure leaves the prior snapshot byte-identical.
- Required corpus loading rejects missing/invalid input.

### Mining tests — parameterize shared cases across both miners

Use small batches (patch batch size if useful), fake episode dictionaries, and
fake `mine_batch` results. Patch CLI arguments and all store/corpus paths. Do
not call the real feed, Anthropic API, or email. No retry sleeps are needed.

1. Fresh checkpoint: successful batch saves rows and GUIDs together.
2. Existing checkpoint: already mined GUIDs do not reach `mine_batch`.
3. Successful empty batch: GUIDs saved with no added rows.
4. Extraction failure: failed GUIDs absent from the next saved checkpoint.
5. Two batches, second save fails: disk retains exactly the first successful
   checkpoint; failure aborts; no later batch is attempted.
6. Restart after that failure: reload from disk, skip first batch, retry the
   uncommitted second batch, and do not duplicate first-batch results.
7. Corrupt/unreadable/invalid checkpoint: fail before extraction and preserve
   bytes; do not emit a successful completion message.
8. Preserve `--limit` and no-work behavior.
9. Entity miner: three consecutive extraction failures abort with saved progress
   intact; an intervening success resets the counter.
10. Event miner: an extraction failure still allows a later successful batch.

For each unchanged-file test, compare bytes before and after, not just counts.
Do not derive expected fixture contents by calling the production merge logic.

## Verification commands

From the repository root, using the project's current interpreter:

```bash
python3 --version
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_json_storage.py tests/test_archive.py tests/test_fab413.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
python3 -m ruff check --no-cache .
git diff --check
git diff --stat
git status --short
```

Add newly created checkpoint/snapshot tests to the focused command. Do not run
live scrapers, mining scripts, email, regeneration, or deployment. Do not source
shell files containing credentials. If a test reaches the network, fix isolation.

## Final handoff and acceptance criteria

Different agents may execute phases sequentially. Each handoff should include
changed files, actual helper signatures, test results, known failures, and the
state of the first refactor integration. Do not assign overlapping edits to
`pipeline.py` to agents running independently.

The final reviewer must verify:

1. Only genuinely missing optional stores receive empty defaults.
2. Existing damaged stores cannot silently become empty replacement histories.
3. Every in-scope writer serializes before replacing its destination.
4. All required failure-path and restart tests pass offline.
5. Domain behavior, JSON formatting, and first-refactor guarantees are preserved.
6. No output data or unrelated code has changed.
7. Documentation accurately distinguishes per-file atomic replacement from
   multi-file transactions, power-loss durability, and concurrent-writer safety.

The executing agent's final report must list intentional behavior changes,
interpreter and verification results, integration with the first refactor, and
remaining limitations. Explicitly state that previously damaged data is not
automatically repaired and that an uncommitted mining batch may be re-extracted.
