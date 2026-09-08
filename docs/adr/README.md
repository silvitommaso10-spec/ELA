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
| [0023](0023-composition-root-and-api.md) | Composition root, configurazione unificata e API locale: `ela.composition`, `ela.api`, token statico su loopback, regola 27 | Accettata |
| [0024](0024-cli.md) | La CLI di ELA: un client dell'API locale, `ela.cli`, `AuditVerifier` e le rotte `/devices` e `/audit/verify`, quattro codici di uscita, regola 3 estesa e regola 28 | Accettata |
| [0025](0025-phase-8-debts.md) | I debiti di Fase 8: `TaskRepository.count`, `AuditLog.read(newest_first=)`, `ExecutionResultStore.for_task` con `GET /tasks/{id}/results` e `ela task results`, `ELA_NOTES_SCOPE` e `ELA_DECISION_TTL_SECONDS`, regola 29 | Accettata |
| [0026](0026-placement-as-data.md) | Il piazzamento come dato: `PlacementDecision`, `ensure_placed` e `confirm`; il confronto del token a tempo costante; regole 30 e 31 | Accettata |
| [0027](0027-exemptions-withdrawn.md) | Le esenzioni senza codice dietro, ritirate (regole 6, 15, 16, 21); la tabella `CONSTANTS` che se ne accorge, e il criterio dell'attore legittimo | Accettata |
| [0028](0028-perception-core.md) | Il primo contatto con l'hardware: la sonda isolata, lo stato con la sua causa, e il criterio dell'audit (regole 32–34) | Accettata |
| [0029](0029-screen-capture.md) | La prima lettura di contenuto: l'artefatto che si può verificare, il figlio che non è nostro, e la credenza che non decide (regola 35) | Accettata |
| [0030](0030-screen-text.md) | Comprendere ciò che si vede: il contesto che non costa un permesso, il figlio che torna nostro, e l'artefatto che eredita (regola 36) | Accettata |
| [0031](0031-runner-parity.md) | La copertura non dipende dal runner: una scelta di piattaforma è un'istruzione, non un'espressione (regola 37) | Accettata |
| [0032](0032-context-core.md) | Il contesto che si ricalcola: le assenze derivate, il confine con la memoria, e le due porte chiuse (regole 38 e 39) | Accettata |

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
