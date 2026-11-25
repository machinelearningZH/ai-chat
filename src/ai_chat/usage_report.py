"""The usage statistics report: `make stats` on the command line.

Renders the counters of ai_chat.usage_stats for an 80-column terminal, as a
one-screen overview or with every counter.
"""

import argparse
import calendar
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from ai_chat.usage_stats import FILE_TYPES, PERIOD_LENGTHS, load_usage_stats

DOCUMENT_OUTCOMES = ("documents_processed", "documents_failed", "documents_skipped")
OFFICE_TYPES = ("file_type_docx", "file_type_pptx", "file_type_xlsx")
TEXT_TYPES = ("file_type_csv", "file_type_txt", "file_type_md")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# The report is laid out for a terminal that is 80 characters wide.
LABEL_WIDTH = 21
CELL_WIDTH = 6
SHOWN_PERIODS = 6
SHARE_BAR_WIDTH = 16
CHART_BAR_WIDTH = 30
SPARK_MARKS = "▁▂▃▄▅▆▇█"
TO_DATE_NOTES = {"month": "* month to date", "day": "* today so far"}

Metrics = str | tuple[str, ...]


def amount(counters: Counter[str], metrics: Metrics) -> int:
    names = (metrics,) if isinstance(metrics, str) else metrics
    return sum(counters[name] for name in names)


def compact(value: float, decimals: int = 0) -> str:
    """Format a number in at most five characters, such as 3.1, 5,755 or 36k."""
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if value >= max(0.9995 * size, 9_999.5):
            return f"{value / size:.3g}{suffix}"
    return f"{value:,.0f}" if value >= 999.5 else f"{value:.{decimals}f}"


def plural(count: int, noun: str) -> str:
    return f"{compact(count)} {noun}{'' if count == 1 else 's'}"


@dataclass(frozen=True)
class Row:
    """A report line: a total of metrics, or with `per` their average or share."""

    label: str
    metrics: Metrics
    per: Metrics = ()
    minus: Metrics = ()  # Taken off the total.
    unit: float = 1  # Divides the total: 1000 turns milliseconds into seconds.
    decimals: int = 0
    share: bool = False

    def count(self, counters: Counter[str]) -> int:
        """Sum the metrics and take off `minus`, but never below nothing.

        A chat can reach a length on a later day than the length before it, which
        would turn the difference of that day negative.
        """
        return max(amount(counters, self.metrics) - amount(counters, self.minus), 0)

    def value(self, counters: Counter[str]) -> float | None:
        """Return the number of the line, or None with nothing to divide by."""
        total = self.count(counters) / self.unit
        if not self.per:
            return total
        count = amount(counters, self.per)
        return total / count if count else None

    def cell(self, counters: Counter[str]) -> str:
        """Format the value for a narrow column."""
        value = self.value(counters)
        if value is None:
            return "-"
        return f"{value:.0%}" if self.share else compact(value, self.decimals)

    def exact(self, counters: Counter[str]) -> str:
        """Format the value in full, a share together with its count."""
        value = self.value(counters)
        if value is None:
            return "-"
        if self.share:
            return f"{self.count(counters):,} ({value:.0%})"
        return f"{value:,.{self.decimals}f}"


SECONDS_PER_ANSWER = Row(
    "  seconds each", "response_ms", "responses", unit=1000, decimals=1
)
# Waiting for the first answer token, which includes any thinking, is its own
# row: the tokens of the answer are divided by the time it took to stream them.
SECONDS_TO_FIRST_TOKEN = Row(
    "  until first token",
    "response_ms",
    "responses",
    minus="response_stream_ms",
    unit=1000,
    decimals=1,
)
# Milliseconds are the divisor, so the unit turns the result into seconds.
TOKENS_PER_SECOND = Row(
    "  tokens/second", "response_tokens", "response_stream_ms", unit=1 / 1000
)
TOKENS_PER_MESSAGE = Row("  tokens each", "message_tokens", "messages")
TOKENS_PER_ANSWER = Row("  tokens each", "response_tokens", "responses")
TOKENS_PER_DOCUMENT = Row("  tokens each", "document_tokens", "documents_processed")
UPLOADED_MB = Row("  MB", "uploaded_bytes", unit=1_000_000, decimals=1)
IMPORT_SECONDS_EACH = Row(
    "  import seconds each", "document_ms", DOCUMENT_OUTCOMES, unit=1000, decimals=1
)

# Report tables as groups of rows; indented rows detail the first row of a group.
OVERVIEW_ROWS = [
    [
        Row("Chats", "chats"),
        Row("Messages", "messages"),
        Row("  per chat", "messages", "chats", decimals=1),
        Row("Documents", DOCUMENT_OUTCOMES),
    ],
    [
        Row("Answered", "responses", "messages", share=True),
        SECONDS_PER_ANSWER,
        TOKENS_PER_SECOND,
    ],
]
DETAILED_ROWS = [
    [
        Row("Chats", "chats"),
        Row("  with follow-up", "chats_with_follow_up", "chats", share=True),
        Row("  with documents", "chats_with_documents", "chats", share=True),
        Row("  with thinking", "chats_with_thinking", "chats", share=True),
        Row("  messages per chat", "messages", "chats", decimals=1),
        Row("  1 message", "chats", "chats", minus="chats_with_follow_up", share=True),
        Row(
            "  2-5 messages",
            "chats_with_follow_up",
            "chats",
            minus="chats_with_6_messages",
            share=True,
        ),
        Row(
            "  6-10 messages",
            "chats_with_6_messages",
            "chats",
            minus="chats_with_11_messages",
            share=True,
        ),
        Row(
            "  11-20 messages",
            "chats_with_11_messages",
            "chats",
            minus="chats_with_21_messages",
            share=True,
        ),
        Row("  21+ messages", "chats_with_21_messages", "chats", share=True),
    ],
    [
        Row("Messages", "messages"),
        Row("  with documents", "messages_with_documents", "messages", share=True),
        Row("  with thinking", "messages_with_thinking", "messages", share=True),
        Row("  history trimmed", "history_trimmed", "messages", share=True),
        Row("  answered", "responses", "messages", share=True),
        Row("  too large", "message_too_large", "messages", share=True),
        Row("  model error", "llm_errors", "messages", share=True),
        Row("  tokens", "message_tokens"),
        TOKENS_PER_MESSAGE,
    ],
    [
        Row("Answers", "responses"),
        Row("  seconds", "response_ms", unit=1000, decimals=1),
        SECONDS_PER_ANSWER,
        SECONDS_TO_FIRST_TOKEN,
        Row("  tokens", "response_tokens"),
        TOKENS_PER_ANSWER,
        TOKENS_PER_SECOND,
    ],
    [
        Row("Documents", DOCUMENT_OUTCOMES),
        Row("  failed", "documents_failed"),
        Row("  too large", "documents_skipped"),
        UPLOADED_MB,
        Row("  import seconds", "document_ms", unit=1000, decimals=1),
        IMPORT_SECONDS_EACH,
    ],
    [
        Row("Processed documents", "documents_processed"),
        Row("  tokens", "document_tokens"),
        TOKENS_PER_DOCUMENT,
        *(
            Row(
                f"  {file_type}",
                f"file_type_{file_type}",
                "documents_processed",
                share=True,
            )
            for file_type in FILE_TYPES
        ),
    ],
]


def fill_periods(
    counters: dict[str, dict[str, int]], by: str
) -> dict[str, Counter[str]]:
    """Return the counters of every month or day from the first to the last one.

    Periods without usage are added, so that the report columns form a calendar.
    """
    first, last = min(counters), max(counters)
    if by == "day":
        start = date.fromisoformat(first)
        length = (date.fromisoformat(last) - start).days + 1
        names = [(start + timedelta(days=days)).isoformat() for days in range(length)]
    else:
        start, end = (
            int(month[:4]) * 12 + int(month[5:]) - 1 for month in (first, last)
        )
        names = [
            f"{index // 12:04}-{index % 12 + 1:02}" for index in range(start, end + 1)
        ]
    return {name: Counter(counters.get(name, {})) for name in names}


def period_label(period: str, by: str) -> str:
    """Name a month as Nov and a day as 11-19."""
    return period[5:] if by == "day" else calendar.month_abbr[int(period[5:])]


def sparkline(values: Iterable[float | None]) -> str:
    """Draw one mark per value, scaled from zero to the largest value.

    A dot stands for nothing, which keeps a small amount apart from none at all.
    """
    values = list(values)
    top = max((value or 0 for value in values), default=0)
    highest = len(SPARK_MARKS)
    return "".join(
        SPARK_MARKS[min(highest, max(1, round(highest * value / top))) - 1]
        if value
        else "·"
        for value in values
    )


def share_bar(part: int, whole: int) -> str:
    """Draw the part of a whole as a bar in half-character steps, with its share."""
    if not whole:
        return f"{'·' * SHARE_BAR_WIDTH}    -"
    halves = min(2 * SHARE_BAR_WIDTH, round(2 * SHARE_BAR_WIDTH * part / whole))
    bar = "█" * (halves // 2) + "▌" * (halves % 2)
    if part and not bar:
        bar = "▏"
    return f"{bar.ljust(SHARE_BAR_WIDTH, '·')} {part / whole:>4.0%}"


def format_table(
    groups: list[list[Row]],
    periods: dict[str, Counter[str]],
    by: str,
    current_period: str,
    exact_total: bool,
) -> str:
    """Render one line per row, with the latest periods as columns and a total.

    The total covers all periods, also those too old to get a column. It is
    shortened like the other cells unless the exact total is asked for.
    """
    shown = dict(list(periods.items())[-SHOWN_PERIODS:])
    overall = sum(periods.values(), Counter())
    to_date = list(shown)[-1] == current_period
    total_width = 13 if exact_total else 8

    labels = "".join(period_label(period, by).rjust(CELL_WIDTH) for period in shown)
    # The marker of an unfinished period hangs into the gap before the total.
    header = (
        f"{'':{LABEL_WIDTH}}{labels}{'*' * to_date}{'total':>{total_width - to_date}}"
    )
    lines = [header]
    for index, group in enumerate(groups):
        if index:
            lines.append("")
        for row in group:
            cells = "".join(
                row.cell(counters).rjust(CELL_WIDTH) for counters in shown.values()
            )
            total = row.exact(overall) if exact_total else row.cell(overall)
            lines.append(f"{row.label:{LABEL_WIDTH}}{cells}{total:>{total_width}}")

    if to_date:
        lines.append(TO_DATE_NOTES[by].rjust(len(f"{'':{LABEL_WIDTH}}{labels}*")))
    hidden = len(periods) - len(shown)
    if hidden:
        note = f"+ {plural(hidden, f'earlier {by}')} in total"
        lines.append(f"{'':{LABEL_WIDTH}}{note}")
    return "\n".join(lines)


def format_breakdown(overall: Counter[str]) -> str:
    """Render how the chats, messages and documents of all periods split up."""
    chats, messages = overall["chats"], overall["messages"]
    documents = amount(overall, DOCUMENT_OUTCOMES)
    share_width = SHARE_BAR_WIDTH + 5

    def line(label: str, *columns: str) -> str:
        return f"{label:{LABEL_WIDTH}}{'    '.join(columns)}".rstrip()

    def of(part: str, whole: int) -> str:
        return share_bar(overall[part], whole)

    lines = [
        line(
            "How it is used",
            f"of {plural(chats, 'chat')}".ljust(share_width),
            f"of {plural(messages, 'message')}",
        ),
        line("  follow-up", of("chats_with_follow_up", chats)),
        line(
            "  documents",
            of("chats_with_documents", chats),
            of("messages_with_documents", messages),
        ),
        line(
            "  thinking",
            of("chats_with_thinking", chats),
            of("messages_with_thinking", messages),
        ),
        line("  history trimmed", " " * share_width, of("history_trimmed", messages)),
        "",
    ]

    if documents:
        outcomes = [
            ("  processed", "documents_processed"),
            ("  failed", "documents_failed"),
            ("  too large", "documents_skipped"),
            ("", ""),
        ]
        file_types = [
            ("PDF", "file_type_pdf"),
            ("Office", OFFICE_TYPES),
            ("Text", TEXT_TYPES),
            ("other", "file_type_other"),
        ]
        lines.append(
            line(
                "Documents",
                f"{compact(documents)} uploaded · {UPLOADED_MB.cell(overall)} MB · "
                f"avg {TOKENS_PER_DOCUMENT.cell(overall)} tokens, "
                f"{IMPORT_SECONDS_EACH.cell(overall)} s import",
            )
        )
        for (outcome, metric), (file_type, type_metrics) in zip(
            outcomes, file_types, strict=True
        ):
            lines.append(
                line(
                    outcome,
                    of(metric, documents) if outcome else " " * share_width,
                    f"{file_type:8}"
                    + share_bar(
                        amount(overall, type_metrics), overall["documents_processed"]
                    ),
                )
            )
    else:
        lines.append(line("Documents", "none uploaded"))

    lines += [
        "",
        line(
            "Not answered",
            f"{compact(max(messages - overall['responses'], 0))} of "
            f"{plural(messages, 'message')} · "
            f"{compact(overall['message_too_large'])} too large · "
            f"{plural(overall['llm_errors'], 'model error')}",
        ),
    ]
    if overall["responses"]:
        lines.append(
            line(
                "Typical exchange",
                f"{TOKENS_PER_MESSAGE.cell(overall)}-token message → "
                f"{TOKENS_PER_ANSWER.cell(overall)}-token answer in "
                f"{SECONDS_PER_ANSWER.cell(overall)} s",
            )
        )
    return "\n".join(lines)


def messages_by_weekday(days: dict[str, dict[str, int]]) -> dict[str, int]:
    """Sum the messages of daily counters per weekday, Monday first."""
    weekdays = dict.fromkeys(WEEKDAYS, 0)
    for day, counters in days.items():
        weekdays[WEEKDAYS[date.fromisoformat(day).weekday()]] += counters.get(
            "messages", 0
        )
    return weekdays


def peak(values: dict[str, int]) -> str:
    """Name the largest value with its share of the sum."""
    whole = sum(values.values())
    if not whole:
        return "no messages"
    label, largest = max(values.items(), key=lambda item: item[1])
    return f"peak {label} ({largest / whole:.0%})"


def format_activity(hours: dict[int, int], weekdays: dict[str, int]) -> str:
    """Render the messages per hour of day and per weekday as two small charts."""
    by_hour = {f"{hour:02}h": hours.get(hour, 0) for hour in range(24)}
    rows = [
        (
            "When",
            sparkline(by_hour.values()),
            " ".join(2 * mark for mark in sparkline(weekdays.values())),
        ),
        ("", "00    06    12    18", " ".join(day[:2] for day in weekdays)),
        ("", peak(by_hour), peak(weekdays)),
    ]
    gap = " " * 5
    return "\n".join(
        f"{label:{LABEL_WIDTH}}{by_hours:{len(by_hour)}}{gap}{by_weekdays}"
        for label, by_hours, by_weekdays in rows
    )


def format_bar_chart(title: str, values: dict[str, int]) -> str:
    """Render one bar per value, scaled to the largest, with its share of the sum."""
    whole, largest = sum(values.values()), max(values.values())
    if not whole:
        return f"{title}\nno data yet"
    return "\n".join(
        [
            title,
            *(
                f"{label:<5}"
                f"{'█' * round(CHART_BAR_WIDTH * value / largest):<{CHART_BAR_WIDTH}}"
                f"{value:>8,}{f'({value / whole:.0%})':>8}"
                for label, value in values.items()
            ),
        ]
    )


def format_report(
    counters: dict[str, dict[str, int]],
    hours: dict[int, int],
    weekdays: dict[str, int],
    *,
    timezone: str,
    by: str = "month",
    current_period: str = "",
    detailed: bool = False,
) -> str:
    """Render the one-screen overview, or every counter when detailed."""
    if not counters:
        return "No usage statistics recorded yet."

    periods = fill_periods(counters, by)
    first, last = min(periods), max(periods)
    title = f"Usage   {first} – {last} · {plural(len(periods), by)} · {timezone}"
    if detailed:
        by_hour = {f"{hour:02}": hours.get(hour, 0) for hour in range(24)}
        blocks = [
            format_table(DETAILED_ROWS, periods, by, current_period, exact_total=True),
            format_bar_chart(f"Messages by hour of day ({timezone})", by_hour),
            format_bar_chart("Messages by weekday", weekdays),
        ]
    else:
        blocks = [
            format_table(OVERVIEW_ROWS, periods, by, current_period, exact_total=False),
            format_breakdown(sum(periods.values(), Counter())),
            format_activity(hours, weekdays),
        ]
    return "\n\n".join([title, *blocks])


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Show anonymous usage statistics.")
    parser.add_argument(
        "--by",
        choices=list(PERIOD_LENGTHS),
        default="month",
        help="show one column per month (default) or per day",
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        default=date.min,
        help="first day to include, as YYYY-MM-DD",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="show every counter instead of the overview",
    )
    options = parser.parse_args(arguments)
    stats = load_usage_stats()
    since = options.since.isoformat()

    print(
        format_report(
            stats.read(options.by, since),
            stats.read_message_hours(since),
            messages_by_weekday(stats.read("day", since)),
            timezone=stats.timezone.key,
            by=options.by,
            current_period=stats.today().isoformat()[: PERIOD_LENGTHS[options.by]],
            detailed=options.detailed,
        )
    )


if __name__ == "__main__":
    main()
