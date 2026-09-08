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
# ela.executive is the only caller of a tool and ela.tools guards the workspace (M5.1);
# ela.devices decides whether a node may be used at all (M6.1, ADR 0016); ela.providers is the
# boundary the user's content crosses to leave this machine and the place where it is decided
# whether a failed call is tried again (M7.1, ADR 0020 §11); ela.routing decides *where* that
# content goes and refuses to send it to a provider nobody chose (M7.3, ADR 0022).
# ela.api è l'unica porta da cui un "sì" dell'utente entra nel sistema e l'unica che controlla il
# token; ela.composition decide chi parla con chi e rifiuta una configurazione sbagliata
# (M8.1, ADR 0023 §12). ela.cli porta il token in un header ed è la tastiera su cui quel "sì"
# viene scritto: se sbaglia comando o esce con il codice sbagliato, sbaglia l'utente
# (M8.2, ADR 0024 §7).
# ela.perception decide che cosa ELA crede di sapere della macchina su cui gira, compreso quando
# non sa: entra nel gate nella milestone che gli dà codice (M10.1, ADR 0028 §1).
# ela.infrastructure.perception NON entra, e il criterio è scritto nell'ADR: un package entra nel
# gate quando ogni suo ramo può essere eseguito in CI, e nessun runner ha una webcam. Dove questo
# è falso il package non deve contenere nessun ramo che decida qualcosa — ed è la regola 34 a
# renderlo vero invece che promesso.
CRITICAL_PACKAGES = ela.tasks ela.infrastructure.persistence ela.audit ela.permissions \
	ela.executive ela.tools ela.devices ela.providers ela.routing ela.api ela.composition \
	ela.cli ela.perception ela.context

cov-critical:
	$(UV) run pytest -o addopts="" -q $(foreach p,$(CRITICAL_PACKAGES),--cov=$(p)) \
		--cov-branch --cov-fail-under=100 --cov-report=term-missing

milestones:
	$(UV) run python scripts/check_milestone.py

secrets:
	$(UV) run detect-secrets-hook --baseline .secrets.baseline $$(git ls-files)

check: lint typecheck test cov-critical milestones secrets
