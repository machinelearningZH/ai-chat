import os
import time
from pathlib import Path

import pytest

from ai_chat.documents import (
    ExtractionLimitError,
    extract_text_file,
    run_conversion_in_process,
)


def read_text_worker(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def slow_conversion_worker(path: str | Path) -> str:
    source = Path(path)
    source.with_suffix(".started").write_text("started", encoding="utf-8")
    time.sleep(5)
    source.with_suffix(".completed").write_text("completed", encoding="utf-8")
    return "too late"


def crashing_conversion_worker(path: str | Path) -> str:
    os._exit(42)


def test_extract_text_file_enforces_byte_ceiling(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("0123456789", encoding="utf-8")

    assert extract_text_file(source, max_output_bytes=10) == "0123456789"

    with pytest.raises(ExtractionLimitError) as error:
        extract_text_file(source, max_output_bytes=5)

    assert error.value.extracted_bytes == 6


def test_conversion_process_returns_result(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")

    result = run_conversion_in_process(
        read_text_worker,
        source,
        timeout_seconds=5,
        kill_grace_seconds=0.5,
    )

    assert result == "content"


def test_conversion_timeout_terminates_worker(tmp_path: Path) -> None:
    source = tmp_path / "slow.txt"
    source.write_text("content", encoding="utf-8")

    with pytest.raises(TimeoutError, match="timed out"):
        run_conversion_in_process(
            slow_conversion_worker,
            source,
            timeout_seconds=0.5,
            kill_grace_seconds=0.2,
        )

    time.sleep(0.2)
    assert source.with_suffix(".started").exists()
    assert not source.with_suffix(".completed").exists()


def test_conversion_enforces_max_output_bytes_in_worker(tmp_path: Path) -> None:
    source = tmp_path / "large.txt"
    source.write_text("0123456789", encoding="utf-8")

    with pytest.raises(ExtractionLimitError) as error:
        run_conversion_in_process(
            read_text_worker,
            source,
            timeout_seconds=5,
            kill_grace_seconds=0.5,
            max_output_bytes=5,
        )

    assert error.value.extracted_bytes == 10


def test_conversion_reports_real_exit_code_when_worker_crashes(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")

    with pytest.raises(RuntimeError, match="exited with code 42"):
        run_conversion_in_process(
            crashing_conversion_worker,
            source,
            timeout_seconds=5,
            kill_grace_seconds=0.5,
        )
