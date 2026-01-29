# AGENTS Guidelines (Python)

Guidelines for agent-assisted development. Python 3.12+, managed with `uv`.

## Process & Security
- **Living Doc**: Update this file with new findings/notes.
- **Scope**: Work only in this repo.
- **Approvals**: **ALWAYS** ask before fetching external resources or installing packages.

## Environment (`uv`)
Manage env with `uv`. Re-run `uv sync` after changes.
```bash
uv sync                 # Lock/Sync
uv add [--dev] <pkg>    # Add dependency
uv run <cmd>            # Run in env
```

## Python Conventions
- **Types**: Modern syntax (`list[str]`, `X | None`, `Self`). No `typing.List`.
- **Data**: Use `dataclasses` or `TypedDict`.
- **Paths**: `pathlib.Path` ONLY.
- **Resources**: `with` context managers.
- **Cleanup**: Always release resources (files, connections, temp dirs). Use `atexit` for global cleanup.
- **Errors**: Specific exceptions with messages. No bare `except:`.
- **Formatting**: f-strings (`f"{var=}"`).

## Principles
1. **Simple Architecture**: Flat, explicit, linear control flow. No meta-programming.
2. **Predictable**: Consistent layout, standard patterns, deterministic tests.
3. **Regenerable**: Decoupled modules, config in `config.yaml` (no magic values).
4. **Quality**: Descriptive names, structured logging.

## Documentation
- **Comments/Docstrings**: Explain *why*. Follow PEP 257.
- **README**: Concise usage/examples. No fluff.
- **Files**: Avoid extra docs. Update README/AGENTS.md instead.

## Code Quality
```bash
uv run ruff format .          # Format
uv run ruff check . [--fix]   # Lint
uv run pytest                 # Test
```

## Stack & Best Practices
- **CLI**: Use `typer` for command-line interfaces (not `argparse`). Type hints, auto-docs, `typer.Argument()`, `typer.Option()`.
- **FastAPI**: Pydantic validation, `app/routers/` modules, dependency injection, `async` I/O.
- **Streamlit**: `st.sidebar` for controls, `st.session_state`, `@st.cache_data`.
- **LLM**: OpenRouter (OpenAI SDK). load API key from `.env`. Config in `config.yaml` (model, temp, tokens). Concurrent: `ThreadpoolExecutor`.
- **Embeddings**: `sentence-transformers` (local, e.g., `intfloat/multilingual-e5-small`).
- **Rich**: `Console`, `Table` for terminal output.
- **Playwright**: `async`, headless, built-in selectors (`role`, `text`).
- **Data Science**: Jupyter, pandas (vectorized), pyarrow/parquet, scikit-learn, seaborn.
- **Docling**: Parse docs to MD (`export_to_markdown`). `uv add docling`.

## Discovery Log
- (Agent: Add project-specific notes/stack decisions here)
