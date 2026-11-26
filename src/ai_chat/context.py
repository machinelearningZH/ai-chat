"""Conversation history, attachment labels, and context-window budgeting."""

from dataclasses import dataclass
from pathlib import Path
from typing import Self

ChatMessage = dict[str, str]


@dataclass(frozen=True, slots=True)
class ContextWindow:
    messages: list[ChatMessage]
    token_counts: list[int]
    was_trimmed: bool
    current_message_fits: bool


@dataclass(slots=True)
class ConversationHistory:
    """In-session conversation turns paired with their token counts."""

    messages: list[ChatMessage]
    token_counts: list[int]

    def __post_init__(self) -> None:
        if len(self.messages) != len(self.token_counts):
            raise ValueError("messages and token_counts must have equal length")

    @classmethod
    def initial(cls, system_prompt: str, system_prompt_tokens: int) -> Self:
        return cls(
            messages=[{"role": "system", "content": system_prompt}],
            token_counts=[system_prompt_tokens],
        )

    def with_completed_turn(
        self,
        window: ContextWindow,
        assistant_content: str,
        assistant_tokens: int,
    ) -> Self:
        """Return a new history committing the request window and assistant reply."""
        return type(self)(
            messages=[
                *window.messages,
                {"role": "assistant", "content": assistant_content},
            ],
            token_counts=[*window.token_counts, assistant_tokens],
        )


@dataclass(slots=True)
class ChatUploadUsage:
    """Cumulative accepted upload usage tracked per chat session."""

    files: int = 0
    uploaded_bytes: int = 0


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


def resolve_attachment_suffix(element_name: str, file_path: Path) -> str:
    """Resolve the lowercase extension, preferring the original upload filename.

    Chainlit names stored files from the browser-reported MIME type, which can
    yield .bin, .txt, .xls, or extensionless temp files for formats accepted
    under generic MIME types.
    """
    return Path(element_name).suffix.lower() or file_path.suffix.lower()


def resolve_model_name(
    selected_model: str,
    available_models: set[str],
    default_model: str,
) -> str:
    """Resolve client-provided model settings to an allowed model name."""
    return selected_model if selected_model in available_models else default_model


def build_context_window(
    past_messages: list[ChatMessage],
    past_token_counts: list[int],
    current_message: ChatMessage,
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
