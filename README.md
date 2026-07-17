# Local AI Chat with Document Processing

**A locally operated AI chat with document processing, based on [Ollama](https://ollama.com/), [Chainlit](https://github.com/Chainlit/chainlit) and [Docling](https://github.com/docling-project/docling).**

![GitHub License](https://img.shields.io/github/license/machinelearningZH/ai-chat)
[![PyPI - Python](https://img.shields.io/badge/python-v3.13-blue.svg)](https://github.com/machinelearningZH/ai-chat)
[![GitHub Stars](https://img.shields.io/github/stars/machinelearningZH/ai-chat.svg)](https://github.com/machinelearningZH/ai-chat/stargazers)
[![GitHub Issues](https://img.shields.io/github/issues/machinelearningZH/ai-chat.svg)](https://github.com/machinelearningZH/ai-chat/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/machinelearningZH/ai-chat.svg)](https://img.shields.io/github/issues-pr/machinelearningZH/ai-chat)
[![Current Version](https://img.shields.io/badge/version-0.2-green.svg)](https://github.com/machinelearningZH/ai-chat)
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

# Pull models, e.g.:
ollama pull hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:q6_k

ollama pull qwen3.6

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

## Project Information

We use this AI chat internally as a lightweight local AI assistant with document processing capabilities that we can operate on-premise. We like [Chainlit](https://docs.chainlit.io/get-started/overview) for its simplicity and configurability. We have also experimented successfully with other frameworks like [Open WebUI](https://github.com/open-webui/open-webui).

Our current go-to LLM for small on-premise servers is [Qwen3.6-35B-A3B](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF), which performs well for general-purpose tasks and works sufficiently well for the German language too.

## Project Team

**Chantal Amrhein**, **Patrick Arnecke** – [Amt für Statistik und Daten Kanton Zürich: Team Data](https://www.zh.ch/de/direktion-der-justiz-und-des-innern/amt-fuer-statistik-und-daten.html)

## Feedback and Contributing

We welcome feedback and contributions! [Email us](mailto:datashop@statistik.zh.ch) or open an issue or pull request.

We use [`ruff`](https://docs.astral.sh/ruff/) for linting and formatting.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Disclaimer

This software (the Software) incorporates open-source models (the Models) from providers like Ollama, Hugging Face, Docling and OpenAI. The app has been developed according to and with the intent to be used under Swiss law. Please be aware that the EU Artificial Intelligence Act (EU AI Act) may, under certain circumstances, be applicable to your use of the Software. You are solely responsible for ensuring that your use of the Software as well as of the underlying Models complies with all applicable local, national and international laws and regulations. By using this Software, you acknowledge and agree (a) that it is your responsibility to assess which laws and regulations, in particular regarding the use of AI technologies, are applicable to your intended use and to comply therewith, and (b) that you will hold us harmless from any action, claims, liability or loss in respect of your use of the Software.
