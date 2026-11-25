# Local AI Chat

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](pyproject.toml)
[![Version 1.0.0](https://img.shields.io/badge/version-1.0.0-green.svg)](pyproject.toml)

Chat with a model you run yourself. Attach documents to ask questions about them,
summarize them, or pull out specific information. The app uses Chainlit for the
chat interface and works with Ollama, vLLM, llama.cpp, and other servers that
support the OpenAI chat completions API.

## Get started with Ollama

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and start
[Ollama](https://ollama.com/). The app uses Python 3.13.

```sh
git clone https://github.com/machinelearningZH/ai-chat
cd ai-chat
uv sync --locked
ollama pull hf.co/unsloth/gemma-4-E2B-it-GGUF:q6_k
make run-native
```

Open <http://localhost:8000>. The app allows 100,000 tokens for the default
model's conversation and reply combined. To use the full limit, set
`OLLAMA_CONTEXT_LENGTH=100000` in the environment that starts Ollama. If you
have less memory, choose lower limits in both Ollama and
[config.yaml](config.yaml), leaving room for the reply.

## Use the chat

Ask a question and, if needed, attach up to 12 files to a message. Each file
can be up to 20 MB. The chat accepts PDF, Word, Excel, PowerPoint, CSV, HTML,
plain text, Markdown, Python, R, and R Markdown. PDF import reads existing text,
so scanned pages need text recognition before you upload them.

The app skips files if their text would exceed the model's limit. In long
chats, it drops older turns from what it sends with your next message.
You can change models in the chat settings and turn on Thinking Mode if your
model server supports it.

## Configure the app

- In [config.yaml](config.yaml), set the model names and limits under `model`,
  and edit the prompts and chat messages under `messages`. Restart the app
  after editing the file.
- Set `openai.base_url` or override it with `AI_CHAT_BASE_URL`. For a server
  that requires a key, set `AI_CHAT_API_KEY` in your environment or in the
  repository's ignored `.env` file. The default setup supplies a dummy key for
  localhost. Other addresses require a key value.
- In [.chainlit/config.toml](.chainlit/config.toml), set the upload limits,
  accepted formats, and interface language. Add the URL users will open to
  `allow_origins` if you use a different host or port.
- Chainlit telemetry is off by default. The app sends chat text and extracted
  document text to the configured model server. Run both on your own
  infrastructure to keep those requests there. The app has no built-in sign-in.

For a configured server other than local Ollama, start the app with
`uv run chainlit run src/app.py`.

### Use vLLM or llama.cpp

Install [vLLM](https://docs.vllm.ai/en/latest/getting_started/installation/) or
[llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)
separately. Start the server and then run the matching app command in another
terminal.

| Server    | Start the server                                | Start the app       |
| --------- | ----------------------------------------------- | ------------------- |
| vLLM      | `make serve-vllm MODEL=google/gemma-3-4b-it`    | `make run-vllm`     |
| llama.cpp | `make serve-llamacpp MODEL=/path/to/model.gguf` | `make run-llamacpp` |

The helpers serve the model under the default name in `config.yaml`. If you
set `APP_MODEL_NAME`, use the same name in `model.default_selection` and in
the model list. Set the app's context and answer limits within the limits
supported by the server and model.

vLLM uses localhost port 8001 and llama.cpp uses 8002. To change a port, pass
`VLLM_PORT` or `LLAMACPP_PORT` to both commands. For server-specific options,
run the helpers in [scripts/](scripts/) directly. If your server rejects
`reasoning_effort`, set `runtime.reasoning_effort_when_thinking_disabled`
to `null` in `config.yaml`.

## Run with Docker Compose

Run `uv sync --locked` first so Make can read the model settings.

| Command             | Where Ollama runs                                    |
| ------------------- | ---------------------------------------------------- |
| `make app-host`     | On your host, with only the app in Docker            |
| `make stack-cpu`    | In Docker on the CPU                                 |
| `make stack-nvidia` | In Docker on Linux with the NVIDIA Container Toolkit |
| `make stack-amd`    | In Docker on Linux with a supported AMD GPU and ROCm |

On macOS, run Ollama on the host to use the Apple GPU. With `make app-host`,
Ollama must accept connections from Docker. On Linux this usually means
listening on an address reachable from the container.

For example, start the CPU stack and download the model into it.

```sh
make stack-cpu UP_FLAGS=-d
make model MODEL=hf.co/unsloth/gemma-4-E2B-it-GGUF:q6_k
```

Open <http://localhost:8000>. Use `AI_CHAT_PORT` to change the host port and
`OLLAMA_CONTEXT_LENGTH` to change Ollama's context size. By default,
Compose uses the configured context size of the default model. `make logs`
shows service logs, and `make down` stops the stack while keeping downloaded
models and usage statistics. Run `make help` for all commands.

For a direct Docker deployment, build with `make build`. The image serves the
app on port 8000 as user ID 10001. Mount your config at `/app/config.yaml` and
set `AI_CHAT_BASE_URL` and `AI_CHAT_API_KEY` for your model server. Mount
`/app/stats` to keep usage counts across container replacements and make it
writable by the app user. Uploads are temporary. Mount the configured log path
if you need logs across container replacements.

## Read usage statistics

The default config records totals for chats, messages, replies, and document
imports in `stats/usage_stats.sqlite`. Reports also show activity by hour and
weekday. The database stores counts and timings without chat text, file names,
or user identifiers. `usage_stats.timezone` sets the reporting time zone.

```sh
make stats                             # monthly overview
make stats DETAILED=1                  # all counters
make stats BY=day SINCE=2026-01-01      # daily report from this date
```

`make stats` looks for the Compose app or its stats volume first, then uses the
local file. The `usage_stats` section is required. To turn counting off, set
`db_file: null` in [config.yaml](config.yaml). When counting is enabled, the app
must be able to write to the configured location at startup.

## Project team

**Chantal Amrhein**, **Jonas Egloff**, **Patrick Arnecke** —
[Amt für Statistik und Daten](https://www.zh.ch/de/direktion-der-justiz-und-des-innern/amt-fuer-statistik-und-daten.html)

## Contributing

Feedback and contributions are welcome. [Email us](mailto:datashop@statistik.zh.ch)
or open an issue or pull request.

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
