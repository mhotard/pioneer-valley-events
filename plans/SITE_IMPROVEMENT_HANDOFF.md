# Site improvement plan and agent handoff

Prepared October 2, 2026. Direction: balanced reliability and event discovery.
This is an execution plan; the proposed work below has not been dispatched.

## Goal

A visitor should quickly find a relevant upcoming event, understand how current
and trustworthy its details are, and share or save it. A maintainer should be
able to explain a bad update without manually reading an entire Actions log.
Keep the vanilla JavaScript static site and existing GitHub Pages hosting.

## Starting point

- `docs/app.js` provides list, cards, calendar, text/date/category/town/source
  filters, and event details. `docs/event-data.js` contains pure transformations.
  Dates currently default to unrestricted, so past listings compete with
  upcoming events. Filter and view state is not shareable in the URL.
- The current working changes add main-page freshness warnings and explicit
  load failure states. They are validated with 324 passing tests and clean
  ruff lint. Land this baseline before agents start dependent work.
- GitHub evidence shows successful weekly data commits and Pages builds through
  September 27; the local checkout is behind. See
  [the investigation](WEEKLY_UPDATE_INVESTIGATION.md). Do not plan a cron or
  secret repair around the unsupported July-stoppage premise.
- `pipeline.py` isolates scraping, transformation, health checks, and publication.
  Unhealthy runs must still fail before touching events or archives. Archives
  remain append-only; optional podcast steps must not block event publishing.
- `docs/seasonal.html` and `docs/413/index.html` have independent data loaders
  without useful error recovery. Podcast coverage is historical evidence, not
  confirmation that an event will happen this year.
- The modal declares `aria-labelledby="modal-title"`, but the rendered title
  lacks that ID. Focus is moved into the modal but is not trapped or returned.

## Execution order and ownership

| Wave | Agent package | Priority | Dependencies | Primary write ownership |
|---|---|---|---|---|
| 0 | Coordinator: land validated safeguard baseline | First | None | Current changes and integration |
| 1 | A: explain update health | High | Baseline | `pipeline.py`, weekly workflow, orchestration tests |
| 1 | B: upcoming-event discovery | High | Baseline | Main app, event-data module, index, shared CSS, frontend tests |
| 1 | C: trustworthy secondary pages | Medium | Baseline | Seasonal page, 413 page, new secondary-page tests |
| 2 | D: mobile and keyboard access | High | B merged | Main UI and frontend tests |
| 2 | E: validate extracted event details | High | A merged | Scraper conversion/validation, scraper tests |
| 3 | F: share and save events | Medium | B and D merged | Main UI, new calendar-export module and tests |
| 3 | Coordinator: integrated release review | Required | A–F merged | Integration fixes and release notes |

Run at most three implementation agents concurrently. These packages can run
in isolated branches/worktrees; the coordinator merges one at a time. C must
use scoped page CSS instead of modifying `docs/style.css` while B owns it.
A and E run sequentially to avoid overlapping validation and health decisions.
D and F must follow B because they share UI files. Give each agent the current
merged baseline, not an old snapshot of `main`.

## Common instructions for every agent

Inspect repository instructions and relevant existing tests before editing.
Keep the change within its package. Return a reviewable diff, a short rationale,
test results, and any unresolved limitations. Do not deploy, send emails, run
paid extraction, change secrets, regenerate production data, or reformat the
whole repository. Use synthetic fixtures and temporary publication paths.

Keep current JSON consumers compatible. Never backfill a generation timestamp
with today's date to make old data appear fresh. Never weaken the 34% health
threshold or bypass failing tests. Never reset archives or mining checkpoints.
Preserve scraper-specific category maps and venue-aware deduplication.

The owner requires a light footprint on source websites. Preserve the existing
weekly scrape schedule and source-request workload: no additional scheduled
scrapes, source polling, automated availability probes, new scraper retries,
or extra source requests for diagnostics or validation. Reuse results already
collected by the pipeline. Visitor filters, sharing, calendar downloads, and
data-status checks must use published JSON, never fetch source websites.
Frontend retries and cache revalidation may request the site's own static JSON
on GitHub Pages; they must not trigger scraping. Tests use mocked responses.
Any proposed increase in source traffic requires the owner's explicit approval.

Do not add a framework, backend, account system, service worker, or recurring
automation. Do not claim cancellation, free admission, accessibility, or a
precise event time unless the source supplies that information. Public status
must contain whitelisted facts, never credentials or raw exception bodies.

Each package runs its relevant tests and `python3 -m ruff check .`. Integration
runs the full suite. Frontend tests must use the project URL prefix, fixed
dates, network interception, and mocked JSON. Validate mobile layout and
keyboard interaction in Chromium, not only helper functions.

## A — Explain update health

**Dispatch prompt:** Implement safe, structured reporting for the existing
weekly pipeline. Show maintainers what was attempted, which sources yielded
events or regressed, whether publication was accepted, and what was written.
Preserve all existing publication rules. Do not change the schedule or secrets.

**Scope:** `pipeline.py`, `.github/workflows/weekly-update.yml`,
`tests/test_pipeline_orchestration.py`, focused new report tests, README.

**Deliverables:**

- A machine-readable run report using source names, event counts, status enums,
  run date, publication decision, and published event count. No raw error text
  or environment values. Write diagnostic reports outside `docs/data/` so a
  rejected run cannot change published data.
- An Actions job summary plus a diagnostic artifact available even after
  pipeline failure. A failure before the pipeline starts is visibly identified
  as an earlier workflow failure, rather than described as successful scraping.
- A short maintainer troubleshooting path separating scheduling, lint/tests,
  missing-key preflight, source health, publication/push, and Pages deployment.

**Acceptance:** Healthy full runs, unhealthy runs, dry runs, single-source runs,
missing-key preflight, and write failures have truthful outcomes. Reports cannot
convert an exception into exit 0. Existing rejected-run tests still prove that
events and archives are unchanged. Report tests use fake credentials and assert
those values and raw error bodies are absent. Optional mining remains optional.

## B — Make upcoming events easy to discover

**Dispatch prompt:** Improve the main event browser with an upcoming default,
quick date choices, richer search, and shareable filter/view state. Preserve
the stale-data warning and all existing list/cards/calendar interactions.

**Scope:** `docs/app.js`, `docs/event-data.js`, `docs/index.html`,
`docs/style.css`, frontend data/UI tests.

**Deliverables:**

- Default to events on or after today in `America/New_York`, the region's
  timezone. Provide Today, Next 7 days, This weekend, and All published dates.
  Next 7 days includes today through today + 6. Weekend means the upcoming
  Saturday–Sunday, including the remaining day when it is already Sunday.
- Keep calendar date boundaries consistent with the quick choices. Clear
  returns to the upcoming default; All published dates explicitly permits
  browsing earlier dates still present in the file.
- Search title, description, venue, and town; handle missing optional strings.
- Encode supported filters and view in URL parameters. Restore on reload,
  handle browser back/forward, and safely ignore unsupported values. Text
  typing must not add a history entry per keystroke.
- Explain empty results with a useful reset action while retaining data-status
  warnings. Friendly source names can be displayed without changing source IDs.

**Acceptance:** Fixed-date tests cover month/year boundaries, DST, weekend
definitions, viewers in other timezones, URL round trips, unknown parameters,
clear/reset, combined filters, empty states, and all views. Old July fixtures
are still flagged. No archive or production-data mutation is needed.

## C — Make secondary pages trustworthy

**Dispatch prompt:** Add loading, unavailable, empty, and data-status states to
the seasonal guide and Fabulous 413 dashboard. Clearly distinguish historical
podcast coverage from confirmed upcoming event dates. Keep failures in optional
map/chart libraries from blanking the useful text content.

**Scope:** `docs/seasonal.html`, `docs/413/index.html`, new focused tests.
If shared code is needed, add a new module rather than editing B's files in
parallel. Use page-scoped styles in wave 1.

**Deliverables:**

- Check HTTP status and expected envelope shape; show an understandable failure
  and retry control instead of an empty or broken page.
- Display the dataset's real generation date and coverage period. Use the
  existing pure freshness helper when applicable, with explicit copy about
  historical coverage. Do not label an old podcast mention as a confirmed event.
- Make the explorer usable when Leaflet, Chart.js, or map tiles fail; use a
  text fallback for the information needed to navigate by town.
- Add clear cross-links among Events, Seasonal Guide, and the 413 dashboard.

**Acceptance:** Offline browser fixtures cover healthy, empty, stale, invalid,
missing, HTTP-error, and dependency-error cases. Navigation works under
`/pioneer-valley-events/`. Historical entries do not acquire invented dates.
No changes to miners or generated production JSON.

## D — Improve mobile and keyboard access

**Dispatch prompt:** Finish the main event browser's accessibility and mobile
interaction after discovery changes land. Keep the existing visual identity
and make concrete fixes demonstrated by browser checks.

**Scope:** Main UI files and frontend UI tests; avoid pipeline changes.

**Deliverables:**

- Fix the modal label ID, trap focus while open, close with Escape, restore
  focus to the opener, and prevent interaction with background controls.
- Expose selected view state with `aria-pressed`, label search controls, provide
  visible focus indicators, and make calendar day selection keyboard reachable.
- Guard event and image URLs from already published data before adding them to
  the DOM; only HTTP/HTTPS links should activate. Use adversarial browser
  fixtures and coordinate the allowed-link policy with E.
- At 390px width, keep filters manageable and event details readable. Provide
  an accessible filter disclosure if needed; retain a visible active-filter
  summary and preserve the data warning outside collapsed filters.
- Check color contrast, 200% zoom, reduced motion, and practical touch targets.
  Make only needed style changes; no broad redesign.

**Acceptance:** Playwright verifies keyboard-only filtering, opening, tabbing,
closing, focus return, and calendar selection. Desktop and mobile screenshots
are inspected. No horizontal page overflow at the target width; warning copy
and primary actions remain readable. Existing UI regressions still pass.

## E — Validate extracted event details

**Dispatch prompt:** Tighten validation of externally extracted event details
without making sources less resilient. Reject impossible calendar dates and
unsafe link schemes, distinguish unknown times from midnight, and keep source
health/reporting honest. Do not broaden category maps or change dedup semantics.

**Scope:** `scrapers/claude_scraper.py`, appropriate shared validation helpers,
scraper and schema tests. Touch `pipeline.py` only after A merges and only if
necessary to carry validation counts into its report.

**Deliverables:**

- Validate actual date values, not only the `YYYY-MM-DD` regex. Normalize
  optional times carefully; never invent times from invalid text.
- Restrict externally supplied clickable event URLs to HTTP/HTTPS. Renderers
  must also guard links supplied by existing published data; D owns that
  frontend check, so E must not edit the main UI files concurrently.
- Count rejected records by safe reason enums so an invalid extraction is
  visible in diagnostics. Keep missing optional fields acceptable.
- Add representative fixtures for malformed dates/times/links and a valid
  payload regression. Do not make real network or model calls in tests.

**Acceptance:** Leap days, month lengths, whitespace, unknown times, unsafe
URLs, and partial responses have explicit tests. Valid existing records retain
their IDs and order. Existing parser salvage, scraper isolation, threshold,
archive, and dedup tests pass. A validation failure cannot silently look like
a productive, healthy scrape: if a nonempty extraction contains no valid event
records, record a source error rather than a successful empty response. Valid
partial extractions remain publishable under the existing health rules.

## F — Share and save events

**Dispatch prompt:** Add direct event links and a safe downloadable calendar
entry after the discovery and accessibility work lands. Keep the site static;
do not require an account or external service.

**Scope:** Main UI, a pure calendar-export module, focused data/UI tests.

**Deliverables:**

- A share/copy action using a URL that identifies the published event by its
  existing ID. Restore the event detail on direct navigation. If it has left
  the current dataset, show that it is unavailable; never substitute another
  event. Preserve supported filter parameters when useful.
- Download one [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545.html) calendar
  entry. Use `America/New_York` for known local
  times; use an all-day date for unknown times and explain that choice. Include
  title, venue, organizer URL, and the dataset update date in the description.
  Use a stable UID derived from the existing event ID.
- Correct escaping, CRLF line endings, UTF-8 line folding, exclusive all-day
  end dates, and a tested policy for missing end times. Do not imply a known
  duration where the data has none. Keep stale warnings visible beside saving.

**Acceptance:** Parse generated calendar files with the existing `icalendar`
test dependency, testing Unicode, newlines, punctuation, DST, all-day events,
and missing end times. Browser tests cover direct links, unavailable IDs,
clipboard fallback, download content, and modal focus behavior. No email send
or external calendar write is part of this task.

## Integrated release review

Merge each package only after its tests pass and review covers the stated
acceptance checks. Run the full pytest suite and ruff on the merged result.
Inspect the main page on desktop/mobile, fresh/stale/unavailable datasets, a
shared filtered URL, one direct event URL, a downloaded calendar file, the
seasonal guide, and the 413 dashboard with blocked third-party assets.

Confirm that a healthy fake pipeline still publishes, an unhealthy fake run
leaves events and archives untouched, diagnostics contain no secret-like fixture
values, and optional podcast work cannot block the main publication. Review
the workflow diff for accidental secret/environment exposure and preserve the
Sunday cron. Prepare release notes and a reviewable PR; publishing is a separate
step when authorized.

Success is measured by demonstrable behavior, not guessed traffic: a visitor
can find next-week events in a few interactions, share the exact view/event,
use the UI with a keyboard, and recognize stale/unavailable information. A
maintainer can identify the failed stage and affected sources from one run
summary. Analytics, accounts, maps of individual events, and new scrapers can
be considered after this foundation, when a concrete user need justifies them.
