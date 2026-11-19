from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_chat import usage_stats
from ai_chat.usage_stats import UsageStats


class FakeSession:
    def __init__(self, values: dict | None = None) -> None:
        self.values = values if values is not None else {}

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def set(self, key: str, value) -> None:
        self.values[key] = value


@pytest.fixture
def chat(monkeypatch):
    from ai_chat import app

    messages = []

    class Message:
        def __init__(self, content: str, **kwargs) -> None:
            self.content = content
            self.sent = []
            self.updated = []
            self.tokens = []
            messages.append(self)

        async def send(self) -> None:
            self.sent.append(self.content)

        async def update(self) -> None:
            self.updated.append(self.content)

        async def stream_token(self, token: str) -> None:
            self.tokens.append(token)
            self.content += token

    session = FakeSession()
    create = AsyncMock(side_effect=AssertionError("Unexpected model request"))
    monkeypatch.setattr(app.cl, "Message", Message)
    monkeypatch.setattr(app.cl, "user_session", session)
    monkeypatch.setattr(
        app,
        "local_client",
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    return SimpleNamespace(messages=messages, session=session, create=create)


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
