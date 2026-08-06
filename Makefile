# =============================================================================
# Makefile — convenience tasks for Unix-friendly devs.
#
# WHY THIS EXISTS
#   `./build.sh` (build.bat on Windows) is the canonical clean-clone entry
#   point; it creates `.venv` and installs the package. Every other target
#   calls that venv's python directly — no wrapper scripts (SiteAudit-style).
#   If you add a target, point it at $(PY), not at a shell script.
#
#   There is one pytest suite (tests/, no unit/integration/e2e tiers) — `make
#   test` runs all of it, coverage included, matching CI and CONTRIBUTING.md.
#
# Tabs matter in Makefiles. Recipes are tab-indented. Do not convert to spaces.
# =============================================================================

ifeq ($(OS),Windows_NT)
  PY := .venv/Scripts/python.exe
else
  PY := .venv/bin/python
endif

# `make run` culls FOLDER into the local web UI. ARGS appends raw cull flags,
# e.g.: make run ARGS="--no-serve --json-out"
FOLDER ?= demo/shoot
TOP ?= 10
ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help build seed run test lint fmt clean docker docker-run

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Clean-clone -> running prerequisites met (delegates to build.sh)
	./build.sh

seed: ## Generate demo/shoot (40 synthetic photos) so `make run` works anywhere
	$(PY) demo/seed.py

run: ## Cull FOLDER (default demo/shoot) to the top TOP in the local web UI
	$(PY) -c "from photopicker.cli import cull_main; cull_main()" $(FOLDER) --top $(TOP) $(ARGS)

test: ## Run the full pytest suite with coverage (the only tier there is)
	$(PY) -m pytest

lint: ## Ruff lint — same invocation as CI
	$(PY) -m ruff check photopicker tests

fmt: ## Autofix lint findings + apply ruff format
	$(PY) -m ruff check --fix photopicker tests
	$(PY) -m ruff format photopicker tests

clean: ## Remove build artifacts and caches (keeps .venv and dist/)
	rm -rf build .pytest_cache .ruff_cache htmlcov .coverage coverage.xml
	find photopicker tests -name __pycache__ -type d -prune -exec rm -rf {} +

docker: ## Build Docker image
	docker build -t $(shell basename $(CURDIR)):local .

docker-run: ## Run Docker image with local .env
	docker run --rm -p 8000:8000 --env-file .env $(shell basename $(CURDIR)):local
