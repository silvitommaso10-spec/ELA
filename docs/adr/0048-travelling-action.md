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

## Alternative considerate

- **Il battito nella rotta, dopo il lock** — l'alimentazione del primo piazzamento sarebbe stata
  fresca, e quella degli step dopo vecchia quanto il giro; e il battito l'avrebbe scritto una rotta che
  sta rispondendo, contro ADR 0044 §8. Scartata dalla review (decisione 7).
- **Il solo ciclo periodico** — gli step sarebbero stati piazzati su un'alimentazione vecchia fino a
  venti secondi: la credenza periodica che ADR 0029 §7 vieta. Scartata dalla review (decisione 7).
- **Il tick della percezione** — spento di default (§2).

## Conseguenze

- `ela.domain` ha `is_text`; `ela.executive` ha `RESULT_NOT_TEXT`.
- `ela.ports` ha `LocalBeat`; `ela.devices` ha `LocalHeartbeat`, `BEATS_PER_TTL` e `period_of`;
  `ela.testing.fakes` ha `FakeLocalBeat`; `TaskRunner` riceve `beat`, `Ela` ha `heartbeat`.
- I port sono **ventotto**; le regole di architettura del registro restano **cinquantasette** — le
  due nuove sono test di `tests/architecture/test_travel_rules.py` con i loro casi negativi, fuori dal
  registro, come quelle di M13.2 —, e le rotte **quarantotto**. Questi conteggi di oggi vivono qui; gli
  ADR precedenti restano appuntati a ciò che videro.
