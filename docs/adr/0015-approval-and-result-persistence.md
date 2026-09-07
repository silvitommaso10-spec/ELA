# 0015. Persistenza di Approval ed ExecutionResult: `ApprovalStore` ed `ExecutionResultStore`, la risposta dallo store, ripresa di uno step interrotto, finestre 5, 7b, 8, 8a–8c e 9a riparate, richieste scadute in `recover()`, regola 19

- **Stato:** Accettata. Review del 2026-09-06: `pending` prende `now` opzionale (§1); il presidio
  della finestra 7a è in codice — `Tool.idempotent` e il rifiuto del `ToolRegistry` (§8); le due
  regole di `recover()` sono scritte insieme (§6).
  **ADR 0018 §4**: `execute` perde anche il parametro `arguments` (sono `step.arguments`) e prende `device_id` obbligatorio; la tabella delle finestre di §8 non cambia, ma la finestra 7b ora riscrive `targets` calcolati sugli **stessi** argomenti del run, perché il retry rilegge il piano.
- **Data:** 2026-09-06
- **Riferimenti spec:** §14, §27, §30, §32, §33, §54, §57, §62, §63
- **Milestone:** M5.3

## Contesto

Fino a M5.2 l'`Approval` che l'executor costruisce e l'`ExecutionResult` che il tool produce
vivevano solo in memoria. Ne seguivano le finestre di crash 5, 7 e 8 di ADR 0013 §8 e 8a–8c, 9a
di ADR 0014 §6: chi chiamava l'executor doveva tenere l'`Approval` per farla rispondere, un crash
fra il tool e la chiusura dello step faceva rieseguire il tool, e un `TOOL_EXECUTED` senza
`EXECUTION_VERIFIED` non poteva essere ri-verificato perché il risultato non c'era più. ADR 0013
dichiarava: "fino a M5.3 l'executor è utilizzabile solo in-process". Le domande erano: dove
vivono le richieste e i risultati; come la risposta dell'utente arriva all'executor senza un
parametro; da dove un retry riprende; che cosa non si può riparare per costruzione; chi chiude un
task che aspetta una richiesta scaduta; chi può rispondere a una richiesta. Le decisioni A–J sono
dell'utente (2026-09-06, `docs/milestones/M5.3.md`).

## Decisione

### 1. Due port introdotti: `ApprovalStore` ed `ExecutionResultStore`

`ela.ports` prende `ApprovalStore` (async: `add`, `get`, `for_task`, `pending`, `respond`) ed
`ExecutionResultStore` (async: `add`, `get`, `for_step`); i fake in `ela.testing`, gli adapter
`SqlApprovalStore` e `SqlExecutionResultStore` in `ela.infrastructure.persistence`, il contratto
in `tests/contracts/test_approval_store.py` e `test_execution_result_store.py` su fake e SQLite.
Le righe sotto sono lette da `tests/docs/test_adr_ports.py` come introduzioni.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ApprovalStore` | §30, §62 | async | `add`, `get`, `for_task`, `pending`, `respond` |
| `ExecutionResultStore` | §63 | async | `add`, `get`, `for_step` |

I port sono diciassette; ADR 0005 prende nello stato il rimando.

**Contratto di `ApprovalStore`.** `add` accetta **solo** una richiesta PENDING (`ValueError`,
decisione H): un "sì" entra nello store per una porta sola, `respond`. `for_task` ritorna ogni
richiesta del task, di qualsiasi stato, in ordine di inserimento. `pending(*, now=None, limit=None)`
(decisione A) ritorna le PENDING **di tutti i task**, in ordine di inserimento, le prime `limit`
(`check_limit`, applicato dopo il filtro): "cosa aspetta una mia risposta" per M8.1 e per
l'iPhone, aggiunto ora perché cambiare un port dopo costa più che aggiungerlo prima. **`now` è
opzionale** (review del 2026-09-06): se dato, una richiesta scaduta a quell'istante
(`expires_at <= now`, lo **stesso verso chiuso** di `respond`) è esclusa — `respond` la
rifiuterebbe, e mostrare all'utente una domanda che non può più ricevere risposta sarebbe
chiedere l'impossibile (§33); se non è dato, tornano tutte, scadute comprese. Lo store resta
senza orologio: chi ne ha uno — M8.1 — passa `now`. `respond(approval_id, *, status, responded_by, now) -> Approval` risponde **una
volta**: `status` fuori da {GRANTED, REJECTED} → `ValueError` (`check_answer` in `ela.ports`,
una fonte per fake e adapter come `check_limit`; PENDING non è una risposta ed EXPIRED non è
dell'utente); id ignoto → `NotFoundError`; già risposta → `ApprovalAlreadyAnsweredError`; scaduta
(`expires_at <= now`, verso chiuso) → `ApprovalExpiredError`; altrimenti scrive `status`,
`responded_by`, `responded_at = now` — nient'altro — e ritorna la richiesta come sta nello store.
Le due eccezioni estendono `ApprovalNotAnswerableError(PortError)`, specchio di
`AuthorizationNotUsableError` (ADR 0012 §3). L'ordine "già risposta prima di scaduta" è
deliberato: una richiesta risposta in tempo e poi scaduta è risposta. In SQL `respond` è **un
`UPDATE` condizionale** (`WHERE id = :id AND status = 'PENDING' AND (expires_at IS NULL OR
expires_at > :now)`) seguito, se `rowcount == 0`, da una lettura che nomina l'errore: di venti
risposte concorrenti una sola passa (ADR 0012 §5, stesso meccanismo). `now` è un fatto del
chiamante, come per `consume`.

**Contratto di `ExecutionResultStore`.** Insert-only: `add` (`AlreadyExistsError` sull'id), `get`
(`NotFoundError`), `for_step(task_id, step_id)` in ordine di inserimento. `output` è contenuto
dell'utente (§57): sta qui, nel database privato (ADR 0006 §4), e nell'audit non entra mai.

### 2. `ExecutionResult` sa da quale decisione e quale grant è nato

Due campi additivi nel dominio (decisione B: "un risultato deve sapere da quale decisione nasce,
è §32"): `decision_id: DecisionId | None = None` e `authorization_id: AuthorizationId | None =
None`, gli stessi di `AuditEvent`. Li **timbra l'executor** con `model_copy` prima di
`results.add`: `decision_id` della decisione ALLOWED, `authorization_id` **del grant consumato o
`None`** — non `decision.authorization_id`, che il Guardian riempie anche quando la regola ignora
il grant (ADR 0013 §7). Il tool non li conosce (non sa se il grant è stato speso) e la sua firma
non cambia. `Execution.result` è il risultato timbrato. Un risultato costruito altrove
(`engine.complete` nei test) li lascia nulli. ADR 0003 prende nello stato il rimando.

### 3. Schema: due tabelle, migrazione `0004`

| Tabella | Colonne |
|---|---|
| `approvals` | `seq`, `id`, `created_at`, `task_id`, `step_id`, `capability_id`, `targets`, `prompt`, `status`, `decision_id`, `responded_at`, `responded_by`, `expires_at`, `metadata` |
| `execution_results` | `seq`, `id`, `created_at`, `capability_id`, `status`, `task_id`, `step_id`, `tool_name`, `device_id`, `decision_id`, `authorization_id`, `output`, `error`, `duration_ms`, `metadata` |

`ApprovalRow` ed `ExecutionResultRow` in `orm.py`, mapper campo per campo con il test di
completezza (ADR 0006 §5); `status` come stringa, `targets`/`output`/`error`/`metadata` JSON;
indici su `task_id` di entrambe e su `approvals.status` (le letture sono per task, per step e
per "cosa aspetta"). **Nessuna FK su `task_id`**: store separati dal repository, come
`authorizations` (ADR 0006 §6). Migrazione `0004` reversibile (non tocca `audit_events`). La
tabella è confrontata con `Base.metadata` da `tests/docs/test_adr_persistence.py`; ADR 0006
prende nello stato il rimando.

### 4. L'executor: costruttore, firma, `Execution`

`Executor(*, …, approvals: ApprovalStore, results: ExecutionResultStore, …)` keyword-only,
obbligatori come `verifiers`: un executor che tenesse richieste e risultati in memoria non
potrebbe essere ritentato. **`execute(task_id, step_id, arguments)`**: il parametro `approval` di
ADR 0013 §1 sparisce (decisione dell'utente), la risposta arriva dallo store (§6). `Execution`
prende `decision: PermissionDecision | None` (decisione G): `None` solo quando la chiamata ha
ripreso un run, completato una richiesta o fallito un task già decisi da una chiamata
precedente; l'id della decisione è in `result.decision_id` o in `approval.decision_id`, la
decisione in `PERMISSION_DECIDED`. `approval` è la richiesta fatta o completata da questa
chiamata; `verification` è la parola del verifier entrata in questa chiamata: consultato ora,
oppure riletta da `EXECUTION_VERIFIED` su una ripresa (§5) con `failures` vuota e l'`error` che le
porta in `details`.

### 5. Ripresa di un run interrotto

Dopo le precondizioni di ADR 0013 §2 e ADR 0014 §3 (invariate, nulla scritto) e **prima del
Guardian**, l'executor legge `results.for_step`. Nessun risultato → pipeline normale. Più di uno
→ `ExecutorError` (uno step si esegue una volta, ADR 0013 §1: due risultati sono un'incoerenza
dello store, §33). Un risultato `r` con lo step RUNNING significa che il tool è girato e le
scritture si sono fermate: l'executor legge l'audit del task, cerca il `TOOL_EXECUTED` e
l'`EXECUTION_VERIFIED` il cui `payload["result_id"]` è `r.id`, e **riprende dalla prima scrittura
mancante**, senza Guardian, senza `consume`, senza tool:

| Trovato | Operazioni | Finestra |
|---|---|---|
| nessun `TOOL_EXECUTED` | `TOOL_EXECUTED` da `r` (decisione e grant di `r`, `targets` dagli argomenti della chiamata, `uses` = `authorizations.uses(r.authorization_id)` letto ora, o `None`), poi come le righe sotto | 7b |
| `r` non SUCCEEDED | `fail_step` con l'errore di `r` (ADR 0013 §5) | 8 |
| SUCCEEDED, nessun `EXECUTION_VERIFIED` | `verify` → `EXECUTION_VERIFIED` → chiusura (ADR 0014 §4) | 8a |
| `EXECUTION_VERIFIED` passata | `complete_step(r)` | 8b |
| `EXECUTION_VERIFIED` fallita | `fail_step` + `fail` con l'`error` dell'evento | 8c |

Un `TOOL_EXECUTED` o `EXECUTION_VERIFIED` scritto in una ripresa ha la forma di quello normale,
`created_at` = orologio di ora, e **`payload["recovered"] = True`** (decisione E; costante
`RECOVERED`): i numeri che porta — `uses` in particolare — sono letti al retry, non al run.
Onestà sull'origine del dato, senza inventare precisione: per un grant monouso `uses` è 1, per
uno di policy è il contatore dello store in quel momento. Un evento scritto con il run non porta
la chiave. La ri-verifica è idempotente per costruzione (regola 18: il verifier legge soltanto).

### 6. La richiesta: persistita prima dell'attesa, ritrovata al retry, mai richiesta se scaduta

`_ask`: l'`Approval` ha **id deterministico per decisione**, `uuid5(APPROVAL_NAMESPACE,
str(decision.id))` (una decisione, una richiesta: la proprietà di §30 per le richieste, come ADR
0013 §3 per i grant); `approvals.add` → `engine.request_approval`, nell'ordine di `store.grant` →
`AUTHORIZATION_GRANTED`: l'entità esiste prima del fatto che la cita. Al retry, dopo il controllo
dei risultati (§5) e prima del Guardian, l'executor cerca fra `approvals.for_task` l'ultima
PENDING di questo step: se non è scaduta chiama `engine.request_approval` con quella e ritorna
(`decision=None`, `approval` = quella) — nessuna seconda decisione, nessuna seconda richiesta
(finestra 5). Se è **scaduta** (`expires_at <= now`) la chiamata è rifiutata come **precondizione**
(decisione C): `ExecutorError` "approval … expired … it is not asked again", nulla scritto, la
richiesta resta PENDING com'è. Così **una seconda `Approval` per lo stesso step nasce solo da una
nuova decisione del Guardian** (finestra 6: grant esaurito → `REQUIRES_APPROVAL` → nuova
decisione → nuova richiesta), mai da un retry. Una PENDING di uno step RUNNING con il task
EXECUTING non ha altra origine che la finestra 5: da WAITING_APPROVAL si esce solo con `approve`,
`deny`, `cancel`, `expire`. `AlreadyExistsError` da `add` non viene catturata: con il controllo
prima del Guardian è raggiungibile solo da due executor sullo stesso step (ADR 0008 §11).

**La risposta: `respond` prima, l'engine dopo.** Chi risponde (l'API di M8.1; qui i test) fa
`approval = await approvals.respond(id, status=…, responded_by=…, now=…)` e poi
`engine.approve(task_id, approval)` o `engine.deny(task_id, approval=approval)`, **in
quest'ordine**: se l'engine si muovesse prima e `respond` cadesse, il task sarebbe QUEUED con
una richiesta ancora PENDING e il retry dell'executor la richiederebbe in un ciclo. Al retry con
il task EXECUTING, lo step RUNNING, nessun risultato e nessuna PENDING, l'executor prende
**l'ultima GRANTED dello step in ordine di inserimento** e la passa a `_grant` (ADR 0013 §3,
invariato): l'ultima, perché una seconda richiesta sullo stesso step nasce solo quando il grant
della prima non è più usabile. Senza GRANTED: `select_authorization` sui grant di policy. Una
GRANTED incoerente (altro task, step, capability) è `ApprovalMismatchError` prima di ogni
scrittura (ADR 0012 §2).

**Chi chiude un task che aspetta una richiesta scaduta è `recover()`** (decisione C).
`TaskEngine.__init__` prende `approvals: ApprovalStore` keyword-only, **obbligatorio**: un engine
che non vede le richieste non può chiuderle, e un default `None` sarebbe un buco silenzioso.
`recover()` (ADR 0008 §6) aggiunge un secondo ciclo dopo gli orfani: per ogni task in
`tasks(states={WAITING_APPROVAL})` legge `approvals.for_task`, prende **l'ultima PENDING** (quella
che il task aspetta) e, se `expires_at <= now` (verso chiuso), sotto il lock del task ricarica e
ricontrolla — ancora WAITING_APPROVAL, la richiesta ancora PENDING e scaduta; una risposta
arrivata nel frattempo è la finestra 5c, non questa — e applica la riga **`expire`** già in
tabella (WAITING_APPROVAL → EXPIRED, `TASK_EXPIRED`; nessuna riga nuova) con attore
`SYSTEM_ACTOR` (`task-engine`), `reason = "approval <id> expired at <istante>"`, payload
`{"approval_id", "expires_at"}`, senza la guardia sul `deadline` (che è del metodo `expire`, non
della riga). Un task WAITING_APPROVAL senza PENDING scaduta, o senza alcuna PENDING (risposta già
nello store, finestra 5c; oppure nessuna richiesta nello store, finestra 5b), è lasciato dov'è.
`RecoverySummary` guadagna `expired`. **Lo store non viene toccato**: la richiesta resta PENDING
(record immutabile), il fatto è `TASK_EXPIRED`; `ApprovalStatus.EXPIRED` resta nel dominio senza
scrittore in v0.1.

**Le due regole di `recover()`, da leggere insieme** (confermato in review il 2026-09-06). Sono
due perché guardano due stati diversi, e insieme non lasciano scoperto nessun task fermo:

| Task | Sintomo | Regola | Esito |
|---|---|---|---|
| EXECUTING | silenzioso da `orphan_after` (nessun heartbeat) | orfani (ADR 0008 §6) | FAILED, codice `orphaned` |
| WAITING_APPROVAL | l'ultima `Approval` PENDING è scaduta | richieste scadute (questo §) | EXPIRED, `TASK_EXPIRED` |

Un task **EXECUTING** con una PENDING scaduta — la finestra 5 più un ritardo oltre il TTL: la
richiesta è nello store, ma il task non è mai arrivato ad aspettarla — cade nella **prima** riga,
non nella seconda: il retry dell'executor è rifiutato (`ExecutorError` "expired"), il task tace, e
la regola degli orfani lo fallisce come qualunque altro EXECUTING senza segni di vita. È il
comportamento voluto: quel task non sta aspettando l'utente, sta fermo, e ciò che lo descrive è
"nessuno lo sta portando avanti", non "una domanda è scaduta". La seconda riga guarda solo
WAITING_APPROVAL perché solo lì la richiesta scaduta *è* il motivo per cui il task non si muove.

### 7. Finestra 9a: lo step FAILED per verifica chiude il task

Decisione D: è la regola di asimmetria di M5.2 (ADR 0014 §4), e sta all'executor applicarla. La
precondizione "step RUNNING" è rivista: se lo step è FAILED, il task EXECUTING e l'ultimo
`STEP_FAILED` dell'audit di quello step porta un `error` con codice `verification.failed` (il
codice dello step è sempre questo: un verifier che solleva è un fallimento con causa
`verification.exception`, ADR 0014 §7), l'executor chiama `engine.fail(task_id, error)` con lo
**stesso** `ErrorMetadata` e ritorna (`decision=None`, `result=None`). Uno step FAILED per ogni
altro motivo (`tool.refused`, `grant_vanished`, risultato FAILED) lascia il task EXECUTING per
decisione (ADR 0014 §4, decisione C) e resta `ExecutorError` "not RUNNING"; uno step FAILED nella
trail senza `STEP_FAILED` nell'audit è la finestra 9 (buco dell'engine) e resta `ExecutorError`.
È il completamento di un'operazione che l'executor stesso aveva iniziato, come la riparazione
della finestra 1.

### 8. Ordine delle scritture e finestre di crash

Questa tabella **sostituisce** quella di ADR 0013 §8 ed estende ADR 0014 §6 (rimandi di stato
in entrambi). Ordine normale: precondizioni → ripresa (§5, §6, §7: solo letture) → [`store.grant`
→ `AUTHORIZATION_GRANTED`] → `authorize` → [`consume`] → tool → timbro → `results.add` →
`TOOL_EXECUTED` → `verify` → `EXECUTION_VERIFIED` → `complete_step` | `fail_step` [+ `fail`].
Richiesta: `approvals.add` → `request_approval`. Risposta: `respond` → `approve` | `deny`.
"Retry" è la stessa chiamata `execute(task_id, step_id, arguments)` ripetuta. Le righe con
**Riparato.** hanno un test `test_window_<n>_…` in `tests/executive/test_executor_recovery.py`
(`REPAIRED`), e viceversa: `tests/docs/test_adr_recovery.py` confronta le due liste. Le altre
righe hanno il test del comportamento dichiarato.

| # | Il processo muore dopo… | …e prima di | Stato che resta | Retry |
|---|---|---|---|---|
| 0 | una precondizione fallita, o `authorization_from_approval` | qualsiasi scrittura | nulla scritto | riparte da zero |
| 1 | `store.grant` | `AUTHORIZATION_GRANTED` | grant nello store, `uses = 0`, audit senza evento | `AlreadyExistsError` → rilettura, stesso `approval_id` → l'audit non ha l'evento → scritto ora (ADR 0013 §3). **Riparato.** |
| 2 | `AUTHORIZATION_GRANTED` | `authorize` | grant e audit coerenti, nessuna decisione | grant riletto, audit trovato → nuova decisione. Nessun buco. |
| 3 | `PERMISSION_DECIDED` (dentro il Guardian) | il ritorno della decisione | un `PERMISSION_DECIDED` senza seguito | nuova decisione, secondo `PERMISSION_DECIDED`. Non riparato: ogni decisione è un evento (ADR 0011 §8). |
| 4 | `engine.deny` → `save` (task DENIED) | `STATE_CHANGED` / `TASK_DENIED` | task DENIED senza evento né audit | `ExecutorError` (task non EXECUTING). Buco dell'engine (ADR 0008 §4). **Non riparato.** |
| 5 | `approvals.add` | `engine.request_approval` | `Approval` PENDING nello store, task EXECUTING, step RUNNING | la PENDING dello step è ritrovata → `request_approval` con quella; nessuna decisione nuova, nessuna seconda `Approval` (§6). **Riparato.** |
| 5b | `request_approval` → `save` (WAITING_APPROVAL) | `STATE_CHANGED` / `APPROVAL_REQUESTED` | task in attesa senza evento; l'`Approval` **è** nello store | `ExecutorError` (task non EXECUTING). La richiesta è rispondibile: `respond` → `approve` funziona. Resta il buco dell'engine (ADR 0008 §4): trail e audit senza la richiesta. **Non riparato**, declassato da "richiesta persa" a "evento mancante". |
| 5c | `approvals.respond` | `engine.approve` / `deny` | risposta nello store, task WAITING_APPROVAL | non è dell'executor (task non EXECUTING) né di `recover()` (nessuna PENDING): chi risponde (M8.1) trova un task WAITING_APPROVAL con una richiesta risolta e chiama `approve`/`deny` di nuovo. **Dichiarato → M8.1.** |
| 6 | `consume` | il tool | grant speso, nessun effetto, step RUNNING | la GRANTED dello step dà il grant esaurito → `REQUIRES_APPROVAL` → seconda `Approval` dello stesso step, da una seconda decisione (§6). Accettato (ADR 0012 §6). |
| 7a | il tool (effetto prodotto) | `results.add` | effetto, nessuna traccia | il tool **riesegue** con una decisione nuova (`write_note` sovrascrive, `echo` è innocuo; grant monouso speso → domanda all'utente). **Non riparabile per costruzione**: l'effetto e l'`INSERT` sono due sistemi; la finestra è ridotta a questo istante. Limite dichiarato (decisione J, sotto). |
| 7b | `results.add` | `TOOL_EXECUTED` | risultato nello store, audit senza | il risultato dello step è ritrovato, nessun `TOOL_EXECUTED` lo nomina → scritto ora con `recovered`, poi si prosegue (§5). Il tool non gira. **Riparato.** |
| 8 | `TOOL_EXECUTED` (risultato non SUCCEEDED) | `fail_step` | audit "eseguito", step RUNNING | `fail_step` con l'errore del risultato riletto. **Riparato.** |
| 8a | `TOOL_EXECUTED` (SUCCEEDED) | `EXECUTION_VERIFIED` | eseguito, non verificato | il verifier gira sul risultato riletto, `EXECUTION_VERIFIED` con `recovered`, poi chiusura. **Riparato.** |
| 8b | `EXECUTION_VERIFIED` (passata) | `complete_step` | verificato, step RUNNING | `complete_step` con il risultato riletto; né tool né verifier. **Riparato.** |
| 8c | `EXECUTION_VERIFIED` (fallita) | `fail_step` | verifica fallita scritta, step RUNNING | `fail_step` + `fail` con l'`error` dell'evento. **Riparato.** |
| 9 | `complete_step` / `fail_step` → `append_event` (`STEP_*`) | l'audit `STEP_*` | step COMPLETED/FAILED nella trail, audit mancante | `ExecutorError` (step non RUNNING). Buco dell'engine (ADR 0009 §5–6). **Non riparato.** |
| 9a | `fail_step` (`STEP_FAILED` con `verification.failed`) | `engine.fail` | step FAILED, task EXECUTING, `is_blocked` | `engine.fail` con l'`error` di `STEP_FAILED` (§7). **Riparato.** |
| 10 | `fail_step` per `grant_vanished` / `tool.refused` | — | come 9; con `tool.refused` il grant è speso | come 9; il grant speso costa una nuova approvazione. |

**La finestra 7a resta dichiarata (decisione J), e il suo presidio è in codice** (review del
2026-09-06). La riparazione della 7a è "il tool riesegue", e regge solo finché ogni tool
eseguibile promette che due volte è come una. La promessa non può dipendere dalla memoria di chi
scriverà il prossimo tool, quindi è dichiarata e verificata: `ela.tools.base.Tool` prende
`idempotent: ClassVar[bool]` **senza default** — la risposta è del singolo tool, e dimenticarla
non deve leggersi come un sì — dichiarato `True` da `EchoTool` (nulla è scritto) e da
`WriteNoteTool` (la nota è sovrascritta con lo stesso corpo); `ToolRegistry`, **in costruzione**,
rifiuta con `NotIdempotentError` ogni tool che dichiari `False` **o che non dichiari nulla** (un
dubbio non è un sì, §33), e il messaggio nomina la finestra 7a e il piano STARTED qui sotto. Così
il primo tool non idempotente non entra in un registro senza aver prima implementato il
protocollo; il controllo precede quello sui doppioni, perché è ciò che rende il tool pericoloso,
non la sua chiave.

Il piano, per quel giorno: il primo tool non idempotente porta con sé
l'id di esecuzione scritto prima dell'azione, in un `ExecutionResult` persistito con stato
STARTED prima che il tool agisca. Un retry che trova uno STARTED senza esito per lo stesso step
non riesegue: verifica (M5.2) se il tool ha lasciato un effetto verificabile e chiude lo step di
conseguenza, altrimenti lo marca FAILED con codice `execution.interrupted`. Nessun tool viene mai
avviato due volte per lo stesso execution id. `ExecutionStatus` guadagna STARTED; l'audit resta
`TOOL_EXECUTED` all'esito. È l'ADR di quel tool (M7.2 `model.complete`, o il primo con un costo
non ripetibile) a portarlo; in v0.1 i due tool sono idempotenti e nulla di questo esiste.

Nessun lock nell'executor, come prima; il `cancel` concorrente non visto fra lettura e tool
resta il limite in-process di ADR 0008 §11.

### 9. Regola architetturale 19: il Core non risponde alle proprie richieste

`check_approval_responders` in `tests/architecture/rules.py` (decisione F): in **ogni** modulo di
`src/ela` è segnalata ogni chiamata `<x>.respond(`. Un "sì" è dell'utente (§30: un "sì" fuori
contesto non autorizza; §62: chi chiede è ELA, chi risponde è l'utente): l'unico chiamante di
`respond` arriverà con l'API di M8.1, che sarà l'unica esenzione, per percorso, quando esisterà.
Le definizioni (`ports.py`, `approval_store.py`, `fakes.py`) non sono chiamate. Casi in
`violations.py` (l'executor e un modulo di `tasks` che chiamano `.respond(`: riportati; una
classe che lo definisce: no); vacuità (i tre moduli contengono `def respond(`; l'executor non
contiene `.respond(` e contiene `_approvals.add(` e `_results.add(`). Nessun contratto
import-linter: non è un import.

## Alternative considerate

- **`ExecutionResult` nel `TaskRepository`** — il repository tiene l'aggregato task; un risultato
  contiene contenuto dell'utente che `plan()` non deve trascinarsi. Tabella e port propri.
  Scartata (decisione dell'utente).
- **Il parametro `approval` di `execute` mantenuto per compatibilità** — due vie per la stessa
  risposta, una delle quali non sopravvive a un crash. Scartata (decisione dell'utente).
- **`decision_id`/`authorization_id` in `metadata` del risultato o in colonne dello store** —
  uno schema nascosto o un port che si allarga; un risultato che sa da quale decisione nasce è
  §32. Scartata (B).
- **Riusare una PENDING scaduta al retry** — l'utente vedrebbe una richiesta già morta (§33);
  **ignorarla e chiederne una nuova** — due PENDING per uno step e una seconda richiesta senza una
  seconda decisione. Precondizione, e il task lo chiude `recover()`. Scartate (C).
- **Finestra 9a lasciata all'orchestrator di M6.2** — è la regola di asimmetria dell'executor, e
  sta all'executor applicarla. Scartata (D).
- **`uses` salvato nella riga del risultato, o `None` al retry** — inventerebbe precisione o
  nasconderebbe un numero che lo store ha; il contatore di ora con `"recovered": true` dice la
  verità sull'origine. Scartata (E).
- **Nessuna regola 19** — "la review basta" non è verificabile; il Core che si autoapprova è il
  bypass che §30 esiste per impedire. Scartata (F).
- **Un secondo tipo di ritorno `Resumption`** — un `NamedTuple` in più per un campo opzionale;
  `decision: PermissionDecision | None` costa un `is not None` ai chiamanti. Scartata (G).
- **`add` di una richiesta non PENDING come `PortError` nominato** — è un bug del chiamante,
  come un `limit` non positivo. `ValueError`. Scartata (H).
- **`ResultStore`** — il port si chiama per l'entità, come `AuthorizationStore`. Scartata (I).
- **Chiudere la finestra 7a ora con uno STARTED** — nessun tool di v0.1 ne ha bisogno e uno
  stato senza scrittore sarebbe uno stub; arriva con il primo tool non idempotente. Rinviata (J).
- **`pending(task_id)` per task** — l'executor filtra `for_task` in memoria; l'inbox è per tutti i
  task. Scartata (A).
- **`pending` senza `now`, con il filtro sulla scadenza lasciato al chiamante** — ogni chiamante
  riscriverebbe il verso chiuso, e uno prima o poi lo sbaglierebbe; `now` opzionale lo tiene in
  una riga sola, accanto a quella di `respond`, e lo store resta senza orologio. Scartata
  (review).
- **`Tool.idempotent` con default `True`** — un tool nuovo erediterebbe il sì senza che nessuno ci
  pensi, cioè esattamente il rischio che il presidio esiste per togliere. Nessun default, e chi
  non dichiara è rifiutato. Scartata (review).
- **Solo una nota nell'ADR sul primo tool non idempotente** — una nota si legge se ci si ricorda
  di cercarla; un rifiuto in costruzione si incontra. Scartata (review).
- **`ApprovalStore` opzionale nell'engine** — un engine che non vede le richieste non le chiude,
  in silenzio. Obbligatorio. Scartata.
- **Lo store scrive `EXPIRED` sulla richiesta scaduta** — il record è immutabile; il fatto è
  `TASK_EXPIRED`. Scartata (C).
- **FK su `task_id` delle due tabelle** — store separati dal repository, come `authorizations`;
  un fake senza repository non potrebbe onorare il contratto. Scartata.
- **`UNIQUE (task_id, step_id)` su `execution_results`** — l'executor rifiuta due risultati;
  un vincolo in SQL arriverà con un ADR se un secondo scrittore lo richiederà. Rinviata.

## Conseguenze

- `Tool.idempotent` (senza default) e `NotIdempotentError` in `ela.tools`, con il rifiuto del
  `ToolRegistry` in costruzione: la riparazione della finestra 7a non dipende da chi ricorda.
- `ApprovalStore`, `ExecutionResultStore`, `ApprovalNotAnswerableError`,
  `ApprovalAlreadyAnsweredError`, `ApprovalExpiredError`, `ANSWERS`, `check_answer` in
  `ela.ports` (diciassette port); `ExecutionResult.decision_id` e `authorization_id` nel dominio;
  `FakeApprovalStore`, `FakeExecutionResultStore` in `ela.testing`; `SqlApprovalStore`,
  `SqlExecutionResultStore`, `ApprovalRow`, `ExecutionResultRow`, i mapper e la migrazione `0004`
  in `ela.infrastructure.persistence`; `APPROVAL_NAMESPACE`, `RECOVERED`, `Execution.decision`
  opzionale, `Executor(approvals=, results=)`, `execute` senza `approval` in `ela.executive`;
  `TaskEngine(approvals=)`, `RecoverySummary.expired` in `ela.tasks`.
- **L'executor sopravvive a un crash**: fino a M5.2 era utilizzabile solo in-process; ora un retry
  riprende dalla prima scrittura mancante, e ciò che non si può riparare (7a) è un istante
  dichiarato. M6.2 può chiamare `execute` di nuovo dopo un riavvio, senza tenere nulla in memoria.
- **Per M6.2 (orchestrator).** Un `ExecutorError` "expired" su una richiesta scaduta non si
  ritenta; un task EXECUTING con `is_blocked` e uno step FAILED per verifica si chiude
  ritentando lo step (§7); ogni altro step FAILED è dell'orchestrator. `Execution.decision` può
  essere `None`.
- **Per M8.1 (API).** Chi risponde chiama `respond` e poi `approve`/`deny`, in quest'ordine, ed
  è l'unica esenzione alla regola 19; riprende i task WAITING_APPROVAL con una richiesta già
  risolta (finestra 5c); `pending()` è l'inbox; `DEFAULT_APPROVAL_TTL` resta un setting da fare.
- **Per M7.2 e per il primo tool non idempotente.** Lo STARTED di §8 (decisione J).
- **Limiti dichiarati.** Le finestre 3, 4, 5b, 5c, 6, 7a, 9 e 10 di §8. La ripresa legge l'audit
  per `result_id`: un audit alterato può far riprendere dal punto sbagliato, ed è `verify_chain`
  (su richiesta, ADR 0007) a dirlo, non ogni `execute`. Il `cancel` concorrente non visto.
- L'audit di una ripresa: gli stessi tipi di una chiamata normale, con `"recovered": true` sugli
  eventi scritti al retry. Gli argomenti, l'`output`, il `prompt` fuori da `APPROVAL_REQUESTED` e
  il contenuto confrontato non vi entrano mai, nemmeno al retry.
- Regola 19 in `tests/architecture/rules.py` con casi positivi e negativi; le tabelle di §1, §3 e
  §8 sono verificate dal codice (`tests/docs/test_adr_ports.py`, `test_adr_persistence.py`,
  `test_adr_recovery.py`) con casi negativi; i contratti dei due store girano su fake e SQLite;
  ogni finestra riparata ha il suo test di crash e retry sui fake, e le finestre 1, 5, 7a, 7b,
  8a, 8b e 9 anche su SQLite con la catena verificata dopo il retry.
