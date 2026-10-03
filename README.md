# Pioneer Valley Events

A community-built event aggregator for Amherst, Northampton, and the Pioneer Valley. Hosted free on GitHub Pages, updated weekly via GitHub Actions.

**Live site:** [mhotard.github.io/pioneer-valley-events](https://mhotard.github.io/pioneer-valley-events)

---

## Project structure

```
pioneer-valley-events/
├── docs/                       # Static site (served by GitHub Pages)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/
│       ├── events.json         # Event data, regenerated weekly
│       └── archive-YYYY.json   # Append-only history, one file per year
├── scrapers/
│   ├── base.py                 # BaseScraper + Event dataclass
│   ├── claude_scraper.py       # Claude Haiku-powered universal scraper
│   ├── ical.py                 # Shared base for iCal feed scrapers
│   └── ...                     # One file per structured-data source
├── sources.json                # Config for all Claude-powered sources
├── community_events.json       # Manually-curated events (supports recurrence)
├── pipeline.py                 # Aggregation, dedup, and output script
├── requirements.txt
├── pyproject.toml              # ruff linting config
└── .github/workflows/
    └── weekly-update.yml       # Lint → test → scrape → commit every Sunday
```

---

## How it works

1. **Static scrapers** (`umass.py`, `amherst_cinema.py`) use hand-written parsers for reliable structured sources.
2. **Claude-powered scrapers** (`claude_scraper.py`) fetch each URL in `sources.json`, clean the HTML, and send it to Claude Haiku for event extraction — no custom parser needed per site.
3. `pipeline.py` collects normalized events, filters them to 3 days back through
   90 days ahead, deduplicates near-identical events, then sorts them
   chronologically.
4. Before publishing, the pipeline checks source health. A full run fails
   without changing `events.json` or archives when more than 34% of sources
   errored or regressed from at least 5 published events to zero.
5. Healthy full runs write `docs/data/events.json` and update the append-only
   yearly archives. Dry runs and single-source runs only preview results.
6. GitHub Pages serves `docs/` as the static site. GitHub Actions re-runs the
   pipeline every Sunday and commits any changes.

Persistent JSON writes use a temporary file beside the destination, flush and
sync the complete serialization, and then atomically replace that one file.
Readers therefore see either the old complete file or the new complete file;
a serialization, sync, or replacement failure leaves the previous destination
unchanged. Existing malformed, unreadable, or structurally unsafe archives,
podcast snapshots, and mining checkpoints fail loudly instead of being treated
as empty history. Missing optional stores still start with an empty envelope,
while the entity miner's episode corpus remains required.

This is a per-file guarantee, not a transaction across `events.json` and all
yearly archives. It does not add directory-sync power-loss guarantees or protect
against concurrent writers. A hard process kill can leave an ignored temporary
file, and a mining batch whose checkpoint was not replaced may be extracted
again on the next run. Damaged historical data is reported, not automatically
repaired.

The event page warns visibly when `events.json` was generated more than 14
calendar days ago (allowing one missed weekly update), or when its generation
date is missing, invalid, or in the future. Old listings remain browsable with
the warning in every view. HTTP, network, JSON, and envelope failures show an
unavailable state rather than an ordinary empty result. Data requests revalidate
the browser cache, and open tabs reassess freshness hourly and when revisited.

---

## Run the pipeline manually

```bash
# Install dependencies once
pip install -r requirements.txt
playwright install chromium

# Set your Anthropic API key (required for Claude-powered sources)
export ANTHROPIC_API_KEY=sk-ant-...

# Run all scrapers and update events.json
python3 pipeline.py

# Preview results without writing
python3 pipeline.py --dry-run

# Run a single source
python3 pipeline.py --source umass
python3 pipeline.py --source jones-library

# Commit and push to redeploy
git add docs/data/events.json
git commit -m "chore: update events $(date +%Y-%m-%d)"
git push
```

---

## Preview and test the frontend

The frontend uses browser-native JavaScript modules, so preview it over HTTP
rather than opening `docs/index.html` directly:

```bash
python3 -m http.server 8000 --directory docs
```

Then open [http://localhost:8000](http://localhost:8000). To install Chromium
and run the isolated frontend tests (which use fixed fixture data and never
overwrite `docs/data/events.json`):

```bash
python3 -m playwright install chromium
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_frontend_data.py tests/test_frontend_ui.py
```

Run the complete test and lint suite with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
python3 -m ruff check --no-cache .
```

---

## Adding a new event source

Just add an entry to `sources.json` — no code required:

```json
{
  "name": "my-venue",
  "url": "https://myvenue.com/events",
  "venue": "My Venue Name",
  "town": "Northampton",
  "type": "html"
}
```

Use `"type": "playwright"` for JavaScript-rendered pages. The Claude Haiku model handles extraction automatically.

---

## Automated weekly updates (GitHub Actions)

The workflow in `.github/workflows/weekly-update.yml` runs every Sunday at 6 AM UTC (2 AM EDT / 1 AM EST). It:
1. Lints with `ruff` (blocks deploy on failure)
2. Runs `pytest` (blocks deploy on failure)
3. Runs `python pipeline.py`
4. Commits and pushes `events.json` if it changed
5. GitHub Pages autodeploys on push

**Required secret:** Add `ANTHROPIC_API_KEY` in your repo under **Settings → Secrets and variables → Actions**.

To trigger manually: **Actions → Weekly Event Update → Run workflow**


Each pipeline run writes `logs/run-report.json` (or the path supplied with
`--report`), separate from published data. It records the run date, mode,
per-source counts and status, health/publication decision, and completed or
failed destination writes. It contains no source URLs, error bodies, or
credentials. `published_event_count` is populated only after `events.json` was
actually replaced; archives are separate writes, so a later archive failure
can leave an explicitly reported partial publication. A preview can complete
successfully while its selected source reports an error. Reports never replace
the pipeline's exit status or exception.

Extracted records with missing titles, impossible dates, malformed structure,
or unsafe event links are counted by reason in diagnostics and the Actions
summary. A nonempty extraction with no valid records is a source error. Useful
partial results remain eligible under the existing health rules. Unparseable
optional times remain unknown; supplied midnight remains midnight.

The weekly Action always attempts a job summary and uploads the
**weekly-update-diagnostics** artifact, containing only safe diagnostic JSON
from the runner's temporary directory. The workflow report distinguishes an
earlier workflow failure from missing pipeline diagnostics, and reports
commit/push separately. Optional podcast outcomes remain visible without
blocking the main publication. Raw log files are not included in the artifact.

When an update looks wrong, use this sequence without rerunning scrapers:

1. **Scheduling:** check the Weekly Event Update run history for the expected
   Sunday run. The existing cron is 06:00 UTC (02:00 EDT / 01:00 EST).
2. **Setup, lint, or tests:** read the failed workflow step. A skipped pipeline
   means no scrape completed; the summary identifies earlier workflow failures.
3. **Preflight:** a `missing_api_key` reason means collection never started.
   Check whether the required repository secret is configured without displaying
   its value.
4. **Source health:** inspect source `error` and `regression` statuses and event
   counts in the summary/report. The existing 34% rejection threshold remains
   in force. Diagnose from collected results and logs; do not add source probes,
   retries, or extra scraping.
5. **Publication and push:** distinguish the accepted health decision from
   destination writes, then check commit/push outcome. A failed write or push
   does not establish that the new file reached GitHub.
6. **Pages:** check the separate GitHub Pages build/deployment and its commit.
   Pipeline success alone does not confirm what visitors received.

---

## Sources currently scraped

| Source | Town | Notes |
|--------|------|-------|
| UMass Athletics | Amherst | Home game schedule (iCal) |
| Amherst College Athletics | Amherst | Home game schedule (iCal) |
| Amherst Cinema | Amherst | Film showtimes |
| Jones Library | Amherst | Programs and events (RSS) |
| Eric Carle Museum | Amherst | Special exhibitions and programs |
| Town of Amherst | Amherst | Community calendar |
| The Drake | Amherst | Live music venue |
| Emily Dickinson Museum | Amherst | Tours and programs |
| Smith College | Northampton | Campus events |
| The Parlor Room | Northampton | Live music (Iron Horse collective) |
| Bombyx Center | Florence | Music and arts venue |
| Look Memorial Park | Florence | Outdoor events and concerts |
| Shea Theater | Turners Falls | Performing arts |
| Historic Deerfield | Deerfield | Museum programs (Events Calendar API) |
| Forbes Library | Northampton | Programs and events (LibCal RSS) |
| Iron Horse Music Hall | Northampton | Live music (Parlor Room collective) |
| Academy of Music | Northampton | Theatre and music |
| Northampton Center for the Arts | Northampton | Arts events |
| Northampton.live | Northampton | Aggregated listings |
| Mount Holyoke College | South Hadley | Campus events (Localist API) |
| UMass Amherst | Amherst | Campus events (Localist API) |
| Springfield Museums | Springfield | Exhibits, tours, classes (Events Calendar API) |
| Hawks & Reed | Greenfield | Performing arts (Events Calendar API) |
| NEPM + Culture to Do | Pioneer Valley | Curated regional events and weekly newsletter |
| Harriers Race Calendar | Pioneer Valley | Western Mass road races |
| Arts Hub WMA, Valley Arts Newsletter, Visit Hampshire County | Pioneer Valley | Regional calendars |
| Community events | — | Manually curated in `community_events.json` |

---

## Event categories

`music` · `arts` · `film` · `comedy` · `community` · `academia` · `family` · `food` · `outdoor` · `festival`

---

## Seasonal guide

[The Seasonal Guide](https://mhotard.github.io/pioneer-valley-events/seasonal.html)
lists the 413's annual events — mined from three years of NEPM's
[The Fabulous 413](https://www.nepm.org/podcast/the-fabulous-413) podcast
archive. Events covered in multiple years surface with their typical month
and links to every episode about them; the weekly digest includes an
"on your radar" preview of the next ~6 weeks.

---

## Roadmap

- [x] Springfield Museums
- [x] Weekly email digest
- [x] Seasonal guide of annual events (Fabulous 413 archive)
- [ ] Eventbrite API integration for broader coverage
- [ ] Holyoke coverage (gap since Gateway City Arts closed)
- [ ] Hampshire College (site blocks scrapers; needs a feed/API)
