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
| [0012](0012-authorizations.md) | Autorizzazioni: nascita da un'Approval, consumo atomico, invariante del grant monouso | Accettata |
| [0013](0013-executor.md) | Executor: uno step per chiamata, grant scelto e consumato prima del tool, ordine delle scritture, `ToolRegistryPort` e `AuthorizingGuardianPort`, tool v0.1 e workspace, regola 16 | Accettata |
| [0014](0014-verification.md) | Verification: condizioni di successo come vocabolario chiuso per capability, `VerifierPort` e `VerifierRegistryPort`, verifica prima di `complete_step`, verifica fallita → task FAILED, `EXECUTION_VERIFIED`, regole 17 e 18 | Accettata |
| [0015](0015-approval-and-result-persistence.md) | Persistenza di Approval ed ExecutionResult: `ApprovalStore` ed `ExecutionResultStore`, la risposta dallo store, ripresa di uno step interrotto, finestre 5, 7b, 8, 8a–8c e 9a riparate, richieste scadute in `recover()`, regola 19 | Accettata |
| [0016](0016-device-registry.md) | Device Registry: disponibilità derivata dall'heartbeat, nodo `local` deterministico, tabella `devices` | Accettata |
| [0017](0017-device-orchestrator.md) | Device Orchestrator: filtri di idoneità, punteggio esplicito per i criteri di §17, attesa invece di fallimento, eventi `DEVICE_SELECTED`/`DEVICE_UNAVAILABLE`, regole 20–22 | Accettata |
| [0018](0018-step-arguments.md) | Gli `arguments` di uno step stanno nel piano (`TaskStep.arguments`): ciò che è autorizzato è ciò che è eseguito, anche dopo un crash; regola 23 | Accettata |
| [0019](0019-task-runner.md) | Task Runner: un ciclo ri-entrante che non scrive nulla di suo, `device_id` fino all'executor e all'audit, finestre R1–R9 | Accettata |
| [0020](0020-provider-anthropic.md) | Provider Anthropic: `ProviderStatus` dichiarato, chiave solo da `ELA_ANTHROPIC_API_KEY`, retry di ELA con backoff, costo stimato in `Decimal`, vocabolario chiuso degli errori nel port, regola 24 | Accettata |
| [0021](0021-started-protocol-and-model-complete.md) | Protocollo STARTED per i tool che non si possono rifare, `ProviderUsage` da `Outcome` all'audit, `Outcome.retryable`, tool e verifier di `model.complete`, regola 25 | Accettata |
| [0022](0022-model-router.md) | Model Router: `task_type` come argomento, tabella di rotte su profili, fallback sulla disponibilità dichiarata, `ELA_ANTHROPIC_MODEL` ritirata, regola 26 | Accettata |

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
