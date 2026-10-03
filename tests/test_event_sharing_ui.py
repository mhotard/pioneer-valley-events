from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from icalendar import Calendar
from playwright.sync_api import expect

from tests.conftest import FIXED_DATE_SCRIPT, PROJECT_PREFIX


def show_all(page):
    page.locator('[data-dates="all"]').click()


def goto_event(page, server, event_id, **filters):
    query = urlencode({**filters, "event": event_id})
    page.goto(f"{server}{PROJECT_PREFIX}/?{query}")


def test_exact_direct_link_preserves_filtered_view_and_reload(app_page, frontend_server):
    goto_event(
        app_page, frontend_server, "single", q="other-search", town="Springfield", view="cards"
    )
    expect(app_page.get_by_role("dialog", name="Solo Concert")).to_be_visible()
    expect(app_page.locator("#result-count")).to_have_text("0 events")
    expect(app_page.locator("#search")).to_have_value("other-search")
    expect(app_page.locator('.view-btn[data-view="cards"]')).to_have_attribute(
        "aria-pressed", "true"
    )
    app_page.reload()
    expect(app_page.get_by_role("dialog", name="Solo Concert")).to_be_visible()
    app_page.keyboard.press("Escape")
    expect(app_page.locator('.view-btn[data-view="cards"]')).to_be_focused()
    query = parse_qs(urlsplit(app_page.url).query)
    assert "event" not in query
    assert query["q"] == ["other-search"]
    assert query["town"] == ["Springfield"]
    assert query["view"] == ["cards"]


@pytest.mark.parametrize("event_id", ["gone", "", "single-other"])
def test_unavailable_id_never_substitutes_an_event(app_page, frontend_server, event_id):
    goto_event(app_page, frontend_server, event_id)
    expect(app_page.get_by_role("dialog", name="Event unavailable")).to_be_visible()
    expect(app_page.locator("#modal-content")).to_contain_text(
        "no longer in the current published listings"
    )
    expect(app_page.locator("#download-event")).to_have_count(0)
    expect(app_page.locator("#copy-event-link")).to_have_count(0)
    app_page.keyboard.press("Tab")
    expect(app_page.locator("#modal-close")).to_be_focused()
    app_page.keyboard.press("Escape")
    expect(app_page.locator('.view-btn[data-view="list"]')).to_be_focused()
    expect(app_page.locator("#result-count")).to_have_text("2 events")


def test_direct_event_on_failed_dataset_is_unverified_not_gone(chromium_browser, frontend_server):
    context = chromium_browser.new_context(timezone_id="America/New_York")
    page = context.new_page()
    page.add_init_script(FIXED_DATE_SCRIPT)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route(
        "**/*",
        lambda route: (
            route.fulfill(status=503, json={})
            if route.request.url.endswith("/data/events.json")
            else route.continue_()
            if route.request.url.startswith(frontend_server)
            else route.abort()
        ),
    )
    try:
        goto_event(page, frontend_server, "single")
        expect(page.get_by_role("dialog", name="Event unavailable")).to_be_visible()
        expect(page.locator("#modal-content")).to_contain_text("cannot be checked")
        expect(page.locator("#modal-content")).not_to_contain_text("no longer")
        expect(page.locator("#result-count")).to_have_text("Events unavailable")
        assert errors == []
    finally:
        context.close()


def test_browser_back_forward_and_close_return_focus_after_render(app_page):
    show_all(app_page)
    opener = app_page.locator('.list-item[data-id="single"]')
    opener.click()
    assert parse_qs(urlsplit(app_page.url).query)["event"] == ["single"]
    app_page.go_back()
    expect(app_page.locator("#modal-overlay")).to_have_class("modal-overlay hidden")
    expect(opener).to_be_focused()
    app_page.go_forward()
    expect(app_page.get_by_role("dialog", name="Solo Concert")).to_be_visible()
    app_page.keyboard.press("Escape")
    expect(opener).to_be_focused()
    app_page.go_back()
    expect(app_page.get_by_role("dialog", name="Solo Concert")).to_be_visible()


def test_copy_link_success_preserves_exact_id_and_view(app_page):
    show_all(app_page)
    app_page.locator('.view-btn[data-view="cards"]').click()
    app_page.locator('.card[data-id="single"]').click()
    app_page.evaluate("""() => {
      Object.defineProperty(navigator, 'clipboard', { configurable: true,
        value: { writeText: async value => { window.copiedEventLink = value; } } });
    }""")
    app_page.locator("#copy-event-link").click()
    expect(app_page.locator("#event-action-status")).to_have_text("Event link copied.")
    expect(app_page.locator("#copy-link-fallback")).to_be_hidden()
    copied = app_page.evaluate("window.copiedEventLink")
    parts = urlsplit(copied)
    assert parts.path == f"{PROJECT_PREFIX}/"
    assert parse_qs(parts.query) == {"dates": ["all"], "view": ["cards"], "event": ["single"]}


@pytest.mark.parametrize("clipboard", ["absent", "denied"])
def test_copy_fallback_selection_and_focus_trap(app_page, clipboard):
    show_all(app_page)
    opener = app_page.locator('.list-item[data-id="single"]')
    opener.click()
    app_page.evaluate(
        """kind => {
      Object.defineProperty(navigator, 'clipboard', { configurable: true,
        value: kind === 'absent' ? undefined : {
          writeText: async () => { throw new DOMException('Denied', 'NotAllowedError'); }
        } });
    }""",
        clipboard,
    )
    app_page.locator("#copy-event-link").click()
    field = app_page.get_by_label("Event link — select and copy")
    expect(field).to_be_visible()
    expect(field).to_be_focused()
    assert field.evaluate(
        "element => element.selectionStart === 0 && element.selectionEnd === element.value.length"
    )
    assert parse_qs(urlsplit(field.input_value()).query)["event"] == ["single"]
    app_page.keyboard.press("Tab")
    expect(app_page.locator("#modal-close")).to_be_focused()
    app_page.keyboard.press("Shift+Tab")
    expect(field).to_be_focused()
    app_page.keyboard.press("Escape")
    expect(opener).to_be_focused()


def test_ids_with_punctuation_unicode_and_quotes_share_exactly(
    app_page, frontend_server, sample_events
):
    event_id = 'a / ? & " 🎷'
    value = {**sample_events[0], "id": event_id}
    app_page.route(
        f"{frontend_server}{PROJECT_PREFIX}/data/events.json",
        lambda route: route.fulfill(json={"generated": "2026-08-14", "events": [value]}),
    )
    goto_event(app_page, frontend_server, event_id)
    expect(app_page.get_by_role("dialog", name="Solo Concert")).to_be_visible()
    assert parse_qs(urlsplit(app_page.locator("#event-link-input").input_value()).query)[
        "event"
    ] == [event_id]
    assert app_page.locator("[onfocus], [autofocus]").count() == 0


@pytest.mark.parametrize(("event_id", "all_day"), [("single", False), ("multi-untimed", True)])
def test_download_content_and_explanation(app_page, event_id, all_day, tmp_path):
    show_all(app_page)
    app_page.locator(f'.list-item[data-id="{event_id}"]').click()
    expect(app_page.locator(".calendar-note")).to_contain_text(
        "all-day date reminder" if all_day else "no duration is supplied"
    )
    with app_page.expect_download() as download:
        app_page.locator("#download-event").click()
    path = tmp_path / "event.ics"
    download.value.save_as(path)
    content = path.read_bytes()
    assert b"\n" not in content.replace(b"\r\n", b"")
    records = Calendar.from_ical(content).walk("VEVENT")
    assert len(records) == 1
    assert str(records[0]["SUMMARY"]) == ("All Day Art" if all_day else "Solo Concert")
    if all_day:
        assert records[0]["DTSTART"].params["VALUE"] == "DATE"
    else:
        assert records[0]["DTSTART"].params["TZID"] == "America/New_York"
        assert "DTEND" not in records[0]
    assert "Dataset updated: 2026-08-14" in str(records[0]["DESCRIPTION"])
    expect(app_page.locator("#event-action-status")).to_contain_text("Calendar file downloaded")
    expect(app_page.locator("#download-event")).to_be_focused()


def test_stale_warning_beside_saving_refreshes_with_open_tab(app_page):
    show_all(app_page)
    app_page.locator('.list-item[data-id="single"]').click()
    expect(app_page.locator("#modal-data-warning")).to_be_hidden()
    app_page.evaluate("""() => {
      const RealDate = Date;
      const now = new RealDate('2026-08-30T12:00:00-04:00').getTime();
      window.Date = class extends RealDate {
        constructor(...args) { super(...(args.length ? args : [now])); }
        static now() { return now; }
      };
      document.dispatchEvent(new Event('visibilitychange'));
    }""")
    expect(app_page.locator("#modal-data-warning")).to_be_visible()
    expect(app_page.locator("#modal-data-warning")).to_contain_text("Last updated Aug 14, 2026")
    expect(app_page.locator("#download-event")).to_be_visible()


@pytest.mark.parametrize(
    "kind", ["null", "empty", "blank-id", "blank-title", "bad-date", "date-type", "duplicate"]
)
def test_malformed_published_records_show_unavailable_state(
    app_page, frontend_server, sample_events, kind
):
    value = sample_events[0]
    rows = {
        "null": [None],
        "empty": [{}],
        "blank-id": [{**value, "id": " "}],
        "blank-title": [{**value, "title": " "}],
        "bad-date": [{**value, "date": "2026-02-30"}],
        "date-type": [{**value, "date": None}],
        "duplicate": [value, value],
    }[kind]
    app_page.route(
        f"{frontend_server}{PROJECT_PREFIX}/data/events.json",
        lambda route: route.fulfill(json={"generated": "2026-08-14", "events": rows}),
    )
    app_page.reload()
    expect(app_page.locator("#result-count")).to_have_text("Events unavailable")
    expect(app_page.locator("#data-warning")).to_contain_text("could not be loaded")
    expect(app_page.locator(".empty-state")).to_contain_text("could not be loaded")


def test_optional_fields_missing_still_share_and_download(app_page, frontend_server, tmp_path):
    value = {"id": "minimal", "title": "Minimal event", "date": "2026-08-20"}
    app_page.route(
        f"{frontend_server}{PROJECT_PREFIX}/data/events.json",
        lambda route: route.fulfill(json={"generated": "2026-08-14", "events": [value]}),
    )
    goto_event(app_page, frontend_server, "minimal")
    expect(app_page.get_by_role("dialog", name="Minimal event")).to_be_visible()
    expect(app_page.locator("#result-count")).to_have_text("1 event")
    expect(app_page.locator(".calendar-note")).to_contain_text("all-day date reminder")
    with app_page.expect_download() as download:
        app_page.locator("#download-event").click()
    path = tmp_path / "minimal.ics"
    download.value.save_as(path)
    assert (
        str(Calendar.from_ical(path.read_bytes()).walk("VEVENT")[0]["SUMMARY"]) == "Minimal event"
    )


def test_mobile_share_save_stale_and_fallback_screenshots(
    app_page, frontend_server, sample_events, tmp_path
):
    app_page.emulate_media(reduced_motion="reduce")
    app_page.route(
        f"{frontend_server}{PROJECT_PREFIX}/data/events.json",
        lambda route: route.fulfill(json={"generated": "2026-07-03", "events": sample_events}),
    )
    goto_event(app_page, frontend_server, "single", dates="all", view="cards")
    expect(app_page.locator("#modal-data-warning")).to_be_visible()
    app_page.screenshot(path=tmp_path / "share-save-desktop.png")
    app_page.set_viewport_size({"width": 390, "height": 844})
    app_page.screenshot(path=tmp_path / "share-save-mobile.png")
    assert app_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    app_page.evaluate(
        "Object.defineProperty(navigator, 'clipboard', { configurable:true, value:undefined })"
    )
    app_page.locator("#copy-event-link").click()
    expect(app_page.locator("#event-link-input")).to_be_focused()
    assert app_page.locator("#event-link-input").evaluate(
        """input => {
          const field = input.getBoundingClientRect();
          const modal = input.closest('.modal').getBoundingClientRect();
          return field.top >= modal.top && field.bottom <= modal.bottom;
        }"""
    )
    app_page.screenshot(path=tmp_path / "share-fallback-mobile.png")
    assert all(path.stat().st_size > 1000 for path in Path(tmp_path).glob("*.png"))


@pytest.mark.parametrize("generated", [None, "bad-date", "2026-02-29", "2026-08-16"])
def test_unverified_update_warning_remains_beside_download(
    app_page, frontend_server, sample_events, generated, tmp_path
):
    app_page.route(
        f"{frontend_server}{PROJECT_PREFIX}/data/events.json",
        lambda route: route.fulfill(json={"generated": generated, "events": sample_events}),
    )
    goto_event(app_page, frontend_server, "single")
    expect(app_page.locator("#modal-data-warning")).to_be_visible()
    expect(app_page.locator("#modal-data-warning")).to_contain_text("could not be verified")
    with app_page.expect_download() as download:
        app_page.locator("#download-event").click()
    path = tmp_path / "unverified.ics"
    download.value.save_as(path)
    description = str(Calendar.from_ical(path.read_bytes()).walk("VEVENT")[0]["DESCRIPTION"])
    assert "unverified" in description
    if generated == "2026-08-16":
        assert "2026-08-16" in description
    assert "Dataset updated:" not in description
    expect(app_page.locator("#modal-data-warning")).to_be_visible()
