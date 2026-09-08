from pathlib import Path

from playwright.sync_api import expect


def modal_title(page):
    return page.locator("#modal-content .modal-title")


def switch_view(page, view):
    page.locator(f'.view-btn[data-view="{view}"]').click()


def test_boot_count_dropdowns_and_generated_label(app_page):
    expect(app_page.locator("#result-count")).to_have_text("8 events")
    expect(app_page.locator(".list-item")).to_have_count(8)
    expect(app_page.locator("#last-updated")).to_have_text("Updated Aug 14, 2026")
    expect(app_page.locator("#source-filter option")).to_have_count(3)
    expect(app_page.locator("#town-filter option")).to_have_count(4)
    expect(app_page.locator('#town-filter option[value="Pioneer Valley"]')).to_have_text(
        "Regionwide"
    )


def test_combined_filters_views_and_clear(app_page):
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
    expect(app_page.locator("#result-count")).to_have_text("8 events")
    expect(app_page.locator(".cal-pill")).to_have_count(5)


def test_calendar_geometry_today_pills_and_day_toggle(app_page):
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
    expect(app_page.locator(".empty-state")).to_have_count(0)
    expect(app_page.locator("#result-count")).to_have_text("0 events")


def test_representative_screenshots(app_page, tmp_path):
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
