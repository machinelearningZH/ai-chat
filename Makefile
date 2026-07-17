SHELL := /bin/sh
.DEFAULT_GOAL := help

CONFIG_CONTEXT_LENGTH = $(shell UV_NO_CACHE=1 PYTHONPATH=src uv run --no-sync python -c 'from ai_chat.config import default_model_context_length, load_config; print(default_model_context_length(load_config()))')
OLLAMA_CONTEXT_LENGTH ?= $(CONFIG_CONTEXT_LENGTH)
COMPOSE = OLLAMA_CONTEXT_LENGTH=$(OLLAMA_CONTEXT_LENGTH) docker compose -f compose.yaml
NVIDIA_COMPOSE = $(COMPOSE) -f compose.nvidia.yaml
AMD_COMPOSE = $(COMPOSE) -f compose.amd.yaml
OLLAMA_VERSION ?= 0.32.0
UP_FLAGS ?=

export OLLAMA_VERSION

.PHONY: help setup run-native build app-host stack-cpu stack-nvidia stack-amd \
	down logs ps model

help: ## Show the available commands.
	@printf '%s\n' \
		'make setup          Install the locked Python environment' \
		'make run-native     Run the app locally with native Ollama' \
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
