import json
import logging
import os
from pathlib import Path
from string import Formatter
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    """Raised when application configuration is missing or inconsistent."""


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured application logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "timestamp": self.formatTime(record, self.datefmt),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_config_cache: dict | None = None

ANALYTICS_LEVEL = 25
logging.addLevelName(ANALYTICS_LEVEL, "ANALYTICS")


REQUIRED_MESSAGE_KEYS = {
    "welcome",
    "system_prompt",
    "document_processing_template",
    "document_item_template",
    "document_error_template",
    "document_limit_warning",
    "document_success",
    "document_partial_success",
    "document_failure",
    "document_processing_status",
    "context_trimmed",
    "message_too_large",
    "llm_error",
}

REQUIRED_TEMPLATE_FIELDS = {
    "document_processing_template": {"instructions", "documents", "horizontal_line"},
    "document_item_template": {"horizontal_line", "filename", "content"},
    "document_error_template": {"filename"},
    "document_limit_warning": {"element_name"},
}


def parse_log_level(value: str | int) -> int:
    """Return a logging level from config, failing loudly for typos."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if not isinstance(value, str):
        raise ConfigError("logging.log_level must be a string or integer")
    level = logging.getLevelName(value.upper())
    if isinstance(level, int):
        return level
    raise ConfigError(f"Unknown logging.log_level: {value}")


def _is_local_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def resolve_openai_api_key(openai_config: dict) -> str:
    """Resolve API keys from the environment, with local dummy-key support."""
    env_name = openai_config.get("api_key_env")
    if env_name:
        api_key = os.environ.get(env_name)
        if api_key:
            return api_key

    base_url = openai_config.get("base_url", "")
    if _is_local_base_url(base_url):
        local_api_key = openai_config.get("local_api_key")
        if local_api_key:
            return local_api_key

    if env_name:
        raise ConfigError(f"Set {env_name} in the environment or .env")
    raise ConfigError("openai.api_key_env is required for non-local OpenAI endpoints")


def _require_mapping(config: dict, key: str) -> dict:
    value = config.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a mapping")
    return value


def _require_positive_int(config: dict, key: str) -> int:
    value = config.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{key} must be a positive integer")
    return value


def apply_environment_overrides(config: dict) -> None:
    """Apply deployment-specific settings without duplicating config files."""
    if not isinstance(config, dict):
        raise ConfigError("config.yaml must contain a mapping")
    base_url = os.environ.get("AI_CHAT_BASE_URL")
    if base_url is None:
        return
    base_url = base_url.strip()
    if not base_url:
        raise ConfigError("AI_CHAT_BASE_URL must not be blank")
    _require_mapping(config, "openai")["base_url"] = base_url


def default_model_context_length(config: dict) -> int:
    """Return the configured context length for the default model."""
    model = _require_mapping(config, "model")
    default_selection = model.get("default_selection")
    models = model.get("models", [])
    for model_config in models:
        if model_config.get("name") == default_selection:
            return _require_positive_int(model_config, "max_tokens_context")
    raise ConfigError("model.default_selection must match a configured model name")


def _template_fields(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name is not None
    }


def validate_config(config: dict) -> None:
    """Validate runtime configuration once at startup."""
    if not isinstance(config, dict):
        raise ConfigError("config.yaml must contain a mapping")

    model = _require_mapping(config, "model")
    models = model.get("models")
    if not isinstance(models, list) or not models:
        raise ConfigError("model.models must contain at least one model")

    context_token_buffer = _require_positive_int(config, "context_token_buffer")
    model_names: set[str] = set()
    for index, model_config in enumerate(models):
        if not isinstance(model_config, dict):
            raise ConfigError(f"model.models[{index}] must be a mapping")
        name = model_config.get("name")
        if not isinstance(name, str) or not name:
            raise ConfigError(f"model.models[{index}].name must be a non-empty string")
        if name in model_names:
            raise ConfigError(f"Duplicate model name: {name}")
        model_names.add(name)

        max_tokens_context = _require_positive_int(model_config, "max_tokens_context")
        max_tokens_output = _require_positive_int(model_config, "max_tokens_output")
        if max_tokens_output + context_token_buffer >= max_tokens_context:
            raise ConfigError(
                f"model {name} max_tokens_output plus context_token_buffer "
                "must be smaller than max_tokens_context"
            )
        temperature = model_config.get("temperature")
        if (
            not isinstance(temperature, int | float)
            or isinstance(temperature, bool)
            or temperature < 0
        ):
            raise ConfigError(f"model {name} temperature must be a non-negative number")

    default_selection = model.get("default_selection")
    if default_selection not in model_names:
        raise ConfigError("model.default_selection must match a configured model name")

    openai_config = _require_mapping(config, "openai")
    if (
        not isinstance(openai_config.get("base_url"), str)
        or not openai_config["base_url"]
    ):
        raise ConfigError("openai.base_url is required")
    timeout = openai_config.get("request_timeout_seconds")
    if (
        not isinstance(timeout, int | float)
        or isinstance(timeout, bool)
        or timeout <= 0
    ):
        raise ConfigError("openai.request_timeout_seconds must be a positive number")
    max_retries = openai_config.get("max_retries")
    if (
        not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or max_retries < 0
    ):
        raise ConfigError("openai.max_retries must be a non-negative integer")
    resolve_openai_api_key(openai_config)

    logging_config = _require_mapping(config, "logging")
    parse_log_level(logging_config.get("log_level", "INFO"))
    if (
        not isinstance(logging_config.get("log_file"), str)
        or not logging_config["log_file"]
    ):
        raise ConfigError("logging.log_file must be a non-empty string")

    runtime = _require_mapping(config, "runtime")
    for key in ("tiktoken_cache_dir", "token_encoding", "upload_dir"):
        if not isinstance(runtime.get(key), str) or not runtime[key]:
            raise ConfigError(f"runtime.{key} must be a non-empty string")
    _require_positive_int(runtime, "max_concurrent_document_conversions")
    reasoning_effort = runtime.get("reasoning_effort_when_thinking_disabled")
    if reasoning_effort is not None and (
        not isinstance(reasoning_effort, str) or not reasoning_effort
    ):
        raise ConfigError(
            "runtime.reasoning_effort_when_thinking_disabled must be a non-empty "
            "string or null"
        )

    chat = _require_mapping(config, "chat")
    if not isinstance(chat.get("app_name"), str) or not chat["app_name"]:
        raise ConfigError("chat.app_name must be a non-empty string")

    messages = _require_mapping(config, "messages")
    missing_messages = REQUIRED_MESSAGE_KEYS - set(messages)
    if missing_messages:
        missing = ", ".join(sorted(missing_messages))
        raise ConfigError(f"messages is missing required keys: {missing}")
    for key in REQUIRED_MESSAGE_KEYS:
        if not isinstance(messages[key], str) or not messages[key]:
            raise ConfigError(f"messages.{key} must be a non-empty string")
    for key, required_fields in REQUIRED_TEMPLATE_FIELDS.items():
        missing_fields = required_fields - _template_fields(messages[key])
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ConfigError(f"messages.{key} is missing template fields: {missing}")

    whitelist = config.get("file_format_whitelist")
    if not isinstance(whitelist, list) or not whitelist:
        raise ConfigError("file_format_whitelist must be a non-empty list")
    if any(
        not isinstance(extension, str) or not extension.startswith(".")
        for extension in whitelist
    ):
        raise ConfigError("file_format_whitelist entries must be file extensions")


def load_config() -> dict:
    """Load and cache the repository's config.yaml file."""
    global _config_cache
    if _config_cache is None:
        load_dotenv(PROJECT_ROOT / ".env")
        config_path = PROJECT_ROOT / "config.yaml"
        with config_path.open(encoding="utf-8") as config_file:
            loaded_config = yaml.safe_load(config_file)
        apply_environment_overrides(loaded_config)
        validate_config(loaded_config)
        _config_cache = loaded_config
    return _config_cache


def get_custom_logger(
    name: str = "chainlit_logger", log_file: str | Path | None = None
) -> logging.Logger:
    """Return the application's structured file logger."""
    if log_file is None:
        config = load_config()
        log_file = config["logging"]["log_file"]
        log_level = parse_log_level(config["logging"].get("log_level", "INFO"))
    else:
        log_level = logging.INFO

    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    if not logger.handlers:
        log_path = Path(log_file)
        if not log_path.is_absolute():
            log_path = PROJECT_ROOT / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
        logger.propagate = False

    return logger
