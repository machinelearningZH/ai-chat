import os
from datetime import date

import pytest

from ai_chat.config import ConfigError
from ai_chat.usage_stats import UsageStats, file_type_metric


def test_record_sums_counters_per_day(seeded_stats) -> None:
    seeded_stats.record({"messages": 1, "uploaded_bytes": 2048})

    assert seeded_stats.read(by="day") == {
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
    assert stats.read() != {}
    assert all("documents_failed" not in counters for counters in stats.read().values())


def test_read_sums_days_into_months(seeded_stats) -> None:
    assert seeded_stats.read(by="month") == {
        "2026-10": {"messages": 3},
        "2026-11": {"messages": 4},
    }


def test_read_ignores_days_before_since(seeded_stats) -> None:
    assert seeded_stats.read(by="month", since="2026-10-20") == {
        "2026-10": {"messages": 2},
        "2026-11": {"messages": 4},
    }


def test_record_adds_messages_to_the_hour_of_day_profile(seeded_stats) -> None:
    seeded_stats.record({"chats": 1})

    assert seeded_stats.read_message_hours() == {9: 3, 14: 4}


def test_read_message_hours_ignores_days_before_since(seeded_stats) -> None:
    assert seeded_stats.read_message_hours(since="2026-10-20") == {9: 2, 14: 4}
    assert seeded_stats.read_message_hours(since="2026-10-21") == {14: 4}


def test_record_uses_the_configured_time_zone(tmp_path, set_clock) -> None:
    stats = UsageStats(tmp_path / "usage.sqlite", "Europe/Zurich")
    set_clock(2026, 10, 31, 23, 30)

    stats.record({"messages": 1})

    assert stats.today() == date(2026, 11, 1)
    assert stats.read(by="day") == {"2026-11-01": {"messages": 1}}
    assert stats.read_message_hours() == {0: 1}


def test_record_rejects_metrics_outside_the_closed_set(tmp_path) -> None:
    stats = UsageStats(tmp_path / "usage.sqlite")

    with pytest.raises(ValueError, match="Unknown usage metric") as error:
        stats.record({"messages": 1, "text typed by a user": 1})

    assert "text typed by a user" not in str(error.value)
    assert stats.read() == {}


def test_disabled_stats_store_nothing() -> None:
    stats = UsageStats(None)

    stats.check_writable()
    stats.record({"messages": 1})

    assert stats.read() == {}
    assert stats.read_message_hours() == {}


def test_read_does_not_create_a_missing_stats_file(tmp_path) -> None:
    db_file = tmp_path / "usage.sqlite"

    assert UsageStats(db_file).read() == {}
    assert not db_file.exists()


def test_record_does_not_raise_when_storage_fails(tmp_path) -> None:
    not_a_directory = tmp_path / "file"
    not_a_directory.write_text("", encoding="utf-8")
    stats = UsageStats(not_a_directory / "usage.sqlite")

    stats.record({"messages": 1})

    assert stats.read() == {}


def test_check_writable_accepts_a_new_stats_file_without_counting(tmp_path) -> None:
    stats = UsageStats(tmp_path / "stats" / "usage.sqlite")

    stats.check_writable()

    assert stats.read() == {}


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
        (".secret-project-name", "file_type_other"),
        ("", "file_type_other"),
    ],
)
def test_file_type_metric_maps_extensions_to_closed_set(
    suffix: str, expected: str
) -> None:
    assert file_type_metric(suffix) == expected
