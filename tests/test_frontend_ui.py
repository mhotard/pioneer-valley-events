from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.conftest import FIXED_DATE_SCRIPT, PROJECT_PREFIX


def modal_title(page):
    return page.locator("#modal-content .modal-title")


def all_published_dates(page):
    page.locator('[data-dates="all"]').click()


def switch_view(page, view):
    page.locator(f'.view-btn[data-view="{view}"]').click()


def test_boot_count_dropdowns_and_generated_label(app_page):
    expect(app_page.locator("#result-count")).to_have_text("2 events")
    expect(app_page.locator("#date-from")).to_have_value("2026-08-15")
    all_published_dates(app_page)
    expect(app_page.locator("#result-count")).to_have_text("8 events")
    expect(app_page.locator(".list-item")).to_have_count(8)
    expect(app_page.locator("#last-updated")).to_have_text("Updated Aug 14, 2026")
    expect(app_page.locator("#data-warning")).to_be_hidden()
    expect(app_page.locator("#source-filter option")).to_have_count(3)
    expect(app_page.locator("#town-filter option")).to_have_count(4)
    expect(app_page.locator('#town-filter option[value="Pioneer Valley"]')).to_have_text(
        "Regionwide"
    )


def test_stale_warning_survives_filters_and_views(app_page, frontend_server, sample_events):
    all_published_dates(app_page)
    app_page.route(
        f"{frontend_server}{PROJECT_PREFIX}/data/events.json",
        lambda route: route.fulfill(json={"generated": "2026-07-03", "events": sample_events}),
    )
    app_page.reload()
    expect(app_page.locator("#data-warning")).to_be_visible()
    expect(app_page.locator("#data-warning")).to_contain_text("Last updated Jul 3, 2026")
    expect(app_page.locator("#last-updated")).to_have_text("Out of date · updated Jul 3, 2026")
    app_page.locator("#search").fill("does-not-exist")
    for view in ("cards", "calendar", "list"):
        switch_view(app_page, view)
        expect(app_page.locator("#data-warning")).to_be_visible()
    app_page.locator("#clear-filters").click()
    expect(app_page.locator("#result-count")).to_have_text("2 events")
    expect(app_page.locator("#data-warning")).to_be_visible()


@pytest.mark.parametrize("generated", [None, "bad-date", "2026-02-29", "2026-08-16"])
def test_unverifiable_date_warns_without_hiding_events(
    app_page, frontend_server, sample_events, generated
):
    all_published_dates(app_page)
    app_page.route(
        f"{frontend_server}{PROJECT_PREFIX}/data/events.json",
        lambda route: route.fulfill(json={"generated": generated, "events": sample_events}),
    )
    app_page.reload()
    expect(app_page.locator("#data-warning")).to_be_visible()
    expect(app_page.locator("#data-warning")).to_contain_text("could not be verified")
    expect(app_page.locator("#last-updated")).to_have_text("Update date unverified")
    expect(app_page.locator("#result-count")).to_have_text("8 events")


@pytest.mark.parametrize("failure", ["http", "json", "shape", "network"])
def test_failed_load_is_not_an_ordinary_empty_result(chromium_browser, frontend_server, failure):
    context = chromium_browser.new_context(timezone_id="America/New_York")
    page = context.new_page()
    page.add_init_script(FIXED_DATE_SCRIPT)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def respond(route):
        if failure == "network":
            route.abort()
        elif failure == "shape":
            route.fulfill(json={"generated": "2026-08-14", "events": {}})
        else:
            route.fulfill(
                status=503 if failure == "http" else 200,
                content_type="application/json",
                body="not json",
            )

    page.route(f"{frontend_server}{PROJECT_PREFIX}/data/events.json", respond)
    try:
        page.goto(f"{frontend_server}{PROJECT_PREFIX}/")
        expect(page.locator("#data-warning")).to_be_visible()
        expect(page.locator("#data-warning")).to_contain_text("could not be loaded")
        expect(page.locator("#result-count")).to_have_text("Events unavailable")
        for view in ("list", "cards", "calendar"):
            switch_view(page, view)
            expect(page.locator(".empty-state")).to_contain_text("could not be loaded")
        assert errors == []
    finally:
        context.close()


def test_open_tab_rechecks_freshness_when_revisited(app_page):
    app_page.evaluate(
        """() => {
          const RealDate = Date;
          const fixed = new RealDate('2026-08-30T12:00:00-04:00').getTime();
          window.Date = class extends RealDate {
            constructor(...args) { super(...(args.length ? args : [fixed])); }
            static now() { return fixed; }
          };
          document.dispatchEvent(new Event('visibilitychange'));
        }"""
    )
    expect(app_page.locator("#data-warning")).to_be_visible()
    expect(app_page.locator("#last-updated")).to_have_text("Out of date · updated Aug 14, 2026")


def test_combined_filters_views_and_clear(app_page):
    all_published_dates(app_page)
    app_page.locator("#search").fill("solo")
    app_page.locator("#date-from").fill("2026-08-05")
    app_page.locator("#date-to").fill("2026-08-05")
    app_page.locator("#category-filter").select_option("music")
    app_page.locator("#town-filter").select_option("Amherst")
    app_page.locator("#source-filter").select_option("alpha")
    expect(app_page.locator("#result-count")).to_have_text("1 event")
    expect(app_page.locator(".list-item-title")).to_have_text("Solo Concert")

    switch_view(app_page, "cards")
    expect(app_page.locator(".card-title")).to_have_text("Solo Concert")
    switch_view(app_page, "calendar")
    expect(app_page.locator(".cal-pill")).to_have_count(1)
    expect(app_page.locator("#result-count")).to_have_text("1 event")

    app_page.locator("#clear-filters").click()
    expect(app_page.locator("#result-count")).to_have_text("2 events")
    expect(app_page.locator(".cal-pill")).to_have_count(1)


def test_calendar_geometry_today_pills_and_day_toggle(app_page):
    all_published_dates(app_page)
    switch_view(app_page, "calendar")
    expect(app_page.locator(".cal-month-label")).to_have_text("August 2026")
    expect(app_page.locator('.cal-day[data-date="2026-08-15"]')).to_have_class("cal-day today")
    expect(app_page.locator(".cal-days > .cal-day")).to_have_count(42)

    multi = app_page.locator('.cal-day[data-date="2026-08-10"]')
    expect(multi.locator(".cal-pill")).to_have_count(3)
    expect(multi.locator(".cal-more")).to_have_text("+2 more")
    multi.locator(".cal-more").click()
    expect(app_page.locator(".cal-day-detail .list-item-title")).to_have_text(
        ["All Day Art", "Morning Jazz", "Morning Jazz Springfield", "Noon Lecture", "Evening Film"]
    )
    app_page.locator('.cal-day[data-date="2026-08-10"] .cal-day-num').click()
    expect(app_page.locator(".cal-day-detail")).to_have_count(0)

    app_page.locator('.cal-day[data-date="2026-08-11"] .cal-day-num').click()
    app_page.locator(".cal-day.other-month").first.click()
    expect(app_page.locator(".cal-day-detail")).to_have_count(0)
    expect(app_page.locator("#modal-overlay")).to_have_class("modal-overlay hidden")


def test_calendar_event_activation_and_duplicate_regression(app_page):
    all_published_dates(app_page)
    switch_view(app_page, "calendar")
    app_page.evaluate(
        """() => {
          window.modalReplacements = 0;
          window.modalObserver = new MutationObserver(records => {
            window.modalReplacements += records
              .filter(record => record.type === 'childList').length;
          });
          window.modalObserver.observe(
            document.querySelector('#modal-content'), { childList: true }
          );
        }"""
    )
    app_page.locator('.cal-pill[data-id="multi-morning"]').click()
    expect(modal_title(app_page)).to_have_text("Morning Jazz")
    app_page.wait_for_function("window.modalReplacements > 0")
    assert app_page.evaluate("window.modalReplacements") == 1
    app_page.locator("#modal-close").click()

    app_page.locator('.cal-day[data-date="2026-08-05"] .cal-day-num').click()
    expect(modal_title(app_page)).to_have_text("Solo Concert")
    app_page.locator("#modal-close").click()

    app_page.locator('.cal-day[data-date="2026-08-10"] .cal-more').click()
    app_page.locator('.cal-day-detail .list-item[data-id="multi-evening"] .list-item-title').click()
    expect(modal_title(app_page)).to_have_text("Evening Film")


def test_selected_day_refreshes_with_filters_without_stale_events(app_page):
    all_published_dates(app_page)
    switch_view(app_page, "calendar")
    app_page.locator('.cal-day[data-date="2026-08-10"] .cal-more').click()
    expect(app_page.locator(".cal-day-detail .list-item")).to_have_count(5)

    app_page.locator("#category-filter").select_option("arts")
    expect(app_page.locator(".cal-day-detail .list-item")).to_have_count(1)
    expect(app_page.locator(".cal-day-detail .list-item-title")).to_have_text("All Day Art")
    assert app_page.locator('.cal-day-detail [data-id="multi-evening"]').count() == 0

    app_page.locator("#category-filter").select_option("food")
    expect(app_page.locator(".cal-day-detail")).to_have_count(0)


def test_navigation_across_year_today_and_view_reset_selection(app_page):
    all_published_dates(app_page)
    switch_view(app_page, "calendar")
    app_page.locator('.cal-day[data-date="2026-08-10"] .cal-more').click()
    expect(app_page.locator(".cal-day-detail")).to_have_count(1)

    for _ in range(5):
        app_page.locator("#cal-next").click()
    expect(app_page.locator(".cal-month-label")).to_have_text("January 2027")
    expect(app_page.locator(".cal-day-detail")).to_have_count(0)
    app_page.locator("#cal-prev").click()
    expect(app_page.locator(".cal-month-label")).to_have_text("December 2026")
    app_page.locator("#cal-next").click()
    expect(app_page.locator(".cal-month-label")).to_have_text("January 2027")
    app_page.locator("#cal-today").click()
    expect(app_page.locator(".cal-month-label")).to_have_text("August 2026")

    app_page.locator('.cal-day[data-date="2026-08-10"] .cal-more').click()
    switch_view(app_page, "list")
    switch_view(app_page, "calendar")
    expect(app_page.locator(".cal-day-detail")).to_have_count(0)


def test_keyboard_activation_and_modal_close_paths(app_page):
    all_published_dates(app_page)
    first = app_page.locator('.list-item[data-id="single"]')
    first.focus()
    app_page.keyboard.press("Enter")
    expect(modal_title(app_page)).to_have_text("Solo Concert")
    expect(app_page.locator("#modal-close")).to_be_focused()
    app_page.locator("#modal-content").click()
    expect(app_page.locator("#modal-overlay")).not_to_have_class("modal-overlay hidden")
    app_page.keyboard.press("Escape")
    expect(app_page.locator("#modal-overlay")).to_have_class("modal-overlay hidden")

    first.focus()
    app_page.keyboard.press("Space")
    expect(modal_title(app_page)).to_have_text("Solo Concert")
    app_page.locator("#modal-overlay").click(position={"x": 2, "y": 2})
    expect(app_page.locator("#modal-overlay")).to_have_class("modal-overlay hidden")

    switch_view(app_page, "cards")
    card = app_page.locator('.card[data-id="single"]')
    card.focus()
    app_page.keyboard.press("Enter")
    expect(modal_title(app_page)).to_have_text("Solo Concert")
    app_page.locator("#modal-close").click()


def test_repeated_renders_still_open_once(app_page):
    all_published_dates(app_page)
    for _ in range(3):
        app_page.locator("#search").fill("jazz")
        app_page.locator("#search").fill("")
        switch_view(app_page, "calendar")
        app_page.locator("#cal-next").click()
        app_page.locator("#cal-prev").click()
        switch_view(app_page, "cards")
        switch_view(app_page, "list")

    app_page.evaluate(
        """() => {
          window.modalReplacements = 0;
          new MutationObserver(records => {
            window.modalReplacements += records
              .filter(record => record.type === 'childList').length;
          }).observe(document.querySelector('#modal-content'), { childList: true });
        }"""
    )
    app_page.locator('.list-item[data-id="single"] .list-item-title').click()
    app_page.wait_for_function("window.modalReplacements > 0")
    assert app_page.evaluate("window.modalReplacements") == 1


def test_no_results_per_view(app_page):
    app_page.locator("#search").fill("does-not-exist")
    expect(app_page.locator(".empty-state")).to_have_count(1)
    switch_view(app_page, "cards")
    expect(app_page.locator(".empty-state")).to_have_count(1)
    switch_view(app_page, "calendar")
    expect(app_page.locator(".cal-days > .cal-day")).to_have_count(42)
    expect(app_page.locator(".empty-state")).to_have_count(1)
    expect(app_page.locator("#result-count")).to_have_text("0 events")


def test_representative_screenshots(app_page, tmp_path):
    all_published_dates(app_page)
    output = Path(tmp_path)
    switch_view(app_page, "cards")
    app_page.screenshot(path=output / "cards-desktop.png", full_page=True)
    switch_view(app_page, "calendar")
    app_page.locator('.cal-day[data-date="2026-08-10"] .cal-more').click()
    app_page.screenshot(path=output / "calendar-detail-desktop.png", full_page=True)
    app_page.locator('.cal-day-detail .list-item[data-id="multi-evening"]').click()
    app_page.screenshot(path=output / "modal-desktop.png", full_page=True)
    app_page.locator("#modal-close").click()
    app_page.set_viewport_size({"width": 390, "height": 844})
    app_page.evaluate(
        """() => {
          document.documentElement.style.scrollBehavior = 'auto';
          window.scrollTo(0, 0);
        }"""
    )
    app_page.wait_for_function("window.scrollY === 0")
    app_page.screenshot(path=output / "calendar-detail-narrow.png")
    assert all(path.stat().st_size > 1_000 for path in output.glob("*.png"))


@pytest.mark.parametrize("timezone", ["America/New_York", "UTC", "Asia/Tokyo", "Pacific/Honolulu"])
def test_upcoming_and_calendar_use_regional_date(
    chromium_browser, frontend_server, sample_events, timezone
):
    context = chromium_browser.new_context(timezone_id=timezone)
    page = context.new_page()
    page.add_init_script(
        FIXED_DATE_SCRIPT.replace("2026-08-15T12:00:00-04:00", "2026-08-16T02:30:00Z")
    )
    page.route(
        "**/*",
        lambda route: (
            route.fulfill(json={"generated": "2026-08-14", "events": sample_events})
            if route.request.url.endswith("/data/events.json")
            else route.continue_()
            if route.request.url.startswith(frontend_server)
            else route.abort()
        ),
    )
    try:
        page.goto(f"{frontend_server}{PROJECT_PREFIX}/?view=calendar")
        expect(page.locator("#date-from")).to_have_value("2026-08-15")
        expect(page.locator("#result-count")).to_have_text("2 events")
        expect(page.locator('.cal-day[data-date="2026-08-15"]')).to_have_class("cal-day today")
        expect(page.locator(".cal-pill")).to_have_count(1)
    finally:
        context.close()


def test_quick_dates_calendar_bounds_and_clear(app_page, frontend_server, sample_events):
    events = [
        {**sample_events[0], "id": str(i), "date": day}
        for i, day in enumerate(
            ["2026-08-14", "2026-08-15", "2026-08-16", "2026-08-21", "2026-08-22"]
        )
    ]
    app_page.route(
        f"{frontend_server}{PROJECT_PREFIX}/data/events.json",
        lambda route: route.fulfill(json={"generated": "2026-08-14", "events": events}),
    )
    app_page.reload()
    expect(app_page.locator("#result-count")).to_have_text("4 events")
    for choice, start, end, count in [
        ("today", "2026-08-15", "2026-08-15", 1),
        ("week", "2026-08-15", "2026-08-21", 3),
        ("weekend", "2026-08-15", "2026-08-16", 2),
        ("all", "", "", 5),
    ]:
        app_page.locator(f'[data-dates="{choice}"]').click()
        expect(app_page.locator("#date-from")).to_have_value(start)
        expect(app_page.locator("#date-to")).to_have_value(end)
        switch_view(app_page, "calendar")
        expect(app_page.locator(".cal-pill")).to_have_count(count)
    app_page.locator("#clear-filters").click()
    expect(app_page.locator("#date-from")).to_have_value("2026-08-15")
    expect(app_page.locator("#date-to")).to_have_value("")
    expect(app_page.locator(".cal-pill")).to_have_count(4)


def test_url_reload_back_forward_and_typing_history(app_page):
    all_published_dates(app_page)
    app_page.locator("#category-filter").select_option("music")
    switch_view(app_page, "cards")
    history_length = app_page.evaluate("history.length")
    app_page.locator("#search").press_sequentially("Morning Jazz")
    expect(app_page.locator("#search")).to_have_value("Morning Jazz")
    expect(app_page.locator(".card")).to_have_count(2)
    assert app_page.evaluate("history.length") == history_length
    saved_url = app_page.url
    app_page.reload()
    expect(app_page.locator("#search")).to_have_value("Morning Jazz")
    expect(app_page.locator('.view-btn[data-view="cards"]')).to_have_class("view-btn active")
    expect(app_page.locator(".card")).to_have_count(2)
    assert app_page.url == saved_url
    app_page.go_back()
    expect(app_page.locator("#search")).to_have_value("")
    expect(app_page.locator("#category-filter")).to_have_value("music")
    expect(app_page.locator('.view-btn[data-view="list"]')).to_have_class("view-btn active")
    app_page.go_forward()
    expect(app_page.locator("#search")).to_have_value("Morning Jazz")
    expect(app_page.locator(".card")).to_have_count(2)


def test_combined_shared_url_unknown_values_and_calendar_navigation(app_page, frontend_server):
    app_page.goto(
        f"{frontend_server}{PROJECT_PREFIX}/?dates=custom&from=2026-08-10&to=2026-08-10&q=Morning+Jazz&category=music&town=Amherst&source=alpha&view=calendar&month=2026-08"
    )
    expect(app_page.locator("#result-count")).to_have_text("1 event")
    expect(app_page.locator(".cal-pill")).to_have_text("Morning Jazz")
    app_page.locator("#cal-next").click()
    app_page.reload()
    expect(app_page.locator(".cal-month-label")).to_have_text("September 2026")
    app_page.go_back()
    expect(app_page.locator(".cal-month-label")).to_have_text("August 2026")
    app_page.goto(
        f"{frontend_server}{PROJECT_PREFIX}/?dates=bad&view=bad&town=bad&category=bad&source=bad&from=bad&unknown=x"
    )
    expect(app_page.locator("#result-count")).to_have_text("2 events")
    expect(app_page.locator("#town-filter")).to_have_value("")
    expect(app_page.locator('.view-btn[data-view="list"]')).to_have_class("view-btn active")


def test_empty_reset_retains_stale_warning_and_published_browsing(
    app_page, frontend_server, sample_events
):
    app_page.route(
        f"{frontend_server}{PROJECT_PREFIX}/data/events.json",
        lambda route: route.fulfill(json={"generated": "2026-07-03", "events": sample_events}),
    )
    app_page.reload()
    app_page.locator("#search").fill("missing")
    switch_view(app_page, "calendar")
    expect(app_page.locator(".empty-state")).to_contain_text("No events match")
    app_page.locator("#reset-results").click()
    expect(app_page.locator("#result-count")).to_have_text("2 events")
    expect(app_page.locator("#data-warning")).to_be_visible()
    app_page.locator('[data-dates="today"]').click()
    app_page.locator("#show-all-dates").click()
    expect(app_page.locator("#result-count")).to_have_text("8 events")
    expect(app_page.locator("#data-warning")).to_be_visible()


def test_discovery_mobile_controls_and_only_published_requests(app_page, tmp_path):
    requests = []
    app_page.on("request", lambda request: requests.append(request.url))
    app_page.set_viewport_size({"width": 390, "height": 844})
    for choice in ("today", "week", "weekend", "all"):
        app_page.locator(f'[data-dates="{choice}"]').click()
    app_page.locator("#search").fill("springfield")
    expect(app_page.locator("#result-count")).to_have_text("1 event")
    app_page.screenshot(path=tmp_path / "discovery-mobile.png", full_page=True)
    assert app_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert requests == []



def test_calendar_selected_day_url_restores_panel(app_page):
    all_published_dates(app_page)
    switch_view(app_page, "calendar")
    app_page.locator('.cal-day[data-date="2026-08-10"] .cal-more').click()
    expect(app_page.locator(".cal-day-detail .list-item")).to_have_count(5)
    assert "day=2026-08-10" in app_page.url
    app_page.reload()
    expect(app_page.locator(".cal-day-detail .list-item")).to_have_count(5)
    app_page.go_back()
    expect(app_page.locator(".cal-day-detail")).to_have_count(0)
