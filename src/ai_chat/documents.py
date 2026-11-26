"""Document text extraction with process isolation, timeouts, and output caps."""

import multiprocessing
from collections.abc import Callable
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path

import pymupdf


class ExtractionLimitError(ValueError):
    """Raised when extracted output exceeds the configured byte ceiling."""

    def __init__(self, extracted_bytes: int) -> None:
        self.extracted_bytes = extracted_bytes
        super().__init__(f"Extracted output exceeds limit ({extracted_bytes} bytes)")


def extract_text_file(path: str | Path, *, max_output_bytes: int | None = None) -> str:
    """Read a UTF-8 text file, bounding bytes read when a ceiling is configured."""
    file_path = Path(path)
    if max_output_bytes is None:
        return file_path.read_text(encoding="utf-8")

    with file_path.open("rb") as handle:
        raw = handle.read(max_output_bytes + 1)
    if len(raw) > max_output_bytes:
        raise ExtractionLimitError(len(raw))
    return raw.decode("utf-8")


def extract_text_pymupdf(path: str | Path) -> str:
    """Extract selectable text from a PDF using PyMuPDF."""
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text("text") for page in doc).strip()


def extract_with_docling(path: str | Path) -> str:
    """Convert an Office or HTML document to Markdown using Docling."""
    from docling.document_converter import DocumentConverter

    doc_result = DocumentConverter().convert(path)
    return doc_result.document.export_to_markdown()


def _stop_process(process: BaseProcess, kill_grace_seconds: float) -> None:
    if process.is_alive():
        process.terminate()
        process.join(kill_grace_seconds)
        if process.is_alive():
            process.kill()
            process.join()


def _conversion_worker(
    converter: Callable[[str | Path], str],
    path: str,
    connection: Connection,
    max_output_bytes: int | None,
) -> None:
    try:
        output = converter(path)
        if max_output_bytes is not None:
            output_bytes = len(output.encode("utf-8"))
            if output_bytes > max_output_bytes:
                connection.send(("too_large", output_bytes))
                return
        connection.send(("ok", output))
    except Exception as error:  # noqa: BLE001
        # Report converter exceptions to the parent across the process boundary.
        connection.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


def run_conversion_in_process(
    converter: Callable[[str | Path], str],
    path: str | Path,
    *,
    timeout_seconds: float,
    kill_grace_seconds: float,
    max_output_bytes: int | None = None,
) -> str:
    """Run one conversion in a spawned process that can be killed on timeout.

    When ``max_output_bytes`` is set, oversized extracted payloads are rejected
    inside the worker before pickling across the pipe.
    """
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_conversion_worker,
        args=(converter, str(path), send_connection, max_output_bytes),
        name="document-converter",
    )
    try:
        process.start()
        # Close the parent's copy of the write end so worker crashes surface as
        # immediate EOF on poll() instead of blocking until timeout_seconds.
        send_connection.close()
        if not receive_connection.poll(timeout_seconds):
            _stop_process(process, kill_grace_seconds)
            raise TimeoutError(
                f"Document conversion timed out after {timeout_seconds}s"
            )

        try:
            status, payload = receive_connection.recv()
        except EOFError as error:
            process.join(kill_grace_seconds)
            raise RuntimeError(
                f"Document conversion process exited with code {process.exitcode}"
            ) from error

        process.join(kill_grace_seconds)
        if process.is_alive():
            _stop_process(process, kill_grace_seconds)
            raise RuntimeError("Document conversion process did not exit cleanly")
        if status == "too_large":
            raise ExtractionLimitError(int(payload))
        if status != "ok":
            raise RuntimeError(str(payload))
        return str(payload)
    finally:
        receive_connection.close()
        send_connection.close()
        _stop_process(process, kill_grace_seconds)
        process.close()
