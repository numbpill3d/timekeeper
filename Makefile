.PHONY: test lint web-build mobile-typecheck compose-config check

PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)
COMPOSE ?= docker-compose
ENV_FILE ?= .env

test:
	$(PYTHON) -m pytest -q

lint:
	ruff check api services shared tests

web-build:
	cd apps/web && npm ci && npm run build

mobile-typecheck:
	cd apps/mobile && npm ci && npm run typecheck

compose-config:
	TIMEKEEPER_ENV_FILE=$(ENV_FILE) $(COMPOSE) --env-file $(ENV_FILE) config --quiet

check: test lint web-build mobile-typecheck
