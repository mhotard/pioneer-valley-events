"""Published-JSON-only browser checks for the historical podcast pages."""

from copy import deepcopy

import pytest
from playwright.sync_api import expect

from tests.conftest import FIXED_DATE_SCRIPT, PROJECT_PREFIX

SEASONAL = {
    "generated": "2026-08-14",
    "months": {
        "8": [
            {
                "name": "Harvest Fair",
                "town": "Amherst",
                "event_type": "festival",
                "years": ["2024", "2025"],
                "episodes": [
                    {
                        "date": "2024-08-09",
                        "title": "Past fair",
                        "url": "https://example.test/episode",
                    },
                    {"date": "2025-08-08", "title": "Past fair", "url": "javascript:alert(1)"},
                ],
            }
        ]
    },
}
DASHBOARD = {
    "generated": "2026-08-14",
    "totals": {"episodes": 2, "entities": 3, "unique": 2, "towns": 2},
    "towns": [{"town": "Amherst", "count": 2, "lat": 42.37, "lng": -72.52}],
    "unmapped_towns": [{"town": "Unmapped Town", "count": 1}],
    "kinds": {"event": 2, "place": 1},
    "months": {"8": 3},
    "timeline": {"quarters": ["2024-Q3", "2025-Q3"], "series": {"event": [1, 1], "place": [0, 1]}},
    "index": [
        {
            "name": "Harvest Fair",
            "kind": "event",
            "town": "Amherst",
            "note": "Historical fair",
            "url": "https://example.test/fair",
            "count": 2,
            "first": "2024-08-09",
            "last": "2025-08-08",
            "episodes": [{"date": "2025-08-08", "url": "https://example.test/episode"}],
        },
        {
            "name": "Town Green",
            "kind": "place",
            "town": "Unmapped Town",
            "count": 1,
            "url": "javascript:alert(1)",
            "episodes": [{"date": "2025-08-08", "url": "data:text/html,bad"}],
        },
    ],
}
PAGES = {
    "seasonal": (
        "seasonal.html",
        "data/seasonal.json",
        SEASONAL,
        "guide-status-text",
        "guide-retry",
    ),
    "dashboard": ("413/", "413/data.json", DASHBOARD, "data-status", "data-retry"),
}


@pytest.fixture
def secondary_page(chromium_browser, frontend_server):
    contexts = []

    def open_page(kind, payload=None, failure=None, libraries="blocked", width=1280, pending=False):
        context = chromium_browser.new_context(
            timezone_id="Asia/Tokyo",
            viewport={"width": width, "height": 900},
        )
        contexts.append(context)
        page = context.new_page()
        page.add_init_script(FIXED_DATE_SCRIPT)
        errors, requests, held = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        path, data_path, default, _, _ = PAGES[kind]

        def respond(route):
            url = route.request.url
            requests.append(url)
            if url == f"{frontend_server}{PROJECT_PREFIX}/{data_path}":
                if pending:
                    held.append(route)
                elif failure == "network":
                    route.abort()
                elif failure in ("http", "missing"):
                    route.fulfill(status=503 if failure == "http" else 404, body="Unavailable")
                elif failure == "json":
                    route.fulfill(content_type="application/json", body="invalid json")
                else:
                    route.fulfill(json=default if payload is None else payload)
            elif url == f"{frontend_server}{PROJECT_PREFIX}/data/seasonal.json":
                route.fulfill(json=SEASONAL)
            elif url == f"{frontend_server}{PROJECT_PREFIX}/413/data.json":
                route.fulfill(json=DASHBOARD)
            elif url == f"{frontend_server}{PROJECT_PREFIX}/data/events.json":
                route.fulfill(json={"generated": "2026-08-14", "events": []})
            elif url.startswith(frontend_server):
                route.continue_()
            elif libraries == "throws" and url.endswith(".js"):
                route.fulfill(
                    content_type="application/javascript",
                    body=(
                        "window.L={map(){throw Error('map failure')}};"
                        "window.Chart=function(){throw Error('chart failure')};"
                    ),
                )
            elif libraries == "tiles" and "leaflet.min.js" in url:
                route.fulfill(
                    content_type="application/javascript",
                    body="""
                window.L = {
                  map: () => ({setView(){return this}, remove(){}}),
                  tileLayer: () => ({on(event, callback){this.callback=callback; return this},
                    addTo(){setTimeout(this.callback, 0); return this}}),
                  circleMarker: () => ({addTo(){return this}, bindTooltip(){}, on(){}})
                };
                """,
                )
            else:
                route.abort()

        page.route("**/*", respond)
        page.goto(f"{frontend_server}{PROJECT_PREFIX}/{path}", wait_until="domcontentloaded")
        return page, errors, requests, held

    yield open_page
    for context in contexts:
        context.close()


@pytest.mark.parametrize("kind", PAGES)
def test_secondary_loading_healthy_and_historical_evidence(secondary_page, kind):
    page, errors, requests, held = secondary_page(kind, pending=True)
    _, _, payload, status, _ = PAGES[kind]
    expect(page.locator(f"#{status}")).to_contain_text("Loading")
    assert held
    held[0].fulfill(json=payload)
    expect(page.locator(f"#{status}")).to_contain_text("Generated 2026-08-14")
    expect(page.locator(f"#{status}")).to_contain_text("historical evidence, not confirmation")
    expect(page.locator("main")).to_contain_text("2024-08-09 to 2025-08-08")
    expect(page.locator('a[href^="javascript:"], a[href^="data:"]')).to_have_count(0)
    if kind == "seasonal":
        expect(page.locator("#guide-container")).to_contain_text("covered 2 years (2024, 2025)")
        expect(page.locator("#guide-container")).not_to_contain_text("2026-08")
        expect(page.locator("#guide-container")).to_contain_text("Historical episodes")
    else:
        expect(page.locator("#rows tr")).to_have_count(2)
    assert errors == []
    assert all("example.test" not in url for url in requests)


@pytest.mark.parametrize("kind", PAGES)
@pytest.mark.parametrize("generated", ["2026-07-03", None, "bad-date", "2026-02-29", "2026-08-16"])
def test_secondary_metadata_warning_preserves_text(secondary_page, kind, generated):
    payload = deepcopy(PAGES[kind][2])
    payload["generated"] = generated
    page, errors, _, _ = secondary_page(kind, payload=payload)
    status = page.locator(f"#{PAGES[kind][3]}")
    expect(status).to_contain_text(
        "more than 14 days old" if generated == "2026-07-03" else "could not be verified"
    )
    expect(page.locator("main")).to_contain_text("Harvest Fair")
    if generated == "2026-07-03":
        expect(status).to_contain_text("Generated 2026-07-03")
    assert errors == []


@pytest.mark.parametrize("kind", PAGES)
@pytest.mark.parametrize("failure", ["http", "missing", "network", "json", "shape", "nested"])
def test_secondary_unavailable_and_retry(secondary_page, frontend_server, kind, failure):
    path, data_path, default, status_id, retry_id = PAGES[kind]
    payload = [] if failure == "shape" else deepcopy(default)
    if failure == "nested":
        if kind == "seasonal":
            payload["months"]["8"][0]["episodes"] = "not an array"
        else:
            payload["index"][0]["count"] = "not a number"
    page, errors, requests, _ = secondary_page(kind, payload=payload, failure=failure)
    expect(page.locator(f"#{status_id}")).to_contain_text("could not be loaded")
    expect(page.locator(f"#{retry_id}")).to_be_visible()
    expect(page.locator("#guide-empty" if kind == "seasonal" else "#data-empty")).to_be_hidden()
    page.route(
        f"{frontend_server}{PROJECT_PREFIX}/{data_path}", lambda route: route.fulfill(json=default)
    )
    page.locator(f"#{retry_id}").click()
    expect(page.locator(f"#{status_id}")).to_contain_text("Generated 2026-08-14")
    expect(page.locator(f"#{retry_id}")).to_be_hidden()
    expect(page.locator("main")).to_contain_text("Harvest Fair")
    assert errors == []
    assert all("example.test" not in url for url in requests)


@pytest.mark.parametrize("kind", PAGES)
def test_secondary_valid_empty_has_metadata_and_no_failure(secondary_page, kind):
    payload = deepcopy(PAGES[kind][2])
    if kind == "seasonal":
        payload["months"] = {}
    else:
        payload["index"] = []
        payload["towns"] = []
        payload["totals"] = dict.fromkeys(payload["totals"], 0)
        payload["kinds"] = {}
        payload["months"] = {}
        payload["timeline"] = {"quarters": [], "series": {}}
    page, errors, _, _ = secondary_page(kind, payload=payload)
    expect(page.locator("#guide-empty" if kind == "seasonal" else "#data-empty")).to_be_visible()
    expect(page.locator(f"#{PAGES[kind][3]}")).to_contain_text("Generated 2026-08-14")
    expect(page.locator(f"#{PAGES[kind][4]}")).to_be_hidden()
    expect(page.locator("main")).to_contain_text("no dated evidence available")
    assert errors == []


@pytest.mark.parametrize("libraries", ["blocked", "throws", "tiles"])
def test_dashboard_text_navigation_survives_dependency_failures(secondary_page, libraries):
    page, errors, _, _ = secondary_page("dashboard", libraries=libraries)
    expect(page.locator("#rows tr")).to_have_count(2)
    page.locator("#town-filter").select_option("Unmapped Town")
    expect(page.locator("#rows tr")).to_have_count(1)
    expect(page.locator("#rows")).to_contain_text("Town Green")
    page.locator("#town-clear").click()
    expect(page.locator("#rows tr")).to_have_count(2)
    page.locator("#q").fill("no match")
    expect(page.locator("#explorer-empty")).to_be_visible()
    expect(page.locator("#data-status")).to_contain_text("Generated 2026-08-14")
    expect(page.locator("#month-totals")).to_contain_text("Aug: 3 mentions")
    expect(page.locator("#quarter-totals")).to_contain_text("2025-Q3: 2 mentions")
    if libraries == "tiles":
        expect(page.locator("#map-status")).to_contain_text("Map tiles could not be loaded")
    assert errors == []


@pytest.mark.parametrize("kind", PAGES)
@pytest.mark.parametrize("width", [1280, 390])
def test_secondary_prefix_navigation_and_mobile_layout(
    secondary_page, frontend_server, kind, width
):
    page, errors, _, _ = secondary_page(kind, width=width)
    expect(page.locator(f"#{PAGES[kind][3]}")).to_contain_text("Generated")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.locator("header").evaluate("""header => {
      const bounds = header.getBoundingClientRect();
      return [...header.querySelectorAll('h1, nav a')].every(element => {
        const rect = element.getBoundingClientRect();
        return rect.top >= bounds.top && rect.bottom <= bounds.bottom;
      });
    }""")
    nav = page.locator('nav[aria-label="Site pages"]')
    if kind == "seasonal":
        nav.locator('a[href="413/"]').click()
        expect(page).to_have_url(f"{frontend_server}{PROJECT_PREFIX}/413/")
    else:
        nav.locator('a[href="../seasonal.html"]').click()
        expect(page).to_have_url(f"{frontend_server}{PROJECT_PREFIX}/seasonal.html")
    assert errors == []
