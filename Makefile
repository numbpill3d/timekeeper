.PHONY: test lint web-build mobile-typecheck synthetic-fixture compose-config check

PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)
COMPOSE ?= docker-compose
ENV_FILE ?= .env

test:
	$(PYTHON) -m pytest -q

lint:
	ruff check api services shared tests
	ruff check --select B api services shared tests

web-build:
	cd apps/web && npm ci && npm run build

mobile-typecheck:
	cd apps/mobile && npm ci && npm run typecheck

synthetic-fixture:
	test -n "$(OWNER_ID)" -o -n "$(OWNER_EMAIL)" || (echo "set OWNER_ID or OWNER_EMAIL"; exit 2)
	TIMEKEEPER_DEMO_OWNER_ID="$(OWNER_ID)" TIMEKEEPER_DEMO_OWNER_EMAIL="$(OWNER_EMAIL)" $(PYTHON) scripts/seed_synthetic.py

compose-config:
	TIMEKEEPER_ENV_FILE=$(ENV_FILE) $(COMPOSE) --env-file $(ENV_FILE) config --quiet

check: test lint web-build mobile-typecheck
