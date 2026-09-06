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
# ela.infrastructure.persistence is here because it keeps the authorizations the Guardian consumes
# (M2.1) and the audit log (M2.2); ela.audit holds the hash chain that makes the log tamper-evident
# (M2.2); ela.permissions holds the capability catalogue (M4.1) and the Guardian (M4.2);
# ela.executive is the only caller of a tool and ela.tools guards the workspace (M5.1).
CRITICAL_PACKAGES = ela.tasks ela.infrastructure.persistence ela.audit ela.permissions \
	ela.executive ela.tools

cov-critical:
	$(UV) run pytest -o addopts="" -q $(foreach p,$(CRITICAL_PACKAGES),--cov=$(p)) \
		--cov-branch --cov-fail-under=100 --cov-report=term-missing

milestones:
	$(UV) run python scripts/check_milestone.py

secrets:
	$(UV) run detect-secrets-hook --baseline .secrets.baseline $$(git ls-files)

check: lint typecheck test cov-critical milestones secrets
