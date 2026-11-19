"""Anonymous usage statistics.

Stores one running total per metric and day, plus the number of messages per
day and hour of day, and nothing else: no per-chat rows, identifiers, text,
file names, or exact times. Metric names come from the closed set METRICS, so
user-controlled values can never be stored.

Counters are added when an event happens, not when a chat ends: Chainlit calls
on_chat_end on every websocket disconnect, which would count a chat repeatedly.

Read the totals with `make stats`, which runs ai_chat.usage_report.
"""

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ai_chat.config import PROJECT_ROOT, ConfigError, get_custom_logger, load_config

logger = get_custom_logger()

FILE_TYPES = ("pdf", "docx", "pptx", "xlsx", "csv", "txt", "md", "other")

METRICS = (
    "chats",  # Chats with at least one message.
    "chats_with_follow_up",  # Chats with more than one message.
    "chats_with_6_messages",  # Chats that reached this number of messages.
    "chats_with_11_messages",
    "chats_with_21_messages",
    "chats_with_documents",
    "chats_with_thinking",
    "messages",
    "messages_with_documents",
    "messages_with_thinking",
    "message_tokens",
    "responses",  # Answers generated without an error.
    "response_ms",  # From sending the request to the end of those answers.
    "response_stream_ms",  # The part of it from the first answer token on.
    "response_tokens",
    "documents_processed",
    "documents_failed",
    "documents_skipped",
    "document_tokens",
    "document_ms",  # Total import time of the messages with documents.
    "uploaded_bytes",
    *(f"file_type_{file_type}" for file_type in FILE_TYPES),
    "history_trimmed",
    "message_too_large",
    "llm_errors",
)

# The metric to count when a chat reaches a number of messages. Each chat adds
# to all metrics up to its length, so a range of lengths is one metric minus the
# next: no per-chat number has to be stored for the distribution.
CHAT_LENGTH_METRICS = {
    1: "chats",
    2: "chats_with_follow_up",
    6: "chats_with_6_messages",
    11: "chats_with_11_messages",
    21: "chats_with_21_messages",
}


# A period is the leading part of an ISO day such as 2026-11-18.
PERIOD_LENGTHS = {"month": 7, "day": 10}

_CREATE_TABLES = """
    CREATE TABLE IF NOT EXISTS counters (
        day TEXT NOT NULL,
        metric TEXT NOT NULL,
        value INTEGER NOT NULL,
        PRIMARY KEY (day, metric)
    );
    CREATE TABLE IF NOT EXISTS message_hours (
        day TEXT NOT NULL,
        hour INTEGER NOT NULL,
        messages INTEGER NOT NULL,
        PRIMARY KEY (day, hour)
    );
"""
_ADD = """
    INSERT INTO counters (day, metric, value) VALUES (?, ?, ?)
    ON CONFLICT (day, metric) DO UPDATE SET value = value + excluded.value
"""
_ADD_MESSAGE_HOUR = """
    INSERT INTO message_hours (day, hour, messages) VALUES (?, ?, ?)
    ON CONFLICT (day, hour) DO UPDATE SET messages = messages + excluded.messages
"""
_READ = """
    SELECT substr(day, 1, ?) AS period, metric, SUM(value)
    FROM counters WHERE day >= ? GROUP BY period, metric
"""
_READ_MESSAGE_HOURS = """
    SELECT hour, SUM(messages) FROM message_hours
    WHERE day >= ? GROUP BY hour
"""


def _move_monthly_hours_to_days(connection: sqlite3.Connection) -> None:
    """Carry over the hours of a stats file that still keeps them per month.

    The day within the month is not known, so they count for its first day. This
    can go once no stats file from before the change is in use.
    """
    columns = connection.execute("PRAGMA table_info(message_hours)").fetchall()
    if "month" in (name for _, name, *_ in columns):
        connection.execute("BEGIN")
        connection.execute("ALTER TABLE message_hours RENAME COLUMN month TO day")
        connection.execute("UPDATE message_hours SET day = day || '-01'")
        connection.commit()


def utc_now() -> datetime:
    return datetime.now(UTC)


def file_type_metric(suffix: str) -> str:
    """Map a user-controlled file extension onto the closed set of metrics."""
    file_type = suffix.lower().removeprefix(".")
    return f"file_type_{file_type if file_type in FILE_TYPES else 'other'}"


class UsageStats:
    """Counters in a SQLite file; a db_file of None disables them."""

    def __init__(self, db_file: Path | None, timezone: str = "UTC") -> None:
        self._db_file = db_file
        self.timezone = ZoneInfo(timezone)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._db_file.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._db_file)) as connection, connection:
            _move_monthly_hours_to_days(connection)
            connection.executescript(_CREATE_TABLES)
            yield connection

    def today(self) -> date:
        """Return the current day in the stats time zone."""
        return utc_now().astimezone(self.timezone).date()

    def check_writable(self) -> None:
        """Raise a ConfigError if counters cannot be written.

        Later write errors are only logged, so that they never break a chat.
        Without this check, a stats folder that the app user may not write to
        would show up as nothing but statistics that stay empty.
        """
        if self._db_file is None:
            return
        try:
            with self._connect() as connection:
                # Opening a read-only file works; only a write shows the problem.
                connection.execute(_ADD, ("", METRICS[0], 0))
                connection.rollback()
        except (OSError, sqlite3.Error) as error:
            raise ConfigError(
                f"usage_stats.db_file is not writable: {self._db_file} ({error}). "
                "Make its folder writable for the user that runs the app, or set "
                "usage_stats.db_file to null to disable usage statistics."
            ) from error

    def record(self, counters: Mapping[str, int]) -> None:
        """Add the counters to today's totals in one transaction.

        Messages are also added to the hour of day they arrive in. A storage
        error is logged and never breaks a chat. An unknown metric raises: it is
        a mistake in the calling code, and its name must not be stored or logged.
        """
        if not set(METRICS).issuperset(counters):
            raise ValueError("Unknown usage metric: only METRICS can be recorded")
        if self._db_file is None:
            return
        now = utc_now().astimezone(self.timezone)
        day = now.date().isoformat()
        rows = [(day, metric, value) for metric, value in counters.items() if value]
        if not rows:
            return
        try:
            with self._connect() as connection:
                connection.executemany(_ADD, rows)
                if messages := counters.get("messages"):
                    connection.execute(_ADD_MESSAGE_HOUR, (day, now.hour, messages))
        except (OSError, sqlite3.Error):
            logger.exception("usage_stats_write_failed")

    def _query(self, sql: str, parameters: tuple) -> list[tuple]:
        if self._db_file is None or not self._db_file.is_file():
            return []
        with self._connect() as connection:
            return connection.execute(sql, parameters).fetchall()

    def read(self, by: str = "month", since: str = "") -> dict[str, dict[str, int]]:
        """Return {period: {metric: value}} per month or day, from an ISO day on."""
        counters: dict[str, dict[str, int]] = {}
        for period, metric, value in self._query(_READ, (PERIOD_LENGTHS[by], since)):
            counters.setdefault(period, {})[metric] = value
        return counters

    def read_message_hours(self, since: str = "") -> dict[int, int]:
        """Return {hour of day: messages}, from an ISO day on."""
        return dict(self._query(_READ_MESSAGE_HOURS, (since,)))


def load_usage_stats() -> UsageStats:
    """Return the stats store configured under usage_stats in config.yaml."""
    config = load_config()["usage_stats"]
    db_file = config["db_file"]
    return UsageStats(PROJECT_ROOT / db_file if db_file else None, config["timezone"])
