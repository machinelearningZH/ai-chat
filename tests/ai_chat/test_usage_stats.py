import os
from contextlib import closing
from datetime import date

import pytest

from ai_chat.config import ConfigError
from ai_chat.usage_report import aggregate_periods
from ai_chat.usage_stats import UsageStats, file_type_metric


def test_record_sums_counters_per_day(seeded_stats) -> None:
    seeded_stats.record({"messages": 1, "uploaded_bytes": 2048})

    days, _ = seeded_stats.read_snapshot()
    assert days == {
        "2026-10-03": {"messages": 1},
        "2026-10-20": {"messages": 2},
        "2026-11-05": {"messages": 5, "uploaded_bytes": 2048},
    }


def test_record_leaves_out_counters_of_zero(tmp_path) -> None:
    db_file = tmp_path / "usage.sqlite"
    stats = UsageStats(db_file)

    stats.record({"documents_failed": 0})
    assert not db_file.exists()

    stats.record({"messages": 1, "documents_failed": 0})
    days, _ = stats.read_snapshot()
    assert days != {}
    assert all("documents_failed" not in counters for counters in days.values())


def test_aggregate_periods_sums_days_into_months(seeded_stats) -> None:
    days, _ = seeded_stats.read_snapshot()
    assert aggregate_periods(days, "month") == {
        "2026-10": {"messages": 3},
        "2026-11": {"messages": 4},
    }


def test_read_snapshot_ignores_days_before_since(seeded_stats) -> None:
    days, hours = seeded_stats.read_snapshot(since="2026-10-20")
    assert aggregate_periods(days, "month") == {
        "2026-10": {"messages": 2},
        "2026-11": {"messages": 4},
    }
    assert hours == {9: 2, 14: 4}
    assert seeded_stats.read_snapshot(since="2026-10-21")[1] == {14: 4}


def test_record_adds_messages_to_the_hour_of_day_profile(seeded_stats) -> None:
    seeded_stats.record({"chats": 1})

    _, hours = seeded_stats.read_snapshot()
    assert hours == {9: 3, 14: 4}


def test_record_uses_the_configured_time_zone(tmp_path, set_clock) -> None:
    stats = UsageStats(tmp_path / "usage.sqlite", "Europe/Zurich")
    set_clock(2026, 10, 31, 23, 30)

    stats.record({"messages": 1})

    assert stats.today() == date(2026, 11, 1)
    days, hours = stats.read_snapshot()
    assert days == {"2026-11-01": {"messages": 1}}
    assert hours == {0: 1}


def test_record_rejects_metrics_outside_the_closed_set(tmp_path) -> None:
    stats = UsageStats(tmp_path / "usage.sqlite")

    with pytest.raises(ValueError, match="Unknown usage metric") as error:
        stats.record({"messages": 1, "text typed by a user": 1})

    assert "text typed by a user" not in str(error.value)
    assert stats.read_snapshot() == ({}, {})


def test_disabled_stats_store_nothing() -> None:
    stats = UsageStats(None)

    stats.check_writable()
    stats.record({"messages": 1})

    assert stats.read_snapshot() == ({}, {})


def test_read_does_not_create_a_missing_stats_file(tmp_path) -> None:
    db_file = tmp_path / "usage.sqlite"

    assert UsageStats(db_file).read_snapshot() == ({}, {})
    assert not db_file.exists()


def test_record_does_not_raise_when_storage_fails(tmp_path) -> None:
    not_a_directory = tmp_path / "file"
    not_a_directory.write_text("", encoding="utf-8")
    stats = UsageStats(not_a_directory / "usage.sqlite")

    stats.record({"messages": 1})

    assert stats.read_snapshot() == ({}, {})


def test_check_writable_accepts_a_new_stats_file_without_counting(tmp_path) -> None:
    stats = UsageStats(tmp_path / "stats" / "usage.sqlite")

    stats.check_writable()

    assert stats.read_snapshot() == ({}, {})


@pytest.mark.skipif(os.geteuid() == 0, reason="root may write everywhere")
@pytest.mark.parametrize("read_only", ["folder", "file"])
def test_check_writable_rejects_a_stats_file_it_cannot_write(
    tmp_path, read_only: str
) -> None:
    folder = tmp_path / "stats"
    stats = UsageStats(folder / "usage.sqlite")
    stats.record({"messages": 1})
    blocked = folder if read_only == "folder" else folder / "usage.sqlite"
    blocked.chmod(0o555 if read_only == "folder" else 0o444)

    try:
        with pytest.raises(ConfigError, match=r"usage_stats\.db_file is not writable"):
            stats.check_writable()
    finally:
        blocked.chmod(0o755)


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        (".pdf", "file_type_pdf"),
        (".DOCX", "file_type_docx"),
        (".py", "file_type_py"),
        (".R", "file_type_r"),
        (".Rmd", "file_type_rmd"),
        (".html", "file_type_html"),
        (".HTM", "file_type_html"),
        (".markdown", "file_type_md"),
        (".mdown", "file_type_md"),
        (".mkd", "file_type_md"),
        (".secret-project-name", "file_type_other"),
        ("", "file_type_other"),
    ],
)
def test_file_type_metric_maps_extensions_to_closed_set(
    suffix: str, expected: str
) -> None:
    assert file_type_metric(suffix) == expected


def test_usage_stats_module_does_not_initialize_logger_at_import() -> None:
    from ai_chat import usage_stats

    assert "logger" not in vars(usage_stats)


def test_usage_stats_enables_wal_and_supports_concurrent_writes_and_reads(
    tmp_path,
) -> None:
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor

    db_file = tmp_path / "usage.sqlite"
    stats = UsageStats(db_file)
    stats.check_writable()

    with closing(sqlite3.connect(db_file)) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal_mode.lower() == "wal"

    def write_batch(_index: int) -> None:
        for _ in range(10):
            stats.record({"messages": 1})

    def read_batch(_index: int) -> None:
        for _ in range(10):
            stats.read_snapshot()

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [
            *(pool.submit(write_batch, i) for i in range(8)),
            *(pool.submit(read_batch, i) for i in range(4)),
        ]
        for future in futures:
            future.result()

    days, hours = stats.read_snapshot()
    assert sum(counters["messages"] for counters in days.values()) == 80
    assert sum(hours.values()) == 80


@pytest.mark.skipif(os.geteuid() == 0, reason="root may write everywhere")
def test_read_snapshot_reads_empty_and_readonly_files_without_writing(
    tmp_path, seeded_stats
) -> None:
    empty_file = tmp_path / "empty.sqlite"
    empty_file.touch()
    empty_file.chmod(0o444)
    try:
        assert UsageStats(empty_file).read_snapshot() == ({}, {})
    finally:
        empty_file.chmod(0o644)

    db_file = seeded_stats._db_file
    db_file.chmod(0o444)
    try:
        days, hours = seeded_stats.read_snapshot(since="2026-10-20")
    finally:
        db_file.chmod(0o644)

    assert days == {"2026-10-20": {"messages": 2}, "2026-11-05": {"messages": 4}}
    assert hours == {9: 2, 14: 4}


@pytest.mark.skipif(os.geteuid() == 0, reason="root may write everywhere")
def test_read_snapshot_reads_wal_db_from_readonly_directory(seeded_stats) -> None:
    db_file = seeded_stats._db_file
    assert db_file is not None
    stats_dir = db_file.parent
    db_file.chmod(0o444)
    stats_dir.chmod(0o555)
    try:
        days, hours = seeded_stats.read_snapshot(since="2026-10-20")
    finally:
        stats_dir.chmod(0o755)
        db_file.chmod(0o644)

    assert days == {"2026-10-20": {"messages": 2}, "2026-11-05": {"messages": 4}}
    assert hours == {9: 2, 14: 4}


def test_record_concurrent_initial_writes_do_not_drop_counts(
    tmp_path, set_clock
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    stats = UsageStats(tmp_path / "concurrent.sqlite")
    set_clock(2026, 11, 20, 10, 0)

    def write_one(_: int) -> None:
        stats.record({"messages": 1})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write_one, range(16)))

    assert stats.read_snapshot() == ({"2026-11-20": {"messages": 16}}, {10: 16})


def test_schema_init_uses_immediate_transaction_and_direct_day_query() -> None:
    from ai_chat import usage_stats

    assert "BEGIN IMMEDIATE;" in usage_stats._CREATE_TABLES
    assert "COMMIT;" in usage_stats._CREATE_TABLES
    assert "GROUP BY" not in usage_stats._READ_DAYS
