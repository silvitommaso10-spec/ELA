# 0014. Verification: condizioni di successo come vocabolario chiuso per capability, `VerifierPort` e `VerifierRegistryPort`, verifica prima di `complete_step`, verifica fallita → task FAILED, `EXECUTION_VERIFIED`, regole 17 e 18

- **Stato:** Accettata
- **Data:** 2026-09-06
- **Riferimenti spec:** §13, §14, §15, §20, §27, §32, §33, §57, §58, §63, §64, §65
- **Milestone:** M5.2

## Contesto

§20 chiude la sequenza Perception → Planning → Permission → Action → **Verification**, e §63 la
motiva: "non considerare l'esecuzione come prova del successo. Se ELA modifica un file, deve
poter verificare che sia corretto". Fino a M5.1 l'executor (ADR 0013 §5) chiamava
`complete_step` appena il tool rispondeva SUCCEEDED: la parola del tool, non un fatto. §13 dà a
ogni step le sue `success_conditions`, ma il campo era solo dato: testo libero che nessuno
leggeva. Le domande erano: chi verifica e con che cosa; come si rende valutabile una condizione
senza un Planner e senza un modello; cosa succede a uno step, e al task, quando la verifica
fallisce; come si distingue un tool che fallisce da un tool che mente; dove finisce ciò che la
verifica ha confrontato; come si impedisce che un secondo modulo completi uno step senza
verificare, e che un verifier scriva. Le decisioni A–J sono dell'utente (2026-09-06,
`docs/milestones/M5.2.md`).

## Decisione

### 1. Due port introdotti: `VerifierPort` e `VerifierRegistryPort`

Il verifier è un oggetto **separato dal tool per costruzione** (decisione D): sullo stesso
oggetto la verifica sarebbe il tool che si autocertifica. `ela.ports` prende `VerifierPort`
(async: legge) con `capability_id`, `name`, `conditions` — il **vocabolario**, le condizioni che
sa controllare — e `verify(conditions, arguments, result) -> tuple[ErrorMetadata, ...]`: un
fallimento per condizione che non vale, nell'ordine dato, vuoto se tutte valgono; e
`VerifierRegistryPort` (sync, `get`, `verifiers`), chiave `verifier.capability_id`, specchio di
`ToolRegistryPort` (ADR 0013 §10). Le righe sotto sono lette da `tests/docs/test_adr_ports.py`
come introduzioni.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `VerifierPort` | §20, §63 | async | `capability_id`, `name`, `conditions`, `verify` |
| `VerifierRegistryPort` | §63 | sync | `get`, `verifiers` |

I port sono quindici; ADR 0005 prende nello stato il rimando.

**Contratto di `verify`** (`tests/contracts/test_verifier.py`, fake e reali), fail-safe da solo
(§33): un risultato di un'altra capability → `verification.wrong_capability`; un risultato non
SUCCEEDED → `verification.not_succeeded`; nessuna condizione → `verification.no_conditions` (la
verità vuota è un dubbio); una condizione fuori dal vocabolario → `verification.unknown_condition`,
una per condizione, e nessuna condizione nota viene guardata. Mai un pass per questi casi, mai
un'eccezione. Ogni fallimento porta `details["condition"]`. Le quattro precondizioni e i loro
codici vivono in `ela.ports.check_verifiable`, condivisa dal fake e dalla base dei verifier: sono
il contratto del port, come `NotAllowedError` lo è di `ToolPort`. Il verifier è **di sola
lettura per costruzione** (decisione I, §10) e non possiede tool, Guardian né store (il contratto
lo prova sugli attributi e sulle annotazioni).

### 2. Le condizioni di successo sono un vocabolario chiuso per capability

In v0.1 non c'è un Planner e un verifier deterministico non può valutare testo libero. Ogni
verifier dichiara le condizioni che sa controllare (`conditions`, attributo di classe come
`error_codes` di un tool) e i codici che può riportare (`failure_codes`). Il Planner di M6.2
emetterà condizioni dal vocabolario del verifier, come emette argomenti dallo schema della
capability. `ela.tools.verify.Verifier` è la base: il contratto di §1 una volta sola in
`verify`, la sottoclasse scrive `_check(condition, arguments, result) -> ErrorMetadata | None`.
Codice comune in più: `verification.arguments_invalid` (il Guardian e il tool l'hanno già
escluso: difesa in profondità). Tabella confrontata con `verifiers_v01` e con gli attributi di
classe da `tests/docs/test_adr_verification.py`:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `core.echo` | `EchoVerifier` | `core-echo-verifier` | `echo.message_matches` | comuni, `echo.message_mismatch` |
| `workspace.write_note` | `WriteNoteVerifier` | `workspace-notes-verifier` | `note.exists`, `note.content_matches` | comuni, `note.missing`, `note.content_mismatch`, `note.unreadable` |

`EchoVerifier`: `output["message"]` è la stringa `arguments["message"]`; altrimenti
`echo.message_mismatch`, non ritentabile (un echo che non fa eco è un difetto del tool), con le
due lunghezze e mai i due testi. È tutto il mondo osservabile di `core.echo`: limite dichiarato.

`WriteNoteVerifier(root)`: stessa radice del tool (`resolve_workspace`: espansa, assoluta,
risolta), **mai creata** — una radice assente è una nota assente. `note.exists`, nell'ordine:
`path` con la forma di `is_relative_note_path`; `(root / path).resolve()` sotto la radice;
nessun componente link (`lstat` su ciascuno); esistenza; **file regolare**; altrimenti
`note.missing` con il motivo — un link che punta fuori è "resolves outside the workspace", uno
che punta dentro "goes through a symbolic link", un componente che è un file "cannot be reached:
NotADirectoryError". L'ordine differisce da quello del tool (ADR 0013 §12: link prima della
risoluzione) perché con l'ordine del tool la rete di sicurezza "risolve fuori" era
irraggiungibile in lettura (trovato dal gate al 100% in implementazione): stessa protezione,
messaggi diversi. `note.content_matches`: tutto ciò che vale per `note.exists`, poi `os.open`
con `O_RDONLY | O_NOFOLLOW | O_CLOEXEC`, `fstat` che riconferma il file regolare (una directory
è "not a regular file", mai letta), `os.read` a blocchi, `os.close`; SHA-256 dei byte letti
uguale allo SHA-256 di `body.encode("utf-8")`; altrimenti `note.content_mismatch` con
`expected_bytes`/`actual_bytes`; `OSError` → `note.unreadable`. Tutti e tre ritentabili. **Il confronto è con l'intento** (gli
argomenti), non con `output` del tool: un verifier che si fidasse del rapporto del tool non
verificherebbe nulla. **Gli hash restano in memoria** (decisione F): lo SHA-256 di una nota breve
si inverte per dizionario e l'audit non si redige; nel log vanno solo le dimensioni.
`VerifierRegistry` congelato, `VerifierNotFound(NotFoundError)`, `verifiers_v01(*, root)`
specchio di `tools_v01`: ogni tool ha il suo verifier, `model.complete` non ha né l'uno né
l'altro. `FakeVerifier` (tabella condizione → fallimento) e `FakeVerifierRegistry` in `ela.testing`.

### 3. Un'azione che non può essere verificata non viene eseguita

È §63 reso regola (decisione A). Tre precondizioni nuove dell'executor, nell'ordine di ADR 0013
§2, tutte `ExecutorError`/`NotFoundError` senza scritture: dopo "esattamente una capability", lo
step dichiara **almeno una condizione di successo**; dopo `ToolNotFound`, **un verifier la
implementa** (`VerifierNotFound`, prima del Guardian: nessun grant speso per un'azione che non
si potrà verificare); poi **ogni condizione è nel vocabolario del verifier** (l'errore elenca le
ignote; decisione B, con il rifiuto nel verifier come difesa in profondità). Uno step senza
condizioni o con una condizione fuori vocabolario è un difetto del piano, come uno step con zero
o due capability: vincolo del Planner per M6.2. `Executor.__init__` prende `verifiers`
keyword-only, obbligatorio.

### 4. Il verifier dopo il tool, prima di chiudere lo step

Dopo `TOOL_EXECUTED` (ADR 0013 §7, invariato: il fatto che il tool è girato si scrive prima di
giudicarlo). Tabella confrontata con `OPERATIONS`/`STEP_OPERATIONS` e con le costanti
dell'executor da `tests/docs/test_adr_verification.py`:

| Risultato del tool | Verifica | Operazioni | Codice | Task |
|---|---|---|---|---|
| non SUCCEEDED | non eseguita | `fail_step` | errore del risultato (ADR 0013 §5) | EXECUTING |
| SUCCEEDED | passata | `complete_step` | — | EXECUTING |
| SUCCEEDED | fallita | `fail_step`, `fail` | `verification.failed` | **FAILED** |
| SUCCEEDED | il verifier solleva | `fail_step`, `fail` | `verification.exception` | **FAILED** |

`verify(step.success_conditions, arguments, result)` è chiamato solo con un risultato SUCCEEDED.
Un'eccezione del verifier — un verifier che non sa rispondere non ha verificato: dubbio — diventa
un fallimento `verification.exception` con il tipo dell'eccezione (mai il messaggio, §57) e segue
la riga sotto. La riga "SUCCEEDED → `complete_step`" di ADR 0013 §5 resta vera e **passa per la
verifica**; ADR 0013 prende nello stato il rimando.

**Perché l'asimmetria, e perché resta** (decisione C). Un tool che riporta il proprio fallimento
è un fallimento normale dello step: il task può avere altri step, e chi decide se il task è
finito è l'orchestrator di M6.2 (ADR 0009 §7, ADR 0013 §5). Una verifica fallita è una
**contraddizione tra ciò che il tool dichiara e la realtà**: è un dubbio ai sensi di §33, e nel
dubbio ELA si ferma tutta, non solo lo step — `fail_step(error)` e poi `engine.fail(task_id,
error)` con lo **stesso** `ErrorMetadata`. Le due cose sono diverse e devono restare diverse: la
prima decisione di "chi esegue decide" (ADR 0009 §7).

### 5. `EXECUTION_VERIFIED`, membro nuovo di `AuditEventType`

Additivo, enum come stringa, nessuna migrazione (ADR 0003 §7). Scritto **sempre** quando il
verifier è stato consultato, passata o fallita (decisione H): §32 registra i fatti, e la tabella
delle finestre di crash (§6) ne ha bisogno per distinguere "eseguito e verificato" da "eseguito e
basta". `created_at = clock.now()` dopo la verifica, attore ELA, `summary = "verify:
passed|failed <capability> by <verifier>"`, task, step, capability, `decision_id`,
`authorization_id` come in `TOOL_EXECUTED` (il grant su cui la decisione si regge), `tool_name`
del tool verificato, `error` = l'`ErrorMetadata` di §7 o nullo, payload `{"passed", "result_id",
"verifier", "conditions", "failed": [<condizioni>], "device": "local"}`. **Mai** argomenti,
output né contenuto confrontato (§57).

### 6. Ordine delle scritture e finestre di crash

Estensione della tabella di ADR 0013 §8, stesso formato; ciò che era vero resta vero:

| # | Il processo muore dopo… | …e prima di | Stato che resta | Retry |
|---|---|---|---|---|
| 8a | `TOOL_EXECUTED` | `EXECUTION_VERIFIED` | eseguito, non verificato, step RUNNING | come 8: il tool riesegue. **M5.3**: un `TOOL_EXECUTED` SUCCEEDED senza `EXECUTION_VERIFIED` deve **ri-verificare** (la verifica è idempotente: solo letture), non rieseguire. |
| 8b | `EXECUTION_VERIFIED` (passata) | `complete_step` | verificato, step RUNNING | come 8 → **M5.3** chiude con il risultato verificato. |
| 8c | `EXECUTION_VERIFIED` (fallita) | `fail_step` | verifica fallita scritta, step RUNNING | come 8; **M5.3**: `fail_step` + `fail` senza rieseguire. |
| 9a | `fail_step` (`STEP_FAILED`) | `engine.fail` | step FAILED, task EXECUTING | `ExecutorError` (step non RUNNING); `GraphState.is_blocked` è vero: chi riprende il task (recovery/orchestrator, M5.3/M6.2) deve chiamare `fail`. **Non riparato qui.** |

Le quattro finestre sono registrate in `docs/milestones/M5.3.md` (decisione J).

### 7. L'`ErrorMetadata` della verifica fallita (§64)

Costruito dall'executor dai fallimenti del verifier, uno per step e per task:

| Campo | Valore | §64 |
|---|---|---|
| `code` | `verification.failed` | cosa |
| `message` | `"<k> of <n> success conditions failed for <capability>: <cond> (<code>), …"` | cosa |
| `cause` | i messaggi dei fallimenti, uniti con `"; "` | perché |
| `tool_name` | il nome del tool | quale tool |
| `model` | `None` (nessun modello fino a M7.2) | quale modello |
| `device_id` / `details["device"]` | `None` / `"local"` (come `TOOL_EXECUTED`) | quale dispositivo |
| `attempted_fix` | `None`: nessuna tentata (decisione E; "non tentato" è già onesto) | soluzione provata |
| `successful_fix` | `None` | soluzione che ha funzionato |
| `retryable` | vero solo se ogni fallimento lo è | — |
| `details` | `{"conditions", "failures": [{condition, code, message, retryable, details}], "result_id", "verifier", "device"}` | — |

Lo stesso oggetto va in `STEP_FAILED`, in `TASK_FAILED` e in `EXECUTION_VERIFIED`. Un retry è un
task nuovo (ADR 0004 P1); il giorno in cui il Self-Improvement (§35) proverà una soluzione
scriverà qui cosa ha provato.

### 8. `Execution` porta la verifica

`Execution(task, step_id, graph, decision, authorization, result, approval, verification)` con
`verification: Verification | None` — `None` se il verifier non è stato consultato.
`Verification(conditions, failures, error)`, `passed = error is None`, `NamedTuple` nel modulo
dell'executor come `Execution` (ADR 0013 §1): non è un'entità di §49 e non è persistita;
`EXECUTION_VERIFIED` è la sua traccia, ed è ciò che M5.3 leggerà.

### 9. Regola architetturale 17: `complete_step` ha un solo chiamante

`check_step_completers` in `tests/architecture/rules.py` (decisione G): in ogni modulo di
`src/ela` **tranne il percorso esatto `executive/executor.py`** segnala ogni chiamata
`<x>.complete_step(`; la definizione in `tasks/engine.py` non è una chiamata. È il modo in cui
"uno step è COMPLETED solo dopo la verifica" diventa codice. Casi in `violations.py` (un
orchestrator, un modulo di `tasks`: riportati; l'executor, una definizione: no); vacuità
(`executor.py` contiene `.complete_step(`). Euristica sui nomi come la regola 16.

### 10. Regola architetturale 18: il modulo dei verifier non scrive

`check_verifier_read_only` (decisione I): closed-world sull'AST di `tools/verifiers.py`.
Riportati: `open`/`fdopen` con modalità di scrittura (`w`, `a`, `x`, `+`) o con una modalità
non letterale; `os.open` con un flag di scrittura (`O_WRONLY`, `O_RDWR`, `O_CREAT`, `O_TRUNC`,
`O_APPEND`, `O_EXCL`) o senza flag; ogni chiamata con il nome di una scrittura (`write`,
`writelines`, `unlink`, `remove`, `rename`, `replace`, `rmdir`, `mkdir`, `makedirs`, `write_text`,
`write_bytes`, `touch`, `chmod`, `chown`, `symlink`, `link`, `truncate`, `utime`, `rmtree`, `copy`,
`move`…); ogni chiamata attraverso `shutil`. Casi negativi per ciascuna famiglia; il modulo reale
e una lettura `os.open(p, os.O_RDONLY | os.O_NOFOLLOW)` non sono riportati; vacuità (il modulo
esiste e contiene `os.open(`, `O_RDONLY`, `O_NOFOLLOW`). La stessa proprietà è provata dal
comportamento: ogni test del verifier delle note confronta albero, dimensioni e mtime della
workspace prima e dopo `verify`, anche sui fallimenti.

### 11. Il verifier non passa dal Guardian

La verifica legge ciò che ELA stessa ha appena scritto nella propria workspace, o l'output del
tool: nessuna capability, nessun effetto esterno, nessuna decisione (§27 mette in fila le
*azioni*). Il giorno in cui un verifier interrogherà un sistema esterno ("la mail è arrivata?",
§63) quella lettura sarà una capability con la sua decisione.

## Alternative considerate

- **Condizione implicita "il risultato è SUCCEEDED", step vuoti ammessi** — sarebbe "esecuzione
  inviata = successo", il contrario di §63. Scartata (A).
- **Step senza condizioni → verifica fallita dopo aver agito** — l'azione sarebbe già fatta; non
  agire su ciò che non si potrà verificare. Scartata (A).
- **Condizione ignota → verifica fallita dopo il tool** — idem: rifiutare prima, e anche dopo per
  difesa in profondità. Scartata (B).
- **Uniforme: ogni `fail_step` dell'executor fallisce anche il task** — confonderebbe un errore
  riportato (che l'orchestrator può gestire) con una contraddizione (che ferma tutto); le due
  cose devono restare diverse. Scartata (C).
- **`verify` come membro di `ToolPort`** o **`ToolRegistryPort.verifier(cid)`** — il tool che si
  autocertifica; l'indipendenza va costruita, non promessa. Scartata (D).
- **`attempted_fix` come costante "none"** — rumore nel payload; `None` è già onesto. Scartata (E).
- **Hash SHA-256 nei `details`** — l'hash di una nota breve si inverte per dizionario e l'audit
  non si redige. Solo dimensioni. Scartata (F).
- **Nessuna regola 17** — "la review basta" non è verificabile; la regola costa quanto la 16.
  Scartata (G).
- **`ERROR_RECORDED` solo sul fallimento, nessun evento sul pass** — le finestre di crash non
  distinguerebbero "verificato" da "eseguito"; e "verificato" è un fatto (§32). Scartata (H).
- **La verifica nel payload di `TOOL_EXECUTED`** — andrebbe scritto dopo la verifica, perdendo
  "il tool è girato" se il verifier cade. Scartata (H).
- **Il verifier attraverso il Guardian** — non è un'azione; una decisione per una lettura della
  propria workspace sarebbe un `PERMISSION_DECIDED` senza contenuto. Scartata (I), con il vincolo
  della sola lettura.
- **Codici delle precondizioni di `verify` duplicati nel fake e nella base** — due fonti di
  verità; stanno in `ela.ports` con `check_verifiable`, come `check_limit`. Scartata.
- **Il verifier che confronta con `output` del tool** — verificherebbe la coerenza del tool con
  sé stesso. Il confronto è con gli argomenti. Scartata.
- **Il vocabolario nel catalogo (`CapabilitySpec`)** — un campo del dominio per un dato che il
  Planner può leggere dal registro; se M6.2 lo vorrà, con un ADR. Rinviata.

## Conseguenze

- `VerifierPort`, `VerifierRegistryPort`, `check_verifiable` e i quattro codici `VERIFICATION_*`
  sono in `ela.ports` (quindici port); `AuditEventType.EXECUTION_VERIFIED` nel dominio;
  `Verifier`, `COMMON_FAILURE_CODES`, `VERIFICATION_ARGUMENTS_INVALID`, `EchoVerifier`,
  `WriteNoteVerifier`, le condizioni e i codici, `VerifierRegistry`, `verifiers_v01`,
  `VerifierNotFound`, `resolve_workspace` l'API di `ela.tools`; `Verification`,
  `Execution.verification`, `VERIFICATION_FAILED`, `VERIFICATION_EXCEPTION` quella di
  `ela.executive`; `FakeVerifier`, `FakeVerifierRegistry`, `VerifierCall`, `FAKE_CONDITION` in
  `ela.testing`.
- **Per M6.2 (Planner e orchestrator).** Uno step eseguibile dichiara almeno una condizione di
  successo, tutte nel vocabolario (`VerifierRegistryPort.get(cid).conditions`) del verifier della
  sua capability; un piano che non lo rispetta è rifiutato dall'executor prima di agire e va
  reso verificabile alla validazione del piano. L'orchestrator non completa mai uno step (regola
  17) e trova un task FAILED, non EXECUTING, dopo una verifica fallita.
- **Per M5.3.** Le finestre 8a–8c e 9a di §6; `EXECUTION_VERIFIED` è ciò che distingue
  "ri-verifica" da "riesegui".
- **Per M7.2.** `model.complete` avrà tool e verifier insieme, o nessuno dei due.
- **Limiti dichiarati.** Il mondo osservabile di `core.echo` è il suo output. Il TOCTOU inverso
  (file corretto alla verifica, alterato dopo) è fuori portata di una verifica puntuale. Un
  crash fra `fail_step` e `fail` (9a) lascia un task EXECUTING bloccato, visibile in
  `is_blocked`.
- L'audit di una chiamata riuscita: `PERMISSION_DECIDED`, `TOOL_EXECUTED`, `EXECUTION_VERIFIED`,
  `STEP_COMPLETED`; di una verifica fallita: `…`, `EXECUTION_VERIFIED`, `STEP_FAILED`,
  `TASK_FAILED`. Gli argomenti, l'`output`, il contenuto confrontato, gli hash e il messaggio di
  un'eccezione non vi entrano mai.
- Regole 17 e 18 in `tests/architecture/rules.py` con casi positivi e negativi; le tabelle di §1,
  §2 e §4 sono verificate dal codice (`tests/docs/test_adr_ports.py`,
  `tests/docs/test_adr_verification.py`) con casi negativi.
