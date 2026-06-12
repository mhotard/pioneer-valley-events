"""Scraper for Mount Holyoke College events — Localist JSON API (events.mtholyoke.edu)."""

import logging

import requests

from .base import BaseScraper, Event
from .umass import guess_category, parse_iso

log = logging.getLogger("pipeline")

API_URL = "https://events.mtholyoke.edu/api/2/events?days=90&pp=100"


class MountHolyokeScraper(BaseScraper):
    name = "mtholyoke"
    url = "https://events.mtholyoke.edu"
    town = "South Hadley"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(API_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        events = []
        seen = set()

        for item in data.get("events", []):
            ev = item.get("event", {})
            title = self.clean(ev.get("title", ""))
            if not title:
                continue

            for inst_wrap in ev.get("event_instances", []):
                inst = inst_wrap.get("event_instance", {})
                start = inst.get("start", "")
                if not start:
                    continue
                date_str, time_str = parse_iso(start)
                if not date_str:
                    continue
                if inst.get("all_day"):
                    time_str = ""

                key = f"{title}|{date_str}"
                if key in seen:
                    continue
                seen.add(key)

                end = inst.get("end") or ""
                end_time_str = parse_iso(end)[1] if end else ""

                events.append(Event(
                    title=title,
                    date=date_str,
                    time=time_str,
                    end_time=end_time_str,
                    venue=self.clean(ev.get("location_name", "")) or "Mount Holyoke College",
                    address=self.clean(ev.get("address", "")) or "South Hadley, MA 01075",
                    town=self.town,
                    description=self.clean(ev.get("description_text", ""))[:500],
                    url=ev.get("localist_url", "") or ev.get("url") or "",
                    image_url=ev.get("photo_url"),
                    category=guess_category(title),
                    source=self.name,
                ))

        log.debug("[%s] Found %d events", self.name, len(events))
        return events
