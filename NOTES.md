# Test-suite audit

## Scope and baseline

Reviewed all Python application modules and both existing test modules, repository
instructions, README/configuration contracts, pytest settings, Makefile, and CI.
This is not an exhaustive deployment, security, or dependency audit.

Pytest uses its standard `test_*.py` discovery with `src` on `pythonpath`.
CI runs `uv sync --locked`, `uv run ruff format --check .`,
`uv run ruff check .`, and `uv run pytest`, followed by Compose validation,
image build, and container health checks. There were no explicit test exclusions,
skips, xfails, or async pytest tests whose bodies were never awaited.
Baseline: 30 passed, six third-party deprecation warnings.

The inherited virtual environment referenced a missing interpreter. `uv sync
--locked` restored declared dependencies without changing the lockfile. Local
checks used `UV_NO_CACHE=1 uv run --offline --no-sync` because the sandbox could
not access the normal uv cache. Python was 3.13.15; CI pins 3.13.14.

## Behavior map and changes

| Behavior / evidence | Before | Protection added or strengthened |
| --- | --- | --- |
| Default model selection (README and helper docstring) | Selected first entry only | Select second model; catches always-first lookup |
| Valid input allowance (config comments and validation contract) | Typical subtraction and over-limit rejection | Exact exhaustion versus one token remaining; invalid integer types including booleans |
| Local dummy keys (README) | localhost and ordinary remote host | IPv4/IPv6 loopback and deceptive/non-loopback hostnames |
| YAML startup loading (loader docstring, README overrides) | Helpers only | Real YAML, override before validation, cache after success, retry after rejected config |
| Preserve system/current messages and trim complete old turns (helper docstring, UI warning) | One removed turn | Multiple turns, exact fit, newest-turn retention, aligned counts, unchanged caller history |
| Streaming chat (README chat feature; OpenAI-compatible request boundary) | Oversize rejection only | SDK chunk objects, metadata/empty chunks, ordered output, selected request settings, optional reasoning field, complete history and token counts |
| Failed model response (configured error copy) | None | Creation and mid-stream errors, visible error, unchanged history, usage counters and subsequent successful request |
| Model setting changes (README configurable models) | Name allowlist only | Different model budgets/sampling and unknown-selection fallback |
| Uploaded documents (README feature, status/warning copy) | Text success/error and single over-budget file | Real two-page PDF, malformed/empty PDFs, symlink escape, cumulative budget, skipped-file budget preservation and deletion |
| Awaited UI effects | No-op send/update methods | Per-test fake records awaited sends, streamed tokens and updates; explicit no-model-call assertion for oversized input |

Failure history remaining unchanged is a conservative application-level contract
inferred from committing completed turns and the configured failure message;
README does not explicitly specify failed-turn retention. PDF whitespace is not
a public contract: the test verifies page text in order after whitespace
normalization. SDK request/stream tests replace the external completion boundary,
not the application handler. They do not validate HTTP framing or SDK retries.

## Harness decisions

- App import loads configuration, creates a logger/client, and initializes Chainlit.
  Tests now use a temporary config/log/Chainlit root and dummy credentials, disable
  `.env` loading, and reject socket connections, including during collection.
  The repository's actual YAML, Chainlit config and tokenizer cache are still used.
- UI/session fakes are function-scoped; no shared class-level message registry.
- Runtime, unraisable-exception, and thread-exception warnings fail tests so lost
  async work cannot quietly pass. Existing dependency deprecations remain visible.
- No dependencies or production code changed. Small explicit matrices were enough;
  property-testing machinery would add little value for the selected contracts.

## Verification

Commands below used the restored existing environment:

```sh
UV_NO_CACHE=1 uv run --offline --no-sync ruff format --check .
UV_NO_CACHE=1 uv run --offline --no-sync ruff check .
UV_NO_CACHE=1 uv run --offline --no-sync pytest -ra
```

Result: formatting and lint pass; 68 tests pass, no skips/xfails, six existing
third-party warnings. The full suite was also run in reverse collection order:

```sh
UV_NO_CACHE=1 uv run --offline --no-sync python - <<'PY'
import pytest
class ReverseOrder:
    def pytest_collection_modifyitems(self, items):
        items.reverse()
raise SystemExit(pytest.main(['-q'], plugins=[ReverseOrder()]))
PY
```

All 68 passed. Focused fault checks used the following command shape for each
corresponding test node: `UV_NO_CACHE=1 uv run --offline --no-sync pytest -q NODE`.
Each temporary production edit was restored in `finally`; assertions failed for:

| Temporary fault | NODE (under `tests/ai_chat/`) |
| --- | --- |
| Always select first model | `test_config.py::test_default_model_context_length_uses_default_selection` |
| Reject exact context fit | `test_app.py::test_context_retains_newest_complete_turns_without_mutating_history` |
| Discard streamed tokens | `test_app.py::test_on_message_streams_and_commits_complete_turn` |
| Omit awaited status update | `test_app.py::test_process_attachments_reports_per_file_success` |
| Ignore prior document token usage | `test_app.py::test_attachment_budget_is_cumulative_and_skipped_file_does_not_consume_it` |
| Persist failed user turn | `test_app.py::test_on_message_model_failure_preserves_history_and_can_recover` |
| Omit upload deletion | `test_app.py::test_process_attachments_extracts_real_pdf_and_cleans_up` |

The first cumulative-budget test survived its mutation because all individually
fitting documents also fit together. An additional one-token document after the
budget is exhausted now distinguishes cumulative from per-file limits.

No production defect was confirmed by this work. See PLAN.md for unverified
boundaries; passing these tests is not evidence of complete production coverage.

## 2026-10-26: eMudhra/emSign certificate update

Require certifi >=2026.10.19; only certifi and affected pip changed package versions. Keep the seven-day cooldown. Remove only the incident certifi exception after 2026-10-27 03:24:17 Europe/Zurich, then relock and sync. Build/CI uv pins are 0.13.5; Python image stages patch existing pip with secure uv. Deployment images still require a fresh build (`--pull --no-cache`) and verification before redeployment. Advisory: https://discuss.python.org/t/109576.

## 2026-11-19: Usage statistics (0.4.0)

- Counters are added when an event happens. Chainlit calls `on_chat_end` on every websocket disconnect and restores the session on reconnect, so the former `chat_session_analytics` log line counted chats several times.
- Chat-level counts rely on the Chainlit session. It survives a reconnect within `session_timeout` (60 s in `.chainlit/config.toml`); after that, or after a restart, the next message counts as a new chat.
- Failed approach: checking writability in `@cl.on_app_startup`. Chainlit 2.12.0 catches exceptions from that hook and only logs them, so the app kept running. The check runs at import of `ai_chat.app` instead.
- Opening a read-only SQLite file and `CREATE TABLE IF NOT EXISTS` raise nothing; only a write does. `check_writable` therefore inserts a row and rolls back.
- The `usage_stats` block in `config.yaml` is required on purpose, so that counting is a stated decision; `db_file: null` disables it. This is the breaking change of 0.4.0.
- Hours are stored per day so that the report follows `--since` exactly; the finer granularity was accepted. The earlier layout with hours per month was never committed, so there is no migration from it.
- Counters are written after the outcome is shown and a finished answer is in the history, because a locked stats file holds a write up for seconds. Only the counters of the message itself are written before the model request, so that a stopped or failed answer still counts as a message.
- `tests/ai_chat/conftest.py` imports application modules inside its fixtures. Given a path (`uv run pytest tests/ai_chat`), pytest loads that file before `tests/conftest.py` has built its sandbox; a top-level import of `ai_chat.usage_stats` then read the real `config.yaml` and `.env` and made collection fail on a blocked tokenizer download.
- `tokens/second` divides by `response_stream_ms`, the time from the first answer token on. Data recorded before has no value for it, and the tokens of the first chunk are not timed.
- `documents_skipped` also counts uploads without a path or outside the upload directory; the report labels them "skipped".
- `ai_chat.usage_stats` resolves the logger lazily on write errors and loads only `usage_stats` via `load_usage_stats_config()`, so `make stats` does not require API keys or touch `chainlit_logs.log`. SQLite uses WAL mode and read-only snapshots (`?mode=ro`) without DDL on reads.
- `FILE_TYPES` includes whitelisted code/text formats (`html`, `py`, `r`, `rmd`) plus aliases (`markdown`, `mdown`, `mkd`, `htm`), and records extensions for all validated uploads (processed, failed, or over-budget skipped).