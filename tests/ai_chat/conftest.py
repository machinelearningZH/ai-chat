from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from ai_chat import usage_stats
from ai_chat.usage_stats import UsageStats


@pytest.fixture
def set_clock(monkeypatch) -> Callable[..., None]:
    """Return a function that freezes the stats clock at a UTC date and time."""

    def freeze(*moment: int) -> None:
        frozen = datetime(*moment, tzinfo=UTC)
        monkeypatch.setattr(usage_stats, "utc_now", lambda: frozen)

    return freeze


@pytest.fixture
def stats(tmp_path, set_clock) -> UsageStats:
    """Return stats with messages on two October days and one November day."""
    stats = UsageStats(tmp_path / "stats" / "usage.sqlite")
    for moment, messages in [
        ((2026, 10, 3, 9, 15), 1),
        ((2026, 10, 20, 9, 45), 2),
        ((2026, 11, 5, 14, 0), 4),
    ]:
        set_clock(*moment)
        stats.record({"messages": messages})
    return stats
