# 0058. Il Planner: una chiamata di `model.complete` in un task figlio, un piano validato prima della porta, e chi l'ha scritto

- **Stato:** Accettata il **2026-10-08**, quando la prova a mano della sezione 24 di `docs/GETTING_STARTED.md` è passata
  sul Mac a `f2b67c0` (`~/Downloads/prova-m14.2-20261008-091143.txt`, 29 PASSATI al primo giro; §12). Aperta il 2026-10-07 con
  l'implementazione di M14.2 e le decisioni della review della SPEC dello stesso giorno (A–M della sessione, 1–17 della
  review, in `docs/milestones/M14.2.md`). Un primo giro, a `28c4c88`, non era passato per due difetti dello script, non
  di ELA (`docs/milestones/M14.2.md`, «Il primo giro»).
- **Data:** 2026-10-07
- **Riferimenti spec:** §12, §13, §14, §25, §27, §33, §44, §57, §63
- **Milestone:** M14.2

## Contesto

Fino a M14.2 un piano lo scrive una persona: `POST /tasks/{task_id}/plan` prende un file, e `PLAN_IS_TEMPORARY` (ADR
0023 §6) dice a chi usa l'API che quella forma esiste perché il Planner di §13 non c'è ancora. §12 vuole che ELA
trasformi un obiettivo in un piano; §13 che il piano resti indipendente dal dispositivo; §27 mette il Guardian fra il
Planner e ogni tool; §57 decide che cosa esce dalla macchina; §63 vuole che ELA verifichi il proprio lavoro.

Tre ADR avevano lasciato un vincolo al giorno del Planner. ADR 0011, Conseguenze: uno step prodotto dal Planner dichiara
tutte le capability che userà. ADR 0014, Conseguenze, «Per M6.2»: uno step senza condizioni di successo, o con una fuori
vocabolario, è rifiutato dall'executor prima di agire, e **va reso verificabile alla validazione del piano**. ADR 0022
§6: un `task_type` sconosciuto è un bug del Planner, che «produrrà tipi da un enum».

Il censimento della SPEC ha trovato che la seconda metà del vincolo di ADR 0014 non l'aveva fatta nessuno, nemmeno per
i piani a mano: un piano con due capability in uno step, o con una condizione fuori vocabolario, entrava — `200`,
`QUEUED` — e al primo `run` l'executor sollevava `ExecutorError` dopo `start` e `start_step`. Il task restava
`EXECUTING` con lo step `RUNNING`, e ogni `run` successivo rispondeva `409` fino al `recover` del riavvio dopo.

M14.1 ha messo il tetto di spesa sulla chiave del modello (ADR 0057): ogni chiamata che spende passa dal cancello prima
di partire. **Il Planner chiama il modello**, e la sua chiamata non può essere una seconda porta.

## Decisione

### 1. La chiamata è uno step: il task di pianificazione, figlio del task

**Il Planner non chiama nessun provider** (decisione A). Per pianificare un task ne crea il **task di pianificazione**:
un figlio, con `parent_id`, il cui piano ha **uno step `model.complete`** scritto dal codice del Planner. Il runner lo
cammina come ogni altro: il Guardian decide sulla spec del catalogo (`MEDIUM`, `requires_authorization`), la domanda
nasce con il caso peggiore e ciò che resta del mese (ADR 0057 §8), il sì, il cancello prenota nella `STARTED` (ADR 0057
§5), `ModelCompleteTool` chiama il router, il verifier verifica, l'audit registra. **Nessuna transizione nuova in ADR
0004, nessuna sorgente nuova di `deny_by_cap` in ADR 0057 §7, nessuna eccezione nel catalogo, nessuna esenzione nelle
regole 25 e 61.** Senza tetto, o con un tetto che non ci sta, il figlio è `DENIED` con `deny_by_cap` **prima della
domanda** e nessuna chiamata parte.

Il figlio lo crea **`create_child`**, un'operazione del Task Engine che **non muove uno stato** — come `create`, non
sta nella tabella delle operazioni (ADR 0008 §3) —: il padre deve esistere; l'id è derivato, `uuid5` del namespace dei
task su `planning/<padre>`, così un secondo gesto trova lo stesso figlio e non ne crea un altro; il goal è «plan task
`<padre>`: `<goal>`»; l'intento e la scadenza sono quelli del padre; la privacy è `LOCAL_ONLY`, il default. Il
`TASK_CREATED` del figlio porta `parent_id` e la chiave.

**Il padre si chiude da dove il figlio è finito**, con `settle`, che è idempotente e chiamano le rotte — il `run` del
figlio e `POST /tasks/{task_id}/planning`, il no, il fermo — e l'avvio (decisione 13, sotto):

| Il figlio finisce | Il padre | Con |
|---|---|---|
| `COMPLETED`, e il modello ha scritto un piano valido | `QUEUED` | `engine.plan`, poi `queue` «planned by ELA's Planner» |
| `COMPLETED`, e il modello ha scritto «nessun piano» | `FAILED` | `planner.no_plan` |
| `COMPLETED`, e il piano è rifiutato (§3, §4) | `FAILED` | il codice del vincolo caduto |
| `COMPLETED` senza una risposta da leggere | `FAILED` | `planner.call_failed` |
| `DENIED` — il no dell'utente, o il tetto | `DENIED` | `deny_by_planning` |
| `CANCELLED` | `CANCELLED` | `cancel`, con la ragione del figlio |
| `FAILED` | `FAILED` | `planner.call_failed` |
| `EXPIRED` — la domanda scaduta | `FAILED` | `planner.unanswered` |

Un'operazione nuova chiude il padre negato:

| Operazione | Da | A | Audit | Chiave |
|---|---|---|---|---|
| `deny_by_planning` | PLANNING | DENIED | `TASK_DENIED` | `planning_task_id` |

La transizione `PLANNING → DENIED` è già legale in ADR 0004; l'operazione controlla che il task nominato sia **il
figlio di pianificazione di questo padre** e che sia `DENIED`. **P5 di ADR 0004 si rilegge apertamente** (decisione 1):
«DENIED solo dove qualcuno decide: PLANNING (il Guardian valuta il piano)» vale anche quando chi ha deciso è l'utente,
con un no alla chiamata che avrebbe scritto il piano, o il cancello del tetto — su un altro task, il figlio, che il
padre nomina nella chiave. **Un no dell'utente è un diniego, non un fallimento** (M13.1c): `FAILED` con un
`planner.denied`, che P4 copriva alla lettera, si sarebbe letto come un errore di ELA.

**Il fermo scende e sale.** Fermare il padre ferma il figlio vivo — un sì dato dopo pagherebbe un piano che nessuno può
attaccare —; fermare il figlio chiude il padre. **La rotta a mano rifiuta un padre che si sta pianificando** (`409`):
due porte aperte sullo stesso task sono due piani.

**Un gesto, una chiamata, nessun ciclo** (decisione G): un piano rifiutato, un «nessun piano», un no non fanno una
seconda chiamata; un padre finito non si ripianifica. Una seconda richiesta è un task nuovo.

**All'avvio** (decisione 13 della review), dopo `recover()` e `close_every_open_step()`, il lifespan di `app.py` chiama
`settle_all`: ogni padre `PLANNING` senza piano il cui figlio è finito, trovato con una lettura del repository. Lo
raggiungono due cose che nessun gesto raggiunge: una domanda che scade, che solo `recover()` scrive; e un crash fra la
fine del figlio e il `settle`.

### 2. Che cosa esce: l'obiettivo, le istruzioni, il catalogo

Gli argomenti della chiamata sono esattamente cinque (decisione F, criterio 8):

- `input`: **il goal del padre**, e nient'altro;
- `instructions`: le istruzioni del Planner, il catalogo e lo schema della risposta;
- `purpose`: che cosa la chiamata fa, per la domanda;
- `task_type`: `planning`, la rotta di §25 per la pianificazione complessa — Opus 5.5;
- `parameters`: `{"max_output_tokens": 16384}`.

**Il catalogo è derivato dai registri**: le capability che hanno un tool **e** un verifier, ciascuna con la descrizione,
il rischio, lo schema dei suoi argomenti e le condizioni del suo verifier; i `task_type` dalla tabella delle rotte.
Una capability aggiunta ai registri compare nel prompt e nello schema senza che nessuno la scriva qui. **Non escono**:
lo `scope` — i siti, le cartelle e i programmi di chi usa ELA —, i dispositivi, il contesto.

**`max_output_tokens` è 16384**, una costante del Planner, `PLANNING_OUTPUT_TOKENS` (decisione 14): Opus 5.5 pensa
sempre, e il pensiero sta dentro `max_tokens`; con i 4096 del default un piano troncato è una chiamata pagata e un passo
della prova da rifare. **Il caso peggiore di una pianificazione**, con il listino di ADR 0057 §3, calcolato da `WorstCase`
dell'adapter sugli argomenti che il Planner scrive (`tests/executive/test_planner_worst_case.py`), non a mano:

| Modello | Caso peggiore |
|---|---|
| Opus 5.5 | 4,262144 $ |

cioè `(1 000 000 − 16 384) × 4 $ + 16 384 × 20 $` per milione di token.

**Il contesto resta fuori** (decisione 7, §44): **il secondo consumatore di ADR 0032 §1 non è consegnato**. La regola
39 vieta che uno snapshot entri in un `AuditEvent` o in una `ProviderRequest` per nome di tipo, e un Planner che mettesse
il contesto nell'`input` come testo non la farebbe scattare. Lo chiude **il contratto 15** di import-linter:
`ela.executive` non importa `ela.context`. A `cc26a85` era già vero, quindi non costa niente oggi e chiude la strada di
domani: chi vorrà il contesto nel prompt troverà il contratto e le quattro domande di §57.

### 3. Che cosa il modello scrive: uno schema, stretto

La risposta è **un oggetto JSON e nient'altro**, spazi a parte, con **una sola** delle due chiavi: `plan`, con i suoi
`steps`, o `no_plan`, con una `reason`. Uno step ha sette campi: `name`, `goal`, `capability`, `arguments`, `after`,
`expected_result`, `success_conditions`. **Non ha** `risk`, `requires_authorization`, un posto dove scegliere una
macchina, né un goal del piano: il rischio e l'autorizzazione sono del catalogo (§4), la macchina dell'orchestrator
(§7), il goal del piano è quello del task — così **nessuna frase del modello entra nel payload di `PLAN_CREATED`**.

`additionalProperties` è `false` a ogni livello, salvo dentro `arguments`, che lo schema della capability decide. «Una
sola delle due» si controlla nel codice, dopo lo schema, perché un `maxProperties` coprirebbe una chiave sconosciuta con
un messaggio sbagliato. Una chiave scritta due volte, una stringa che non è testo (un surrogato solo, `is_text` di M13.3),
una risposta fermata a `max_tokens` sono rifiutate. **Una ragione nomina la chiave, tagliata a quaranta caratteri, e
mai un valore** (§57, come il Guardian per i percorsi, ADR 0011 §8).

`name` è un nome locale (`^[a-z][a-z0-9_-]{0,31}$`) che `after` cita: **gli id li conia il Planner**, derivati
dall'id del risultato, così un secondo `settle` della stessa risposta scrive lo stesso piano — un no-op dell'engine — e
mai un secondo. Le istruzioni dicono quando scrivere `no_plan` — un effetto nel mondo che nessuna capability produce —
e di non scrivere mai un piano che parla dell'obiettivo invece di farlo (decisione 16).

I codici con cui un padre fallisce per la sua pianificazione, e nessun altro:

| Codice | Che cosa |
|---|---|
| `planner.truncated` | la risposta si è fermata a `max_tokens`: una risposta che non è finita non si legge |
| `planner.not_json` | non è un oggetto JSON e nient'altro: una frase, un blocco di codice, un array |
| `planner.malformed` | non ha la forma di un piano: una chiave sconosciuta, una che manca, un tipo sbagliato |
| `planner.unverifiable` | uno step che l'executor rifiuterebbe: la capability, il tool, il verifier, le condizioni |
| `planner.invalid_arguments` | argomenti fuori dallo schema della capability, o un `task_type` fuori tabella |
| `planner.not_a_graph` | due step con lo stesso nome, un `after` fuori dal piano, un cerchio |
| `planner.no_plan` | il modello ha risposto che il catalogo non lo sa fare: una risposta, non un errore |
| `planner.call_failed` | il figlio è fallito: la chiamata, la sua verifica, la sua rotta |
| `planner.unanswered` | la domanda del figlio è scaduta senza risposta |

**La ragione del «nessun piano» resta fuori dall'audit** (ADR 0021 §7): sta nel risultato del figlio, nell'archivio
privato, e `GET /tasks/{task_id}` e `ela task show` la rileggono da lì.

### 4. La validazione prima della porta: le funzioni di chi decide

Un piano scritto dal modello passa, step per step, **le funzioni che decideranno quando gira** (decisione B):

1. **le precondizioni dell'executor**, `readiness` — esattamente una capability, del catalogo, con un tool e un
   verifier, almeno una condizione, tutte nel vocabolario del verifier —: **una funzione sola**, estratta da
   `Executor._prepared`, che l'executor, il Planner e la rotta a mano chiamano; l'executor solleva ciò che sollevava,
   con le stesse frasi;
2. **gli argomenti**, con `validate_arguments` del Guardian sulla spec **registrata**;
3. **il `task_type`** di uno step `model.complete`, con il router stesso: un tipo fuori tabella è
   `planner.invalid_arguments` (ADR 0022 §6);
4. **il grafo**: i nomi, gli `after`, poi `TaskGraph.from_plan`.

`risk` e `requires_authorization` di ogni step sono quelli della spec registrata: **un piano non allenta niente** — la
proprietà di ADR 0026 §7, provata anche sui piani del Planner (`tests/permissions/test_planner_plan_properties.py`).
Il primo vincolo caduto dà il codice e la ragione, e tutti restano nel `details` del fallimento; uno step si nomina per
posizione e capability — «step 2 of 3 (fs.read): …» —, mai con un valore.

**Anche la rotta a mano** (decisione 8): `POST /tasks/{task_id}/plan` chiede `readiness` per ogni step **prima** di
muovere il task, e un piano che l'executor rifiuterebbe è un `422` con lo step per posizione. Il difetto del Contesto è
chiuso per le due porte. Gli argomenti di un piano a mano restano del Guardian, al `run`: un piano scritto a mano può
voler mostrare un diniego.

**`UNKNOWN_CAPABILITY` del Device Orchestrator non si raggiunge più dall'API**, e resta vera: per i piani salvati
**prima** di questo controllo — task `QUEUED` con un piano a mano già nel database, che nessuna migrazione rilegge —
il `run` aspetta un nodo che non può esistere, `waiting_device` con `UNKNOWN_CAPABILITY`, come prima di M14.2. Lo
prova un test che scrive il piano come la rotta lo scriveva allora, con le operazioni dell'engine e senza la rotta
(`tests/api/test_hand_plan_ready.py`); il rifiuto dell'orchestrator da solo è in `tests/devices/test_orchestrator.py`.

### 5. La porta: `engine.plan` e `queue`, nessun `run`

Valido, il piano entra con `engine.plan` — che rifà `TaskGraph.from_plan` — e `engine.queue`: il padre `QUEUED`, come
dopo `/plan`. **Il Planner non avvia** (decisione H): il `run` di un piano scritto dal modello è dell'utente, dopo averlo
letto. **La regola 62, `plans-enter-by-two-doors`**: fuori da `api/tasks.py` e dal modulo del Planner nessuno chiama
`.plan(` su un ricevente che è l'engine — un'euristica sui nomi come le regole 16 e 17; `repository.plan(…)`, la
lettura, ha un altro ricevente.

### 6. Il piano dice chi l'ha scritto

Nel dominio, `PlanAuthor`, con **tre autori** (decisione 5): **`HAND`**, la rotta a mano; **`PLANNER`**, il codice del
Planner — il piano di uno step del figlio —; **`MODEL`**, il modello attraverso il Planner, con **l'id del risultato** da
cui il piano viene e **il modello** che l'ha scritto. `result_id` e `model` sono obbligatori per `MODEL` e vietati agli
altri due, e lo fa rispettare il validatore del dominio. `TaskPlan.author` non ha default; **il payload non può
scriverlo**: lo mette chi apre la porta. `PLAN_CREATED` lo porta nel payload; `GET /tasks/{task_id}` lo dice in
`plan_author`; `ela task show` lo stampa.

Colonne aggiunte:

| Tabella | Colonne |
|---|---|
| `task_plans` | `author` |

La migrazione `0014` aggiunge la colonna, JSON e non nulla, con `{"by": "HAND"}` sulle righe che ci sono: prima di
M14.2 ogni piano l'ha scritto una persona.

### 7. Il piano resta indipendente dal dispositivo

Il criterio della registrazione era «nessuno step nomina una macchina». Un testo libero — il goal di uno step, il corpo di
una nota — può contenere il nome di qualunque cosa, e una regola su un testo sarebbe un filtro di parole. **Si riscrive
apertamente** (proposta 8): un piano del Planner **non ha un posto in cui scegliere una macchina**. Quattro fatti, ciascuno
con il suo test: lo schema della risposta non ha una chiave che sceglie dove gira uno step; il Planner non riceve il
registro dei dispositivi né l'orchestrator; i tratti preferiti sono `()`, perché il vocabolario dei tratti è vuoto — il
giorno in cui un nodo ne dichiarerà uno, lo schema avrà un `enum` da quel vocabolario —; nessuna capability del catalogo
ha un argomento che sceglie la macchina. **La regola 63, `the-planner-names-no-device`**, sorveglia i nomi nel modulo del
Planner: un contratto di import-linter non basta, perché il Planner importa il runner, che importa l'orchestrator.

### 8. La rotta e il comando

| Metodo | Percorso | Che cosa |
|---|---|---|
| `POST` | `/tasks/{task_id}/planning` | chiede il piano a ELA, fin dove arriva: la domanda del figlio, o il piano attaccato e il task in coda |

| Comando | Rotta | Uscite |
|---|---|---|
| `ela task plan` | `POST /tasks/{task_id}/planning` | `0` `1` `2` `3` |

**Rientrante come `run`**: la prima chiamata crea il figlio e lo porta alla sua domanda; dopo il sì la seconda — o un
`run` del figlio — fa la chiamata, e il piano è validato e attaccato. Sotto il lock di `run` del padre e del figlio:
due gesti insieme sullo stesso task sono un `409`. **`ela task plan` senza `--file`** chiama questa rotta e stampa
dove la pianificazione sta: la domanda con il caso peggiore e ciò che resta, e il comando dopo; il piano, con chi l'ha
scritto e gli argomenti e le condizioni di ogni step. **Con `--file`** resta il piano a mano, su `/plan`. **`ela task
show`** stampa l'autore e, sotto la tabella, gli argomenti e le condizioni di ogni step: erano solo in `--json`, e un piano
scritto dal modello lo si avvia dopo averlo visto (decisione I).

**`PLAN_IS_TEMPORARY` si riscrive** (decisione J): la rotta `/plan` resta, perché i test e le prove guidano ELA con piani
a mano, e la frase dice il vero di oggi — la forma è quella di un piano scritto a mano, non versionata, e il Planner
scrive i suoi da `POST /tasks/{task_id}/planning`. Il suo test vuole il Planner **presente**, e fallisce apposta il
giorno in cui sparisse.

### 9. `browser.read` resta `LOW`, sui tre fatti riscritti

Il livello poggia su tre fatti (ADR 0052 §4, decisione 4 della review di M13.4), e il secondo — «il piano è
dell'utente, attaccato a mano» — da oggi non è più sempre vero. **Si riscrivono** (decisione I): i siti li dichiara
l'utente (`ELA_BROWSER_SITES`, senza default); **un piano scritto dal modello lo avvia l'utente dopo averlo visto**, con
gli argomenti; nel browser non c'è nessuna credenziale (ADR 0052 §3). **In M14.2 nessun modello legge il testo di una
pagina**: la chiamata del Planner viene prima di ogni step, il suo `input` è l'obiettivo, e nessun dato passa da uno
step all'altro (ADR 0018 §6). **Il giorno in cui cambia è M14.3**, dove il modello guarda la pagina e il testo di una
pagina diventa un ingresso non fidato: `docs/milestones/M14.3.md` porta l'annotazione datata.

**Il vincolo dichiarato**: un GET scritto dal modello può portare parole dell'obiettivo a un sito dichiarato — nel
percorso, nella query — e può agire se il sito agisce su un GET. La guida lo dice dove i siti si dichiarano, in §1, e lo
ripete all'apertura di §20.

### 10. Righe riviste

Gli ADR non si riscrivono: queste righe si leggono con questo accanto, e lo Stato di ciascuno rimanda qui.

- **ADR 0004, P5**: `DENIED` da `PLANNING` anche per il diniego della chiamata che avrebbe scritto il piano, sul figlio
  (§1).
- **ADR 0008 §3**: la tabella delle operazioni ha `deny_by_planning`; `create_child` non muove stati e non ci sta, come
  `create` (§1).
- **ADR 0011, Conseguenze**: il vincolo per il Planner è chiuso — uno step del Planner dichiara esattamente la capability
  che userà, e `readiness` lo rifiuta altrimenti (§4).
- **ADR 0014, Conseguenze, «Per M6.2»**: «va reso verificabile alla validazione del piano» è fatto, per le due porte (§4).
- **ADR 0022 §6**: i `task_type` del Planner vengono dalla tabella delle rotte, come un `enum` dello schema; un tipo fuori
  tabella è rifiutato prima della porta (§3, §4).
- **ADR 0023 §6**: `PLAN_IS_TEMPORARY` dice il vero di oggi; la tabella delle rotte guadagna la rotta di §8.
- **ADR 0024**: «il piano resta un file scritto a mano finché non esiste il Planner» non è più vero; `ela task plan`
  senza `--file` chiede il piano a ELA (§8).
- **ADR 0032 §1 e §7**: il secondo consumatore dichiarato non è consegnato, e la porta fra il contesto e il Planner la
  chiude anche il contratto 15 (§2).
- **ADR 0052 §4**: i tre fatti su cui `browser.read` è `LOW` sono quelli di §9.

### 11. Il difetto trovato per strada

Scrivendo i test della rotta, il fermo di un task **senza piano** — `CREATED`, o `PLANNING` mentre ELA lo pianifica —
rispondeva `404 task plan not found` per un fermo che l'engine aveva già scritto: `close_open_step` chiedeva il grafo di un
task che non ne ha. Da M6.3c (ADR 0054 §5). Prima un test rosso, poi il fix: senza piano non c'è uno step da chiudere.
La riparazione è **M6.3d** (`docs/milestones/M6.3d.md`): il difetto vive nella Fase 6 (ADR 0035 §1), e questa
sezione ne resta la decisione.

### 12. La prova a mano

La sezione 24 di `docs/GETTING_STARTED.md`, con lo script `scripts/prova_m14_2.py`, **sul Mac**: M14.2 non cambia niente
sul nodo. Quattro chiamate vere a Opus 5.5, tutte con un sì di Tommaso: una nota da scrivere — pianificata, letta,
avviata —, una pagina da leggere e una domanda al modello — pianificate e lette, non avviate —, e un obiettivo fuori
catalogo, che deve finire `planner.no_plan`. Lo script confronta **proprietà, non piani**, perché il modello non è
deterministico; il giudizio «fa ciò che l'obiettivo chiede?» resta all'occhio. Per ogni chiamata scrive se la risposta era
un oggetto JSON e quanti token d'uscita ha usato (decisione 4): la misura con cui la domanda delle uscite strutturate si
riapre. **Il cancello sulla chiamata del Planner lo prova la suite**; la prova lo vede nella domanda. **Passata il
2026-10-08** a `f2b67c0`, sul Mac, 29 PASSATI al primo giro: quattro risposte su quattro un oggetto JSON, il costo vero
di ogni pianificazione fra 0,0195 e 0,0216 $ contro un caso peggiore di 4,262144 $, ogni prenotazione chiusa alla fine,
la nota pianificata, scritta e letta, e l'obiettivo fuori catalogo `FAILED` con `planner.no_plan` e la ragione del
modello. Le misure sono in `docs/milestones/M14.2.md`, «Passata il 2026-10-08».

## Alternative considerate

- **La chiamata sul padre stesso, in `PLANNING`.** Rifiutata (domanda 1): un'`Approval` senza step, `request_approval`
  senza piano, una transizione nuova `WAITING_APPROVAL → PLANNING`, `deny_by_cap` da `PLANNING`, e un secondo cammino
  nell'executor per una chiamata che non è uno step — la seconda porta che la decisione A esclude.
- **Uno step zero nel piano del padre**, poi il piano vero. Rifiutato: un task ha un piano solo, ed estenderlo a run in
  corso è un'operazione nuova su un grafo che il runner sta camminando.
- **Il padre negato `FAILED`, con `planner.denied`.** Rifiutato (decisione 1): un no è un diniego.
- **Le uscite strutturate del fornitore** per lo schema della risposta. Rimandate (domanda 4): la prova ne prende la
  misura — quante risposte erano un oggetto JSON — e la domanda si riapre con i numeri.
- **Il contesto nel prompt** (§44). Rimandato con la porta chiusa (§2).
- **L'avvio automatico** del piano scritto dal modello. Rifiutato (decisione H): §57 e l'occhio dell'utente.
- **Ripianificare un piano rifiutato** con una seconda chiamata. Rifiutato (decisione G): una chiamata per gesto, e un
  ciclo che spende senza che nessuno lo veda è ciò che il tetto esiste per impedire.

## Conseguenze

Con questo ADR le regole di architettura sono **sessantatré** (la 62 e la 63), i contratti di import-linter
**quindici** (il 15), i port restano **trenta**, le rotte dell'API sono **cinquantuno**
(`POST /tasks/{task_id}/planning`) e i comandi della CLI restano **ventotto** (`ela task plan` guadagna una strada, non
un nome).

Ciò che questo ADR dichiara e non risolve:

- **Il caso peggiore di ogni pianificazione è 4,262144 $**: con un tetto di 50 $ stanno in volo al più undici
  pianificazioni, e alla fine del mese, sotto i 4,26 $ di resto, non si pianifica più (ADR 0057, vincoli).
- **Il modello non è deterministico**: lo stesso obiettivo dà piani diversi, e la prova confronta proprietà.
- **Un testo attorno al JSON** — una frase, un blocco di codice — rifiuta il piano, pagato. Le istruzioni lo chiedono;
  la prova misura quanti piani entrano.
- **Un piano senza scope** può nominare un posto fuori dagli scope, e il Guardian lo nega al run: il costo è un run
  negato, mai un effetto.
- **Un GET scritto dal modello** porta parole dell'obiettivo a un sito dichiarato, e agisce se il sito agisce su un GET
  (§9).
- **Il prompt contiene il catalogo intero**: qualche migliaio di token d'ingresso per chiamata; il costo vero si legge
  nella prova.
- **Due task per ogni richiesta** sulle superfici: il padre e il figlio. Console e telefono rispondono alla domanda del
  figlio come a ogni altra, e il loro sì fa la chiamata e attacca il piano; **chiedere un piano dalle pagine resta della
  CLI e dell'API**.
- **Il testo dell'intento non si conserva** (domanda 9): il goal del padre è ciò che esce.
- **Il task nuovo con `parent_id` che punta al vecchio** di ADR 0004 P1 — ripianificare un task fallito — resta non
  costruito: `parent_id` oggi lo porta soltanto il figlio di pianificazione.
