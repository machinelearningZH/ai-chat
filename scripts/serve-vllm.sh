#!/bin/sh
set -eu

usage() {
    cat <<'EOF'
Usage: serve-vllm.sh MODEL [VLLM_ARGUMENT ...]

Start vLLM's OpenAI-compatible server. MODEL is a Hugging Face model ID or a
local model directory. Additional arguments are passed to `vllm serve`.

Environment variables:
  SERVER_HOST        Bind address (default: 127.0.0.1)
  SERVER_PORT        Listen port (default: 8001)
  SERVED_MODEL_NAME  API model name; must match config.yaml (default: MODEL)
  MAX_MODEL_LEN      Optional maximum model context length
  VLLM_BIN           vLLM executable (default: vllm)
EOF
}

if [ "$#" -eq 0 ]; then
    usage >&2
    exit 2
fi

model=$1
shift
vllm_bin=${VLLM_BIN:-vllm}
server_host=${SERVER_HOST:-127.0.0.1}
server_port=${SERVER_PORT:-8001}
served_model_name=${SERVED_MODEL_NAME:-$model}

if ! command -v "$vllm_bin" >/dev/null 2>&1; then
    echo "Error: '$vllm_bin' was not found. Install vLLM in its own supported environment." >&2
    echo "See: https://docs.vllm.ai/en/latest/getting_started/installation/" >&2
    exit 127
fi

set -- "$model" \
    --host "$server_host" \
    --port "$server_port" \
    --served-model-name "$served_model_name" \
    "$@"

if [ -n "${MAX_MODEL_LEN:-}" ]; then
    set -- "$@" --max-model-len "$MAX_MODEL_LEN"
fi

exec "$vllm_bin" serve "$@"
