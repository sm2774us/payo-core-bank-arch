.PHONY: test test-ledger test-screening test-worker lint fmt compose-up compose-down

test: test-ledger test-screening test-worker

test-ledger:
	cd services/ledger-core && pip install -q -e ".[dev]" && pytest -q

test-screening:
	cd services/sanctions-screening && pip install -q -e ".[dev]" && pytest -q

test-worker:
	cd services/reconciliation-worker && pip install -q -e ".[dev]" && pytest -q

lint:
	pre-commit run --all-files

compose-up:
	docker compose up --build

compose-down:
	docker compose down -v
