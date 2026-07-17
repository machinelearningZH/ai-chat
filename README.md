# Local AI Chat with Document Processing

**A locally operated AI chat with document processing, based on [Ollama](https://ollama.com/), [Chainlit](https://github.com/Chainlit/chainlit) and [Docling](https://github.com/docling-project/docling).**

![GitHub License](https://img.shields.io/github/license/machinelearningZH/ai-chat)
[![PyPI - Python](https://img.shields.io/badge/python-v3.13-blue.svg)](https://github.com/machinelearningZH/ai-chat)
[![GitHub Stars](https://img.shields.io/github/stars/machinelearningZH/ai-chat.svg)](https://github.com/machinelearningZH/ai-chat/stargazers)
[![GitHub Issues](https://img.shields.io/github/issues/machinelearningZH/ai-chat.svg)](https://github.com/machinelearningZH/ai-chat/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/machinelearningZH/ai-chat.svg)](https://img.shields.io/github/issues-pr/machinelearningZH/ai-chat)
[![Current Version](https://img.shields.io/badge/version-0.3-green.svg)](https://github.com/machinelearningZH/ai-chat)
<a href="https://github.com/astral-sh/ruff"><img alt="linting - Ruff" class="off-glb" loading="lazy" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json"></a>

![](_imgs/app_ui.png)

## Features

- **On-Premise**: Can be set up to work locally
- **Document Processing**: Supports PDF, DOCX, PPTX, XLSX, HTML, Markdown and more. Intelligent document conversion with options for layout and structure preservation
- **Flexible Configuration**: Customizable models and parameters
- **Lightweight**: Few dependencies and easy setup

## Usage

[Install uv](https://docs.astral.sh/uv/getting-started/installation/) for environment management.

Set up [Ollama](https://ollama.com/) as your local LLM server:

```bash
# Install ollama (e.g. Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the default model:
ollama pull hf.co/unsloth/gemma-4-E2B-it-GGUF:q6_k

# https://docs.ollama.com/context-length
# To increase the default context size that Ollama uses, you can set the environment variable OLLAMA_CONTEXT_LENGTH. For example, to set it to 120k tokens:
export OLLAMA_CONTEXT_LENGTH=120000
```

Install and set up the app:

```bash
git clone https://github.com/machinelearningZH/ai-chat
cd ai-chat
uv sync

# Adjust the configuration
nano config.yaml

# For non-local OpenAI-compatible endpoints, put the key in .env:
# AI_CHAT_API_KEY=...

# UI texts and prompts are configured in config.yaml under messages.

# Adjust the project-local Chainlit configuration if needed.
nano .chainlit/config.toml
# Telemetry is already disabled with project.enable_telemetry = false.

# If you use a custom port, also add it to .chainlit/config.toml allow_origins.

# Start the app (opens in browser at http://localhost:8000):
uv run chainlit run src/app.py

# Or set a specific port, watch and headless mode, and more:
# https://docs.chainlit.io/backend/command-line
uv run chainlit run src/app.py -w -h --port 8501
```

## Run Scenarios

The Makefile provides short commands for the supported local deployment
scenarios. It is a thin wrapper around `uv` and Docker Compose; the underlying
commands remain usable directly.

| Scenario | Command | Notes |
| --- | --- | --- |
| Native app + native Ollama | `make run-native` | Recommended on macOS to retain Metal acceleration |
| App container + native Ollama | `make app-host` | Uses `host.docker.internal` |
| App + CPU Ollama containers | `make stack-cpu` | Portable, but inference is CPU-only |
| App + NVIDIA Ollama containers | `make stack-nvidia` | Linux with NVIDIA Container Toolkit |
| App + AMD Ollama containers | `make stack-amd` | Linux with ROCm-compatible hardware |

Run a Compose scenario in the background by adding `UP_FLAGS=-d`:

```bash
make stack-cpu UP_FLAGS=-d
make model MODEL=hf.co/unsloth/gemma-4-E2B-it-GGUF:q6_k
make logs
make down
```

If port 8000 is already occupied, select another host port without changing
the container configuration:

```bash
make app-host AI_CHAT_PORT=18001 UP_FLAGS=-d
```

`make down` keeps the `ollama-data` volume, so downloaded models survive
container replacement. `make model` starts the Compose Ollama service if it is
not already running; it downloads into the Compose volume, not native Ollama's
model directory. Run `make help` for the complete command list.

For Compose scenarios, Ollama's context length is read from the default model's
`max_tokens_context` in `config.yaml`. You can explicitly lower it for a
memory-constrained machine:

```bash
make stack-cpu OLLAMA_CONTEXT_LENGTH=8192 UP_FLAGS=-d
```

Larger contexts require substantially more RAM or VRAM. When using native
Ollama, configure the same `OLLAMA_CONTEXT_LENGTH` in the host Ollama service;
the Makefile cannot change the environment of an already-running host process.

The Compose files pin Ollama to version `0.32.0`. Override it deliberately when
testing another pinned release:

```bash
make stack-cpu OLLAMA_VERSION=0.31.2 UP_FLAGS=-d
```

On macOS, containerized Ollama cannot use the Apple GPU; prefer
`make run-native` or `make app-host`. The NVIDIA and AMD targets are intended
for supported Linux hosts. See the [official Ollama Docker
guide](https://docs.ollama.com/docker) for host driver requirements.

## Docker

The image runs the app as a non-root user on port 8000. Deployment-specific
model endpoints can be set with `AI_CHAT_BASE_URL`, so `config.yaml` can retain
the native default:

```yaml
openai:
  base_url: "http://localhost:11434/v1"
```

For a direct Docker run with Ollama on the host:

```sh
docker build -t ai-chat .

docker run --rm \
  --name ai-chat \
  --add-host=host.docker.internal:host-gateway \
  -p 8000:8000 \
  -e AI_CHAT_API_KEY=ollama \
  -e AI_CHAT_BASE_URL=http://host.docker.internal:11434/v1 \
  --mount type=bind,source="$(pwd)/config.yaml",target=/app/config.yaml,readonly \
  ai-chat
```

Open <http://localhost:8000>. The `ollama` value above is only a non-secret
dummy key for a local Ollama server. For a remote OpenAI-compatible endpoint,
put the real key in `.env` as `AI_CHAT_API_KEY=...` and replace the `-e` option
with `--env-file .env`. The `.dockerignore` prevents `.env` from entering the
image.

Within the full Compose stack, the app instead connects to
`http://ollama:11434/v1` over the private Compose network. Ollama's API is not
published to the host. For `make app-host` on native Linux, host Ollama must
listen on an address reachable from Docker rather than only on `127.0.0.1`.
Do not expose Ollama beyond trusted interfaces.

Uploaded files and logs are ephemeral by default. Add narrowly scoped volume
mounts for `/app/.files` or the configured log path only if persistence is
required.

The Linux image uses CPU-only PyTorch wheels because document conversion does
not require GPU acceleration. BuildKit retains uv's download cache outside the
runtime image. On the tested platform, the resulting image is about 2.2 GB
unpacked (about 500 MB compressed); exact sizes vary by platform.

## Project Information

We use this AI chat internally as a lightweight local AI assistant with document processing capabilities that we can operate on-premise. We like [Chainlit](https://docs.chainlit.io/get-started/overview) for its simplicity and configurability. We have also experimented successfully with other frameworks like [Open WebUI](https://github.com/open-webui/open-webui).

Our current go-to LLM for small on-premise servers is [Gemma 4 E2B](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF), which performs well for general-purpose tasks and works sufficiently well for the German language too.

## Project Team

**Chantal Amrhein**, **Patrick Arnecke** – [Amt für Statistik und Daten Kanton Zürich: Team Data](https://www.zh.ch/de/direktion-der-justiz-und-des-innern/amt-fuer-statistik-und-daten.html)

## Feedback and Contributing

We welcome feedback and contributions! [Email us](mailto:datashop@statistik.zh.ch) or open an issue or pull request.

We use [`ruff`](https://docs.astral.sh/ruff/) for linting and formatting.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Disclaimer

This software (the Software) incorporates open-source models (the Models) from providers like Ollama, Hugging Face, Docling and OpenAI. The app has been developed according to and with the intent to be used under Swiss law. Please be aware that the EU Artificial Intelligence Act (EU AI Act) may, under certain circumstances, be applicable to your use of the Software. You are solely responsible for ensuring that your use of the Software as well as of the underlying Models complies with all applicable local, national and international laws and regulations. By using this Software, you acknowledge and agree (a) that it is your responsibility to assess which laws and regulations, in particular regarding the use of AI technologies, are applicable to your intended use and to comply therewith, and (b) that you will hold us harmless from any action, claims, liability or loss in respect of your use of the Software.
