.PHONY: install lint typecheck test cov-critical milestones secrets check

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

# Security-critical packages (CLAUDE.md "Qualità", spec §51): 100% branch coverage is a gate.
# Add ela.permissions and ela.audit here when they have code.
CRITICAL_PACKAGES = ela.tasks

cov-critical:
	$(UV) run pytest -o addopts="" -q $(foreach p,$(CRITICAL_PACKAGES),--cov=$(p)) \
		--cov-branch --cov-fail-under=100 --cov-report=term-missing

milestones:
	$(UV) run python scripts/check_milestone.py

secrets:
	$(UV) run detect-secrets-hook --baseline .secrets.baseline $$(git ls-files)

check: lint typecheck test cov-critical milestones secrets
