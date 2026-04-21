.PHONY: install run test smoke lint fmt docs-check help

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  install     create .venv and install with dev dependencies"
	@echo "  run         start SwitchBoard in dev mode (reload enabled)"
	@echo "  test        run full test suite"
	@echo "  smoke       smoke-test a running instance (requires make run)"
	@echo "  lint        check code style with ruff"
	@echo "  fmt         auto-format with ruff"
	@echo "  docs-check  verify all doc-referenced files exist"

install:
	uv sync

run:
	bash scripts/run_dev.sh

test:
	uv run pytest -q

smoke:
	bash scripts/smoke_test.sh

lint:
	uv run ruff check src test

fmt:
	uv run ruff format src test

docs-check:
	bash scripts/check_docs.sh
