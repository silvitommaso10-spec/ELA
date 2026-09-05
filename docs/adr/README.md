# Architecture Decision Records

Ogni decisione architetturale significativa viene registrata qui (spec §48: "ogni modifica
architetturale significativa deve essere documentata"). Un ADR è immutabile: se una decisione
cambia, si scrive un nuovo ADR che sostituisce il precedente.

## Indice

| ID | Titolo | Stato |
|----|--------|-------|
| [0001](0001-stack.md) | Stack tecnico del Core | Accettata |
| [0002](0002-architecture-rules.md) | Regole di dipendenza e come vengono verificate | Accettata |
| [0003](0003-domain-model.md) | Forma del domain model: identità, tempo, immutabilità, ordine del rischio | Accettata |
| [0004](0004-task-transitions.md) | Transizioni di stato del Task e forma della funzione `transition` | Accettata |
| [0005](0005-ports.md) | Forma dei ports: async dove c'è I/O, errori nominati, tool senza Guardian, fake in `ela.testing` | Accettata |
| [0006](0006-persistence.md) | Persistenza: SQLAlchemy async su SQLite, ORM separato dal dominio, migrazioni alembic | Accettata |
| [0007](0007-audit-log.md) | Audit log persistente: hash chain, quattro livelli di append-only | Accettata |
| [0008](0008-task-engine.md) | Task Engine: tabella delle operazioni, idempotenza, ordine delle scritture, heartbeat come evento, piano persistito, recovery | Accettata |
| [0009](0009-task-graph.md) | Task Graph: DAG degli step, stato derivato dalla trail, operazioni per step, propagazione dei fallimenti | Accettata |
| [0010](0010-capability-catalogue.md) | Catalogo delle capability v0.1: registro immutabile, port ridotto, validazione JSON Schema, rischio massimo MEDIUM | Accettata |
| [0011](0011-permission-guardian.md) | Permission Guardian: catalogo, policy v0.1 per rischio, scope, autorizzazioni, fail-safe, audit delle decisioni | Accettata |

## Template

Nome file: `NNNN-titolo-breve.md` (numero progressivo a 4 cifre).

```markdown
# NNNN. Titolo della decisione

- **Stato:** Proposta | Accettata | Deprecata | Sostituita da NNNN
- **Data:** AAAA-MM-GG
- **Riferimenti spec:** §N, §M

## Contesto

Qual è il problema o la forza in gioco che richiede una decisione.

## Decisione

Cosa si è deciso, in forma attiva ("Usiamo X per Y").

## Alternative considerate

- **Alternativa A** — perché è stata scartata.
- **Alternativa B** — perché è stata scartata.

## Conseguenze

Effetti positivi, negativi e vincoli che la decisione introduce (inclusi i test di
architettura che la rendono verificabile).
```
