# 0052. Il browser: un profilo vuoto per ogni step, il sito della domanda, e un click inviato che il verifier guarda riuscire

- **Stato:** **Proposta**. SPEC di M13.4 decisa dal revisore il 2026-09-29, con le decisioni 1–14
  (`docs/milestones/M13.4.md`). Resta Proposta finché **i numeri 3 e 4** della registrazione — il tempo
  che il browser aggiunge a `make check` e alla CI — non sono misurati e sotto la soglia scritta prima
  di loro (§16), e finché **la prova a mano** di `docs/GETTING_STARTED.md` §20, il passo sul PC
  compreso, non è passata.
- **Data:** 2026-09-29
- **Riferimenti spec:** §10, §18, §19, §20, §27, §28, §29, §30, §32, §33, §39, §57, §59, §62, §63
- **Milestone:** M13.4

## Contesto

§19 vuole che ELA usi un browser: apra pagine, legga, compili form, navighi, estragga dati, esegua
workflow e verifichi i risultati — «soggetta al Guardian quando produce effetti esterni rilevanti».
La registrazione di M13.4 aveva scelto Playwright e chiesto che il costo si misurasse prima di
deciderlo. Le misure stanno nella SPEC («Le misure», M1–M9 e M5-bis), con le uscite e le sonde in
`.git/m13.4-reference/measure/`; questo ADR scrive le decisioni che poggiano su di loro, e la misura
che ciascuna cita.

## Decisione

### 1. Playwright, e il Chrome Headless Shell che il lock nomina

La dipendenza è `playwright` (1.63.0 nel lock), di progetto: una ruota per ogni sistema, con un
Node.js dentro — 116 MiB dei 134 del pacchetto su questo Mac (M1). Il browser è **lo shell di
Chromium della versione che il lock porta** (153.0.8010.12), installato una volta per macchina con
`uv run playwright install --only-shell chromium`, in `~/Library/Caches/ms-playwright` su questo Mac
(M2). `uv sync --locked` non lo scarica, e senza di lui il primo avvio fallisce con «Executable doesn't
exist»: a runtime non si scarica niente (M2).

Perché lo shell, con le misure: è **il solo che non apre connessioni sue** — zero in trenta secondi,
contro sei e sette destinazioni di Google per il Chromium intero e per il Chrome installato (M4) —; la
sua versione **sta nel repository**, mentre il Chrome installato è già un numero avanti e lo aggiorna
Google (M7); è il più veloce — 226 ms a freddo dall'import al testo letto, 36 a caldo (M3) —; e pesa la
metà del Chromium intero, 195 MiB contro 359 (M2). Sempre senza finestra.

### 2. Il perimetro: il Core, e nessun nodo

Le due capability girano solo su `local`. È la terza risposta di ADR 0048 §7: **il verifier legge la
macchina** — una pagina che vive in un processo di questa macchina, del genere degli store del Core che
ADR 0038 §14 conta già — **e nessun nodo lo porta**. `reads_the_machine = True`, nessuna delle due entra
in `VERIFIED_ON_THE_NODE` né in `node_tools`, e un nodo è rifiutato con `UNVERIFIABLE` anche se
dichiarasse il tool.

Sul PC il browser lancerebbe `node.exe` (firmato OpenJS Foundation) e `chrome-headless-shell.exe` con
quattro DLL **senza firma Authenticode** (M8), sotto uno Smart App Control che blocca ciò che non
riconosce e non si spegne; e non guadagnerebbe niente, perché il profilo è vuoto (§3). **Non è
ripiazzabile**: `browser.act` non è idempotente, e `browser.read` rifatto altrove è un'altra visita.

**Sul PC arriva comunque la ruota** — 38,6 MB, con `node.exe` —, e il processo del nodo importa
l'adapter, perché `ela.composition` è un pacchetto solo: niente li lancia lì. Che lo Smart App Control
lasci stare il nodo è un fatto del PC, e lo prova il passo sul PC di §20, prima del merge (decisione
1). Il nodo non legge né richiede `ELA_BROWSER_SITES`.

### 3. Il profilo: vuoto, di uno step solo

Ogni pagina si apre in **un browser nuovo**, con il profilo temporaneo di Playwright, e si chiude con
lui: nessun cookie, nessuna sessione, niente del Chrome o del Safari dell'utente, niente di un task
precedente. Perché: la registrazione tiene fuori il browser dell'utente; un cookie è una credenziale
(§57), e con il profilo dell'utente ogni azione sarebbe **come l'utente** (§30, §39); il profilo di
Chrome è dietro il portachiavi (ADR 0039 §6), che Playwright non tocca (`--use-mock-keychain`, M7); e un
profilo di ELA che durasse porterebbe un login da un task all'altro senza che nessuna domanda lo dica.
**La domanda di `browser.act` lo dice**: «il sito vede un visitatore, non il tuo account».

### 4. Le due capability, e il loro livello

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `browser.read` | LOW | `undeclared` | `site` | no | `site: string`, `path: string`, `purpose: string` | `selector: string` |
| `browser.act` | HIGH | `undeclared` | `site` | sì | `site: string`, `path: string`, `fill: array`, `click: string`, `expect_text: string`, `purpose: string` | — |

La colonna «Scope» porta il valore di comodo delle fabbriche, `UNDECLARED_SITES`; il confine vero è
`ELA_BROWSER_SITES`, **obbligatoria e senza default**, con `[]` risposta ammessa: le due capability
entrano in `DECLARES_AN_EMPTY_SCOPE`.

**`browser.read` è `LOW`, e poggia su tre fatti** (decisione 4): i siti li dichiara l'utente, il piano
lo scrive l'utente, e nel browser non c'è nessuna credenziale dell'utente. **Non perché una lettura non
abbia effetti**: un GET con un token nella query agisce da sé, e la pagina esegue il suo JavaScript. Il
secondo fatto smette di valere con M14.2, e `docs/milestones/M14.2.md` lo dice. Dentro i siti è
permessa senza domanda — salvo uno step che la chieda —, fuori è negata con `Rule.SCOPE`.

**`browser.act` è `HIGH`**: un click può mandare qualcosa fuori dalla macchina, e ciò che è mandato
non si riprende — per sempre, non «finché §37 non esiste». Il rischio è della capability e mai degli
argomenti (ADR 0026 §7): ELA non sa se un click manda, quindi la capability dice che può.

### 5. Il sito, e un indirizzo che ELA compone

`site` è un nome di host e l'unico argomento con lo scope. **La grammatica sta in un posto solo**,
`SITE_PATTERN`: la legge lo schema — un sito fuori grammatica è `DENIED` con `Rule.ARGUMENTS`, prima
dello scope —, la leggono le impostazioni all'avvio, la rilegge il tool. Non è quella dello scope,
che confronta segmenti di un percorso: `www.example.com` non è `example.com`, e ciascuno si dichiara.

**L'indirizzo è l'origine del sito più `path`, composto dal tool**, mai letto da una stringa del
piano: il bersaglio che il Guardian giudica e l'host su cui il browser va non possono essere due.
**L'origine è una dipendenza del tool** (`Browsing.origin`): in produzione `https://` e il sito, e la
composizione è tenuta a `https` da un test; nei test del browser vero, un'origine locale.

### 6. Il confine della cornice principale

Il Guardian giudica il sito del piano; dove la pagina porta dopo è del tool (ADR 0011, Conseguenze).
Ogni navigazione della cornice principale fuori dal confine **non parte** — l'adapter interrompe la
richiesta — e lo step fallisce `browser.left_site`. Il confine è una funzione di `ela.tools.browser`,
passata all'adapter:

- per **`browser.read`**, le origini dei siti dichiarati;
- per **`browser.act`**, **l'origine del sito della domanda e nessun'altra** (decisione 13): un sì è
  dato per quel sito, e un redirect verso un altro sito dichiarato avrebbe portato i gesti dove la
  domanda non li aveva nominati. Un modulo che manda a un altro host non si invia; un redirect dopo un
  invio riuscito lascia il verifier senza la pagina di conferma, e lo dice.

Ciò che la pagina **carica** — script, immagini, cornici interne — viene da dove la pagina vuole: il
confine è la pagina su cui ELA agisce, non ogni richiesta che fa.

**Come l'adapter lo fa, corretto implementando.** Playwright chiama una route **solo per il primo
indirizzo** di una navigazione: un redirect del server veniva seguito senza passare da lei — un test
del browser vero l'ha trovato, con un secondo server che contava le richieste. Quindi il documento
della cornice principale **lo prende la route**, senza seguire i redirect: un redirect che il confine
rifiuta non si segue, uno che ammette si consegna alla pagina, che lo segue ripassando dalla route
(provato con il browser vero, per ciascuna delle due capability). **La route è il driver**: quel
documento lo scarica Node, con la sua pila TLS e il suo ambiente (§14), e il resto della pagina il
browser — rimisurato così, il 2026-09-30, solo le connessioni che la pagina chiede (M4-bis). E
**la route si risolve sempre**: una prima stesura lasciava senza risposta la richiesta di un sito che
rifiuta la connessione, e la navigazione — senza timeout di Playwright, per scelta — aspettava per
sempre; lo ha trovato lo stesso file di test.

### 7. La domanda, e «partirebbe»: ADR 0045 §6-bis rivista per un browser

La domanda di `browser.act` nomina il sito, l'indirizzo per intero, i gesti uno per riga — ogni campo
con il suo valore, poi il click —, il testo atteso, il tempo e **la frase del tool**: il browser è
vuoto, il sito vede un visitatore, e ciò che manda ELA non può saperlo prima né riprenderlo dopo. Li
porta un campo nuovo di `Prospect`, `visit` — un `Visit`, non un `Target`: il suo `exists` sarebbe un
fatto su un sito che nessuno ha visitato —, e un ramo di `Executor._asked`. `Asked` e `ApprovalOut`
guadagnano `address`, `gestures` ed `expect`, e le tre superfici li mostrano (la regola H di ADR
0045 §11). La domanda di `browser.read`, quando uno step la chiede, nomina sito, indirizzo, tempo e la
frase della lettura.

**ADR 0045 §6-bis si legge, per un browser, «partirebbe, per tutto ciò che si sa senza aprire la
pagina»** (decisione 5), come ADR 0047 §5 l'ha letta per un comando: la grammatica di sito, percorso e
selettori, la forma dei gesti e i loro limiti, e lo shell installato (`browser.not_installed`) si
rifiutano prima della domanda. Aprire la pagina prima del sì sarebbe una visita che l'audit non
registra. **Si perde**: una domanda può nascere già condannata, e il sì è speso — **mai un effetto
diverso da quello approvato**.

### 8. Il gesto: prima si guarda tutto, poi si agisce; e i campi segreti

`browser.act` apre la pagina — uno stato `≥ 400` è `browser.http_status`, un sito che non risponde
`browser.unreachable` —, **controlla ogni elemento prima del primo gesto** — esattamente uno per
selettore, o `browser.element_missing` / `browser.element_ambiguous` —, poi riempie i campi e clicca
(decisione 7). I selettori sono quelli di Playwright senza cambi di motore: `>>`, un prefisso `nome=`,
virgolette o `//` in testa si rifiutano prima della domanda, e la domanda mostra il selettore com'è.
I limiti — 20 campi, 512 caratteri per un selettore, 4096 per un valore, 256 per il testo atteso,
2048 per il percorso — sono decisioni.

**Un campo che si dichiara segreto non si riempie** — `type="password"`, o `autocomplete`
`current-password`, `new-password`, `one-time-code`, `cc-number`, `cc-csc`, `cc-exp*` —, con
`browser.secret_field`, prima del primo gesto (decisione 6). **Il rifiuto non protegge il segreto**:
arriva dopo il sì, quando il valore è già nel piano, in `asked` e sul telefono. Protegge la verità della
frase del tool, falsa dopo un login riuscito dentro lo step, e, per la carta, §30 finché non c'è M14.1.
**Tutti e due i riconoscimenti sono parziali**, e la guida dice: mai una password o una carta in un
piano.

### 9. Il risultato, e un click inviato che il verifier guarda riuscire

Tool aggiunti:

| Capability | Tool | Nome | Idempotente | Codici d'errore | Numeri nell'audit |
|---|---|---|---|---|---|
| `browser.read` | `BrowserReadTool` | `browser-read` | sì | `arguments.invalid`, `browser.not_installed`, `browser.unreachable`, `browser.http_status`, `browser.left_site`, `browser.element_missing`, `browser.element_ambiguous`, `browser.timeout`, `browser.stopped`, `browser.failed` | `status`, `shown`, `total` |
| `browser.act` | `BrowserActTool` | `browser-act` | no | `arguments.invalid`, `browser.not_installed`, `browser.unreachable`, `browser.http_status`, `browser.left_site`, `browser.element_missing`, `browser.element_ambiguous`, `browser.secret_field`, `browser.timeout`, `browser.stopped`, `browser.failed` | `status`, `gestures` |

`browser.read` restituisce l'indirizzo finale, lo stato, il titolo e **l'inizio** del testo, fino a
64 KiB su un confine di carattere, con `shown` e `total`. `browser.act` restituisce lo stato della
pagina del modulo e quanti gesti ha fatto — **non l'indirizzo dopo il click**, che dipende da quando la
navigazione comincia. Un risultato riuscito **lascia la pagina aperta** sotto un identificativo opaco,
`page`: la parola del tool su *quale* pagina, mai su che cosa mostra.

Verifier aggiunti:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `browser.read` | `BrowserReadVerifier` | `browser-read-verifier` | `browser.text_matches` | `browser.text_mismatch`, `browser.page_gone` |
| `browser.act` | `BrowserActVerifier` | `browser-act-verifier` | `browser.expect_visible` | `browser.expect_missing`, `browser.page_gone` |

**Il verifier guarda la pagina, una volta** (ADR 0014 §2): il port la rilascia con l'occhiata, quindi
il verifier non chiama niente che chiuda, e sta in `ela/tools/verifiers.py` con gli altri, dentro la
regola 18. Per un'azione aspetta **l'evento** — il testo atteso che compare — entro il tempo del tool:
**un click inviato non è un click riuscito** (§20), e un click che non fa niente è
`browser.expect_missing`. **Dice ciò che ha verificato, mai che l'effetto sia avvenuto** (ADR 0047 §9).
Una pagina che cambia da sola fra la lettura e l'occhiata fallisce `browser.text_mismatch`, e lo si
dice. **L'occhiata ha una scadenza sola**, attorno a tutta lei: il tempo dell'attesa del testo più
`LOOK_GRACE_SECONDS`, 5 s, per contare, leggere e chiudere; oltre, il verifier solleva e l'executor
scrive `verification.exception` — un'occhiata che non ha risposto non ha verificato (§33). Corretto
implementando: senza, una pagina che non rispondeva teneva la verifica per sempre. **`browser.page_gone`**: ELA si è fermata o riavviata fra il tool e l'occhiata, che `_resume` rifà
al `run` dopo; lo step fallisce, non ritentabile — la risposta di `terminal.program_gone`.
L'adapter chiude da sé una pagina consegnata e mai guardata, allo scadere del tempo del tool contato
dalla consegna.

### 10. Il figlio che non è nostro

- **Un driver e un browser per pagina**, avviati quando lo step comincia e chiusi quando la verifica
  finisce (M3: 226 ms a freddo); la composizione non avvia niente.
- **Il browser riceve quattro variabili** — `PATH`, `HOME`, `TMPDIR`, `LANG`, come un programma del
  terminale (ADR 0047 §6) —, misurato (M6). **Il driver Node è un processo suo** e riceve l'ambiente di
  `ela serve` (§14).
- **I segnali sono di ELA sola**: `handle_sigint`, `handle_sigterm` e `handle_sighup` spenti. Playwright
  avvia il driver nel gruppo di `ela serve`, e con i suoi gestori un `SIGINT` al gruppo chiude la pagina
  in tre giri su tre; spenti, la pagina resta usabile in tre su tre (M5-bis).
- **Il tempo**: 30 s, `BROWSER_TIMEOUT_SECONDS`, costante del tool (decisione 8) — una decisione e non
  una mediana, come ADR 0047 §7 dice di un comando —, e altrettanti al verifier, più il margine di
  §9. **Una scadenza sola attorno a tutto il lavoro del port**, `open` compreso, e nessun timeout di
  Playwright sulle singole chiamate. Allo scadere, `browser.timeout`, con i gesti fatti fin lì e senza
  testo.
- **La fermata di ELA** (ADR 0038 §11): l'adapter chiude ogni browser, e lo step è `browser.stopped`.
- **La morte di colpo** non lascia orfani: l'albero intero se ne va entro mezzo secondo (M5). ADR 0047
  §7 lo dichiarava come limite per il terminale, e qui non c'è.
- **Chiudere è un evento**: quando la chiusura torna, il kernel non conosce più nessun processo della
  pagina (M5-bis), e un test guarda i discendenti del proprio worker subito dopo.

### 11. Dove sta il codice: la regola 32 vede Playwright

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `Browser` | §19 | async | `installed`, `open`, `count`, `field`, `fill`, `click`, `text`, `title`, `left`, `keep`, `glance`, `close` |

Un **meccanismo**: ogni decisione — l'indirizzo, il confine, l'elemento, il valore — gli arriva come
dato da `ela.tools.browser`, che sta nel gate al 100% dei rami. L'adapter è
`ela.infrastructure.machine.browser`, **l'unico modulo che importa `playwright`**: sta lì perché avvia
processi, e ELA tocca il sistema operativo in un posto solo (ADR 0029 §3). `playwright` entra in
`MACHINE_LIBRARIES`, e la regola 32 lo vede ovunque, con il suo caso negativo: **nessuna regola
nuova**. La regola 34 guarda solo gli stati della percezione e di un browser non vede niente: ciò che
tiene le decisioni fuori dall'adapter è che gli arrivano da fuori, e i suoi rami li prova il browser
vero, non il gate. `build()` accetta un `browser=` accanto a `clock`, `power` e `bell`.

### 12. L'audit

`PERMISSION_DECIDED` porta il sito come bersaglio; il `prompt` porta il sito e `purpose`, mai
l'indirizzo, i gesti o i valori, che stanno in `asked` — nella tabella delle approvazioni, che non si
redige nemmeno lei. `TOOL_EXECUTED` porta **solo interi** (ADR 0047 §10). Le frasi d'errore del tool e
dei fallimenti del verifier nominano il sito, l'origine di una navigazione interrotta, lo stato HTTP e
il numero di un gesto, **mai** un selettore, un valore, il percorso, il testo atteso o il testo della
pagina.

### 13. La vista

Nessuna vista propria: la risposta all'impronta di ADR 0044 §6 è scritta nella forma N della SPEC.

### 14. L'ambiente del driver, misurato

Decisione 14: **il driver Node è un processo suo**, con l'ambiente di `ela serve` più ciò che
Playwright aggiunge per sé, e le impostazioni di ELA leggono il `.env` senza esportarlo. **Misurato il
2026-09-29** su questo Mac, i nomi e mai i valori (`.git/m13.4-reference/measure/driver-environment.txt`
e `driver-environment-2.txt`):

- **il driver** di un `ela serve` isolato — con il suo `.env` nella cartella di lavoro, niente
  esportato —, lanciato da una zsh di login interattiva con l'ambiente di un terminale: le variabili
  della shell (`HOME`, `PATH`, `LANG`, `SHELL`, `TERM`, `TMPDIR`, `USER`, quelle di Homebrew…), quelle
  di `uv` (`UV`, `UV_RUN_RECURSION_DEPTH`, `VIRTUAL_ENV`) e quelle di Playwright (`PW_CLI_DISPLAY_VERSION`,
  `PW_LANG_NAME`, `PW_LANG_NAME_VERSION`);
- **l'`ela serve` che Tommaso aveva acceso in quel momento**, da Terminal (`uv run ela serve`): la
  stessa forma, più i nomi che Terminal dà — fra cui `SSH_AUTH_SOCK` —; è l'ambiente che il suo driver
  riceverebbe, più le tre `PW_…`;
- **nessuna variabile `ELA_`**, in nessuno dei processi guardati.

Quindi il driver riceve ciò che la shell dà, e fra ciò anche **`SSH_AUTH_SOCK`** quando c'è: è codice
di Playwright e non un programma dell'utente, e **il browser non la riceve** — gli arrivano le quattro
variabili di §10 (M6). La condizione d'arresto della decisione 14 — una `ELA_` con un segreto — non è
scattata.

**E il documento della cornice principale lo scarica il driver** (§6), non il browser: **la
validazione del certificato e la strada di quella richiesta dipendono dall'ambiente del driver**.
Misurato il 2026-09-30 (M4-ter della SPEC, `tls-invalid-certificate.jsonl`), con un server locale e
un certificato autofirmato: con l'ambiente di oggi il certificato è **rifiutato** e il server non
riceve niente; con **`NODE_TLS_REJECT_UNAUTHORIZED=0`**, o con **`NODE_EXTRA_CA_CERTS`** che nomina il
certificato, la stessa pagina **si apre e si legge**. **`NODE_OPTIONS`** può cambiare le radici di
fiducia o caricare codice nel driver, e non è misurata. **I proxy dell'ambiente** (`HTTPS_PROXY`,
anche con `NODE_USE_ENV_PROXY=1`) oggi **non** cambiano la strada — misurato, con Playwright 1.63.0 —,
e una versione nuova di Playwright va rimisurata. Le richieste che fa il browser le giudica Chromium,
con l'ambiente chiuso di §10: uno script da quel server non si carica nemmeno con
`NODE_TLS_REJECT_UNAUTHORIZED=0` nell'ambiente del driver. **Nella misura della decisione 14 nessuna di
queste variabili c'è**: né una `NODE_…`, né un proxy, né una `SSL_CERT…`. Chi le mette nella shell da
cui lancia `ela serve` cambia che cosa il browser di ELA accetta, e ELA non lo vede.

### 15. Un debito datato: il «ferma» a metà di uno step del browser

**Debito a carico di M6.3c**, dichiarato il **2026-09-29**, dalla SPEC di M13.4 (forma M, decisione 11).

Uno step del browser dura quanto il sito, quindi il caso di M6.3c capita davvero: `POST
/tasks/{id}/cancel` non prende il lock di `run`, e un «ferma» dato mentre il browser lavora **non ferma
il browser** — per `browser.act`, i campi si riempiono e il click parte dopo il «ferma» —; il risultato
si scrive, il verifier guarda la pagina, `TOOL_EXECUTED` ed `EXECUTION_VERIFIED` seguono
`TASK_CANCELLED`, `run` risponde `409` e lo step resta `RUNNING` in un task `CANCELLED`. **Non è il
comportamento giusto.** Il `409` e lo step sono di M6.3c, e da questa SPEC anche **fermare il gesto in
volo** (decisione 11): M6.3c porta la fermata a un tool che gira prima del suo punto di non ritorno —
per `browser.act`, prima del primo gesto —, e dove l'effetto è già avvenuto l'esito e le superfici lo
dicono. **M6.3c è la prima milestone dopo M13.4.**

**Non si ripara qui.**

**La difesa più piccola**:
`tests/api/test_browser_stopped_midway.py::test_a_browser_step_stopped_midway_is_the_defect_of_m6_3c`
afferma il difetto com'è, attraverso l'API, con il browser finto che trattiene il click finché il test
non ha fermato il task. Il giorno in cui fallisce il debito si sta pagando: si scrive il pagamento in un
ADR, e il test si gira.

### 16. I numeri 3 e 4, e la regola scritta prima dei numeri

**Numero 3**: due giri di `make check` prima — sul commit della SPEC decisa, il cui codice è quello di
`main` — e due dopo, sull'ultimo commit dell'implementazione, tutti con l'alimentatore attaccato, Low
Power Mode spento e nessun altro lavoro sulla macchina (decisione 10). Se i due giri «prima»
differiscono fra loro di più del 5 %, il confronto non si legge, e si aggiungono giri. **Numero 4**: i
due passi d'installazione a freddo sul primo push che li porta; il job intero sul primo commit verde, a
freddo con la cache cancellata e con la cache al push dopo. **La soglia**: `make check` più lento del
10 %, un job della CI più lento di due minuti a freddo o di trenta secondi con la cache. **I numeri si
scrivono qui quando ci sono**; sotto la soglia la decisione su Playwright diventa definitiva, sopra la
milestone si ferma e lo dice.

### 17. Righe riviste

Un ADR accettato non si riscrive: le righe qui sotto si leggono con questo accanto.

- **ADR 0045 §6-bis** — «riuscirebbe sul disco di adesso»: per un browser, «partirebbe, per tutto ciò
  che si sa senza aprire la pagina» (§7).
- **ADR 0029 §14** — «il numero si misura»: per un browser il tempo è una decisione, e ciò che si misura
  è la chiusura (§10).
- **ADR 0047 §7** — «se ELA muore di colpo il comando le sopravvive»: vero del terminale, non del
  browser, che se ne va con il padre (§10).
- **ADR 0038 §14**, e la docstring di `VerifierPort.reads_the_machine` — «legge il disco»: una pagina
  che vive in un processo di questa macchina è la macchina (§2).
- **La registrazione di M13.4**, che citava ADR 0038 §16 per il livello nella capability: la regola è
  di ADR 0026 §7, come ADR 0047 §14 aveva già corretto (annotata nel documento della milestone).

## Alternative considerate

- **Il Chrome installato, con `channel="chrome"`** — niente da scaricare e firmato Google; parla con
  Google per conto suo (M4), e la sua versione non è del lock (M7). Scartata (decisione 2).
- **Il Chromium intero** — parla con Google (M4) e pesa il doppio (M2). Scartata.
- **Il browser anche sul PC** — binari senza firma sotto lo Smart App Control (M8), un verifier sul nodo
  per una capability nuova, e niente da guadagnare con un profilo vuoto. Scartata (decisione 1).
- **Un profilo di ELA che dura, o quello dell'utente** — il primo porta sessioni fra i task in silenzio,
  il secondo è fuori dalla registrazione e dietro il portachiavi. Scartate (decisione 3).
- **`browser.read` `MEDIUM`** — una domanda a ogni lettura, per un livello che poggia su tre fatti che
  oggi valgono. Scartata (decisione 4), con M14.2 che la riesamina.
- **Guardare la pagina prima della domanda** — una visita che l'audit non registra. Scartata (decisione
  5).
- **Una sequenza libera di gesti** — un modulo riempito a metà quando la pagina non è quella del piano.
  Scartata (decisione 7).
- **Un redirect fra due siti dichiarati ammesso per un'azione** — i gesti su un sito che la domanda non
  ha nominato: il rilievo bloccante della rilettura. Scartata (decisione 13).
- **Una cartella sua per l'adapter, con una regola nuova** — lasciava la regola 32 cieca sul lancio dei
  processi. Scartata (decisione 9).
- **Il timeout in una variabile** — un numero che decide il sito, e una riga in più. Scartata
  (decisione 8).

## Conseguenze

- `ela.ports` ha il port `Browser`, i fatti `Opened`, `Field`, `Glanced` e `Visit`, e gli errori
  `BrowserError`, `BrowserNotInstalled`, `SiteUnreachable`, `BrowserStopped`, `PageGone` e
  `BrowserFailed`; **`Prospect` ha `visit`**.
- `ela.permissions` ha `BROWSER_READ`, `BROWSER_ACT`, `browser_read`, `browser_act`,
  `UNDECLARED_SITES`, `SITE_PATTERN`, `PATH_PATTERN` e i limiti; `production_catalogue` prende `sites`.
- `ela.tools` ha `browser.py` e i due verifier in `verifiers.py`; `production_tools` prende `browsing` e
  `browser`, `production_verifiers` `browser` e `browser_seconds`. `ela.infrastructure.machine` ha
  `PlaywrightBrowser`. `ela.testing.fakes` ha `FakeBrowser` e `FakePage`.
- `ela.composition` ha `BrowserSettings`; `build()` prende `browser`; `ela init` tiene
  `ELA_BROWSER_SITES` in `REQUIRED`, con l'esempio `[]`.
- `Asked` e `ApprovalOut` hanno `address`, `gestures` ed `expect`; le due pagine le coppie «Indirizzo»,
  «Gesti» e «Testo atteso», e la riga di comando le righe `address`, `gestures` ed `expects`.
- Le capability di produzione sono **tredici**, e **quattro viaggiano, nove no**; le regole di
  architettura restano **cinquantasette**; i port sono **ventinove**; le rotte restano **quarantanove**.
  Questi conteggi di oggi vivono qui; gli ADR precedenti restano appuntati a ciò che videro.
- **Che cosa questa milestone non fa**: non porta il browser su un nodo, non apre il browser
  dell'utente, non fa login, non riconosce un pagamento, non ferma un gesto in volo (M6.3c), non porta
  il Planner.
