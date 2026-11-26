import json
import logging
import sys

import pytest

from ai_chat.config import (
    ConfigError,
    JSONFormatter,
    apply_environment_overrides,
    default_model_context_length,
    get_custom_logger,
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
            "document_conversion_timeout_seconds": 120,
            "document_conversion_kill_grace_seconds": 5,
        },
        "uploads": {
            "allowed_extensions": [".txt", ".pdf", ".docx"],
            "max_file_bytes": 20_971_520,
            "max_extracted_text_bytes": 2_097_152,
            "max_files_per_chat": 30,
            "max_aggregate_upload_bytes_per_chat": 52_428_800,
        },
        "logging": {"log_file": "test.log", "log_level": "INFO"},
        "usage_stats": {
            "db_file": "stats/usage_stats.sqlite",
            "timezone": "Europe/Zurich",
        },
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


def test_validate_config_rejects_output_and_buffer_that_exhaust_context() -> None:
    config = make_config()
    config["model"]["models"][0]["max_tokens_output"] = 3900

    with pytest.raises(ConfigError, match="max_tokens_output"):
        validate_config(config)


def test_validate_config_rejects_duplicate_model_names() -> None:
    config = make_config()
    config["model"]["models"].append(config["model"]["models"][0].copy())

    with pytest.raises(ConfigError, match="Duplicate model name"):
        validate_config(config)


def test_validate_config_rejects_template_missing_required_field() -> None:
    config = make_config()
    config["messages"]["document_item_template"] = "{filename}{content}"

    with pytest.raises(ConfigError, match="horizontal_line"):
        validate_config(config)


def test_validate_config_allows_omitting_reasoning_effort() -> None:
    config = make_config()
    config["runtime"].pop("reasoning_effort_when_thinking_disabled")

    validate_config(config)


def test_validate_config_allows_disabling_usage_stats() -> None:
    config = make_config()
    config["usage_stats"]["db_file"] = None

    validate_config(config)


def test_validate_config_allows_disabling_usage_stats_without_timezone() -> None:
    config = make_config()
    config["usage_stats"] = {"db_file": None}

    validate_config(config)


def test_load_usage_stats_config_does_not_require_api_key_or_open_log_file(
    config_file, monkeypatch, tmp_path
) -> None:
    import yaml

    from ai_chat.config import load_usage_stats_config

    log_file = tmp_path / "untouched.log"
    settings = make_config()
    settings["openai"]["base_url"] = "https://api.example.test/v1"
    settings["logging"]["log_file"] = str(log_file)
    config_file.write_text(yaml.safe_dump(settings), encoding="utf-8")
    monkeypatch.delenv("AI_CHAT_API_KEY", raising=False)

    loaded = load_usage_stats_config()

    assert loaded == settings["usage_stats"]
    assert not log_file.exists()


def test_validate_config_requires_a_decision_about_usage_stats() -> None:
    config = make_config()
    del config["usage_stats"]

    with pytest.raises(ConfigError, match="set db_file to null to disable") as error:
        validate_config(config)

    assert "usage_stats" in str(error.value)


def test_validate_config_rejects_blank_usage_stats_file() -> None:
    config = make_config()
    config["usage_stats"]["db_file"] = ""

    with pytest.raises(ConfigError, match=r"usage_stats\.db_file"):
        validate_config(config)


@pytest.mark.parametrize("timezone", ["Mars/Olympus_Mons", "", None, 2])
def test_validate_config_rejects_unknown_usage_stats_time_zone(timezone) -> None:
    config = make_config()
    config["usage_stats"]["timezone"] = timezone

    with pytest.raises(ConfigError, match=r"usage_stats\.timezone"):
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

    config["model"]["default_selection"] = "larger-model"

    assert default_model_context_length(config) == 8192


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


def test_parse_log_level_rejects_unknown_name() -> None:
    with pytest.raises(ConfigError, match="Unknown logging.log_level"):
        parse_log_level("verbose-ish")


def test_custom_logger_sends_errors_to_stderr_as_well(tmp_path, capsys) -> None:
    log_file = tmp_path / "app.log"
    logger = get_custom_logger("test_errors_to_stderr", log_file)

    try:
        logger.info("routine_event")
        logger.error("write_failed")
    finally:
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

    stderr = capsys.readouterr().err
    assert json.loads(stderr)["message"] == "write_failed"
    assert "routine_event" in log_file.read_text(encoding="utf-8")
    assert "write_failed" in log_file.read_text(encoding="utf-8")


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


def test_json_formatter_includes_exception_details() -> None:
    formatter = JSONFormatter()
    try:
        raise RuntimeError("sensitive operation failed")
    except RuntimeError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="operation failed",
        args=(),
        exc_info=exc_info,
    )

    payload = json.loads(formatter.format(record))

    assert "RuntimeError: sensitive operation failed" in payload["exception"]


@pytest.mark.parametrize("remaining_input", [0, 1])
def test_validate_config_context_boundary(remaining_input: int) -> None:
    config = make_config()
    config["model"]["models"][0]["max_tokens_context"] = 1280 + remaining_input
    if remaining_input:
        validate_config(config)
    else:
        with pytest.raises(ConfigError, match="must be smaller"):
            validate_config(config)


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "4096", None])
@pytest.mark.parametrize("key", ["max_tokens_context", "max_tokens_output"])
def test_validate_config_rejects_invalid_token_limits(key, value) -> None:
    config = make_config()
    config["model"]["models"][0][key] = value
    with pytest.raises(ConfigError, match=f"{key} must be a positive integer"):
        validate_config(config)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/v1", "http://[::1]:8000/v1"])
def test_resolve_openai_api_key_accepts_loopback_addresses(monkeypatch, url) -> None:
    config = make_config()["openai"]
    config["base_url"] = url
    monkeypatch.delenv("AI_CHAT_API_KEY", raising=False)
    assert resolve_openai_api_key(config) == "ollama"


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost.example.test/v1",
        "https://localhost@api.example.test/v1",
        "http://ollama:11434/v1",
    ],
)
def test_resolve_openai_api_key_does_not_treat_other_hosts_as_loopback(
    monkeypatch, url
) -> None:
    config = make_config()["openai"]
    config["base_url"] = url
    monkeypatch.delenv("AI_CHAT_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="AI_CHAT_API_KEY"):
        resolve_openai_api_key(config)


def test_load_config_applies_override_before_validation_and_caches(
    config_file, monkeypatch
) -> None:
    import yaml

    from ai_chat.config import load_config

    settings = make_config()
    settings["openai"]["base_url"] = "https://api.example.test/v1"
    config_file.write_text(yaml.safe_dump(settings), encoding="utf-8")
    monkeypatch.delenv("AI_CHAT_API_KEY", raising=False)
    monkeypatch.setenv("AI_CHAT_BASE_URL", "  http://127.0.0.1:8001/v1  ")
    loaded = load_config()
    assert loaded["openai"]["base_url"] == "http://127.0.0.1:8001/v1"
    assert loaded["model"]["default_selection"] == "local-model"
    config_file.unlink()
    assert load_config() == loaded


def test_load_config_can_retry_after_invalid_configuration(config_file) -> None:
    import yaml

    from ai_chat.config import load_config

    config_file.write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError, match="must contain a mapping"):
        load_config()
    config_file.write_text(yaml.safe_dump(make_config()), encoding="utf-8")
    assert load_config()["model"]["default_selection"] == "local-model"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_validate_config_rejects_non_finite_temperature_and_timeout(
    value: float,
) -> None:
    config = make_config()
    config["model"]["models"][0]["temperature"] = value
    with pytest.raises(ConfigError, match="temperature"):
        validate_config(config)

    config = make_config()
    config["openai"]["request_timeout_seconds"] = value
    with pytest.raises(ConfigError, match="request_timeout_seconds"):
        validate_config(config)


@pytest.mark.parametrize(
    ("template", "pattern"),
    [
        ("{element_name} {typo}", "unexpected template fields"),
        ("{element_name} {broken", "invalid template"),
    ],
)
def test_validate_config_rejects_unexpected_and_malformed_template_fields(
    template: str, pattern: str
) -> None:
    config = make_config()
    config["messages"]["document_limit_warning"] = template

    with pytest.raises(ConfigError, match=pattern):
        validate_config(config)


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("openai", "base_url"),
        ("logging", "log_file"),
        ("usage_stats", "db_file"),
        ("runtime", "upload_dir"),
        ("runtime", "reasoning_effort_when_thinking_disabled"),
        ("chat", "app_name"),
        ("messages", "welcome"),
    ],
)
def test_validate_config_rejects_whitespace_only_strings(
    section: str, key: str
) -> None:
    config = make_config()
    config[section][key] = "   \n  "

    with pytest.raises(ConfigError):
        validate_config(config)


def test_load_model_config_does_not_require_api_key(config_file, monkeypatch) -> None:
    import yaml

    from ai_chat.config import load_model_config

    settings = make_config()
    settings["openai"]["base_url"] = "https://api.example.test/v1"
    config_file.write_text(yaml.safe_dump(settings), encoding="utf-8")
    monkeypatch.delenv("AI_CHAT_API_KEY", raising=False)

    loaded = load_model_config()

    assert loaded["default_selection"] == "local-model"
    assert default_model_context_length({"model": loaded}) == 4096


@pytest.mark.parametrize(
    "base_url",
    [
        "file:///etc/passwd",
        "localhost:11434/v1",
        "http://",
        "http://:11434/v1",
        "ftp://example.test/v1",
    ],
)
def test_validate_config_rejects_non_http_base_url(base_url: str) -> None:
    config = make_config()
    config["openai"]["base_url"] = base_url

    with pytest.raises(ConfigError, match=r"openai\.base_url.*http://"):
        validate_config(config)


def test_parse_log_level_rejects_boolean() -> None:
    with pytest.raises(ConfigError, match="log_level"):
        parse_log_level(True)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_concurrent_document_conversions", 0),
        ("max_concurrent_document_conversions", True),
        ("document_conversion_timeout_seconds", 0),
        ("document_conversion_timeout_seconds", float("inf")),
        ("document_conversion_timeout_seconds", True),
        ("document_conversion_kill_grace_seconds", -1),
        ("document_conversion_kill_grace_seconds", float("nan")),
    ],
)
def test_validate_config_rejects_invalid_conversion_runtime_settings(
    key: str, value: object
) -> None:
    config = make_config()
    config["runtime"][key] = value

    with pytest.raises(ConfigError, match=rf"runtime\.{key}"):
        validate_config(config)


def test_validate_config_requires_uploads_section() -> None:
    config = make_config()
    del config["uploads"]

    with pytest.raises(ConfigError, match="uploads"):
        validate_config(config)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("allowed_extensions", []),
        ("allowed_extensions", ["pdf"]),
        ("max_file_bytes", 0),
        ("max_file_bytes", True),
        ("max_extracted_text_bytes", -5),
        ("max_files_per_chat", 0),
        ("max_aggregate_upload_bytes_per_chat", 0),
    ],
)
def test_validate_config_rejects_invalid_upload_limits(key: str, value: object) -> None:
    config = make_config()
    config["uploads"][key] = value

    with pytest.raises(ConfigError, match=rf"uploads\.{key}"):
        validate_config(config)


def test_validate_config_rejects_plain_text_extension_outside_allowed_uploads() -> None:
    config = make_config()
    config["file_format_whitelist"] = [".txt", ".json"]

    with pytest.raises(ConfigError, match="file_format_whitelist"):
        validate_config(config)


def test_chainlit_config_hardening_and_upload_limits_match_app_config() -> None:
    import tomllib
    from pathlib import Path

    import yaml

    repo_root = Path(__file__).resolve().parents[2]
    chainlit_config = tomllib.loads(
        (repo_root / ".chainlit" / "config.toml").read_text(encoding="utf-8")
    )
    app_config = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))

    assert chainlit_config["project"]["session_timeout"] >= 3600
    assert chainlit_config["features"]["edit_message"] is False
    assert chainlit_config["features"]["mcp"] == {"enabled": False}

    upload_ui = chainlit_config["features"]["spontaneous_file_upload"]
    assert (
        upload_ui["max_size_mb"] * 1024 * 1024
        == app_config["uploads"]["max_file_bytes"]
    )
    accepted = {
        ext.lower() for extensions in upload_ui["accept"].values() for ext in extensions
    }
    allowed = {ext.lower() for ext in app_config["uploads"]["allowed_extensions"]}
    assert accepted == allowed
    assert app_config["openai"]["max_retries"] == 0
