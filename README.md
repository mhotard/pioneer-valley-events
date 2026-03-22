# Pioneer Valley Events

A community-built event aggregator for Amherst, Northampton, and the Pioneer Valley. Hosted free on GitHub Pages, updated weekly.

## Live site

Once deployed: `https://<your-username>.github.io/pioneer-valley-events`

---

## Project structure

```
pioneer-valley-events/
├── site/                   # Static site (what gets hosted)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/
│       └── events.json     # Event data, updated weekly
├── scrapers/               # One Python scraper per source
│   ├── base.py             # Base class + Event dataclass
│   ├── umass.py
│   ├── iron_horse.py
│   ├── amherst_cinema.py
│   ├── the_drake.py
│   ├── northampton.py
│   ├── hawks_reed.py
│   └── gateway_city_arts.py
├── pipeline.py             # Aggregation + dedup script
├── requirements.txt
└── .github/
    └── workflows/
        └── weekly-update.yml   # GitHub Actions automation
```

---

## Deploy to GitHub Pages

1. Create a new GitHub repo named `pioneer-valley-events`
2. Push this directory:
   ```bash
   git init
   git add .
   git commit -m "initial commit"
   git remote add origin https://github.com/<your-username>/pioneer-valley-events.git
   git push -u origin main
   ```
3. In your repo settings: **Pages → Source → Deploy from branch → `main` → `/site`**
4. Your site will be live at `https://<your-username>.github.io/pioneer-valley-events/`

---

## Run the pipeline manually (Claude Code workflow)

```bash
# Install dependencies once
pip install -r requirements.txt

# Run all scrapers and update events.json
python pipeline.py

# Preview results without writing
python pipeline.py --dry-run

# Run a single source
python pipeline.py --source umass
python pipeline.py --source iron-horse

# Then commit and push to redeploy
git add site/data/events.json
git commit -m "chore: update events $(date +%Y-%m-%d)"
git push
```

---

## Automated weekly updates (GitHub Actions)

The workflow in `.github/workflows/weekly-update.yml` runs every Sunday at 6 AM UTC. It:
1. Runs `python pipeline.py`
2. If `events.json` changed, commits and pushes it
3. GitHub Pages automatically redeploys on push

To trigger it manually: **Actions → Weekly Event Update → Run workflow**

---

## Adding a new event source

1. Create `scrapers/my_source.py` extending `BaseScraper`:
   ```python
   from .base import BaseScraper, Event

   class MySourceScraper(BaseScraper):
       name = "my-source"
       town = "Northampton"

       def _fetch(self) -> list[Event]:
           # fetch, parse, return list of Event(...)
           ...
   ```
2. Add it to `scrapers/__init__.py`:
   ```python
   from .my_source import MySourceScraper
   ALL_SCRAPERS = [..., MySourceScraper]
   ```
3. Run `python pipeline.py --source my-source` to test it.

---

## Event categories

`music` · `arts` · `film` · `comedy` · `community` · `academia` · `family` · `food` · `outdoor` · `festival`

---

## Sources currently scraped

| Source | Town | Category |
|--------|------|----------|
| UMass Amherst | Amherst | Mixed |
| Iron Horse Music Hall | Northampton | Music |
| Pearl Street Nightclub | Northampton | Music |
| Amherst Cinema | Amherst | Film |
| The Drake | Amherst | Music |
| City of Northampton | Northampton | Community |
| Hawks & Reed | Greenfield | Mixed |
| Gateway City Arts | Holyoke | Arts |

---

## Roadmap

- [ ] Add more sources: Smith College, Hampshire College, Academy of Music, Pleasant Street Theater, Springfield Museums
- [ ] Eventbrite API integration for broader coverage
- [ ] Claude API enrichment pass (better category tagging, description cleanup)
- [ ] Image support
- [ ] Email/RSS subscription
