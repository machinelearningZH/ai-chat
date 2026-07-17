FROM ghcr.io/astral-sh/uv:0.11.23 AS uv

FROM python:3.13.14-slim-bookworm

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

ENV HOME=/tmp

COPY --chown=10001:10001 .chainlit .chainlit
COPY --chown=10001:10001 _tiktoken_cache _tiktoken_cache
COPY --chown=10001:10001 chainlit.md config.yaml ./
COPY --chown=10001:10001 src src

RUN mkdir -p .files \
    && chown 10001:10001 /app .files

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3)"

CMD ["chainlit", "run", "src/app.py", "--host", "0.0.0.0", "--port", "8000"]
