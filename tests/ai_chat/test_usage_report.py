import re
from collections import Counter

import pytest

from ai_chat import usage_report, usage_stats
from ai_chat.usage_report import (
    compact,
    fill_periods,
    format_activity,
    format_bar_chart,
    format_breakdown,
    format_report,
    messages_by_weekday,
    share_bar,
    sparkline,
)
from ai_chat.usage_stats import UsageStats

REPORT_COUNTERS = {
    "2026-11": {"chats": 1, "messages": 4},
    "2026-10": {
        "chats": 2,
        "chats_with_follow_up": 1,
        "chats_with_6_messages": 1,
        "chats_with_documents": 1,
        "messages": 5,
        "message_tokens": 450,
        "responses": 4,
        "response_ms": 10_000,
        "response_stream_ms": 6_000,
        "response_tokens": 500,
        "llm_errors": 1,
        "documents_processed": 2,
        "documents_failed": 1,
        "documents_skipped": 3,
        "document_ms": 9_000,
        "uploaded_bytes": 1_500_000,
        "file_type_pdf": 1,
        "file_type_docx": 1,
    },
}
REPORT_OVERALL = sum(map(Counter, REPORT_COUNTERS.values()), Counter())
REPORT_HOURS = {9: 3, 14: 1}
REPORT_WEEKDAYS = dict.fromkeys(usage_report.WEEKDAYS, 0) | {"Mon": 4, "Wed": 2}


def report(counters: dict[str, dict[str, int]] = REPORT_COUNTERS, **options) -> str:
    options = {"timezone": "UTC", "current_period": "2026-11"} | options
    return format_report(counters, REPORT_HOURS, REPORT_WEEKDAYS, **options)


def rows_from(text: str, head: str) -> dict[str, list[str]]:
    """Return {label: cells} of the lines from the head row to the next blank line."""
    lines = text.splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if re.match(rf"{re.escape(head)}(\s{{2,}}|$)", line)
    )
    rows: dict[str, list[str]] = {}
    for line in lines[start:]:
        if not line:
            break
        label, *cells = re.split(r"\s{2,}", line.strip())
        rows[label] = cells
    return rows


def test_fill_periods_adds_months_and_days_without_usage() -> None:
    months = fill_periods({"2026-02": {"chats": 2}, "2025-11": {"chats": 1}}, "month")
    days = fill_periods({"2026-02-27": {"chats": 1}, "2026-03-01": {}}, "day")

    assert list(months) == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert [counters["chats"] for counters in months.values()] == [1, 0, 0, 2]
    assert list(days) == ["2026-02-27", "2026-02-28", "2026-03-01"]


@pytest.mark.parametrize(
    ("value", "decimals", "expected"),
    [
        (3.14, 1, "3.1"),
        (88.9, 0, "89"),
        (5_754.7, 1, "5,755"),
        (36_016, 0, "36k"),
        (576_611, 0, "577k"),
        (1_234_567, 0, "1.23M"),
        (99_999_999, 0, "100M"),
    ],
)
def test_compact_keeps_numbers_within_five_characters(
    value: float, decimals: int, expected: str
) -> None:
    assert compact(value, decimals) == expected


def test_row_takes_off_metrics_without_going_below_nothing() -> None:
    row = usage_report.Row("", "reached", "chats", minus="reached_more", share=True)

    assert row.exact(Counter(chats=4, reached=3, reached_more=1)) == "2 (50%)"
    # A chat can reach the next length on a later day than the one before.
    assert row.exact(Counter(chats=4, reached=1, reached_more=3)) == "0 (0%)"
    assert row.cell(Counter(chats=4, reached=1, reached_more=3)) == "0%"


def test_sparkline_scales_marks_from_zero_to_the_largest_value() -> None:
    assert sparkline([0, 1, 4, 8, None]) == "·▁▄█·"


@pytest.mark.parametrize(
    ("part", "whole", "expected"),
    [
        (1, 2, "████████········  50%"),
        (3, 32, "█▌··············   9%"),
        (1, 500, "▏···············   0%"),
        (3, 2, "████████████████ 150%"),
        (0, 0, "················    -"),
    ],
)
def test_share_bar_draws_the_part_of_the_whole(
    part: int, whole: int, expected: str
) -> None:
    assert share_bar(part, whole) == expected


def test_format_report_overview_shows_periods_as_columns_with_a_total() -> None:
    overview = report()

    lines = overview.splitlines()
    assert lines[0] == "Usage   2026-10 – 2026-11 · 2 months · UTC"
    assert lines[2].split() == ["Oct", "Nov*", "total"]
    assert rows_from(overview, "Chats") == {
        "Chats": ["2", "1", "3"],
        "Messages": ["5", "4", "9"],
        "per chat": ["2.5", "4.0", "3.0"],
        "Documents": ["6", "0", "6"],
    }
    assert rows_from(overview, "Answered") == {
        "Answered": ["80%", "0%", "44%"],
        "seconds each": ["2.5", "-", "2.5"],
        "tokens/second": ["83", "-", "83"],
        "* month to date": [],
    }
    assert "of 3 chats" in overview
    assert "peak Mon (67%)" in overview


def test_format_report_marks_only_the_current_period_as_to_date() -> None:
    overview = report(current_period="2026-12")

    assert overview.splitlines()[2].split() == ["Oct", "Nov", "total"]
    assert "to date" not in overview


def test_format_report_shows_the_latest_periods_and_totals_all_of_them() -> None:
    counters = {f"2026-{month:02}": {"chats": month} for month in range(1, 9)}

    overview = report(counters, current_period="2026-08")

    assert overview.splitlines()[2].split() == [
        *["Mar", "Apr", "May", "Jun", "Jul", "Aug*"],
        "total",
    ]
    assert rows_from(overview, "Chats")["Chats"] == [
        *["3", "4", "5", "6", "7", "8"],
        "36",
    ]
    assert rows_from(overview, "Answered")["+ 2 earlier months in total"] == []


def test_format_report_by_day_shows_the_latest_days_as_columns() -> None:
    counters = {f"2026-11-{day:02}": {"chats": 1} for day in range(1, 31)}

    overview = report(counters, by="day", current_period="2026-11-30")

    lines = overview.splitlines()
    assert lines[0].startswith("Usage   2026-11-01 – 2026-11-30 · 30 days")
    assert lines[2].split()[:6] == [
        *["11-25", "11-26", "11-27", "11-28", "11-29"],
        "11-30*",
    ]
    assert rows_from(overview, "Chats")["Chats"][-2:] == ["1", "30"]
    assert rows_from(overview, "Answered")["* today so far"] == []
    assert rows_from(overview, "Answered")["+ 24 earlier days in total"] == []


@pytest.mark.parametrize("detailed", [False, True])
def test_format_report_fits_the_terminal_with_large_numbers(detailed: bool) -> None:
    large = dict.fromkeys(usage_stats.METRICS, 123_456_789)
    counters = {f"2026-{month:02}": large for month in range(1, 13)}

    lines = report(counters, detailed=detailed).splitlines()

    assert max(map(len, lines)) <= 80


def test_format_breakdown_shows_shares_of_chats_messages_and_documents() -> None:
    breakdown = format_breakdown(REPORT_OVERALL)

    shares = {
        line.split()[0]: re.findall(r"\d+%", line)
        for line in breakdown.splitlines()
        if "%" in line
    }
    assert shares == {
        "follow-up": ["33%"],
        "documents": ["33%", "0%"],
        "thinking": ["0%", "0%"],
        "history": ["0%"],
        "processed": ["33%", "50%"],
        "failed": ["17%", "50%"],
        "skipped": ["50%", "0%"],
        "Code": ["0%"],
        "other": ["0%"],
    }
    for text in (
        "of 3 chats",
        "of 9 messages",
        "6 uploaded · 1.5 MB · avg 0 tokens, 1.5 s import",
        "5 of 9 messages · 0 too large · 1 model error",
        "50-token message → 125-token answer in 2.5 s",
    ):
        assert text in breakdown


def test_format_breakdown_leaves_out_what_has_no_data() -> None:
    breakdown = format_breakdown(Counter(chats=1, messages=1))

    assert f"{'Documents':<21}none uploaded" in breakdown.splitlines()
    assert "processed" not in breakdown
    assert "Typical exchange" not in breakdown


def test_format_activity_draws_messages_by_hour_and_weekday() -> None:
    marks, _, peaks = format_activity(REPORT_HOURS, REPORT_WEEKDAYS).splitlines()

    hours = "·········█····▃·········"
    assert marks.split() == ["When", hours, "██", "··", "▄▄", "··", "··", "··", "··"]
    assert "peak 09h (75%)" in peaks
    assert "peak Mon (67%)" in peaks


def test_format_activity_handles_missing_data() -> None:
    weekdays = dict.fromkeys(usage_report.WEEKDAYS, 0)

    marks, _, peaks = format_activity({}, weekdays).splitlines()

    assert marks.split() == ["When", "·" * 24, *["··"] * 7]
    assert peaks.split() == ["no", "messages", "no", "messages"]


def test_format_report_detailed_shows_every_counter_as_a_row() -> None:
    detailed = report(detailed=True)

    assert detailed.splitlines()[2].split() == ["Oct", "Nov*", "total"]
    assert rows_from(detailed, "Chats") == {
        "Chats": ["2", "1", "3"],
        "with follow-up": ["50%", "0%", "1 (33%)"],
        "with documents": ["50%", "0%", "1 (33%)"],
        "with thinking": ["0%", "0%", "0 (0%)"],
        "messages per chat": ["2.5", "4.0", "3.0"],
        "1 message": ["50%", "100%", "2 (67%)"],
        "2-5 messages": ["0%", "0%", "0 (0%)"],
        "6-10 messages": ["50%", "0%", "1 (33%)"],
        "11-20 messages": ["0%", "0%", "0 (0%)"],
        "21+ messages": ["0%", "0%", "0 (0%)"],
    }
    assert rows_from(detailed, "Messages") == {
        "Messages": ["5", "4", "9"],
        "with documents": ["0%", "0%", "0 (0%)"],
        "with thinking": ["0%", "0%", "0 (0%)"],
        "history trimmed": ["0%", "0%", "0 (0%)"],
        "answered": ["80%", "0%", "4 (44%)"],
        "too large": ["0%", "0%", "0 (0%)"],
        "model error": ["20%", "0%", "1 (11%)"],
        "tokens": ["450", "0", "450"],
        "tokens each": ["90", "0", "50"],
    }
    assert rows_from(detailed, "Answers") == {
        "Answers": ["4", "0", "4"],
        "seconds": ["10.0", "0.0", "10.0"],
        "seconds each": ["2.5", "-", "2.5"],
        "until first token": ["1.0", "-", "1.0"],
        "tokens": ["500", "0", "500"],
        "tokens each": ["125", "-", "125"],
        "tokens/second": ["83", "-", "83"],
    }
    documents = rows_from(detailed, "Documents")
    assert list(documents)[6:] == list(usage_stats.FILE_TYPES)
    assert documents["Documents"] == ["6", "0", "6"]
    assert documents["failed"] == ["1", "0", "1"]
    assert documents["skipped"] == ["3", "0", "3"]
    assert documents["MB"] == ["1.5", "0.0", "1.5"]
    assert documents["import seconds"] == ["9.0", "0.0", "9.0"]
    assert documents["import seconds each"] == ["1.5", "-", "1.5"]
    assert documents["pdf"] == ["50%", "-", "1 (50%)"]
    processed = rows_from(detailed, "Processed documents")
    assert processed["Processed documents"] == ["2", "0", "2"]
    assert processed["tokens"] == ["0", "0", "0"]
    assert processed["tokens each"] == ["0", "-", "0"]
    assert processed["* month to date"] == []


def test_report_rows_name_only_known_metrics_and_cover_all_of_them() -> None:
    def metric_names(groups: list[list[usage_report.Row]]) -> set[str]:
        names: set[str] = set()
        for row in (row for group in groups for row in group):
            for metrics in (row.metrics, row.minus, row.per):
                names.update((metrics,) if isinstance(metrics, str) else metrics)
        return names

    known = set(usage_stats.METRICS)
    # A misspelled metric would not fail: it would count as zero in the report.
    assert metric_names(usage_report.OVERVIEW_ROWS) <= known
    assert metric_names(usage_report.DETAILED_ROWS) == known


def test_format_report_handles_empty_statistics() -> None:
    assert report({}) == "No usage statistics recorded yet."


def test_messages_by_weekday_sums_days_from_monday_to_sunday() -> None:
    days = {
        "2026-11-16": {"messages": 3},
        "2026-11-18": {"messages": 5, "chats": 2},
        "2026-11-23": {"messages": 1},
        "2026-11-24": {"chats": 1},
    }

    assert messages_by_weekday(days) == {
        "Mon": 4,
        "Tue": 0,
        "Wed": 5,
        "Thu": 0,
        "Fri": 0,
        "Sat": 0,
        "Sun": 0,
    }


def test_format_bar_chart_scales_bars_to_the_largest_value() -> None:
    chart = format_bar_chart("Messages by weekday", {"Mon": 30, "Tue": 10, "Wed": 0})

    title, monday, tuesday, wednesday = chart.splitlines()
    assert title == "Messages by weekday"
    assert monday.split() == ["Mon", "█" * 30, "30", "(75%)"]
    assert tuesday.split() == ["Tue", "█" * 10, "10", "(25%)"]
    assert wednesday.split() == ["Wed", "0", "(0%)"]


def test_format_bar_chart_handles_missing_data() -> None:
    assert format_bar_chart("Messages by weekday", {"Mon": 0}) == (
        "Messages by weekday\nno data yet"
    )


def test_main_shows_the_overview_in_the_stats_time_zone(
    seeded_stats, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(usage_report, "load_usage_stats", lambda: seeded_stats)

    usage_report.main([])

    overview = capsys.readouterr().out
    lines = overview.splitlines()
    assert lines[0] == "Usage   2026-10 – 2026-11 · 2 months · UTC"
    assert lines[2].split() == ["Oct", "Nov*", "total"]
    assert rows_from(overview, "Chats")["Messages"] == ["3", "4", "7"]
    assert "peak 14h (57%)" in overview
    assert "peak Thu (57%)" in overview


def test_main_applies_options(seeded_stats, monkeypatch, capsys) -> None:
    monkeypatch.setattr(usage_report, "load_usage_stats", lambda: seeded_stats)

    usage_report.main(["--since", "2026-10-20", "--by", "day", "--detailed"])

    detailed = capsys.readouterr().out
    lines = detailed.splitlines()
    assert lines[0] == "Usage   2026-10-20 – 2026-11-05 · 17 days · UTC"
    assert lines[2].split()[-2:] == ["11-05*", "total"]
    assert rows_from(detailed, "Messages")["Messages"][-2:] == ["4", "6"]
    assert "pptx" in detailed
    assert "Messages by hour of day (UTC)" in detailed
    # The hours follow --since too: the message of 3 October at 09h is left out.
    assert rows_from(detailed, "09")["09"][-2:] == ["2", "(33%)"]
    assert "Messages by weekday" in detailed


def test_main_reports_empty_statistics(tmp_path, monkeypatch, capsys) -> None:
    empty = UsageStats(tmp_path / "usage.sqlite")
    monkeypatch.setattr(usage_report, "load_usage_stats", lambda: empty)

    usage_report.main([])

    assert capsys.readouterr().out == "No usage statistics recorded yet.\n"


@pytest.mark.parametrize("arguments", [["--since", "last week"], ["--by", "hour"]])
def test_main_rejects_invalid_options(arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        usage_report.main(arguments)


@pytest.mark.parametrize("count", [12_345, 123_456])
def test_format_report_detailed_keeps_gap_and_alignment_for_large_totals(
    count: int,
) -> None:
    monthly = {
        "chats": count,
        "chats_with_follow_up": count,
        "messages": count,
        "responses": count,
    }
    counters = {f"2026-{month:02}": monthly for month in range(1, 7)}

    lines = report(counters, current_period="2026-06", detailed=True).splitlines()
    table_lines = [
        line
        for line in lines[2:]
        if line
        and not line.startswith(("Messages by ", "* ", " ", "0", "1", "2"))
        or line.startswith("  ")
    ]
    # Header line and all table metric rows should share one right edge and <= 80 cols.
    header_width = len(lines[2])
    assert header_width <= 80
    follow_up_line = next(line for line in lines if line.startswith("  with follow-up"))
    assert len(follow_up_line) == header_width
    # At least two spaces separate the rightmost period cell ("100%") from the total.
    assert re.search(r"100%\s{2,}[\d,]+ \(100%\)$", follow_up_line)
    assert len(table_lines) > 0


def test_main_reports_disabled_usage_statistics(monkeypatch, capsys) -> None:
    disabled = UsageStats(None)
    monkeypatch.setattr(usage_report, "load_usage_stats", lambda: disabled)

    usage_report.main([])

    assert "disabled" in capsys.readouterr().out.lower()


def test_main_reports_empty_window_when_since_matches_no_data(
    seeded_stats, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(usage_report, "load_usage_stats", lambda: seeded_stats)

    usage_report.main(["--since", "2026-12-01"])

    assert capsys.readouterr().out == "No usage statistics recorded since 2026-12-01.\n"


def test_main_reads_usage_in_a_single_snapshot(
    seeded_stats, monkeypatch, capsys
) -> None:
    calls: list[str] = []
    original = seeded_stats.read_snapshot

    def counting_snapshot(since: str = ""):
        calls.append(since)
        return original(since)

    monkeypatch.setattr(seeded_stats, "read_snapshot", counting_snapshot)
    monkeypatch.setattr(usage_report, "load_usage_stats", lambda: seeded_stats)

    usage_report.main(["--by", "day"])

    assert calls == [""]
    assert "Usage   2026-10-03" in capsys.readouterr().out


def test_format_breakdown_shows_code_types_and_skipped_label() -> None:
    overall = Counter(
        chats=1,
        messages=1,
        documents_processed=1,
        documents_failed=1,
        documents_skipped=1,
        file_type_py=2,
        file_type_rmd=1,
    )

    breakdown = format_breakdown(overall)

    assert "  skipped" in breakdown
    assert "  too large" not in breakdown
    assert "Code" in breakdown
    assert "100%" in next(line for line in breakdown.splitlines() if "Code" in line)


def test_format_report_marks_partial_first_month_when_since_is_mid_month() -> None:
    overview = report(since="2026-10-20")

    assert overview.splitlines()[0] == (
        "Usage   2026-10 – 2026-11 · 2 months · from 2026-10-20 · UTC"
    )


def test_format_report_omits_from_marker_when_since_is_first_of_month() -> None:
    overview = report(since="2026-10-01")

    assert overview.splitlines()[0] == "Usage   2026-10 – 2026-11 · 2 months · UTC"


def test_format_report_omits_from_marker_for_daily_reports() -> None:
    daily = report(
        {"2026-10-20": {"chats": 1, "messages": 1}},
        by="day",
        current_period="2026-10-20",
        since="2026-10-20",
    )

    assert daily.splitlines()[0] == "Usage   2026-10-20 – 2026-10-20 · 1 day · UTC"


def test_main_falls_back_to_utc_when_timezone_key_is_none(
    seeded_stats, monkeypatch, capsys
) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(seeded_stats, "timezone", SimpleNamespace(key=None))
    monkeypatch.setattr(usage_report, "load_usage_stats", lambda: seeded_stats)
    monkeypatch.setattr(seeded_stats, "today", lambda: usage_report.date(2026, 11, 5))

    usage_report.main([])

    assert capsys.readouterr().out.splitlines()[0].endswith(" · UTC")
