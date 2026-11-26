SHELL := /bin/sh
.DEFAULT_GOAL := help

CONFIG_CONTEXT_LENGTH = $(shell UV_NO_CACHE=1 PYTHONPATH=src uv run --no-sync python -c 'from ai_chat.config import default_model_context_length, load_model_config; print(default_model_context_length({"model": load_model_config()}))')
CONFIG_MODEL_NAME = $(shell UV_NO_CACHE=1 PYTHONPATH=src uv run --no-sync python -c 'from ai_chat.config import load_model_config; print(load_model_config()["default_selection"])')
OLLAMA_CONTEXT_LENGTH ?= $(CONFIG_CONTEXT_LENGTH)
COMPOSE = OLLAMA_CONTEXT_LENGTH=$(OLLAMA_CONTEXT_LENGTH) docker compose -f compose.yaml
COMPOSE_NO_CONTEXT = OLLAMA_CONTEXT_LENGTH=1 docker compose -f compose.yaml
NVIDIA_COMPOSE = $(COMPOSE) -f compose.nvidia.yaml
AMD_COMPOSE = $(COMPOSE) -f compose.amd.yaml
OLLAMA_VERSION ?= 0.32.0
UP_FLAGS ?=
APP_MODEL_NAME ?= $(CONFIG_MODEL_NAME)
SERVER_HOST ?= 127.0.0.1
VLLM_PORT ?= 8001
LLAMACPP_PORT ?= 8002
STATS_SOURCE ?= auto
STATS_ARGS = $(if $(SINCE),--since "$(SINCE)") $(if $(BY),--by "$(BY)") \
	$(if $(filter-out 0 false FALSE no NO,$(DETAILED)),--detailed)

export OLLAMA_VERSION

.PHONY: help setup update-packages test lint format check run-native run-vllm run-llamacpp serve-vllm serve-llamacpp \
	build app-host stack-cpu stack-nvidia stack-amd down logs ps model stats

help: ## Show the available commands.
	@printf '%s\n' \
		'make setup          Install the Python environment' \
		'make update-packages  Upgrade, check, commit, and push the lockfile' \
		'make test           Run the test suite' \
		'make lint           Run the Ruff linter' \
		'make format         Format code with Ruff' \
		'make check          Run formatting check, linter, and tests' \
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
		'make stats          Show the usage statistics (DETAILED=1 for every counter)' \
		'make down           Stop the Compose stack' \
		'' \
		'Add UP_FLAGS=-d to a Compose start target to run in the background.' \
		'Add SINCE=YYYY-MM-DD, BY=day, or STATS_SOURCE=native|compose to make stats.' \
		'Compose context length follows config.yaml; override with OLLAMA_CONTEXT_LENGTH=…'

setup: ## Install the Python environment.
	uv sync

update-packages: ## Upgrade dependencies, verify checks, and push the lockfile from a feature branch.
	@branch=$$(git symbolic-ref --quiet HEAD) && [ "$$branch" != refs/heads/main ] || { \
		echo 'Run update-packages on a branch other than main.' >&2; exit 1; \
	}
	@changes=$$(git status --porcelain --untracked-files=no) && [ -z "$$changes" ] || { \
		echo 'Commit or stash tracked changes before running update-packages.' >&2; exit 1; \
	}
	@base=$$(git rev-parse --verify HEAD); \
	branch=$$(git symbolic-ref --quiet HEAD); \
	tab=$$(printf '\t'); \
	remote_rc=0; \
	remote_head=$$(git ls-remote --exit-code origin "$$branch") || remote_rc=$$?; \
	if [ "$$remote_rc" -eq 0 ]; then \
		[ "$$remote_head" = "$$base$${tab}$$branch" ] || { \
			echo 'The current branch must match origin before updating dependencies.' >&2; exit 1; \
		}; \
	elif [ "$$remote_rc" -eq 2 ]; then \
		origin_main=$$(git ls-remote --exit-code origin refs/heads/main) || { \
			echo 'Could not verify origin/main before updating dependencies.' >&2; exit 1; \
		}; \
		[ "$$origin_main" = "$$base$${tab}refs/heads/main" ] || { \
			echo 'A new topic branch must start from origin/main before updating dependencies.' >&2; exit 1; \
		}; \
	else \
		echo 'Could not query origin before updating dependencies.' >&2; exit 1; \
	fi
	uv lock --upgrade
	uv sync
	$(MAKE) check
	@status=$$(git status --porcelain --untracked-files=no); \
	case "$$status" in \
		'') echo 'Dependencies are up to date.' ;; \
		' M uv.lock') git commit --only -m 'chore: update packages' -- uv.lock && git push origin HEAD ;; \
		*) echo 'Expected only an unstaged uv.lock change after the checks.' >&2; exit 1 ;; \
	esac

test: ## Run the test suite.
	uv run pytest

lint: ## Run the Ruff linter.
	uv run ruff check .

format: ## Format code with Ruff.
	uv run ruff format .

check: ## Run formatting check, linter, and tests.
	uv run ruff format --check .
	uv run ruff check .
	uv run pytest

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
	$(COMPOSE_NO_CONTEXT) exec ollama ollama pull "$(MODEL)"

logs: ## Follow Compose logs.
	$(COMPOSE_NO_CONTEXT) logs --follow

ps: ## Show Compose service status.
	$(COMPOSE_NO_CONTEXT) ps

stats: ## Show usage statistics of the Compose app or volume, else of the native app.
	@case "$(STATS_SOURCE)" in \
		native) \
			echo 'Source: native app'; \
			PYTHONPATH=src uv run --no-sync python -m ai_chat.usage_report $(STATS_ARGS); \
			;; \
		compose) \
			if [ -n "$$($(COMPOSE_NO_CONTEXT) ps --quiet app 2>/dev/null)" ]; then \
				echo 'Source: Compose app'; \
				$(COMPOSE_NO_CONTEXT) exec -T app env PYTHONPATH=src python -m ai_chat.usage_report $(STATS_ARGS); \
			else \
				echo 'Source: Compose volume (app is stopped)'; \
				$(COMPOSE_NO_CONTEXT) run --rm --no-deps -T app env PYTHONPATH=src python -m ai_chat.usage_report $(STATS_ARGS); \
			fi; \
			;; \
		auto) \
			if [ -n "$$($(COMPOSE_NO_CONTEXT) ps --quiet app 2>/dev/null)" ]; then \
				echo 'Source: Compose app'; \
				$(COMPOSE_NO_CONTEXT) exec -T app env PYTHONPATH=src python -m ai_chat.usage_report $(STATS_ARGS); \
			elif docker volume inspect ai-chat_usage-stats >/dev/null 2>&1 \
				&& docker image inspect "ai-chat:$${AI_CHAT_TAG:-latest}" >/dev/null 2>&1; then \
				echo 'Source: Compose volume (app is stopped)'; \
				$(COMPOSE_NO_CONTEXT) run --rm --no-deps -T app env PYTHONPATH=src python -m ai_chat.usage_report $(STATS_ARGS); \
			else \
				echo 'Source: native app'; \
				PYTHONPATH=src uv run --no-sync python -m ai_chat.usage_report $(STATS_ARGS); \
			fi; \
			;; \
		*) \
			echo "Invalid STATS_SOURCE='$(STATS_SOURCE)' (expected auto, native, or compose)." >&2; \
			exit 2; \
			;; \
	esac

down: ## Stop the Compose stack and keep models and usage statistics.
	$(COMPOSE_NO_CONTEXT) down
