#!/usr/bin/env python3
"""
Precomputes the /413/ dashboard's data file.

Reads fab413_entities.json (+ episode counts), aggregates everything the
dashboard needs — town bubbles with coordinates, kind/month/timeline
histograms, leaderboards, and the deduplicated explorer index — and writes
docs/413/data.json. Pure Python, no API calls; runs weekly after the miners.

Usage:  python3 fab413_stats.py
"""

import json
import os
import re
from collections import Counter, defaultdict
from datetime import date

from json_storage import write_json_atomic

BASE = os.path.dirname(__file__)
ENTITIES_PATH = os.path.join(BASE, "docs", "data", "fab413_entities.json")
EPISODES_PATH = os.path.join(BASE, "docs", "data", "fab413_episodes.json")
OUTPUT_PATH = os.path.join(BASE, "docs", "413", "data.json")

# Town gazetteer for the map (western MA + close neighbors). Towns not listed
# still appear everywhere else — they just don't get a bubble.
GAZETTEER = {
    "Northampton": (42.3251, -72.6412), "Amherst": (42.3732, -72.5199),
    "Springfield": (42.1015, -72.5898), "Easthampton": (42.2668, -72.6690),
    "Greenfield": (42.5876, -72.5995), "Holyoke": (42.2043, -72.6162),
    "Florence": (42.3626, -72.6740), "North Adams": (42.7003, -73.1087),
    "Lenox": (42.3565, -73.2846), "Great Barrington": (42.1959, -73.3621),
    "Turners Falls": (42.6043, -72.5565), "Shelburne Falls": (42.6042, -72.7392),
    "South Hadley": (42.2584, -72.5742), "Hadley": (42.3418, -72.5884),
    "Williamstown": (42.7120, -73.2037), "Pittsfield": (42.4501, -73.2454),
    "Chicopee": (42.1487, -72.6079), "Westfield": (42.1251, -72.7495),
    "Deerfield": (42.5443, -72.6051), "South Deerfield": (42.4778, -72.6079),
    "Sunderland": (42.4467, -72.5787), "Montague": (42.5359, -72.5350),
    "Orange": (42.5903, -72.3120), "Athol": (42.5959, -72.2267),
    "Ware": (42.2598, -72.2398), "Belchertown": (42.2770, -72.4009),
    "Ludlow": (42.1601, -72.4759), "Stockbridge": (42.2876, -73.3204),
    "Ashfield": (42.5265, -72.7884), "Hatfield": (42.3709, -72.5981),
    "Millers Falls": (42.5818, -72.4926), "Adams": (42.6242, -73.1179),
    "Lee": (42.3042, -73.2482), "Palmer": (42.1584, -72.3287),
    "Wilbraham": (42.1237, -72.4312), "East Longmeadow": (42.0598, -72.5126),
    "Longmeadow": (42.0501, -72.5828), "Agawam": (42.0695, -72.6148),
    "West Springfield": (42.1070, -72.6412), "Whately": (42.4398, -72.6348),
    "Leverett": (42.4520, -72.5023), "Shutesbury": (42.4570, -72.4212),
    "Pelham": (42.3934, -72.4037), "Granby": (42.2565, -72.5162),
    "Bernardston": (42.6709, -72.5495), "Charlemont": (42.6278, -72.8698),
    "Cummington": (42.4629, -72.9051), "Worthington": (42.3998, -72.9309),
    "Huntington": (42.2354, -72.8837), "Chesterfield": (42.3915, -72.8398),
    "Goshen": (42.4401, -72.7995), "Conway": (42.5098, -72.6995),
    "Buckland": (42.5926, -72.7912), "Colrain": (42.6731, -72.6968),
    "Heath": (42.6851, -72.8340), "Rowe": (42.6959, -72.9260),
    "Warwick": (42.6820, -72.3390), "Wendell": (42.5482, -72.3970),
    "New Salem": (42.4990, -72.3320), "Erving": (42.6001, -72.3987),
    "Gill": (42.6398, -72.4995), "Northfield": (42.6959, -72.4529),
    "Hinsdale": (42.4384, -73.1254), "Dalton": (42.4737, -73.1662),
    "Cheshire": (42.5595, -73.1587), "Becket": (42.3320, -73.0829),
    "Housatonic": (42.2626, -73.3665), "Sheffield": (42.1101, -73.3551),
}


def normalize(name: str) -> str:
    n = name.lower()
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\b(the|a|an)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def build_payload(entities: list[dict], n_episodes: int) -> dict:
    """Aggregate mined entities into the dashboard's data payload."""
    # Deduplicate into an explorer index: one row per (normalized name, kind)
    index: dict = {}
    for e in entities:
        key = (normalize(e["name"]), e["kind"])
        row = index.get(key)
        if row is None:
            row = index[key] = {
                "name": e["name"], "kind": e["kind"], "town": e["town"],
                "note": e["note"], "url": e["url"], "count": 0,
                "first": e["episode_date"], "last": e["episode_date"],
                "episodes": [],
            }
        row["count"] += 1
        row["first"] = min(row["first"], e["episode_date"])
        row["last"] = max(row["last"], e["episode_date"])
        if not row["town"] and e["town"]:
            row["town"] = e["town"]
        if not row["url"] and e["url"]:
            row["url"] = e["url"]
        if len(row["episodes"]) < 3:
            row["episodes"].append({"date": e["episode_date"], "url": e["episode_url"]})

    rows = sorted(index.values(), key=lambda r: (-r["count"], r["name"].lower()))

    # Aggregations
    towns = Counter(e["town"] for e in entities if e["town"])
    town_rows = []
    unmapped = []
    for town, count in towns.most_common():
        if town in GAZETTEER:
            lat, lng = GAZETTEER[town]
            town_rows.append({"town": town, "count": count, "lat": lat, "lng": lng})
        else:
            unmapped.append({"town": town, "count": count})

    kinds = Counter(e["kind"] for e in entities)
    months = Counter(int(e["episode_date"][5:7]) for e in entities)

    # Timeline: entities per quarter per kind
    timeline: dict = defaultdict(Counter)
    for e in entities:
        y, m = int(e["episode_date"][:4]), int(e["episode_date"][5:7])
        q = f"{y}-Q{(m - 1) // 3 + 1}"
        timeline[q][e["kind"]] += 1
    quarters = sorted(timeline)

    return {
        "generated": date.today().isoformat(),
        "totals": {
            "episodes": n_episodes,
            "entities": len(entities),
            "unique": len(rows),
            "towns": len(towns),
        },
        "towns": town_rows,
        "unmapped_towns": unmapped[:20],
        "kinds": dict(kinds.most_common()),
        "months": {str(m): months.get(m, 0) for m in range(1, 13)},
        "timeline": {
            "quarters": quarters,
            "series": {
                kind: [timeline[q].get(kind, 0) for q in quarters]
                for kind in kinds
            },
        },
        "index": rows,
    }


def main(*, entities_path=None, episodes_path=None, output_path=None):
    entities_path = entities_path or ENTITIES_PATH
    episodes_path = episodes_path or EPISODES_PATH
    output_path = output_path or OUTPUT_PATH
    with open(entities_path) as f:
        entities = json.load(f)["entities"]
    with open(episodes_path) as f:
        n_episodes = json.load(f)["count"]

    payload = build_payload(entities, n_episodes)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    write_json_atomic(output_path, payload, separators=(",", ":"))
    print(
        f"Wrote {output_path}: {len(entities)} mentions, "
        f"{payload['totals']['unique']} unique things, "
        f"{len(payload['towns'])} mapped towns"
    )


if __name__ == "__main__":
    main()
