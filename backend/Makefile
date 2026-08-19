.PHONY: help install install-test test test-fast coverage coverage-html lint clean

COVERAGE_MIN ?= 100

help: ## Bu yardım mesajını göster
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Runtime bağımlılıklarını kur
	pip install -r requirements.txt

install-test: install ## Runtime + test bağımlılıklarını kur
	pip install -r requirements-test.txt

test: ## Testleri %100 coverage gate ile çalıştır (backend/ dizininden)
	pytest

test-fast: ## Testleri coverage ölçmeden hızlıca çalıştır
	pytest --no-cov

coverage: ## Terminal coverage raporu üret
	pytest --cov-report=term-missing

coverage-html: coverage ## HTML coverage raporu üret (htmlcov/index.html)
	@echo "Rapor: htmlcov/index.html"

lint: ## ruff varsa çalıştır
	@command -v ruff >/dev/null 2>&1 && ruff check app tests || echo "ruff kurulu değil, atlanıyor"

clean: ## Test/coverage artefaktlarını temizle
	rm -rf .pytest_cache htmlcov coverage.xml .coverage

ci: install-test test ## CI'da çalıştırılacak tam adım
