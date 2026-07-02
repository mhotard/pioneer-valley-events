#!/usr/bin/env python3
"""
Builds the seasonal guide from mined Fabulous 413 mentions.

Reads docs/data/fab413_mentions.json, groups mentions of the same event
across years, keeps events covered in 2+ distinct years whose coverage
clusters seasonally (filtering out weekly series like "Live Music Friday"),
runs one Haiku pass to canonicalize names/towns and drop non-events, and
writes docs/data/seasonal.json for the site page and the email digest.

Usage:
    source ~/.zshrc && python3 fab413_guide.py
"""

import json
import os
import re
from collections import Counter
from datetime import date
from difflib import SequenceMatcher

from scrapers.claude_scraper import _get_client, _parse_json_array

MENTIONS_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "fab413_mentions.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "seasonal.json")

MIN_YEARS = 2          # seen in at least this many distinct calendar years
MIN_SEASONALITY = 0.6  # share of mentions inside the best 2-adjacent-month window

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

CURATE_PROMPT = """\
You are curating a seasonal guide of annual events in Western Massachusetts
(the 413), built from mentions on the public-radio show "The Fabulous 413".

Below are candidate event groups. Each has: an index, name variants as they
appeared across episodes, towns seen, and the months they were covered in.

Return a JSON array with one element per index:
  index          — the group's index, unchanged
  canonical_name — the best clean, short name (no years, no ordinals like
                   "27th", no "Annual"). Pick the most recognizable form.
  town           — the single best town/place label, cleaned up ("Springfield
                   to Greenfield" → "Springfield"; use "" if genuinely unclear)
  keep           — false if this is NOT a real annual public event someone
                   could plan to attend: drop weekly/monthly series, radio
                   segments, one-off news stories, and generic topics.

Return ONLY valid JSON, no markdown fences.

Groups:
{groups}"""


def normalize(name: str) -> str:
    n = name.lower()
    n = re.sub(r"\b(19|20)\d{2}\b", "", n)
    n = re.sub(r"\b\d+(st|nd|rd|th)?\b", "", n)
    n = re.sub(r"\b(annual|the|festival|fest)\b", " ", n)
    n = re.sub(r"[^a-z ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def group_mentions(mentions: list[dict]) -> list[list[dict]]:
    """Fuzzy-group mentions by normalized event name."""
    groups: dict = {}
    for m in mentions:
        key = normalize(m["name"])
        if not key:
            continue
        best = None
        for existing in groups:
            if key == existing or SequenceMatcher(None, key, existing).ratio() > 0.87:
                best = existing
                break
        groups.setdefault(best or key, []).append(m)
    return list(groups.values())


def seasonality(months: list[int]) -> tuple[float, int]:
    """Best share of mentions inside any 2-adjacent-month circular window,
    and the primary month of that window."""
    counts = Counter(months)
    best_share, best_month = 0.0, months[0]
    for start in range(1, 13):
        nxt = 1 if start == 12 else start + 1
        share = (counts.get(start, 0) + counts.get(nxt, 0)) / len(months)
        if share > best_share:
            best_share = share
            best_month = start if counts.get(start, 0) >= counts.get(nxt, 0) else nxt
    return best_share, best_month


def candidates(mentions: list[dict]) -> list[dict]:
    """Annual-event candidates: 2+ years of coverage, seasonally clustered."""
    out = []
    for ms in group_mentions(mentions):
        years = sorted({m["episode_date"][:4] for m in ms})
        if len(years) < MIN_YEARS:
            continue
        months = [int(m["episode_date"][5:7]) for m in ms]
        share, month = seasonality(months)
        if share < MIN_SEASONALITY:
            continue

        names = Counter(m["name"] for m in ms)
        towns = Counter(m["town"] for m in ms if m["town"])
        types = Counter(m["event_type"] for m in ms if m["event_type"])
        episodes = sorted(
            {(m["episode_date"], m["episode_title"], m["episode_url"]) for m in ms},
            reverse=True,
        )
        out.append({
            "name_variants": [n for n, _ in names.most_common(4)],
            "town_guesses": [t for t, _ in towns.most_common(2)],
            "month": month,
            "years": years,
            "mention_count": len(ms),
            "event_type": types.most_common(1)[0][0] if types else "other",
            "episodes": [
                {"date": d, "title": t, "url": u} for d, t, u in episodes[:3]
            ],
        })
    return out


def curate(cands: list[dict]) -> list[dict]:
    """One Haiku call: canonical names, clean towns, drop non-events."""
    rendered = "\n".join(
        f"[{i}] variants: {c['name_variants']} | towns: {c['town_guesses']} | "
        f"months covered: {sorted({MONTH_NAMES[m - 1] for m in [c['month']]})} | "
        f"years: {c['years']}"
        for i, c in enumerate(cands)
    )
    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=16384,
        messages=[{"role": "user", "content": CURATE_PROMPT.format(groups=rendered)}],
    )
    verdicts = {int(v["index"]): v for v in _parse_json_array(message.content[0].text)
                if isinstance(v, dict) and "index" in v}

    kept = []
    for i, c in enumerate(cands):
        v = verdicts.get(i)
        if not v or not v.get("keep", False):
            continue
        kept.append({
            "name": str(v.get("canonical_name") or c["name_variants"][0]).strip(),
            "town": str(v.get("town", "")).strip(),
            "month": c["month"],
            "years": c["years"],
            "mention_count": c["mention_count"],
            "event_type": c["event_type"],
            "episodes": c["episodes"],
        })
    return kept


def main():
    with open(MENTIONS_PATH) as f:
        mentions = json.load(f)["mentions"]

    cands = candidates(mentions)
    print(f"{len(mentions)} mentions → {len(cands)} annual-event candidates")

    events = curate(cands)
    print(f"After curation: {len(events)} events kept")

    months: dict = {str(m): [] for m in range(1, 13)}
    for e in sorted(events, key=lambda e: (-len(e["years"]), -e["mention_count"])):
        months[str(e["month"])].append(e)

    payload = {"generated": date.today().isoformat(), "months": months}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {sum(len(v) for v in months.values())} events to {OUTPUT_PATH}")

    for m in range(1, 13):
        evs = months[str(m)]
        if evs:
            print(f"  {MONTH_NAMES[m - 1]:10s} {', '.join(e['name'] for e in evs[:4])}"
                  + (f" (+{len(evs) - 4})" if len(evs) > 4 else ""))


if __name__ == "__main__":
    main()
