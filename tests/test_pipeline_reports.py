"""Offline safety and truthful outcomes for pipeline and workflow diagnostics."""

import json
import logging
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pipeline
from scrapers.base import BaseScraper, Event

RUN_DATE = pipeline.date(2026, 10, 2)
SECRET = "fake-key-fixture-DO-NOT-REPORT"
RAW_ERROR = "raw-error-body-with-private-fixture"


class ReportScraper(BaseScraper):
    def __init__(self, name="alpha", *, count=1, error=None, needs_api_key=False):
        self.name = name
        self.url = "https://example.test/" + SECRET
        self.count = count
        self.error = error
        self.needs_api_key = needs_api_key
        self.calls = 0

    def _fetch(self):
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return [Event(title=f"Event {i}", date="2026-10-03", source=self.name,
                      venue="Test Venue", town="Amherst", category="music")
                for i in range(self.count)]


@pytest.fixture
def setup_run(monkeypatch, tmp_path):
    output = tmp_path / "published" / "events.json"
    archive = tmp_path / "published"
    report = tmp_path / "diagnostics" / "run-report.json"
    monkeypatch.setattr(pipeline, "setup_logging", lambda: (logging.getLogger("pipeline"), "test"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.delenv("ANTHROPIC_API_KEY_PIONEER", raising=False)

    def invoke(scrapers, argv=()):
        monkeypatch.setattr(pipeline, "get_all_scrapers", lambda: scrapers)
        return pipeline.main(list(argv), output_path=str(output), archive_dir=str(archive),
                             report_path=str(report), run_date=RUN_DATE)

    return invoke, output, archive, report


def load_safe(report):
    text = report.read_text()
    assert SECRET not in text
    assert RAW_ERROR not in text
    assert "https:" not in text
    assert "ANTHROPIC" not in text
    return json.loads(text)


@pytest.mark.parametrize("argv,mode,decision,published", [
    ([], "full", "accepted", 1),
    (["--dry-run"], "dry_run", "preview", None),
    (["--source", "alpha"], "single_source", "preview", None),
])
def test_success_and_preview_reports(setup_run, argv, mode, decision, published):
    invoke, output, archive, path = setup_run
    scraper = ReportScraper()
    assert invoke([scraper], argv) == 0
    report = load_safe(path)
    assert scraper.calls == 1
    assert report["run_date"] == "2026-10-02"
    assert report["mode"] == mode
    assert report["status"] == "success"
    assert report["publication"] == decision
    assert report["prepared_event_count"] == 1
    assert report["published_event_count"] == published
    assert report["sources"] == [{"name": "alpha", "count": 1, "status": "ok"}]
    if published:
        assert report["writes"] == [
            {"destination": "events", "status": "written"},
            {"destination": "archive-2026", "status": "written", "new_events": 1},
        ]
    else:
        assert not output.exists()
        assert not archive.exists()
        assert report["writes"] == []


def test_unhealthy_report_is_rejected_and_files_untouched(setup_run):
    invoke, output, archive, path = setup_run
    output.parent.mkdir()
    old_events = {"generated": "2026-09-27", "events": [{"source": "zero"}] * 5}
    output.write_text(json.dumps(old_events))
    archive_file = archive / "archive-2026.json"
    archive_file.write_text('{"events": []}')
    before = (output.read_bytes(), archive_file.read_bytes())
    assert invoke([ReportScraper("broken", error=RAW_ERROR), ReportScraper("zero", count=0)]) == 1
    report = load_safe(path)
    assert report["stage"] == "health"
    assert report["reason"] == "unhealthy_sources"
    assert report["publication"] == "rejected"
    assert report["sources"] == [
        {"name": "broken", "count": 0, "status": "error"},
        {"name": "zero", "count": 0, "status": "regression", "previous_count": 5},
    ]
    assert report["writes"] == []
    assert report["published_event_count"] is None
    assert (output.read_bytes(), archive_file.read_bytes()) == before


def test_missing_key_preflight_did_not_scrape(setup_run, monkeypatch):
    invoke, output, archive, path = setup_run
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    scraper = ReportScraper(needs_api_key=True)
    assert invoke([scraper]) == 1
    report = load_safe(path)
    assert report["stage"] == "preflight"
    assert report["reason"] == "missing_api_key"
    assert report["publication"] == "not_attempted"
    assert report["sources"] == [{"name": "alpha", "count": None, "status": "not_attempted"}]
    assert scraper.calls == 0
    assert not output.exists()
    assert not archive.exists()


def test_single_source_error_remains_preview_with_truthful_source_status(setup_run):
    invoke, _output, _archive, path = setup_run
    assert invoke([ReportScraper(error=RAW_ERROR)], ["--source", "alpha"]) == 0
    report = load_safe(path)
    assert report["publication"] == "preview"
    assert report["sources"][0]["status"] == "error"
    assert report["published_event_count"] is None


def test_events_write_failure_propagates_and_reports_no_written_events(setup_run, monkeypatch):
    invoke, output, _archive, path = setup_run
    real_write = pipeline.write_json_atomic

    def fail_events(destination, *args, **kwargs):
        if str(destination) == str(output):
            raise OSError(RAW_ERROR)
        return real_write(destination, *args, **kwargs)

    monkeypatch.setattr(pipeline, "write_json_atomic", fail_events)
    with pytest.raises(OSError, match=RAW_ERROR):
        invoke([ReportScraper()])
    report = load_safe(path)
    assert report["status"] == "failed"
    assert report["stage"] == "publication"
    assert report["publication"] == "accepted"
    assert report["writes"] == [{"destination": "events", "status": "failed"}]
    assert report["published_event_count"] is None
    assert not output.exists()


def test_archive_failure_reports_partial_publication(setup_run):
    invoke, output, archive, path = setup_run
    archive.mkdir()
    archive_file = archive / "archive-2026.json"
    archive_file.write_text('{broken archive')
    with pytest.raises(pipeline.JsonStorageError):
        invoke([ReportScraper()])
    report = load_safe(path)
    assert report["status"] == "failed"
    assert report["publication"] == "accepted"
    assert report["published_event_count"] == 1
    assert output.exists()
    assert archive_file.read_text() == '{broken archive'
    assert report["writes"] == [
        {"destination": "events", "status": "written"},
        {"destination": "archive-2026", "status": "failed"},
    ]


def test_diagnostic_write_failure_never_swallows_publication_exception(setup_run, monkeypatch):
    invoke, _output, _archive, _path = setup_run

    def fail_write(*args, **kwargs):
        raise OSError(RAW_ERROR)

    monkeypatch.setattr(pipeline, "write_json_atomic", fail_write)
    with pytest.raises(OSError, match=RAW_ERROR):
        invoke([ReportScraper()])


def test_report_cannot_target_publication_directory(setup_run, monkeypatch):
    _invoke, output, archive, _path = setup_run
    scraper = ReportScraper()
    monkeypatch.setattr(pipeline, "get_all_scrapers", lambda: [scraper])
    with pytest.raises(ValueError, match="outside publication"):
        pipeline.main([], output_path=str(output), archive_dir=str(archive),
                      report_path=str(archive / "report.json"), run_date=RUN_DATE)
    assert scraper.calls == 0
    assert not output.exists()


def test_arbitrary_source_name_is_not_diagnostic_free_text(setup_run):
    invoke, _output, _archive, path = setup_run
    assert invoke([ReportScraper(SECRET)], ["--dry-run"]) == 0
    assert load_safe(path)["sources"][0]["name"] == "unknown"


def workflow_summary_script():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/weekly-update.yml"
    workflow = path.read_text()
    script = workflow.split("          python3 - <<'PYTHON'\n", 1)[1]
    script = script.split("          PYTHON", 1)[0]
    return "\n".join(line[10:] for line in script.splitlines()), workflow


@pytest.mark.parametrize("pipeline_outcome,lint_outcome,diagnostic", [
    ("skipped", "failure", "earlier_workflow_failure"),
    ("failure", "success", "pipeline_report_unavailable"),
])
def test_actions_summary_identifies_early_failure(tmp_path, monkeypatch, pipeline_outcome,
                                                lint_outcome, diagnostic):
    directory = tmp_path / "diagnostics"
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("DIAGNOSTIC_DIR", str(directory))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("PIPELINE_OUTCOME", pipeline_outcome)
    monkeypatch.setenv("LINT_OUTCOME", lint_outcome)
    script, workflow = workflow_summary_script()
    exec(compile(script, "workflow-summary", "exec"), {})
    report = load_safe(directory / "workflow-report.json")
    assert report["pipeline_diagnostics"] == diagnostic
    assert diagnostic in summary.read_text()
    assert report["pages_deployment"] == "separate_workflow_check_required"
    assert "cron: '0 6 * * 0'" in workflow
    assert workflow.count("continue-on-error: true") == 4
    assert re.search(r"name: Summarize update diagnostics\n        if: always\(\)", workflow)
    assert re.search(r"name: Upload safe diagnostic reports\n        if: always\(\)", workflow)
    assert "pve-diagnostics/*.json" in workflow
    assert "path: logs/" not in workflow


def test_actions_summary_carries_source_and_write_outcomes(setup_run, monkeypatch):
    invoke, _output, _archive, path = setup_run
    invoke([ReportScraper()])
    summary = path.parent / "summary.md"
    monkeypatch.setenv("DIAGNOSTIC_DIR", str(path.parent))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("PIPELINE_OUTCOME", "success")
    monkeypatch.setenv("PUBLISH_OUTCOME", "failure")
    script, _workflow = workflow_summary_script()
    exec(compile(script, "workflow-summary", "exec"), {})
    text = summary.read_text()
    assert "| alpha | ok | 1 |" in text
    assert "| events | written |" in text
    assert "| publish | failure |" in text
    assert SECRET not in text
    assert RAW_ERROR not in text


def test_actions_summary_explains_rejected_records(setup_run, monkeypatch):
    invoke, _output, _archive, path = setup_run
    scraper = ReportScraper()
    scraper.last_rejected_counts = {"invalid_date": 2, "unsafe_url": 1, SECRET: 10}
    assert invoke([scraper]) == 0
    summary = path.parent / "summary.md"
    monkeypatch.setenv("DIAGNOSTIC_DIR", str(path.parent))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    script, _workflow = workflow_summary_script()
    exec(compile(script, "workflow-summary", "exec"), {})
    text = summary.read_text()
    assert "invalid_date: 2, unsafe_url: 1" in text
    assert SECRET not in text
    assert RAW_ERROR not in text


def test_unknown_selection_reports_no_attempt(setup_run):
    invoke, output, _archive, path = setup_run
    scraper = ReportScraper()
    assert invoke([scraper], ["--source", "not-configured"]) == 1
    report = load_safe(path)
    assert report["stage"] == "selection"
    assert report["reason"] == "unknown_source"
    assert report["sources"] == []
    assert report["publication"] == "not_attempted"
    assert scraper.calls == 0
    assert not output.exists()


def test_setup_exception_still_attempts_safe_report(setup_run, monkeypatch):
    invoke, output, _archive, path = setup_run

    def fail_setup():
        raise OSError(RAW_ERROR)

    monkeypatch.setattr(pipeline, "setup_logging", fail_setup)
    with pytest.raises(OSError, match=RAW_ERROR):
        invoke([ReportScraper()])
    report = load_safe(path)
    assert report["stage"] == "setup"
    assert report["status"] == "failed"
    assert report["publication"] == "not_attempted"
    assert not output.exists()


def test_report_rejects_secondary_publication_path(setup_run):
    _invoke, output, archive, _path = setup_run
    dashboard = Path(pipeline.__file__).parent / "docs" / "413" / "data.json"
    with pytest.raises(ValueError, match="outside publication"):
        pipeline.main([], output_path=str(output), archive_dir=str(archive),
                      report_path=str(dashboard), run_date=RUN_DATE)
