from datetime import date, timedelta

import pytest
from icalendar import Calendar

from tests.conftest import PROJECT_PREFIX


@pytest.fixture
def calendar_page(chromium_browser, frontend_server):
    context = chromium_browser.new_context(timezone_id="Asia/Tokyo")
    page = context.new_page()
    page.route(
        "**/*",
        lambda route: (
            route.continue_() if route.request.url.startswith(frontend_server) else route.abort()
        ),
    )
    page.goto(f"{frontend_server}/module-test.html")
    try:
        yield page
    finally:
        context.close()


def module_call(page, server, function, *args):
    return page.evaluate(
        """async ({ url, name, args }) => (await import(url))[name](...args)""",
        {"url": f"{server}{PROJECT_PREFIX}/calendar-export.js", "name": function, "args": args},
    )


def event(**overrides):
    result = {
        "id": "fixture-1",
        "title": "Jazz Night",
        "date": "2026-08-20",
        "time": "7:00 PM",
        "end_time": "9:00 PM",
        "venue": "Town Hall",
        "town": "Amherst",
        "address": "1 Main St",
        "description": "Published description",
        "url": "https://example.test/event",
    }
    result.update(overrides)
    return result


def exported(page, server, value=None, generated="2026-08-14"):
    content = module_call(
        page, server, "createCalendar", value or event(), generated, "2026-08-15T16:00:00Z"
    )
    calendar = Calendar.from_ical(content)
    events = calendar.walk("VEVENT")
    assert len(events) == 1
    assert not events[0].errors
    return content, calendar, events[0]


def test_timed_event_preserves_supplied_details_and_offsets(calendar_page, frontend_server):
    content, calendar, record = exported(calendar_page, frontend_server)
    assert str(record["SUMMARY"]) == "Jazz Night"
    assert str(record["LOCATION"]) == "Town Hall, Amherst, 1 Main St"
    assert str(record["URL"]) == "https://example.test/event"
    description = str(record["DESCRIPTION"])
    assert "Event: Jazz Night" in description
    assert "Organizer: https://example.test/event" in description
    assert "Dataset updated: 2026-08-14." in description
    assert record.decoded("DTSTAMP").isoformat() == "2026-08-15T16:00:00+00:00"
    assert record["DTSTART"].params["TZID"] == "America/New_York"
    assert record.decoded("DTSTART").isoformat() == "2026-08-20T19:00:00-04:00"
    assert record.decoded("DTEND").isoformat() == "2026-08-20T21:00:00-04:00"
    zones = calendar.walk("VTIMEZONE")
    assert len(zones) == 1
    assert str(zones[0]["TZID"]) == "America/New_York"
    assert "TZOFFSETFROM:-0500\r\nTZOFFSETTO:-0400" in content
    assert "TZOFFSETFROM:-0400\r\nTZOFFSETTO:-0500" in content
    explicit_zone = zones[0].to_tz(lookup_tzid=False)
    assert record.decoded("DTSTART").replace(tzinfo=explicit_zone).utcoffset() == timedelta(
        hours=-4
    )


@pytest.mark.parametrize(
    ("day", "time", "offset"),
    [
        ("2026-03-07", "3:30 AM", -5),
        ("2026-03-08", "3:30 AM", -4),
        ("2026-10-31", "3:30 AM", -4),
        ("2026-11-01", "3:30 AM", -5),
        ("2026-11-01", "1:30 AM", -4),  # RFC's first occurrence for repeated local time.
        ("2006-03-12", "3:30 AM", -5),  # Historical DST rules come from Intl, not current RRULE.
    ],
)
def test_dst_and_historical_timezone_definition(calendar_page, frontend_server, day, time, offset):
    _, calendar, record = exported(
        calendar_page, frontend_server, event(date=day, time=time, end_time="")
    )
    start = record.decoded("DTSTART")
    assert start.utcoffset() == timedelta(hours=offset)
    local_zone = calendar.walk("VTIMEZONE")[0].to_tz(lookup_tzid=False)
    assert start.replace(tzinfo=local_zone).utcoffset() == timedelta(hours=offset)


@pytest.mark.parametrize("time", [None, "", "TBD", "13 PM", "0:30 AM", "9:60 AM", 9])
def test_unknown_or_invalid_start_is_explained_all_day(calendar_page, frontend_server, time):
    _, calendar, record = exported(
        calendar_page, frontend_server, event(date="2026-12-31", time=time, end_time="9:00 PM")
    )
    assert record.decoded("DTSTART") == date(2026, 12, 31)
    assert record.decoded("DTEND") == date(2027, 1, 1)
    assert record["DTSTART"].params["VALUE"] == "DATE"
    assert not calendar.walk("VTIMEZONE")
    assert "all-day date reminder" in str(record["DESCRIPTION"])
    assert "does not mean the event lasts all day" in str(record["DESCRIPTION"])


@pytest.mark.parametrize("end_time", [None, "", "TBD", "13 PM", "7:00 PM", "6:00 PM", "1:00 AM"])
def test_missing_invalid_equal_or_overnight_end_does_not_invent_duration(
    calendar_page, frontend_server, end_time
):
    _, _, record = exported(calendar_page, frontend_server, event(end_time=end_time))
    assert "DTEND" not in record
    assert "DURATION" not in record
    assert "no duration is supplied" in str(record["DESCRIPTION"])


@pytest.mark.parametrize(
    ("time", "minutes"), [("12:00 AM", 0), ("12 PM", 720), ("07:30 PM", 1170), (" 9:05 pm ", 1265)]
)
def test_strict_valid_times(calendar_page, frontend_server, time, minutes):
    assert module_call(calendar_page, frontend_server, "calendarMinutes", time) == minutes


def test_unicode_escaping_folding_and_injection_are_roundtrippable(calendar_page, frontend_server):
    title = "Café 🎷: música, art; a \\ path\n" + "🎶漢é" * 60
    description = "Line one\r\nBEGIN:VEVENT\r\nSUMMARY:Injected\r\nEND:VEVENT"
    value = event(
        id="odd\r\nEND:VEVENT;🎷", title=title, description=description, venue="Hall, room; B\\C"
    )
    content, _, record = exported(calendar_page, frontend_server, value)
    assert str(record["SUMMARY"]) == title
    assert description.replace("\r\n", "\n") in str(record["DESCRIPTION"])
    assert str(record["LOCATION"]) == "Hall, room; B\\C, Amherst, 1 Main St"
    assert content.count("BEGIN:VEVENT\r\n") == 1
    assert "\r\n " in content
    assert "\n" not in content.replace("\r\n", "")
    assert all(len(line.encode("utf-8")) <= 75 for line in content.split("\r\n"))
    uid = str(record["UID"])
    _, _, updated = exported(calendar_page, frontend_server, {**value, "title": "Updated details"})
    assert str(updated["UID"]) == uid
    _, _, another = exported(calendar_page, frontend_server, {**value, "id": value["id"] + "x"})
    assert str(another["UID"]) != uid


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,bad",
        "https://@example.test",
        "https://example.test/\nBEGIN:VEVENT",
        "https://example.test\\bad",
    ],
)
def test_unsafe_organizer_urls_never_enter_calendar(calendar_page, frontend_server, url):
    _, _, record = exported(calendar_page, frontend_server, event(url=url))
    assert "URL" not in record
    assert "Organizer:" not in str(record["DESCRIPTION"])


@pytest.mark.parametrize("generated", [None, "", "2026-02-30", "not-a-date"])
def test_missing_update_date_is_not_backfilled(calendar_page, frontend_server, generated):
    _, _, record = exported(calendar_page, frontend_server, generated=generated)
    assert "Dataset update date unverified." in str(record["DESCRIPTION"])
    assert "Dataset updated:" not in str(record["DESCRIPTION"])


@pytest.mark.parametrize("day", ["2026-02-29", "2026-04-31", "bad", None])
def test_impossible_dates_cannot_export(calendar_page, frontend_server, day):
    result = calendar_page.evaluate(
        """async ({url, event}) => {
          try { (await import(url)).createCalendar(event, '2026-08-14'); return 'unexpected'; }
          catch { return 'rejected'; }
        }""",
        {"url": f"{frontend_server}{PROJECT_PREFIX}/calendar-export.js", "event": event(date=day)},
    )
    assert result == "rejected"


def test_all_day_leap_day_end_is_exclusive(calendar_page, frontend_server):
    _, _, record = exported(calendar_page, frontend_server, event(date="2024-02-29", time=""))
    assert record.decoded("DTSTART") == date(2024, 2, 29)
    assert record.decoded("DTEND") == date(2024, 3, 1)


def test_future_update_date_retains_supplied_value_as_unverified(calendar_page, frontend_server):
    _, _, record = exported(calendar_page, frontend_server, generated="2026-08-16")
    description = str(record["DESCRIPTION"])
    assert "Dataset supplied update date: 2026-08-16 (unverified; in the future)." in description
    assert "Dataset updated:" not in description
