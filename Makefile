SHELL := /bin/sh
.DEFAULT_GOAL := help

CONFIG_CONTEXT_LENGTH = $(shell UV_NO_CACHE=1 PYTHONPATH=src uv run --no-sync python -c 'from ai_chat.config import default_model_context_length, load_config; print(default_model_context_length(load_config()))')
CONFIG_MODEL_NAME = $(shell UV_NO_CACHE=1 PYTHONPATH=src uv run --no-sync python -c 'from ai_chat.config import load_config; print(load_config()["model"]["default_selection"])')
OLLAMA_CONTEXT_LENGTH ?= $(CONFIG_CONTEXT_LENGTH)
COMPOSE = OLLAMA_CONTEXT_LENGTH=$(OLLAMA_CONTEXT_LENGTH) docker compose -f compose.yaml
NVIDIA_COMPOSE = $(COMPOSE) -f compose.nvidia.yaml
AMD_COMPOSE = $(COMPOSE) -f compose.amd.yaml
OLLAMA_VERSION ?= 0.32.0
UP_FLAGS ?=
APP_MODEL_NAME ?= $(CONFIG_MODEL_NAME)
SERVER_HOST ?= 127.0.0.1
VLLM_PORT ?= 8001
LLAMACPP_PORT ?= 8002

export OLLAMA_VERSION

.PHONY: help setup run-native run-vllm run-llamacpp serve-vllm serve-llamacpp \
	build app-host stack-cpu stack-nvidia stack-amd down logs ps model

help: ## Show the available commands.
	@printf '%s\n' \
		'make setup          Install the locked Python environment' \
		'make run-native     Run the app locally with native Ollama' \
		'make serve-vllm MODEL=…       Serve a Hugging Face model with vLLM' \
		'make run-vllm                 Run the app against vLLM on port 8001' \
		'make serve-llamacpp MODEL=…   Serve a local GGUF with llama.cpp' \
		'make run-llamacpp             Run the app against llama.cpp on port 8002' \
		'make build          Build the app image' \
		'make app-host       Run the app container with Ollama on the host' \
		'make stack-cpu      Run the app and CPU-only Ollama in Docker' \
		'make stack-nvidia   Run the app and NVIDIA Ollama in Docker (Linux)' \
		'make stack-amd      Run the app and AMD ROCm Ollama in Docker (Linux)' \
		'make model MODEL=…  Pull a model into Compose Ollama (starts it if needed)' \
		'make logs           Follow Compose logs' \
		'make ps             Show Compose service status' \
		'make down           Stop the Compose stack' \
		'' \
		'Add UP_FLAGS=-d to a Compose start target to run in the background.' \
		'Compose context length follows config.yaml; override with OLLAMA_CONTEXT_LENGTH=…'

setup: ## Install the locked Python environment.
	uv sync

run-native: ## Run the app locally with Ollama on localhost.
	AI_CHAT_BASE_URL=http://localhost:11434/v1 uv run chainlit run src/app.py

serve-vllm: ## Serve MODEL with vLLM, aliased to the configured app model name.
	@if [ -z "$(MODEL)" ]; then echo 'Usage: make serve-vllm MODEL=<Hugging-Face-model-or-path>'; exit 2; fi
	SERVER_HOST="$(SERVER_HOST)" SERVER_PORT="$(VLLM_PORT)" \
		SERVED_MODEL_NAME="$(APP_MODEL_NAME)" MAX_MODEL_LEN="$(CONFIG_CONTEXT_LENGTH)" \
		./scripts/serve-vllm.sh "$(MODEL)"

run-vllm: ## Run the app locally against vLLM.
	AI_CHAT_BASE_URL=http://localhost:$(VLLM_PORT)/v1 uv run chainlit run src/app.py

serve-llamacpp: ## Serve the local GGUF MODEL with llama.cpp.
	@if [ -z "$(MODEL)" ]; then echo 'Usage: make serve-llamacpp MODEL=/path/to/model.gguf'; exit 2; fi
	SERVER_HOST="$(SERVER_HOST)" SERVER_PORT="$(LLAMACPP_PORT)" \
		SERVED_MODEL_NAME="$(APP_MODEL_NAME)" MAX_MODEL_LEN="$(CONFIG_CONTEXT_LENGTH)" \
		./scripts/serve-llamacpp.sh "$(MODEL)"

run-llamacpp: ## Run the app locally against llama.cpp.
	AI_CHAT_BASE_URL=http://localhost:$(LLAMACPP_PORT)/v1 uv run chainlit run src/app.py

build: ## Build the app image.
	docker build -t ai-chat .

app-host: ## Run the app container with Ollama on the Docker host.
	AI_CHAT_BASE_URL=http://host.docker.internal:11434/v1 \
		AI_CHAT_API_KEY=ollama $(COMPOSE) up --build $(UP_FLAGS) app

stack-cpu: ## Run the app and CPU-only Ollama in Docker.
	AI_CHAT_API_KEY=ollama $(COMPOSE) up --build $(UP_FLAGS) app ollama

stack-nvidia: ## Run the app and NVIDIA Ollama in Docker on Linux.
	AI_CHAT_API_KEY=ollama $(NVIDIA_COMPOSE) up --build $(UP_FLAGS) app ollama

stack-amd: ## Run the app and AMD ROCm Ollama in Docker on Linux.
	AI_CHAT_API_KEY=ollama $(AMD_COMPOSE) up --build $(UP_FLAGS) app ollama

model: ## Pull MODEL into Compose Ollama, starting the service if needed.
	@if [ -z "$(MODEL)" ]; then echo 'Usage: make model MODEL=<model-name>'; exit 2; fi
	$(COMPOSE) up --detach ollama
	$(COMPOSE) exec ollama ollama pull "$(MODEL)"

logs: ## Follow Compose logs.
	$(COMPOSE) logs --follow

ps: ## Show Compose service status.
	$(COMPOSE) ps

down: ## Stop the Compose stack without deleting models.
	$(COMPOSE) down
