"""Tests for the Fabulous 413 seasonal-guide logic and the digest radar."""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import fab413_guide
from email_digest import radar_events
from fab413_guide import candidates, normalize, seasonality
from fab413_stats import build_payload


def mention(name, episode_date, town="Greenfield", event_type="festival"):
    return {
        "name": name, "episode_date": episode_date, "town": town,
        "event_type": event_type, "episode_title": "ep", "episode_url": "https://x",
        "venue": "", "timing": "", "annual": True, "url": "",
    }


class TestNormalize:
    def test_strips_years_and_ordinals(self):
        assert normalize("27th Annual Green River Festival 2026") == "green river"

    def test_variants_collapse(self):
        assert normalize("Solid Sound Festival 2026") == normalize("Solid Sound")


class TestSeasonality:
    def test_clustered_months_score_high(self):
        share, month = seasonality([6, 7, 7, 6])
        assert share == 1.0
        assert month in (6, 7)  # ties within the window resolve to the earlier month

    def test_scattered_months_score_low(self):
        share, _ = seasonality([1, 3, 5, 7, 9, 11])
        assert share < 0.6

    def test_december_january_wraps(self):
        share, _ = seasonality([12, 1, 12, 1])
        assert share == 1.0


class TestCandidates:
    def test_annual_event_across_two_years_kept(self):
        ms = [mention("Green River Festival", "2023-07-10"),
              mention("Green River Festival 2024", "2024-07-08")]
        out = candidates(ms)
        assert len(out) == 1
        assert out[0]["years"] == ["2023", "2024"]

    def test_single_year_event_dropped(self):
        ms = [mention("One Off Fest", "2024-07-10"),
              mention("One Off Fest", "2024-07-11")]
        assert candidates(ms) == []

    def test_weekly_series_dropped_by_seasonality(self):
        ms = [mention("Live Music Friday", f"{y}-{m:02d}-05")
              for y in (2023, 2024) for m in (1, 3, 5, 7, 9, 11)]
        assert candidates(ms) == []


class TestCurate:
    CANDS = [
        {"name_variants": ["27th Green River Festival"], "town_guesses": ["Greenfield"],
         "month": 7, "years": ["2023", "2024"], "mention_count": 5,
         "event_type": "festival", "episodes": []},
        {"name_variants": ["Live Music Friday"], "town_guesses": [],
         "month": 3, "years": ["2023", "2024"], "mention_count": 2,
         "event_type": "other", "episodes": []},
    ]

    def test_goes_through_call_haiku_and_applies_verdicts(self, monkeypatch):
        calls = []

        def fake_call_haiku(prompt, **kwargs):
            calls.append(kwargs)
            return ('[{"index": 0, "canonical_name": "Green River Festival", '
                    '"town": "Greenfield", "keep": true}, '
                    '{"index": 1, "canonical_name": "Live Music Friday", "keep": false}]')

        monkeypatch.setattr(fab413_guide, "call_haiku", fake_call_haiku)
        kept = fab413_guide.curate(self.CANDS)

        assert [e["name"] for e in kept] == ["Green River Festival"]
        assert kept[0]["town"] == "Greenfield"
        assert calls and calls[0]["label"]


def entity(name, kind, town, episode_date, note="", url=""):
    return {
        "name": name, "kind": kind, "town": town, "note": note, "url": url,
        "episode_date": episode_date, "episode_title": "ep",
        "episode_url": "https://nepm.org/ep",
    }


class TestBuildPayload:
    ENTITIES = [
        entity("The Iron Horse", "venue", "Northampton", "2024-06-01"),
        entity("Iron Horse", "venue", "Northampton", "2025-06-10"),  # same thing
        entity("Green River Festival", "event", "Greenfield", "2024-07-01"),
        entity("Mystery Spot", "place", "Atlantis", "2024-08-01"),  # unmapped town
    ]

    def test_index_dedupes_name_variants(self):
        p = build_payload(self.ENTITIES, n_episodes=10)
        venues = [r for r in p["index"] if r["kind"] == "venue"]
        assert len(venues) == 1
        assert venues[0]["count"] == 2
        assert venues[0]["first"] == "2024-06-01"
        assert venues[0]["last"] == "2025-06-10"

    def test_mapped_towns_get_coordinates(self):
        p = build_payload(self.ENTITIES, n_episodes=10)
        noho = next(t for t in p["towns"] if t["town"] == "Northampton")
        assert 42 < noho["lat"] < 43 and -73 < noho["lng"] < -72
        assert noho["count"] == 2

    def test_unmapped_town_listed_not_dropped(self):
        p = build_payload(self.ENTITIES, n_episodes=10)
        assert {"town": "Atlantis", "count": 1} in p["unmapped_towns"]
        assert p["totals"]["towns"] == 3  # unmapped still counts

    def test_totals_and_kinds(self):
        p = build_payload(self.ENTITIES, n_episodes=10)
        assert p["totals"] == {"episodes": 10, "entities": 4, "unique": 3, "towns": 3}
        assert p["kinds"]["venue"] == 2

    def test_timeline_series_align_with_quarters(self):
        p = build_payload(self.ENTITIES, n_episodes=10)
        tl = p["timeline"]
        for series in tl["series"].values():
            assert len(series) == len(tl["quarters"])


class TestRadarEvents:
    SEASONAL = {"months": {
        "7": [{"name": "Green River Festival", "town": "Greenfield",
               "years": ["2023", "2024", "2025"], "mention_count": 16}],
        "8": [{"name": "Arcadia Folk Festival", "town": "Easthampton",
               "years": ["2024", "2025"], "mention_count": 3}],
        "12": [{"name": "First Night", "town": "Northampton",
                "years": ["2023", "2024"], "mention_count": 4}],
        "1": [{"name": "January Thing", "town": "",
               "years": ["2024", "2025"], "mention_count": 2}],
    }}

    def test_this_month_and_next(self):
        out = radar_events(self.SEASONAL, today=date(2026, 7, 15))
        names = [e["name"] for e in out]
        assert names == ["Green River Festival", "Arcadia Folk Festival"]

    def test_december_wraps_to_january(self):
        out = radar_events(self.SEASONAL, today=date(2026, 12, 5))
        names = {e["name"] for e in out}
        assert names == {"First Night", "January Thing"}

    def test_sorted_by_years_then_mentions(self):
        out = radar_events(self.SEASONAL, today=date(2026, 7, 1))
        assert out[0]["name"] == "Green River Festival"  # 3 years beats 2

    def test_no_seasonal_data(self):
        assert radar_events(None) == []
