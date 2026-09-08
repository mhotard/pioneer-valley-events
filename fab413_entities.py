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
import os
import sys

from fab413_miner import validated_episode_rows
from json_storage import read_json, write_json_atomic
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


def load_episodes(path=None) -> list[dict]:
    path = path or EPISODES_PATH
    return validated_episode_rows(read_json(path), path)


def _validated_checkpoint(value: object, path: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid mining checkpoint in {path}: expected an object")
    mined_guids = value.get("mined_guids")
    entities = value.get("entities")
    if not isinstance(mined_guids, list) or not all(
        isinstance(guid, str) for guid in mined_guids
    ):
        raise ValueError(f"Invalid mining checkpoint in {path}: expected string mined_guids")
    if not isinstance(entities, list) or not all(isinstance(row, dict) for row in entities):
        raise ValueError(f"Invalid mining checkpoint in {path}: expected object entities")
    return value


def load_store(path=None) -> dict:
    path = path or OUTPUT_PATH
    value = read_json(
        path, default_factory=lambda: {"mined_guids": [], "entities": []}
    )
    return _validated_checkpoint(value, path)


def save_store(store: dict, path=None) -> None:
    path = path or OUTPUT_PATH
    _validated_checkpoint(store, path)
    write_json_atomic(path, store, separators=(",", ":"))


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


def main(argv=None, *, output_path=None, episodes_path=None):
    parser = argparse.ArgumentParser(description="Mine Fabulous 413 episodes for all entities")
    parser.add_argument("--limit", type=int, help="Only mine the N newest unmined episodes")
    args = parser.parse_args(argv)

    output_path = output_path or OUTPUT_PATH
    episodes_path = episodes_path or EPISODES_PATH

    store = load_store(output_path)
    mined = set(store["mined_guids"])
    episodes = load_episodes(episodes_path)
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
        save_store(store, output_path)
        total_new += len(entities)
        done = min(start + BATCH_SIZE, len(todo))
        print(f"  {done}/{len(todo)} episodes → {total_new} entities so far")

    print(f"\nDone: {total_new} new entities, {len(store['entities'])} total → {output_path}")


if __name__ == "__main__":
    main()
