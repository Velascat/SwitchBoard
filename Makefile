.PHONY: install run test smoke smoke-aider lint fmt docs-check help

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  install      install with dev dependencies (uv sync)"
	@echo "  run          start SwitchBoard in dev mode (reload enabled)"
	@echo "  test         run full test suite"
	@echo "  smoke        smoke-test a running instance (requires make run)"
	@echo "  smoke-aider  Aider reference client smoke test (requires make run + bootstrap_aider)"
	@echo "  lint         check code style with ruff"
	@echo "  fmt          auto-format with ruff"
	@echo "  docs-check   verify all doc-referenced files exist"

install:
	uv sync

run:
	bash scripts/run_dev.sh

test:
	uv run pytest -q

smoke:
	bash scripts/smoke_test.sh

smoke-aider:
	bash scripts/aider_smoke.sh

lint:
	uv run ruff check src test

fmt:
	uv run ruff format src test

docs-check:
	bash scripts/check_docs.sh
