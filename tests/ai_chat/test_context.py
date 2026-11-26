from pathlib import Path

import pytest

from ai_chat.context import (
    ChatUploadUsage,
    ConversationHistory,
    build_context_window,
    calculate_input_token_limit,
    normalize_attachment_name,
    resolve_attachment_suffix,
    resolve_model_name,
)


def test_conversation_history_enforces_equal_lengths() -> None:
    with pytest.raises(ValueError, match="equal length"):
        ConversationHistory(
            messages=[{"role": "system", "content": "system"}],
            token_counts=[],
        )


def test_conversation_history_initial_and_with_completed_turn_do_not_mutate() -> None:
    initial = ConversationHistory.initial("system", system_prompt_tokens=2)
    window = build_context_window(
        past_messages=initial.messages,
        past_token_counts=initial.token_counts,
        current_message={"role": "user", "content": "hello"},
        current_message_tokens=3,
        max_tokens=10,
    )

    updated = initial.with_completed_turn(window, "hi there", assistant_tokens=4)

    assert initial.messages == [{"role": "system", "content": "system"}]
    assert initial.token_counts == [2]
    assert updated.messages == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    assert updated.token_counts == [2, 3, 4]


@pytest.mark.parametrize(
    ("element_name", "disk_name", "expected"),
    [
        ("notes.md", "9f43c2", ".md"),
        ("analysis.Rmd", "9f43c2.bin", ".rmd"),
        ("script.py", "9f43c2.txt", ".py"),
        ("data.CSV", "9f43c2.xls", ".csv"),
        ("no_extension", "9f43c2.pdf", ".pdf"),
        ("no_extension", "9f43c2", ""),
    ],
)
def test_resolve_attachment_suffix_prefers_uploaded_filename(
    element_name: str, disk_name: str, expected: str
) -> None:
    assert resolve_attachment_suffix(element_name, Path(disk_name)) == expected


def test_chat_upload_usage_starts_at_zero() -> None:
    assert ChatUploadUsage() == ChatUploadUsage(files=0, uploaded_bytes=0)


def test_calculate_input_token_limit_and_helpers_work_without_chainlit() -> None:
    assert calculate_input_token_limit(10_000, 2_000, 500) == 7_500
    assert normalize_attachment_name("../dir/a\nb.txt") == "a b.txt"
    assert resolve_model_name("other", {"a"}, "a") == "a"
