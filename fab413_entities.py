#!/usr/bin/env python3
"""
The Fabulous 413 — full entity mine (v2).

Where fab413_miner.py extracts *events* (feeding the seasonal guide), this
extracts EVERYTHING the show talks about — restaurants, venues, places,
businesses, people, organizations — from the raw episode descriptions already
stored in docs/data/fab413_episodes.json. No feed fetch, no dependency on the
podcast host. Results accumulate in docs/data/fab413_entities.json,
incremental by episode guid. Powers the /413/ data dashboard.

Usage:
    source ~/.zshrc && python3 fab413_entities.py             # mine new episodes
    source ~/.zshrc && python3 fab413_entities.py --limit 16  # smoke test
"""

import argparse
import json
import os
import sys

from scrapers.claude_scraper import _parse_json_array, call_haiku

MAX_CONSECUTIVE_FAILS = 3  # abort the run instead of silently skipping the rest

EPISODES_PATH = os.path.join(
    os.path.dirname(__file__), "docs", "data", "fab413_episodes.json"
)
OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "docs", "data", "fab413_entities.json"
)
BATCH_SIZE = 8

KINDS = {"event", "venue", "restaurant", "place", "business", "person", "org"}

EXTRACT_PROMPT = """\
You are indexing episode descriptions of "The Fabulous 413," a public-radio
show about life in Western Massachusetts. For EACH episode below, extract
every distinct named thing the episode covers.

Return a JSON array. Each element must have exactly these fields:
  episode — integer index of the episode it came from (given in brackets)
  name    — the thing's proper name as commonly known (no years/ordinals)
  kind    — one of:
            event      (festival, concert, market, happening)
            venue      (music hall, theater, museum, gallery)
            restaurant (restaurant, cafe, bar, brewery, food truck)
            place      (park, trail, river, farm, landmark, neighborhood)
            business   (shop, bookstore, maker, service)
            person     (guest, artist, notable local — real people only)
            org        (nonprofit, band, troupe, institution)
  town    — town/city in or near the 413 if identifiable, else ""
  note    — what it is / why mentioned, max 10 words
  url     — the URL linked for it in the text, else ""

Rules:
- Named things only — skip generic topics ("local farms"), weather, politics.
- The show's hosts (Monte Belmonte, Kaliis Smith) don't count.
- One element per distinct thing per episode.
- Return ONLY valid JSON. No markdown fences. [] if nothing qualifies.

Episodes:
{episodes}"""


def load_episodes() -> list[dict]:
    with open(EPISODES_PATH) as f:
        return json.load(f)["episodes"]


def load_store() -> dict:
    try:
        with open(OUTPUT_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"mined_guids": [], "entities": []}


def mine_batch(batch: list[dict]) -> list[dict]:
    rendered = "\n\n".join(
        f"[Episode {i} | {ep['date']} | {ep['title']}]\n{ep['text']}"
        for i, ep in enumerate(batch)
    )
    raw = _parse_json_array(call_haiku(EXTRACT_PROMPT.format(episodes=rendered)))

    entities = []
    for e in raw:
        try:
            idx = int(e.get("episode", -1))
            name = str(e.get("name", "")).strip()
            kind = str(e.get("kind", "")).strip().lower()
            if not (0 <= idx < len(batch)) or not name or kind not in KINDS:
                continue
            ep = batch[idx]
            entities.append({
                "name": name,
                "kind": kind,
                "town": str(e.get("town", "")).strip(),
                "note": str(e.get("note", "")).strip()[:80],
                "url": str(e.get("url", "")).strip(),
                "episode_date": ep["date"],
                "episode_title": ep["title"],
                "episode_url": ep["link"],
            })
        except (TypeError, ValueError, AttributeError):
            continue
    return entities


def main():
    parser = argparse.ArgumentParser(description="Mine Fabulous 413 episodes for all entities")
    parser.add_argument("--limit", type=int, help="Only mine the N newest unmined episodes")
    args = parser.parse_args()

    store = load_store()
    mined = set(store["mined_guids"])
    episodes = load_episodes()
    todo = [ep for ep in episodes if ep["guid"] not in mined]
    if args.limit:
        todo = todo[: args.limit]
    print(f"Corpus: {len(episodes)} episodes | mined: {len(mined)} | to mine: {len(todo)}")
    if not todo:
        return

    total_new = 0
    consecutive_fails = 0
    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start : start + BATCH_SIZE]
        try:
            entities = mine_batch(batch)
            consecutive_fails = 0
        except Exception as e:
            consecutive_fails += 1
            print(f"  batch at {start}: ERROR {e} — skipping", file=sys.stderr)
            if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                print(
                    f"  {consecutive_fails} consecutive failures — aborting "
                    "(progress is saved; re-run to resume)", file=sys.stderr,
                )
                sys.exit(1)
            continue
        store["entities"].extend(entities)
        store["mined_guids"].extend(ep["guid"] for ep in batch)
        total_new += len(entities)
        done = min(start + BATCH_SIZE, len(todo))
        print(f"  {done}/{len(todo)} episodes → {total_new} entities so far")

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\nDone: {total_new} new entities, {len(store['entities'])} total → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
