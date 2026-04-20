.PHONY: install run test smoke lint

install:
	python -m venv .venv
	.venv/bin/pip install -e ".[dev]" -q

run:
	bash scripts/run_dev.sh

test:
	.venv/bin/pytest -v

smoke:
	bash scripts/smoke_test.sh

lint:
	.venv/bin/ruff check src test
