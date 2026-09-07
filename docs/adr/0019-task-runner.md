# 0019. Task Runner: un ciclo ri-entrante che non scrive nulla di suo, finestre R1–R9

- **Stato:** Accettata
- **Data:** 2026-09-07
- **Riferimenti spec:** §13, §14, §15, §17, §18, §27, §32, §33, §63
- **Milestone:** M6.3

## Contesto

Alla fine di M6.2 ELA sapeva fare ogni singola cosa che serve per eseguire un piano e non sapeva
eseguirne uno. Il grafo dice quali step sono pronti (`GraphState.ready`), l'orchestrator dice su
quale nodo girano (`DeviceOrchestrator.place`), l'executor ne esegue uno con permesso,
autorizzazione, verifica e ripresa dopo crash (`Executor.execute`), il Task Engine chiude il task
quando ogni step è `COMPLETED`. Mancava il driver.

ADR 0017 §6 aveva già lasciato un vincolo per chi lo avrebbe scritto: chi riceve un `Placement`
vuoto deve avere un comportamento definito, altrimenti il runner lo reinventa. Questo documento
lo applica e decide il resto.

## Decisione

### 1. `ela.executive.runner.TaskRunner`, servizio del Core

Non un port: come il registro (ADR 0016 §1) e l'orchestrator (ADR 0017 §1), non esiste una
seconda implementazione all'orizzonte — esiste **una politica di camminata** che deve poter essere
letta e cambiata con un ADR.

Sta in `ela.executive`, accanto all'executor che guida: importa `ela.tasks` (l'engine),
`ela.devices` (l'orchestrator) e l'executor, e nessun contratto import-linter lo vieta. La
direzione opposta resta vietata dalla regola 22.

**Non è l'inizio dell'Action Core.** §18 elenca *ciò con cui* ELA agisce — filesystem, browser,
terminale — e quello è `ela.tools`; il runner cammina un grafo di task, che è §14–§15.

`TaskRunner(*, engine, orchestrator, executor, repository, results, audit)`. Nessuna tabella
nuova, nessun port nuovo.

### 2. Il runner non scrive nulla di suo, **nessun `AuditEventType` nuovo**

Ogni fatto che il ciclo produce è già l'evento di qualcun altro: `place` scrive
`DEVICE_SELECTED`/`DEVICE_UNAVAILABLE`, l'engine scrive i `TASK_*` e gli `STEP_*`, l'executor
scrive `PERMISSION_DECIDED`, `TOOL_EXECUTED` ed `EXECUTION_VERIFIED`. Un secondo evento per un
fatto già registrato è rumore nella catena di §32 — è ADR 0017 §6.3 generalizzata da un caso a
tutti. `test_the_runner_writes_no_audit_event_of_its_own` fissa l'insieme esatto, e una proprietà
lo verifica su ogni piano generato.

### 3. Il ciclo

```
1. is_blocked   → fail del task e ritorno              (§7)
2. is_complete  → complete del task e ritorno          (§6)
3. lo step: uno RUNNING se c'è, altrimenti ready()[0]  (§5)
4. il nodo: place() se PENDING, l'audit se RUNNING     (§4, §5)
   nessun nodo idoneo → il task resta QUEUED e ritorno (§8 di ADR 0017, qui §9)
5. task QUEUED → engine.start(device_id)               (no-op se già EXECUTING)
6. step PENDING → engine.start_step(device_id)
7. executor.execute(task_id, step_id, device_id=…)
8. il task è in uno stato di OUTCOMES → ritorno; altrimenti si rilegge il grafo e si ripete
```

**Un solo step alla volta.** `ready()` può restituirne più d'uno; eseguirli in parallelo è una
decisione che questa milestone non prende, e la sequenza è il default prudente: l'ordine è quello
topologico, quindi deterministico.

**`run` ritorna, non dorme.** Nessun polling, nessun orologio proprio, nessun risveglio. Chi la
richiama quando il mondo è cambiato — un nodo torna disponibile, l'utente risponde — è l'API di
M8.1 o il Proactive Core. Un ciclo che ri-piazzasse subito sarebbe un busy-loop che riempie
l'audit.

**Il ciclo termina senza contatore, e la ragione è una proprietà, non una guardia.** Ogni
iterazione che non ritorna chiude uno step: `execute` rifiuta uno step che non è `RUNNING`, e
ognuno dei suoi cammini o sposta lo step fuori da `RUNNING`, o lascia il task in uno stato di
`OUTCOMES`, su cui l'iterazione successiva ritorna. Quindi al massimo un'iterazione per step del
piano. **Deviazione dichiarata rispetto alla spec di M6.3**, che prevedeva un `RunnerError` oltre
il limite: quel ramo non è raggiungibile, e un ramo irraggiungibile viola sia il gate
`cov-critical` al 100% sia la regola di CLAUDE.md per cui ogni controllo ha un test che ne mostra
il caso negativo. L'invariante è asserita da
`test_a_run_executes_each_step_at_most_once` su piani generati, che è una garanzia più forte di
un contatore.

### 4. `device_id` arriva all'executor come parametro obbligatorio, e al Guardian solo per l'audit

Prima di M6.3 `executor.py` scriveva `device_id=None` sul risultato e metteva la costante
`LOCAL_DEVICE = "local"` nei payload. La costante sparisce.

| Chi | Cosa riceve | Cosa ne fa |
|---|---|---|
| `Executor.execute` | `device_id: DeviceId`, keyword-only, obbligatorio | timbra `result.device_id` con `model_copy`, accanto a `decision_id` e `authorization_id` (ADR 0015 §2) |
| `AuditEvent` di `TOOL_EXECUTED` e `EXECUTION_VERIFIED` | `result.device_id` | la colonna `device_id`, e la chiave `"device"` del payload |
| `ErrorMetadata` di una verifica fallita | `result.device_id` | il campo `device_id` di §64, che era `None` |
| `AuthorizingGuardianPort.authorize` | `device_id: DeviceId \| None = None` | **solo** la colonna `device_id` di `PERMISSION_DECIDED` |

**Il nodo non entra in nessuna regola del Guardian.** `decide` non lo prende e nessuna regola di
ADR 0011 lo legge: un Guardian che decidesse in base al nodo costruirebbe un secondo asse di
permessi, più debole di quello che esiste apposta e fuori da esso. È lo specchio di ADR 0017 §4,
dove il rischio è stato tenuto fuori dal punteggio dell'orchestrator perché un punteggio può
concedere. Qui il nodo può solo essere *registrato*.

**Sul cammino di ripresa l'autorità è il risultato persistito, non il parametro.** `_device`
legge `result.device_id`: su una ripresa il tool è girato in una chiamata precedente, sul nodo che
*quella* chiamata aveva scelto, e riportare il nodo del retry attribuirebbe l'effetto a chi passa
di lì dopo.

### 5. Le due proprietà che rendono il ciclo ri-entrante

Sono decisioni, non dettagli, e hanno un test esplicito ciascuna.

| Proprietà | Perché | Test |
|---|---|---|
| uno step **RUNNING** è scelto prima di qualunque step pronto | `ready()` restituisce solo step `PENDING`: un runner che guardasse lì soltanto non riprenderebbe mai uno step lasciato `RUNNING` da un crash (R3) o da un'approvazione (R8), e il piano si fermerebbe con uno step che nessuno finisce | `test_window_r3_a_step_left_running_is_picked_before_any_ready_one` |
| uno step **RUNNING non viene ri-piazzato**: il nodo si rilegge dall'ultimo `STEP_STARTED` dell'audit | il nodo di uno step avviato è un fatto, non una decisione da riprendere; una seconda `place()` potrebbe nominare un altro nodo mentre un tool è già girato sul primo | `test_window_r3_the_resumed_step_keeps_the_node_it_was_started_on`, `test_the_resumed_step_is_not_placed_a_second_time` |

Il runner è sequenziale, quindi di step `RUNNING` ce n'è al più uno: due sono un'incoerenza della
trail e il ciclo solleva `RunnerError` (§33). Uno step `RUNNING` il cui `STEP_STARTED` non nomina
un nodo è `RunnerError` anch'esso: il nodo non si inventa.

**Limite dichiarato, a carico di M7.** Riprendere uno step `RUNNING` sul nodo del suo
`STEP_STARTED` significa eseguirlo anche se il registro nel frattempo dà quel nodo per
irraggiungibile — è successo davvero in `test_a_walk_resumed_after_the_user_took_their_time_…`,
dove il nodo tace per cinque volte la durata di un heartbeat mentre l'utente decide. In v0.1
l'esecuzione avviene comunque nel Core, quindi la cosa non ha conseguenze; con nodi remoti veri
la scelta fra «riprendi sul nodo di prima» e «ripiazza e ricomincia» è una decisione che dipende
da §15 (il trasferimento di un workload) e va presa allora, non indovinata adesso.

Tutto il resto è riletto dagli store a ogni iterazione, quindi fra due iterazioni non sopravvive
nulla in memoria — ed è per questo che un processo nuovo e un'iterazione nuova sono la stessa
cosa (`test_window_r8_…`).

### 6. La chiusura in `COMPLETED`: il risultato dell'ultimo step in ordine topologico

`engine.complete(task_id, result)` esige un `ExecutionResult` SUCCEEDED del task e usa
`result_id` come chiave di idempotenza. Il runner **non** usa «il risultato che ha in mano»: su
una ripresa non ne ha nessuno, e due chiamate userebbero chiavi diverse — la seconda sarebbe un
`TaskEngineError`, non un no-op.

La regola è deterministica: **il risultato dell'ultimo step di `graph.order`**, riletto da
`ExecutionResultStore.for_step`. A quel punto ogni step è `COMPLETED`, quindi ogni risultato è un
SUCCEEDED veritiero di questo task, e la scelta è la stessa a ogni chiamata. Zero risultati o più
di uno sono un'incoerenza: `RunnerError`, come ADR 0015 §5 per lo stesso motivo.

### 7. La chiusura in `FAILED`: lo stesso `ErrorMetadata` dello step

`is_blocked` con il task ancora `EXECUTING` significa che uno step è fallito per colpa del tool
(`tool.refused`, `grant_vanished`, risultato FAILED) e che ADR 0014 §4 ha lasciato il task
`EXECUTING` di proposito, perché la decisione sul task è di chi orchestra. Ora chi orchestra
esiste.

Il runner prende l'`error` dall'ultimo `STEP_FAILED` dell'audit e chiama `engine.fail` con
**quello**: una seconda descrizione dello stesso fallimento sarebbe una seconda storia su di
esso. La cascata sui discendenti `PENDING` l'ha già applicata `fail_step`; `fail` non ha chiave
di idempotenza, quindi una seconda chiamata su un task già `FAILED` è un no-op silenzioso — ed è
questo che rende sicuro il retry della finestra R6.

Nessuna collisione con la finestra 9a di ADR 0015: l'executor chiude il task da sé **solo** se il
codice è `verification.failed`, e in quel caso il task è già `FAILED` quando il runner rilegge.

### 8. Le finestre di crash

Ordine delle scritture di un'iterazione: `place()` [audit] → [`engine.start`] → `engine.start_step`
→ `executor.execute` (tabella di ADR 0015 §8, invariata) → … → `engine.complete` | `engine.fail`.
«Retry» è una nuova chiamata a `run(task_id)`. Le righe con **Riparato** hanno un
`test_window_<n>_…` in `tests/executive/test_runner_recovery.py` (`REPAIRED`), e viceversa:
`tests/docs/test_adr_runner.py` confronta le due liste.

| # | Il processo muore dopo… | …e prima di | Stato che resta | Retry |
|---|---|---|---|---|
| R1 | `place()` (`DEVICE_SELECTED` scritto) | `engine.start` / `start_step` | un evento su un piazzamento che nessuno ha usato; step PENDING | ri-piazza e prosegue: un secondo `DEVICE_SELECTED`, legittimo (ADR 0017 §6.4). **Non riparato, per scelta**: un consiglio scaduto non si riusa, ed è il verso fail-safe. |
| R2 | `engine.start` (task EXECUTING) | `start_step` | task EXECUTING, step PENDING | `start` è un no-op, `start_step` prosegue. **Riparato.** |
| R3 | `start_step` (step RUNNING) | qualsiasi scrittura di `execute` | step RUNNING con il nodo in `STEP_STARTED`, nulla d'altro | lo step RUNNING è scelto prima dei pronti, il nodo è riletto dall'audit, `execute` parte da zero (nessun risultato nello store). **Riparato.** |
| R4 | uno step chiuso | l'iterazione successiva | grafo coerente | tutto è ri-derivato dal grafo; lo step già fatto non si riesegue. **Riparato.** |
| R5 | l'ultimo `complete_step` | `engine.complete` | ogni step COMPLETED, task EXECUTING | `is_complete` → risultato dell'ultimo step di `order` riletto dallo store → `complete` con la **stessa** chiave. **Riparato.** |
| R6 | `fail_step` (fallimento del tool) | `engine.fail` | step FAILED, cascata applicata, task EXECUTING | `is_blocked` → `error` dall'ultimo `STEP_FAILED` → `fail`. **Riparato.** |
| R7 | `engine.queue` → `save` (task QUEUED) | `TASK_QUEUED` nell'audit | task QUEUED senza il suo evento | il giro successivo ri-piazza e prosegue; l'evento resta mancante. Buco dell'engine (ADR 0008 §4), come le finestre 4, 5b e 9. **Non riparato.** |
| R8 | `execute` → `request_approval` (task WAITING_APPROVAL) | il ritorno di `run` | task WAITING_APPROVAL, step RUNNING | non è del runner: arriva la risposta (`respond` → `engine.approve`, task QUEUED), e il `run` successivo — anche in un processo nuovo — trova lo step RUNNING, rilegge il nodo, fa `start` ed `execute` trova la GRANTED (ADR 0015 §6). **Riparato.** |
| R9 | `engine.complete` → `save` | `TASK_COMPLETED` nell'audit | task COMPLETED senza il suo evento | riportato alla porta come `COMPLETED`, nulla scritto. Buco dell'engine. **Non riparato.** |

**La finestra 9 di ADR 0015 arriva fin qui.** Un evento `STEP_*` scritto nella trail e non
nell'audit è il buco dell'engine (ADR 0008 §4), e il runner lo incontra in due forme: uno step
`RUNNING` di cui nessun `STEP_STARTED` dice il nodo, e un piano bloccato di cui nessun
`STEP_FAILED` porta l'errore. In entrambi i casi `RunnerError`: il nodo non si inventa e il task
non si chiude su un errore che nessuno ha registrato (§33). Non sono finestre nuove — è la
stessa, vista da un livello più su — quindi non hanno una riga in tabella, ma hanno i loro test.

### 9. `Placement.device is None`: ADR 0017 §6 applicata, non reinventata

1. il task **resta `QUEUED`**; un task `EXECUTING` che si ritrova senza nodo torna a `QUEUED` con
   `engine.queue`. Nessuno stato nuovo;
2. **nessun `fail`, nessun `fail_step`, nessun `ErrorMetadata`**: un nodo che manca non è un
   errore dell'azione;
3. **nessun evento scritto dal runner**: `DEVICE_UNAVAILABLE` l'ha già scritto `place()`, con il
   punteggio e i rifiuti di ogni candidato;
4. il ciclo **ritorna** con esito `WAITING_DEVICE`; riprovare è la chiamata successiva, che
   scriverà il proprio evento perché è una decisione presa in un istante diverso.

`max_privacy` è una keyword di `run`, con default `LOCAL_ONLY`: il runner è il chiamante che
dichiara il nodo più permissivo che tollera, e una privacy non dichiarata non è un permesso
(§33, §57; ADR 0017 §8).

### 10. Che cosa ritorna `run`

| `RunOutcome` | Quando |
|---|---|
| `COMPLETED` | ogni step COMPLETED e il task chiuso |
| `FAILED` | uno step è fallito e il task è FAILED, i discendenti CANCELLED |
| `DENIED` | il Guardian ha negato uno step; il task è DENIED e nulla è girato |
| `WAITING_APPROVAL` | uno step aspetta il consenso dell'utente (§30) |
| `WAITING_DEVICE` | nessun nodo idoneo: il task è QUEUED e **non** fallisce |
| `CANCELLED` | qualcuno ha fermato il task (§65) |
| `EXPIRED` | il task ha finito il tempo (§14) |

**Uno stato, un esito.** `CANCELLED` ed `EXPIRED` sono due righe e non una: un task che qualcuno
ha fermato e uno a cui è scaduto il tempo sono fatti diversi — il primo è una decisione con un
attore dietro, il secondo è il tempo che passa — e un esito unico «terminale» butterebbe via una
distinzione che dopo non si recupera più (review di M6.3).

`Run(task, outcome, steps, executions)`: gli step eseguiti *da questa chiamata*, in ordine, e la
parola dell'executor su ciascuno. Nulla di persistito. La stessa tabella (`OUTCOMES`) serve al
controllo alla porta e a quello fra due iterazioni: un task già chiuso quando `run` è chiamata è
riportato esattamente come uno chiuso dalla chiamata stessa, e `Run.steps` vuoto è ciò che dice
quale dei due è successo.

Precondizioni, prima di qualunque scrittura: il task è `QUEUED` o `EXECUTING` (`CREATED` e
`PLANNING` non hanno un grafo da camminare, e produrlo è del Planner) e il piano ha almeno uno
step — un piano vuoto è `is_complete` per ADR 0004 P7 ma non ha nessun risultato con cui chiudere
il task, quindi è `RunnerError` invece di un task che resta aperto in silenzio.

## Alternative considerate

- **Un `TaskRunnerPort`** — scartata: nessuna implementazione alternativa esiste o è prevista, e
  ADR 0016 §1 e ADR 0017 §1 hanno già preso la stessa decisione. Un port nasconderebbe la
  politica invece di esporla.
- **Il runner in `ela.tasks`** — scartata: importa `ela.devices` ed `ela.executive`, quindi
  farebbe dipendere il Task Engine dall'orchestrator e dall'executor. `ela.tasks` risponde a
  «quali transizioni sono legali», non a «chi va eseguito adesso».
- **Guardare solo `ready()`** — scartata: uno step lasciato RUNNING da un crash o da
  un'approvazione non sarebbe mai ripreso e il piano si fermerebbe per sempre (§5).
- **Ri-piazzare anche uno step RUNNING** — scartata: potrebbe nominare un nodo diverso da quello
  su cui un tool è già girato, e l'audit attribuirebbe l'effetto al nodo sbagliato (§5).
- **Chiudere il task sul risultato che il runner ha in mano** — scartata: la chiave di
  idempotenza di `complete` cambierebbe fra un run e il suo retry, e la seconda chiamata sarebbe
  rifiutata invece di essere un no-op (§6).
- **Un contatore di iterazioni con `RunnerError` oltre il limite** — scartata: il ramo non è
  raggiungibile, quindi violerebbe il gate di copertura e la regola «ogni controllo ha il suo
  caso negativo». La terminazione è una proprietà provata e testata (§3).
- **Far dormire e riprovare il runner quando nessun nodo è idoneo** — scartata: sarebbe uno
  scheduler, con un orologio e una politica di attesa che questa milestone non decide, e
  riempirebbe l'audit di `DEVICE_UNAVAILABLE` identici.
- **Eseguire in parallelo gli step pronti** — scartata per ora: la sequenza è il default prudente
  e il parallelismo richiede di decidere che cosa succede a due step che falliscono insieme.
- **Il nodo come input delle regole del Guardian** — scartata: sarebbe un secondo sistema di
  permessi accanto a quello che esiste apposta (§4).
- **Uno stato `WAITING_DEVICE` del task** — già scartata in ADR 0017: §14 fissa dieci stati
  verbatim e `QUEUED` significa già «pronto, in attesa che un nodo lo prenda».

## Conseguenze

- Il vincolo di ADR 0017 §6 è chiuso: chi riceve un `Placement` vuoto ha un comportamento
  definito, applicato e testato.
- `LOCAL_DEVICE` non esiste più: ogni `ExecutionResult`, ogni `TOOL_EXECUTED`, ogni
  `EXECUTION_VERIFIED` e ogni `PERMISSION_DECIDED` di un'esecuzione nomina il nodo che
  l'orchestrator ha scelto. ADR 0013 e ADR 0014 prendono nello stato il rimando.
- `Executor.execute` cambia firma per la seconda volta (ADR 0015 §4 fu la prima): perde
  `arguments` (ADR 0018 §4) e guadagna `device_id`.
- L'esecuzione di un piano è ora una chiamata sola, e una chiamata interrotta si riprende
  chiamandola di nuovo: R2–R6 e R8 sono riparate, R1 non lo è per scelta, R7 e R9 sono i buchi
  dell'engine già noti.
- `ela.executive` era già nei `CRITICAL_PACKAGES`: il 100% di branch coverage vale da subito sul
  runner.
- `tests/docs/test_adr_runner.py` verifica che le tabelle di §4, §5, §8 e §10 non driftino dal
  codice e dai test.
- Il Planner (§13) resta da fare: M6.3 esegue piani, non li produce.
