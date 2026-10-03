# Site improvement implementation review

Completed locally October 3, 2026. All packages A–F and integrated release
checks are complete; no push or deployment was performed.

Visitors previously had to separate past listings from upcoming events manually,
could not restore a filtered view from its URL, and had incomplete keyboard and
failure recovery support. Maintainers had to reconstruct update failures from
raw logs. This change improves discovery and trust while keeping the static
vanilla JavaScript site and existing weekly collection workload.

## Local review

Implementation branch: `codex/site-improvements`. The initial user changes and
handoff documents were preserved in baseline commit `6d1c289`, after all 324
baseline tests and Ruff passed. Packages were implemented in isolated worktrees,
reviewed, and integrated sequentially following the handoff dependencies.

Review the entire local change with:

```sh
git diff main...codex/site-improvements
git log --oneline main..codex/site-improvements
```

## Behavior changes

- Upcoming listings default to today in `America/New_York`. Quick choices cover
  today, today through six days ahead, the remaining/upcoming weekend, and all
  published dates. Search includes town; filters, views, and calendar selection
  restore from the URL and browser history.
- Existing freshness warnings remain visible. Both historical podcast pages
  now explain their actual generation date and represented coverage, recover
  from JSON failures, and retain useful text and town navigation when optional
  maps or charts fail. Historical mentions do not acquire current event dates.
- Event details have a labeled, trapped-focus modal with Escape and opener
  focus return. Background controls become inert. Mobile filters collapse
  while their active summary and the data warning remain visible. Calendar
  controls work with a keyboard; focus, contrast, touch targets, and reduced
  motion have focused improvements.
- Published event links and images pass HTTP/HTTPS guards before activation.
  Extracted event records validate actual dates, optional times, and URLs.
  A nonempty all-invalid extraction is a source error; valid partial results
  remain eligible under the existing health rules.
- Direct links open only the exact published event ID, even outside active
  filters. Missing IDs show an unavailable dialog; clipboard denial offers a
  selected manual-copy field. One-event calendar downloads use New York local
  times with an explicit timezone definition, or an explained all-day reminder
  when the time is unknown. Stable IDs, UTF-8 folding, escaping, and exclusive
  all-day end dates follow RFC 5545. Uncertain end times do not acquire a
  duration. Real update dates and adjacent freshness warnings remain visible.
  Malformed published rows now produce the recoverable unavailable state.
- Pipeline JSON diagnostics and Actions summaries explain source counts,
  regressions, rejected records, workflow stages, publication decisions, and
  individual write outcomes. Safe artifacts exclude credentials, source URLs,
  environment values, raw exceptions, and raw logs.

## Validation

- `python3 -m pytest -q`: **567 passed** in 40.73 seconds. The existing local
  Python 3.9/urllib3 LibreSSL warning remains; CI uses Python 3.12.
- `python3 -m ruff check .`: **passed**. `git diff --check`: **passed**.
- **22 integrated scenarios** passed and their screenshots were inspected at
  1280px and 390px: fresh/stale upcoming listings, a shared filtered view,
  stale event details with manual-copy fallback, an exact direct event link,
  missing event ID, unavailable events JSON, historical seasonal evidence,
  the dashboard with third-party assets blocked, and each secondary-page
  failure state. No horizontal page overflow or uncaught browser errors.
- **Two actual integrated downloads** parsed as single VEVENT calendar files,
  retaining New York times, the real update date, and no invented end time.
  Focused export tests also parse all-day reminders, leap/year boundaries,
  Unicode/injection cases, stable UIDs, and historical/current DST definitions.
- Mocked pipeline tests prove healthy publication, unhealthy runs preserving
  events and archives, truthful preview/preflight/write-failure diagnostics,
  and exclusion of secret-like fixture values and raw errors. Workflow review
  confirms all four optional podcast steps still use `continue-on-error`.

All implementation tests use synthetic fixtures, mocked responses, fixed dates,
the GitHub Pages project prefix, and temporary publication/download paths. The
seven published JSON files match their starting SHA-256 hashes. The unrelated
untracked `reports/` directory was preserved and excluded from this work.

Local visual-review manifest and screenshots:
[/private/tmp/pve-integrated-review/review.json](/private/tmp/pve-integrated-review/review.json).
Example [mobile share/save dialog](/private/tmp/pve-integrated-review/stale-event-detail-390.png)
and [parsed calendar download](/private/tmp/pve-integrated-review/valley-market-390.ics).
Package F also preserves parsed timed/all-day examples and screenshots under
`/private/tmp/pve-f-screenshots/`. These temporary artifacts are local review aids.

## Preserved boundaries and limitations

The Sunday `0 6 * * 0` cron, scraper requests/retries, 34% health threshold,
venue-aware deduplication, source category maps, append-only archive behavior,
and optional podcast-step behavior remain intact. No production scraping,
paid extraction, source probes, dataset regeneration, email, push, or deployment
was performed. No secret values were inspected or changed.

Publication remains atomic per JSON file, rather than transactional across all
destinations. Reports distinguish a completed events write from a later archive
failure. Diagnostic writes are best effort when their destination is unwritable;
they cannot hide a pipeline exception.

Browser verification uses Chromium; external calendar application import UI
was not exercised. The 200% reflow check uses an equivalent halved CSS viewport.
Actual GitHub Actions artifact upload and Pages deployment
have not been exercised remotely. Coverage spans reflect published podcast
evidence, not an independently verified complete podcast corpus.

A GitHub pull request requires a pushed branch, so the review remains local
with the accompanying PR draft. Publishing is a separate authorized step.
