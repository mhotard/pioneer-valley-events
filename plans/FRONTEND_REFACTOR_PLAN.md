# Handoff: extract frontend data logic and simplify calendar interactions

## Objective

Refactor the main event page so filtering/sorting, grouping by date, and calendar
cell calculation are pure functions with explicit inputs. Separate calendar
rendering from interaction handling and ensure one user action opens one modal.
Preserve the current appearance, templates, filters, and vanilla JavaScript.

Execute the changes, tests, and documentation updates. Keep the structural
extraction and the duplicate-modal fix distinguishable in review. This is a
targeted refactor, not a frontend rewrite.

## Starting context

Repository: `/Users/michaelhotard/Documents/ClaudeTest/pioneer-valley-events`.

Read applicable repository instructions, `CLAUDE.md`, and `README.md`. Inspect
`git status --short` and recent history; preserve unrelated changes and plans.
When this plan was written, the first two refactors were committed:

- `8c0f7a3`: separate pipeline publication from health checks.
- `a0930bf`: make JSON storage atomic.

This planning task did not re-review the storage commit or run its tests. Establish
a fresh baseline rather than assuming an old test count.

Read `docs/app.js`, `docs/index.html`, `docs/style.css`, `requirements.txt`,
`pyproject.toml`, and both workflows under `.github/workflows/`. Inspect existing
test conventions. No frontend test harness or package.json existed at planning
time. Python Playwright is already a dependency; the weekly workflow already
installs Chromium, while the ordinary CI workflow does not.

The frontend loads `data/events.json` and maintains a small global state object.
`applyFilters()` reads global events/filters. List and calendar rendering both
group events by date. `renderCalendar()` computes cells, renders HTML, and binds
navigation/day listeners. `attachEventListeners()` separately binds calendar
pills, which also bubble to the day handler and open the same modal twice.

## Scope

Expected files:

- `docs/app.js` and one new `docs/event-data.js` module.
- `docs/index.html`: only the script-loading adjustment needed for modules.
- New frontend tests under `tests/`, with small local fixtures if needed.
- Minimal Chromium setup in `.github/workflows/ci.yml`; an adjustment to the
  weekly browser-install command only if required for the same test environment.
- Relevant test instructions in `README.md`/`CLAUDE.md`.

Do not change Python pipeline/storage behavior, event IDs or schema, sources,
published JSON, CSS/layout, categories, email, seasonal guide, or 413 dashboard.
Do not add React, a bundler, state-management libraries, a date library, npm
dependencies, or a broad new test framework.

Keep existing escaping and markup behavior. URL sanitization, load-error UX,
focus trapping/restoration, adding new keyboard-accessible calendar controls,
and resolving multiple-showtime identity are separate tasks. Record discoveries
without bundling those features into this refactor.

## Behavior contract

### Filtering and ordering

- All filters combine with AND. Search matches title OR description OR venue.
- Search is case-insensitive. Input trimming remains as currently performed by
  the search control; do not add fuzzy search or new searchable fields.
- Category, town, and source use exact equality. Blank filters do not restrict.
- Date-from and date-to are inclusive ISO date comparisons. Reversed bounds
  produce no matching events, without adding a new validation UI.
- Empty/missing description and venue remain safe through existing fallbacks.
  Do not introduce validation for arbitrary malformed event schemas.
- Sort by date, then the existing `timeMinutes` result. Missing or unparseable
  times sort before parseable times. Preserve parser behavior rather than
  tightening accepted times. Equal sort keys retain input order.
- Do not mutate input arrays, event records, or filter objects.
- Clear resets the six filter controls and filter values. It does not currently
  reset calendar month or selected day; preserve that behavior.
- Source/town dropdowns remain populated from the full loaded event set, not
  the filtered subset. Preserve the `Pioneer Valley` → `Regionwide` town label.
- Result count represents all filtered events, even in calendar view when only
  one month is displayed.

### Calendar and views

- Weeks start Sunday. Include leading/trailing other-month placeholders and
  only enough cells to complete the last week: 28, 35, or 42 cells as appropriate.
- Adjacent-month placeholders show day numbers but no events or interactions.
- Preserve the maximum of three pills per day and `+N more` text.
- Use local calendar dates; do not convert date-only strings through UTC.
  Avoid `new Date('YYYY-MM-DD')`, `toISOString()` for local dates, and adding
  fixed 24-hour millisecond intervals across daylight saving changes.
- Highlight today and the selected day as before. Read the actual clock in the
  UI/controller, then pass date values into pure logic.
- Previous/next month navigation crosses years correctly and resets selection.
  Today returns to the actual current month and resets selection.
- Switching views resets the selected day, but preserves filters and the current
  calendar month. List/cards show the existing empty state when no events match;
  calendar still shows its month grid.
- Changing filters while a day is selected updates that day's detail from the
  current filtered events. If it has no remaining events, the detail disappears;
  do not silently change the stored selection policy.

### Activation and modal behavior

| Action | Result |
| --- | --- |
| Click list item/card, including nested text/icon | Open that event once |
| Enter or Space on a focused list item/card | Open that event once |
| Click a calendar pill | Open that pill's event once, without toggling the day |
| Click non-pill area of a day with one event | Open its event once |
| Click non-pill area or `+N more` of a multi-event day | Toggle that day's detail |
| Click same multi-event day again | Close its detail |
| Click a day with no events or an adjacent-month placeholder | No action |
| Click an event in selected-day detail | Open that event once |
| Modal close button, Escape, or overlay background | Close modal |
| Click inside modal content | Do not close modal |

Opening still focuses the modal close button. Preserve existing links and modal
content. For Space activation, preventing default scrolling is an acceptable
narrow interaction fix and should be identified in the final report.

## Suggested boundaries

### Pure module: `docs/event-data.js`

Export a few plain functions, with no `document`, global `state`, fetch, event
listeners, or implicit clock reads:

```javascript
timeMinutes(time)
filterEvents(events, filters)          // returns filtered, sorted array
groupEventsByDate(events)             // returns new date-keyed groups
buildCalendarCells(year, monthIndex)  // monthIndex is explicitly zero-based
```

Each cell should contain only what rendering needs, for example
`{ date: 'YYYY-MM-DD', day: 1, inCurrentMonth: true }`. Use explicit year/month
inputs and calendar arithmetic. Keep event lookup, selected/today styling, and
HTML out of this geometry helper. Grouping preserves event order within each
date; list rendering can explicitly sort the group keys as it currently does.

Move the existing time parser rather than duplicating or rewriting it. Preserve
the single JavaScript implementation used by filter sorting.

Use browser-native ES modules: import helpers from `./event-data.js` in `app.js`
and change the main script tag to `type="module"`. No build step is required.
Verify paths relative to the GitHub Pages project subdirectory, not just `/`.
Use HTTP for local preview/testing and document that requirement.

### UI/controller: `docs/app.js`

- Keep the small state object and existing templates.
- `render()` calls `filterEvents(state.events, state.filters)`.
- List and calendar renderers use the shared grouping function.
- Calendar renders the computed cell array instead of implementing separate
  leading/current/trailing calendar arithmetic loops.
- Use one delegated click listener on the stable `#events-container`, installed
  once during boot. Handle calendar navigation, explicit event targets, then
  day selection in a clear precedence order, returning after each action.
- Restrict event targets to `.list-item`, `.card`, and `.cal-pill` (or equivalent
  explicit action attributes). Do not generically activate every `[data-id]`,
  because the current calendar-day element also carries that attribute.
- Remove superseded per-item/per-day listeners and `attachEventListeners` if
  unused. Do not leave two competing activation paths.
- Bind one delegated keydown handler for existing focusable list/card targets.
  Do not implement both keydown and keyup activation for the same action.
- Read current state/filtered groups when handling an action; do not capture a
  stale event index from an earlier render. Recomputing for a click is acceptable
  at this project's scale; no caching system is needed.
- Keep filter/view/modal listeners outside render functions. Ensure repeated
  renders do not add more listeners to the stable container.

An explicit event callback parameter on the interaction-setup function is a
reasonable test seam, but do not expose production debug globals or create an
event bus solely for tests.

## Test harness: use the existing Python Playwright dependency

Use ordinary pytest fixtures and `playwright.sync_api`; do not require
pytest-playwright or a Node toolchain. Tests execute the actual JavaScript module
in Chromium, including pure-function assertions through `page.evaluate`.

Suggested files: `tests/test_frontend_data.py`, `tests/test_frontend_ui.py`, and a
small shared fixture module or appropriately scoped conftest.

- Serve the real `docs/` assets on loopback with an ephemeral port. Use a fixture
  that reliably shuts down its server and browser even after failure. Do not
  change process working directory or bind a public interface.
- Include a project-prefix route such as `/pioneer-valley-events/` mapping to
  `docs/` so relative asset and data URLs are exercised as on GitHub Pages.
- Intercept `data/events.json` with fixed fixtures. Never overwrite the real file.
  Block external requests; no source website, image host, or analytics access.
- For pure tests, import `event-data.js` from the loopback origin without booting
  the app. Return actual results to Python for hand-authored assertions.
- For UI tests, load the real index, CSS, and scripts. Fix browser time before
  boot, using Playwright's available clock support or a small test-only Date
  initialization script. Pin a timezone such as America/New_York.
- Wait on DOM state/Playwright assertions, not arbitrary sleeps. Fail on uncaught
  page errors and unexpected local asset load failures.
- Chromium must be installed explicitly. Tests must not silently skip because
  the browser is absent. Document installation and add it to normal CI before
  pytest. On Linux CI, use `python -m playwright install --with-deps chromium`.

This intentionally adds browser installation to test setup, but no new Python
or JavaScript package. Keep the suite small and reuse a browser process with
fresh contexts/pages for isolation.

## Required pure-function tests

| Area | Cases |
| --- | --- |
| Search | Case-insensitive title/description/venue matches; missing optional text; no accidental search by town/source |
| Filters | Each dimension; all six combined with decoy events matching only subsets; blank filters; inclusive bounds; reversed bounds |
| Sorting | Multiple dates; missing/unparseable time, midnight, 9 AM, noon, 7 PM; equal-key stable ordering; existing hour-only/lowercase inputs |
| Mutation | Original array order, records, and filters unchanged after filtering/grouping |
| Grouping | Empty input; multiple dates; exact membership and original order within each group |
| Leap year | February 2024 has 29 current-month cells; February 2025 has 28 |
| Grid length | February 2026 uses 28 cells; April 2026 uses 35; August 2026 uses 42 |
| Boundaries | Correct first/last current-month dates and padding numbers; December/January neighboring dates |
| Timezone | Same date-only cells in America/New_York and UTC, including March/November daylight saving months |

Expected values must be independent of the production calculation. Do not
reimplement the whole algorithm in the test to generate expected results.

## Required browser smoke/regression tests

Use a small fixed dataset with unique IDs: one single-event day, one day with
at least four events, an empty day, events in an adjacent month, and varied
filter fields. Use empty image URLs to avoid external requests.

1. Boot shows expected count/list, populated dropdowns, and generated-date label.
2. Apply combined filters; switch list → cards → calendar and verify the same
   filtered membership and count. Clear restores the full event set.
3. Calendar displays correct month and today's highlight with the fixed clock.
   Verify three pills plus overflow for the multi-event day.
4. Click the multi-event day's number/overflow; verify detail membership and
   ordering. Click again to close. Empty/other-month cells do nothing.
5. Click a pill and single-event day background; each opens the correct modal.
   Click selected-day detail item; it opens the correct event.
6. Change filters with a selected day. Detail reflects current filtered events;
   removed events cannot still be opened via a stale day index.
7. Navigate December → January and back; selection resets. Today returns to the
   fixed current month. View switching also clears selection as specified.
8. Activate list/card items by Enter and Space; close by button, Escape, and
   overlay background. Clicking inside content leaves the modal open.
9. Repeat filtering, month navigation, and view switching several times, then
   activate one event. It still opens exactly once.
10. No results: list/cards show empty state; calendar still renders its grid.
11. Capture and inspect representative desktop and narrow-viewport screenshots
    before and after using the same fixtures. Check calendar wrapping, detail
    panel, cards, and modal. Store temporary QA artifacts outside published data.

**Duplicate-call regression must measure activations, not just visibility.**
Two `openModal` calls leave the same final DOM, so a visible-modal assertion alone
cannot catch this bug. Either test the delegated handler with a recording modal
callback on a real DOM fixture, or observe modal-content replacements in the
actual app using a test-only MutationObserver. For the latter, count child-list
replacement records on `#modal-content`, not observer callbacks (multiple records
can be delivered together). Reset observations between actions. This test should
demonstrate two activations against the original pill wiring and one after the
fix. Do not add a production counter or window debug hook.

## Execution phases and verification gates

1. **Baseline/harness:** run current Python tests/lint; add an isolated browser
   fixture and characterize the existing UI. Reproduce duplicate pill activation
   with a temporary expected-failure or characterization test.
2. **Pure extraction:** introduce the module, imports, and shared helpers. Add
   the pure tests and replace duplicate grouping/calendar arithmetic. Gate:
   filters, ordering, calendar geometry, and representative markup remain equal.
3. **Interaction consolidation:** bind stable delegated listeners once, remove
   old handlers, and implement explicit target precedence. Convert the duplicate
   activation test into an ordinary passing regression test. Gate: all smoke
   tests pass, including repeated renders and keyboard activation.
4. **Integration/documentation:** add CI browser installation and preview/test
   commands. Run all tests/lint and visual QA. Gate: no data/backend/CSS drift,
   no leftover xfails for the fixed bug, no browser tests silently skipped.

## Verification commands

Run from the repository root using the existing project Python environment:

```bash
python3 --version
python3 -m playwright install chromium
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_frontend_data.py tests/test_frontend_ui.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
python3 -m ruff check --no-cache .
git diff --check
git diff --stat
git status --short
```

Browser installation may need network access/approval in a restricted execution
environment. If blocked, report that exact limitation; do not claim browser
verification passed. Do not run live scraping, mining, email, or deployment.

## Agent handoff and completion criteria

Execute phases sequentially; avoid agents independently rewriting `app.js`.
Each handoff should state actual helper signatures, event target precedence,
test fixture setup, verification results, and remaining failures.

Final reviewer checklist:

- Data functions accept explicit inputs and have no DOM/state/clock dependency.
- List/calendar share grouping; calendar geometry exists in one tested helper.
- Rendering does not bind per-render interaction listeners.
- A pill action triggers exactly one modal activation, even after many renders.
- Filtering, local dates, navigation, selection, empty views, and keyboard
  activation preserve the contract above.
- Native module/data URLs work under a project subdirectory without a build step.
- CI runs required browser tests; test data stays isolated from published JSON.
- All tests/lint pass and visual inspection finds no unintended layout change.

Final report: summarize the changes, distinguish the duplicate-activation fix
and any Space-scroll fix from structural extraction, list interpreter/browser
and test results, identify inspected viewports, and disclose any unverified
environment. No deployment is part of this task.
