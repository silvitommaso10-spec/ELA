# 0047. Il terminale: un comando è `argv`, i programmi ammessi sono lo scope, e la domanda nomina ciò che girerà

- **Stato:** Accettata. SPEC di M13.2 approvata con le decisioni 1–16 della review del 2026-09-21, e
  allineata il 2026-09-24 alle tre domande decise alla ripresa, dopo il merge di M13.1b (ADR 0046).
- **Data:** 2026-09-24
- **Riferimenti spec:** §18, §27, §28, §29, §32, §33, §36, §41, §57, §59, §63
- **Milestone:** M13.2

## Contesto

«Terminale» è la seconda voce dell'Action Core di §18, e la capability che il livello `HIGH` esiste
per proteggere: ADR 0045 ha aperto la riga — un'approvazione a ogni uso, che nessuna policy di §59
raggiungerà —, ADR 0046 le ha fatto spendere il suo sì prima dell'azione. Un terminale porta tre
domande che nessuna capability aveva posto: **che cosa, di un comando, può stare in uno scope** che
ha la forma di un percorso; **che cosa riceve un processo** che ELA lancia per conto dell'utente —
fino a oggi ogni figlio ereditava l'ambiente, lo stdin e la cartella di ELA —; e **dove va ciò che
un programma stampa**, in un log che non si redige.

## Decisione

### 1. Il confine sono i programmi, e la difesa è la domanda a ogni uso

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `terminal.run` | HIGH | `undeclared` | `program` | sì | `program: string`, `args: array`, `purpose: string` | `cwd: string`, `expect_exit: integer` |

La colonna «Scope» porta il valore di comodo della fabbrica, `UNDECLARED_PROGRAMS`; il confine vero è
`ELA_TERMINAL_PROGRAMS`, **obbligatoria e senza default**, con `[]` risposta ammessa. Lo scope nomina
i programmi; gli argomenti di ogni chiamata **non** stanno nello scope: li mostra la domanda, e li
giudica l'utente a ogni uso, che è ciò che la riga `HIGH` garantisce.

**Detto senza attenuarlo**: *ammettere un interprete — `sh`, `python`, `env`, `xargs`, `find` —
significa ammettere qualunque cosa, e la difesa è la domanda a ogni uso.* Nessuna lista di interpreti
né di flag pericolosi: sarebbe incompleta dal primo giorno e insegnerebbe che ciò che non c'è è
sicuro. La shell resta fuori perché ELA non passa mai una stringa a `/bin/sh`; se l'utente dichiara
`/bin/sh`, la domanda mostra `/bin/sh`, `-c` e la stringa, e il sì è suo.

Con `[]` la capability esiste e ogni chiamata è `DENIED` con `Rule.SCOPE` e `[]` nel motivo — il
Guardian lo sapeva già fare. Cambia `check_capability`: uno scope vuoto con un argomento scoped resta
un dubbio (§33) per tutti **tranne** le capability di `DECLARES_AN_EMPTY_SCOPE`, dove è una risposta.

### 2. Un comando è `argv`, e un programma si scrive relativo a `/`

Il programma si scrive `usr/bin/git`, nel `.env`, nel piano e quindi nell'audit, **nella grammatica
di ogni scope**: i quattro confronti che leggono uno scope — il Guardian due volte, i bersagli di
un'approvazione, la scelta del grant — **non sono cambiati**, e nessuno dei loro test. Il processo
riceve `["/" + program, *args]` **come lista, dall'argomento al processo**, senza shell e senza
ricerca nel `PATH`. ELA esegue il percorso dichiarato, non il file a cui porta: un programma che
sceglie che cosa fare dal proprio nome continua a funzionare. Lo shim di `xcode-select`
(`/usr/bin/git`) si dichiara, non si aggira: la guida dice di dichiarare `xcrun --find git` se si
vuole che la domanda nomini ciò che gira.

### 3. Il link: il Guardian nega ciò che il piano scrive, non ciò che il disco risolve

Deciso alla ripresa. `usr/bin/git/../../bin/sh` è `DENIED` con `Rule.SCOPE` prima di ogni domanda,
perché `within_scope` rifiuta ogni `..` come forma. Un link che il piano nomina e l'utente **non** ha
dichiarato è negato anche se porta a un programma dichiarato: un link non trasporta la dichiarazione
del suo bersaglio. **Un link dichiarato è una scelta dell'utente**: se porta fuori dall'elenco **non**
è un `DENIED` per `Rule.SCOPE`, e la domanda nomina il file a cui porta. Un link dichiarato
**ripuntato dopo l'avvio** non lo vede il Guardian, che non legge il disco: lo ferma il tool con
`terminal.program_changed`, prima della domanda (§4).

### 4. L'identità di un programma si fissa all'avvio

Ogni voce dichiarata si risolve **una volta**, all'avvio — il file a cui porta e lo sha256 del suo
contenuto (`ela.tools.programs`) — e si riconfronta **quando la domanda si compone e subito prima
dell'`exec`**. Una tabella sola, letta dal tool e dal verifier: è anche la sola definizione di
«programma dichiarato», e `usr/bin/git/x`, che il prefisso del Guardian lascerebbe passare, non ci
sta — `terminal.not_declared`, prima della domanda. Il rifiuto di un programma cambiato dice che
cosa fare:

> `'/opt/homebrew/bin/rg' changed after ELA started (an update, for instance): restart ELA to accept it`

Una voce che all'avvio non c'è non ferma ELA (§6): la sua identità è «assente», ogni chiamata è
`terminal.no_program` prima della domanda, e se il file compare dopo è `terminal.program_changed`.

**Assente non è cambiato** (review di M13.2, decisione 4). Un programma che all'avvio c'era e adesso
non c'è — cancellato, o un link che non porta più a niente — è **`terminal.program_gone`**, non
`terminal.program_changed`: non c'è niente con cui confrontarlo, e «cambiato» affermerebbe un
confronto che nessuno ha fatto. Vale nei due momenti del tool — la domanda non nasce; una domanda
già aperta, approvata, trova il file sparito prima dell'`exec` e non lancia niente — e dopo
l'esecuzione, nel verifier (§9). `terminal.no_program` resta per ciò che non è mai stato lì, e per
un file che c'è ma non si esegue o non si legge.

**Il confronto non gira sul loop.** Confrontare vuol dire rileggere e rifare lo sha256 dell'intero
file, e un programma dichiarato può essere grande quanto vuole. **Misurato** il 2026-09-24 su questo
Mac, a cache calda, cinque giri (`.git/m13.2-reference/measure/hash.jsonl`): `swift-frontend` dei
Command Line Tools, 357 MB, **119,5 ms**; `clang`, 291 MB, 98 ms; `git`, 7,6 MB, 2,4 ms. Chiamato sul
loop, un ticker da 10 ms ha visto il loop fermo **129,5 ms** — e fermo il loop vuol dire ferma tutta
ELA, compresa la risposta del telefono —; chiamato con **`asyncio.to_thread`**, il ticker non ha visto
nessuna fermata (11,1 ms, il suo periodo). Così fanno il tool, il verifier e la composizione che fissa
le identità all'avvio; `ela.tools.programs` resta sincrono, e il thread è di chi lo chiama. Da freddo
la lettura va al disco ed è più lenta: una ragione in più, non una in meno.
**Due limiti, dichiarati**: non protegge da ciò che è cambiato *prima* dell'avvio, e resta la
finestra fra l'ultimo confronto e l'`exec` — la stessa che ADR 0045 §7 dichiara fra `classify` e
`open` —, perché chiuderla vorrebbe dire eseguire da un descrittore già verificato, e macOS non ha un
`fexecve`.

### 5. Per un comando, «riuscirebbe» significa «partirebbe»: ADR 0045 §6-bis rivista

ADR 0045 §6-bis dice che una domanda si compone solo per ciò che, approvato adesso, «riuscirebbe sul
disco di adesso». **Per un comando quella frase si legge «partirebbe, per tutto ciò che si può sapere
senza lanciarlo»**: il programma è dichiarato, c'è, è un file regolare eseguibile e ha l'identità
dell'avvio; la cartella c'è ed è una cartella dentro lo scope; gli argomenti si possono passare a un
processo — nessun byte NUL, nessun surrogato isolato, niente oltre i limiti di `execve`
(`terminal.arguments_unpassable`).

**I limiti sono due, e si controllano tutt'e due prima della domanda** (review di M13.2, 5b): un
argomento troppo lungo non partirebbe, e §6-bis dice di non chiedere un sì per ciò che non partirebbe.
Li sceglie la composizione nominando il sistema (`argument_limits`, un `if` per sistema), e il rifiuto
dice **quale** limite e **di quanti byte**, senza mai l'argomento:

- **il totale**, `SC_ARG_MAX`: ogni stringa di `argv` e dell'ambiente con il suo NUL e il suo
  puntatore, più i due puntatori che chiudono i vettori. **Misurato** il 2026-09-24 su questo Mac
  (`.git/m13.2-reference/measure/argument_limit.jsonl`): con l'ambiente chiuso, l'argomento più lungo
  che parte è di **1 048 412 byte**, e lì il conto di ELA è 1 048 576, cioè `SC_ARG_MAX`; un byte in
  più è `E2BIG`. **Il conto è quello del kernel al byte**, e resta esatto con un percorso del programma
  di 226 caratteri: macOS non conta il percorso una seconda volta. Un test lo riafferma sul kernel
  vero, `tests/tools/test_terminal_limits.py`;
- **il singolo argomento**, che su Linux ha un limite suo, `MAX_ARG_STRLEN`: 32 pagine, il NUL di
  chiusura compreso — 128 KiB con pagine da 4 KiB —, qualunque cosa ammetta il totale. Su macOS non
  c'è (lo stesso 1 048 412 lo dimostra), e lì il limite del singolo è il totale; su Windows sono tutti
  e due la riga di comando di `CreateProcess`, 32 767 caratteri. Il test sul kernel di Linux gira sul
  runner ubuntu, e **non lo si deduce dai conteggi**: un test che non si salta mai li sorveglia
  tutt'e due, e diventa rosso se sul kernel che coprono uno `skipif` scatta — un `/usr/bin/true` che
  manca compreso —, e se altrove la ragione del salto non è il kernel che manca.

**Il residuo**, che il controllo non può prendere, e perché. **Su Linux il totale non è esatto**: il
kernel copia il percorso del programma una volta in più (`bprm->filename`) e tetta il limite a tre
quarti di `_STK_LIM`, 6 MiB, mentre `SC_ARG_MAX` di glibc è un quarto del limite dello stack, senza
tetto. Con lo stack di default (8 MiB, quindi 2 MiB) un comando che sta nel conto di ELA per meno
della lunghezza del suo percorso, o uno stack senza limite oltre i 6 MiB, il kernel lo rifiuta dopo
il sì: `terminal.not_started`, con `E2BIG` nella frase. Non si corregge fingendo numeri che su
questa macchina non si misurano: il terminale gira sul Core, che è un Mac, e il giorno in cui
viaggerà su un nodo Linux la misura si prende lì (M13.3). **E il limite si legge all'avvio**: un
limite dello stack cambiato dopo non lo vede nessuno — ELA non lo cambia.

**Ciò che non si sa non si finge di saperlo**: se il programma finirà, con quale codice, che cosa
stamperà o toccherà. E nemmeno «partirebbe» si sa per intero: un formato che il kernel non conosce,
uno shebang verso un interprete che non c'è, si scoprono solo all'`exec`. È `terminal.not_started`,
l'unico rifiuto che arriva dopo un sì. Un rifiuto costruito su una previsione di ciò che un
programma farà sarebbe una diagnosi inventata.

### 6. Che cosa riceve un processo

- **Quattro variabili e nient'altro**: `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, `HOME`, `TMPDIR`,
  `LANG=C.UTF-8`. `HOME` e `TMPDIR` li calcola la composizione, una volta, con `Path.home()` e
  `tempfile.gettempdir()`: il tool non legge `os.environ`. **`SSH_AUTH_SOCK` non arriva**, e si dice:
  un `git` via ssh non funziona da `terminal.run`, perché l'agente ssh è un'autorità che l'utente non
  ha dato a quel comando. Il `PATH` fisso non è un confine: un programma ammesso che ne lancia un
  altro per percorso assoluto lo lancia comunque (§1).
- **stdin è la fine di un file**: un programma che chiede qualcosa non riceve la TTY di ELA.
- **La cartella è quella dello scope di M13.1** (`ELA_FS_ROOT/ELA_FS_SCOPE`), o una sotto (`cwd`),
  classificata con la **stessa** `classify` di `fs.*`: «dentro» è `path.outside_root`, senza una
  seconda definizione; un file è `terminal.cwd_not_a_folder`. **Mai la cartella di ELA**, che fino a
  oggi era la cwd di ogni figlio e contiene il `.env`. **La cartella non è un confine**, e la domanda
  lo dice con la frase del tool: *«runs this program from this folder: it can read and change
  whatever you can, and ELA sees what it prints, not what it changes»*.
- **All'avvio si rifiutano solo** una voce che la grammatica non ammette, una cartella e un file che
  non si esegue. Deciso alla ripresa: **cade anche il rifiuto dei programmi dentro l'albero di ELA e
  il suo `.venv/bin`**, per la ragione del §1 — qualunque interprete ammesso arriva alle stesse cose.

### 7. Il tempo, il gruppo, e la fermata

Il comando nasce in **una sessione sua**, e fermarlo è fermare il suo gruppo: `SIGTERM`, un respiro
di 2 s — una decisione, quindi una costante del tool passata al lanciatore —, `SIGKILL`, e **il
lanciatore torna solo quando il kernel non conosce più nessun processo del gruppo**. Il timeout è
`ELA_TERMINAL_TIMEOUT_SECONDS`, 120 s, tetto 900; la domanda lo mostra; nessun argomento lo cambia.

**ADR 0029 §14 rivista per il terminale.** «Un timeout suo, e il numero si misura» resta vero per i
figli di ELA, che fanno sempre lo stesso lavoro; il lavoro di un terminale è il programma che l'utente
sceglie e non ha una mediana. **Ciò che si misura è l'altra metà**: quanto ci mette ELA, dallo
scadere, a non avere più un processo vivo del gruppo. **Misurato** il 2026-09-24 su questo Mac (macOS
26.6, Python 3.12.14), cinque giri per caso, con il lanciatore vero e un figlio che crea un nipote:
**14–19 ms** quando il gruppo obbedisce a `SIGTERM`; **2024–2028 ms** quando il nipote lo ignora —
il respiro, più 24–28 ms. Il respiro finisce appena il kernel non conosce più nessun processo del
gruppo, e il suo limite è una scadenza sull'orologio del loop: contato in domande da 10 ms, lo stesso
caso misurava 2222 ms, perché un `sleep` di dieci millisecondi ne dura di più. Il numero sta qui e non in un test (ADR 0026 §6): il test afferma il fatto,
il gruppo vuoto.

**La fermata di ELA non è una cancellazione.** La SPEC diceva che, fermandosi, ELA uccide i gruppi
«per la strada della cancellazione»; ma al primo Ctrl-C `uvicorn` chiude i socket e **aspetta** le
richieste in corso (misurato in M12.2, `src/ela/api/server.py`), e il comando aspetterebbe fino al
suo timeout. La strada che c'è è **il segnale di ADR 0038 §11**, alzato dal gestore del segnale
nell'istante del Ctrl-C: diventa un evento di `Ela`, lo stesso per i long-poll delle pagine e per il
lanciatore, che al segnale ferma il gruppo come allo scadere. Il risultato è `FAILED` con un codice
suo, **`terminal.stopped`** — non `terminal.timeout`, che nominerebbe una ragione che non è quella —,
con l'uscita parziale e `ended: "stopped_by_ela"`. Una cancellazione vera ferma il gruppo e rilancia.

**Un comando è finito quando è finito il suo primo processo.** Ciò che lascia nel gruppo non è il
comando: il lanciatore dà alle pipe 2 s per consegnare ciò che è in viaggio, poi svuota il gruppo
come allo scadere e chiude le pipe. Trovato dalla rilettura: prima il lanciatore aspettava la pipe
fino al timeout, e un programma uscito con 0 lasciando un figlio in background diventava
`terminal.timeout` — una ragione che non è quella, come sarebbe stata per la fermata. Il risultato è
quello del programma, `EXITED` con il suo codice; ciò che il discendente avrebbe scritto dopo non lo
legge nessuno.

**Tre limiti, dichiarati.** Un programma che crea una sessione sua (`setsid`, un demone) esce dal
gruppo e sopravvive — e non trattiene il lanciatore sulla pipe che tiene, né trasforma in un timeout
la fine del programma che l'ha creato. Un Ctrl-C nel terminale di
`ela serve` non raggiunge più il comando da solo: lo raggiunge ELA. **Se ELA muore di colpo** il
comando le sopravvive (ADR 0036 §6): il tool è `idempotent = False`, lo step è `STARTED` prima del
lancio, e il ripristino lo chiude come interrotto **senza mai rilanciarlo**.

### 8. L'uscita: testa e coda, e dove sta il taglio

Solo nel risultato, mai nell'audit né in un messaggio d'errore. **Testa e coda**, metà e metà del
tetto (`ELA_TERMINAL_OUTPUT_MAX_BYTES`, 64 KiB per flusso, tetto 1 MiB), tenute **mentre si legge**;
il taglio cade su un confine di carattere; il risultato dice **dove** ha tagliato (`cut_after`),
**quanto manca** (`missing`), quanto ha tenuto e quanto c'era (`shown`, `total`), **tutto in byte
grezzi**. Le relazioni fra i numeri le afferma un modello del dominio con il suo validatore,
`CommandOutput` (il precedente è `ContextWork`). I byte non UTF-8 si sostituiscono e si contano
(`replaced`): **qui è diverso da ADR 0045 §8**, dove un file non UTF-8 è un rifiuto, perché lì il
risultato *è* il contenuto di un file e una sostituzione non dichiarata direbbe che nel file c'è ciò
che non c'è; qui il risultato è ciò che un programma ha stampato, e la sostituzione è dichiarata con
il suo numero. Il tool è `SUCCEEDED` quando il programma è finito da sé, con qualunque codice.

### 9. Il verifier dice ciò che ha verificato, mai che l'effetto sia avvenuto

Verifier aggiunti:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `terminal.run` | `TerminalRunVerifier` | `terminal-run-verifier` | `terminal.exit_code_matches`, `terminal.output_whole`, `terminal.program_unchanged` | `terminal.exit_code_mismatch`, `terminal.output_incomplete`, `terminal.program_changed`, `terminal.program_gone`, `terminal.no_program`, `terminal.not_declared` |

Il codice atteso è un argomento del piano, `expect_exit`, 0 se non c'è: un `grep` che non trova niente
esce con 1, e un piano che cerca un'assenza lo dichiara. Il verifier lo legge dagli **argomenti**,
l'intento (ADR 0014 §2), mai dal risultato. **Un codice è la parola del programma**: l'effetto sul
mondo ELA non lo vede, e un piano che lo vuole aggiunge uno step che legge il mondo. «Se esegue
codice, deve eseguire test» (§63) diventa un `terminal.run` di `pytest` con
`terminal.exit_code_matches`: i test sono il verifier del codice, non il terminale.

**Un programma sparito dopo l'esecuzione non si può verificare, e il verifier lo dice** (review di
M13.2, decisione 4). `terminal.program_unchanged` rilegge il disco; se il file non c'è più — un
disinstallatore si cancella da sé — il fallimento è `terminal.program_gone`, e la frase dice che cosa
ha potuto verificare e che cosa no: non c'è niente con cui confrontare il file dell'avvio, quindi ELA
**non può confermare che il programma eseguito fosse quello dichiarato**, e ciò che ha stampato sta
nel risultato. **Il passo finisce `FAILED`**, `verification.failed` con quel codice, **non
ritentabile**; il risultato del tool resta `SUCCEEDED`, con la sua uscita. **È la risposta onesta**:
«completato» affermerebbe un'identità che nessuno può più controllare; «ritentabile» chiederebbe di
rieseguire un'azione `HIGH`, che è una domanda nuova, e senza il file non partirebbe comunque; e
`FAILED` non dice che il comando non sia avvenuto — il risultato lo mostra —, dice che ELA non lo
può garantire. Ogni problema del programma ha il suo codice anche qui: `terminal.no_program` per un
file che c'è ma non si esegue o non si legge, `terminal.not_declared` per un programma che la tabella
dell'avvio non conosce.

Tool aggiunti:

| Capability | Tool | Nome | Idempotente | Codici d'errore | Numeri nell'audit |
|---|---|---|---|---|---|
| `terminal.run` | `TerminalRunTool` | `terminal-run` | no | `arguments.invalid`, `terminal.not_declared`, `terminal.no_program`, `terminal.program_changed`, `terminal.program_gone`, `terminal.arguments_unpassable`, `terminal.cwd_not_a_folder`, `fs.no_root`, `path.invalid`, `path.outside_root`, `path.symlink`, `path.unreachable`, `path.missing`, `terminal.not_started`, `terminal.timeout`, `terminal.stopped` | `argument_count`, `exit_code`, `signal`, `stdout.shown`, `stdout.total`, `stderr.shown`, `stderr.total` |

### 10. I numeri di un comando entrano nell'audit: un canale nuovo dell'audit, e solo interi

**Un canale nuovo dell'audit**, e si nomina come tale perché è la prima porta da cui un tool scrive
fatti suoi in un log che non si redige. **Perché**: la domanda di §32 — che cosa è successo, con quale
esito — per un comando ha una risposta fatta di numeri (quanti argomenti, quale codice o segnale,
quanti byte per flusso), e nessun campo fisso di `TOOL_EXECUTED` li porta; metterli nel sommario o in
un messaggio sarebbe aprire una porta al testo. **Le condizioni**, decise alla ripresa: le chiavi le
dichiara il tool (`audit_numbers`, senza default, come `idempotent`), sono percorsi nel suo risultato
la cui radice sta fra le sue `output_keys` — `ToolRegistry` rifiuta il silenzio e una chiave fuori —,
e i valori passano da **una funzione sola**, `ela.ports.audited_numbers`, che lascia passare **solo
interi** e `None`: una stringa, un numero decimale, un booleano sono un `ValueError` che nomina la
chiave e il tipo, mai il valore. La funzione si legge dove un risultato nasce — un tool di questa
macchina che ne produce uno fallisce con `tool.audit_number_invalid` e senza uscita; una consegna di
un nodo è un `422` — e dove `TOOL_EXECUTED` si scrive, sotto la chiave `numbers`;
`tests/architecture/test_terminal_rules.py` rifiuta un payload i cui numeri vengano da altrove.
**`fs.read` non lo adotta** in questa milestone: la sua dimensione sta nel risultato (ADR 0046 §6).
Chi vorrà farci passare una stringa dovrà riaprire questa decisione.

`asked` resta fuori dall'audit, e lo tiene così un test: nessun modulo che costruisce un `AuditEvent`
legge `ASKED`. Gli argomenti di un comando stanno lì — nella tabella delle approvazioni, che non è
l'audit e non si redige nemmeno lei — e **non** nel prompt, che entra in `APPROVAL_REQUESTED`.

### 11. Il non-viaggio si afferma

`TerminalRunVerifier` dichiara `reads_the_machine = True`: `terminal.program_unchanged` legge il disco
del Core, e su un nodo confronterebbe il `/usr/bin/git` del Core con un comando girato altrove — il
falso positivo di ADR 0038 §14. L'orchestratore rifiuta un nodo che non è `local` con
`UNVERIFIABLE`, e un test lo afferma.

### 12. La domanda, e una resa visibile sola per tre superfici

La domanda di un comando porta il programma per esteso, **l'etichetta del bersaglio scritta dal
tool** (`program`; `file` per `fs.*` — nessuna superficie possiede una parola che un'altra capability
possa ereditare falsa), il file a cui porta, gli argomenti **come lista i cui confini si vedono**, la
cartella risolta, il timeout e il codice atteso. Stanno in `asked`, i campi di `Asked` li contengono e
quelli di `ApprovalOut` contengono `Asked`: un contenimento affermato da un test, perché un campo non
ridichiarato sparirebbe dal filo in silenzio. La regola H di ADR 0045 §11 vale sulle tre superfici
che rispondono. `terminal.run` non ha una vista propria: il Command Center non mostra il contenuto di
un risultato (ADR 0044 §5).

**La resa visibile vive in un punto solo**, `ela.domain.visible` (con `listed` per le liste): i
controlli C0 e C1 e DEL, i controlli bidirezionali, i caratteri a larghezza zero e la barra rovesciata
diventano caratteri che si leggono; nella domanda anche a capo e tabulazione. La chiamano la riga di
comando, il Command Center e il companion, e un test rifiuta una superficie che non lo fa e un modulo
che ne tiene una copia. Il `--json` sfugge anche C1 e DEL. **Corretto implementando**: la SPEC metteva
la funzione in `ela.api`, sulla premessa che la CLI importi già l'API; la regola 28 lo vieta a ogni
modulo della CLI tranne `serve.py`, e `ela.domain` è la foglia che tutte e due importano.

### 13. Il lanciatore condiviso, riparato per tutti i chiamanti

Il terminale è il primo chiamante che crea nipoti, e due difetti misurati del lanciatore di tutti si
riparano qui, una volta per tutti (il precedente di ADR 0033 §8): **l'attesa dopo l'uccisione ha un
limite**, e passato il limite le pipe si chiudono da questa parte invece di aspettarne la fine — è il
caso che mancava al meccanismo dell'attesa di **ADR 0040 §5**: un nipote che tiene la pipe teneva
fermo `spawn` quanto viveva —; e **`TIMED_OUT` ha un valore che nessun segnale può produrre**
(`-65536`), perché con `-1` un figlio ucciso da `SIGHUP` si leggeva come uno scadere. Il port del
lanciatore del terminale è `CommandLauncher`:

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `CommandLauncher` | §18 | async | `run` |

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ToolPort` | §18, §32 | async | `audit_numbers` |

Il rivelatore della regola 32 si è allargato prima del codice che l'avrebbe messo alla prova —
`asyncio.subprocess.create_subprocess_exec`, `subprocess_exec` del loop, le famiglie `exec` e `spawn`,
`pty`, `multiprocessing` — con un caso negativo per grafia.

**Il debito di Windows è di M13.3.** Sul nodo del PC il meccanismo non è un gruppo di processi ma un
Job Object — ADR 0040 §5 dice già che `TerminateProcess` non uccide ciò che sta sotto —, e un `argv`
lì diventa una stringa sola (`list2cmdline`): il criterio 1 di M13.2 smetterebbe di essere vero. La
prima milestone che porterà il terminale su un nodo, M13.3, lo paga; il job `windows-latest` oggi non
fa girare `test_spawn.py`. Il Core però si costruisce anche lì, nella suite di conformità: il limite
di ciò che un lancio passa a un programma si sceglie nominando il sistema (`argument_limits`, un `if`
per sistema come il lettore dell'alimentazione), perché `os.sysconf` su Windows non c'è.

### 14. Una citazione corretta

`docs/adr/0045-filesystem-and-high.md:140`, in §4, attribuisce ad ADR 0038 §16 la frase «il rischio sta
nella capability e mai negli argomenti». **ADR 0038 §16 non la contiene**: il suo «livello» è la
sensibilità del task, dichiarata alla creazione. La regola per il rischio e lo scope è di **ADR 0026
§7** — «tutto ciò che la policy legge viene dal catalogo». ADR 0045 è immutabile: questa riga la
corregge, e con lei la docstring di `fs_read` e le righe di M13.1 che la ripetevano, annotate.

### 15. Righe riviste

Un ADR accettato non si riscrive: le righe qui sotto si leggono con questo accanto, e la riga «Stato:»
di ciascuno lo dice.

- **ADR 0045 §6-bis** — «sul disco di adesso»: per un comando, «per tutto ciò che si può sapere senza
  lanciarlo» (§5).
- **ADR 0045 §4** (`:140`) — la citazione di ADR 0038 §16 si legge ADR 0026 §7 (§14).
- **ADR 0029 §14** — «il numero si misura»: per un terminale si misura il tempo per svuotare il gruppo
  (§7).
- **ADR 0040 §5** — il meccanismo dell'attesa: il caso del nipote che tiene la pipe è riparato (§13).
- **ADR 0038 §11** — il segnale di fermata diventa un evento di `Ela`, letto anche dal lanciatore (§7).

### 16. Un debito datato: il surrogato isolato fuori dal piano

**Debito a carico di M13.3**, dichiarato il **2026-09-24**, dalla review di M13.2.

Un surrogato isolato (`"\ud800"`) è una stringa per il parser JSON che FastAPI usa, e non è testo per
nessun altro: non si codifica, non si scrive, non si passa a un processo. Il piano lo rifiuta da
questa milestone (Conseguenze), e il testo di un task lo rifiuta già pydantic, che non accetta un
surrogato in un campo `str`. **Resta aperto l'unico altro corpo con JSON libero in ingresso: la
consegna di un nodo** (`WorkResultIn`, `output` e `node`). Visto il 2026-09-24 con l'API vera: una
consegna con un surrogato nell'`output` è un `422` che nasce dall'`UnicodeEncodeError` della
persistenza, non da una regola di ELA — e il messaggio riporta il carattere —; il passo resta
`EXECUTING`, e alla scadenza dell'assegnazione un tool ripetibile torna a un nodo, che consegna di
nuovo la stessa cosa. **Il task non finisce mai.**

**Non si ripara qui.** La consegna è il confine fra il Core e un nodo, e decidere che cosa il Core fa
di un risultato che non può conservare — un rifiuto con un nome suo, il passo che finisce invece di
tornare a un nodo, che cosa si dice al nodo — è la materia di **M13.3**, la milestone in cui
un'azione e il suo verifier girano sul nodo. `docs/milestones/M13.3.md` lo nomina fra ciò che deve
chiudere.

**La difesa più piccola**:
`tests/api/test_nodes_work.py::test_a_delivery_holding_a_lone_surrogate_is_still_refused_by_the_encoder`
afferma il difetto com'è. Il giorno in cui fallisce il debito si sta pagando: si scrive il pagamento
in un ADR, e il test si gira.

## Alternative considerate

- **I programmi a percorso assoluto nello scope** — avrebbero cambiato i quattro confronti che leggono
  uno scope e la loro grammatica. Scartata dalla review (decisione 3).
- **Un prefisso di `argv` nello scope, o una lista di interpreti** — incompleta dal primo giorno, e un
  confine che insegna che ciò che non c'è è sicuro. Scartata (decisione 2).
- **Negare per `Rule.SCOPE` un link dichiarato che porta fuori** — il Guardian avrebbe dovuto leggere
  il disco. Scartata alla ripresa (Domanda 1).
- **I numeri come campi fissi di `TOOL_EXECUTED`** — ogni capability nuova avrebbe cambiato lo schema
  del payload per tutte. Scartata alla ripresa (Domanda 2).
- **Tenere il rifiuto dell'interprete di ELA e del suo albero** — una porta chiusa fra molte aperte.
  Scartata (decisione 16, Domanda 3).
- **Fermare i comandi con la cancellazione della richiesta** — al primo Ctrl-C nessuno la cancella.
  Scartata implementando (§7).

## Conseguenze

- `ela.permissions` esporta `TERMINAL_RUN`, `terminal_run`, `UNDECLARED_PROGRAMS`,
  `DECLARES_AN_EMPTY_SCOPE`; `production_catalogue` prende `programs`.
- `ela.ports` esporta `CommandLauncher`, `Command`, `Captured`, `Ran`, `Ending`, `Invocation` e
  `audited_numbers`; `Target` ha `label`, `Prospect` ha `invocation`, `ToolPort` ha `audit_numbers`.
- `ela.domain` ha `CommandOutput`, `visible` e `listed`; e un `JsonMapping` accetta un valore già
  congelato — **un difetto trovato implementando**: `args` è il primo argomento di un piano che è un
  array, e un array congelato non passava da un modello all'altro. Prima il test che falliva.
- `ela.tools` ha `terminal.py`, `programs.py` e `TerminalRunVerifier`; ogni tool dichiara
  `audit_numbers`. `ela.infrastructure.machine` ha `ProcessGroupLauncher`. `Ela` ha `stopping`.
- `ela.composition` ha `TerminalSettings`, e `Settings.load()` legge tutte le sezioni prima di
  rifiutare: un `.env` senza le righe di due sezioni le sente nominare tutte.
- `ela init` tiene `ELA_TERMINAL_PROGRAMS` in `REQUIRED`, con l'esempio `[]`.
- **Un piano che porta un surrogato isolato è un `422`**, prima che si scriva niente: il parser di
  FastAPI legge `"\ud800"` come una stringa, e nessuno dopo di lui la sa codificare — non il
  percorso di un tool, non l'argomento di un processo, non la pagina del task. Accettato, lasciava il
  task `RUNNING` per sempre, ogni `run` un `422`; **il difetto era già di `fs.*`**, e l'ha trovato la
  rilettura sugli argomenti del terminale. Il rifiuto sta in `PlanIn` e `StepIn`, dove nascono gli
  argomenti; la grammatica dei percorsi e `terminal.arguments_unpassable` rifiutano anche loro,
  perché un tool non si fida del chiamante. Il testo di un task e gli altri corpi dell'API restano
  fuori da questo ADR.
- `ela.composition.system` ha `argument_limits` e `LINUX_PAGES_IN_ONE_ARGUMENT`: i due limiti di un
  lancio si scelgono nominando il sistema (§5, §13). `ela.tools` ha `ArgumentLimits` e
  `PROGRAM_GONE`; il tool, il verifier e la composizione confrontano i programmi con
  `asyncio.to_thread` (§4) — il primo `to_thread` del codice.
- Il debito datato di §16 è a carico di M13.3, e `docs/milestones/M13.3.md` lo nomina insieme al
  debito di Windows di §13.
- Le capability di produzione sono **undici**, e **quattro viaggiano, sette no**;
  le regole di architettura restano **cinquantasette** (le tre nuove di M13.2 sono test di
  `tests/architecture` con i loro casi negativi, fuori dal registro), i port sono **ventisette**, le
  rotte **quarantotto**. Questi conteggi di oggi vivono qui; gli ADR precedenti restano appuntati a
  ciò che videro.
- **Che cosa questa milestone non fa**: non porta il terminale su un nodo (M13.3), non costruisce le
  policy di §59, non porta il Planner, e non dà a `terminal.run` una vista propria.
