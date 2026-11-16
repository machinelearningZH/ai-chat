from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


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
