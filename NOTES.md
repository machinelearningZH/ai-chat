# Maintenance notes

## Chat handling and document imports

- Serialize turns per Chainlit session with a session-scoped `asyncio.Lock` so
  overlapping messages cannot interleave or overwrite `past_content` and its
  token counts.
- Run PDF and Docling conversions in a dedicated `ThreadPoolExecutor` sized to
  `runtime.max_concurrent_document_conversions`. Docling's `DocumentConverter`
  lives in thread-local state, so a bounded pool caps both concurrent imports
  and converter memory use.
- Validate uploaded paths upfront (resolved inside `runtime.upload_dir` and
  regular files only) before processing, and clean up all validated uploads in
  an outer `finally` block so cancelled conversions do not leave files behind.
  Budget failed-document placeholders against the attachment token limit so
  import failures cannot push the turn over `max_tokens`.

## Configuration and tooling

- `load_model_config()` and `load_usage_stats_config()` validate only their own
  section of `config.yaml` so Makefile helpers and the CLI usage report run
  without model credentials or creating the application log file.
- `validate_config()` rejects blank strings, non-finite timeouts and
  temperatures, and missing, unexpected, or malformed template fields in
  `messages` at startup.
- Keep plain-text Markdown extensions (`.md`, `.markdown`, `.mdown`, `.mkd`) in
  `file_format_whitelist` aligned with `.chainlit/config.toml` so they read
  directly as UTF-8 instead of falling through to Docling.

## Usage statistics

- Count a chat on its first message. Chainlit can reuse the session after a
  reconnect, so counting disconnects would inflate chat totals. Chat-length
  counters record when each threshold is reached, which can fall on a later
  day than the first message.
- Count the message before requesting a reply. A stopped reply contributes to
  “Not answered” without adding a completed reply or model error. The report
  measures streaming speed from the first reply text to the end of the stream.
- The app checks write access at import because Chainlit can continue serving
  after a startup hook fails. Later storage errors are logged so the chat can
  continue.
- SQLite uses WAL mode with locked one-time schema initialization. The report
  reads one read-only snapshot without model keys; when a read-only directory
  blocks WAL `-shm` creation, it falls back to `immutable=1` only if no
  non-empty `-wal` file is present.
