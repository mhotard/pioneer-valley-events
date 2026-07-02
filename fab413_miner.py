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
import json
import os
import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scrapers.claude_scraper import BROWSER_UA, _get_client, _parse_json_array

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


def load_store() -> dict:
    try:
        with open(OUTPUT_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"mined_guids": [], "mentions": []}


def save_episodes(episodes: list[dict]):
    """Merge fetched episodes into the raw-episode snapshot (append-only by
    guid — episodes already saved survive even if the feed later drops them)."""
    try:
        with open(EPISODES_PATH) as f:
            known = {e["guid"]: e for e in json.load(f).get("episodes", [])}
    except (OSError, json.JSONDecodeError):
        known = {}
    for ep in episodes:
        known[ep["guid"]] = ep  # newest fetch wins for existing guids
    merged = sorted(known.values(), key=lambda e: e["date"], reverse=True)
    with open(EPISODES_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"count": len(merged), "episodes": merged},
            f, ensure_ascii=False, separators=(",", ":"),
        )
    return len(merged)


def mine_batch(batch: list[dict]) -> list[dict]:
    """One Haiku call over a batch of episodes; returns mention dicts."""
    rendered = "\n\n".join(
        f"[Episode {i} | {ep['date']} | {ep['title']}]\n{ep['text']}"
        for i, ep in enumerate(batch)
    )
    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=16384,
        messages=[{"role": "user", "content": EXTRACT_PROMPT.format(episodes=rendered)}],
    )
    raw = _parse_json_array(message.content[0].text)

    mentions = []
    for m in raw:
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


def main():
    parser = argparse.ArgumentParser(description="Mine Fabulous 413 episodes for events")
    parser.add_argument("--limit", type=int, help="Only mine the N newest unmined episodes")
    args = parser.parse_args()

    store = load_store()
    mined = set(store["mined_guids"])

    episodes = fetch_feed()
    total_saved = save_episodes(episodes)
    todo = [ep for ep in episodes if ep["guid"] not in mined]
    if args.limit:
        todo = todo[: args.limit]
    print(
        f"Feed: {len(episodes)} episodes ({total_saved} in raw snapshot) | "
        f"already mined: {len(mined)} | to mine: {len(todo)}"
    )
    if not todo:
        return

    total_new = 0
    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start : start + BATCH_SIZE]
        try:
            mentions = mine_batch(batch)
        except Exception as e:
            print(f"  batch at {start}: ERROR {e} — skipping", file=sys.stderr)
            continue
        store["mentions"].extend(mentions)
        store["mined_guids"].extend(ep["guid"] for ep in batch)
        total_new += len(mentions)
        done = min(start + BATCH_SIZE, len(todo))
        print(f"  {done}/{len(todo)} episodes → {total_new} mentions so far")

        # Save incrementally so an interrupted run loses nothing
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\nDone: {total_new} new mentions, {len(store['mentions'])} total → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
