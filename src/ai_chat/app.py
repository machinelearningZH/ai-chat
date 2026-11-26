import asyncio
import os
import stat
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from weakref import WeakKeyDictionary

import chainlit as cl
import tiktoken
from chainlit.input_widget import Select, Switch
from openai import AsyncOpenAI, OpenAIError

from ai_chat.config import (
    PROJECT_ROOT,
    get_custom_logger,
    load_config,
    resolve_openai_api_key,
)
from ai_chat.context import (
    ChatMessage,
    ChatUploadUsage,
    ContextWindow,
    ConversationHistory,
    build_context_window,
    calculate_input_token_limit,
    normalize_attachment_name,
    resolve_attachment_suffix,
)
from ai_chat.context import (
    resolve_model_name as _resolve_model_name,
)
from ai_chat.documents import (
    ExtractionLimitError,
    extract_text_file,
    extract_text_pymupdf,
    extract_with_docling,
    run_conversion_in_process,
)
from ai_chat.usage_stats import (
    CHAT_LENGTH_METRICS,
    file_type_metric,
    load_usage_stats,
)

__all__ = [
    "AttachmentProcessingResult",
    "ChatMessage",
    "ChatUploadUsage",
    "ContextWindow",
    "ConversationHistory",
    "build_context_window",
    "calculate_input_token_limit",
    "normalize_attachment_name",
    "resolve_attachment_suffix",
    "resolve_model_name",
]

logger = get_custom_logger()
config = load_config()
stats = load_usage_stats()
# Chainlit logs an error in a startup hook and carries on, so the check runs at
# import: the app must not start if enabled usage statistics cannot be written.
stats.check_writable()
runtime_config = config["runtime"]
uploads_config = config["uploads"]

_STRIPPED_MESSAGES = {
    "welcome",
    "system_prompt",
    "document_processing_template",
    "document_item_template",
}
MESSAGES = {
    key: value.strip() if key in _STRIPPED_MESSAGES else value
    for key, value in config["messages"].items()
}
HORIZONTAL_LINE = "\n\n" + ("-" * 80) + "\n\n"

cache_dir = Path(runtime_config["tiktoken_cache_dir"])
if not cache_dir.is_absolute():
    cache_dir = PROJECT_ROOT / cache_dir
os.environ["TIKTOKEN_CACHE_DIR"] = str(cache_dir)
enc = tiktoken.get_encoding(runtime_config["token_encoding"])

MODELS_CONFIG = {model["name"]: model for model in config["model"]["models"]}
DEFAULT_MODEL = config["model"]["default_selection"]
AVAILABLE_MODELS = list(MODELS_CONFIG)
DEFAULT_MODEL_CONFIG = MODELS_CONFIG[DEFAULT_MODEL]
FILE_FORMAT_WHITELIST = {
    extension.lower() for extension in config["file_format_whitelist"]
}
ALLOWED_UPLOAD_EXTENSIONS = {
    extension.lower() for extension in uploads_config["allowed_extensions"]
}

local_client = AsyncOpenAI(
    base_url=config["openai"]["base_url"],
    api_key=resolve_openai_api_key(config["openai"]),
    timeout=config["openai"]["request_timeout_seconds"],
    max_retries=config["openai"]["max_retries"],
)

_UPLOAD_DIR = (PROJECT_ROOT / runtime_config["upload_dir"]).resolve()
_conversion_semaphores: WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Semaphore
] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class AttachmentProcessingResult:
    prompt_content: str
    processed_count: int
    failed_count: int
    skipped_count: int
    file_types: list[str]
    token_counts: list[int]
    uploaded_bytes: int
    uploaded_file_count: int = 0


def count_tokens(text: str) -> int:
    return len(enc.encode(text))


_SYSTEM_PROMPT_TOKENS = count_tokens(MESSAGES["system_prompt"])


def resolve_model_name(
    selected_model: str,
    available_models: set[str] | None = None,
    default_model: str = DEFAULT_MODEL,
) -> str:
    """Resolve client-provided model settings to an allowed model name."""
    allowed = available_models if available_models is not None else set(MODELS_CONFIG)
    return _resolve_model_name(selected_model, allowed, default_model)


def elapsed_ms(started: float, finished: float | None = None) -> int:
    end = time.perf_counter() if finished is None else finished
    return max(round((end - started) * 1000), 0)


def count_once_per_chat(usage: Counter[str], metric: str) -> None:
    """Count a chat-level metric the first time it applies."""
    counted = cl.user_session.get("counted_chat_metrics") or set()
    if metric not in counted:
        cl.user_session.set("counted_chat_metrics", counted | {metric})
        usage[metric] += 1


def count_chat_length(usage: Counter[str]) -> None:
    """Count the message, and the chat when it reaches a counted length."""
    chat_messages = cl.user_session.get("chat_messages", 0) + 1
    cl.user_session.set("chat_messages", chat_messages)
    usage["messages"] += 1
    if chat_messages in CHAT_LENGTH_METRICS:
        usage[CHAT_LENGTH_METRICS[chat_messages]] += 1


def _session_lock() -> asyncio.Lock:
    """Return a per-session lock so overlapping turns do not clobber history."""
    lock = cl.user_session.get("message_lock")
    if lock is None:
        lock = asyncio.Lock()
        cl.user_session.set("message_lock", lock)
    return lock


def _document_conversion_semaphore() -> asyncio.Semaphore:
    """Return a loop-scoped semaphore bounding concurrent document conversions."""
    loop = asyncio.get_running_loop()
    semaphore = _conversion_semaphores.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(
            runtime_config["max_concurrent_document_conversions"]
        )
        _conversion_semaphores[loop] = semaphore
    return semaphore


async def save_usage(usage: Mapping[str, int]) -> None:
    """Write the counters in one transaction, off the event loop.

    A locked stats file would otherwise stall every chat for seconds. It still
    holds up the chat that waits for the write, so an outcome is shown to the
    user, and an answer is kept in the history, before it is counted. A wrong
    metric name is a mistake in this module and must not break a chat either.
    """
    try:
        await asyncio.to_thread(stats.record, usage)
    except ValueError:
        logger.exception("usage_stats_unknown_metric")


async def run_document_conversion(
    extractor: Callable[[str | Path], str],
    path: str | Path,
    *,
    max_output_bytes: int | None = None,
) -> str:
    """Run one document converter in an isolated process under concurrency limits."""
    async with _document_conversion_semaphore():
        return await asyncio.to_thread(
            run_conversion_in_process,
            extractor,
            path,
            timeout_seconds=runtime_config["document_conversion_timeout_seconds"],
            kill_grace_seconds=runtime_config["document_conversion_kill_grace_seconds"],
            max_output_bytes=max_output_bytes,
        )


def _unlink_upload(upload_path: Path) -> None:
    try:
        upload_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("attachment_cleanup_failed")


def _prepare_uploads(
    elements: list,
) -> tuple[list[tuple[Path, Path, str, int | None]], int]:
    """Validate uploaded paths inside _UPLOAD_DIR off the event loop."""
    validated: list[tuple[Path, Path, str, int | None]] = []
    skipped = 0
    for element in elements:
        element_path = getattr(element, "path", None)
        if not element_path:
            skipped += 1
            continue

        upload_path = Path(element_path)
        element_name = normalize_attachment_name(getattr(element, "name", None))
        try:
            file_path = upload_path.resolve(strict=True)
            file_path.relative_to(_UPLOAD_DIR)
        except (OSError, RuntimeError, ValueError):
            logger.warning("attachment_outside_upload_directory")
            skipped += 1
            continue
        try:
            stat_result = file_path.stat()
        except OSError:
            validated.append((upload_path, file_path, element_name, None))
            continue
        if not stat.S_ISREG(stat_result.st_mode):
            logger.warning("attachment_not_a_regular_file")
            skipped += 1
            continue
        validated.append((upload_path, file_path, element_name, stat_result.st_size))
    return validated, skipped


async def process_attachments(
    elements: list,
    max_tokens: int,
    *,
    chat_usage: ChatUploadUsage | None = None,
) -> AttachmentProcessingResult:
    """Convert safe uploaded files and return per-file processing outcomes."""
    processing_msg = cl.Message(content=MESSAGES["document_processing_status"])
    await processing_msg.send()

    prior_usage = chat_usage if chat_usage is not None else ChatUploadUsage()
    remaining_file_slots = max(
        0, uploads_config["max_files_per_chat"] - prior_usage.files
    )
    remaining_upload_bytes = max(
        0,
        uploads_config["max_aggregate_upload_bytes_per_chat"]
        - prior_usage.uploaded_bytes,
    )
    max_file_bytes = uploads_config["max_file_bytes"]
    max_extracted_text_bytes = uploads_config["max_extracted_text_bytes"]

    attached_docs: list[str] = []
    token_count = 0
    processed_count = 0
    failed_count = 0
    file_types: list[str] = []
    document_token_counts: list[int] = []
    uploaded_file_count = 0
    uploaded_bytes = 0

    validated_uploads, skipped_count = await asyncio.to_thread(
        _prepare_uploads, elements
    )

    try:
        for upload_path, file_path, element_name, file_size in validated_uploads:
            suffix = resolve_attachment_suffix(element_name, file_path)
            try:
                if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
                    logger.warning("attachment_extension_not_allowed")
                    skipped_count += 1
                    continue

                if uploaded_file_count >= remaining_file_slots:
                    logger.warning("attachment_chat_file_limit_exceeded")
                    skipped_count += 1
                    continue

                actual_size = (
                    file_size
                    if file_size is not None
                    else (await asyncio.to_thread(file_path.stat)).st_size
                )
                if actual_size > max_file_bytes:
                    logger.warning("attachment_file_size_limit_exceeded")
                    skipped_count += 1
                    continue

                available_upload_bytes = max(0, remaining_upload_bytes - uploaded_bytes)
                if actual_size > available_upload_bytes:
                    logger.warning("attachment_chat_size_limit_exceeded")
                    skipped_count += 1
                    continue

                uploaded_file_count += 1
                uploaded_bytes += actual_size
                file_types.append(suffix or "unknown")

                if suffix in FILE_FORMAT_WHITELIST:
                    result = await asyncio.to_thread(
                        extract_text_file,
                        file_path,
                        max_output_bytes=max_extracted_text_bytes,
                    )
                elif suffix == ".pdf":
                    result = await run_document_conversion(
                        extract_text_pymupdf,
                        file_path,
                        max_output_bytes=max_extracted_text_bytes,
                    )
                    if not result.strip():
                        raise RuntimeError("PyMuPDF returned empty content")
                else:
                    result = await run_document_conversion(
                        partial(extract_with_docling, expected_extension=suffix),
                        file_path,
                        max_output_bytes=max_extracted_text_bytes,
                    )
                    if not result.strip():
                        raise RuntimeError("Docling returned empty content")

                document_item = MESSAGES["document_item_template"].format(
                    horizontal_line=HORIZONTAL_LINE,
                    filename=element_name,
                    content=result,
                )
                candidate_tokens = await asyncio.to_thread(count_tokens, document_item)
                if token_count + candidate_tokens > max_tokens:
                    await cl.Message(
                        content=MESSAGES["document_limit_warning"].format(
                            element_name=element_name
                        )
                    ).send()
                    skipped_count += 1
                    continue

                token_count += candidate_tokens
                attached_docs.append(document_item)
                processed_count += 1
                document_token_counts.append(candidate_tokens)
            except ExtractionLimitError:
                logger.warning("attachment_extracted_text_limit_exceeded")
                await cl.Message(
                    content=MESSAGES["document_limit_warning"].format(
                        element_name=element_name
                    )
                ).send()
                skipped_count += 1
            except Exception:
                logger.exception("attachment_processing_failed")
                failed_count += 1
                error_item = MESSAGES["document_error_template"].format(
                    filename=element_name
                )
                error_tokens = await asyncio.to_thread(count_tokens, error_item)
                if token_count + error_tokens <= max_tokens:
                    token_count += error_tokens
                    attached_docs.append(error_item)
            finally:
                _unlink_upload(upload_path)
    finally:
        # Clean up any remaining validated uploads if processing was cancelled.
        for upload_path, _, _, _ in validated_uploads:
            _unlink_upload(upload_path)

    if processed_count and not (failed_count or skipped_count):
        processing_msg.content = MESSAGES["document_success"]
    elif processed_count:
        processing_msg.content = MESSAGES["document_partial_success"]
    else:
        processing_msg.content = MESSAGES["document_failure"]
    await processing_msg.update()

    return AttachmentProcessingResult(
        prompt_content="".join(attached_docs),
        processed_count=processed_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        file_types=file_types,
        token_counts=document_token_counts,
        uploaded_bytes=uploaded_bytes,
        uploaded_file_count=uploaded_file_count,
    )


def set_session_model_settings(selected_model: str) -> str:
    """Validate the model and apply its token and sampling settings."""
    resolved_model = resolve_model_name(selected_model)
    if resolved_model != selected_model:
        logger.warning("invalid_model_selection")
    model_config = MODELS_CONFIG[resolved_model]
    max_tokens = calculate_input_token_limit(
        model_config["max_tokens_context"],
        model_config["max_tokens_output"],
        config["context_token_buffer"],
    )
    cl.user_session.set("selected_model", resolved_model)
    cl.user_session.set("max_tokens", max_tokens)
    cl.user_session.set("temperature", model_config["temperature"])
    cl.user_session.set("max_tokens_output", model_config["max_tokens_output"])
    return resolved_model


@cl.on_settings_update
async def setup_agent(settings: dict) -> None:
    selected_model = settings.get("model", DEFAULT_MODEL)
    set_session_model_settings(selected_model)
    cl.user_session.set("thinking", bool(settings.get("thinking", False)))


@cl.on_chat_start
async def on_chat_start() -> None:
    logger.info("chat_initiated")
    cl.user_session.set(
        "conversation_history",
        ConversationHistory.initial(MESSAGES["system_prompt"], _SYSTEM_PROMPT_TOKENS),
    )
    cl.user_session.set("upload_usage", ChatUploadUsage())
    cl.user_session.set("thinking", False)
    cl.user_session.set("chat_messages", 0)
    cl.user_session.set("counted_chat_metrics", set())
    cl.user_session.set("message_lock", asyncio.Lock())
    set_session_model_settings(DEFAULT_MODEL)

    elements = [
        cl.Text(
            name=config["chat"]["app_name"],
            content=MESSAGES["welcome"],
            display="inline",
        )
    ]
    await cl.Message(content="", elements=elements).send()
    await cl.ChatSettings(
        [
            Select(
                id="model",
                label="LLM Model",
                values=AVAILABLE_MODELS,
                initial_value=DEFAULT_MODEL,
            ),
            Switch(
                id="thinking",
                label="Thinking Mode",
                initial=False,
                tooltip="Toggle thinking mode on or off.",
                description=(
                    "Enable thinking mode for models that support it. When enabled, "
                    "the model can reason before answering."
                ),
            ),
        ]
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    async with _session_lock():
        await _handle_message(message)


async def _handle_message(message: cl.Message) -> None:
    user_message_content = message.content
    elements = message.elements or []
    history = cl.user_session.get("conversation_history")
    if not isinstance(history, ConversationHistory):
        history = ConversationHistory.initial(
            MESSAGES["system_prompt"], _SYSTEM_PROMPT_TOKENS
        )
    max_tokens = cl.user_session.get(
        "max_tokens",
        calculate_input_token_limit(
            DEFAULT_MODEL_CONFIG["max_tokens_context"],
            DEFAULT_MODEL_CONFIG["max_tokens_output"],
            config["context_token_buffer"],
        ),
    )

    usage: Counter[str] = Counter()
    if elements:
        upload_usage = cl.user_session.get("upload_usage")
        if not isinstance(upload_usage, ChatUploadUsage):
            upload_usage = ChatUploadUsage()
        empty_document_prompt = MESSAGES["document_processing_template"].format(
            instructions=message.content,
            documents="",
            horizontal_line=HORIZONTAL_LINE,
        )
        prompt_overhead_tokens = history.token_counts[0] + await asyncio.to_thread(
            count_tokens, empty_document_prompt
        )
        attachment_budget = max(0, max_tokens - prompt_overhead_tokens)
        started = time.perf_counter()
        attachment_result = await process_attachments(
            elements, attachment_budget, chat_usage=upload_usage
        )
        usage["document_ms"] += elapsed_ms(started)
        upload_usage.files += attachment_result.uploaded_file_count
        upload_usage.uploaded_bytes += attachment_result.uploaded_bytes
        cl.user_session.set("upload_usage", upload_usage)
        user_message_content = MESSAGES["document_processing_template"].format(
            instructions=message.content,
            documents=attachment_result.prompt_content,
            horizontal_line=HORIZONTAL_LINE,
        )
        usage["messages_with_documents"] += 1
        count_once_per_chat(usage, "chats_with_documents")
        usage["documents_processed"] += attachment_result.processed_count
        usage["documents_failed"] += attachment_result.failed_count
        usage["documents_skipped"] += attachment_result.skipped_count
        usage["document_tokens"] += sum(attachment_result.token_counts)
        usage["uploaded_bytes"] += attachment_result.uploaded_bytes
        usage.update(map(file_type_metric, attachment_result.file_types))

    count_chat_length(usage)
    usage["message_tokens"] += await asyncio.to_thread(count_tokens, message.content)
    if cl.user_session.get("thinking", False):
        usage["messages_with_thinking"] += 1
        count_once_per_chat(usage, "chats_with_thinking")

    current_message = {"role": "user", "content": user_message_content}
    current_message_tokens = await asyncio.to_thread(count_tokens, user_message_content)
    context_window = build_context_window(
        past_messages=history.messages,
        past_token_counts=history.token_counts,
        current_message=current_message,
        current_message_tokens=current_message_tokens,
        max_tokens=max_tokens,
    )
    logger.debug(
        "context_window_tokens=%s max_input_tokens=%s",
        sum(context_window.token_counts),
        max_tokens,
    )

    if context_window.was_trimmed:
        logger.info("context_history_trimmed")
        usage["history_trimmed"] += 1
        await cl.Message(content=MESSAGES["context_trimmed"]).send()

    if not context_window.current_message_fits:
        usage["message_too_large"] += 1
        await cl.Message(content=MESSAGES["message_too_large"]).send()
        await save_usage(usage)
        return

    # The message is counted now: its answer can take minutes, fail or be stopped.
    await save_usage(usage)
    msg = cl.Message(content="")
    message_sent = False

    selected_model = resolve_model_name(
        cl.user_session.get("selected_model", DEFAULT_MODEL)
    )
    request_kwargs = {
        "messages": context_window.messages,
        "stream": True,
        "model": selected_model,
        "max_tokens": cl.user_session.get(
            "max_tokens_output", DEFAULT_MODEL_CONFIG["max_tokens_output"]
        ),
        "temperature": cl.user_session.get(
            "temperature", DEFAULT_MODEL_CONFIG["temperature"]
        ),
    }
    reasoning_effort = runtime_config.get("reasoning_effort_when_thinking_disabled")
    if not cl.user_session.get("thinking", False) and reasoning_effort:
        request_kwargs["reasoning_effort"] = reasoning_effort

    started = time.perf_counter()
    # Until the first answer token, the model server queues, reads the prompt and
    # thinks. Only the time after it measures how fast the answer is generated.
    stream_started: float | None = None
    try:
        stream = await local_client.chat.completions.create(**request_kwargs)
        async for part in stream:
            if not part.choices:
                continue
            if token := part.choices[0].delta.content or "":
                if token.strip() and stream_started is None:
                    stream_started = time.perf_counter()
                if not message_sent:
                    await msg.send()
                    message_sent = True
                await msg.stream_token(token)
    except Exception as error:
        event = (
            "llm_request_failed"
            if isinstance(error, OpenAIError)
            else "unexpected_llm_request_failed"
        )
        logger.exception(event)
        msg.content = MESSAGES["llm_error"]
        if message_sent:
            await msg.update()
        else:
            await msg.send()
        await save_usage({"llm_errors": 1})
        return

    finished = time.perf_counter()
    if not message_sent:
        await msg.send()
    response_ms = elapsed_ms(started, finished)
    response_stream_ms = (
        elapsed_ms(stream_started, finished) if stream_started is not None else 0
    )
    response_tokens = await asyncio.to_thread(count_tokens, msg.content)
    cl.user_session.set(
        "conversation_history",
        history.with_completed_turn(context_window, msg.content, response_tokens),
    )
    await msg.update()
    await save_usage(
        {
            "responses": 1,
            "response_ms": response_ms,
            "response_stream_ms": response_stream_ms,
            "response_tokens": response_tokens,
        }
    )
