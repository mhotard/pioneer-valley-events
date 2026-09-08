#!/usr/bin/env python3
"""
The Fabulous 413 podcast miner.

Fetches the show's full RSS feed (~800 episodes back to Feb 2023) and uses
Haiku to extract every local event/happening mentioned in each episode
description. Results accumulate in docs/data/fab413_mentions.json —
append-only, keyed by episode guid, so re-runs only mine NEW episodes.

This is the raw material for the seasonal guide: mentions carry the episode
date, so events that recur across years (Green River Festival every July...)
can be detected by grouping mentions.

Usage:
    source ~/.zshrc && python3 fab413_miner.py             # mine new episodes
    source ~/.zshrc && python3 fab413_miner.py --limit 12  # smoke test
"""

import argparse
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from fab413_common import (
    empty_checkpoint,
    extract_rows,
    mine_incrementally,
    validated_checkpoint,
)
from json_storage import read_json, write_json_atomic
from scrapers.base import BROWSER_UA

FEED_URL = "https://publicfeeds.net/f/3459/feed-rss.xml"
OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "docs", "data", "fab413_mentions.json"
)
# Raw episode descriptions, kept forever: the feed could truncate or vanish
# any time, and the raw text is what lets us re-mine with better prompts later.
EPISODES_PATH = os.path.join(
    os.path.dirname(__file__), "docs", "data", "fab413_episodes.json"
)
BATCH_SIZE = 8  # episodes per Haiku call

EXTRACT_PROMPT = """\
You are mining episode descriptions of "The Fabulous 413," a public-radio show
about culture and events in Western Massachusetts (the 413: Pioneer Valley,
Hilltowns, and Berkshires). For EACH episode below, extract the distinct local
events, festivals, exhibits, markets, performances, and recurring traditions
the episode covers.

Return a JSON array. Each element must have exactly these fields:
  episode    — integer index of the episode it came from (given in brackets)
  name       — short canonical name of the event/happening (e.g. "Green River Festival")
  venue      — venue name if identifiable, else ""
  town       — town/city if identifiable, else ""
  event_type — one of: festival, music, arts, food, outdoor, market, exhibit,
               theater, community, other
  timing     — timing language from the text ("mid-July", "every June",
               "this weekend", "through August"), else ""
  annual     — true if described as annual or recurring yearly
               ("27th annual", "returns this year", "every summer"), else false
  url        — the URL linked for this event/venue in the text, else ""

Rules:
- Only include actual happenings or visitable places tied to a happening.
  Skip interviews with no event, general chat topics, weather, and politics.
- One element per distinct event; don't repeat the same event within an episode.
- Return ONLY valid JSON. No markdown fences. [] if nothing qualifies.

Episodes:
{episodes}"""


def fetch_feed() -> list[dict]:
    """Return all episodes: guid, date (YYYY-MM-DD), title, text, link."""
    resp = requests.get(FEED_URL, headers={"User-Agent": BROWSER_UA}, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "xml")

    episodes = []
    for item in soup.find_all("item"):
        guid = item.find("guid")
        guid = guid.get_text(strip=True) if guid else ""
        title = item.find("title")
        title = title.get_text(strip=True) if title else ""
        link = item.find("link")
        link = link.get_text(strip=True) if link else ""
        pub = item.find("pubDate")
        pub = pub.get_text(strip=True) if pub else ""
        try:
            date = datetime.strptime(pub[:16].strip(), "%a, %d %b %Y").strftime("%Y-%m-%d")
        except ValueError:
            date = ""

        # Description HTML → text, keeping link targets inline: "text (url)"
        desc = item.find("description")
        desc_soup = BeautifulSoup(desc.get_text() if desc else "", "html.parser")
        for a in desc_soup.find_all("a", href=True):
            a.replace_with(f"{a.get_text(strip=True)} ({a['href']})")
        text = re.sub(r"\s+", " ", desc_soup.get_text(" ", strip=True))[:2500]

        if guid and date and text:
            episodes.append(
                {"guid": guid, "date": date, "title": title, "link": link, "text": text}
            )
    return episodes


def load_store(path=None) -> dict:
    path = path or OUTPUT_PATH
    value = read_json(path, default_factory=lambda: empty_checkpoint("mentions"))
    return validated_checkpoint(value, path, result_key="mentions")


def validated_episode_rows(
    value: object, path: str, *, reject_duplicate_guids: bool = True
) -> list[dict]:
    if not isinstance(value, dict) or not isinstance(value.get("episodes"), list):
        raise ValueError(f"Invalid episode snapshot in {path}: expected an episodes list")

    seen_guids = set()
    for index, episode in enumerate(value["episodes"]):
        if not isinstance(episode, dict):
            raise ValueError(f"Invalid episode row {index} in {path}: expected an object")
        guid = episode.get("guid")
        if not isinstance(guid, str) or not guid.strip():
            raise ValueError(f"Invalid episode row {index} in {path}: unusable guid")
        for field in ("date", "title", "link", "text"):
            item = episode.get(field)
            if not isinstance(item, str):
                raise ValueError(
                    f"Invalid episode row {index} in {path}: expected string {field}"
                )
        if reject_duplicate_guids and guid in seen_guids:
            raise ValueError(f"Duplicate episode guid {guid!r} in {path}")
        seen_guids.add(guid)
    return value["episodes"]


def save_episodes(episodes: list[dict], path=None):
    """Merge fetched episodes into the raw-episode snapshot (append-only by
    guid — episodes already saved survive even if the feed later drops them)."""
    path = path or EPISODES_PATH
    stored = read_json(path, default_factory=lambda: {"episodes": []})
    known = {episode["guid"]: episode for episode in validated_episode_rows(stored, path)}
    incoming = validated_episode_rows(
        {"episodes": episodes},
        "fetched episode feed",
        reject_duplicate_guids=False,
    )
    for ep in incoming:
        known[ep["guid"]] = ep  # newest fetch wins for existing guids
    merged = sorted(known.values(), key=lambda e: e["date"], reverse=True)
    write_json_atomic(
        path,
        {"count": len(merged), "episodes": merged},
        separators=(",", ":"),
    )
    return len(merged)


def save_store(store: dict, path=None) -> None:
    path = path or OUTPUT_PATH
    validated_checkpoint(store, path, result_key="mentions")
    write_json_atomic(path, store, separators=(",", ":"))


def mine_batch(batch: list[dict]) -> list[dict]:
    """One Haiku call over a batch of episodes; returns mention dicts."""
    mentions = []
    for m in extract_rows(batch, EXTRACT_PROMPT):
        try:
            idx = int(m.get("episode", -1))
            if not (0 <= idx < len(batch)) or not str(m.get("name", "")).strip():
                continue
            ep = batch[idx]
            mentions.append({
                "name": str(m.get("name", "")).strip(),
                "venue": str(m.get("venue", "")).strip(),
                "town": str(m.get("town", "")).strip(),
                "event_type": str(m.get("event_type", "other")).strip(),
                "timing": str(m.get("timing", "")).strip(),
                "annual": bool(m.get("annual", False)),
                "url": str(m.get("url", "")).strip(),
                "episode_date": ep["date"],
                "episode_title": ep["title"],
                "episode_url": ep["link"],
            })
        except (TypeError, ValueError, AttributeError):
            continue
    return mentions


def main(argv=None, *, output_path=None, episodes_path=None):
    parser = argparse.ArgumentParser(description="Mine Fabulous 413 episodes for events")
    parser.add_argument("--limit", type=int, help="Only mine the N newest unmined episodes")
    args = parser.parse_args(argv)

    output_path = output_path or OUTPUT_PATH
    episodes_path = episodes_path or EPISODES_PATH

    store = load_store(output_path)
    mined = set(store["mined_guids"])

    episodes = fetch_feed()
    total_saved = save_episodes(episodes, episodes_path)
    todo = [ep for ep in episodes if ep["guid"] not in mined]
    if args.limit:
        todo = todo[: args.limit]
    print(
        f"Feed: {len(episodes)} episodes ({total_saved} in raw snapshot) | "
        f"already mined: {len(mined)} | to mine: {len(todo)}"
    )
    if not todo:
        return

    total_new = mine_incrementally(
        todo,
        store,
        result_key="mentions",
        mine_batch=mine_batch,
        save=lambda current: save_store(current, output_path),
        batch_size=BATCH_SIZE,
    )
    print(f"\nDone: {total_new} new mentions, {len(store['mentions'])} total → {output_path}")


if __name__ == "__main__":
    main()
