# MoneyFast RAG service: test and coverage targets.
#
# Tabs matter in a Makefile. If you retype these recipes, keep the leading
# tab characters or make will report "missing separator".

PYTHON      ?= python3
PIP         ?= $(PYTHON) -m pip
PYTEST      ?= $(PYTHON) -m pytest
COVERAGE_MIN ?= 95

.DEFAULT_GOAL := help
.PHONY: help install install-test test test-fast coverage lint clean ci

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime dependencies
	$(PIP) install --no-cache-dir -r requirements.txt

install-test: ## Install test dependencies
	$(PIP) install --no-cache-dir -r requirements-test.txt

test: ## Run the unit suite with the coverage gate
	$(PYTEST)

test-fast: ## Run the suite without coverage (quick inner loop)
	$(PYTEST) --no-cov -q

coverage: ## Run tests and print a per-file coverage report
	$(PYTEST) --cov=. --cov-branch \
		--cov-report=term-missing \
		--cov-report=xml:coverage.xml \
		--cov-fail-under=$(COVERAGE_MIN)

lint: ## Style check (optional; skipped when ruff is absent)
	@$(PYTHON) -m ruff check . 2>/dev/null || echo "ruff not installed, skipping"

clean: ## Remove test and coverage artefacts
	rm -rf .pytest_cache htmlcov coverage.xml .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

ci: install install-test test ## Full pipeline used by the Docker test stage
