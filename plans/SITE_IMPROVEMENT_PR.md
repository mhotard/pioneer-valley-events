# Improve event discovery, trust, accessibility, and update diagnostics

Past listings competed with upcoming events, filtered views could not be shared,
secondary-page failures hid useful content, and weekly update failures required
reading raw logs. The event browser now defaults to upcoming New York dates,
restores discovery state from URLs, supports keyboard and mobile interaction,
and makes data freshness and historical coverage explicit. Exact-ID event links
and one-event calendar downloads preserve supplied details and explain unknown
times; unavailable IDs never substitute another event. Structured diagnostics
explain source health and publication outcomes without exposing raw errors or
credentials.

The weekly schedule and source workload are preserved, as are publication health
checks, append-only archives, optional podcast steps, and the static architecture.
Extracted dates/times/links and existing published links receive focused
validation. Production JSON is unchanged.

Validation: **567 tests passed**, Ruff and diff checks passed. **22 desktop/mobile
scenarios** passed and screenshots were inspected; **two integrated calendar
downloads** parsed successfully. Tests use mocks and temporary paths. The seven
published JSON files match their starting hashes. Baseline: 324 passing tests.

Local branch: `codex/site-improvements`; review with `git diff main...codex/site-improvements`.
Remote workflow execution and external calendar client import UI remain untested.
No push or deployment was performed. Publication remains atomic per destination;
partial writes are reported explicitly. Browser checks use Chromium, with 200%
reflow assessed through an equivalent halved viewport.
