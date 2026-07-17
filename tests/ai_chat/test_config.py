import json
import logging

import pytest

from ai_chat.config import (
    ConfigError,
    JSONFormatter,
    apply_environment_overrides,
    default_model_context_length,
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
            "request_timeout_seconds": 600,
            "max_retries": 2,
        },
        "runtime": {
            "tiktoken_cache_dir": "./_tiktoken_cache",
            "token_encoding": "cl100k_base",
            "upload_dir": ".files",
            "reasoning_effort_when_thinking_disabled": "none",
            "max_concurrent_document_conversions": 2,
        },
        "logging": {"log_file": "test.log", "log_level": "INFO"},
        "chat": {"app_name": "AI Chat"},
        "context_token_buffer": 256,
        "file_format_whitelist": [".txt"],
        "messages": {
            "welcome": "Welcome",
            "system_prompt": "System",
            "document_processing_template": "{instructions}{documents}{horizontal_line}",
            "document_item_template": "{horizontal_line}{filename}{content}",
            "document_error_template": "{filename}",
            "document_limit_warning": "{element_name}",
            "document_success": "Success",
            "document_partial_success": "Partial success",
            "document_failure": "Failure",
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


def test_validate_config_rejects_output_and_buffer_that_exhaust_context() -> None:
    config = make_config()
    config["model"]["models"][0]["max_tokens_output"] = 3900

    with pytest.raises(ConfigError, match="max_tokens_output"):
        validate_config(config)


def test_validate_config_allows_omitting_reasoning_effort() -> None:
    config = make_config()
    config["runtime"].pop("reasoning_effort_when_thinking_disabled")

    validate_config(config)


def test_default_model_context_length_uses_default_selection() -> None:
    config = make_config()
    config["model"]["models"].append(
        {
            "name": "larger-model",
            "temperature": 0.7,
            "max_tokens_context": 8192,
            "max_tokens_output": 1024,
        }
    )

    assert default_model_context_length(config) == 4096


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


def test_environment_override_replaces_openai_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    monkeypatch.setenv("AI_CHAT_BASE_URL", "http://ollama:11434/v1")

    apply_environment_overrides(config)

    assert config["openai"]["base_url"] == "http://ollama:11434/v1"


def test_environment_override_rejects_blank_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    monkeypatch.setenv("AI_CHAT_BASE_URL", "   ")

    with pytest.raises(ConfigError, match="AI_CHAT_BASE_URL"):
        apply_environment_overrides(config)


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
