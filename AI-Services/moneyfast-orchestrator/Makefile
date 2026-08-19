# MoneyFast orchestrator: test, coverage and container targets.
#
# Tabs matter. If you retype a recipe, keep the leading tab or make will
# report "missing separator".

PYTHON       ?= python
PIP          ?= $(PYTHON) -m pip
PYTEST       ?= $(PYTHON) -m pytest
COVERAGE_MIN ?= 100
IMAGE        ?= moneyfast-orchestrator

.DEFAULT_GOAL := help
.PHONY: help install install-test test test-fast coverage coverage-html \
        lint clean ci docker-test docker-build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime dependencies
	$(PIP) install --no-cache-dir -r requirements.txt

install-test: ## Install runtime + test dependencies
	$(PIP) install --no-cache-dir -r requirements.txt -r requirements-test.txt

test: ## Run the suite with the 100% line + branch coverage gate
	$(PYTEST)

test-fast: ## Run the suite without coverage (quick inner loop)
	$(PYTEST) --no-cov -q

coverage: ## Run tests and print a per-file coverage report
	$(PYTEST) --cov --cov-branch \
		--cov-report=term-missing \
		--cov-report=xml:coverage.xml \
		--cov-fail-under=$(COVERAGE_MIN)

coverage-html: ## Generate the browsable HTML report
	$(PYTEST) --cov --cov-branch --cov-report=html:htmlcov --cov-fail-under=$(COVERAGE_MIN)
	@echo "Open htmlcov/index.html"

lint: ## Style check (skipped when ruff is absent)
	@$(PYTHON) -m ruff check . 2>/dev/null || echo "ruff not installed, skipping"

clean: ## Remove test and coverage artefacts
	rm -rf .pytest_cache htmlcov coverage.xml .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

ci: install-test test ## Pipeline used by the Docker test stage

docker-test: ## Build only the test stage; fails the build if the gate fails
	docker build --target test -t $(IMAGE):test .

docker-build: docker-test ## Build the shipping image after the gate passes
	docker build --target runtime -t $(IMAGE):latest .
