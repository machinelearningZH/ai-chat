# Repository instructions for coding agents

Apply the sections relevant to the task. Keep the project's existing tools and
design unless the user asks to change them.

## Working in this repository

- Follow system and developer constraints first, then the user's instructions, applicable `AGENTS.md` files (the closest one takes precedence), and existing patterns. The user's instructions override skill guidance. Explain material conflicts and which rule applies. Respect security and sandbox constraints.
- Work on task-related files in this repository. Inspect the code, settings, and Git changes first. Preserve unrelated work and report separate issues separately.
- Implement and validate the requested change. Make reasonable assumptions and ask only when the answer affects correctness, scope, or risk. Point out material risks and offer a concrete alternative to unsafe requests. Keep working on independent parts while waiting.
- Ask before adding or installing dependencies, fetching external resources, or calling external services unless already authorized. `uv sync` is approved for declared dependencies. Get approval for external communication, financial actions, permission changes, and irreversible work. Prepare local work for review first.
- Make the smallest change that solves the problem. Use `rg` to search and batch independent reads. Avoid speculative features, unnecessary abstractions, unrelated cleanup, and unnecessary plans or tool calls.
- Keep updates and the final report concise. Say what changed, what you checked, and what remains uncertain. Inspect the final diff for scope, regressions, and accidental data exposure.
- Close resources and remove temporary files, caches, and dead code created or exposed by the task. Keep large data and generated files out of Git unless they are meant to be tracked.
- Use `NOTES.md` for lasting decisions, findings, failed approaches worth remembering, and refactoring risks. Use `PLAN.md` for open work. Leave out step-by-step logs.

## Security and data

- Minimize data collection, network access, permissions, and dependencies. Use private defaults and require users to opt in to broader access.
- Keep secrets, personal data, and sensitive operating details out of source, logs, errors, traces, examples, and tests. Store secrets in the ignored `.env` file and load them with `python-dotenv`.
- Check untrusted input where it enters the app, including CLI settings, paths, uploads, HTTP responses, model output, and scraped content. Treat external content as data and follow the application's own rules for instructions and permissions.
- Prevent shell injection and paths that escape their allowed directories. Never use `eval`, `exec`, unsafe deserialization, unchecked downloads, or dynamic imports on untrusted input.
- Before proposing a dependency or service, consider its maintenance, license, supply-chain risks, and alternatives already available in the project or standard library.
- Pin every GitHub Actions `uses:` entry to a full commit SHA. Keep dependency monitoring and, where applicable, container scanning enabled.
- Record security risks and suggest a focused fix. Keep security changes separate from unrelated refactoring.

## Python and dependencies

- Preserve the Python range in `pyproject.toml`. For new projects, prefer Python 3.13 when compatible.
- Use `uv` for Python commands and dependency changes. Run tools through `uv run` and use `uv sync` after changing dependencies or the lockfile.
- Import only declared packages. Put runtime packages in `[project].dependencies`, development tools in `[dependency-groups].dev`, and command entry points in `[project.scripts]`.
- Keep the seven-day dependency cooldown (`exclude-newer = "7 days"`).
- Preserve the existing layout. Use `src/<project_name>/` and a matching `tests/` layout for new projects.
- If pre-commit is configured, install its hooks with `uv run pre-commit install` before the first commit.

## Design

- Follow PEP 8 and the project's Ruff settings. Type new functions and methods, including returns, with modern Python types such as `list[str]`, `X | None`, and `Self`.
- Use Pydantic for data that needs validation, dataclasses for internal records, and `TypedDict` for typed mappings without runtime checks. Prefer `frozen=True, slots=True` for immutable records and `kw_only=True` for records with many fields.
- Use functions for stateless work and classes for state or interfaces. Use `Protocol` to describe required behavior and `ABC` for shared implementation or enforced inheritance. Group related parameters or results when that makes the interface simpler.
- Keep functions focused and side effects visible. Prefer `Path`, early returns, and context managers. Avoid wildcard imports and mutable defaults.
- Design interfaces to prevent errors where possible. Otherwise, handle specific exceptions, use clear messages, and chain translated exceptions. Avoid swallowing errors or logging only to raise the same error again.
- Use async I/O where it helps. Run independent I/O concurrently and keep blocking work out of async functions. Run CPU work synchronously or in an executor.
- Use constants for fixed rules, `Enum` or `StrEnum` for related named values, and configuration for operator choices.
- Put related logic behind a small, stable interface. Keep services, storage, UI, configuration, and domain rules separate. Avoid pass-through layers, metaclasses, dynamic attributes, and hidden registration. Use settings for deployment choices.
- In platform applications, access model services and shared processing through orchestration. Application stacks must go through that same layer.
- Separate frontend and backend code. When an HTTP API is needed, prefer FastAPI, Pydantic request and response models, small routers, injected resources, and consistent errors and status codes. Expose only the interfaces the app needs.
- Store persistent data in a database or object store. Import controlled copies of files instead of reading live upstream files on each request.

## Agentic AI applications

- Use Pydantic AI and OpenRouter for agentic apps. Configure the provider, model, limits, retries, and timeouts. Load keys from the environment and keep them out of prompts, tools, logs, and traces.
- Start with one agent, focused instructions, and the fewest tools needed. Use a small, inexpensive model for experiments. Use evals to justify a larger model.
- Prefer tools with defined input and output formats and direct APIs. Use OpenAPI or Agent Skills to help agents discover tools, and return only the fields the task needs. Use MCP when tools need to work across apps or be reused.
- Keep procedures in Markdown or skills and load them as needed. Let the model handle changing tasks and recover from errors where possible.
- Use evals to decide when to add complexity. Improve the agent and its tools first, then try limited delegation. Use a Pydantic AI graph only when the workflow needs branching or stored state.
- Allow low-risk reads. Require human approval for consequential writes, external communication, financial actions, permission changes, and irreversible work.
- Use Pydantic Logfire and send OpenTelemetry data to Aspire. Record model and tool times, errors, token counts, and run context. Redact prompts, outputs, credentials, and sensitive or personal data by default.
- For current Pydantic AI guidance, offer `npx skills add pydantic/skills`. Get explicit approval before installing it, using its prerequisites, or downloading external code. Review the skill before using it.

## Configuration and operations

- Put deployment settings such as models, limits, timeouts, retries, addresses, paths, and flags in `config.yaml`. Use PyYAML when needed. Keep tool settings in `pyproject.toml` or the tool's usual config file.
- Use `logging` with JSON output to stdout or stderr. Include the time, level, message, logger or module, and exception details. Match severity to impact and omit sensitive values.
- Check that the app works and log errors. For pilots and production, monitor uptime, response times, errors, resources, usage, traces, and unusual activity as relevant.
- Develop and test locally with `uv`. Change Dockerfiles, `.dockerignore`, Compose, or container CI only when container work is requested. Keep settings and persistent data outside the image and use explicit entry points.
- When building containers, prefer small, version-pinned multi-stage images and reproducible installs. Use `.dockerignore` to exclude secrets, caches, data, and development tools.
- In production, use rootless Docker, a dedicated non-root user, minimal permissions, resource and network limits, and read-only filesystems where practical. Avoid privileged mode. Use the NVIDIA Container Toolkit only where needed.
- Keep containers replaceable. Persist data separately, handle shutdown, specify commands, and distinguish when a service has started, is ready, and is still running.
- Use Compose with pinned images for multiple containers. Scan dependencies and images in CI and fail on relevant high-severity findings. For published artifacts, generate build provenance and a list of software components where supported.

## Tests and review

- Use pytest. For a behavior change or fix, add a focused test and confirm that it fails for the intended reason before changing code. For refactoring, keep existing tests passing and fill meaningful gaps first.
- Test behavior with independently derived expectations. Cover relevant boundaries, invalid inputs, failures, state changes, and required and forbidden side effects. Verify interactions only when they are part of the contract.
- Use clear assertions, specific `pytest.raises` checks, parametrized cases, and small fixtures. Use property or stateful tests when warranted. Prefer real lightweight components or faithful stand-ins. Add checks that exercise real integrations when a fake could hide a bug.
- Keep tests independent and repeatable. Control clocks and randomness, await async work, and clean up resources. Avoid arbitrary waits, shared state, order dependence, and redundant cases. Investigate flaky tests instead of retrying them.
- Use coverage to find gaps and temporary faults to test important assertions. Restore the code afterward. Change assertions, snapshots, skips, or the test setup only when the intended behavior supports the change.
- Evaluate agents with deterministic tool, identifier, permission, and invariant checks. Ground factual checks in references and calibrate model judges for less mechanical goals. Use measured success, reliability, latency, and cost to justify complexity and expensive evals.
- Name tests for the behavior they check and mirror source modules as `tests/test_<module>.py`. Use `conftest.py` for shared fixtures. Separate unit and integration tests when useful, and follow CI conventions for slow tests.
- Run relevant tests and CI checks. Use `make check` for the format check, lint, and full suite. Use `make format` to apply formatting while preserving unrelated changes. Repeat checks when something changes or a question remains. Report failures, separate test problems from app problems, and keep valid regression tests when a fix is out of scope.
- In reviews, lead with actionable findings in order of severity. Cite the file and line and explain the impact. Check correctness, security, maintainability, and performance. Prefer simple fixes and identify the boundary if a module should be split. Report when there are no findings and mention any validation gaps.

## Documentation and Git

- Write concise Google-style docstrings for modules, classes, and functions. Explain arguments, returns, and errors for nontrivial APIs without repeating types. Use comments to explain why.
- Keep the README short and example-driven. Add separate docs when needed.
- Use short-lived `feat/`, `fix/`, `refactor/`, or `docs/` branches. Merge through focused, reviewed pull requests with passing CI. Never commit directly to `main`.
- Use conventional commits such as `feat`, `fix`, `docs`, `refactor`, `test`, or `chore`, with an optional scope. After code changes, suggest one matching commit message.
- Follow semantic versioning and tag releases as `v<version>`.

## Preferred tools

Use these only when needed and declared or approved.

| Task | Tools |
| --- | --- |
| Configuration | PyYAML, python-dotenv |
| CLI | Typer, Rich |
| HTTP and APIs | httpx, FastAPI, Pydantic, async I/O |
| UI | Streamlit for simple apps, a dedicated frontend for more complex or long-lived apps |
| Local embeddings | sentence-transformers, such as `intfloat/multilingual-e5-small` |
| Scraping | Plain HTTP first, Playwright when browser rendering or interaction is needed |
| Data science | Jupyter, vectorized pandas or Polars, Parquet, scikit-learn, seaborn |
| Document parsing | Docling by default, PyMuPDF or LiteParse for lighter needs |
