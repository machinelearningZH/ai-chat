# Maintenance notes

## Chat handling and document imports

- Serialize turns per Chainlit session with a session-scoped `asyncio.Lock` so
  overlapping messages cannot interleave or overwrite conversation history.
- Keep session history in a single `ConversationHistory` object (in
  `src/ai_chat/context.py`) so messages and token counts cannot drift, and
  commit completed turns atomically so errors or cancellations never leave a
  dangling user turn.
- Keep `features.edit_message` disabled in `.chainlit/config.toml` because
  transient `ConversationHistory` is not rewound when editing past UI messages.
  Keep `project.session_timeout` at least one hour (`3600`) so brief WebSocket
  disconnects or sleep do not discard transient chat state.
- Defer sending the assistant message bubble until the first streamed token (or
  error) arrives so pressing Stop before the first token does not leave an empty
  bubble behind. Start `response_stream_ms` on the first non-whitespace token.
- Run PDF and Docling conversions in `spawn`ed subprocesses
  (`src/ai_chat/documents.py`) bounded by a loop-scoped `asyncio.Semaphore`
  sized to `runtime.max_concurrent_document_conversions`, with configurable
  `document_conversion_timeout_seconds`, `document_conversion_kill_grace_seconds`,
  and worker-side `uploads.max_extracted_text_bytes` enforcement before pickling
  back across the pipe.
- Dispatch attachment handling and file-type stats from the original uploaded
  filename suffix before falling back to Chainlit's saved disk path, because
  Chainlit derives stored temp extensions from browser-reported MIME types.
- Validate uploaded paths off the event loop (resolved inside
  `runtime.upload_dir` and regular files only), enforce server-side `uploads`
  limits (`allowed_extensions`, `max_file_bytes`, `max_extracted_text_bytes`,
  and per-chat file/byte quotas in `ChatUploadUsage`) without letting rejected
  files consume remaining chat quota, and clean up all validated uploads in an
  outer `finally` block so cancelled conversions do not leave files behind.
  Budget failed-document placeholders against the attachment token limit so
  import failures cannot push the turn over `max_tokens`.

## Configuration and tooling

- `load_model_config()` and `load_usage_stats_config()` validate only their own
  section of `config.yaml` so Makefile helpers and the CLI usage report run
  without model credentials or creating the application log file.
- `validate_config()` rejects blank strings, non-`http(s)` `openai.base_url`
  values, non-finite timeouts and temperatures, invalid `uploads` limits, and
  missing, unexpected, or malformed template fields in `messages` at startup.
- Keep `openai.max_retries` at `0` by default for local model servers so slow or
  OOM requests do not stall across retries; deployments using remote gateways
  can raise it in `config.yaml`.
- Keep `uploads.allowed_extensions`, `uploads.max_file_bytes`, and
  `file_format_whitelist` aligned with `.chainlit/config.toml` so plain-text
  Markdown and code files read directly as UTF-8 instead of falling through to
  Docling.
- Keep `[features.mcp]` free of pre-2.12.0 subsections in
  `.chainlit/config.toml`.

## Usage statistics

- Count a chat on its first message. Chainlit can reuse the session after a
  reconnect, so counting disconnects would inflate chat totals. Chat-length
  counters record when each threshold is reached, which can fall on a later
  day than the first message.
- Count the message before requesting a reply. A stopped reply contributes to
  “Not answered” without adding a completed reply or model error. The report
  measures streaming speed from the first non-whitespace reply text to the end
  of the stream.
- The app checks write access at import because Chainlit can continue serving
  after a startup hook fails. Later storage errors are logged so the chat can
  continue.
- SQLite uses WAL mode with locked one-time schema initialization wrapped in
  `BEGIN IMMEDIATE; ... COMMIT;` so concurrent readers never observe half the
  schema and concurrent writers queue on `busy_timeout`. The report reads daily
  rows directly in one read-only snapshot without model keys, marks partial
  first months with `from YYYY-MM-DD` when `--since` starts mid-month, and when
  a read-only directory blocks WAL `-shm` creation, falls back to `immutable=1`
  only if no non-empty `-wal` file is present.
