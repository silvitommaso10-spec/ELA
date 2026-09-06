# 0013. Executor: uno step per chiamata, grant scelto e consumato prima del tool, ordine delle scritture, `ToolRegistryPort` e `AuthorizingGuardianPort`, tool v0.1 e workspace, regola 16

- **Stato:** Accettata
- **Data:** 2026-09-06
- **Riferimenti spec:** §12, §13, §14, §15, §17, §18, §23, §27, §28, §29, §30, §32, §33, §47, §49, §51, §52, §57, §58, §63, §64, §65
- **Milestone:** M5.1

## Contesto

§27 mette ogni azione con effetti esterni in fila: Planner → Capability → Guardian → Authorization
→ Tool → Device → Audit. Fino a M4.3 esistevano tutti i pezzi e nessuno che li mettesse in fila:
il catalogo (ADR 0010), il Guardian con `authorize` (ADR 0011), la nascita del grant da
un'`Approval` e il `consume` atomico (ADR 0012), l'engine che muove task e step (ADR 0008, 0009),
il port `ToolPort` con il solo fake (ADR 0005 §5). Le domande erano: quanto esegue una chiamata
dell'executor e chi chiude lo step; da dove arriva il grant che il Guardian giudica e quale, fra
molti; cosa fa l'executor con ciascun esito del Guardian; quale istante serve ad `authorize` e a
`consume`; in che ordine scrive e cosa lascia un crash; come l'executor conosce i tool senza
importarli; cosa un tool controlla da solo su un percorso; come si impedisce che un secondo
modulo chiami un tool. Le decisioni A–J sono dell'utente (2026-09-06, `docs/milestones/M5.1.md`).

## Decisione

### 1. Una chiamata esegue uno step, e lo chiude

`ela.executive.executor.Executor.execute(task_id, step_id, arguments, *, approval=None) ->
Execution`. Uno step eseguibile dichiara **esattamente una** capability
(`required_capabilities` di lunghezza 1; decisione B): l'executor la legge dallo step, non dal
chiamante. Dopo il tool l'executor chiama `engine.complete_step` (risultato SUCCEEDED) o
`engine.fail_step` (ogni altro stato, con l'errore del risultato o uno coniato dallo stato):
**l'executor non lascia mai uno step RUNNING dopo una chiamata conclusa**. Ciò che resta a M6.2 è
la scelta dello step successivo (la camminata del grafo), non l'esito dello step appena eseguito.
`Execution(task, step_id, graph, decision, authorization, result, approval)` è un `NamedTuple`
del modulo, come `GraphState` in `ela.tasks`: non è un'entità di §49.

### 2. Precondizioni: nulla scritto se una fallisce

Nell'ordine: il task è EXECUTING (`ExecutorError`); lo step è nel piano (`UnknownStepError`) ed è
RUNNING (`ExecutorError`: "start the step first" — è la garanzia che le dipendenze sono
COMPLETED, e uno step RUNNING sopravvive a WAITING_APPROVAL → QUEUED → EXECUTING, ADR 0009 §8);
lo step dichiara una capability (`ExecutorError`); la capability è nel catalogo
(`CapabilityNotFound`); un tool la implementa (`ToolNotFound`) — **prima** del Guardian e del
`consume`: decidere e spendere un grant monouso per un tool che non c'è brucerebbe
un'approvazione (ADR 0012 §6). Un'`Approval` incoerente è `ApprovalMismatchError` (ADR 0012 §2),
prima di ogni scrittura.

### 3. Il grant: da un'`Approval` o dallo store, mai uno che non copre

Con `approval`: `authorization_from_approval(..., now=<orologio dell'executor>,
authorization_id=uuid5(AUTHORIZATION_NAMESPACE, str(approval.id)), ttl=authorization_ttl)`.
**L'id del grant è deterministico per approvazione** (decisione H): un "sì" genera un grant, sempre
lo stesso, quante volte si ritenti. `store.grant`; su `AlreadyExistsError` l'executor rilegge il
grant, esige `approval_id` uguale (altrimenti `ExecutorError`) e **ripara il buco**: se l'audit del
task non ha un `AUTHORIZATION_GRANTED` con quell'`authorization_id`, lo scrive ora. Poi l'audit
`AUTHORIZATION_GRANTED`: attore `Actor(USER, granted_by)`, `created_at` del grant, `approval_id`,
`authorization_id`, task, step, capability, `decision_id` dell'approvazione, payload con
`expires_at`, `max_uses`, `targets`, `scope`, mai il `prompt` (ADR 0012 §6).

Senza `approval`: `store.for_capability` e `store.uses` per ciascuno, poi la funzione pura
`select_authorization(candidates, *, task, step, targets, now)` (decisione F): **copre** se
`task_id`/`step_id` assenti o uguali e `scope_covers(grant.scope, targets)` (funzioni pubbliche di
`ela.permissions.scope`: riuso); **usabile** se non scaduto (verso chiuso) e `uses < max_uses`. Prima
i grant legati a questo step, poi gli altri, a parità l'ordine di concessione; il primo che copre
ed è usabile, altrimenti il primo che copre (così il motivo del Guardian nomina il grant scaduto o
esaurito e la domanda lo spiega), altrimenti nessuno. Un grant che **non copre non viene mai
consegnato**: il Guardian lo leggerebbe come incoerenza del chiamante e negherebbe (ADR 0011 §6),
trasformando "un'altra nota nello stesso step" in un diniego invece che in una domanda.

### 4. Il Guardian attraverso un port: `AuthorizingGuardianPort`

L'executor non dipende dalla classe `PermissionGuardian` (decisione J). `ela.ports` prende
`AuthorizingGuardianPort`, async, con il solo `authorize` — la stessa firma di `decide` (ADR 0011
§5). Un port ha una modalità sola (ADR 0005 §1), quindi `authorize` non poteva entrare in
`PermissionGuardianPort`. Nessun fake: il Guardian vero è puro e gira sull'`AuditLog` fake, ed è
l'unica implementazione registrata nei contract test (`tests/contracts/test_authorizing_guardian.py`).
Il `FakePermissionGuardian` resta al contratto di `decide`.

### 5. Gli esiti del Guardian sono mosse dell'engine

L'executor gestisce gli esiti del Guardian e la chiusura dello step; l'orchestrator (M6.2)
sceglie lo step successivo. Tabella confrontata con il codice da `tests/docs/test_adr_executor.py`
(operazioni dell'engine e codici di errore):

| Esito | Operazione | Codice |
|---|---|---|
| `DENIED` | `deny_by_decision` | — |
| `REQUIRES_APPROVAL` | `request_approval` | — |
| `ALLOWED`, `consume` solleva `AuthorizationNotUsableError` | `request_approval` | — |
| `ALLOWED`, `consume` solleva `NotFoundError` | `fail_step` | `grant_vanished` |
| `ALLOWED`, il tool solleva `NotAllowedError` | `fail_step` | `tool.refused` |
| `ALLOWED`, il tool solleva altro | `fail_step` | `tool.exception` |
| `ALLOWED`, risultato non SUCCEEDED | `fail_step` | errore del risultato |
| `ALLOWED`, risultato SUCCEEDED | `complete_step` | — |

`DENIED` porta il **task** in DENIED (decisione E): è la riga che ADR 0004 e ADR 0008 hanno
previsto per "il Guardian nega"; un retry è un task nuovo (ADR 0004 P1). `REQUIRES_APPROVAL`:
l'executor costruisce l'`Approval` PENDING — `created_at = decision.created_at`, task, step,
capability, **`targets` = le stringhe di `decision.metadata["targets"]`** (ADR 0012 §6: il legame
decisione → approvazione nasce qui), `prompt = "<capability>[ on <targets>] for step <id>
(<goal>): <motivo>"` (nomina bersagli e motivo, mai gli argomenti: il prompt finisce nell'audit come
`reason` di `APPROVAL_REQUESTED`), `decision_id`, **`expires_at = created_at + approval_ttl`** con
`DEFAULT_APPROVAL_TTL = 24 ore` e tetto `MAX_APPROVAL_TTL = 7 giorni` (`ValueError` alla
costruzione fuori da `(0, 7 giorni]`: nessun TTL senza tetto, la regola di M4.2 e M4.3; review
del 2026-09-06; setting in M8.1 entro lo stesso tetto) — e chiama
`engine.request_approval`. Chi fa scadere un task rimasto WAITING_APPROVAL **non è l'executor**:
recovery o Proactive Core, rinvio registrato. Un `consume` che solleva scaduto/esaurito dopo un
`ALLOWED` (un altro executor è arrivato prima) **chiede di nuovo**; un grant sparito fra `authorize`
e `consume` è un'incoerenza dello store: `fail_step` con codice `grant_vanished` e audit, così il
task non resta EXECUTING fino alla recovery e l'evento è visibile; nulla viene eseguito (decisione
G).

### 6. Un solo istante per `authorize` e `consume`: `decision.created_at`

ADR 0012 §6 vuole lo stesso istante per il giudizio e per la spesa. `authorize` non ha un
parametro `now` e il Guardian legge il proprio `Clock` (lo stesso oggetto del Core): la decisione
torna con `created_at`, che **è** l'istante del giudizio, e l'executor lo passa a
`consume(authorization.id, now=decision.created_at)` (decisione C). Nessuna estensione del port. Lo
stesso istante è il `created_at` dell'`Approval`. `consume` è chiamato **solo se la decisione si
regge sul grant**: `outcome is ALLOWED` e la regola è in `CONSUMING_RULES` (ADR 0011 §6, §9):

| Regola | Consuma |
|---|---|
| `ALLOW` | no |
| `ALLOW_WITHIN_SCOPE` | no |
| `APPROVAL_UNLESS_AUTHORIZED` | sì |
| `AUTHORIZATION_REQUIRED` | sì |

Un `ALLOWED` senza grant applicato non consuma nulla, e l'audit lo dice (`authorization_id`
nullo in `TOOL_EXECUTED`).

### 7. Il tool, e l'unico punto che lo chiama

Prima di `tool.execute(decision, arguments)` l'executor verifica `outcome is ALLOWED` e
`capability_id` uguale (il tool lo riverifica: difesa in profondità, ADR 0005 §5). Un'eccezione
del tool diversa da `NotAllowedError` diventa un `ExecutionResult` FAILED con
`ErrorMetadata(code="tool.exception", message=<tipo dell'eccezione>)` — il tipo, mai il
messaggio (§57, come ADR 0011 §8) — così `TOOL_EXECUTED` registra sempre che un tool è stato
invocato, anche quando è caduto a metà; poi `fail_step`. `NotAllowedError` è un rifiuto **prima**
di agire: nessun `TOOL_EXECUTED`, `fail_step` con `tool.refused`; il grant, se consumato, resta
speso (ADR 0012 §6). Il tool riporta i propri fallimenti come risultati FAILED con un codice, mai
come eccezioni (§63 "eseguire non è riuscire"), come un provider (ADR 0005).

`TOOL_EXECUTED`: `created_at` del risultato, attore ELA, `summary = "execute: <status>
<capability> by <tool>"`, task, step, capability, `decision_id`, `authorization_id` (il grant
consumato, o nullo: "con quale autorizzazione" è quella su cui la decisione si regge; un grant
consegnato e ignorato non entra qui, è già nel `PERMISSION_DECIDED` se il Guardian lo cita —
review del 2026-09-06), `tool_name`, `device_id` nullo, `error` del risultato, payload `{status,
result_id, targets, duration_ms, device: "local", uses}`. **Mai** gli argomenti né l'`output`: il
messaggio di `core.echo` e il corpo di una nota sono contenuto dell'utente (§57). "Device per ora
è local": nessun `Device` registrato per il Core; il Device Orchestrator (§17) porterà un
`DeviceId`.

### 8. Ordine delle scritture e finestre di crash

Nessuna transazione fra port (ADR 0006 §4). Le scritture sono nell'ordine in cui il codice le
fa; "retry" è la stessa chiamata `execute(task_id, step_id, arguments[, approval])` ripetuta dal
chiamante. I buchi che si possono riparare vengono riparati; gli altri sono dichiarati qui
(review del 2026-09-06):

| # | Il processo muore dopo… | …e prima di | Stato che resta | Retry |
|---|---|---|---|---|
| 0 | una precondizione fallita, o `authorization_from_approval` | qualsiasi scrittura | nulla scritto | riparte da zero |
| 1 | `store.grant` | `AUTHORIZATION_GRANTED` | grant nello store, `uses = 0`, audit senza evento | `AlreadyExistsError` → rilettura, stesso `approval_id` → l'audit non ha l'evento → **scritto ora**. Riparato. |
| 2 | `AUTHORIZATION_GRANTED` | `authorize` | grant e audit coerenti, nessuna decisione | grant riletto, audit trovato → nessun duplicato → nuova decisione. Nessun buco. |
| 3 | `PERMISSION_DECIDED` (dentro il Guardian) | il ritorno della decisione | un `PERMISSION_DECIDED` senza seguito | nuova decisione, secondo `PERMISSION_DECIDED`. Non riparato: ogni decisione è un evento (ADR 0011 §8). |
| 4 | `engine.deny` → `save` (task DENIED) | `STATE_CHANGED` / `TASK_DENIED` | task DENIED senza evento né audit | `ExecutorError` (task non EXECUTING). Buco dell'engine (ADR 0008 §4); `engine.deny` ripetuto solleva `TaskEngineError` perché l'ultimo `STATE_CHANGED` non porta la chiave. **Non riparato.** |
| 5 | `engine.request_approval` → `save` (WAITING_APPROVAL) | `STATE_CHANGED` / `APPROVAL_REQUESTED` | task in attesa senza evento; l'`Approval` esisteva solo in memoria | `ExecutorError`. Il task aspetta un'approvazione che nessuno possiede: scade con la recovery/Proactive Core. **Non riparato.** Vale anche senza crash: l'`Approval` non è persistita in v0.1, chi chiama l'executor la deve tenere → **M5.3**. |
| 6 | `consume` | il tool | grant speso (`uses + 1`), nessun effetto, nessun `TOOL_EXECUTED`, step RUNNING | il grant monouso è riselezionato ed è esaurito → `REQUIRES_APPROVAL` → si chiede di nuovo (ADR 0012 §6: meglio chiedere due volte). Un grant di policy con `max_uses > 1` è consumato di nuovo e il tool gira una volta. Accettato. |
| 7 | il tool (effetto prodotto) | `TOOL_EXECUTED` | nota scritta, nessuna traccia, step RUNNING | tutta la pipeline riparte: nuova decisione, il tool **riesegue** (`write_note` sovrascrive lo stesso corpo, `echo` è innocuo); con un grant monouso già speso → domanda all'utente e seconda esecuzione dopo il nuovo sì. **Limite dichiarato**: i risultati non sono persistiti → **M5.3**. |
| 8 | `TOOL_EXECUTED` | `complete_step` / `fail_step` | audit dice "eseguito", trail dice RUNNING | come 7: il tool riesegue e nasce un secondo `TOOL_EXECUTED`; il primo resta senza chiusura. **Non riparato** qui: un `TOOL_EXECUTED` SUCCEEDED di questo step senza `STEP_COMPLETED` deve chiudere lo step invece di rieseguire (il `result_id` è nel payload) → **M5.3**. |
| 9 | `complete_step` / `fail_step` → `append_event` (`STEP_*`) | l'audit `STEP_*` | step COMPLETED/FAILED nella trail, audit mancante | `ExecutorError` (step non RUNNING). Buco dell'engine (ADR 0009 §5–6); la cascata di `fail_step` interrotta si completa chiamando `engine.fail_step` di nuovo (idempotente per esito): compito dell'orchestrator. |
| 10 | `fail_step` per `grant_vanished` / `tool.refused` | — | come 9; con `tool.refused` il grant è speso | come 9; il grant speso costa una nuova approvazione (ADR 0012 §6). |

Il solo buco che l'executor ripara è l'1, quello che tocca una proprietà di §30 (un sì, un grant,
un evento). Gli altri sono buchi dell'engine già dichiarati (4, 5, 9) o il costo della non
persistenza di `Approval` ed `ExecutionResult` (5, 7, 8), che è la milestone **M5.3**
(`docs/milestones/M5.3.md`). **Vincolo:** `ApprovalStore` e la persistenza degli `ExecutionResult`
sono prerequisiti di M6.2 e M8.1; **fino a M5.3 l'executor è utilizzabile solo in-process** — il
chiamante tiene l'`Approval` in memoria e non sopravvive a un crash fra le finestre 5, 7 e 8.

Nessun lock nell'executor: il `consume` atomico decide fra due executor sullo stesso grant (ADR
0012 §5); fra la lettura dello stato e il tool un `cancel` concorrente non è visto (limite
in-process di ADR 0008 §11).

### 9. Un solo chiamante: regola architetturale 16

`check_tool_execute_callers` in `tests/architecture/rules.py`: in ogni modulo di `src/ela`
**tranne il percorso esatto `executive/executor.py`** segnala ogni chiamata `<x>.execute(`, salvo
quando il ricevitore è un nome in `SQL_EXECUTORS = {"session", "connection", "cursor"}`
(l'`execute` di SQLAlchemy nella persistenza: esenzione per nome, chiusa e testata). Euristica sui
nomi come le regole 5, 11, 12 e 15. Casi in `violations.py`; test di vacuità (`executor.py`
contiene `.execute(`). Nessun contratto import-linter: non è un import.

### 10. `ToolRegistryPort` e `AuthorizingGuardianPort`: due port introdotti

`ToolRegistryPort` (decisione D), sincrono come `CapabilityRegistryPort` (ADR 0005 §1): `get`,
`tools`. La chiave di ogni voce **è** `tool.capability_id`: un tool non può essere registrato sotto
un'altra capability; due tool per una capability sono `AlreadyExistsError`. Perché un port e non
l'import della classe: `ela.tools` ospiterà il tool di `model.complete` (M7.2), che importerà
`ela.providers`; il contratto 4 segue le catene indirette, e un `ela.executive` che importasse
`ela.tools` romperebbe quel giorno. Un test lo fissa da subito: `ela.executive` non importa
`ela.tools`. `ela.tools.registry.ToolRegistry(tools)` congela alla costruzione; `FakeToolRegistry`
in `ela.testing`; `tools_v01(*, root, clock, ids)` costruisce i due tool di questa milestone. Le
righe sotto sono lette da `tests/docs/test_adr_ports.py` come **introduzioni**, terza categoria
accanto a estensioni e sostituzioni: un port introdotto non deve esistere già.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `AuthorizingGuardianPort` | §27, §32 | async | `authorize` |
| `ToolRegistryPort` | §28 | sync | `get`, `tools` |

I port sono tredici; ADR 0005 prende nello stato il rimando.

### 11. I tool di v0.1

Ogni tool estende `ela.tools.base.Tool`: la verifica della decisione (ADR 0005 §5), i tempi e la
forma del risultato stanno lì una volta sola; un tool scrive `_run` e risponde con un `Outcome`
(output, oppure codice ed errore). Tabella confrontata con `tools_v01` e con le costanti dei tool
da `tests/docs/test_adr_executor.py`:

| Capability | Tool | Nome | Output | Codici di errore |
|---|---|---|---|---|
| `core.echo` | `EchoTool` | `core-echo` | `message` | `arguments.invalid` |
| `workspace.write_note` | `WriteNoteTool` | `workspace-notes` | `path`, `bytes` | `arguments.invalid`, `path.invalid`, `path.symlink`, `path.outside_workspace`, `path.is_directory`, `io.error` |

`model.complete` non ha tool (M7.2): l'executor solleva `ToolNotFound` prima di ogni scrittura.

### 12. `workspace.write_note` scrive solo dentro la workspace

`WorkspaceSettings` (pydantic-settings, prefisso `ELA_`, `.env` opzionale): `workspace_dir`, da
`ELA_WORKSPACE_DIR`, default `~/.ela/workspace` (specchio di `PersistenceSettings`; M8.1 unificherà).
`WriteNoteTool(root, clock, ids)`: `root` espansa, assoluta, creata con `0o700` se manca (§57) e
**risolta**: il confine è la directory reale. I bersagli dello scope (`workspace/notes`, ADR 0010
§5) sono relativi a questa radice: la cartella delle note è `$ELA_WORKSPACE_DIR/workspace/notes`; la
ridondanza del nome è nota e resta per M8.1.

Quattro controlli, tutti prima di toccare il disco, ognuno un FAILED con il suo codice e nulla
scritto: **`path.invalid`** — relativo, senza segmenti vuoti, `.` o `..`, senza `\` né NUL (la
sintassi delle voci di scope riscritta con `pathlib`: un tool non importa `ela.permissions`);
`a/../b` è rifiutato anche se risolverebbe dentro; **`path.symlink`** — nessun componente esistente
di `root / path` è un link, verso dentro o verso fuori: scrivere *attraverso* un link è un dubbio
(§33); **`path.outside_workspace`** — `(root / path).resolve()` non è sotto `root`: la rete di
sicurezza dietro i primi due; **`path.is_directory`**. Scrittura: directory intermedie `0o700`,
file aperto con `O_NOFOLLOW` e modo `0o600`, UTF-8, sovrascritto se esiste (una nota si riscrive: è
ciò che rende innocuo il retry di §8); `OSError` → `io.error`. Il tool **non** controlla lo scope
(è la decisione del Guardian, ADR 0011 §4) né che `path` coincida con `decision.metadata["targets"]`
(il legame decisione → esecuzione è `decision_id`): il tool protegge la workspace, lo scope
protegge la cartella. Un link inserito in una directory intermedia fra i controlli e l'`open` è un
limite dichiarato (workspace locale, singolo utente).

### 13. Contratto 7 a import diretti

`ela.executive.executor` importa `ela.tasks.engine`, che importa `ela.tasks.state_machine`; il
contratto import-linter 7 seguiva le catene indirette e l'avrebbe segnalato — come segnalerà
l'orchestrator e l'API, che useranno l'engine. La regola (ADR 0008 §12) è "nessuno *chiama*
`transition` fuori dall'engine": chi importa l'engine non lo può fare. Il contratto 7 passa ad
`allow_indirect_imports = "True"` come i contratti 2, 6 e 8; la regola 10 in pytest è diretta per
natura e non cambia; `test_direct_only_contracts_are_the_ones_whose_source_imports_the_domain`
elenca i quattro.

### 14. Gate e registrazioni

`ela.executive` e `ela.tools` entrano in `CRITICAL_PACKAGES` (100% branch, decisione I): l'executor
è il punto in cui "un Tool non può essere eseguito senza una `PermissionDecision`" diventa codice,
e il controllo dei percorsi di `write_note` è la difesa del filesystem. `EchoTool` e `WriteNoteTool`
sono registrati sotto `ToolPort` in `tests/contracts/implementations.py` (il secondo su una
directory temporanea), `ToolRegistry` e `FakeToolRegistry` sotto `ToolRegistryPort`,
`PermissionGuardian` sotto `AuthorizingGuardianPort`.

## Alternative considerate

- **`execute(input)` come nel prompt** — sostituire il port toglierebbe la verifica della
  decisione nel tool (ADR 0005 §5). Il port resta; `input` sono gli `arguments`. Scartata (A).
- **Una chiamata = una capability, lo step chiuso dal chiamante** (prima proposta) — uno step con
  due chiamate non avrebbe saputo quando è finito, e M6.2 avrebbe dovuto chiudere step che non ha
  eseguito. Uno step ha una capability, l'executor lo chiude. Scartata (B).
- **`decide`/`authorize` estesi con `now`** — una firma di port in più e la terza categoria
  "firma modificata" ancora a debito; `decision.created_at` è già l'istante del giudizio.
  Scartata (C).
- **L'executor riceve un `Mapping[CapabilityId, ToolPort]`** — nessun port, ma nessun contratto e
  nessun `NotFoundError` nominato; e la simmetria con `CapabilityRegistryPort` vale. Scartata (D).
- **L'executor ritorna l'esito e non muove il task** — il chiamante avrebbe dovuto rifare ciò che
  il dominio ha già previsto (`deny_by_decision`, `request_approval`). Scartata (E).
- **`Approval` senza scadenza** — un titolo aperto per sempre; 24 ore, setting in M8.1 (E).
- **`approval_ttl` senza tetto** — la regola di M4.2 e M4.3 è "nessun TTL senza tetto"; 7 giorni,
  `ValueError` oltre (review). Scartata.
- **Consegnare sempre il grant legato allo step** — "un'altra nota nello stesso step" sarebbe un
  `DENIED AUTHORIZATION_MISMATCH` invece di una domanda. Scartata (F).
- **`NotFoundError` da `consume` che esce** — lascerebbe il task EXECUTING fino alla recovery,
  senza un evento che spieghi. `fail_step` con `grant_vanished`. Scartata (G).
- **Id del grant dal generatore** — un retry dopo un crash fra `grant` e audit conierebbe un
  secondo grant dalla stessa approvazione: due "sì" da uno. Scartata (H).
- **Executor tipizzato su `PermissionGuardian`** — dipendenza dalla classe concreta; un port con il
  solo `authorize` costa una riga e tiene l'executor sulle astrazioni. Scartata (J).
- **`authorize` dentro `PermissionGuardianPort`** — un port metà sync e metà async, contro ADR
  0005 §1 e `test_adr_ports`. Scartata.
- **Un fake dell'`AuthorizingGuardianPort`** — il Guardian vero è puro e gira sull'`AuditLog`
  fake: un fake in più non avrebbe reso i test più semplici, solo meno veri. Scartata (J).
- **Tool che sollevano per un percorso rifiutato** — un'eccezione a metà lascerebbe l'audit senza il
  fatto che il tool è stato invocato; un risultato FAILED con codice è ciò che l'executor registra.
  Scartata.
- **`..` ammesso se risolve dentro** — la traversal è rifiutata come forma, non come esito (§33).
  Scartata.
- **Link verso dentro ammessi** — scrivere attraverso un link è un dubbio, e distinguere "dentro"
  da "fuori" al momento del controllo non vale al momento della scrittura. Scartata.
- **Il tool verifica anche lo scope** — duplicherebbe la decisione del Guardian con un secondo
  codice da tenere allineato; il tool protegge il confine che solo lui conosce (la workspace).
  Scartata.
- **Rule 16 con esenzione per package `infrastructure/`** — un tool chiamato da un modulo di
  persistenza non sarebbe visto; l'esenzione è per nome del ricevitore, e il caso negativo lo
  prova. Scartata.
- **Contratto 7 invariato, l'executor importa `ela.tasks` senza `engine`** — impossibile: l'engine è
  l'API del ciclo di vita. Scartata (§13).

## Conseguenze

- `Executor`, `Execution`, `select_authorization`, `approved_targets`, `AUTHORIZATION_NAMESPACE`,
  `DEFAULT_APPROVAL_TTL`, `MAX_APPROVAL_TTL`, `CONSUMING_RULES`, `LOCAL_DEVICE`, `TOOL_EXCEPTION`, `TOOL_REFUSED`,
  `GRANT_VANISHED`, `ExecutorError` sono l'API pubblica di `ela.executive`; `Tool`, `Outcome`,
  `check_decision`, `EchoTool`, `WriteNoteTool`, `ToolRegistry`, `tools_v01`, `WorkspaceSettings`,
  `ToolNotFound` e i codici di errore quella di `ela.tools`.
- `ela.ports` ha tredici port; ADR 0005 prende nello stato il rimando; `REQUIRED_PORTS` e
  `test_ports_are_exactly_the_thirteen_required` lo dicono con motivazione.
- **Per M6.2 (Planner e orchestrator).** Uno step eseguibile dichiara *esattamente una* capability
  (decisione B): un piano prodotto dal Planner con uno step a zero o più capability è un difetto
  del Planner, da rendere verificabile lì (validazione del piano o test). L'orchestrator sceglie lo
  step successivo, chiama `Executor.execute`, e non chiude mai uno step: l'executor lo ha già fatto.
  Estende il vincolo di ADR 0011 (Conseguenze).
- **Per M8.1.** `DEFAULT_APPROVAL_TTL` (24 ore, tetto `MAX_APPROVAL_TTL` 7 giorni) e
  `WorkspaceSettings` diventano setting con gli
  altri; `notes_scope` letto dall'ambiente; il nome della cartella delle note può cambiare lì con
  un ADR che sostituisca ADR 0010 §5.
- **Rinvio.** Chi fa scadere un task rimasto WAITING_APPROVAL oltre `Approval.expires_at` (e
  imposta `ApprovalStatus.EXPIRED`) non è l'executor: recovery o Proactive Core.
- **Per M5.3 (prerequisito di M6.2 e M8.1).** `ApprovalStore` (port, fake, SQLite, migrazione)
  e la persistenza degli `ExecutionResult`: l'executor persiste l'`Approval` prima di
  `request_approval` e legge la risposta dallo store; un `TOOL_EXECUTED` SUCCEEDED senza
  `STEP_COMPLETED` chiude lo step invece di rieseguire (finestra 8); un retry dopo la finestra 7
  non riesegue il tool. **Fino a M5.3 l'executor è utilizzabile solo in-process.**
- **Limiti dichiarati.** Le finestre 3, 4, 6, 9 e 10 di §8. Il TOCTOU sui link intermedi della
  workspace. Il `cancel` concorrente non visto fra lettura e tool.
- L'audit di una chiamata: `AUTHORIZATION_GRANTED` (se un'approvazione entra), `PERMISSION_DECIDED`
  (Guardian), poi `TOOL_EXECUTED` e `STEP_COMPLETED`/`STEP_FAILED`, oppure `TASK_DENIED`, oppure
  `APPROVAL_REQUESTED`. Gli argomenti, l'`output` e il `prompt` non vi entrano mai.
- Regola 16 in `tests/architecture/rules.py` con casi positivi e negativi; le tabelle di §5, §6, §10
  e §11 sono verificate dal codice (`tests/docs/test_adr_executor.py`, `tests/docs/test_adr_ports.py`)
  con casi negativi; il contratto 7 è a import diretti.
