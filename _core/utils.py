import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv


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

# Define custom ANALYTICS logging level
ANALYTICS_LEVEL = 25  # Between INFO (20) and WARNING (30)
logging.addLevelName(ANALYTICS_LEVEL, "ANALYTICS")


REQUIRED_MESSAGE_KEYS = {
    "welcome",
    "system_prompt",
    "document_processing_template",
    "document_item_template",
    "document_error_template",
    "document_limit_warning",
    "document_success",
    "document_processing_status",
    "context_trimmed",
    "message_too_large",
    "llm_error",
}


def parse_log_level(value: str | int) -> int:
    """Return a logging level from config, failing loudly for typos."""
    if isinstance(value, int):
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
    """Resolve API keys from environment, allowing only local dummy keys in config."""
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
    if not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{key} must be a positive integer")
    return value


def validate_config(config: dict) -> None:
    """Validate runtime config once at startup for clear operator errors."""
    if not isinstance(config, dict):
        raise ConfigError("config.yaml must contain a mapping")

    model = _require_mapping(config, "model")
    models = model.get("models")
    if not isinstance(models, list) or not models:
        raise ConfigError("model.models must contain at least one model")

    context_token_buffer = _require_positive_int(config, "context_token_buffer")
    model_names = set()
    for index, model_config in enumerate(models):
        if not isinstance(model_config, dict):
            raise ConfigError(f"model.models[{index}] must be a mapping")
        name = model_config.get("name")
        if not isinstance(name, str) or not name:
            raise ConfigError(f"model.models[{index}].name must be a non-empty string")
        model_names.add(name)
        max_tokens_context = _require_positive_int(model_config, "max_tokens_context")
        _require_positive_int(model_config, "max_tokens_output")
        if max_tokens_context <= context_token_buffer:
            raise ConfigError(
                "context_token_buffer must be smaller than every "
                "model max_tokens_context"
            )

    default_selection = model.get("default_selection")
    if default_selection not in model_names:
        raise ConfigError("model.default_selection must match a configured model name")

    openai_config = _require_mapping(config, "openai")
    if not openai_config.get("base_url"):
        raise ConfigError("openai.base_url is required")
    resolve_openai_api_key(openai_config)

    logging_config = _require_mapping(config, "logging")
    parse_log_level(logging_config.get("log_level", "INFO"))
    if not logging_config.get("log_file"):
        raise ConfigError("logging.log_file is required")

    runtime = _require_mapping(config, "runtime")
    for key in (
        "tiktoken_cache_dir",
        "token_encoding",
        "upload_dir",
        "reasoning_effort_when_thinking_disabled",
    ):
        if not isinstance(runtime.get(key), str) or not runtime[key]:
            raise ConfigError(f"runtime.{key} must be a non-empty string")

    messages = _require_mapping(config, "messages")
    missing_messages = REQUIRED_MESSAGE_KEYS - set(messages)
    if missing_messages:
        missing = ", ".join(sorted(missing_messages))
        raise ConfigError(f"messages is missing required keys: {missing}")

    if not isinstance(config.get("file_format_whitelist"), list):
        raise ConfigError("file_format_whitelist must be a list")


def load_config() -> dict:
    """Load configuration from config.yaml file.

    Uses a singleton pattern to cache the configuration and avoid
    repeated file reads during the application lifecycle.
    """
    global _config_cache
    if _config_cache is None:
        load_dotenv()
        config_path = Path(__file__).parent.parent / "config.yaml"
        with config_path.open("r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f)
        validate_config(_config_cache)
    return _config_cache


def get_custom_logger(
    name: str = "chainlit_logger", log_file: str | Path | None = None
) -> logging.Logger:
    if log_file is None:
        config = load_config()
        log_file = config["logging"]["log_file"]
        log_level = parse_log_level(config["logging"].get("log_level", "INFO"))
    else:
        log_level = logging.INFO

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Avoid adding multiple handlers if already set
    if not logger.handlers:
        log_path = Path(log_file)
        if log_path.parent != Path("."):
            log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(JSONFormatter())

        # Add the handler to the logger
        logger.addHandler(file_handler)

        # Prevent it from propagating to the root logger (used by the framework)
        logger.propagate = False

    return logger
