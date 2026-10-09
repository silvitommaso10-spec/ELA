# 0060. Il browser guidato dal modello: una sessione di Claude Code lanciata da ELA, ogni gesto un task figlio deciso dal Guardian, e ogni chiamata della sessione pesata sulla prenotazione prima di lasciare il Mac

- **Stato:** Accettata il **2026-10-09**, quando la prova a mano della sezione 26 di `docs/GETTING_STARTED.md` è passata
  sul Mac a `f58a6cb` (`~/Downloads/prova-m14.3-20261009-104118.txt`, 45 PASSATI al primo giro; §17). Aperta lo stesso
  giorno con l'implementazione di M14.3, dopo la SPEC decisa (le decisioni 1–17 della sessione, 18–20 della review dello
  script e 21–30 della review della SPEC, in `docs/milestones/M14.3.md`) e la misura di Tommaso del 2026-10-08
  (`~/Downloads/misura-m14.3-20261008-222255.txt`, a `dac715b`); riletta dalla review del riepilogo (decisioni 31–38): §6 ha
  la cartella e il processo che un crash lascia, §17 le sessioni a 1,10 $. Tre giri prima non erano passati: per lo script,
  per lo strumento `act` che non diceva la grammatica del selettore, e per un criterio del passo 4 che la prova non poteva
  costruire (`docs/milestones/M14.3.md`, «Il primo giro», «Il secondo giro», «Il terzo giro»).
- **Data:** 2026-10-09
- **Riferimenti spec:** §13, §19, §24, §25, §27, §30, §32, §33, §39, §57, §59, §62, §63
- **Milestone:** M14.3

## Contesto

Da una frase — «apri YouTube e cerca il canale di MrBeast» — il modello guarda la pagina e sceglie il gesto dopo, fino a
quando la frase è fatta o non si può fare. È **lavoro agentico** (`docs/STATO.md` 5.7): la registrazione di M14.3 lo
voleva come una sessione di Claude Code lanciata da ELA, con le capability del browser di ELA come strumenti e il Guardian
come host dei permessi — oppure una revisione aperta della 5.7, con i costi delle due strade misurati.

La SPEC ha scritto la regola per lasciare la sessione **prima dei numeri**, nella forma di ADR 0052 §16 — tre fatti: (a) la
sessione non si chiude sulle sole capability di ELA; (b) una chiamata della sessione non passa dal cancello; (c) sulle
stesse frasi la sessione costa più del doppio del ciclo di ELA, con tutti e due i modelli —, e la misura di Tommaso non
ne ha trovato nessuno (decisione 21): ogni richiesta ha offerto solo `mcp__ela__read` e `mcp__ela__act`, nessuna
connessione fuori da loopback, la chiave in nessun posto, e la sessione costa 1,26 volte il ciclo su Haiku 4.5, 1,10 su
Haiku 5.5 e 1,11 su Sonnet 5.5. **La strada è la sessione.**

Quattro cose che il codice di prima non sapeva: **un tool non sa il task e lo step della sua chiamata** — riceve la
decisione, gli argomenti e il «ferma» —; **lo scope di una capability si fissa quando il registro nasce**, e un passo non
può stringerlo; **il cancello di M14.1 prenota per uno step e chiude con un esito**, e non ha un modo di pesare una
chiamata dentro una prenotazione che c'è già; **la regola 61 vede solo chi chiama `.complete(`**, e una sessione spende
sulla stessa chiave senza chiamarlo.

## Decisione

### 1. La capability: `browser.guided`, un sì per una sessione

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `browser.guided` | MEDIUM | `undeclared` | `sites` | sì | `goal: string`, `sites: array`, `max_cost_usd: string`, `looks: integer`, `seconds: integer` | `task_type: string` |

`MEDIUM` con `requires_authorization`: **un sì copre una sessione** (ADR 0046). **Né idempotente né ripiazzabile**
(regola 60): spende. Sul Core soltanto. Non `browser.session`, che è il nome di M13.10 per un browser che dura fra gli step.
I siti sono **l'argomento con lo scope**, uno o più, ciascuno un bersaglio suo (`targets_of` impara gli elenchi: un elenco
vuoto non dà bersagli, e uno scope non vuoto senza bersagli è un dubbio), ciascuno dentro `ELA_BROWSER_SITES`, e sono il
confine di ogni gesto. `looks` va da 1 a 30, `seconds` da 30 a 1800; `max_cost_usd` è un `Decimal` scritto come stringa.
`task_type` sceglie la rotta del router, `browsing` di default (§14).

**La domanda** nomina, oltre ai pezzi di ogni domanda, **la frase**, **i siti**, **il modello** che il router sceglie,
**il costo massimo**, **gli sguardi massimi**, **la durata** e **che il testo delle pagine va ad Anthropic**, con il caso
peggiore — «0.6 USD, claude-haiku-5-5, up to 991808 tokens in and 8192 out per call» — e ciò che resta del mese di ADR 0057
§8. I campi della domanda sono `phrase`, `sites`, `model`, `max_cost`, `looks` e `sends`; la durata riusa
`timeout_seconds`. La console e il telefono mostrano il modello, il costo, gli sguardi e ciò che esce **sopra il tetto**, la
frase e i siti **sotto**, come lo scopo di uno step (regola H di ADR 0045 §11).

**«Partirebbe»** (ADR 0045 §6-bis): prima della domanda si rifiutano gli argomenti, la rotta, un costo massimo sotto il
caso peggiore di una chiamata (`guided.cap_below_one_call`), il binario che non c'è (`guided.not_installed`) e la cartella
che non si prepara (`guided.folder_changed`). **Il modello della domanda è quello dell'esecuzione**: se al sì il router ne
sceglie un altro, lo step fallisce, `guided.route_changed`, e la sessione non parte.

### 2. Il tetto della sessione

**La prenotazione** è il costo massimo, dichiarato da `worst_case` del tool e prenotato nella `STARTED` dello step dal
cancello di M14.1. `WorstCase` porta l'importo della sessione e i token di **una** chiamata (`per_call`).

**Il bilancio della sessione**, `SessionBudget` in `ela.executive.spending`, pesa ogni chiamata **prima che lasci il Mac**:
parte solo se **speso nella sessione + in volo + caso peggiore ≤ prenotazione**, con il caso peggiore di ADR 0057 §2 sul
modello e sul `max_tokens` della richiesta vera. Rifiuta prima della rete, e ciascun rifiuto **ferma la sessione** con il
suo codice — una sessione che riceve errori ritenta, e ogni ritentativo sarebbe una chiamata nuova da rifiutare:

| Rifiuto | Codice |
|---|---|
| una chiamata prima che gli strumenti dell'avvio siano controllati | `guided.unchecked` |
| strumenti che non sono esattamente i due della sessione, all'avvio o in una chiamata | `guided.tools_changed` |
| un modello diverso da quello del router | `guided.model_changed` |
| nessun `max_tokens`, o più di quello dichiarato | `guided.max_tokens` |
| un `cache_control` | `guided.cache` |
| una chiamata che non ci sta, o senza prezzo | `guided.cost` |

Il bilancio sta in memoria: la prenotazione è già nel libro del mese, e un crash lascia la `STARTED` aperta al suo caso
peggiore, come ADR 0057 §4. **La chiusura**: lo usage della sessione è la somma delle chiamate, **quella dall'esito ignoto
al suo caso peggiore** — lo stream interrotto, la connessione caduta, una chiamata ancora in volo alla fine —, e chiude la
`STARTED` (la domanda 11, decisa (a)). `--max-budget-usd` uguale al costo massimo è **una seconda recinzione, dichiarata
come tale** — un'altra stima, con un altro listino, controllata a risposta arrivata —, e `total_cost_usd` si scrive nel
risultato accanto al conto di ELA, mai al suo posto.

**Il cancello che chiude a zero.** Una chiamata che spende fermata prima di agire **non ha mandato niente**, e il suo
risultato lo dice (`sent` falso): la sua prenotazione si chiude a zero invece di restare al caso peggiore fino al primo del
mese. Vale per ogni tool che spende — `model.complete` compreso — ed è la decisione 11, «ogni prenotazione aperta si
chiude».

### 3. Il gateway, sulla porta di sempre

| Metodo | Percorso | Che cosa |
|---|---|---|
| `POST` | `/sessions/{session}/v1/messages` | una chiamata della sessione al modello: pesata dal bilancio, e inoltrata con la chiave solo se ammessa |

**Una rotta dell'app di `ela serve`**, non un secondo ascoltatore (la domanda 5, decisa (a)): la regola «un solo posto
dove si risolve un'identità» regge, e la tailnet non vede le rotte di una sessione. **Un'identità nuova, `SESSION`**, la
sesta di `Kind`, risolta in `security.py` come ogni altra: valida solo se i due capi del socket sono di loopback, solo sul
percorso della sua sessione e solo finché la sessione è aperta. **Il gettone arriva in `x-api-key`** — Claude Code manda lì
`ANTHROPIC_API_KEY`, e l'`ANTHROPIC_API_KEY` della sessione è il gettone —, 32 byte casuali che valgono solo lì; `security.py`
e solo lui (regola 47) legge quell'intestazione, sui soli percorsi di una sessione, e la confronta con `compare_digest`
(regola 31), rifiutando lì il gettone del Core (`core_on_a_session`) e un socket non di loopback (`session_from_elsewhere`).
**`count_tokens`, `HEAD /api/hello` e `GET /v1/models` non hanno una rotta**: rifiutati, e non fermano niente.

**La chiave** sta in un pacchetto solo: l'adattatore `AnthropicGateway` di `ela.providers.anthropic`, accanto al provider,
la mette su una chiamata **solo con un `Admission`** — ciò che il bilancio ha coniato per lei —, manda il corpo com'è
arrivato, e restituisce la risposta **evento per evento**, leggendo lo usage mentre passa: `message_start` dà l'ingresso,
`message_delta` l'uscita, `message_stop` dice che la chiamata è finita. Un `4xx` o un `529` sono una chiamata rifiutata prima
di girare, a costo zero (la lettura di `classify`); una chiamata che non è partita costa zero e lo dice; il resto è un esito
ignoto. **I byte del corpo** (M14.6) entrano nello usage di ogni chiamata.

### 4. Un gesto, un task figlio

**Ogni gesto della sessione è un task figlio** del task della sessione (la domanda 1, decisa (a)): un cammino solo
nell'executor, nessuna seconda porta. **La stanza delle sessioni**, `ela.executive.sessions`, lo crea con
`create_child` e la chiave `gesture-<n>/<step della sessione>`, `LOCAL_ONLY`, con un goal di parole di ELA — il numero, lo
step, la capability e il sito se è della sessione —; lo pianifica con uno step: la capability chiesta, gli argomenti scritti
dal modello con lo scopo scritto da ELA, **il rischio e l'autorizzazione del catalogo**, le condizioni del suo verifier, e
**`within`**, i siti della sessione.

**`TaskStep.within` può solo stringere** (la domanda 2, decisa (a)): il Guardian nega con `Rule.SCOPE` un bersaglio che lo
scope della capability non copre **o** che `within` non copre. È la proprietà di ADR 0026 §7 — un passo può stringere e mai
allargare — estesa allo scope, e la sua proprietà la prova anche lì (`test_client_plan_properties.py`). Viaggia nel JSON
dei passi: nessuna migrazione; la rotta del piano a mano non lo porta.

**Chi l'ha scritto: un quarto autore, `SESSION`** (la domanda 3, decisa (b), perché la `STARTED` non arriva al tool): con **lo
step della sessione** e il suo modello, obbligatori per `SESSION` e rifiutati agli altri tre dal validatore del dominio.
**La porta è `engine.plan`, e la stanza ne è la terza** (la domanda 4, decisa (a)): la regola 62 tiene lo slug di M14.2 e
ammette `executive/sessions.py`.

**Il cammino**: la stanza prende **il lock di `run` del figlio** — lo stesso insieme delle rotte, che smette di vivere in
`app.state` e diventa di `Ela` (`Ela.running`) — e chiama `runner.run`; la regola del lock di `test_travel_rules.py` si
estende alla stanza, ai metodi della sua classe. **Il cammino è blindato** (`asyncio.shield`): l'interrupt della sessione
cancella la chiamata del suo strumento in-process, e un runner cancellato a metà lascerebbe aperto lo step del figlio e
libero il suo lock; il figlio va avanti fino alla fine che il suo «ferma» gli dà. **I tool nascono prima del runner e dei
verifier**: la stanza nasce con l'engine e il catalogo, e li riceve con `bind`, **l'unico legame tardivo del grafo**, scritto.

**Un sì resta dell'utente** (regola 19): un `browser.act` porta il figlio a `WAITING_APPROVAL`, la campana suona, e **la
sessione aspetta** che il figlio finisca — un sì dalla console o dal telefono lo fa ripartire, con la CLI `ela task approve`
e poi `ela task run <figlio>` —; un no lo chiude `DENIED`, e la sessione legge la ragione. **La durata conta l'attesa** (la
domanda 12). **Il testo che torna alla sessione** è il risultato del figlio — l'indirizzo, lo stato, il titolo, il testo —
o la ragione della sua fine.

**Il «ferma» scende**: la rotta di `cancel` ferma i figli vivi della sessione, come `stop_planning`, e chiude ciò che
lasciano aperto; la sessione sente il «ferma» del suo task. **E all'avvio**: un figlio di un gesto ancora vivo il cui padre
è finito si ferma nel lifespan, con una lettura del repository, prima della chiusura degli step dei task finiti.

### 5. Il livello dei permessi di Claude Code, e la 5.7 riletta

**Niente da chiedere**: `--tools ""`, i soli server in-process di ELA con `--strict-mcp-config`, `--allowedTools` con i due
strumenti, `--permission-mode dontAsk`, `--permission-prompts none`, **nessun permission prompt tool e nessun
`can_use_tool`**. **Una richiesta di permesso è un fatto anomalo** (§33): la sessione la nega da sé, ed ELA la ferma,
`guided.permission_asked` (la domanda 13).

**Gli strumenti si controllano a ogni chiamata, non una volta** (decisione 22): il gateway rifiuta prima della rete una
chiamata il cui `tools` non è esattamente i due della sessione, e lo stesso controllo vale per l'elenco del messaggio
d'avvio, prima della prima chiamata — il gateway non ne ammette nessuna finché quel controllo non è passato.

**La 5.7 si legge così**: la **prima** condizione è intatta — un processo, mai mouse e tastiera —; la **seconda**, «il
Guardian è l'host dei permessi della sessione», si legge **«ogni effetto della sessione è un'esecuzione dell'executor, con il
Guardian»**: lo strato dei permessi di Claude Code non decide niente, perché non ha niente da decidere; la **terza**,
decisa il 2026-09-30, «ciò che si approva è ogni effetto, uno per uno».

### 6. La cartella, e il lanciatore

**Una cartella per sessione**, `<capture store>/../sessions/<step>/` — accanto all'archivio delle catture, come la cartella
della voce —, creata vuota da ELA: è la `HOME`, la `CLAUDE_CONFIG_DIR` e la cartella di lavoro della sessione. **Contiene
solo il lanciatore**, che ELA scrive e **ricontrolla prima del lancio** — esattamente quel file, con l'impronta scritta —;
altrimenti la sessione non parte, `guided.folder_changed`. **Alla fine si cancella**: Claude Code ci lascia i suoi registri,
che possono portare il testo delle pagine (§57). La 5.8 vale per quella cartella: modalità pulita con la chiave, `--bare`,
che non legge né OAuth né il portachiavi, e la «chiave» è il gettone.

**Una sessione per step, alla volta.** Lo step è l'identità della cartella, del percorso del gateway e del posto nella
stanza, e un piano a mano porta gli id dei suoi step: lo stesso file mandato a due task dà due sessioni con lo stesso step.
**La seconda è rifiutata prima di toccare la prima**, con `guided.folder_changed` — ciò che la sua cartella sarebbe —, e la
sua prenotazione si chiude a zero: niente è uscito. Trovato scrivendo la prova a mano (`milestones/M14.3.md`,
«L'implementazione, e dove si scosta»).

**Ciò che un crash lascia, e l'avvio che lo spazza** (decisione 34 della review del riepilogo). ELA ferma una sessione
con l'interrupt e, dopo la grazia, con `SIGKILL` al processo: codice che gira solo se `ela serve` gira. **Misurato sul Mac
il 2026-10-09**, con il binario dell'SDK e il modello finto, nessuna spesa (`.git/m14.3-reference/sonde/probe_crash.py`): un
processo che fa la parte di `ela serve` — il gateway e la sessione — ucciso con `SIGKILL`, in due momenti, un gesto in corso
e una chiamata al modello in volo. **In tutti e due `claude` sopravvive**: adottato da `launchd` (ppid 1), vivo dopo 1 s,
dopo 5 s e dopo 120 s, quando la sonda lo uccide; la cartella resta, con i file che Claude Code ci scrive. Quindi:
(a) **al lancio ELA scrive il pid del processo nella cartella**, accanto al lanciatore, e il controllo della cartella conosce
quel file — un numero e nient'altro —; (b) **all'avvio**, dopo `close_orphans` e accanto alla purga delle catture e allo
spazzino della voce, **ELA legge ogni cartella delle sessioni**: se il pid è vivo, `SIGKILL`; poi cancella la cartella.
All'avvio nessuna sessione ha diritto di vivere: il suo gateway era il processo che riparte. **Un pid il kernel lo ridà**, e
dopo un crash e un riavvio può nominare un altro programma: ELA uccide il processo solo se il suo comando è il binario della
sessione, e la cartella la cancella comunque. È la forma di ADR 0029 §1 — l'avvio è il solo momento che ELA raggiunge di
certo — e di ADR 0034 §7 — uno spazzino che normalmente non trova niente —, e la cartella è §57 come i file di ADR 0047 §6:
può tenere i registri di Claude Code con il testo delle pagine. Il port `AgentSession` ha `sweep`; il resto della finestra è
il crash fra la partenza del processo e la scrittura del suo pid, un passo.

**L'ambiente è chiuso**: i quattro nomi di un programma del terminale (ADR 0047 §6) e quelli della sessione — il gateway, il
gettone, il traffico non essenziale spento, l'aggiornamento automatico, la telemetria e le segnalazioni spenti, il titolo
spento, la cache spenta, la compattazione spenta, ogni modello di servizio uguale al modello del router,
`CLAUDE_CODE_MAX_OUTPUT_TOKENS`, `MAX_THINKING_TOKENS=0`, `MCP_TOOL_TIMEOUT` alla durata. **L'SDK costruisce l'ambiente di
`claude` da quello del processo che lo usa**: dentro ELA erediterebbe quello di `ela serve`, una variabile `ELA_` compresa.
Quindi `cli_path` è il lanciatore: `env -i`, i nomi che passa **per nome** — mai i valori: il gettone non sta nel file —, e
il binario che l'SDK porta.

### 7. Il «ferma»

Al «ferma» del task, ELA chiama **l'interrupt dell'SDK** — che chiude il turno e scrive la fine —, poi chiude l'ingresso del
processo, e dopo una grazia senza uscita (`GRACE_SECONDS`, cinque secondi) **`SIGKILL` al processo**. **Mai `SIGTERM` per
primo**. Il processo è uno: la sessione non ha strumenti propri, quindi nessun figlio, e il verifier lo guarda (`guided.closed`).
Il gesto in corso è fermato dal «ferma» del suo figlio, con il punto di non ritorno di sempre. **Ogni prenotazione si
chiude**: la `STARTED` della sessione con la somma, quelle dei figli con i loro esiti.

**Lo step fermato.** Il punto di non ritorno della sessione è **il lancio** (`the launch of the session`): un «ferma» prima
non lancia niente, e lo step è `CANCELLED` con `execution.stopped` e la prenotazione chiusa a zero (§2); dopo, la sessione
ha mandato la frase e ha speso, e il risultato è `FAILED` con **`guided.stopped`**, lo usage della somma, e `halt` `ACTED`.

### 8. Che cosa il modello guarda, e le quattro risposte di §57

Solo **il testo che `browser.read` già restituisce** — l'indirizzo finale, lo stato, il titolo, l'inizio del testo
visibile fino a 64 KiB —; i due strumenti dichiarano `anthropic/maxResultSizeChars` sopra quel taglio, perché la sessione
non riceva un percorso di file. Nessuna immagine (M14.4), nessun link (la domanda 14). **Il contesto di ELA non entra**: la
stanza sta in `ela.executive`, che non importa `ela.context` (contratto 15).

1. **Il fornitore**: Anthropic, con la chiave di ELA, attraverso il gateway.
2. **I dati**: la frase, i siti, le istruzioni di ELA, il testo delle pagine lette nella sessione — fino a 64 KiB per
   pagina —, l'esito di ogni gesto, e ciò che Claude Code aggiunge di suo (le definizioni dei due strumenti e un blocco di
   attribuzione con la sua versione).
3. **Il perché**: il modello sceglie il gesto dopo.
4. **La policy**: «we automatically delete inputs and outputs on our backend within 30 days», salvo un accordo diverso, la
   Usage Policy — fino a due anni per una conversazione segnalata — e la legge; mai per l'addestramento senza un permesso
   espresso. Letta il 2026-10-08.

### 9. `browser.read` resta `LOW`, sui fatti riscritti

ADR 0052 §4 e ADR 0058 §9 sono riletti: i tre fatti diventano (1) **i siti li dichiara l'utente**; (2) **una sessione la
avvia l'utente con un sì che nomina la frase, i siti, il modello, il costo e la durata, e dentro la sessione una lettura sui
suoi siti non chiede**; (3) **nel browser non c'è nessuna credenziale**. **Il vincolo del GET si allarga e si dichiara**: un
GET scritto dal modello può portare a un sito della sessione parole della frase **e del testo delle pagine lette**, e agisce
se il sito agisce su un GET. Si accetta perché le pagine sono pubbliche e il browser è vuoto; il giorno in cui non lo sono
più è M13.9, che riceve un'annotazione datata. **Nessun livello si abbassa**: `browser.act` resta `HIGH`.

### 10. YouTube e il consenso

Il consenso sta sopra la home e i risultati, sullo stesso host, e il testo dei risultati porta «@MrBeast»: **la frase della
registrazione si fa senza un click**. La pagina di un canale rimanda a `consent.youtube.com`, che il confine non lascia
partire: **in M14.3 non si apre** (la domanda 16), e la strada è M13.9 con il profilo che dura.

### 11. Il risultato, il verifier e l'audit

Tool aggiunti:

| Capability | Tool | Nome | Idempotente | Codici d'errore | Numeri nell'audit |
|---|---|---|---|---|---|
| `browser.guided` | `BrowserGuidedTool` | `browser-guided` | no | `arguments.invalid`, `guided.cache`, `guided.cap_below_one_call`, `guided.cost`, `guided.duration`, `guided.failed`, `guided.folder_changed`, `guided.looks`, `guided.max_tokens`, `guided.model_changed`, `guided.not_installed`, `guided.permission_asked`, `guided.route_changed`, `guided.session_gone`, `guided.stopped`, `guided.tools_changed`, `guided.unchecked`, `guided.unreserved`, `provider.authentication_error`, `provider.bad_request`, `provider.malformed_response`, `provider.no_output`, `provider.rate_limited`, `provider.refusal`, `provider.rejected`, `provider.server_error`, `provider.spend_limit`, `provider.timeout`, `provider.unavailable`, `provider.unknown_model`, `provider.unknown_model_hint`, `provider.unreachable`, `provider.unsupported_parameter`, `routing.empty_routes`, `routing.unknown_provider`, `routing.unknown_task_type` | `looks`, `refused`, `acts`, `calls`, `input_tokens`, `output_tokens`, `unknown_calls`, `input_minus_bytes_max` |

Verifier aggiunti:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `browser.guided` | `BrowserGuidedVerifier` | `browser-guided-verifier` | `guided.closed`, `guided.reservations_closed`, `guided.gestures_audited` | `guided.left_running`, `guided.reservation_open`, `guided.gesture_unaudited` |

**L'esito**: quando il modello finisce il turno, lo step è `SUCCEEDED`; **quando ELA ferma la sessione su un limite** è
`FAILED` con il codice del limite — `guided.looks`, `guided.duration`, `guided.cost`, e i rifiuti di §2 —, e **un limite e
la fine del turno nello stesso istante sono il limite**: la parola di ELA prima. Una fine con un errore della sessione è
`guided.failed`. **Un `SUCCEEDED` non dice che la frase è fatta**: dice che la sessione ha finito il suo turno da sé.

**Il risultato** porta il testo finale, gli sguardi, i gesti negati, gli `act` chiesti, le chiamate — una per una come
modello, token e byte —, i token, il costo con il listino di ELA, le chiamate dall'esito ignoto, la fine, il modello, la
versione di Claude Code e `total_cost_usd` accanto. **Il testo finale è contenuto arrivato da fuori** (ADR 0059 §4): sta
nel risultato, nell'archivio privato. **Nell'audit solo numeri**: `TOOL_EXECUTED` porta quelli della tabella — con
**`input_minus_bytes_max`**, il massimo sulle chiamate di token d'ingresso meno byte del corpo, il numero con cui ADR 0057
§2 si rivede (decisione 26) — e lo usage; mai la frase, i siti, un indirizzo, il testo di una pagina o la risposta.

**Il verifier** ha tre condizioni e mai una quarta: **`guided.closed`** — nessun processo della sessione resta, letto dal
kernel —; **`guided.reservations_closed`** — la sessione non è più aperta nella stanza, e il risultato chiude la `STARTED`
con un costo —; **`guided.gestures_audited`** — ogni gesto che il risultato conta è un figlio con il suo `TASK_CREATED`
nell'audit. **Mai «la frase è fatta»** (ADR 0047 §9).

### 12. La regola 65, e come si rileggono la 25 e la 61

**La regola 65, `who-spends-passes-the-gate`**, in tre parti, ciascuna con i suoi casi negativi:

1. **Il lasciapassare lo conia il cancello**: fuori da `ela.executive.spending` nessuno costruisce un `Admission` — ciò che
   il bilancio dà a una chiamata ammessa — o una `Reservation` — ciò che il cancello dà a una `STARTED` prenotata.
2. **Chi spende si trova leggendo l'albero, non un elenco**: i metodi dei port che ricevono un lasciapassare —
   `ModelGateway.forward`, `AgentSession.launch` —, e in ogni pacchetto con un modulo che legge la chiave, ogni funzione che
   chiama il fornitore è un metodo di una classe che definisce `complete` — la strada di ADR 0057 — o riceve un `Admission`.
   **La vacuità**: sull'albero vero i port hanno un metodo per ciascun lasciapassare, o la regola non guarda niente e lo dice.
3. **Chi lancia una sessione dichiara il suo caso peggiore**: una classe che chiama un metodo che riceve una `Reservation`
   definisce `worst_case`, la forma della regola 61 estesa.

**La 25** dice dove sta la chiamata a `complete`, e resta vera: il gateway non chiama `complete`. **La 61** dice che chi la
chiama la limita, ed è una delle due strade: la frase «this rule is blind to it» diventa «the other road is rule 65's».
**Nessuna esenzione nuova** nelle tre. E la **regola 32** vede `claude_agent_sdk` fra le librerie che lanciano processi.

### 13. Il binario: l'Agent SDK, con gli strumenti in-process

**`claude-agent-sdk` 0.2.165 nel lock**, con il binario di Claude Code 2.1.294 dentro la sua ruota: la versione che gira è
quella del lock (la domanda 6, decisa (a)). **L'import di `claude_agent_sdk` sta in un modulo solo**,
`ela.infrastructure.machine.agent`. Gli strumenti sono in-process — nessuna rotta MCP, nessun gettone per lei —, e **un gesto
che aspetta un sì non scade dalla parte di Claude Code**: «The idle timeout applies to every server type except IDE servers
and SDK in-process servers», e la prova a secco ha visto una risposta dopo 330,0 s. Il prezzo: una ruota di 98–110 MB per
sistema, il PC compreso.

**La regola P** (proposta 13): `make check` dentro il giro — a + b + c, la soglia il 10 % — e la CI — i passi
d'installazione, due minuti a freddo e trenta secondi con la cache —; sopra, la milestone si ferma. I numeri sono nel
documento della milestone, «L'implementazione, e dove si scosta».

### 14. La rotta `browsing`

| `task_type` | Provider | Profilo |
|---|---|---|
| `browsing` | `anthropic` | `cheap` |

La rotta di una sessione, **il profilo economico**, che con M14.6 è Haiku 5.5 (decisione 25): sei frasi su sei nella misura,
come Sonnet 5.5, a un diciannovesimo del costo: 0,004609 $ a sessione contro 0,088818 $ (il file della misura,
`milestones/M14.3.md`, «La misura del 2026-10-08 — i numeri»). **`max_tokens` resta 8192**, una costante del tool: nessuna chiamata della misura ci è
arrivata. Su Haiku 5.5 la sessione pensa nonostante `MAX_THINKING_TOKENS=0`, e il pensiero sta dentro `max_tokens`: il caso
peggiore regge.

### 15. I port, e il punto di non ritorno

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ModelGateway` | §26, §30, §57 | async | `read`, `worst`, `forward` |
| `Gestures` | §19, §27 | async | `open`, `start`, `gesture`, `halt`, `halted`, `close`, `is_open`, `gesture_ids` |
| `AgentSession` | §19, §24 | async | `tools`, `ready`, `running`, `launch`, `sweep` |

Un modo solo per port (ADR 0005 §1): i richiami della sessione verso l'host — gli strumenti dell'avvio, un gesto, un
permesso chiesto — sono async anche loro. Il tool riceve **la decisione** con un gancio della base, `_decided`, perché i
gesti sono figli del task del suo step: le due id vengono dalla decisione, mai da un argomento.

| Capability | Qui | Su un nodo |
|---|---|---|
| `browser.guided` | `the launch of the session` | `None` |

### 16. Righe riviste

Gli ADR non si riscrivono: queste righe si leggono con questo accanto.

- **`docs/STATO.md` 5.7**: la seconda e la terza condizione si leggono come §5.
- **ADR 0052 §4 e ADR 0058 §9**: i tre fatti di `browser.read` e il vincolo del GET sono quelli di §9.
- **ADR 0057 §6**: il cancello sta anche dove una sessione chiama il modello — il gateway, con il bilancio di §2 — e chiude
  a zero la prenotazione di una chiamata fermata prima di agire.
- **ADR 0026 §7**: un passo può stringere anche lo scope, con `within`.
- **La regola 62**: tre porte, con lo slug di oggi.
- **La regola 61**: una delle due strade; l'altra è la 65.

### 17. La prova a mano

La **sezione 26** di `docs/GETTING_STARTED.md`, con `scripts/prova_m14_3.py`, sul Mac, su Haiku 5.5, con le sessioni a
1,10 $ — più di due casi peggiori di una chiamata, 1,032768 $, così due chiamate stanno in volo insieme: con 0,60 $ ne stava
una alla volta, e una sessione di Claude Code che ne mandava due si fermava con `guided.cost` — e un margine di 5,50 $
calcolato dalla funzione del cancello. La lancia Tommaso. **Passata il 2026-10-09** a `f58a6cb`, sul Mac, 45 PASSATI al
primo giro: cinque sessioni su Haiku 5.5 per 0,0032935 $ in tutto, ognuna chiusa con il suo costo vero e la fascia bassa
uguale al libro; ogni gesto un figlio scritto dalla sessione e dentro i suoi siti; il no e il sì al gesto che invia, con i
selettori che il modello ha scritto dalla grammatica degli strumenti, e il modulo partito; il «ferma» che chiude la
sessione e il figlio che aspettava. Le misure sono in `docs/milestones/M14.3.md`, «Il quarto giro».

## Alternative considerate

- **Il ciclo di ELA** — il modello chiamato da ELA uno sguardo alla volta, con un oggetto JSON —: la regola scritta prima dei
  numeri lo voleva solo se la misura trovava uno dei tre fatti, e non ne ha trovato nessuno.
- **La CLI installata** invece dell'SDK: la sua versione non sta nel repository e cambia da sé, e servirebbe una rotta MCP.
- **Gli step aggiunti al piano della sessione** invece dei figli: un'operazione nuova su un grafo che il runner cammina.
- **Un grant della sessione** con lo scope dei suoi siti: un grant con più usi nato da un sì è la forma delle policy di §59.
- **Un secondo ascoltatore per sessione**: un secondo posto dove si risolve un'identità.
- **Il caso peggiore preso dalla richiesta** (la domanda 17): non in M14.3; M14.6 scrive i byte perché il mese di usage
  con cui ADR 0057 §2 si rivede esista.

## Conseguenze

Con questo ADR le regole di architettura sono **sessantacinque** (la 65), i contratti di import-linter restano **quindici**,
i port sono **trentatré**, le rotte dell'API **cinquantadue** e i comandi della CLI restano **ventotto**; le capability sono
**quattordici**, e ne viaggiano **quattro**; le identità del middleware sono **sei**. Nessuna migrazione: `within` e l'autore
`SESSION` viaggiano nel JSON dei piani, i byte nello usage di M14.6.

Ciò che questo ADR dichiara e non risolve:

- **Il vincolo del GET**: un GET scritto dal modello può portare a un sito della sessione parole della frase e delle pagine
  lette, e agire se il sito agisce su un GET.
- **Una sessione su Sonnet 5.5 prenota più di due dollari** prima di spendere un centesimo: il caso peggiore è la finestra.
- **Il binario si aggiorna con il lock**: gli strumenti si controllano a ogni chiamata, non si fidano della misura di un
  giorno.
- **`SIGKILL` al processo, non al gruppo**: l'SDK avvia `claude` nel gruppo di ELA, e un gruppo suo non si ha senza
  l'SDK; la sessione non ha strumenti propri, e il verifier guarda che nessun processo resti.
- **L'ambiente del processo si legge dal processo solo su Linux**: macOS non dà l'ambiente di un altro processo né a
  `KERN_PROCARGS2` né a `ps -E`; il test del binario vero lo legge sul runner Linux, e su questo Mac prova il lanciatore.
- **YouTube cambia**: se un giorno i risultati rimandano al consenso su un altro host, la frase dell'esempio non si fa più in
  M14.3.
- **Il numero di WhatsApp bloccato** è il rischio di M13.9, scritto nella SPEC di M14.3.
