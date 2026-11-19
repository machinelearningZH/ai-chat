"""Isolate import-time app configuration from developer credentials and files."""

import logging
import socket
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from ai_chat import config


def pytest_configure(config: pytest.Config) -> None:
    from ai_chat import config as app_config

    patch = pytest.MonkeyPatch()
    sandbox = TemporaryDirectory(prefix="ai-chat-tests-")
    root = Path(sandbox.name)
    config.add_cleanup(sandbox.cleanup)
    config.add_cleanup(patch.undo)
    original_root = app_config.PROJECT_ROOT
    settings = yaml.safe_load((original_root / "config.yaml").read_text())
    settings["runtime"]["tiktoken_cache_dir"] = str(original_root / "_tiktoken_cache")
    settings["logging"]["log_file"] = str(root / "test.log")
    (root / "config.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    (root / ".chainlit").mkdir()
    (root / ".chainlit" / "config.toml").write_text(
        (original_root / ".chainlit" / "config.toml").read_text(), encoding="utf-8"
    )
    patch.setattr(app_config, "PROJECT_ROOT", root)
    patch.setenv("PYTHON_DOTENV_DISABLED", "1")
    patch.setenv("CHAINLIT_APP_ROOT", str(root))
    patch.setenv("AI_CHAT_BASE_URL", "http://localhost:11434/v1")
    patch.setenv("AI_CHAT_API_KEY", "test-dummy-key")

    def deny_connection(*args, **kwargs):
        raise AssertionError("Tests must not connect to external services")

    patch.setattr(socket.socket, "connect", deny_connection)
    patch.setattr(socket.socket, "connect_ex", deny_connection)

    def close_test_logs() -> None:
        logger = logging.getLogger("chainlit_logger")
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

    config.add_cleanup(close_test_logs)


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """Use the real YAML loader with a fresh cache and an isolated config root."""
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.delenv("AI_CHAT_BASE_URL", raising=False)
    return tmp_path / "config.yaml"
