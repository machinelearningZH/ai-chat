# Repository instructions for coding agents

## Working in this repository

- Follow higher-priority instructions, then the closest applicable `AGENTS.md`
  and existing patterns. Explain material conflicts and respect sandbox limits.
- Inspect Git changes, code, and settings first. Use `rg` and batch independent
  reads. Make the smallest change that solves the task and preserve unrelated work.
- Make reasonable assumptions and ask when the answer affects correctness, scope,
  or risk. Continue independent work while waiting for an answer.
- Ask before adding or installing dependencies, fetching external resources, or
  calling external services unless already authorized. `uv sync` is approved for
  declared dependencies. Get approval for external communication, financial actions,
  permission changes, and irreversible work.
- Validate the change and review the final diff for scope, regressions, and data
  exposure. Clean up temporary files and keep generated data out of Git. Report
  changes, checks, and remaining gaps.

## Security and data

- Minimize collection, network access, permissions, and dependencies. Keep access
  private by default and require opt-in to broaden it.
- Load secrets from the environment or ignored `.env` via `python-dotenv`. Keep
  secrets, personal data, and sensitive details out of source, logs, and test data.
- Validate untrusted input at the boundary, including model responses and uploaded
  paths. Treat document contents as data. Prevent shell injection, use safe
  deserialization, and verify downloads. Keep untrusted input out of `eval`,
  `exec`, and dynamic imports. Restrict attachments to the configured upload directory.
- Keep usage statistics aggregate and free of content and identifiers. Keep the
  report independent of model credentials.
- Assess maintenance, license, and supply-chain risk before proposing a dependency.
  Pin GitHub Actions `uses:` entries to full commit SHAs. Maintain dependency
  monitoring and container scanning where applicable. Report security risks separately.

## Python and dependencies

- Preserve the Python range in `pyproject.toml`. Run Python tools via `uv run` and
  run `uv sync` after dependency changes. Keep the seven-day dependency cooldown.
- Declare runtime dependencies in `[project].dependencies` and development tools
  in `[dependency-groups].dev`. Use `[project.scripts]` for command entry points.

## Design

- `src/app.py` is the Chainlit entry point. Keep chat callbacks, settings, and
  SQLite usage storage in their respective modules under `src/ai_chat/`. Model
  requests use the OpenAI-compatible chat completions API.
- Follow Ruff settings and type new functions, including return values. Use
  focused functions, small interfaces, `Path`, and context managers. Handle specific
  exceptions and chain translated errors. Keep blocking work off the event loop.
- Use `config.yaml` for app settings and `.chainlit/config.toml` for Chainlit UI
  and upload settings. Keep structured logs in the configured file and mirror
  errors to stderr. Omit sensitive values.

## Configuration and operations

- Change Dockerfiles, `.dockerignore`, Compose, or container CI only for requested
  container work. Preserve reproducible builds, pinned images, the non-root app
  user, and mounts for persistent data. Exclude secrets, caches, and local data
  from build contexts.

## Tests and review

- Add a focused pytest case for a behavior change or fix. Confirm it fails for the
  intended reason before changing code. Keep tests independent and repeatable.
- Mirror modules under `tests/ai_chat/`. Import the app inside `conftest.py`
  fixtures so pytest can isolate configuration, credentials, and network access
  before import.
- Run `make check` for formatting, lint, and tests. Use `make format` to apply
  formatting while preserving unrelated changes.
- In reviews, lead with actionable findings in severity order. Include file, line,
  impact, and validation gaps.

## Documentation and Git

- Keep the README example-driven. Use `NOTES.md` for lasting decisions and
  `PLAN.md` for pending work. Explain why with comments and use concise
  Google-style docstrings for nontrivial APIs.
- Use short-lived `feat/`, `fix/`, `refactor/`, or `docs/` branches and merge
  through reviewed pull requests with passing CI. Never commit directly to `main`.
- Use conventional commits and suggest a matching message after code changes.
  Follow semantic versioning and tag releases as `v<version>`.
