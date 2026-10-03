# Weekly update investigation

Evidence checked October 2, 2026. Local baseline: `fbf391b` on `main`.

## Finding

The claim that commits stopped after July 3 is contradicted by the available
repository and GitHub evidence. No current scheduling or publication blocker
was established. Do not change secrets, the cron, or health thresholds to
address an unverified failure.

- Local event-file history contains weekly commits on July 5, 12, 19, and 26;
  August 2, 9, 16, 23, and 30; and September 6.
- GitHub's Weekly Event Update run history reports successful Sunday runs
  through September 27. The September 13 and September 27 step results both
  show successful pipeline, commit/push, and digest steps.
- [September 27 run](https://github.com/mhotard/pioneer-valley-events/actions/runs/36316017390)
  pushed [commit 469f177](https://github.com/mhotard/pioneer-valley-events/commit/469f177e88ffb82d7c48f117d821f7839a29b7a0).
  GitHub's contents API reports `generated: 2026-09-27` and 794 events.
- The Pages API reports legacy deployment from `main:/docs`. Its latest build
  is successful at the same September 27 commit, completed at 11:40:07 UTC.
  A direct read of the public JSON could not be verified with the web tool;
  the deployment finding is based on GitHub's build evidence.
- This local checkout stops at September 7; its committed event data is from
  September 6. That explains its difference from current GitHub data, but does
  not establish why a visitor might have seen July data.
- The last failed weekly run in the returned history was
  [June 7](https://github.com/mhotard/pioneer-valley-events/actions/runs/27087960161).
  It failed at lint and skipped tests, pipeline, and commit steps. This
  predates the alleged July stoppage; later runs succeeded.

## Focused repair

The established frontend defect was that stale data had no prominent warning,
and failed loads looked like an ordinary empty result. The main event page now:

- Warns when generation is more than 14 calendar days old, allowing one missed
  weekly run. Retains the real update date and leaves listings browsable.
- Warns when the generation date is missing, invalid, or in the future.
- Keeps warnings visible across filters and all three views; reassesses an
  open tab hourly and on visibility changes.
- Revalidates cached JSON and checks HTTP status and the events envelope.
- Shows a distinct unavailable state for network, HTTP, JSON, or envelope
  failures. Says updates are scheduled weekly instead of claiming they occur.

Healthy rendering, pipeline health checks, publication, archives, cron,
optional podcast steps, and digest behavior remain unchanged. No secret values
were inspected, printed, changed, or added. No paid scraping or email sending
was needed.

## Validation

`python3 -m pytest -q`: **324 passed**. The first sandboxed attempt could not
bind the local HTTP server or launch Chromium; the complete suite passed after
running with the required execution permission. The existing local Python 3.9
environment emits a urllib3/LibreSSL warning; CI specifies Python 3.12.

`python3 -m ruff check .`: **passed**.

Tests cover the freshness boundary, bad and future dates, visible stale
warnings, filter/view persistence, aging open tabs, load failures, and the
existing healthy frontend and publication behavior.
