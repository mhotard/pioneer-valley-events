"""Tests for the Fabulous 413 seasonal-guide logic and the digest radar."""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from email_digest import radar_events
from fab413_guide import candidates, normalize, seasonality


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
