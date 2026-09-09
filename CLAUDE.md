# ELA — Executive Life Assistant

## Cosa stai costruendo
ELA è un assistente personale AI distribuito (Core Python, nodi Mac/Windows/iPhone).
La specifica completa è in `docs/spec/ELA_spec.md`. È la fonte di verità: in caso di
dubbio leggila. Non inventare comportamenti non descritti lì.

## Regola fondamentale
Lavori su UNA milestone alla volta, quella indicata nel prompt. Non anticipare
milestone future, non creare stub "per dopo", non aggiungere feature non richieste.
Ciclo obbligatorio: SPEC → IMPLEMENTATION → TEST → REVIEW → COMMIT → NEXT
MILESTONE.
Alla fine della milestone committi e pushi sul branch di lavoro. Non fai mai merge su main
e non usi mai --force: il merge lo fa l'utente dopo revisione esterna.

## Prima di scrivere codice
1. Leggi `docs/spec/ELA_spec.md` (sezioni rilevanti) e `docs/adr/`.
2. Scrivi in `docs/milestones/<id>.md` la SPEC della milestone: cosa entra, cosa NON entra,
   criteri di accettazione, test previsti. Fermati e mostramela prima di implementare
   (usa plan mode).
3. Se la spec del documento è ambigua, elenca le interpretazioni possibili e chiedi.
   Non scegliere in silenzio.

## Architettura (non negoziabile)
- `src/ela/domain.py`: entità pure (pydantic), zero I/O, zero import da infrastruttura.
- `src/ela/ports.py`: interfacce (Protocol/ABC). Nessun import di provider concreti.
- Il Core non importa mai `anthropic`, `openai`, `sqlalchemy`, `fastapi`, `httpx`.
  Solo `providers/`, `infrastructure/`, `api/` possono farlo.
- Un Tool non può essere eseguito senza una `PermissionDecision` del Guardian.
  Il Guardian non possiede tool: decide su Capability + contesto.
- Capability (spec, rischio, schema, scope) ≠ Tool (implementazione).
- Task state machine deterministica: transizioni illegali sollevano eccezione.
- Audit Log append-only: nessuna API di update/delete.
- Fail-safe: in caso di dubbio l'azione è DENIED, mai eseguita.
- Nessun secret nel repo. Config via `pydantic-settings` + `.env`.

## Qualità
- `ruff check`, `ruff format`, `mypy --strict src/` devono passare.
- `pytest` deve passare. Moduli security-critical (`permissions/`, `audit/`, `tasks/`):
  100% branch coverage.
- Il gate `cov-critical` del Makefile (`CRITICAL_PACKAGES`) si estende a `permissions/` e
  `audit/` nella stessa milestone in cui il package riceve codice, non dopo.
- Ogni nuova regola architetturale → un architecture test in `tests/architecture/`.
- Ogni bug trovato → prima un test che fallisce, poi il fix.
- Tutto ciò che gira in `make check` ha un test che ne dimostra il fallimento nel caso
  negativo.
- **`make check` si lancia in primo piano, una volta, e si aspetta lì.** Non in background, non
  sorvegliato da un monitor, non interrogato a intervalli: il ciclo dura tre minuti e il polling
  costa più del lavoro che sorveglia. Una volta è costato sei ore.
- **`make check-linux` prima di ogni push.** `make check` gira su una macchina sola, e una suite
  che eredita da quella macchina passa lì e fallisce sull'altra — è successo il 2026-09-08, e la
  CI se n'è accorta undici minuti dopo il merge. Questo target rifà la suite e il gate della
  copertura fingendo l'altra metà della matrice. **Ha dei limiti e sono scritti in
  `tests/foreign_machine.py`**: finge `platform.system()` e i tre binari di Apple, e nient'altro
  — resta CPython su macOS, non dimostra che Linux funzioni, e non dice niente su tempi e
  installazione. Verde lì significa che la suite non sta ereditando la macchina; verde sul runner
  vero resta l'unica cosa che conta.
- **Un test afferma solo ciò di cui ha costruito le precondizioni.** Se gli serve una macchina
  vera, la dichiara con uno `skipif`, che compare nel riepilogo — un `if` dentro il test no
  (ADR 0031 §6). Una precondizione che non si può costruire dichiarando il sistema si costruisce
  iniettando la dipendenza: `available()` legge il filesystem, non `platform.system()`.

## Fine sessione
Produci un riepilogo con: file toccati, test aggiunti, output di `pytest -q --cov`,
cosa hai semplificato o lasciato aperto, domande per la review.
Alla fine della milestone committi e pushi sul branch di lavoro. Non fai mai merge su main
e non usi mai --force: il merge lo fa l'utente dopo revisione esterna.
