import json
import logging

import pytest

from _core.utils import (
    ConfigError,
    JSONFormatter,
    parse_log_level,
    resolve_openai_api_key,
    validate_config,
)


def make_config() -> dict:
    return {
        "model": {
            "default_selection": "local-model",
            "models": [
                {
                    "name": "local-model",
                    "temperature": 0.7,
                    "max_tokens_context": 4096,
                    "max_tokens_output": 1024,
                }
            ],
        },
        "openai": {
            "base_url": "http://localhost:11434/v1",
            "api_key_env": "AI_CHAT_API_KEY",
            "local_api_key": "ollama",
        },
        "runtime": {
            "tiktoken_cache_dir": "./_tiktoken_cache",
            "token_encoding": "cl100k_base",
            "upload_dir": ".files",
            "reasoning_effort_when_thinking_disabled": "none",
        },
        "logging": {"log_file": "test.log", "log_level": "INFO"},
        "context_token_buffer": 256,
        "default_ollama_max_tokens": 4096,
        "default_max_tokens_output": 1024,
        "default_temperature": 0.7,
        "file_format_whitelist": [".txt"],
        "messages": {
            "welcome": "Welcome",
            "system_prompt": "System",
            "document_processing_template": "{instructions}{documents}{horizontal_line}",
            "document_item_template": "{horizontal_line}{filename}{content}",
            "document_error_template": "{filename}{error}",
            "document_limit_warning": "{element_name}",
            "document_success": "Success",
            "document_processing_status": "Processing",
            "context_trimmed": "Trimmed",
            "message_too_large": "Too large",
            "llm_error": "LLM error",
        },
    }


def test_validate_config_rejects_unknown_default_model() -> None:
    config = make_config()
    config["model"]["default_selection"] = "missing"

    with pytest.raises(ConfigError, match="default_selection"):
        validate_config(config)


def test_validate_config_rejects_context_buffer_that_exhausts_model() -> None:
    config = make_config()
    config["context_token_buffer"] = 4096

    with pytest.raises(ConfigError, match="context_token_buffer"):
        validate_config(config)


def test_resolve_openai_api_key_prefers_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    monkeypatch.setenv("AI_CHAT_API_KEY", "real-key")

    assert resolve_openai_api_key(config["openai"]) == "real-key"


def test_resolve_openai_api_key_allows_local_dummy_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    monkeypatch.delenv("AI_CHAT_API_KEY", raising=False)

    assert resolve_openai_api_key(config["openai"]) == "ollama"


def test_resolve_openai_api_key_requires_env_for_non_localhost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    config["openai"]["base_url"] = "https://api.example.test/v1"
    monkeypatch.delenv("AI_CHAT_API_KEY", raising=False)

    with pytest.raises(ConfigError, match="AI_CHAT_API_KEY"):
        resolve_openai_api_key(config["openai"])


def test_parse_log_level_accepts_configured_names() -> None:
    assert parse_log_level("WARNING") == logging.WARNING


def test_json_formatter_emits_structured_log_record() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert payload["message"] == "hello"
    assert "timestamp" in payload
