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
from threading import Lock
from zoneinfo import ZoneInfo

from ai_chat.config import (
    PROJECT_ROOT,
    ConfigError,
    get_custom_logger,
    load_usage_stats_config,
)

FILE_TYPES = (
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "csv",
    "txt",
    "md",
    "html",
    "py",
    "r",
    "rmd",
    "other",
)

FILE_TYPE_ALIASES = {
    "markdown": "md",
    "mdown": "md",
    "mkd": "md",
    "htm": "html",
}

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

# Create both tables together under an immediate write lock so a first report
# cannot see half the schema and concurrent writers queue on busy_timeout.
_CREATE_TABLES = """
    BEGIN IMMEDIATE;
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
    COMMIT;
"""
_ADD = """
    INSERT INTO counters (day, metric, value) VALUES (?, ?, ?)
    ON CONFLICT (day, metric) DO UPDATE SET value = value + excluded.value
"""
_ADD_MESSAGE_HOUR = """
    INSERT INTO message_hours (day, hour, messages) VALUES (?, ?, ?)
    ON CONFLICT (day, hour) DO UPDATE SET messages = messages + excluded.messages
"""
_READ_DAYS = """
    SELECT day, metric, value FROM counters WHERE day >= ?
"""
_READ_MESSAGE_HOURS = """
    SELECT hour, SUM(messages) FROM message_hours
    WHERE day >= ? GROUP BY hour
"""


def utc_now() -> datetime:
    return datetime.now(UTC)


def file_type_metric(suffix: str) -> str:
    """Map a user-controlled file extension onto the closed set of metrics."""
    file_type = suffix.lower().removeprefix(".")
    file_type = FILE_TYPE_ALIASES.get(file_type, file_type)
    return f"file_type_{file_type if file_type in FILE_TYPES else 'other'}"


class UsageStats:
    """Counters in a SQLite file; a db_file of None disables them."""

    def __init__(self, db_file: Path | None, timezone: str = "UTC") -> None:
        self._db_file = db_file
        self.timezone = ZoneInfo(timezone)
        self._schema_ready = False
        self._init_lock = Lock()

    @property
    def enabled(self) -> bool:
        """Return whether usage statistics storage is enabled."""
        return self._db_file is not None

    def _needs_schema_init(self) -> bool:
        assert self._db_file is not None
        return (
            not self._schema_ready
            or not self._db_file.is_file()
            or self._db_file.stat().st_size == 0
        )

    @contextmanager
    def _connect_write(self) -> Iterator[sqlite3.Connection]:
        assert self._db_file is not None
        self._db_file.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._db_file)) as connection:
            if self._needs_schema_init():
                with self._init_lock:
                    if self._needs_schema_init():
                        connection.execute("PRAGMA journal_mode=WAL")
                        connection.executescript(_CREATE_TABLES)
                        self._schema_ready = True
            with connection:
                yield connection

    def _has_readable_db(self) -> bool:
        return (
            self._db_file is not None
            and self._db_file.is_file()
            and self._db_file.stat().st_size > 0
        )

    def _read_snapshot_from_uri(
        self, uri: str, since: str
    ) -> tuple[dict[str, dict[str, int]], dict[int, int]]:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("BEGIN")
            days: dict[str, dict[str, int]] = {}
            for day, metric, value in connection.execute(_READ_DAYS, (since,)):
                days.setdefault(day, {})[metric] = value
            hours = dict(connection.execute(_READ_MESSAGE_HOURS, (since,)))
        return days, hours

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
            with self._connect_write() as connection:
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
            with self._connect_write() as connection:
                connection.executemany(_ADD, rows)
                if messages := counters.get("messages"):
                    connection.execute(_ADD_MESSAGE_HOUR, (day, now.hour, messages))
        except (OSError, sqlite3.Error):
            get_custom_logger().exception("usage_stats_write_failed")

    def read_snapshot(
        self, since: str = ""
    ) -> tuple[dict[str, dict[str, int]], dict[int, int]]:
        """Return daily counters and message hours from one read-only snapshot."""
        if not self._has_readable_db():
            return {}, {}
        assert self._db_file is not None
        resolved = self._db_file.resolve()
        try:
            return self._read_snapshot_from_uri(f"{resolved.as_uri()}?mode=ro", since)
        except sqlite3.OperationalError:
            # Reading a WAL database from a read-only directory fails because
            # SQLite cannot create the -shm file. Fall back to immutable=1 only
            # when no uncheckpointed WAL data exists.
            wal_path = Path(f"{resolved}-wal")
            if wal_path.exists() and wal_path.stat().st_size > 0:
                raise
            return self._read_snapshot_from_uri(
                f"{resolved.as_uri()}?mode=ro&immutable=1", since
            )


def load_usage_stats() -> UsageStats:
    """Return the stats store configured under usage_stats in config.yaml."""
    config = load_usage_stats_config()
    db_file = config["db_file"]
    timezone = config.get("timezone") or "UTC"
    return UsageStats(PROJECT_ROOT / db_file if db_file else None, timezone)
