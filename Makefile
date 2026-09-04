.PHONY: install lint typecheck test check

UV ?= uv

install:
	$(UV) sync

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run lint-imports

typecheck:
	$(UV) run mypy --strict src/

test:
	$(UV) run pytest

check: lint typecheck test
