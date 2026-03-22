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
│       └── events.json         # Event data, regenerated weekly
├── scrapers/
│   ├── base.py                 # BaseScraper + Event dataclass
│   ├── umass.py                # UMass events (JSON-LD parsing)
│   ├── amherst_cinema.py       # Amherst Cinema showtimes
│   └── claude_scraper.py       # Claude Haiku-powered universal scraper
├── sources.json                # Config for all Claude-powered sources
├── pipeline.py                 # Aggregation, dedup, and output script
├── requirements.txt
├── pyproject.toml              # ruff linting config
└── .github/workflows/
    ├── ci.yml                  # Lint + test on every push
    └── weekly-update.yml       # Scrape → commit → deploy every Sunday
```

---

## How it works

1. **Static scrapers** (`umass.py`, `amherst_cinema.py`) use hand-written parsers for reliable structured sources.
2. **Claude-powered scrapers** (`claude_scraper.py`) fetch each URL in `sources.json`, clean the HTML, and send it to Claude Haiku for event extraction — no custom parser needed per site.
3. `pipeline.py` merges all results, deduplicates near-identical events, filters to the next 90 days, and writes `docs/data/events.json`.
4. GitHub Pages serves `docs/` as the static site. GitHub Actions re-runs the pipeline every Sunday and commits any changes.

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

The workflow in `.github/workflows/weekly-update.yml` runs every Sunday at 6 AM UTC (2 AM Eastern). It:
1. Lints with `ruff` (blocks deploy on failure)
2. Runs `pytest` (blocks deploy on failure)
3. Runs `python pipeline.py`
4. Commits and pushes `events.json` if it changed
5. GitHub Pages autodeploys on push

**Required secret:** Add `ANTHROPIC_API_KEY` in your repo under **Settings → Secrets and variables → Actions**.

To trigger manually: **Actions → Weekly Event Update → Run workflow**

---

## Sources currently scraped

| Source | Town | Notes |
|--------|------|-------|
| UMass Amherst | Amherst | JSON-LD structured data |
| Amherst Cinema | Amherst | Film showtimes |
| Jones Library | Amherst | Programs and events |
| Eric Carle Museum | Amherst | Special exhibitions and programs |
| Town of Amherst | Amherst | Community calendar |
| Amherst College Athletics | Amherst | Home game schedule |
| Smith College | Northampton | Campus events |
| Hawks & Reed | Greenfield | Performing arts |
| Gateway City Arts | Holyoke | Arts and culture |
| NEPM | Pioneer Valley | Curated regional events (includes Iron Horse, Academy of Music) |
| UMass Athletics | Amherst | Home game schedule |

---

## Event categories

`music` · `arts` · `film` · `comedy` · `community` · `academia` · `family` · `food` · `outdoor` · `festival`

---

## Roadmap

- [ ] Pleasant Street Theater (Northampton)
- [ ] Springfield Museums
- [ ] Eventbrite API integration for broader coverage
- [ ] Email/RSS subscription
- [ ] Image support
