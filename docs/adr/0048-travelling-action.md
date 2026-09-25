# 0048. L'azione che viaggia: il verifier dove avviene l'effetto, il battito di `local`, e il lock di un task senza fessura

- **Stato:** Accettata. SPEC di M13.3 decisa dall'utente il 2026-09-25, con le decisioni 1–13 della
  review. Si scrive un pezzo per commit, nell'ordine della SPEC; le righe dei pesi e della deriva
  dell'orologio arrivano dopo la prova a mano, con i numeri presi.
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

### 2. Il battito di `local` lo scrive il Core, prima di ogni piazzamento e a un periodo

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

**Che Windows legga davvero così** lo mostra un modulo che gira solo lì,
`tests/tools/test_paths_windows.py`: una giunzione vera, un flusso alternativo vero, un punto in coda
tolto davvero — prima il fatto di Windows, poi il rifiuto. Il job `windows-latest` lo raccoglie (§5).

### 5. Il debito di ADR 0047 §17, saldato: i test di Windows nel job, o la ragione per cui no

Il job `node-windows` raccoglieva `tests/node`, `tests/conformance` e
`tests/composition/test_build_node.py`, e i test riservati a Windows stavano fuori: nessun job della CI
li eseguiva mai.

**Il pagamento**:

- **entrano nel job, per nome**, `tests/infrastructure/machine/test_acl_smoke.py`,
  `tests/infrastructure/machine/test_power_smoke.py` e `tests/tools/test_paths_windows.py` (§4);
- **chi resta fuori lo dice in un posto che un test legge**: `tests/windows.py`, una mappa file →
  ragione. Oggi ha una voce, `test_sapi_smoke.py`, con la ragione che la sua docstring già scriveva: un
  runner non ha altoparlanti;
- **la difesa di ADR 0047 §17 si è girata**:
  `tests/docs/test_adr_terminal.py::test_every_test_of_windows_is_in_the_job_or_says_why_not` ricava
  dalla suite ogni file con uno `skipif` riservato a Windows, e afferma che ognuno o sta nella riga del
  job o sta nella mappa — l'uguaglianza fallisce anche per una voce della mappa che non è più riservata
  a Windows, o che il job ora nomina. Il suo caso negativo è costruito su una suite finta.

**Il primo run del job è la misura**: che l'ACL si legga sotto l'utente del runner e che `PowerStatus`
risponda su una macchina virtuale, da qui non si sa. Se uno dei due non ci riesce, entra nella mappa
con la ragione misurata, e questa sezione lo registra.

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

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ToolPort` | §17, §33 | async | `relocatable` |

## Alternative considerate

- **Il battito nella rotta, dopo il lock** — l'alimentazione del primo piazzamento sarebbe stata
  fresca, e quella degli step dopo vecchia quanto il giro; e il battito l'avrebbe scritto una rotta che
  sta rispondendo, contro ADR 0044 §8. Scartata dalla review (decisione 7).
- **Il solo ciclo periodico** — gli step sarebbero stati piazzati su un'alimentazione vecchia fino a
  venti secondi: la credenza periodica che ADR 0029 §7 vieta. Scartata dalla review (decisione 7).
- **Il tick della percezione** — spento di default (§2).

## Conseguenze

- `ela.domain` ha `is_text`; `ela.executive` ha `RESULT_NOT_TEXT`.
- `ela.tools` ha `RESERVED_ON_WINDOWS` e `RelocationError`; `ToolPort` ha `relocatable`, dichiarato da
  ogni tool; `tests/windows.py` ha la mappa dei test di Windows fuori dal job.
- `ela.ports` ha `LocalBeat`; `ela.devices` ha `LocalHeartbeat`, `BEATS_PER_TTL` e `period_of`;
  `ela.testing.fakes` ha `FakeLocalBeat`; `TaskRunner` riceve `beat`, `Ela` ha `heartbeat`.
- I port sono **ventotto**; le regole di architettura del registro restano **cinquantasette** — le
  due nuove sono test di `tests/architecture/test_travel_rules.py` con i loro casi negativi, fuori dal
  registro, come quelle di M13.2 —, e le rotte **quarantotto**. Questi conteggi di oggi vivono qui; gli
  ADR precedenti restano appuntati a ciò che videro.
