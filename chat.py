from pathlib import Path
from collections import Counter
import os
import chainlit as cl
from chainlit.input_widget import Select
from openai import AsyncOpenAI
from docling.document_converter import DocumentConverter
import tiktoken
from _core.utils import get_custom_logger, load_config
from _core.constants import (
    WELCOME,
    SYSTEM_PROMPT,
    HORIZONTAL_LINE,
    DOCUMENT_PROCESSING_TEMPLATE,
    DOCUMENT_ITEM_TEMPLATE,
    DOCUMENT_LIMIT_WARNING,
    DOCUMENT_SUCCESS,
    DOCUMENT_PROCESSING_STATUS,
    DOCUMENT_ERROR_TEMPLATE,
    CONTEXT_TRIMMED,
)

logger = get_custom_logger()
config = load_config()

# Set environment variable for tiktoken cache directory to make sure it uses the local cache.
# Otherwise, tiktoken may not work on airgapped environments.
# See also this issue: https://github.com/openai/tiktoken/issues/317
os.environ["TIKTOKEN_CACHE_DIR"] = "./_tiktoken_cache"
enc = tiktoken.get_encoding("cl100k_base")
logger.debug(f"Loaded tiktoken encoding: {enc.name}")
logger.debug(f"Tiktoken test: {enc.encode('Hello, world!')}")


# Build model configuration dictionary
MODELS_CONFIG = {model["name"]: model for model in config["model"]["models"]}
DEFAULT_MODEL = config["model"]["default_selection"]
AVAILABLE_MODELS = [model["name"] for model in config["model"]["models"]]

FILE_FORMAT_WHITELIST = config["file_format_whitelist"]

local_client = AsyncOpenAI(
    base_url=config["openai"]["base_url"], api_key=config["openai"]["api_key"]
)

# Initialize Docling converter
docling_converter = DocumentConverter()


async def process_attachments(elements):
    """Process uploaded files, convert them to markdown, and update the UI status message.

    Args:
        elements: List of Chainlit attachment elements to process.

    Returns:
        A markdown string aggregating all processed documents. Empty string if none valid.
    """
    processing_msg = cl.Message(content=DOCUMENT_PROCESSING_STATUS)
    await processing_msg.send()

    attached_docs = ""
    token_count = 0

    for element in elements:
        if hasattr(element, "path") and element.path:
            file_path = Path(element.path)

            # Validate that file_path is within .files/ folder (anchored to project root)
            project_root = Path(__file__).parent.resolve()
            allowed_dir = project_root / ".files"
            try:
                file_path.resolve().relative_to(allowed_dir)
            except ValueError:
                logger.warning(f"File {file_path} is not in .files/ folder. Skipping.")
                continue

            try:
                if file_path.suffix in FILE_FORMAT_WHITELIST:
                    with open(file_path) as f:
                        result = f.read()
                else:
                    result = docling_converter.convert(element.path)
                    result = result.document.export_to_markdown()

                # Check token limit before adding document to attached_docs
                token_count += len(enc.encode(result))
                if token_count >= cl.user_session.get(
                    "max_tokens", config["default_ollama_max_tokens"]
                ):
                    token_limit_message = cl.Message(
                        content=DOCUMENT_LIMIT_WARNING.format(element_name=element.name)
                    )
                    await token_limit_message.send()
                    continue

                attached_docs += DOCUMENT_ITEM_TEMPLATE.format(
                    horizontal_line=HORIZONTAL_LINE,
                    filename=element.name,
                    content=result,
                )
            except Exception as e:
                attached_docs += DOCUMENT_ERROR_TEMPLATE.format(
                    filename=element.name, error=str(e)
                )

            # Clean up the temporary file that Chainlit created.
            try:
                Path(element.path).unlink()
            except OSError as e:
                logger.error(f"Error removing file {element.path}: {str(e)}")

    processing_msg.content = DOCUMENT_SUCCESS
    await processing_msg.update()
    return attached_docs


def set_session_model_settings(selected_model: str) -> None:
    """Set user session token and word limits for the selected model."""
    model_config = MODELS_CONFIG.get(selected_model, MODELS_CONFIG[DEFAULT_MODEL])
    # Subtract buffer from max tokens to leave room for response
    max_tokens = model_config["max_tokens_context"] - config["context_token_buffer"]
    cl.user_session.set("max_tokens", max_tokens)
    cl.user_session.set("temperature", model_config["temperature"])
    cl.user_session.set("max_tokens_output", model_config["max_tokens_output"])


@cl.on_settings_update
async def setup_agent(settings):
    cl.user_session.set("selected_model", settings["model"])
    # Set max tokens and words in user session based on model selection.
    set_session_model_settings(settings["model"])


@cl.on_chat_start
async def on_chat_start():
    logger.info("chat_initiated")

    # Initialize conversation with system prompt
    cl.user_session.set("past_content", [{"role": "system", "content": SYSTEM_PROMPT}])
    cl.user_session.set("selected_model", DEFAULT_MODEL)

    # Initialize analytics tracking
    cl.user_session.set(
        "analytics",
        {
            "user_message_count": 0,
            "user_total_tokens": 0,
            "user_token_count": [],
            "attached_doc_count": 0,
            "attached_doc_types": [],
            "attached_doc_token_count": [],
        },
    )

    # Set max tokens and words in user session based on model selection.
    set_session_model_settings(DEFAULT_MODEL)

    elements = [
        cl.Text(name=config["chat"]["app_name"], content=WELCOME, display="inline")
    ]

    await cl.Message(
        content="",
        elements=elements,
    ).send()

    await cl.ChatSettings(
        [
            Select(
                id="model",
                label="LLM Model",
                values=AVAILABLE_MODELS,
                initial_value=DEFAULT_MODEL,
            ),
        ]
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    user_message_content = message.content
    elements = message.elements or []
    past_content = cl.user_session.get("past_content")
    analytics = cl.user_session.get("analytics")

    # Process any attached files
    attached_docs = ""
    if elements:
        attached_docs = await process_attachments(elements)
        user_message_content = DOCUMENT_PROCESSING_TEMPLATE.format(
            instructions=message.content,
            documents=attached_docs,
            horizontal_line=HORIZONTAL_LINE,
        )

    # Track attached documents analytics
    doc_token_count = len(enc.encode(attached_docs))
    analytics["attached_doc_count"] += len(elements)
    analytics["attached_doc_token_count"].append(doc_token_count)

    # Track file types
    for element in elements:
        if hasattr(element, "path") and element.path:
            file_type = Path(element.path).suffix or "unknown"
            analytics["attached_doc_types"].append(file_type)

    # Track user message analytics
    user_token_count = len(enc.encode(message.content))
    analytics["user_message_count"] += 1
    analytics["user_total_tokens"] += user_token_count
    analytics["user_token_count"].append(user_token_count)

    past_content.append({"role": "user", "content": user_message_content})

    # Trim past content if exceeding max tokens
    max_tokens = cl.user_session.get("max_tokens", config["default_ollama_max_tokens"])
    current_tokens = sum(len(enc.encode(msg["content"])) for msg in past_content)
    logger.debug(
        f"Current tokens in past content: {current_tokens}, Max tokens allowed: {max_tokens}"
    )
    if current_tokens > max_tokens:
        logger.info(
            "Past content exceeded max tokens. Trimming oldest messages to fit within context window."
        )
        # Notify user about context trimming
        msg = cl.Message(content=CONTEXT_TRIMMED)
        await msg.send()

        # Trim oldest messages until within token limit
        while current_tokens > max_tokens and len(past_content) > 1:
            # We set the index to 1 to avoid removing the system prompt at index 0.
            current_tokens -= len(enc.encode(past_content[1]["content"]))
            del past_content[1]

    msg = cl.Message(content="")
    await msg.send()

    # Create streaming completion
    stream = await local_client.chat.completions.create(
        messages=past_content,  # type: ignore[arg-type]
        stream=True,
        model=cl.user_session.get("selected_model", DEFAULT_MODEL),
        max_tokens=cl.user_session.get(
            "max_tokens_output", config["default_max_tokens_output"]
        ),
        temperature=cl.user_session.get("temperature", config["default_temperature"]),
    )

    # Stream the response
    async for part in stream:
        if token := part.choices[0].delta.content or "":
            await msg.stream_token(token)

    past_content.append({"role": "assistant", "content": msg.content})
    cl.user_session.set("past_content", past_content)
    await msg.update()


@cl.on_chat_end
async def end() -> None:
    """Log detailed analytics when chat session ends."""
    analytics = cl.user_session.get("analytics")
    if analytics is None:
        logger.warning("Analytics not available at chat end")
        return

    # Calculate user message statistics
    user_msg_count = analytics["user_message_count"]
    user_total_tokens = analytics["user_total_tokens"]
    user_token_counts = analytics["user_token_count"]
    avg_user_tokens = user_total_tokens / user_msg_count if user_msg_count > 0 else 0

    # Calculate document statistics
    doc_count = analytics["attached_doc_count"]
    doc_types = analytics["attached_doc_types"]
    doc_token_counts = analytics["attached_doc_token_count"]
    total_doc_tokens = sum(doc_token_counts)
    avg_doc_tokens = total_doc_tokens / doc_count if doc_count > 0 else 0
    doc_type_counts = Counter(doc_types) if doc_types else {}

    # Log all analytics in a single event
    logger.analytics(
        f"chat_session_analytics - "
        f"user_messages={{count: {user_msg_count}, total_tokens: {user_total_tokens}, "
        f"avg_tokens_per_msg: {avg_user_tokens:.1f}, token_counts: {user_token_counts}}}, "
        f"attached_documents={{count: {doc_count}, total_tokens: {total_doc_tokens}, "
        f"avg_tokens_per_doc: {avg_doc_tokens:.1f}, file_types: {dict(doc_type_counts)}, "
        f"token_counts_per_doc: {doc_token_counts}}}"
    )
