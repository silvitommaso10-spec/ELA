.PHONY: install lint typecheck test cov-critical check-linux milestones secrets check

UV ?= uv

install:
	$(UV) sync

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run lint-imports

typecheck:
	$(UV) run mypy --strict src/

# Una esecuzione sola, due gate (2026-09-12). Fino a qui `make check` faceva girare la suite due
# volte — `test` e `cov-critical` — e la seconda misurava le stesse righe della prima con un
# `--cov` più stretto: quattro minuti pagati per un filtro. `addopts` in pyproject.toml misura già
# tutto `ela` con i rami, quindi la suite gira qui, una volta, e lascia `.coverage`; i due gate di
# `make check` — la suite verde, e il 100% di ramo sui package critici — leggono quel file. Stessa
# severità: la prova è che il totale del gate non è cambiato di una riga (7490 stmt, 1324 branch).
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
# ela.node tiene un segreto su disco ed esegue tool su una macchina che il Core non è: entra nel
# gate nella milestone che gli dà codice (M12.3, ADR 0039 §1), e il criterio d'ingresso di ADR 0028
# §1 è soddisfatto — ogni ramo del ciclo di un nodo gira in CI, perché nessuno di essi ha bisogno
# di una macchina (i quattro tool sì, e restano dove sono).
# ela.infrastructure.machine NON entra, e il criterio è scritto nell'ADR: un package entra nel
# gate quando ogni suo ramo può essere eseguito in CI, e nessun runner ha una webcam. Dove questo
# è falso il package non deve contenere nessun ramo che decida qualcosa — ed è la regola 34 a
# renderlo vero invece che promesso.
CRITICAL_PACKAGES = ela.tasks ela.infrastructure.persistence ela.audit ela.permissions \
	ela.executive ela.tools ela.devices ela.providers ela.routing ela.api ela.composition \
	ela.cli ela.perception ela.context ela.node

# Gli stessi package come pattern di file, derivati dalla lista qui sopra e non riscritti accanto
# a essa: una seconda lista si disallinea alla prima milestone distratta. `coverage report` vuole
# un `--include` solo, separato da virgole.
empty :=
space := $(empty) $(empty)
comma := ,
CRITICAL_INCLUDE = \
	$(subst $(space),$(comma),$(foreach p,$(CRITICAL_PACKAGES),src/$(subst .,/,$(p))/*))

# Il gate, scritto una volta sola perché `cov-critical` e `check-linux` lo chiedono entrambi e due
# copie divergono. Un `--include` che non trova nessun file non è un 100% silenzioso: `coverage
# report` risponde «No data to report.» ed esce 1 — il caso di un package scritto male sta in
# tests/scripts/test_coverage_gates.py insieme agli altri due.
COVERAGE_CRITICAL = $(UV) run coverage report --include='$(CRITICAL_INCLUDE)' \
	--fail-under=100 --show-missing

# Dipende da `test` e non dal file `.coverage`: chiamato da solo fa girare la suite invece di
# leggere la misura di ieri, e dentro `make check` gira comunque una volta sola.
cov-critical: test
	$(COVERAGE_CRITICAL)

# La seconda macchina, prima del push (2026-09-09). `make check` gira su una macchina sola, e una
# suite che eredita da quella macchina passa lì e fallisce sull'altra: è successo, e la CI se n'è
# accorta undici minuti dopo il merge. Questo target esegue la suite e il gate della copertura
# fingendo l'altra metà della matrice — `tests/foreign_machine.py` dice cosa finge e, soprattutto,
# **cosa non può riprodurre**. Non entra in `make check`: è il controllo prima di un push, e
# raddoppierebbe l'attesa di ogni ciclo.
check-linux:
	PYTHONPATH=. $(UV) run pytest -p tests.foreign_machine
	$(COVERAGE_CRITICAL)

milestones:
	$(UV) run python scripts/check_milestone.py

secrets:
	$(UV) run detect-secrets-hook --baseline .secrets.baseline $$(git ls-files)

check: lint typecheck test cov-critical milestones secrets
