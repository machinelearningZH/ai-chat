# Local AI Chat

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](pyproject.toml)
[![Latest release](https://img.shields.io/github/v/release/machinelearningZH/ai-chat)](https://github.com/machinelearningZH/ai-chat/releases/latest)

Local AI Chat is a Chainlit app for chatting with a model you host yourself.
Attach documents to ask questions, summarize them, or extract information. The
app works with Ollama, vLLM, llama.cpp, and other servers that support the
OpenAI chat completions API.

## Get started with Ollama

You need Python 3.13, `make`, and a running Ollama server. Use `uv` to install
the locked Python dependencies. [uv installation](https://docs.astral.sh/uv/getting-started/installation/) ·
[Ollama](https://ollama.com/)

```sh
git clone https://github.com/machinelearningZH/ai-chat
cd ai-chat
uv sync --locked
ollama pull hf.co/unsloth/gemma-4-E2B-it-GGUF:q6_k
make run-native
```

Open <http://localhost:8000>. To match the app's default 100,000-token context
window, start Ollama with `OLLAMA_CONTEXT_LENGTH=100000`. For lower memory use,
reduce Ollama's context size and the app's `max_tokens_context` together. Set
`max_tokens_output` to leave room for the prompt and the context buffer.
[config.yaml](config.yaml)

## Use the chat

Attach PDFs with selectable text, Office documents, HTML, or text and code
files. The app skips attachments that exceed the input budget and drops older
turns from long chats when building the next request. Use chat settings to pick
a model and toggle Thinking Mode. [Upload guide](chainlit.md)

## Configure the app

- Set model names and token limits under `model`, prompts and chat copy under
  `messages`, and the model server URL under `openai.base_url`. Restart the
  app after editing settings. [config.yaml](config.yaml)
- Override the model server URL with `AI_CHAT_BASE_URL`. Set `AI_CHAT_API_KEY`
  in the environment or the repository's ignored `.env` file. The default
  dummy key applies to loopback addresses. Non-loopback URLs require a key
  value.
- Set upload limits, allowed types, and the Chainlit interface language in
  `.chainlit/config.toml`. Add the browser origin to `allow_origins` if you
  change the app host or port. [Chainlit settings](.chainlit/config.toml)

Start the app with `uv run chainlit run src/app.py` to use the configured
server URL. The app sends chat text and extracted document text to that server.
Chainlit telemetry is disabled. The app has no built-in sign-in.

### Use vLLM or llama.cpp

Install the model server separately. Run the matching app command in another
terminal once the server is ready.
[vLLM installation](https://docs.vllm.ai/en/latest/getting_started/installation/) ·
[llama.cpp build guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)

| Server    | Start the server                                | Start the app       |
| --------- | ----------------------------------------------- | ------------------- |
| vLLM      | `make serve-vllm MODEL=google/gemma-3-4b-it`    | `make run-vllm`     |
| llama.cpp | `make serve-llamacpp MODEL=/path/to/model.gguf` | `make run-llamacpp` |

The helpers use the default model name and context size from `config.yaml`.
Adjust the context and output limits to fit the model and hardware. If you
override `APP_MODEL_NAME`, use the same name in the app's model list and select
it in the app. If the server rejects `reasoning_effort`, set
`runtime.reasoning_effort_when_thinking_disabled` to `null`. [config.yaml](config.yaml)

vLLM uses localhost port 8001 and llama.cpp uses 8002. To change a port, pass
`VLLM_PORT` or `LLAMACPP_PORT` to both commands. Run the shell helpers directly
to pass server-specific arguments. [Server scripts](scripts/)

## Run with Docker Compose

Install Docker Compose and run `uv sync --locked` so Make can load the model
settings.

| Command             | Where Ollama runs                                    |
| ------------------- | ---------------------------------------------------- |
| `make app-host`     | On your host, with only the app in Docker            |
| `make stack-cpu`    | In Docker on the CPU                                 |
| `make stack-nvidia` | In Docker on Linux with the NVIDIA Container Toolkit |
| `make stack-amd`    | In Docker on Linux with a supported AMD GPU and ROCm |

On macOS, run Ollama on the host for Apple GPU support. `make app-host` starts
the app container and connects it to Ollama, which must listen on an address
reachable from Docker.

For a containerized Ollama setup, download the model into the shared Ollama
volume, then start the desired stack.

```sh
make model MODEL=hf.co/unsloth/gemma-4-E2B-it-GGUF:q6_k
make stack-cpu UP_FLAGS=-d
```

Open <http://localhost:8000>. Set `AI_CHAT_PORT` to change the host port.
Compose uses the default model's context size unless you set
`OLLAMA_CONTEXT_LENGTH`. `make down` stops the stack and preserves its model
and usage volumes. Run `make help` for all commands.

For Docker without Compose, `make build` creates the `ai-chat` image. The
container runs as UID 10001 and serves the app on port 8000. Mount your config at
`/app/config.yaml`, set `AI_CHAT_BASE_URL` and `AI_CHAT_API_KEY`, and mount a writable
`/app/stats` to persist usage counters. Mount the configured log path if you
need to retain logs across container replacements.

## Read usage statistics

The app stores aggregate counts and timings for chats, messages, replies, and
document imports in `stats/usage_stats.sqlite` by default. The database
contains no chat text, filenames, or user identifiers. `usage_stats.timezone`
sets the day and hour boundaries used to record activity.

```sh
make stats                              # monthly overview
make stats DETAILED=1                   # all counters
make stats BY=day SINCE=2026-01-01      # daily overview starting on this date
make stats STATS_SOURCE=native          # read the native database explicitly
```

By default (`STATS_SOURCE=auto`), `make stats` uses the running Compose app, or
its stats volume if the app is stopped and the image is available; otherwise it
reads the native database. Pass `STATS_SOURCE=native` or `STATS_SOURCE=compose`
to select a source explicitly. The app checks that the database is writable at
startup. Set `usage_stats.db_file` to `null` to disable counting.
[config.yaml](config.yaml)

## Project team

**Chantal Amrhein**, **Jonas Egloff**, **Patrick Arnecke** —
[Amt für Statistik und Daten](https://www.zh.ch/de/direktion-der-justiz-und-des-innern/amt-fuer-statistik-und-daten.html)

## Contributing

Run `make check` before opening a pull request. It checks formatting, runs
Ruff, and runs pytest. Use `make format` to apply formatting. The tests use an
isolated configuration and a stand-in model client. CI also validates the
Compose files and checks that the container serves the chat page.
[CI workflow](.github/workflows/ci.yaml)

For feedback, open an issue or email the project team at
[datashop@statistik.zh.ch](mailto:datashop@statistik.zh.ch).

## License

The application code is available under the [MIT License](LICENSE). Model files have their own licenses; check the terms for the model you choose.

## Disclaimer

This software (the Software) incorporates machine learning models and analytical
tools for document analysis and has been developed according to and with the
intent to be used under Swiss law. Please be aware that the EU Artificial
Intelligence Act (EU AI Act) may, under certain circumstances, be applicable to
your use of the Software. You are solely responsible for ensuring that your use
of the Software as well as of the underlying models complies with all applicable
local, national and international laws and regulations. By using this Software,
you acknowledge and agree (a) that it is your responsibility to assess which
laws and regulations, in particular regarding the use of AI technologies, are
applicable to your intended use and to comply therewith, and (b) that you will
hold us harmless from any action, claims, liability or loss in respect of your
use of the Software.
