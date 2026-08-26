.PHONY: help install install-test test test-fast coverage coverage-html lint clean \
        hooks db-export db-load db-dump db-restore

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

# --- Veritabanı paylaşımı ---------------------------------------------------
# Migration'lar şemayı ve enstrüman evrenini kurar ama HİÇBİR migration
# kullanıcı oluşturmaz. Bu hedefler, elle üretilen durumu (kullanıcı, hesap,
# portföy, izleme listesi, sohbet) kullanıcı başına birer dosyaya çıkarır —
# böylece iki kişi kendi test kullanıcısını eklediğinde farklı dosyalara
# dokunur ve git çakışma yaşamaz.
#
# Normalde bunların hiçbirini elle çalıştırmak gerekmez: yükleme her backend
# açılışında, export ise her commit'te olur (`make hooks`). Buradakiler o
# otomatik yolun dışına çıkmak istediğinde var.

# Overridable: Docker needs sudo on some machines and not others.
#   make db-export COMPOSE="sudo docker compose -f ../infra/docker-compose.yml"
COMPOSE ?= docker compose -f ../infra/docker-compose.yml

db-export: ## Yerel DB -> seeds/users/*.sql. Tek kullanıcı: make db-export TC=11111111112
	$(COMPOSE) exec -T backend python -m scripts.export_seeds $(if $(TC),--user $(TC),)

# Backend her açılışta zaten yüklüyor. Bu hedef, yeniden başlatmadan bir takım
# arkadaşının yeni kullanıcısını çekmek için.
db-load: ## Seed dosyalarını elle yükle (idempotent)
	$(COMPOSE) exec -T backend python -m scripts.load_seeds

hooks: ## Otomatik export'u kur (klon başına BİR kez): pre-commit hook'u bağlar
	@git -C .. config core.hooksPath .githooks
	@echo "core.hooksPath=.githooks — commit'lerde seeds/users otomatik güncellenecek"
	@# Docker'a nasıl erişildiğini tespit et. `docker` grubunda olmayan bir
	@# makinede her çağrı sudo ister ve hook parola soramaz; bunu şimdi
	@# saptamazsak export sessizce hiç çalışmaz. Deneme daemon'a gerçekten
	@# bağlanmalı: `docker compose version` istemci tarafında kalır ve
	@# erişim olmasa bile başarılı olur.
	@if docker ps >/dev/null 2>&1; then \
		git -C .. config --unset moneyfast.compose 2>/dev/null || true; \
		echo "docker doğrudan çalışıyor"; \
	elif sudo -n docker ps >/dev/null 2>&1; then \
		git -C .. config moneyfast.compose "sudo docker compose -f infra/docker-compose.yml"; \
		echo "docker sudo ile (parolasız) çalışıyor; hook'a kaydedildi"; \
	else \
		echo ""; \
		echo "UYARI: docker parola istiyor. Hook parola soramaz, bu yüzden"; \
		echo "export her commit'te atlanacak. Kalıcı çözüm (bir kez):"; \
		echo "    sudo usermod -aG docker $$USER   # sonra oturumu kapatıp açın"; \
		echo "Bu yapılana kadar: cd backend && make db-export"; \
	fi

db-dump: ## Tam yedek -> dumps/ (gitignore'da). Riskli bir şeyden ÖNCE çalıştır.
	@mkdir -p ../dumps
	$(COMPOSE) exec -T base-db pg_dump -U $$BASE_DB_USER -d $$BASE_DB_NAME --clean --if-exists \
		> ../dumps/moneyfast-$$(date +%Y%m%d-%H%M%S).sql
	@ls -1t ../dumps | head -1 | sed 's|^|yedek: dumps/|'

db-restore: ## dumps/ içinden geri yükle: make db-restore FILE=dumps/xxx.sql
	@test -n "$(FILE)" || (echo "FILE=dumps/... gerekli"; exit 1)
	$(COMPOSE) exec -T base-db psql -U $$BASE_DB_USER -d $$BASE_DB_NAME < $(FILE)

