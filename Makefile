# =============================================================================
# Makefile — convenience tasks for Unix-friendly devs.
#
# WHY THIS EXISTS
#   `./build.sh` is the canonical full-build entry point. Make wraps the common
#   per-task commands so you can type `make test` instead of remembering the
#   per-stack incantation. It MUST stay in sync with build.sh and scripts/.
#
# Tabs matter in Makefiles. Recipes are tab-indented. Do not convert to spaces.
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: help build run test test-unit test-integration test-e2e lint fmt clean docker docker-run deploy

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Clean-clone -> running prerequisites met (delegates to build.sh)
	./build.sh

run: ## Run the service locally
	./scripts/run.sh

test: ## Run all tests
	./scripts/test.sh

test-unit: ## Run unit tests only
	./scripts/test.sh unit

test-integration: ## Run integration tests only
	./scripts/test.sh integration

test-e2e: ## Run end-to-end tests (Selenium / Playwright)
	./scripts/test.sh e2e

lint: ## Lint + format check (no changes)
	./scripts/lint.sh

fmt: ## Lint + format with --fix
	./scripts/lint.sh --fix

clean: ## Remove build artifacts and caches
	rm -rf .venv node_modules bin obj dist build .pytest_cache __pycache__ htmlcov

docker: ## Build Docker image
	docker build -t $(shell basename $(CURDIR)):local .

docker-run: ## Run Docker image with local .env
	docker run --rm -p 8000:8000 --env-file .env $(shell basename $(CURDIR)):local

deploy: ## Deploy to the platform configured in scripts/deploy.sh
	./scripts/deploy.sh
