# 0048. L'azione che viaggia: il verifier dove avviene l'effetto, il battito di `local`, e il lock di un task senza fessura

- **Stato:** Accettata. SPEC di M13.3 decisa dall'utente il 2026-09-25, con le decisioni 1–13 della
  review. Si è scritta un pezzo per commit, nell'ordine della SPEC; l'esito della misura dei pesi
  (§13) e della deriva dell'orologio (§14) è scritto dopo la prova a mano del 2026-09-26, con i numeri
  presi.
- **Data:** 2026-09-25
- **Riferimenti spec:** §13, §15, §16, §17, §18, §23, §28, §32, §33, §56, §57, §63
- **Milestone:** M13.3

## Contesto

Fino a M13.3 un'azione dell'Action Core gira soltanto sul Core, e la divisione di ADR 0038 §14 —
**che cosa legge il verifier** — è l'unica risposta a «questa capability può viaggiare?». M13.3 fa
viaggiare `fs.read` e `fs.write` con il loro verifier sulla macchina dove l'effetto avviene, e paga
qui i debiti che la Fase 13 le ha affidato: il battito di `local` (ADR 0044 §8), i pesi di §17 e la
deriva dell'orologio (ADR 0043 §9), il surrogato isolato (ADR 0047 §16) e i test di Windows che
nessun job raccoglie (ADR 0047 §17).

Il censimento della SPEC ha trovato difetti che la registrazione non nominava, e questo ADR li scrive
nell'ordine in cui la milestone li ripara: prima quelli che un test mostra rossi sul codice di oggi.

## Decisione

### 1. Il lock di un task si prende senza niente in mezzo

`running_of` (`src/ela/api/deps.py`) promette che il controllo e l'inserimento del lock di un task
avvengano **senza un `await` in mezzo**. `run_task` rompeva la promessa: fra `identifier in running` e
`running.add` scriveva il battito di `local` e leggeva l'alimentazione, che su un Mac è un processo
`pmset`. Due `run` dello stesso task arrivati insieme — il sì dal telefono e un `ela task run` al Mac
— passavano tutti e due il controllo, ed era la corsa che i Rischi di M13.1b davano per fuori da ogni
configurazione dichiarata: **lo era, in una configurazione dichiarata**. Il test che lo mostra
(`tests/api/test_task_lock.py`) ferma la lettura dell'alimentazione dopo il controllo e manda il
secondo `run`: prima della riparazione rispondevano tutti e due `200`.

La riparazione: l'inserimento segue il controllo, e tutto il resto sta dentro il lock. **La regola che
la tiene** sta in `tests/architecture/test_travel_rules.py`, con i casi costruiti che la fanno
fallire: in ogni funzione di `ela.api` nessun `await` fra un controllo del lock e l'inserimento che lo
segue; e ogni rotta che arriva al runner, a `begin` o a `deliver` lo fa dentro il lock — anche
attraverso le funzioni di mezzo del modulo —, con l'eccezione voluta della consegna di un id che il
Core non ha mai coniato, che non ha un task da bloccare (ADR 0038 §12).

**ADR 0023 §9 — «due `run` sullo stesso task non si sovrappongono»** — era vera nell'intenzione e
falsa nel codice; si legge con questa sezione accanto.

### 2. Il debito di ADR 0044 §8, saldato: il battito di `local` lo scrive il Core, prima di ogni piazzamento e a un periodo

Il debito di ADR 0044 §8: il Mac risultava `available: false` mentre ELA girava, perché `local`
batteva solo all'avvio e all'inizio di ogni `run`. E il censimento ha trovato che non era soltanto
un'etichetta: il runner piazza ogni step di un giro senza battere, quindi uno step locale più lungo del
TTL del battito lasciava `local` scaduto per lo step dopo, **nello stesso `run`** — un task
`LOCAL_ONLY` tornava `QUEUED` con `WAITING_DEVICE` mentre il Mac era lì, e uno `TRUSTED` mandava lo step
dopo a un'altra macchina. Il test (`tests/executive/test_runner_heartbeat.py`) lo mostrava rosso: «no
eligible node among 1: 1 UNAVAILABLE».

**Un port, `LocalBeat`, e un servizio del Core che lo implementa**, `LocalHeartbeat` in `ela.devices`:

- **il runner chiede un battito prima di ogni piazzamento** — prima di `place` per uno step `PENDING`
  e prima di `confirm` per uno `RUNNING` —, così `local` è vivo per il registro ogni volta che il
  runner sta per sceglierlo, e l'alimentazione che il piazzamento pesa è letta **in quell'istante**:
  una credenza periodica non decide un'azione (ADR 0029 §7). Il runner riceve il port e non il
  servizio, e nei test il port si finge;
- **un ciclo a un periodo di un terzo del TTL** — 20 s col default, due battiti persi prima che il Mac
  risulti silenzioso —, un valore derivato e non una variabile nuova, che il lifespan avvia accanto
  alla percezione e lo spegnimento ferma. **Non decide niente**: tiene vero il Device Center fra un
  `run` e l'altro. Un battito che fallisce non ferma il ciclo; se il ciclo smette di battere, `local`
  scade, che è la diagnosi giusta;
- **il battito porta anche lo stato di `local`**, dalla review dell'implementazione (§13): `BUSY`
  mentre un tool è in corso su questa macchina, dall'avvio del tool al risultato registrato, altrimenti
  `IDLE` — la domanda la risponde l'executor, e il servizio la riceve dalla composizione come riceve la
  lettura dell'alimentazione; per questo il servizio si costruisce dopo l'executor;
- **la rotta smette di battere**, e il battito dell'avvio passa dal servizio: **fuori da
  `devices/beat.py` nessun modulo chiama `heartbeat` per `LOCAL_DEVICE_ID`**, e un test di
  architettura lo tiene, con il suo caso negativo.

**Non il tick della percezione**, che è spento di default: un battito che avesse bisogno della
percezione accesa farebbe sparire il Mac dal registro il giorno in cui l'utente la spegne. **E non il
muro del processo residente** (ADR 0029 §16, ADR 0039 §6): il ciclo vive dentro `ela serve`, che
l'utente ha già avviato in primo piano, e muore con lui.

**Che cosa cambia per un test.** Da M13.3 il nodo `local` non può più tacere sotto un giro del
runner. I test che provano che cosa fa il runner quando **nessun nodo è idoneo** — un ramo che resta
raggiungibile per un nodo che non è questa macchina, o per una capability che nessun nodo ha —
costruiscono la precondizione dichiarando un battito che non arriva al registro
(`ela.testing.fakes.FakeLocalBeat`), non aspettando che il TTL passi. Il test end-to-end che guardava
`local` tacere sotto un giro si è girato: ora afferma che non tace.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `LocalBeat` | §16 | async | `beat` |

### 3. Il debito di ADR 0047 §16, saldato: un risultato che non è testo chiude il suo step

Un surrogato isolato (`"\ud800"`) è una stringa per il parser
JSON che FastAPI usa, e testo per nessun altro. La consegna di un nodo lo accettava in ogni stringa —
`output`, `node`, `error.message` —, e la richiesta moriva in un `422` con il carattere nel messaggio;
il nodo, che legge un `422` come «il Core non ha deciso», teneva la busta e la riconsegnava finché la
scadenza non diventava un `410`, e alla scadenza un tool ripetibile tornava a un nodo: **il task non
finiva mai**.

**Una riga di ADR 0047 §16 si corregge.** Diceva che il `422` «nasce dall'`UnicodeEncodeError` della
persistenza». Nasceva prima: `Envelope.digest` serializzava con `ensure_ascii=False` e codificava in
UTF-8 stretto, prima di ogni scrittura (M13.3, C7).

**Il pagamento**, in tre parti:

- **un controllo solo**, `ela.domain.is_text`: lo leggono il piano, dove gli argomenti nascono, e
  l'executor **dove un risultato si conserva, qualunque macchina l'abbia prodotto**. La risposta di un
  fornitore che contiene `\ud800` — un JSON valido — è un produttore vero, e sul Core rompeva la
  persistenza come la consegna la rompeva sul filo: la parità di ADR 0038 §3 vuole la stessa risposta
  nei due posti;
- **l'impronta si calcola sempre**: `.encode("utf-8", "surrogatepass")` dà, per ogni busta di testo,
  gli stessi byte della codifica stretta — un test lo afferma su buste vere —, e per una busta con un
  surrogato un'impronta invece di un'eccezione;
- **il Core conia un risultato `FAILED` con `result.not_text`**, senza uscita, senza `usage`, e dei
  metadati solo ciò che il Core aveva scritto; il messaggio nomina i campi e mai il contenuto. Poi la
  seconda metà di sempre: `TOOL_EXECUTED`, lo step `FAILED`, e per una consegna l'assegnazione
  `DELIVERED`. **Al nodo si risponde `200`** (decisione 8): il Core ha deciso e ha scritto, e il nodo
  lascia la busta; una replica riceve la stessa risposta.

La difesa di ADR 0047 §16 si è girata: `tests/api/test_nodes_work.py` afferma il `200`, lo step
`FAILED` con `result.not_text`, un messaggio senza il carattere, e il task `FAILED` al `run` dopo.

**Fuori, e dichiarata**: l'annuncio di un nodo (`DeclarationIn`, il nome e i tool) è l'altra porta da
cui arrivano stringhe da un'altra macchina; un surrogato lì fa fallire l'annuncio, e il nodo non entra
— il verso fail-safe, e nessun task resta a metà.

### 4. I percorsi che Windows legge diversamente: una grammatica per ogni sistema

`fs.read` e `fs.write` viaggiano anche verso il PC (decisione 3): senza, l'azione che viaggia si
proverebbe sullo stesso disco del Core, cioè non si proverebbe. E sul PC un percorso che la grammatica
di M5.2 ammetteva poteva nominare un altro file. **Una grammatica per ogni sistema**, in
`ela.tools.paths`, e non un `if` per sistema: ciò che un sistema qualunque leggerebbe diversamente si
rifiuta ovunque, con `path.invalid`, prima della domanda sul Core e prima di agire sul nodo:

- **`:` in un componente** — su NTFS `nota.md:x` è un flusso alternativo di `nota.md`, e `C:x` una
  lettera di unità;
- **un componente che è un nome riservato di Windows**, con o senza estensione e anche con uno spazio
  prima del punto: `RESERVED_ON_WINDOWS`, la tabella di `ntpath` di CPython 3.13 — `CON`, `PRN`, `AUX`,
  `NUL`, `CONIN$`, `CONOUT$`, `COM` e `LPT` con una cifra da 1 a 9 o con `¹`, `²`, `³` —, più `COM0` e
  `LPT0`, che la documentazione di Microsoft elenca;
- **un componente che finisce con un punto o con uno spazio**, che Windows toglie.

**La tabella è una copia, e sa accorgersi di diventare falsa**: Python 3.12 non ha
`ntpath.isreserved`, e `tests/tools/test_paths.py` afferma che non c'è — il giorno del passaggio a
3.13 fallisce. **La sostituzione non sarà a scatola chiusa**: `ntpath.isreserved` non ha `COM0` e
`LPT0`, e rifiuta anche `*?"<>|` e i caratteri di controllo, un secondo restringimento del Mac. Quel
giorno la copia si confronta con la funzione, e ciò che cambia si dichiara.

**Una giunzione è un link**: la camminata di `classify` chiede `is_junction()` accanto a
`is_symlink()`, su ogni sistema — su POSIX risponde sempre no, e su Windows `is_symlink()` una giunzione
non la vede. Una giunzione che portava dentro la radice passava, dove un link simbolico no.

**Il Mac si stringe, e lo si scrive**: un nome con `:` o che finisce con un punto, legale su macOS, da
M13.3 è rifiutato ovunque — per `fs.*`, per le note, che condividono la grammatica, e per la cartella di
un comando, che la classifica con la stessa `classify`. La frase del rifiuto nomina ciò che è
rifiutato. Nessun esempio e nessun piano del repository usava un nome così.

**Restano dichiarati**: il confronto dello scope distingue le maiuscole e NTFS no — un percorso scritto
con maiuscole diverse dallo scope è negato, il verso fail-safe —, e su Windows non c'è `O_NOFOLLOW`,
quindi la finestra di ADR 0045 §7 lì è più larga.

**E i byte, su Windows** — trovato dalla rilettura dell'implementazione, prima della prova a mano, e
misurato dal job di Windows (run `36162668652`, 2026-09-25): senza `O_BINARY` un `os.open` di Windows
apre in modo testo, e **una lettura riceve altri byte da quelli del disco** — `a\r\nb\x1ac` diventava
`a\nb`, il ritorno a capo tolto e tutto ciò che segue un `0x1A` perso —, e il verifier, che legge allo
stesso modo, non vedeva il `\r` che il piano non aveva: `fs.read` e il suo verifier si sarebbero dati
ragione su un contenuto che il disco non ha, il falso positivo di ADR 0038 §14 proprio sulla macchina
dove M13.3 manda `fs.*`. La scrittura, misurata, era già giusta; il flag c'è anche lì, perché il modo
lo decide `os.open` e non chi scrive dopo. I flag di `fs.*` e del verifier portano `O_BINARY` (che
altrove non esiste, ed è `0`), e `tests/tools/test_fs_windows.py` guarda i byte sul disco, non il
testo riletto.

**Che Windows legga davvero così** lo mostra un modulo che gira solo lì,
`tests/tools/test_paths_windows.py`: una giunzione vera, un flusso alternativo vero, un punto in coda
tolto davvero — prima il fatto di Windows, poi il rifiuto. Il job `windows-latest` lo raccoglie (§5).

### 5. Il debito di ADR 0047 §17, saldato: i test di Windows nel job, o la ragione per cui no

Il job `node-windows` raccoglieva `tests/node`, `tests/conformance` e
`tests/composition/test_build_node.py`, e i test riservati a Windows stavano fuori: nessun job della CI
li eseguiva mai.

**Il pagamento**:

- **entrano nel job, per nome**, `tests/infrastructure/machine/test_acl_smoke.py`,
  `tests/infrastructure/machine/test_power_smoke.py`, `tests/tools/test_paths_windows.py` e
  `tests/tools/test_fs_windows.py` (§4) — i due smoke dopo il giro che racconta il paragrafo sotto;
- **chi resta fuori lo dice in un posto che un test legge**: `tests/windows.py`, una mappa file →
  ragione. Oggi ha una voce, `test_sapi_smoke.py`, con la ragione che la sua docstring già scriveva: un
  runner non ha altoparlanti;
- **la difesa di ADR 0047 §17 si è girata**:
  `tests/docs/test_adr_terminal.py::test_every_test_of_windows_is_in_the_job_or_says_why_not` ricava
  dalla suite ogni file con uno `skipif` riservato a Windows, e afferma che ognuno o sta nella riga del
  job o sta nella mappa — l'uguaglianza fallisce anche per una voce della mappa che non è più riservata
  a Windows, o che il job ora nomina. Il suo caso negativo è costruito su una suite finta.

**Il primo run del job è stato la misura** (run `36151577468`, 2026-09-25). La giunzione, il flusso
alternativo e il punto in coda sono passati su NTFS vero. **I due smoke no, e non per le ragioni che
la SPEC immaginava** — l'utente del runner, una macchina virtuale —: la shell del job è PowerShell 7,
e il `powershell.exe` 5.1 che i test e ELA lanciano ne eredita il `PSModulePath`, e non carica i
propri moduli — «The 'Get-Acl' command was found in the module 'Microsoft.PowerShell.Security', but
the module could not be loaded» —; `power_status` ha risposto `None`. Per un giro sono stati nella mappa, con questa ragione.

**Ma la misura diceva una cosa sul prodotto, non sul runner**: un nodo lanciato da PowerShell 7 lancia
i suoi `powershell.exe` nello stesso ambiente, e sul PC l'alimentazione risultava `UNKNOWN` e la voce
SAPI falliva. Le prove a mano di M12.4 erano passate perché il nodo girava in Windows PowerShell 5.1.
**Riparato da M12.3d** (`docs/milestones/M12.3d.md`), per la decisione 1 della review
dell'implementazione: i `powershell.exe` di ELA partono con l'ambiente del nodo meno `PSModulePath`, e
Windows PowerShell 5.1 calcola il suo. I due smoke sono tornati nella riga del job, sotto la stessa
shell PowerShell 7: rossi prima della riparazione (run `36164151413`). Dopo, l'ACL è passato; la
lettura dell'alimentazione ha mostrato una ragione sua, misurata e non supposta (run `36178451554` e
`36178717970`): `power_status` dà `None` dopo 5,01 s — la prima PowerShell del runner, a freddo, supera
il tetto di 5 s di ELA —, e lo stesso script subito dopo risponde `Online` e `0` in 2,91–3,03 s. Il
tetto è quello del PC, misurato da P6 in 0,25–0,4 s, e resta il prodotto; **lo smoke aspetta un
minuto**, con il lanciatore e l'ambiente di ELA, e afferma ciò che dice: la forma della risposta, cioè
la riparazione (decisione dell'utente, 2026-09-25). La guida non dice più da quale shell lanciare il
nodo; dice di controllare che il PC risulti `AC`.

### 6. Ripiazzabile: la dichiarazione, e il secondo predicato di ADR 0038 §8

`fs.read` è idempotente: rileggere lascia il disco com'era. Alla presa di un nodo la `STARTED` si
scriveva solo per un tool non idempotente, quindi **una `fs.read` reclamata e scaduta sarebbe stata
rilasciata e ripiazzata** — anche su un'altra macchina, dove lo stesso percorso è un altro file.
È l'avvertimento di ADR 0038 §8 per la nota, e il test che quell'avvertimento aveva messo di guardia
non l'avrebbe visto: calcolava «viaggia» da `reads_the_machine`, e `fs.*` continua a leggere la
macchina.

**Un membro nuovo di `ToolPort`, `relocatable`**, senza default, nella forma di `idempotent` e di
`audit_numbers`: *il lavoro di questo tool, preso da un nodo che poi tace, si può rifare su un'altra
macchina senza che cambi che cosa significa e senza raddoppiarne l'effetto.* `ToolRegistry` rifiuta
con `RelocationError` un tool muto, e `relocatable` vero accanto a `idempotent` falso — ciò che non si
può rifare qui non si rifà altrove. I due rifiuti non hanno un produttore in produzione, come
`SilentVerifierError`: valgono per il loro caso negativo, costruito con un tool finto
(`tests/tools/test_relocatable.py`). **Il nome è `relocatable`** (decisione 4): `replaceable` si
leggerebbe «sostituibile».

**I valori**: `core.echo` sì; **ogni altro no**. `fs.read` è quello che rende la dichiarazione una
dichiarazione e non un sinonimo: idempotente sulla sua macchina, un altro file su un'altra.

**Il predicato**: alla presa la `STARTED` si scrive per un tool **non ripiazzabile**. Nel percorso
locale non cambia niente: lì la `STARTED` difende dal crash della stessa macchina, e resta legata a
`idempotent`. **ADR 0038 §8 si legge con questa riga accanto**: *reclamata e scaduta ⇒ un tool non
ripiazzabile si chiude `interrupted`, uno ripiazzabile si ripiazza.* **E ADR 0021 con la stessa
riga**: la `STARTED` di una presa non dice più «un tool che non si può rifare», ma «un lavoro che non
si può spostare». La frase di `execution.interrupted` diceva «it cannot be repeated», falso per una
`fs.read` interrotta; ora dice «it is not run again, here or on another machine».

**La guardia di ADR 0038 §8 si è riscritta, e non si è allentata**, e ha cambiato casa:
`tests/docs/test_adr_travel.py` chiede all'orchestrator stesso quali capability F7 lascia andare — il
verifier non legge la macchina, e da §7 anche un verifier che un nodo porta —, e afferma che
«viaggia ∩ ripiazzabile» è `{core-echo}`; il suo caso negativo vede un tool ripiazzabile in più.
**La condizione d'ingresso di M13.6 resta non soddisfatta** — un solo ripiazzabile che viaggia —, e
M13.6 resta `Proposta`: la sua registrazione diceva «dichiarano la propria idempotenza», e
`docs/milestones/M13.6.md` è annotata, perché la dichiarazione che conta è `relocatable`.

**Nei test**, `FakeTool.relocatable` segue `idempotent` finché un test non lo imposta: era l'unico
predicato che la presa leggesse prima di M13.3, e un test che spegne `idempotent` dopo aver costruito
il suo mondo continua a voler dire ciò che diceva.

`ToolPort` è esteso con `relocatable`: la tabella dei port estesi è una, nelle Conseguenze.

### 7. Il verifier dove avviene l'effetto: `fs.read` e `fs.write` su un nodo che ha una radice

La divisione di ADR 0038 §14 resta vera di ciò che descrive — **che cosa legge il verifier** — e smette
di essere l'unica risposta a «questa capability può viaggiare?». Da M13.3 le risposte sono tre:

1. il verifier **non legge la macchina** — eco, modello, voce: viaggia, e il Core verifica la parola del
   nodo, come da M12.2;
2. il verifier **legge la macchina, e un nodo lo porta con sé** — `fs.read`, `fs.write`: viaggia, e
   **il nodo verifica** sulla propria macchina; il Core registra il verdetto e dove è stato preso;
3. il verifier **legge la macchina, e nessun nodo lo porta** — `workspace.write_note`, `perception.*`,
   `terminal.run`: non viaggia, e un nodo è rifiutato con `UNVERIFIABLE`, come prima.

`reads_the_machine` non cambia né di nome né di valore: `fs.*` continua a leggere la macchina, ed è per
questo che il verifier deve stare lì.

**La radice di un nodo.** `ELA_FS_ROOT` nel `.env` del nodo, **facoltativa e sola**: sul Core la stessa
variabile è obbligatoria insieme allo scope, sul nodo lo scope non c'è, perché resta uno, dell'utente,
sul Core, e il nodo non ha un Guardian e non ne guadagna uno. Le regole della radice sono quelle del
Core (ADR 0045 §5), **con un testo solo** (`refuse_the_root`) e un elenco derivato da ciò che **il
nodo** usa per esistere: la cartella del segreto (ADR 0039 §6), il `.env` letto, l'albero sorgente. Una
radice che è un link è rifiutata, **e una giunzione è un link** (§4): `is_symlink` una giunzione non la
vede, e la rilettura dell'implementazione l'ha trovato. Un
nodo con una radice costruisce i due tool e i loro verifier (`node_tools`, `node_verifiers`) e li
dichiara; uno senza non costruisce niente, riceve `MISSING_TOOL` da F4, e `ela node run` lo dice con una
riga. `build_node` rifiuta un tool da verificare sul nodo senza il suo verifier (`carried`): in
produzione non scatta, e vale per il suo caso negativo. Guarda l'insieme di `VERIFIED_ON_THE_NODE`, e
non ogni capability il cui verifier legge la macchina: un tool di un'altra di quelle il nodo non lo
costruisce, e se lo costruisse F7 lo terrebbe comunque sul Core.

**F7 legge un insieme in più.** `verified_here` era «il verifier legge la macchina»; è **«il verifier
legge la macchina, e nessun nodo lo porta»**. L'insieme è una costante di `ela.tools`,
`VERIFIED_ON_THE_NODE`, e la composizione la passa all'orchestratore accanto al registro dei verifier;
`node_verifiers` costruisce i due verifier per nome, e un test (`tests/composition/test_build_node.py`)
tiene uguali la costante e ciò che il nodo costruisce. **Perché non una dichiarazione del nodo**, con una
colonna nel registro: un nodo che dichiara il tool e non il verifier non ha un produttore, e il rifiuto
che quella colonna farebbe scattare non scatterebbe mai (ADR 0026 §7). Il Core sa quali verifier un
nodo porta perché è lo stesso codice, come sa i nomi dei tool.

**L'ordine porta le condizioni, e ADR 0038 §11 si legge con questa riga accanto.** «E nient'altro»
resta vero per ogni capability che il Core verifica da sé; per una che il nodo verifica l'ordine ha
una settima chiave, `success_conditions`, e per le altre la chiave **manca**, non è vuota.

**Il nodo verifica dopo il tool e prima di consegnare.** Il verifier si cerca **prima** che il tool
agisca — un nodo non agisce su ciò che non sa verificare — e gira dopo, su un risultato riuscito, con le
condizioni e gli argomenti dell'ordine. Il verdetto entra nella busta: le condizioni controllate,
nell'ordine; quelle che non valgono, ciascuna con il suo **codice**; oppure il **nome** del tipo
dell'eccezione del verifier. **Mai un messaggio**: la frase che finisce in `EXECUTION_VERIFIED` la
compone il Core dal codice, perché il testo di un'altra macchina — che può nominare un percorso, cioè
il contenuto dell'utente — non entri in un log che non si redige (§57). **Il verdetto entra
nell'impronta**, e solo quando c'è: due buste che differiscono solo nel verdetto sono una consegna in
conflitto, e l'impronta di ogni busta senza verdetto è quella di prima.

**Il Core registra il verdetto e non lo rifà.** Per un risultato di un nodo il cui verifier legge la
macchina il Core prende il verdetto conservato con il risultato (`metadata["verdict"]`) invece di
chiamare il proprio verifier, **alla consegna e in ogni ripresa**: una morte fra il risultato e
`EXECUTION_VERIFIED` si ripara con il verdetto conservato, mai rileggendo il disco del Core — sarebbe il
falso positivo di ADR 0038 §14 dalla porta di servizio. `EXECUTION_VERIFIED` porta `verified_on`, il
nodo che ha verificato; senza quella chiave ha verificato il Core, come sempre.

**Ciò che il Core prova ancora**: che il verdetto nomini **esattamente** le condizioni del piano,
nell'ordine, e che i suoi codici stiano nel vocabolario del verifier (ADR 0014 §2), che per questo
entra nel port: `VerifierPort.failure_codes`. Un verdetto che manca, che nomina altre condizioni, che
fallisce due volte la stessa, o con un codice o una forma fuori posto, per un risultato `SUCCEEDED`, **è
un dubbio**: lo step fallisce `verification.failed` con un fallimento solo, `verification.missing` —
dentro la tabella di ADR 0014 §4 e non accanto —, e il task con lui. I fallimenti che il Core compone
da un verdetto non sono `retryable`: il Core ha solo la parola del nodo. Un risultato che non è
`SUCCEEDED` non porta verdetto, e una busta che ne porta uno è un `422`; lo è anche un verdetto per una
capability che il Core verifica da sé, prima di ogni scrittura.

**Un verdetto che non è testo** è un risultato che non si può conservare (§3): `result.not_text`, con
`verdict` fra i campi nominati.

**Il contratto ha una quattordicesima storia**, `what_is_verified_on_the_node_is_verified_there`
(`tests/conformance/test_node_contract.py`), recitata dal nodo finto e dai due reali: un file scritto
sulla radice del nodo e non su quella del Core supera la verifica; un `fs.write` del nodo che risponde
`SUCCEEDED` senza scrivere, con lo stesso file sulla radice del Core, non la supera — il falso positivo
di ADR 0038 §14 nei due versi —; e un nodo che consegna senza il verdetto non è creduto. ADR 0038 §18,
«tredici storie», si legge con questa riga accanto.

`VerifierPort` è esteso con `failure_codes`, nella tabella delle Conseguenze.

### 8. La domanda di uno step su un nodo: ciò che il piano afferma, e che ELA non ha guardato quel disco

La domanda di un `fs.*` si componeva con il `prospect` del tool **del Core**, sulla radice **del
Core**: per uno step piazzato sul PC avrebbe detto il file del Mac, e se sul Mac c'è — un fatto vero di
un'altra macchina, cioè la diagnosi falsa di ADR 0045 §5 nella frase su cui si regge un sì `HIGH`.

**La domanda nomina ciò che il piano afferma, e il nodo lo fa valere** (decisione 1). Per uno step
piazzato su un nodo il cui verifier legge la macchina l'executor non chiede al tool del Core che
cosa c'è sul disco, ma **che cosa la chiamata afferma**: un membro nuovo di `ToolPort`, `asserted`,
accanto a `prospect` che guarda. Per `fs.write` l'`overwrite` del piano, nelle parole del tool —
«creates a new file: the plan says nothing is there», o «overwrites a file: the plan says one is
there» —; per `fs.read` che il file c'è. I controlli che non leggono un disco restano **prima** della
domanda: lo scope, nel Guardian; la forma degli argomenti e la grammatica di §4, che è pura. La domanda
porta anche **la macchina**, con il nome che il nodo ha scelto — può cambiare a ogni annuncio e non è
unico — e l'inizio dell'id che il Core ha coniato (decisione 10), e **la frase di ciò che ELA non ha
fatto** (`UNSEEN`): non ha guardato quel disco, e il nodo rifiuta prima di agire se il disco dice
altro. `Asked` ha `machine` e `unseen`; le tre superfici che rispondono le mostrano come stanno, e il
test che tiene ogni campo di `Asked` alle tre superfici (`tests/api/test_answering_surfaces.py`) lo
ha verificato da sé. **Per uno step su `local` la domanda è quella di prima, byte per byte**: nessuna
delle due chiavi entra nella borsa, e la riga della macchina e quella del disco mancano.

**Perché regge.** La proprietà su cui ADR 0045 §6-bis si appoggia è che *l'asserzione del piano è il
fatto approvato, e il tool la riconfronta con il disco prima di scrivere*. Sul nodo resta vera alla
lettera, perché il tool del nodo è questo codice: `_look` gira dentro `_run`, e
`fs.overwrite_mismatch` rifiuta nei due versi. **Nessun sì produce un effetto diverso da quello che
la domanda dice**, fuori dalla finestra fra `classify` e `open` che ADR 0045 §7 dichiara già — più
larga su un nodo Windows, dove `O_NOFOLLOW` non c'è. Il rifiuto dopo il sì dice **quale fatto** il
disco ha smentito, con un codice: `fs.overwrite_mismatch` con la frase di ADR 0045 §6-bis, `path.missing`
per una lettura, `path.symlink` per un link o una giunzione.

**Che cosa si perde, e ADR 0011 §3 e ADR 0045 §6 e §6-bis si leggono con questa sezione accanto per
uno step su un nodo.** «A un utente non si chiede di approvare ciò che sarebbe negato comunque»: per
uno step su un nodo la domanda **può nascere già condannata** — un file che c'è dove il piano ne
dichiara uno nuovo si scopre dopo il sì, e il sì è speso. È il difetto che la prova a mano di M13.1
aveva trovato e che ADR 0045 §6-bis aveva chiuso sul Core; qui torna per un nodo, e lo si dice con il suo
nome. **Ogni domanda già condannata finisce senza effetto: il costo è un sì speso, mai un effetto
diverso da quello approvato.** E la domanda nomina il percorso **scritto**, non quello risolto, e non
dice se attraversa un link, che il nodo rifiuta comunque.

### 9. Un debito datato: il terminale su un nodo, ridichiarato

**Debito a carico di M13.7**, dichiarato il **2026-09-25**, dalla review della SPEC di M13.3 (vincolo 2
e decisione 6).

ADR 0047 §13 diceva «il debito di Windows è di M13.3»: sul PC il gruppo di un comando è un Job Object
e non un gruppo di processi, e un `argv` diventa una stringa sola (`list2cmdline`), e il criterio 1 di
M13.2 smetterebbe di essere vero. **Il terminale non viaggia in M13.3**: nessuna voce dell'eredità lo
chiede, l'obiettivo è soddisfatto senza, e il suo verifier legge l'identità dei programmi **sul disco
del Core** — `terminal.run` non è in `VERIFIED_ON_THE_NODE`, e un nodo è rifiutato con `UNVERIFIABLE`.
La proprietaria è **M13.7 — il terminale su un nodo** (`docs/milestones/M13.7.md`), `Proposta`, in coda
alla Fase 13 dopo M13.5. ADR 0047 §13 si legge con questa sezione accanto.

**La difesa più piccola**: `tests/devices/test_terminal_stays.py` afferma che un comando resta sul
Core e che il nodo costruito per vincere è rifiutato `UNVERIFIABLE`, e `tests/docs/test_adr_travel.py`
che `terminal.run` non è fra le capability che un nodo verifica. Il giorno in cui fallisce, il debito si
sta pagando.

### 10. Un debito datato: il residuo di Linux del terminale, ridichiarato

**Debito a carico di M13.7**, dichiarato il **2026-09-25**, dalla review della SPEC di M13.3 (decisione
5), **come criterio a sé**.

ADR 0047 §5 lasciava il residuo di Linux — il kernel conta il percorso del programma una volta in più e
tetta il totale a tre quarti di `_STK_LIM`, quindi un comando al limite del conto di ELA può essere
rifiutato dopo il sì — a «il giorno in cui viaggerà su un nodo Linux la misura si prende lì (M13.3)».
**Nessuna macchina di ELA esegue il terminale su Linux**, e la sua precondizione — un kernel Linux che
esegue il terminale — non è quella del Job Object: per questo è un criterio a sé della stessa
proprietaria, e non una riga del debito di §9. `docs/milestones/M13.7.md` lo porta fra ciò che eredita.

**La difesa più piccola**: `tests/docs/test_adr_travel.py` afferma che M13.7 lo nomina con ADR 0047 §5,
e che un nodo Linux non riceve `terminal.run` per la stessa ragione di §9.

### 11. Le quattro risposte di §57, per un file su un nodo

Nella forma di ADR 0038 §16:

| Domanda | Risposta |
|---|---|
| **Quale nodo** | quello che il piazzamento ha scelto e la domanda nomina; lo stesso fino alla fine dello step, perché uno step `RUNNING` non si ripiazza; e uno rilasciato rifà la domanda, perché ogni grant di `fs.*` nasce da un sì ed è monouso (ADR 0045 §4), e si è speso prima dell'offerta |
| **Quale tipo di dati** | per `fs.write` il corpo del file, dal Core al nodo, negli argomenti dell'ordine; per `fs.read` il contenuto del file, dal nodo al Core, nella busta e poi nel risultato — mai nell'audit, come prima; e il verdetto, dal nodo al Core, fatto di condizioni e codici e mai di frasi |
| **Perché viene inviato** | perché l'orchestratore ha scelto quel nodo, e `DEVICE_SELECTED` lo registra con i punteggi e i rifiuti di ogni candidato |
| **Quale policy lo consente** | la sensibilità del task, dichiarata alla nascita, contro il tetto del nodo, imposto all'arruolamento; e il sì dell'utente a una domanda che nomina la macchina |

**Il limite si scrive**: `ELA/prova.md` è un file sul Mac e un altro sul PC, e il piazzamento sceglie
per punteggio; un task `TRUSTED` legge o scrive il file della macchina che vince, e l'utente lo vede
nella domanda. È una scelta a occhi aperti, e la sua proprietaria è **M13.8 — un file che vive su una
macchina** (`docs/milestones/M13.8.md`).

### 12. Che cosa smette di essere provato quando il verifier gira sul nodo

Nella forma di ADR 0038 §14, per le due capability che viaggiano da M13.3. La riga «da lontano» di
ADR 0038 §14 diceva che cosa si prova quando **il Core** verifica la parola del nodo; qui verifica **il
nodo**:

| Capability | Il verifier legge | Dal nodo prova | Dal nodo non prova | Legge la macchina |
|---|---|---|---|---|
| `fs.read` | il disco del nodo, sul nodo | che il nodo dice di aver riletto, al percorso sotto la sua radice, i byte che il risultato porta, per le condizioni che il piano chiedeva | che il file ci sia davvero; che la radice sia quella che l'utente ha scritto nel `.env` del nodo; che a verificare sia stato il codice del Core e non un altro; che il verifier abbia riletto il disco invece di ricopiare il risultato | `True`, del nodo |
| `fs.write` | il disco del nodo, sul nodo | che il nodo dice di aver riletto, al percorso, i byte che il piano chiedeva di scrivere | le stesse quattro cose; che il nodo abbia riconfrontato l'`overwrite` del piano con il disco prima di scrivere — la cosa su cui la domanda di §8 si regge —; che il percorso sotto la radice non abbia attraversato un link o una giunzione; che il verifier sia girato dopo il tool; che il tool non abbia scritto nient'altro; che il file non sia cambiato fra la verifica e la consegna | `True`, del nodo |

**Che cosa il Core prova ancora**, e non è poco: che il verdetto viene dal nodo a cui il lavoro era
affidato, autenticato dal suo segreto; che è arrivato in tempo, contro una decisione che il Core ha
coniato; che nomina **esattamente** le condizioni che il piano dichiarava; che i suoi codici stanno nel
vocabolario del verifier. **Che cosa cambia rispetto a un verifier locale**: sul Core il verifier
girava nel processo che l'utente ha avviato, sul disco dove il Core scrive, con il codice che l'utente
ha in mano; sul nodo gira nel processo del nodo, e il Core si fida del suo codice, del suo orologio e
del suo disco. È il limite di M12.1 D1 detto una volta per tutte, e non si attenua scrivendolo più
piano. **La versione del nodo** resta dichiarata e non risolta: il Core sa quali verifier un nodo porta
perché è lo stesso codice; un nodo con un codice più vecchio non dichiara `fs.*` e non li riceve, uno
con un codice diverso e gli stessi nomi non si distingue.

### 13. I pesi di §17: lo stato di `local` si osserva, la corrente pesa 20, l'ordine della rete si misura

**Le grandezze sono tassi di cambio**, e nessuna misura li dà (decisione 12): quanto vale un nodo sulla
rete locale rispetto a uno su una rete lontana, contro quanto vale un alimentatore, è un cambio fra
cose che non hanno un'unità comune. Un debito che nessun dato può pagare è una scelta, e **ADR 0048 la
scrive come tale**, e chiude quella parte del «da ritarare» di ADR 0017. ADR 0017 si legge con questa
sezione accanto.

**La decisione 12 era sbagliata sullo stato**, e questa sezione lo dice apertamente (review
dell'implementazione, decisione 2). Lo stato non è uno stub: i nodi lo producono — `IDLE` quando stanno
per chiedere, `BUSY` mentre un loro tool gira. **Lo stub era lo stato di `local`**, che nessuno
produceva e che valeva 0: nel blocco B della misura il PC vinceva perché nessuno osservava lo stato del
Mac. Il risultato era sensato, la ragione era falsa.

**Lo stato di `local` lo dice il Core**, nello stesso battito che §2 chiede prima di ogni piazzamento:
**`BUSY` mentre un tool è in corso su `local` — dall'avvio del tool al risultato registrato —,
altrimenti `IDLE`**. È un fatto che il Core osserva, non una supposizione: lo dice l'executor
(`Executor.running_here`), l'unico modulo che esegue un tool su questa macchina (regola 16), con un
conto in memoria — è un fatto di questo processo: un processo morto non esegue niente, e quello dopo
parte da zero. Il battito riceve la domanda come riceve la lettura dell'alimentazione, perché
`ela.devices` non importa `ela.executive`.

**Una domanda non occupa il Mac** (correzione dell'utente dopo la prova a mano, 2026-09-26). La prima
forma di questa sezione diceva `BUSY` se c'era uno step `RUNNING` su `local`, e uno step che aspetta il
sì dell'utente è `RUNNING`: una domanda lasciata aperta per ore avrebbe mandato ogni lavoro
ripiazzabile al PC con il Mac sotto corrente e fermo. `BUSY` è ciò che un nodo dice di sé mentre un suo
tool gira, e per `local` ora vuol dire la stessa cosa. Nemmeno uno step affidato a un nodo occupa
`local`: il suo `BUSY` è del nodo, nel battito del nodo. `tests/executive/test_local_status.py` tiene
i casi.

**Con lo stato simmetrico e i valori di ADR 0017 l'alimentazione non poteva più spostare niente**: lo
scarto di `NETWORK_POINTS` (15) superava quello di `POWER_POINTS` (10), e la rilettura
dell'alimentazione di M12.3c sarebbe diventata decorativa nell'unica scelta che ELA fa. **La scelta,
come tasso di cambio: un Mac a batteria cede un lavoro ripiazzabile a un PC sotto corrente; con il Mac
sotto corrente, e libero, il lavoro resta sul Mac.** `POWER_POINTS` `AC` passa da 10 a 20; il resto dei
valori di ADR 0017 non cambia:

| Componente | Criterio §17 | Valore |
|---|---|---|
| `power` | consumo energetico | AC +20, BATTERY 0, UNKNOWN 0 |

Il tetto del punteggio diventa 115, e i tratti restano la componente più pesante: 40 su 115 possibili.

**I conti dei quattro casi**, contro il PC di §12 della guida — sulla tailnet, sotto corrente, `IDLE`,
potenza ignota: **5 + 20 + 10 = 35**. Il Mac è sulla rete locale, 20:

| Il Mac | Rete | Corrente | Stato | Totale | Vince |
|---|---|---|---|---|---|
| sotto corrente, `IDLE` | 20 | 20 | +10 | **50** | il Mac |
| sotto corrente, `BUSY` | 20 | 20 | −10 | **30** | il PC |
| a batteria, `IDLE` | 20 | 0 | +10 | **30** | il PC |
| a batteria, `BUSY` | 20 | 0 | −10 | **10** | il PC |

La seconda riga è lo stato che fa il suo mestiere: un Mac sotto corrente ma occupato — da un tool che
gira lì, non da una domanda che aspetta — cede il lavoro a un PC libero. `tests/devices/test_mac_or_pc.py` tiene i quattro
casi e l'aritmetica della ragione.

**La potenza di calcolo e il carico non hanno un lavoro che viaggi e li metta alla prova: sono stub,
non debiti** (ADR 0026 §7). Nessuna capability che viaggia dipende dalla potenza di una macchina o da
quanto è occupata. **Li tiene un tripwire**: `tests/docs/test_adr_travel.py` appunta l'insieme delle
capability che viaggiano, chiesto a F7 e non riscritto a mano; quando l'insieme cambia, il test
fallisce e rimanda a questa sezione.

**L'ordine di `NETWORK_POINTS` si misura**, ed è l'unica cosa dei pesi che una misura può dire: se un
lavoro sul nodo della rete locale costa davvero meno di uno su una rete lontana, nell'ordine in cui la
tabella li mette. La regola è scritta prima dei numeri (SPEC di M13.3, «Le prove a mano»), la misura è
la prova a mano di `docs/GETTING_STARTED.md` §17. Se l'eco e la lettura danno ordini diversi, la misura
si ferma lì, con i numeri, e non sceglie un tipo di lavoro (review dell'implementazione, decisione 3).

**L'esito: l'ordine è misurato**, il **2026-09-26**, fra le 00:48 e le 00:57 dell'ora del Mac, con dieci
prove per lavoro e per macchina, tutte valide per la regola 5 della SPEC: ogni prova ha un solo
`DEVICE_SELECTED`, che sceglie `local` nel blocco A — il PC rifiutato per `PRIVACY`, 35 punti contro
50 — e il PC nel blocco B — `local` fra i candidati con 30 punti e nessun rifiuto, il PC con 35 —, e
Low Power Mode è spento prima e dopo ogni prova. Sull'orologio del Core, `local` dalla decisione
`ALLOWED` al risultato registrato, il PC dall'offerta alla consegna ricevuta:

| Lavoro | `local`, mediana | `local`, massimo | PC, mediana | PC, massimo | PC, minimo |
|---|---|---|---|---|---|
| `core.echo` | 0,9 ms | 1,0 ms | 463 ms | 1010 ms | 93,5 ms |
| `fs.read` | 1,7 ms | 1,9 ms | 559 ms | 1092 ms | 144 ms |

La mediana del PC supera quella di `local` per tutti e due i lavori, quindi **l'eco e la lettura danno
lo stesso ordine**, e la regola 2 non lo smentisce: `LOCAL` 20 sopra `REMOTE` 5 resta com'è. Il tool,
sul PC, ha impiegato fra 0 e 1 ms: la differenza è il costo del protocollo, cioè la rilettura del
long-poll a un secondo, due tragitti sulla tailnet e la presa. **L'ordine vale per la sola coppia
misurata**, `local` contro un nodo sulla tailnet: `OFFLINE`, `UNKNOWN` e un nodo fuori dalla tailnet
non sono stati misurati, e restano come sono. I file stanno in `~/Downloads` della macchina che ha
misurato: `m13.3-pesi-A-eco.jsonl`, `m13.3-pesi-A-lettura.jsonl`, `m13.3-pesi-B-eco.jsonl`,
`m13.3-pesi-B-lettura.jsonl`, lo stato dei nodi in `m13.3-pesi-A-nodi.json` e `m13.3-pesi-B-nodi.json`,
e le righe del database in `m13.3-pesi-eventi.json`, `m13.3-pesi-assegnazioni.json` e
`m13.3-pesi-risultati.json`.

### 14. L'orologio di un nodo: il margine calcolato, la deriva misurata

L'unico orologio di un nodo che arriva al Core è `node.ran_at`, che il Core conserva e non confronta
con niente. **Il margine peggiore, calcolato e non misurato**: una decisione vive
`ELA_DECISION_TTL_SECONDS`, un'offerta al più `ELA_ASSIGNMENT_TTL_SECONDS` e mai oltre la decisione, e
il nodo confronta la decisione con il proprio orologio all'inizio della chiamata, subito dopo la presa.
Un'offerta presa all'ultimo istante lascia alla decisione la differenza delle due impostazioni:
**180 s con i default**, e zero se sono uguali, che la validazione ammette. Un nodo **avanti** più di
così rifiuta, `tool.refused`; un nodo **indietro** non rifiuta mai, e accetta una decisione scaduta per
quanto è indietro — il verso di ADR 0038 §5, la decisione come titolo al portatore, qui esteso a un
orologio che è indietro: ADR 0038 §5 lo dice di una decisione ripresentata entro la sua scadenza.

**La misura** è la prova a mano di `docs/GETTING_STARTED.md` §17, passo 5, fatta il 2026-09-26. ELA
non corregge l'orologio di un nodo: lo misura e lo scrive.

**La premessa era sbagliata** (vincolo 3 della review della SPEC, corretto dall'utente dopo la misura).
La SPEC chiamava caso peggiore il PC appena uscito dal sonno, prima che l'ora si risincronizzi. La
misura lo smentisce: al risveglio Windows rimette l'ora di sistema da quella dell'orologio hardware, e
dopo dieci ore di sonno il PC era avanti di 0,39 s; la sera prima, otto giorni dopo l'ultima
sincronizzazione, di 6,94 s.
**L'errore cresce con il tempo passato dall'ultima sincronizzazione**, e il sonno non ci aggiunge niente
che si veda: le due misure del PC danno lo stesso passo, **0,83 s al giorno in avanti** — 6,94 s in 8,3
giorni dalla correzione del 17 settembre, 0,385 s in 11,2 ore dalla correzione delle 02:13 del 26. Il
peggio non è un risveglio: è il PC rimasto più a lungo senza sincronizzazione, e lo dice la storia delle
correzioni. L'orologio hardware si legge al secondo — l'evento del risveglio lo scrive «13:02:06.500» —,
e la misura non basta a dire se, a parte questo, tenga meglio o peggio di quello di sistema.

**Le misure**, contro `time.apple.com`, nella convenzione di NTP — l'orologio del server meno quello
locale, la correzione che l'orologio locale dovrebbe applicare:

| Quando, il 2026-09-26 | Il Mac, `sntp` | Il PC, `w32tm /stripchart`, cinque campioni | Il PC rispetto al Core |
|---|---|---|---|
| 01:01–01:03, il PC otto giorni dopo l'ultima sincronizzazione | +0,0698 ± 0,030 s | da −6,9403 a −6,9468 s | **+7,01 s** |
| 13:26, il PC ventiquattro minuti dopo un sonno di dieci ore | +0,0362 ± 0,031 s | da −0,3833 a −0,3862 s | **+0,42 s** |

Il Mac è indietro di 0,04–0,07 s in due misure a dodici ore di distanza: stabile, e l'istante in cui lo
si misura rispetto al PC non pesa. **La misura del risveglio vale**: il PC era sospeso dalle 00:52:25Z e
si è riattivato alle 11:02:08Z; l'unico cambio dell'ora fra il risveglio e la misura è quello delle
11:02:06Z, «System time synchronized with the hardware clock», cioè il risveglio stesso, e nessuna
sincronizzazione del servizio dell'ora.

**Il segno, confermato due volte** e non preso dalla convenzione. Nelle venti consegne del blocco B dei
pesi, `node.ran_at` meno l'istante in cui il Core ha ricevuto la busta va da 6,998 s a 7,007 s, mediana
7,001 s: positivo, quindi il PC è avanti, e un limite inferiore di quanto, perché il tragitto della busta
ne sottrae una parte (`m13.3-pesi-assegnazioni.json`). E il servizio dell'ora del PC, alle 02:13 del 26,
un'ora dopo la misura della sera, ha portato l'ora indietro di 6,925 s: quanto `w32tm` aveva detto, con
il segno meno.

**La storia di trenta giorni**: gli eventi `Kernel-General` 1 del PC, esclusi i risvegli, tutti del
servizio dell'ora e **tutti con il segno meno**, l'ora portata indietro. Sei correzioni a scatto — il 3
settembre di 38,3 s, il 4 di 1,1 s, il 9 di 2,0 s, il 14 di 1,4 s, il 17 di 2,1 s, il 26 di 6,9 s — e
sincronizzazioni a 0 ms il 7, il 12 e il 16: **una sincronizzazione ogni uno-nove giorni**. Fra il 17 e
il 26 non ce n'è nessun'altra, e quell'intervallo dà lo stesso passo delle due misure, 6,9 s in 8,4
giorni. **Fra il 3 e il 4 il passo è stato più rapido**: 1,1 s in quindici ore, 1,7 s al giorno, subito
dopo la correzione più grande. Gli altri intervalli contengono una sincronizzazione a 0 ms di cui il
riassunto non porta l'ora, e un passo non lo danno. **Il peggio osservato è 38,3 s avanti**, il 3 settembre, dopo un intervallo che il
registro non copre. **In trenta giorni il PC non è mai stato indietro.**

**Contro il margine, nel verso che conta per un nodo avanti.** Un nodo avanti di X vede scadere una
decisione X secondi prima del Core, e rifiuta con `tool.refused` ciò che per il Core vale ancora: il
fail-safe, mai una decisione scaduta eseguita. Dei 180 s, un PC avanti di 7,01 s ne lascia 173;
avanti di 38,3 s — il peggio osservato — ne lascia 141,7, e consuma il 21 % del margine. Al passo
misurato, i 180 s si consumerebbero in circa 217 giorni senza una sincronizzazione, e a quello più
rapido della storia in più di cento; il PC si sincronizza ogni uno-nove. Il verso che accetterebbe una decisione scaduta, un nodo indietro, in trenta
giorni non si è visto. **La deriva ci sta dentro con margine, e i cinque minuti di ADR 0011 §9
restano.**

I file stanno in `~/Downloads` della macchina che ha misurato: `m13.3-orologio-mac.txt`,
`m13.3-orologio-mac-2.txt`, e quelli del PC — `m13.3-orologio-pc.txt`, `m13.3-orologio-pc-sveglio.txt`,
`m13.3-orologio-pc-sveglio-eventi.txt` trascritti dalla chat, `m13.3-orologio-pc-correzioni.txt`
riassunto; gli originali restano sul PC.

## Alternative considerate

- **Il battito nella rotta, dopo il lock** — l'alimentazione del primo piazzamento sarebbe stata
  fresca, e quella degli step dopo vecchia quanto il giro; e il battito l'avrebbe scritto una rotta che
  sta rispondendo, contro ADR 0044 §8. Scartata dalla review (decisione 7).
- **Il solo ciclo periodico** — gli step sarebbero stati piazzati su un'alimentazione vecchia fino a
  venti secondi: la credenza periodica che ADR 0029 §7 vieta. Scartata dalla review (decisione 7).
- **Il tick della percezione** — spento di default (§2).
- **Lo sguardo sul nodo prima della domanda** (§8) — il Core avrebbe chiesto al nodo il `prospect`
  sul suo disco, e la domanda avrebbe detto il fatto e non l'asserzione. Costa un secondo tipo di
  lavoro nel protocollo — un'offerta che non esegue e una risposta che non è una busta —, e un nuovo
  chiamante dell'executor sullo step. **Scartata dalla review (decisione 1), e non è un debito**: il
  costo della strada scelta è un sì speso, mai un effetto diverso.

## Conseguenze

- `ela.domain` ha `is_text`; `ela.executive` ha `RESULT_NOT_TEXT`.
- `ela.tools` ha `RESERVED_ON_WINDOWS` e `RelocationError`; `ToolPort` ha `relocatable`, dichiarato da
  ogni tool; `tests/windows.py` ha la mappa dei test di Windows fuori dal job.
- `ela.tools` ha `VERIFIED_ON_THE_NODE` e `node_verifiers`, e `node_tools` riceve `fs_root`;
  `ela.composition` ha `NodeFilesystemSettings`, `refuse_the_root` e `carried`, e `NodeWorld` ha
  `verifiers`; `ela.executive` ha `Verdict`, `VERDICT` e `VERIFICATION_MISSING`, e `Claimed` le
  condizioni; `ela.node.runner` ha `verdict_of`; `DeviceOrchestrator` riceve `carried`;
  `VerifierPort` ha `failure_codes`; `ela node run` ha `NO_ROOT`.
- `Executor` ha `running_here`; `LocalHeartbeat` riceve `busy` (`ela.devices.Busy`) e batte lo stato
  di `local`; `POWER_POINTS` `AC` vale 20.
- `ToolPort` ha `asserted`, e `FsReadTool` e `FsWriteTool` lo implementano con `ASSERTED_CREATES`,
  `ASSERTED_OVERWRITES` e `ASSERTED_READS`; `ela.executive` ha `UNSEEN`; `Asked` e `ApprovalOut` hanno
  `machine` e `unseen`, le due pagine le coppie «Su quale macchina» e «Il disco», e la riga di comando
  le righe `machine` e `disk`.
- `ela.ports` ha `LocalBeat`; `ela.devices` ha `LocalHeartbeat`, `BEATS_PER_TTL` e `period_of`;
  `ela.testing.fakes` ha `FakeLocalBeat`; `TaskRunner` riceve `beat`, `Ela` ha `heartbeat`.
- I port sono **ventotto**; le regole di architettura del registro restano **cinquantasette** — le
  due nuove sono test di `tests/architecture/test_travel_rules.py` con i loro casi negativi, fuori dal
  registro, come quelle di M13.2 —, e le rotte **quarantotto**. Questi conteggi di oggi vivono qui; gli
  ADR precedenti restano appuntati a ciò che videro.

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ToolPort` | §17, §33 | async | `relocatable`, `asserted` |
| `VerifierPort` | §20, §63 | async | `failure_codes` |
