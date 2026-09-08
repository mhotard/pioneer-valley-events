"""Offline tests for pipeline collection, publication, and CLI orchestration."""

import json
import logging
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pipeline
from scrapers.base import BaseScraper, Event

RUN_DATE = date(2026, 7, 10)


class FakeScraper(BaseScraper):
    def __init__(self, name, events=(), *, error=None, needs_api_key=False):
        self.name = name
        self.url = f"https://example.com/{name}"
        self.events = list(events)
        self.error = error
        self.needs_api_key = needs_api_key
        self.fetch_count = 0

    def _fetch(self):
        self.fetch_count += 1
        if self.error:
            raise RuntimeError(self.error)
        return self.events


def event(title, source, event_date="2026-07-11", **kwargs):
    return Event(
        title=title,
        date=event_date,
        venue=kwargs.get("venue", "Test Venue"),
        town="Amherst",
        source=source,
        category="music",
        time=kwargs.get("time", "7:00 PM"),
        description=kwargs.get("description", ""),
        url="https://example.com/event",
    )


@pytest.fixture(autouse=True)
def isolate_cli(monkeypatch, caplog):
    monkeypatch.delenv("ANTHROPIC_API_KEY_PIONEER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        pipeline,
        "setup_logging",
        lambda: (logging.getLogger("pipeline"), "(test logging)"),
    )
    caplog.set_level(logging.INFO, logger="pipeline")


def invoke(monkeypatch, tmp_path, scrapers, argv=()):
    output_path = tmp_path / "published" / "events.json"
    archive_dir = tmp_path / "archives"
    monkeypatch.setattr(pipeline, "get_all_scrapers", lambda: scrapers)
    status = pipeline.main(
        list(argv),
        output_path=str(output_path),
        archive_dir=str(archive_dir),
        run_date=RUN_DATE,
    )
    return status, output_path, archive_dir


def seed_previous_events(path, counts):
    path.parent.mkdir(parents=True, exist_ok=True)
    events = []
    for source, count in counts.items():
        events.extend({"id": f"{source}-{i}", "source": source} for i in range(count))
    path.write_text(json.dumps({"generated": "2026-07-03", "events": events}))


def seed_archive(path, record=None):
    path.mkdir(parents=True, exist_ok=True)
    archive = path / "archive-2026.json"
    record = record or {"id": "sentinel", "date": "2026-07-11"}
    archive.write_text(
        json.dumps({"year": "2026", "count": 1, "events": [record]}, separators=(",", ":"))
    )
    return archive


def test_collection_returns_result_and_has_no_publication_side_effects(
    monkeypatch, tmp_path
):
    inside = event("Inside", "alpha")
    outside = event("Outside", "alpha", "2027-01-01")
    duplicate = event("Inside!", "beta", description="richer description")
    scrapers = [FakeScraper("alpha", [inside, outside]), FakeScraper("beta", [duplicate])]

    def fail_io(*args, **kwargs):
        pytest.fail("collection attempted file I/O")

    monkeypatch.setattr("builtins.open", fail_io)
    monkeypatch.setattr(pipeline, "read_json", fail_io)
    monkeypatch.setattr(pipeline, "write_json_atomic", fail_io)
    monkeypatch.setattr(pipeline, "publish_payload", fail_io)

    result = pipeline.run(scrapers, previous_counts={}, run_date=RUN_DATE)

    assert [scraper.fetch_count for scraper in scrapers] == [1, 1]
    assert result.results == [
        pipeline.SourceResult("alpha", "https://example.com/alpha", 2, None),
        pipeline.SourceResult("beta", "https://example.com/beta", 1, None),
    ]
    assert result.regressions == []
    assert result.payload == {
        "generated": "2026-07-10",
        "events": [
            {
                "id": "evt-3f9168a06c",
                "title": "Inside!",
                "date": "2026-07-11",
                "venue": "Test Venue",
                "town": "Amherst",
                "source": "beta",
                "category": "music",
                "time": "7:00 PM",
                "end_time": "",
                "address": "",
                "description": "richer description",
                "url": "https://example.com/event",
                "image_url": None,
            }
        ],
    }
    assert list(tmp_path.iterdir()) == []


def test_healthy_full_run_publishes_payload_and_archive(monkeypatch, tmp_path, caplog):
    scraper = FakeScraper("alpha", [event("Café Show", "alpha")])

    status, output_path, archive_dir = invoke(monkeypatch, tmp_path, [scraper])

    assert status == 0
    assert json.loads(output_path.read_text())["generated"] == "2026-07-10"
    assert "Café Show" in output_path.read_text()
    archive = json.loads((archive_dir / "archive-2026.json").read_text())
    assert archive["events"][0]["first_seen"] == "2026-07-10"
    assert "Wrote 1 events" in caplog.text


def test_one_failure_of_three_still_publishes(monkeypatch, tmp_path):
    scrapers = [
        FakeScraper("failed", error="offline"),
        FakeScraper("alpha", [event("Alpha", "alpha")]),
        FakeScraper("beta", [event("Beta", "beta")]),
    ]

    status, output_path, archive_dir = invoke(monkeypatch, tmp_path, scrapers)

    assert status == 0
    assert output_path.exists()
    assert (archive_dir / "archive-2026.json").exists()


def test_all_sources_fail_without_touching_existing_publication(monkeypatch, tmp_path, caplog):
    scrapers = [FakeScraper(name, error="offline") for name in ("alpha", "beta", "gamma")]
    output_path = tmp_path / "published" / "events.json"
    archive_dir = tmp_path / "archives"
    seed_previous_events(output_path, {"alpha": 5})
    archive = seed_archive(archive_dir)
    output_before = output_path.read_bytes()
    archive_before = archive.read_bytes()
    monkeypatch.setattr(pipeline, "get_all_scrapers", lambda: scrapers)
    monkeypatch.setattr(
        pipeline,
        "publish_payload",
        lambda *args, **kwargs: pytest.fail("rejected run attempted publication"),
    )

    status = pipeline.main(
        [], output_path=str(output_path), archive_dir=str(archive_dir), run_date=RUN_DATE
    )

    assert status == 1
    assert output_path.read_bytes() == output_before
    assert archive.read_bytes() == archive_before
    assert "3 of 3 sources unhealthy" in caplog.text
    assert "ERROR" in caplog.text
    assert "offline" in caplog.text


def test_yield_regressions_reject_without_touching_files(monkeypatch, tmp_path):
    updated = event("Updated Event", "gamma", description="new description")
    scrapers = [FakeScraper("alpha"), FakeScraper("beta"), FakeScraper("gamma", [updated])]
    output_path = tmp_path / "published" / "events.json"
    archive_dir = tmp_path / "archives"
    seed_previous_events(output_path, {"alpha": 5, "beta": 6})
    archived_record = {**updated.to_dict(), "description": "old", "first_seen": "2026-07-01"}
    archive = seed_archive(archive_dir, archived_record)
    before = (output_path.read_bytes(), archive.read_bytes())
    monkeypatch.setattr(pipeline, "get_all_scrapers", lambda: scrapers)
    monkeypatch.setattr(
        pipeline,
        "publish_payload",
        lambda *args, **kwargs: pytest.fail("rejected run attempted publication"),
    )

    status = pipeline.main(
        [], output_path=str(output_path), archive_dir=str(archive_dir), run_date=RUN_DATE
    )

    assert status == 1
    assert (output_path.read_bytes(), archive.read_bytes()) == before


def test_rejected_first_run_creates_no_publication(monkeypatch, tmp_path):
    scrapers = [FakeScraper("alpha", error="offline")]

    status, output_path, archive_dir = invoke(monkeypatch, tmp_path, scrapers)

    assert status == 1
    assert not output_path.exists()
    assert not archive_dir.exists()


@pytest.mark.parametrize("preexisting", [False, True])
def test_healthy_dry_run_never_publishes(monkeypatch, tmp_path, preexisting, caplog):
    scraper = FakeScraper("alpha", [event("Alpha", "alpha")])
    output_path = tmp_path / "published" / "events.json"
    archive_dir = tmp_path / "archives"
    if preexisting:
        seed_previous_events(output_path, {"old": 1})
        archive = seed_archive(archive_dir)
        before = (output_path.read_bytes(), archive.read_bytes())
    monkeypatch.setattr(pipeline, "get_all_scrapers", lambda: [scraper])

    status = pipeline.main(
        ["--dry-run"],
        output_path=str(output_path),
        archive_dir=str(archive_dir),
        run_date=RUN_DATE,
    )

    assert status == 0
    assert "DRY RUN" in caplog.text
    if preexisting:
        assert (output_path.read_bytes(), archive.read_bytes()) == before
    else:
        assert not output_path.exists()
        assert not archive_dir.exists()


def test_unhealthy_full_dry_run_fails_without_publication(monkeypatch, tmp_path):
    status, output_path, archive_dir = invoke(
        monkeypatch,
        tmp_path,
        [FakeScraper("alpha", error="offline")],
        ["--dry-run"],
    )

    assert status == 1
    assert not output_path.exists()
    assert not archive_dir.exists()


@pytest.mark.parametrize("extra_args", [[], ["--dry-run"]])
def test_single_source_fetches_only_selection_and_never_publishes(
    monkeypatch, tmp_path, extra_args
):
    selected = FakeScraper("selected", error="offline")
    unselected = FakeScraper("unselected", [event("Other", "unselected")])

    status, output_path, archive_dir = invoke(
        monkeypatch,
        tmp_path,
        [selected, unselected],
        ["--source", "selected", *extra_args],
    )

    assert status == 0
    assert selected.fetch_count == 1
    assert unselected.fetch_count == 0
    assert not output_path.exists()
    assert not archive_dir.exists()


def test_unknown_source_exits_before_fetch_or_publication(monkeypatch, tmp_path):
    scraper = FakeScraper("known", [event("Known", "known")])

    status, output_path, archive_dir = invoke(
        monkeypatch, tmp_path, [scraper], ["--source", "unknown"]
    )

    assert status == 1
    assert scraper.fetch_count == 0
    assert not output_path.exists()
    assert not archive_dir.exists()


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--dry-run"],
        ["--source", "claude"],
        ["--source", "claude", "--dry-run"],
    ],
)
def test_missing_api_key_exits_before_fetch(monkeypatch, tmp_path, args):
    scraper = FakeScraper("claude", needs_api_key=True)

    status, output_path, archive_dir = invoke(monkeypatch, tmp_path, [scraper], args)

    assert status == 1
    assert scraper.fetch_count == 0
    assert not output_path.exists()
    assert not archive_dir.exists()


def test_unselected_key_source_does_not_block_selected_source(monkeypatch, tmp_path):
    selected = FakeScraper("selected", [event("Selected", "selected")])
    key_source = FakeScraper("claude", needs_api_key=True)

    status, output_path, _archive_dir = invoke(
        monkeypatch,
        tmp_path,
        [selected, key_source],
        ["--source", "selected"],
    )

    assert status == 0
    assert selected.fetch_count == 1
    assert key_source.fetch_count == 0
    assert not output_path.exists()


def test_explicit_paths_control_previous_counts_and_publication(monkeypatch, tmp_path):
    output_path = tmp_path / "custom" / "events.json"
    archive_dir = tmp_path / "custom-archives"
    seed_previous_events(output_path, {"alpha": 5})
    scrapers = [FakeScraper("alpha"), FakeScraper("beta"), FakeScraper("gamma")]
    monkeypatch.setattr(pipeline, "get_all_scrapers", lambda: scrapers)
    monkeypatch.setattr(pipeline, "OUTPUT_PATH", str(tmp_path / "wrong" / "events.json"))
    monkeypatch.setattr(pipeline, "ARCHIVE_DIR", str(tmp_path / "wrong-archives"))

    status = pipeline.main(
        [], output_path=str(output_path), archive_dir=str(archive_dir), run_date=RUN_DATE
    )

    assert status == 0
    assert json.loads(output_path.read_text())["events"] == []
    assert not (tmp_path / "wrong").exists()
    assert not (tmp_path / "wrong-archives").exists()


def test_publication_error_propagates_without_false_success(monkeypatch, tmp_path, caplog):
    scraper = FakeScraper("alpha", [event("Alpha", "alpha")])

    def fail_publication(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pipeline, "publish_payload", fail_publication)
    monkeypatch.setattr(pipeline, "get_all_scrapers", lambda: [scraper])

    with pytest.raises(OSError, match="disk full"):
        pipeline.main(
            [],
            output_path=str(tmp_path / "events.json"),
            archive_dir=str(tmp_path / "archives"),
            run_date=RUN_DATE,
        )

    assert "Wrote" not in caplog.text


def test_corrupt_published_history_means_no_regressions_but_run_proceeds(
    monkeypatch, tmp_path, caplog
):
    output_path = tmp_path / "published" / "events.json"
    output_path.parent.mkdir()
    output_path.write_bytes(b"{not json")
    # alpha yields zero; with readable history of >=5 it would be a regression.
    scrapers = [FakeScraper("alpha"), FakeScraper("beta", [event("Beta", "beta")])]

    status, output_path, _archive_dir = invoke(monkeypatch, tmp_path, scrapers)

    assert status == 0
    assert "Yield regressions" not in caplog.text
    assert json.loads(output_path.read_text())["events"][0]["title"] == "Beta"
