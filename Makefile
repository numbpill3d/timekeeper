.PHONY: test web-build compose-config check

PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)
COMPOSE ?= docker-compose
ENV_FILE ?= .env

test:
	$(PYTHON) -m pytest -q

web-build:
	cd apps/web && npm ci && npm run build

compose-config:
	TIMEKEEPER_ENV_FILE=$(ENV_FILE) $(COMPOSE) --env-file $(ENV_FILE) config --quiet

check: test web-build
