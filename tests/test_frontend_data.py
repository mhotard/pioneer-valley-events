import copy

import pytest


def call_module(page, server, function, *args):
    return page.evaluate(
        """async ({ url, functionName, args }) => {
          const module = await import(url);
          return module[functionName](...args);
        }""",
        {
            "url": f"{server}/event-data.js",
            "functionName": function,
            "args": args,
        },
    )


@pytest.fixture
def module_page(chromium_browser, frontend_server):
    context = chromium_browser.new_context(timezone_id="America/New_York")
    page = context.new_page()
    page.goto(f"{frontend_server}/module-test.html")
    try:
        yield page
    finally:
        context.close()


def make_event(event_id, date="2026-08-10", **overrides):
    event = {
        "id": event_id,
        "title": f"Title {event_id}",
        "date": date,
        "time": "7:00 PM",
        "description": "",
        "venue": "Hall",
        "category": "music",
        "town": "Amherst",
        "source": "alpha",
    }
    event.update(overrides)
    return event


BLANK_FILTERS = {
    "q": "",
    "dateFrom": "",
    "dateTo": "",
    "category": "",
    "town": "",
    "source": "",
}


@pytest.mark.parametrize(
    ("generated", "today", "expected"),
    [
        ("2026-08-15", "2026-08-15", "current"),
        ("2026-08-01", "2026-08-15", "current"),
        ("2026-07-31", "2026-08-15", "stale"),
        ("2026-07-03", "2026-08-15", "stale"),
        ("2026-03-01", "2026-03-15", "current"),
        ("2024-02-29", "2024-03-15", "stale"),
        ("2026-08-16", "2026-08-15", "unknown"),
        ("2026-02-29", "2026-08-15", "unknown"),
        ("2026-04-31", "2026-08-15", "unknown"),
        ("garbage", "2026-08-15", "unknown"),
        ("", "2026-08-15", "unknown"),
        (None, "2026-08-15", "unknown"),
        (42, "2026-08-15", "unknown"),
    ],
)
def test_data_freshness(module_page, frontend_server, generated, today, expected):
    assert call_module(module_page, frontend_server, "dataFreshness", generated, today) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("concert", ["title"]),
        ("SCULPTURE", ["description"]),
        ("academy", ["venue"]),
        ("northampton", ["missing"]),
        ("beta", []),
    ],
)
def test_search_fields_are_case_insensitive(module_page, frontend_server, query, expected):
    events = [
        make_event("title", title="Summer Concert"),
        make_event("description", description="Sculpture workshop"),
        make_event("venue", venue="Academy of Music"),
        make_event("missing", description=None, venue=None, town="Northampton", source="beta"),
    ]
    filters = {**BLANK_FILTERS, "q": query}
    result = call_module(module_page, frontend_server, "filterEvents", events, filters)
    assert [event["id"] for event in result] == expected


def test_each_filter_and_all_filters_combined(module_page, frontend_server):
    match = make_event(
        "match",
        "2026-08-10",
        title="Jazz Night",
        category="music",
        town="Amherst",
        source="alpha",
    )
    events = [
        match,
        make_event("wrong-query", title="Poetry Night"),
        make_event("wrong-date", "2026-08-12", title="Jazz Night"),
        make_event("wrong-category", title="Jazz Night", category="arts"),
        make_event("wrong-town", title="Jazz Night", town="Hadley"),
        make_event("wrong-source", title="Jazz Night", source="beta"),
    ]
    filters = {
        "q": "jazz",
        "dateFrom": "2026-08-10",
        "dateTo": "2026-08-10",
        "category": "music",
        "town": "Amherst",
        "source": "alpha",
    }
    result = call_module(module_page, frontend_server, "filterEvents", events, filters)
    assert [event["id"] for event in result] == ["match"]

    dimensions = {
        "dateFrom": ("2026-08-11", ["wrong-date"]),
        "dateTo": ("2026-08-09", []),
        "category": ("arts", ["wrong-category"]),
        "town": ("Hadley", ["wrong-town"]),
        "source": ("beta", ["wrong-source"]),
    }
    for key, (value, expected) in dimensions.items():
        one_filter = {**BLANK_FILTERS, key: value}
        actual = call_module(module_page, frontend_server, "filterEvents", events, one_filter)
        assert [event["id"] for event in actual] == expected


def test_blank_inclusive_and_reversed_bounds(module_page, frontend_server):
    events = [make_event("a", "2026-08-09"), make_event("b"), make_event("c", "2026-08-11")]
    blank = call_module(module_page, frontend_server, "filterEvents", events, BLANK_FILTERS)
    assert [event["id"] for event in blank] == ["a", "b", "c"]

    inclusive = call_module(
        module_page,
        frontend_server,
        "filterEvents",
        events,
        {**BLANK_FILTERS, "dateFrom": "2026-08-10", "dateTo": "2026-08-10"},
    )
    assert [event["id"] for event in inclusive] == ["b"]

    reversed_result = call_module(
        module_page,
        frontend_server,
        "filterEvents",
        events,
        {**BLANK_FILTERS, "dateFrom": "2026-08-11", "dateTo": "2026-08-09"},
    )
    assert reversed_result == []


def test_time_parser_and_stable_sorting(module_page, frontend_server):
    times = [None, "garbage", "12:00 AM", "9 AM", "12:00 PM", "7:00 pm"]
    minutes = [call_module(module_page, frontend_server, "timeMinutes", value) for value in times]
    assert minutes == [-1, -1, 0, 540, 720, 1140]

    events = [
        make_event("later-date", "2026-08-11", time=""),
        make_event("equal-a", time="garbage"),
        make_event("midnight", time="12:00 AM"),
        make_event("morning", time="9 AM"),
        make_event("noon", time="12:00 PM"),
        make_event("evening", time="7:00 pm"),
        make_event("equal-b", time=None),
    ]
    result = call_module(module_page, frontend_server, "filterEvents", events, BLANK_FILTERS)
    assert [event["id"] for event in result] == [
        "equal-a",
        "equal-b",
        "midnight",
        "morning",
        "noon",
        "evening",
        "later-date",
    ]


def test_filtering_and_grouping_do_not_mutate_inputs(module_page, frontend_server):
    events = [make_event("b", "2026-08-11"), make_event("a", "2026-08-10")]
    filters = {**BLANK_FILTERS}
    original_events = copy.deepcopy(events)
    original_filters = copy.deepcopy(filters)

    call_module(module_page, frontend_server, "filterEvents", events, filters)
    groups = call_module(module_page, frontend_server, "groupEventsByDate", events)

    assert events == original_events
    assert filters == original_filters
    assert list(groups) == ["2026-08-11", "2026-08-10"]
    assert [event["id"] for event in groups["2026-08-11"]] == ["b"]

    browser_result = module_page.evaluate(
        """async url => {
          const module = await import(url);
          const events = [
            { id: 'later', title: 'Later', date: '2026-08-11', time: '',
              description: '', venue: '', category: 'music', town: 'Amherst',
              source: 'alpha' },
            { id: 'earlier', title: 'Earlier', date: '2026-08-10', time: '',
              description: '', venue: '', category: 'music', town: 'Amherst',
              source: 'alpha' },
          ];
          const filters = { q: '', dateFrom: '', dateTo: '', category: '',
            town: '', source: '' };
          const beforeEvents = JSON.stringify(events);
          const beforeFilters = JSON.stringify(filters);
          const filtered = module.filterEvents(events, filters);
          const grouped = module.groupEventsByDate(events);
          return {
            eventsUnchanged: JSON.stringify(events) === beforeEvents,
            filtersUnchanged: JSON.stringify(filters) === beforeFilters,
            filteredUsesRecords: filtered[0] === events[1] && filtered[1] === events[0],
            groupedUsesRecords: grouped['2026-08-11'][0] === events[0],
          };
        }""",
        f"{frontend_server}/event-data.js",
    )
    assert browser_result == {
        "eventsUnchanged": True,
        "filtersUnchanged": True,
        "filteredUsesRecords": True,
        "groupedUsesRecords": True,
    }


def test_grouping_empty_and_preserves_order(module_page, frontend_server):
    assert call_module(module_page, frontend_server, "groupEventsByDate", []) == {}
    events = [make_event("a"), make_event("b", "2026-08-11"), make_event("c")]
    groups = call_module(module_page, frontend_server, "groupEventsByDate", events)
    assert [event["id"] for event in groups["2026-08-10"]] == ["a", "c"]
    assert [event["id"] for event in groups["2026-08-11"]] == ["b"]


@pytest.mark.parametrize(
    ("year", "month_index", "length", "current_days"),
    [
        (2024, 1, 35, 29),
        (2025, 1, 35, 28),
        (2026, 1, 28, 28),
        (2026, 3, 35, 30),
        (2026, 7, 42, 31),
    ],
)
def test_calendar_leap_years_and_grid_lengths(
    module_page, frontend_server, year, month_index, length, current_days
):
    cells = call_module(module_page, frontend_server, "buildCalendarCells", year, month_index)
    assert len(cells) == length
    assert sum(cell["inCurrentMonth"] for cell in cells) == current_days


def test_calendar_boundaries_and_padding(module_page, frontend_server):
    april = call_module(module_page, frontend_server, "buildCalendarCells", 2026, 3)
    assert april[0] == {"date": "2026-03-29", "day": 29, "inCurrentMonth": False}
    assert next(cell for cell in april if cell["inCurrentMonth"])["date"] == "2026-04-01"
    assert [cell for cell in april if cell["inCurrentMonth"]][-1]["date"] == "2026-04-30"
    assert april[-1] == {"date": "2026-05-02", "day": 2, "inCurrentMonth": False}

    january = call_module(module_page, frontend_server, "buildCalendarCells", 2027, 0)
    assert january[0]["date"] == "2026-12-27"
    assert january[-1]["date"] == "2027-02-06"


@pytest.mark.parametrize("month_index", [2, 10])
def test_calendar_date_strings_match_across_timezones(
    chromium_browser, frontend_server, month_index
):
    results = []
    for timezone in ("America/New_York", "UTC"):
        context = chromium_browser.new_context(timezone_id=timezone)
        page = context.new_page()
        page.goto(f"{frontend_server}/module-test.html")
        results.append(call_module(page, frontend_server, "buildCalendarCells", 2026, month_index))
        context.close()
    assert results[0] == results[1]


@pytest.mark.parametrize(
    ("choice", "today", "start", "end"),
    [
        ("upcoming", "2026-12-31", "2026-12-31", ""),
        ("today", "2026-12-31", "2026-12-31", "2026-12-31"),
        ("week", "2026-12-31", "2026-12-31", "2027-01-06"),
        ("week", "2026-03-07", "2026-03-07", "2026-03-13"),
        ("week", "2026-10-31", "2026-10-31", "2026-11-06"),
        ("weekend", "2026-08-14", "2026-08-15", "2026-08-16"),
        ("weekend", "2026-08-15", "2026-08-15", "2026-08-16"),
        ("weekend", "2026-08-16", "2026-08-16", "2026-08-16"),
        ("weekend", "2026-08-17", "2026-08-22", "2026-08-23"),
        ("weekend", "2026-12-31", "2027-01-02", "2027-01-03"),
        ("all", "2026-08-15", "", ""),
    ],
)
def test_quick_date_boundaries(module_page, frontend_server, choice, today, start, end):
    assert call_module(module_page, frontend_server, "quickDateRange", choice, today) == {
        "dateFrom": start,
        "dateTo": end,
    }


def test_url_state_roundtrip_and_unknown_values(module_page, frontend_server):
    choices = {"category": ["music"], "town": ["Amherst"], "source": ["alpha"]}
    query = (
        "?dates=custom&from=2026-12-31&to=2027-01-06&q=Jazz+night"
        "&category=music&town=Amherst&source=alpha&view=calendar&month=2027-01&day=2027-01-02"
    )
    state = call_module(
        module_page, frontend_server, "readBrowserState", query, choices, "2026-08-15"
    )
    params = call_module(module_page, frontend_server, "browserStateParams", state)
    assert (
        call_module(module_page, frontend_server, "readBrowserState", params, choices, "2026-08-15")
        == state
    )
    invalid = call_module(
        module_page,
        frontend_server,
        "readBrowserState",
        "?dates=bogus&view=bogus&category=bogus&town=bogus&source=bogus&from=2026-02-30&month=2026-13&day=bad&unknown=ignored",
        choices,
        "2026-08-15",
    )
    assert invalid["filters"] == {**BLANK_FILTERS, "dateFrom": "2026-08-15"}
    assert invalid["view"] == "list"
    assert invalid["calendarMonth"] == "2026-08-01"
    custom = call_module(
        module_page,
        frontend_server,
        "readBrowserState",
        "?dates=custom&from=2026-02-30&to=bad",
        choices,
        "2026-08-15",
    )
    assert custom["filters"] == BLANK_FILTERS


def test_search_accepts_missing_optional_strings(module_page, frontend_server):
    events = [
        make_event("town", title=None, description=None, venue=None, town="Hadley"),
        make_event("missing", title=None, town=None, description=42, venue=["Sculpture"]),
    ]
    result = call_module(
        module_page, frontend_server, "filterEvents", events, {**BLANK_FILTERS, "q": " HADLEY "}
    )
    assert [event["id"] for event in result] == ["town"]

    numeric = call_module(
        module_page, frontend_server, "filterEvents", events, {**BLANK_FILTERS, "q": "42"}
    )
    assert [event["id"] for event in numeric] == ["missing"]
