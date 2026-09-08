"""Shared plumbing for the two Fabulous 413 miners.

fab413_miner.py (events → seasonal guide) and fab413_entities.py (everything
→ /413/ dashboard) differ only in their prompt, their output path, and how
they shape Haiku's rows. The checkpoint format, the batch rendering, and the
incremental mine-and-checkpoint loop live here so the two can't drift.
"""

import sys

from scrapers.claude_scraper import _parse_json_array, call_haiku

MAX_CONSECUTIVE_FAILS = 3  # abort the run instead of silently skipping the rest


def empty_checkpoint(result_key: str) -> dict:
    return {"mined_guids": [], result_key: []}


def validated_checkpoint(value: object, path, *, result_key: str) -> dict:
    """Return a mining checkpoint after checking the shape needed to resume."""
    if not isinstance(value, dict):
        raise ValueError(f"Invalid mining checkpoint in {path}: expected an object")
    mined_guids = value.get("mined_guids")
    rows = value.get(result_key)
    if not isinstance(mined_guids, list) or not all(
        isinstance(guid, str) for guid in mined_guids
    ):
        raise ValueError(f"Invalid mining checkpoint in {path}: expected string mined_guids")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"Invalid mining checkpoint in {path}: expected object {result_key}")
    return value


def render_batch(batch: list[dict]) -> str:
    """Format a batch of episodes the way both extraction prompts expect."""
    return "\n\n".join(
        f"[Episode {i} | {ep['date']} | {ep['title']}]\n{ep['text']}"
        for i, ep in enumerate(batch)
    )


def extract_rows(batch: list[dict], prompt: str) -> list:
    """One Haiku call over a rendered batch; returns the parsed JSON array."""
    return _parse_json_array(call_haiku(prompt.format(episodes=render_batch(batch))))


def mine_incrementally(
    todo: list[dict],
    store: dict,
    *,
    result_key: str,
    mine_batch,
    save,
    batch_size: int,
    max_consecutive_fails: int = MAX_CONSECUTIVE_FAILS,
) -> int:
    """Mine `todo` in batches, checkpointing after each successful batch.

    A failed batch is skipped (its guids stay unmined, so a re-run retries
    it). After `max_consecutive_fails` failures in a row the run exits 1 with
    every earlier successful batch already saved — a rate-limited run must
    never look like a complete one. Returns the number of new rows added.
    """
    total_new = 0
    consecutive_fails = 0
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        try:
            rows = mine_batch(batch)
            consecutive_fails = 0
        except Exception as e:
            consecutive_fails += 1
            print(f"  batch at {start}: ERROR {e} — skipping", file=sys.stderr)
            if consecutive_fails >= max_consecutive_fails:
                print(
                    f"  {consecutive_fails} consecutive failures — aborting "
                    "(progress is saved; re-run to resume)", file=sys.stderr,
                )
                sys.exit(1)
            continue
        store[result_key].extend(rows)
        store["mined_guids"].extend(ep["guid"] for ep in batch)
        save(store)
        total_new += len(rows)
        done = min(start + batch_size, len(todo))
        print(f"  {done}/{len(todo)} episodes → {total_new} {result_key} so far")
    return total_new
