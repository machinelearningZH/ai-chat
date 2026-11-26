import json
import logging
import math
import os
from pathlib import Path
from string import Formatter
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    level = logging.getLevelNamesMapping().get(value.upper())
    if level is not None:
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


def _require_non_empty_str(mapping: dict, key: str, label: str | None = None) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label or key} must be a non-empty string")
    return value


def _require_positive_int(config: dict, key: str, label: str | None = None) -> int:
    value = config.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{label or key} must be a positive integer")
    return value


def _require_extensions(mapping: dict, key: str, label: str | None = None) -> list[str]:
    target = label or key
    extensions = mapping.get(key)
    if not isinstance(extensions, list) or not extensions:
        raise ConfigError(f"{target} must be a non-empty list")
    if any(
        not isinstance(extension, str)
        or not extension.startswith(".")
        or len(extension) < 2
        or extension != extension.strip()
        for extension in extensions
    ):
        raise ConfigError(f"{target} entries must be file extensions")
    return extensions


def _require_finite_number(
    mapping: dict, key: str, label: str, *, allow_zero: bool = False
) -> int | float:
    value = mapping.get(key)
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or (value < 0 if allow_zero else value <= 0)
    ):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ConfigError(f"{label} must be a finite {qualifier} number")
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
        if (
            isinstance(model_config, dict)
            and model_config.get("name") == default_selection
        ):
            return _require_positive_int(model_config, "max_tokens_context")
    raise ConfigError("model.default_selection must match a configured model name")


def _template_fields(key: str, template: str) -> set[str]:
    try:
        return {
            field_name
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name is not None
        }
    except ValueError as error:
        raise ConfigError(f"messages.{key} is an invalid template: {error}") from error


def validate_model_config(config: dict) -> dict:
    """Validate and return the model section of config.yaml."""
    if not isinstance(config, dict):
        raise ConfigError("config.yaml must contain a mapping")
    model = _require_mapping(config, "model")
    models = model.get("models")
    if not isinstance(models, list) or not models:
        raise ConfigError("model.models must contain at least one model")

    model_names: set[str] = set()
    for index, model_config in enumerate(models):
        if not isinstance(model_config, dict):
            raise ConfigError(f"model.models[{index}] must be a mapping")
        name = _require_non_empty_str(
            model_config, "name", f"model.models[{index}].name"
        )
        if name in model_names:
            raise ConfigError(f"Duplicate model name: {name}")
        model_names.add(name)
        _require_positive_int(
            model_config,
            "max_tokens_context",
            f"model.models[{index}].max_tokens_context",
        )
        _require_positive_int(
            model_config,
            "max_tokens_output",
            f"model.models[{index}].max_tokens_output",
        )
        _require_finite_number(
            model_config, "temperature", f"model {name} temperature", allow_zero=True
        )

    default_selection = model.get("default_selection")
    if default_selection not in model_names:
        raise ConfigError("model.default_selection must match a configured model name")
    return model


def validate_usage_stats_config(config: dict) -> dict:
    """Validate and return the usage_stats section of config.yaml."""
    if not isinstance(config, dict):
        raise ConfigError("config.yaml must contain a mapping")
    # Required on purpose: whether usage is counted has to be a stated decision,
    # not the side effect of a config file written before the setting existed.
    if "usage_stats" not in config:
        raise ConfigError(
            "usage_stats is missing in config.yaml. Add it with db_file and "
            "timezone, or set db_file to null to disable usage statistics"
        )
    usage_stats = _require_mapping(config, "usage_stats")
    db_file = usage_stats.get("db_file")
    if db_file is not None and (not isinstance(db_file, str) or not db_file.strip()):
        raise ConfigError("usage_stats.db_file must be a non-empty string or null")
    timezone = usage_stats.get("timezone")
    if db_file is not None or timezone is not None:
        try:
            ZoneInfo(timezone)
        except (TypeError, ValueError, ZoneInfoNotFoundError) as error:
            raise ConfigError(
                "usage_stats.timezone must be a time zone name such as Europe/Zurich"
            ) from error
    return usage_stats


def validate_config(config: dict) -> None:
    """Validate runtime configuration once at startup."""
    if not isinstance(config, dict):
        raise ConfigError("config.yaml must contain a mapping")

    model = validate_model_config(config)
    context_token_buffer = _require_positive_int(config, "context_token_buffer")
    for model_config in model["models"]:
        if (
            model_config["max_tokens_output"] + context_token_buffer
            >= model_config["max_tokens_context"]
        ):
            raise ConfigError(
                f"model {model_config['name']} max_tokens_output plus "
                "context_token_buffer must be smaller than max_tokens_context"
            )

    openai_config = _require_mapping(config, "openai")
    base_url = _require_non_empty_str(openai_config, "base_url", "openai.base_url")
    parsed_base_url = urlparse(base_url)
    if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.hostname:
        raise ConfigError("openai.base_url must use http:// or https://")
    _require_finite_number(
        openai_config, "request_timeout_seconds", "openai.request_timeout_seconds"
    )
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
    _require_non_empty_str(logging_config, "log_file", "logging.log_file")

    validate_usage_stats_config(config)

    runtime = _require_mapping(config, "runtime")
    for key in ("tiktoken_cache_dir", "token_encoding", "upload_dir"):
        _require_non_empty_str(runtime, key, f"runtime.{key}")
    _require_positive_int(
        runtime,
        "max_concurrent_document_conversions",
        "runtime.max_concurrent_document_conversions",
    )
    for key in (
        "document_conversion_timeout_seconds",
        "document_conversion_kill_grace_seconds",
    ):
        _require_finite_number(runtime, key, f"runtime.{key}")
    reasoning_effort = runtime.get("reasoning_effort_when_thinking_disabled")
    if reasoning_effort is not None and (
        not isinstance(reasoning_effort, str) or not reasoning_effort.strip()
    ):
        raise ConfigError(
            "runtime.reasoning_effort_when_thinking_disabled must be a non-empty "
            "string or null"
        )

    uploads = _require_mapping(config, "uploads")
    allowed_extensions = {
        extension.lower()
        for extension in _require_extensions(
            uploads, "allowed_extensions", "uploads.allowed_extensions"
        )
    }
    for key in (
        "max_file_bytes",
        "max_extracted_text_bytes",
        "max_files_per_chat",
        "max_aggregate_upload_bytes_per_chat",
    ):
        _require_positive_int(uploads, key, f"uploads.{key}")

    chat = _require_mapping(config, "chat")
    _require_non_empty_str(chat, "app_name", "chat.app_name")

    messages = _require_mapping(config, "messages")
    missing_messages = REQUIRED_MESSAGE_KEYS - set(messages)
    if missing_messages:
        missing = ", ".join(sorted(missing_messages))
        raise ConfigError(f"messages is missing required keys: {missing}")
    for key in REQUIRED_MESSAGE_KEYS:
        _require_non_empty_str(messages, key, f"messages.{key}")
    for key, required_fields in REQUIRED_TEMPLATE_FIELDS.items():
        fields = _template_fields(key, messages[key])
        missing_fields = required_fields - fields
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ConfigError(f"messages.{key} is missing template fields: {missing}")
        unexpected_fields = fields - required_fields
        if unexpected_fields:
            unexpected = ", ".join(sorted(unexpected_fields))
            raise ConfigError(
                f"messages.{key} has unexpected template fields: {unexpected}"
            )

    whitelist = _require_extensions(config, "file_format_whitelist")
    if not {extension.lower() for extension in whitelist} <= allowed_extensions:
        raise ConfigError(
            "file_format_whitelist entries must be included in uploads.allowed_extensions"
        )


def _read_raw_config() -> dict:
    config_path = PROJECT_ROOT / "config.yaml"
    with config_path.open(encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def load_config() -> dict:
    """Load and cache the repository's config.yaml file."""
    global _config_cache
    if _config_cache is None:
        load_dotenv(PROJECT_ROOT / ".env")
        loaded_config = _read_raw_config()
        apply_environment_overrides(loaded_config)
        validate_config(loaded_config)
        _config_cache = loaded_config
    return _config_cache


def load_model_config() -> dict:
    """Load and validate only the model section from config.yaml.

    Avoids requiring API keys when Makefile helpers read the default model
    name or context length.
    """
    if _config_cache is not None:
        return _config_cache["model"]
    return validate_model_config(_read_raw_config())


def load_usage_stats_config() -> dict:
    """Load and validate only usage_stats from config.yaml.

    Avoids requiring API keys or opening the application log file when reading
    reports from the CLI.
    """
    if _config_cache is not None:
        return _config_cache["usage_stats"]
    return validate_usage_stats_config(_read_raw_config())


def get_custom_logger(
    name: str = "chainlit_logger", log_file: str | Path | None = None
) -> logging.Logger:
    """Return the application's structured logger.

    Everything goes to the log file. Errors also go to stderr, so that they show
    up in the container logs and not only in a file inside the container.
    """
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

        error_handler = logging.StreamHandler()
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        logger.addHandler(error_handler)
        logger.propagate = False

    return logger
