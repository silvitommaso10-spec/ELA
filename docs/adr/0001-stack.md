# 0001. Stack tecnico del Core

- **Stato:** Accettata
- **Data:** 2026-09-04
- **Riferimenti spec:** §48, §49, §51, §52, §53, §54

## Contesto

La v0.1 di ELA è "il nucleo professionale sul quale costruire tutto il resto" e deve essere
"piccola, rigorosa e verificabile" (§54). Il Core è in Python; i nodi Mac/Windows/iPhone
arriveranno in fasi successive. Servono da subito uno strumento di gestione del progetto,
regole di qualità automatiche e un modo per rendere l'architettura un contratto verificabile
(§52) invece di semplice documentazione.

## Decisione

| Ambito | Scelta |
|--------|--------|
| Linguaggio | Python 3.12 (`requires-python >= 3.12`, `.python-version`) |
| Gestione progetto e dipendenze | `uv` con `pyproject.toml`, `uv.lock` e build backend `uv_build`; layout `src/` con package `ela` |
| Modello di dominio | `pydantic` per le entità pure di `domain.py` (aggiunto come dipendenza runtime quando `domain.py` avrà contenuto) |
| Configurazione | `pydantic-settings` + `.env` (mai nel repo; `.env.example` versionato) |
| Lint e formattazione | `ruff` (check + format), line length 100, regole `E F W I UP B SIM` |
| Type checking | `mypy --strict` su `src/` |
| Test | `pytest` con `pytest-cov` (branch coverage su `ela`) e `hypothesis` per i test property-based |
| Architettura | `import-linter` (contratti in `pyproject.toml`) più architecture test in `tests/architecture/` |
| Pre-commit | `pre-commit` con ruff, mypy e `detect-secrets` |

Nessuna dipendenza runtime viene aggiunta finché non esiste codice che la richiede.

## Alternative considerate

- **Poetry / pip-tools** — uv copre lockfile, ambienti e gestione delle versioni Python in
  un solo strumento, con risoluzione molto più rapida.
- **hatchling come build backend** — funzionalmente equivalente per un package puro Python;
  `uv_build` evita una dipendenza aggiuntiva e resta allineato allo strumento scelto.
- **black + isort + flake8** — ruff li sostituisce tutti con una sola configurazione.
- **pyright** — mypy in modalità strict è più diffuso nell'ecosistema pydantic e ha un plugin
  dedicato; la scelta può essere rivista in un ADR successivo.
- **dataclasses / attrs per il dominio** — pydantic offre validazione dichiarativa e schema
  JSON, utili per Capability (§28) e per i contratti API (§54).
- **Solo architecture test in pytest, senza import-linter** — import-linter esprime i vincoli
  di dipendenza come configurazione leggibile; i test pytest restano per le regole che
  import-linter non può esprimere.

## Conseguenze

- `make check` (lint + typecheck + test) è il criterio minimo per ogni milestone.
- Ogni nuova regola architetturale richiede un contratto import-linter o un test in
  `tests/architecture/` (CLAUDE.md, "Qualità").
- `detect-secrets` mantiene una baseline (`.secrets.baseline`) che va aggiornata
  consapevolmente quando cambia.
- Python 3.12 esclude per ora versioni precedenti: accettabile, il Core gira su macchine
  dell'utente.
