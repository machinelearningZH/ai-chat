#!/bin/sh
set -eu

usage() {
    cat <<'EOF'
Usage: serve-llamacpp.sh MODEL.gguf [LLAMA_SERVER_ARGUMENT ...]

Start llama.cpp's OpenAI-compatible llama-server. Additional arguments are
passed to llama-server.

Environment variables:
  SERVER_HOST        Bind address (default: 127.0.0.1)
  SERVER_PORT        Listen port (default: 8002)
  SERVED_MODEL_NAME  API model name; must match config.yaml (default: filename)
  MAX_MODEL_LEN      Optional context length passed as --ctx-size
  LLAMA_SERVER_BIN   llama.cpp server executable (default: llama-server)
EOF
}

if [ "$#" -eq 0 ]; then
    usage >&2
    exit 2
fi

model_file=$1
shift
llama_server_bin=${LLAMA_SERVER_BIN:-llama-server}
server_host=${SERVER_HOST:-127.0.0.1}
server_port=${SERVER_PORT:-8002}
served_model_name=${SERVED_MODEL_NAME:-$(basename "$model_file")}

if [ ! -f "$model_file" ]; then
    echo "Error: model file does not exist: $model_file" >&2
    exit 2
fi

if ! command -v "$llama_server_bin" >/dev/null 2>&1; then
    echo "Error: '$llama_server_bin' was not found. Install or build llama.cpp first." >&2
    echo "See: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md" >&2
    exit 127
fi

set -- \
    --model "$model_file" \
    --host "$server_host" \
    --port "$server_port" \
    --alias "$served_model_name" \
    "$@"

if [ -n "${MAX_MODEL_LEN:-}" ]; then
    set -- "$@" --ctx-size "$MAX_MODEL_LEN"
fi

exec "$llama_server_bin" "$@"
