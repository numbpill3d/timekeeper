.PHONY: test web-build compose-config check

test:
	pytest -q

web-build:
	cd apps/web && npm ci && npm run build

compose-config:
	docker compose config --quiet

check: test web-build
