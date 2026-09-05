# 0008. Task Engine: tabella delle operazioni, idempotenza, ordine delle scritture, heartbeat come evento, piano persistito, recovery

- **Stato:** Accettata. §9 (`complete`) esteso da ADR 0009 §7 con la guardia sugli step; le operazioni per step sono in ADR 0009 §5. §3: `PERMISSION_DECIDED` lo scrive il Guardian (`authorize`, ADR 0011 §8).
- **Data:** 2026-09-04
- **Riferimenti spec:** §12, §13, §14, §15, §27, §32, §33, §49, §51, §52, §63, §65
- **Milestone:** M3.1

## Contesto

§14 affida al Task Engine il ciclo di vita del task e ne elenca gli scopi: recuperare attività,
capire cosa è successo, evitare duplicazioni, riprendere attività interrotte. M1.2 (ADR 0004) ha
fissato *quali* mosse sono legali con una funzione pura; M2.1 e M2.2 (ADR 0006, 0007) hanno dato
dove persistere il task, la sua trail e l'audit. Mancava chi mette insieme le tre cose: un solo
punto in cui una mossa legale diventa un task salvato, un `TaskEvent` e un `AuditEvent`, e che
sia sicuro da ritentare. Le decisioni sono state approvate in review il 2026-09-04
(`docs/milestones/M3.1.md`).

## Decisione

### 1. Forma e firme

`TaskEngine(repository, audit_log, clock, ids, *, actor, orphan_after)` in
`src/ela/tasks/engine.py`, tutto `async` (due port di I/O, ADR 0005 §1). I metodi ricevono un
`TaskId`, mai un `Task`: un `Task` è immutabile e la copia del chiamante può essere stantia;
l'engine ricarica il task sotto lock e la state machine lavora sullo stato salvato. Ogni metodo
ritorna il `Task` salvato dopo l'operazione. `orphan_after <= 0` è `ValueError`.

### 2. Il piano è un'entità persistita: `TaskRepository.add_plan` e `plan`

Il Task Graph (M3.2) e l'orchestrator per step (M6.2) leggono il piano di continuo, e
un'entità con id non si ricava scansionando eventi. Nessun port nuovo: `TaskRepository` si
estende con due membri, documentati qui perché ADR 0005 è immutabile (`tests/docs/
test_adr_ports.py` unisce le righe di 0005 e 0008 e le confronta con `ela.ports`).

| Port | Spec | Modo | Membri aggiunti |
|---|---|---|---|
| `TaskRepository` | §13, §14 | async | `add_plan`, `plan` |

`add_plan(plan)`: `NotFoundError` se il task è sconosciuto, `AlreadyExistsError` se il task ha
già un piano o l'id del piano è già usato. `plan(task_id)`: `NotFoundError` se il task è
sconosciuto o non ha piano. Una tabella nuova, con le convenzioni di ADR 0006 §6 e la migrazione
`0003` (reversibile: non tocca `audit_events`), verificata da `tests/docs/test_adr_persistence.py`
nell'unione con 0006 e 0007:

| Tabella | Colonne |
|---|---|
| `task_plans` | `seq`, `id`, `created_at`, `task_id`, `goal`, `steps`, `metadata` |

`task_id` è UNIQUE e FK verso `tasks.id`: un piano per task, ripianificare non è ammesso in v0.1
(ADR 0004). Gli step sono value-like e immutabili e stanno in una colonna JSON come array,
tramite il mapper esplicito (`plan_values`, `plan_to_row`, `row_to_plan`); una tabella di step
sarà una migrazione con ADR il giorno che qualcosa dovrà interrogarli in SQL.

### 3. La tabella delle operazioni

L'engine è guidato da `OPERATIONS`: una riga per operazione che cambia stato, con le sorgenti
ammesse, il target, il tipo di audit e la chiave di idempotenza. La tabella qui sotto è
confrontata con il codice da `tests/docs/test_adr_engine.py`; `tests/tasks/test_engine_table.py`
verifica che ogni coppia (sorgente, target) sia legale in `TRANSITIONS` e che l'unione delle
coppie copra tutte e 23 le transizioni legali di ADR 0004: nessuna mossa è raggiungibile solo
aggirando l'engine.

| Operazione | Da | A | Audit | Chiave |
|---|---|---|---|---|
| `start_planning` | CREATED | PLANNING | `TASK_PLANNING_STARTED` | — |
| `request_approval` | PLANNING, EXECUTING | WAITING_APPROVAL | `APPROVAL_REQUESTED` | `approval_id` |
| `approve` | WAITING_APPROVAL | QUEUED | `APPROVAL_RESOLVED` | `approval_id` |
| `deny_by_approval` | WAITING_APPROVAL | DENIED | `APPROVAL_RESOLVED` | `approval_id` |
| `deny_by_decision` | PLANNING, EXECUTING | DENIED | `TASK_DENIED` | `decision_id` |
| `queue` | PLANNING, EXECUTING | QUEUED | `TASK_QUEUED` | — |
| `start` | QUEUED | EXECUTING | `TASK_STARTED` | — |
| `complete` | EXECUTING | COMPLETED | `TASK_COMPLETED` | `result_id` |
| `fail` | PLANNING, EXECUTING | FAILED | `TASK_FAILED` | — |
| `cancel` | CREATED, PLANNING, WAITING_APPROVAL, QUEUED, EXECUTING | CANCELLED | `TASK_CANCELLED` | — |
| `expire` | CREATED, PLANNING, WAITING_APPROVAL, QUEUED, EXECUTING | EXPIRED | `TASK_EXPIRED` | — |
| `recover` | EXECUTING | FAILED | `TASK_FAILED` | — |

Tre operazioni non passano dalla tabella delle transizioni: `create` (nasce in CREATED, audit
`TASK_CREATED`), `plan` (attacca il piano a un task PLANNING senza cambiarne lo stato, evento
`PLAN_ATTACHED` con il solo `plan_id` nei metadati, audit `PLAN_CREATED`) e `heartbeat` (§5).
`start_planning` esiste perché ADR 0004 P4 ammette PLANNING → FAILED ("il planner non produce un
piano") e quello stato deve esistere *prima* che un piano esista. `deny` è due righe perché
registra due fatti diversi: un'approvazione rifiutata dall'utente è un'approvazione *risolta*, un
diniego del Guardian è un `TASK_DENIED`. `queue` da WAITING_APPROVAL è legale nella tabella ma
non di questa operazione: serve l'`Approval`, quindi `approve`; l'engine solleva
`TaskEngineError` con il suggerimento, mentre per una coppia illegale solleva
`IllegalTransitionError` di M1.2, invariata.

**Un tipo di audit per operazione.** §32 vuole sapere "cosa ha fatto ELA e perché": un log
interrogabile per tipo — tutti i DENIED, tutte le approvazioni — vale più di uno da filtrare sul
payload. Si riusano i membri esistenti di `AuditEventType` dove combaciano (`TASK_CREATED`,
`PLAN_CREATED`, `APPROVAL_REQUESTED`, `APPROVAL_RESOLVED`) e si aggiungono
`TASK_PLANNING_STARTED`, `TASK_QUEUED`, `TASK_STARTED`, `TASK_COMPLETED`, `TASK_FAILED`,
`TASK_CANCELLED`, `TASK_EXPIRED`, `TASK_DENIED` (aggiunte a un enum: additive, ADR 0003 §7). Il
`payload` di ogni transizione porta sempre `operation`, `previous_state`, `new_state`, `reason`
e le chiavi. L'engine registra ciò che l'engine fa, il ciclo di vita: `PERMISSION_DECIDED`,
`TOOL_EXECUTED`, `PROVIDER_CALLED` li scriverà chi chiama il Guardian e chi esegue (M5+).

### 4. Un solo percorso di scrittura: save, poi evento, poi audit

Ogni operazione che cambia stato fa: lock per `task_id` (§11) → `get` → `events` → controllo di
idempotenza (§8) → controllo delle sorgenti (§3) → orologio e skew (§7) → controlli che dipendono
dal task (§9) → `transition` → `save` → `append_event` → `audit.append`. Non esiste unit-of-work
fra port (ADR 0006 §4): l'ordine è quello in cui un crash a metà lascia un buco, mai un duplicato:

| Crash dopo | Stato salvato | Trail | Audit | Retry |
|---|---|---|---|---|
| nulla | vecchio | — | — | riapplica |
| `save` | nuovo | manca STATE_CHANGED | manca | no-op |
| `append_event` | nuovo | completa | manca | no-op |
| `audit.append` | nuovo | completa | completa | no-op |

Con l'audit prima, un crash lascerebbe un audit che afferma ciò che non è avvenuto e il retry
duplicherebbe. I buchi sono il problema di unit-of-work rinviato all'executor (M5), che potrà
anche ripararli; M3.1 li dichiara e non li ripara.

### 5. L'heartbeat è un `TaskEvent`

`TaskEventType.HEARTBEAT`; `heartbeat(task_id)` appende l'evento a un task EXECUTING e non
scrive audit: un segno di vita non è un "evento significativo" di §32. È l'unica operazione
volutamente non idempotente: ripeterla è il suo scopo. Conseguenze: i `TaskEvent` non sono
audit, quindi gli HEARTBEAT sono potabili per policy in futuro (l'audit no); il volume dipende
dall'intervallo, che sarà configurazione dei nodi. Nessuna migrazione: la review di M1.1 aveva
già escluso un campo di aggiornamento su `Task` ("i `TaskEvent` portano già i timestamp") e
`Task.metadata` è escluso dal dominio stesso.

### 6. Recovery

`recover()` legge `tasks(states={EXECUTING})` (ADR 0005 §2-ter: il consumatore previsto) e, per
ciascun candidato, prende `last_seen = max(task.created_at, created_at degli eventi)` — lo
STATE_CHANGED in EXECUTING, gli HEARTBEAT, o la nascita se la trail è vuota. Un candidato è orfano
se `now - last_seen >= orphan_after` (verso chiuso, ADR 0005 §2-bis). **Robusta per task, non
per ordine di chiamata** (review 2026-09-05): `recover()` sarà chiamata anche periodicamente dal
Proactive Core, non solo all'avvio, e un'assunzione sull'ordine delle chiamate è fragile. Per ogni
orfano l'engine prende il lock del task, **ricarica** stato e trail e ricontrolla: se il task non
è più EXECUTING, o ha dato un segno di vita nel frattempo, lo **salta**; altrimenti lo porta in
FAILED per la riga `recover`, con attore SYSTEM e `ErrorMetadata(code="orphaned",
retryable=True, details={last_seen_at, orphan_after_seconds})`. Un task che cambia sotto i piedi
non interrompe la recovery degli altri, e il ricontrollo sotto lock rende irraggiungibile
l'`IllegalTransitionError` che una chiamata cieca a `fail` avrebbe potuto sollevare. Ritorna
`RecoverySummary(failed, skipped)`; una seconda chiamata immediata ritorna due tuple vuote.

### 7. Monotonia del tempo: si rifiuta

Prima di scrivere, l'engine confronta `clock.now()` con `last_seen`: se è strettamente
precedente solleva `ClockSkewError` e non scrive nulla. Un clock che va indietro è un guasto, e
§33 dice: nel dubbio non scrivere. Istanti uguali sono ammessi (due eventi allo stesso istante
sono ordinati da `seq`). Chiude il rinvio di M1.2: `test_now_may_precede_task_creation` resta
vero per la state machine, il vincolo vive un livello sopra.

### 8. Idempotenza per stato e per chiave

Un'operazione il cui target è già lo stato salvato è un no-op: ritorna il task salvato senza
`TaskEvent` né `AuditEvent`. Se l'operazione ha una chiave, il no-op vale solo se l'ultimo
STATE_CHANGED registra nei `metadata` **la stessa operazione e la stessa chiave**; altrimenti è
`TaskEngineError`: un "già fatto" silenzioso nasconderebbe un'approvazione mai registrata. La
sola chiave non basta: una richiesta di approvazione e la sua concessione portano lo stesso
`approval_id`, e un task salvato QUEUED senza evento (crash dopo `save`) sarebbe stato scambiato
per "già approvato" perché l'ultimo STATE_CHANGED era la richiesta (trovato in implementazione).
`create` è idempotente per intento: `TaskId = uuid5(TASK_NAMESPACE, str(intent.id))`, così le
richieste ritentate da API e iPhone non creano task doppi; vale per il task radice, i sottotask
(M3.2) hanno `parent_id` e id da `IdGenerator`. `plan`: stesso `plan.id` → no-op; un altro →
`TaskEngineError`; un `add_plan` che trova lo stesso piano già salvato (crash fra `add_plan` e
`save`) prosegue.

### 9. Coerenza degli input: nel dubbio si rifiuta

`TaskEngineError`, nulla scritto: `approve` vuole un'approvazione GRANTED di quel task con
`responded_by`; `deny` esattamente uno fra una decisione DENIED di quel task e un'approvazione
REJECTED con `responded_by`; `request_approval` un'approvazione PENDING di quel task;
`complete` un risultato SUCCEEDED di quel task (§63); `queue` e `request_approval` un piano
attaccato (P7: anche un piano a zero step è un piano); `plan` un task PLANNING e
`plan.task_id` coincidente; `expire` un `deadline` presente e `<= now`; `heartbeat` un task
EXECUTING. È qui che si decide *quando* un task scade: la state machine decide solo *se*.

### 10. Attore dell'audit

ELA (l'`actor` del costruttore) per ciò che compie ELA; `Actor(USER, approval.responded_by)` per
`approve` e `deny_by_approval`; `SYSTEM_ACTOR` (`"task-engine"`) per `expire` e `recover`;
`cancel` accetta un attore opzionale perché a fermare un task può essere l'utente (§65) o ELA.

**Convenzione per gli attori SYSTEM** (review 2026-09-05): l'`id` di un `Actor` di tipo
`SYSTEM` è il nome del componente in kebab-case — `task-engine` qui; `guardian`,
`device-orchestrator`, `proactive-core` quando esisteranno — così ogni componente che agisce
senza che nessuno glielo abbia chiesto è riconoscibile nel log senza reinventare la forma.

### 11. Serializzazione in-process

Un `asyncio.Lock` per `task_id`: fra `get` e `save` ci sono `await`. Copre un Core, un
processo (v0.1). Un secondo processo richiederà una colonna di versione con `UPDATE … WHERE
version = ?` (optimistic locking): migrazione e ADR futuri.

### 12. Regola architetturale 10: la state machine ha un solo chiamante

Fuori da `ela.tasks` nessun modulo importa `ela.tasks.state_machine`: chi chiamasse `transition`
e poi `save` cambierebbe stato senza trail né audit. Contratto import-linter 7 e regola
closed-world `check_state_machine_callers` in `tests/architecture/rules.py`, con casi negativi;
`ela.tasks.errors` resta importabile da chiunque.

## Alternative considerate

- **Metodi che ricevono `Task`** (firma del prompt) — la copia del chiamante può essere stantia
  e l'engine ne userebbe solo l'id; prendere l'id toglie la domanda "quale versione conta".
- **Un solo tipo di audit `TASK_STATE_CHANGED`** con il dettaglio nel payload — uniforme, ma un
  log che si interroga per tipo risponde a §32 senza parsing; scartata dall'utente.
- **Heartbeat come campo `Task.last_heartbeat_at`** — una colonna, una migrazione, il mapper e le
  strategie per un timestamp che la trail già porta; e contraddice la review di M1.1.
- **Piano nei metadati di PLAN_ATTACHED** o **un `PlanRepository` nuovo** — il primo non dà
  un'entità con id ai lettori di M3.2/M6.2, il secondo è un port in più per un aggregato che il
  `TaskRepository` già possiede (§14: la trail appartiene al task, il piano pure).
- **Clamp dell'orologio** (`now = max(clock.now(), last_seen)`) — tiene la trail ordinata al
  prezzo di registrare un istante non vero; nell'audit meglio rifiutare che mentire.
- **`create` non idempotente**, id da `IdGenerator` — ogni retry di una richiesta da API o iPhone
  creerebbe un task doppio: esattamente ciò che §14 chiede di evitare.
- **Audit prima di `save`** — un crash lascerebbe un audit falso e il retry duplicherebbe (§4).
- **`plan(task_id, plan)` che fa anche CREATED → PLANNING** — PLANNING → FAILED del planner non
  sarebbe esprimibile (P4).
- **Riparare i buchi da crash nel no-op** — è la unit-of-work dell'executor (ADR 0006 §4), e va
  decisa insieme a chi scrive `TOOL_EXECUTED`.

## Conseguenze

- `TaskEngine`, `Operation`, `OPERATIONS`, `TASK_NAMESPACE`, `ORPHANED`, `SYSTEM_ACTOR`,
  `LIVE_STATES`, `TaskEngineError`, `ClockSkewError` sono l'API pubblica di `ela.tasks`; il
  gate `cov-critical` copre `engine.py` al 100% branch.
- La tabella di §3, la riga del port di §2 e la tabella dello schema di §2 sono verificate
  contro il codice; cambiare una di esse senza il codice rompe `make check`.
- `TaskRepository` ha otto membri; ADR 0005 e ADR 0006 portano nello stato il rimando a questo
  ADR e restano immutabili nel corpo.
- Ogni operazione legge la trail del task (skew e chiave): cresce con gli HEARTBEAT di un task
  lungo. Se diventasse un costo, un `last_event(task_id)` sul port è un'aggiunta con ADR.
- I buchi da crash (§4) e il lock in-process (§11) sono limiti dichiarati, da chiudere con la
  unit-of-work di M5 e con l'optimistic locking quando ci sarà un secondo processo.
- `TaskEventType.HEARTBEAT` e otto membri di `AuditEventType` in più: additivi, nessuna
  migrazione (ADR 0003 §7). Gli HEARTBEAT sono potabili per policy in futuro, l'audit no.
