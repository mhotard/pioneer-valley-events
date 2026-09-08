import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PROJECT_PREFIX = "/pioneer-valley-events"


class DocsHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/module-test.html":
            body = b"<!doctype html><title>module test</title>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == PROJECT_PREFIX or path.startswith(f"{PROJECT_PREFIX}/"):
            suffix = self.path[len(PROJECT_PREFIX) :]
            self.path = suffix or "/"
        super().do_GET()

    def log_message(self, _format, *_args):
        pass


@pytest.fixture(scope="session")
def frontend_server():
    handler = partial(DocsHandler, directory=str(DOCS))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def chromium_browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def sample_events():
    def event(event_id, title, date, time="7:00 PM", **overrides):
        value = {
            "id": event_id,
            "title": title,
            "date": date,
            "time": time,
            "end_time": "",
            "venue": "Test Hall",
            "town": "Amherst",
            "address": "1 Main St",
            "description": "Fixture event",
            "category": "music",
            "source": "alpha",
            "url": f"https://example.test/{event_id}",
            "image_url": "",
        }
        value.update(overrides)
        return value

    return [
        event("single", "Solo Concert", "2026-08-05", "7:00 PM"),
        event("multi-untimed", "All Day Art", "2026-08-10", "", category="arts"),
        event("multi-morning", "Morning Jazz", "2026-08-10", "9:00 AM"),
        event("multi-noon", "Noon Lecture", "2026-08-10", "12:00 PM", category="academia"),
        event("multi-evening", "Evening Film", "2026-08-10", "7:00 PM", category="film"),
        event(
            "decoy-town",
            "Morning Jazz Springfield",
            "2026-08-10",
            "10:00 AM",
            town="Springfield",
        ),
        event(
            "regionwide",
            "Valley Market",
            "2026-08-20",
            "11:00 AM",
            town="Pioneer Valley",
            category="food",
            source="community",
        ),
        event("next-month", "September Show", "2026-09-02", "6:00 PM"),
    ]


FIXED_DATE_SCRIPT = """
(() => {
  const RealDate = Date;
  const fixed = new RealDate('2026-08-15T12:00:00-04:00').getTime();
  class FixedDate extends RealDate {
    constructor(...args) { super(...(args.length ? args : [fixed])); }
    static now() { return fixed; }
  }
  window.Date = FixedDate;
})();
"""


@pytest.fixture
def app_page(chromium_browser, frontend_server, sample_events):
    context = chromium_browser.new_context(
        timezone_id="America/New_York",
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()
    page.add_init_script(FIXED_DATE_SCRIPT)
    errors = []
    asset_errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "response",
        lambda response: asset_errors.append(f"{response.status} {response.url}")
        if response.url.startswith(frontend_server) and response.status >= 400
        else None,
    )

    def route_request(route):
        url = route.request.url
        if url == f"{frontend_server}{PROJECT_PREFIX}/data/events.json":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"generated": "2026-08-14", "events": sample_events}),
            )
        elif url.startswith(frontend_server):
            route.continue_()
        else:
            route.abort()

    page.route("**/*", route_request)
    page.goto(f"{frontend_server}{PROJECT_PREFIX}/")
    page.locator("#result-count").wait_for(state="visible")
    try:
        yield page
        assert errors == []
        assert asset_errors == []
    finally:
        context.close()
