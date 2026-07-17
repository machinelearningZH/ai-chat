import asyncio
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from threading import local

import chainlit as cl
import fitz
import tiktoken
from chainlit.input_widget import Select, Switch
from openai import AsyncOpenAI, OpenAIError

from ai_chat.config import (
    ANALYTICS_LEVEL,
    PROJECT_ROOT,
    get_custom_logger,
    load_config,
    resolve_openai_api_key,
)
from ai_chat.messages import (
    CONTEXT_TRIMMED,
    DOCUMENT_ERROR_TEMPLATE,
    DOCUMENT_FAILURE,
    DOCUMENT_ITEM_TEMPLATE,
    DOCUMENT_LIMIT_WARNING,
    DOCUMENT_PARTIAL_SUCCESS,
    DOCUMENT_PROCESSING_STATUS,
    DOCUMENT_PROCESSING_TEMPLATE,
    DOCUMENT_SUCCESS,
    HORIZONTAL_LINE,
    LLM_ERROR,
    MESSAGE_TOO_LARGE,
    SYSTEM_PROMPT,
    WELCOME,
)

logger = get_custom_logger()
config = load_config()
runtime_config = config["runtime"]

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

local_client = AsyncOpenAI(
    base_url=config["openai"]["base_url"],
    api_key=resolve_openai_api_key(config["openai"]),
    timeout=config["openai"]["request_timeout_seconds"],
    max_retries=config["openai"]["max_retries"],
)

_UPLOAD_DIR = (PROJECT_ROOT / runtime_config["upload_dir"]).resolve()
_docling_state = local()
_document_conversion_slots = asyncio.Semaphore(
    runtime_config["max_concurrent_document_conversions"]
)


@dataclass(frozen=True)
class ContextWindow:
    messages: list[dict[str, str]]
    token_counts: list[int]
    was_trimmed: bool
    current_message_fits: bool


@dataclass(frozen=True)
class DocumentBudgetDecision:
    include: bool
    next_tokens: int


@dataclass(frozen=True)
class AttachmentProcessingResult:
    prompt_content: str
    processed_count: int
    failed_count: int
    skipped_count: int
    file_types: list[str]
    token_counts: list[int]


def count_tokens(text: str) -> int:
    return len(enc.encode(text))


def calculate_input_token_limit(
    max_tokens_context: int,
    max_tokens_output: int,
    context_token_buffer: int,
) -> int:
    """Reserve both output capacity and estimation overhead from context."""
    return max_tokens_context - max_tokens_output - context_token_buffer


def normalize_attachment_name(name: str | None) -> str:
    """Keep uploaded filenames as one-line labels, not prompt structure."""
    filename = Path(name or "unknown").name
    normalized = " ".join(filename.splitlines()).strip()
    return normalized or "unknown"


def resolve_model_name(
    selected_model: str,
    available_models: set[str] | None = None,
    default_model: str = DEFAULT_MODEL,
) -> str:
    """Resolve client-provided model settings to an allowed model name."""
    allowed = available_models if available_models is not None else set(MODELS_CONFIG)
    return selected_model if selected_model in allowed else default_model


def budget_document_tokens(
    current_tokens: int, candidate_tokens: int, max_tokens: int
) -> DocumentBudgetDecision:
    next_tokens = current_tokens + candidate_tokens
    if next_tokens > max_tokens:
        return DocumentBudgetDecision(include=False, next_tokens=current_tokens)
    return DocumentBudgetDecision(include=True, next_tokens=next_tokens)


def build_context_window(
    past_messages: list[dict[str, str]],
    past_token_counts: list[int],
    current_message: dict[str, str],
    current_message_tokens: int,
    max_tokens: int,
) -> ContextWindow:
    """Trim complete old turns while retaining the system prompt and current turn."""
    if len(past_messages) != len(past_token_counts):
        raise ValueError("past_messages and past_token_counts must have equal length")

    messages = [*past_messages, current_message]
    token_counts = [*past_token_counts, current_message_tokens]
    total_tokens = sum(token_counts)
    was_trimmed = False

    while total_tokens > max_tokens and len(messages) > 2:
        next_user_index = next(
            (
                index
                for index in range(2, len(messages))
                if messages[index].get("role") == "user"
            ),
            len(messages) - 1,
        )
        removed_counts = token_counts[1:next_user_index]
        if not removed_counts:
            break
        total_tokens -= sum(removed_counts)
        del messages[1:next_user_index]
        del token_counts[1:next_user_index]
        was_trimmed = True

    return ContextWindow(
        messages=messages,
        token_counts=token_counts,
        was_trimmed=was_trimmed,
        current_message_fits=total_tokens <= max_tokens,
    )


def default_analytics() -> dict:
    return {
        "user_message_count": 0,
        "user_total_tokens": 0,
        "user_token_count": [],
        "attached_doc_count": 0,
        "attached_doc_types": [],
        "attached_doc_token_count": [],
        "failed_doc_count": 0,
        "skipped_doc_count": 0,
    }


def extract_text_pymupdf(path: str | Path) -> str:
    with fitz.open(path) as doc:
        return "\n".join(page.get_text("text") for page in doc).strip()


async def convert_pdf_to_text(path: str | Path) -> str:
    async with _document_conversion_slots:
        return await asyncio.to_thread(extract_text_pymupdf, path)


def get_docling_converter():
    converter = getattr(_docling_state, "converter", None)
    if converter is None:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        _docling_state.converter = converter
    return converter


def extract_with_docling(file_path: str | Path) -> str:
    doc_result = get_docling_converter().convert(file_path)
    return doc_result.document.export_to_markdown()


async def convert_with_docling(path: str | Path) -> str:
    async with _document_conversion_slots:
        return await asyncio.to_thread(extract_with_docling, path)


async def process_attachments(
    elements: list,
    max_tokens: int,
) -> AttachmentProcessingResult:
    """Convert safe uploaded files and return per-file processing outcomes."""
    processing_msg = cl.Message(content=DOCUMENT_PROCESSING_STATUS)
    await processing_msg.send()

    attached_docs: list[str] = []
    token_count = 0
    processed_count = 0
    failed_count = 0
    skipped_count = 0
    file_types: list[str] = []
    document_token_counts: list[int] = []

    for element in elements:
        element_path = getattr(element, "path", None)
        if not element_path:
            skipped_count += 1
            continue

        upload_path = Path(element_path)
        element_name = normalize_attachment_name(getattr(element, "name", None))
        try:
            file_path = upload_path.resolve(strict=True)
            file_path.relative_to(_UPLOAD_DIR)
        except (OSError, RuntimeError, ValueError):
            logger.warning("attachment_outside_upload_directory")
            skipped_count += 1
            continue

        suffix = file_path.suffix.lower()
        try:
            if suffix in FILE_FORMAT_WHITELIST:
                result = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
            elif suffix == ".pdf":
                result = await convert_pdf_to_text(file_path)
                if not result.strip():
                    raise RuntimeError("PyMuPDF returned empty content")
            else:
                result = await convert_with_docling(file_path)
                if not result.strip():
                    raise RuntimeError("Docling returned empty content")

            document_item = DOCUMENT_ITEM_TEMPLATE.format(
                horizontal_line=HORIZONTAL_LINE,
                filename=element_name,
                content=result,
            )
            candidate_tokens = await asyncio.to_thread(count_tokens, document_item)
            budget_decision = budget_document_tokens(
                token_count, candidate_tokens, max_tokens
            )
            if not budget_decision.include:
                await cl.Message(
                    content=DOCUMENT_LIMIT_WARNING.format(element_name=element_name)
                ).send()
                skipped_count += 1
                continue

            token_count = budget_decision.next_tokens
            attached_docs.append(document_item)
            processed_count += 1
            file_types.append(suffix or "unknown")
            document_token_counts.append(candidate_tokens)
        except Exception:
            logger.exception("attachment_processing_failed")
            attached_docs.append(DOCUMENT_ERROR_TEMPLATE.format(filename=element_name))
            failed_count += 1
        finally:
            try:
                upload_path.unlink()
            except OSError:
                logger.exception("attachment_cleanup_failed")

    if processed_count and not (failed_count or skipped_count):
        processing_msg.content = DOCUMENT_SUCCESS
    elif processed_count:
        processing_msg.content = DOCUMENT_PARTIAL_SUCCESS
    else:
        processing_msg.content = DOCUMENT_FAILURE
    await processing_msg.update()

    return AttachmentProcessingResult(
        prompt_content="".join(attached_docs),
        processed_count=processed_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        file_types=file_types,
        token_counts=document_token_counts,
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
    cl.user_session.set("past_content", [{"role": "system", "content": SYSTEM_PROMPT}])
    cl.user_session.set("past_content_token_counts", [count_tokens(SYSTEM_PROMPT)])
    cl.user_session.set("thinking", False)
    cl.user_session.set("analytics", default_analytics())
    set_session_model_settings(DEFAULT_MODEL)

    elements = [
        cl.Text(name=config["chat"]["app_name"], content=WELCOME, display="inline")
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
    user_message_content = message.content
    elements = message.elements or []
    past_content = cl.user_session.get("past_content") or [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    past_content_token_counts = cl.user_session.get("past_content_token_counts")
    if not past_content_token_counts or len(past_content_token_counts) != len(
        past_content
    ):
        past_content_token_counts = await asyncio.gather(
            *(asyncio.to_thread(count_tokens, item["content"]) for item in past_content)
        )
    analytics = cl.user_session.get("analytics") or default_analytics()
    max_tokens = cl.user_session.get(
        "max_tokens",
        calculate_input_token_limit(
            DEFAULT_MODEL_CONFIG["max_tokens_context"],
            DEFAULT_MODEL_CONFIG["max_tokens_output"],
            config["context_token_buffer"],
        ),
    )

    if elements:
        empty_document_prompt = DOCUMENT_PROCESSING_TEMPLATE.format(
            instructions=message.content,
            documents="",
            horizontal_line=HORIZONTAL_LINE,
        )
        prompt_overhead_tokens = await asyncio.to_thread(
            count_tokens, f"{SYSTEM_PROMPT}{empty_document_prompt}"
        )
        attachment_budget = max(
            0,
            max_tokens - prompt_overhead_tokens,
        )
        attachment_result = await process_attachments(elements, attachment_budget)
        user_message_content = DOCUMENT_PROCESSING_TEMPLATE.format(
            instructions=message.content,
            documents=attachment_result.prompt_content,
            horizontal_line=HORIZONTAL_LINE,
        )
        analytics["attached_doc_count"] += attachment_result.processed_count
        analytics["failed_doc_count"] += attachment_result.failed_count
        analytics["skipped_doc_count"] += attachment_result.skipped_count
        analytics["attached_doc_token_count"].extend(attachment_result.token_counts)
        analytics["attached_doc_types"].extend(attachment_result.file_types)

    user_token_count = await asyncio.to_thread(count_tokens, message.content)
    analytics["user_message_count"] += 1
    analytics["user_total_tokens"] += user_token_count
    analytics["user_token_count"].append(user_token_count)

    current_message = {"role": "user", "content": user_message_content}
    current_message_tokens = await asyncio.to_thread(count_tokens, user_message_content)
    context_window = build_context_window(
        past_messages=past_content,
        past_token_counts=past_content_token_counts,
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
        await cl.Message(content=CONTEXT_TRIMMED).send()

    if not context_window.current_message_fits:
        await cl.Message(content=MESSAGE_TOO_LARGE).send()
        cl.user_session.set("analytics", analytics)
        return

    past_content = context_window.messages
    past_content_token_counts = context_window.token_counts
    msg = cl.Message(content="")
    await msg.send()

    selected_model = resolve_model_name(
        cl.user_session.get("selected_model", DEFAULT_MODEL)
    )
    request_kwargs = {
        "messages": past_content,
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

    try:
        stream = await local_client.chat.completions.create(**request_kwargs)
        async for part in stream:
            if not part.choices:
                continue
            if token := part.choices[0].delta.content or "":
                await msg.stream_token(token)
    except OpenAIError:
        logger.exception("llm_request_failed")
        msg.content = LLM_ERROR
        await msg.update()
        cl.user_session.set("analytics", analytics)
        return
    except Exception:
        logger.exception("unexpected_llm_request_failed")
        msg.content = LLM_ERROR
        await msg.update()
        cl.user_session.set("analytics", analytics)
        return

    past_content.append({"role": "assistant", "content": msg.content})
    past_content_token_counts.append(await asyncio.to_thread(count_tokens, msg.content))
    cl.user_session.set("past_content", past_content)
    cl.user_session.set("past_content_token_counts", past_content_token_counts)
    cl.user_session.set("analytics", analytics)
    await msg.update()


@cl.on_chat_end
def end() -> None:
    """Log aggregate analytics when a chat session ends."""
    analytics = cl.user_session.get("analytics")
    if not analytics:
        return

    user_msg_count = analytics["user_message_count"]
    user_total_tokens = analytics["user_total_tokens"]
    user_token_counts = analytics["user_token_count"]
    avg_user_tokens = user_total_tokens / user_msg_count if user_msg_count else 0

    doc_count = analytics["attached_doc_count"]
    doc_types = analytics["attached_doc_types"]
    doc_token_counts = analytics["attached_doc_token_count"]
    total_doc_tokens = sum(doc_token_counts)
    avg_doc_tokens = total_doc_tokens / doc_count if doc_count else 0
    doc_type_counts = Counter(doc_types)

    logger.log(
        ANALYTICS_LEVEL,
        "chat_session_analytics - "
        f"user_messages={{count: {user_msg_count}, total_tokens: {user_total_tokens}, "
        f"avg_tokens_per_msg: {avg_user_tokens:.1f}, token_counts: {user_token_counts}}}, "
        f"attached_documents={{count: {doc_count}, failed: {analytics['failed_doc_count']}, "
        f"skipped: {analytics['skipped_doc_count']}, total_tokens: {total_doc_tokens}, "
        f"avg_tokens_per_doc: {avg_doc_tokens:.1f}, file_types: {dict(doc_type_counts)}, "
        f"token_counts_per_doc: {doc_token_counts}}}",
    )
