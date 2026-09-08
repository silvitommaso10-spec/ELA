# 0032. Il contesto che si ricalcola: le assenze derivate, il confine con la memoria, e le due porte chiuse

- **Stato:** Accettata. SPEC di M10.4 approvata dall'utente, con le quattro domande poste **prima**
  della spec e risposte prima dello scope. Le tre che cambiano la forma di ciò che ELA dice di
  sapere sono §3 (una domanda porta ciò che la risponde **e** ciò che le manca, e la seconda lista
  è derivata), §4 (il confine con §21, con il test operativo e la direzione della dipendenza) e §7
  (uno snapshot non entra in un `AuditEvent` né in un `ProviderRequest`, e non è una nota).
- **Contesto:** M10.4, la milestone che compone.
- **Riferimenti spec:** §10, §11, §14, §15, §16, §21, §32, §33, §44, §45, §51, §52, §57
- **Estende:** ADR 0002 (le regole di architettura: due nuove, 38 e 39), ADR 0005 (due membri su un
  port esistente), ADR 0023 (una rotta), ADR 0024 (un comando e tre variabili), ADR 0028 §3 (la
  disciplina della provenienza, estesa oltre la percezione), ADR 0028 §10 (la percezione non è
  memoria, esteso al compositore), ADR 0029 §5 (osservare non è agire, esteso al comporre).

## Contesto

ELA vede (§10, §11), sa cosa sta facendo (§14, §15), ha una cronologia verificabile (§32) e sa
dove sta girando (§16). Non ha un posto che metta insieme queste cose nella risposta alla domanda
di §44.

Prima della spec sono state fatte quattro domande, e le risposte hanno deciso lo scope più di
qualunque opinione.

**Quali fonti esistono, e quali no.** Sette domande in §44, contate contro il codice:

| Domanda di §44 | Fonte | Esito |
|---|---|---|
| cosa sta facendo l'utente | `Observation` — `frontmost_bundle_id`, `running_bundle_ids`, `window_count`, `idle_seconds`, `screen_locked`, `on_console` | **c'è** |
| cosa stava facendo prima | l'osservazione precedente e i `PerceptionChange` dell'ultimo tick; `TaskEvent` | **secondi, non ore** — e per decisione (ADR 0028 §10) |
| quali task sono in corso | `TaskRepository.tasks`, `count`, `plan`, `events`; `ApprovalStore.pending` | **c'è** |
| quali scadenze esistono | `Task.deadline` esiste; **nessuna query la interroga** | **metà** |
| quale dispositivo sta usando | `DeviceRegistry` | **c'è**, con una risposta sola |
| quali informazioni sono rilevanti | — | **niente** |
| cosa sta accadendo nei progetti | — | **niente** |

Il fatto che ha deciso la forma della milestone: **l'esempio che §44 dà di sé stessa non è
rispondibile.** «Preparami la riunione di domani» → *controlla calendario, email e documenti*
poggia interamente su tre fonti che non esistono. Uno snapshot che tacesse quelle assenze
sembrerebbe completo, ed è la specie di errore che nessun test trova dopo.

**Chi lo consuma: nessuno.** Non c'è Planner — `POST /tasks/{id}/plan` porta `PLAN_IS_TEMPORARY`
nel proprio schema — non c'è Decision Engine, non c'è Proactive Core. La differenza con lo stub
multimodale che M10.3 ha rifiutato è che quello era **un costo senza qualcuno che avesse ragione
di pagarlo**; questa è una superficie di lettura, e una superficie di lettura ha un lettore dal
primo giorno. Ma «ha un lettore» non basta se `GET /context` è un join che il client saprebbe
fare da sé, e la milestone esiste per quattro cose che un join non dà: le scadenze, **un solo
istante** invece di quattro, la provenienza e l'età su fonti diverse, e **le assenze nominate**.

## 1. Un dato, non un servizio

Il Context Core è uno **snapshot**, composto da un compositore puro, con una sola superficie di
lettura. Non è un servizio che risponde a domande: il principio operativo di §44 — *non chiedere
ciò che ELA può ragionevolmente ottenere da sola* — richiede di sapere **quali** domande vengono
poste, e oggi nessuno ne pone nessuna.

> **Un'interfaccia a domande nasce con chi chiede.** Consegnarla adesso significherebbe dichiarare
> quali domande esistono al posto di chi le porrà, che è la stessa cosa che ADR 0028 §4 rifiutò
> consegnando una causa che non poteva scattare.

Il primo consumatore, oggi, è l'utente via `GET /context` e `ela context`. Il secondo, dichiarato:
il **Planner (§13)** — la milestone che toglie `PLAN_IS_TEMPORARY` — che è anche il primo che avrà
davvero il principio di §44 da applicare.

## 2. Le sette domande sono un enum, e l'elenco è legato alla spec

`ContextQuestion`, sette membri, nell'ordine dei sette punti di §44. **Tutte e sette compaiono
nello snapshot, sempre**, anche quelle senza fonte: una domanda che non compare è una domanda a
cui nessuno si accorge che ELA non risponde.

Il legame non è ricordato, è verificato. `tests/docs/test_spec_context.py` legge il blocco di §44
da `docs/spec/ELA_spec.md`, ne estrae i punti, e asserisce che la tabella testo → membro sia
esaustiva, biunivoca e **nello stesso ordine**. Un punto aggiunto a §44 fa fallire finché l'enum
non cresce; un punto tolto, altrettanto. Il testo italiano dei punti sta nel test e non in `src`:
è una citazione della spec, e le citazioni della spec stanno dove stanno già
(`test_spec_headings.py`).

## 3. Una domanda porta ciò che la risponde **e** ciò che le manca, e la seconda lista è derivata

Non è una partizione fra «risposte» e «assenze», e il caso che lo dimostra è *quali scadenze
esistono*: ELA conosce le scadenze dei propri task e **non** quelle del calendario. Dire solo
«risposta» sarebbe una bugia per omissione — precisamente il modo in cui l'esempio di §44
fallirebbe. Una partizione avrebbe dovuto scegliere, e ogni scelta era falsa.

```python
class ContextQuestionStatus(_DomainModel):
    question: ContextQuestion
    answered_by: tuple[ContextSource, ...]
    missing: tuple[ContextSource, ...]
```

Ogni fonte dichiara **il campo di `ContextSnapshot` che la porta**:

| `ContextSource` | Campo | Esiste |
|---|---|---|
| `PERCEPTION` | `activity` | sì |
| `CHANGES` | `recent` | sì |
| `TASKS` | `work` | sì |
| `TASK_DEADLINES` | `deadlines` | sì |
| `DEVICES` | `device` | sì |
| `CALENDAR` | `calendar` | **no** |
| `MAIL` | `mail` | **no** |
| `DOCUMENTS` | `documents` | **no** |
| `PROJECTS` | `projects` | **no** |
| `RELEVANCE` | `relevance` | **no** |

E la divisione fra le due liste **non è scritta a mano da nessuna parte**. È una funzione pura di
due argomenti:

```python
def held(sources, fields) -> tuple[tuple[ContextSource, ...], tuple[ContextSource, ...]]:
```

chiamata dal compositore con `frozenset(ContextSnapshot.model_fields)`. Ne segue la proprietà per
cui questa milestone esiste:

> **Il giorno in cui il calendario arriverà, chi lo aggiunge dovrà aggiungere il campo `calendar`
> a `ContextSnapshot`, e nell'istante in cui lo fa l'assenza sparisce da sola.** Non c'è una
> seconda lista da ricordarsi di aggiornare, perché non c'è una seconda lista.

È la forma «derivabile invece che elencata» che il repository usa già due volte: `fingerprint()`
deriva le chiavi dai campi meno `UNCOMPARED` (ADR 0028 §5), e la regola 33 ha smesso di nominare
un file (ADR 0030 §6). Il verso è quello fail-safe: una fonte il cui campo non esiste è
**mancante**, mai silenziosamente risposta.

E siccome `held` è pura, il meccanismo si **prova** invece di crederlo: il test la chiama con
`fields | {"calendar"}` e asserisce che `CALENDAR` passa da `missing` a `answered_by` e che
`DEADLINES` resta senza assenze. È la forma di ADR 0031 §3 — *il confronto è una funzione pura di
due argomenti, quindi ogni fallimento si esercita invece di aspettarlo*.

## 4. Il confine con §21, con il test operativo e la direzione già fissata

> **Il contesto è ciò che è vero adesso ed è ri-derivabile dalle fonti vive. La memoria è ciò che
> ELA ha deciso di trattenere perché perderlo perderebbe informazione.**

Il test operativo, per chi dovrà decidere caso per caso:

> **Se il fatto si ricalcola, è contesto. Se perderlo perde informazione, è memoria.**
> «Chrome è in primo piano» si ricalcola. «L'utente preferisce le riunioni al mattino» no.

Ne segue tutto, e ogni conseguenza è controllabile:

- **Il contesto non persiste niente.** Nessuna tabella, nessuna migrazione. Un riavvio non perde
  nulla perché non c'era nulla da perdere.
- **I quattro campi di §21 — importanza, confidenza, scadenza, privacy — governano ciò che è
  tenuto.** Il contesto non tiene niente, quindi non li ha e non deve averli: un `importance` su
  uno snapshot sarebbe memoria improvvisata senza le regole di §21. È ADR 0028 §10 («la percezione
  non è memoria») esteso dal percepire al comporre. Il fatto si controlla: nessuno degli undici
  modelli di contesto ha un `created_at`, e un test lo asserisce fra i value object.
- **`SensorCause` non è confidenza.** È un enum chiuso di ragioni per cui un valore è il default,
  non un grado di credenza. La distinzione «lo so / credo / lo ricordo da una fonte poco
  affidabile» di §21 è un'altra specie di domanda, e assorbirla qui sarebbe l'errore che ADR 0028
  §4 evitò rifiutando un quarto `SensorState`.
- **Il contesto non scrive mai** (regola 38).
- **La direzione della dipendenza, fissata adesso: la memoria sarà una fonte del contesto, mai il
  contrario.** Uno snapshot potrà portare un fatto di memoria con la sua provenienza — con un
  `ContextSource.MEMORY` e il suo campo, che è esattamente il meccanismo di §3. Il Context Core non
  deve mai essere il posto che decide di ricordare qualcosa, perché sarebbe memoria senza le regole.

**Dove i due si toccano è «cosa stava facendo prima»**, ed è lì che il confine regge: una storia
dell'attività dell'utente non è contesto — non è «adesso» e non è ri-derivabile — quindi è memoria
con le regole di §21, oppure è niente. M10.4 non costruisce nessun anello (§10).

## 5. Contenuto e stato, e i due che entrano per decisione

La linea di ADR 0028 §9, applicata al compositore.

**Stato — entra:** sensori con la loro causa (mai uno `SensorState` nudo), mappa dei permessi,
schermi, blocco, console, `idle_seconds` come numero; `running_bundle_ids`, `frontmost_bundle_id`,
`window_count`, già classificati stato da ADR 0030 §1 con la sua nota che non è una scusa —
l'elenco delle app *è* informazione personale anche se non è contenuto, quindi non esce, non entra
nell'audit, non entra nella memoria; le righe del registry; stati e conteggi dei task; **gli
istanti** delle scadenze; che ci sono N approvazioni pendenti e per quale capability.

**Contenuto — non entra:** il testo dell'OCR e i pixel di una cattura, che sono la tentazione
precisa di §44 — «cosa sta facendo l'utente» si risponderebbe meglio leggendo lo schermo, e ADR
0030 §1 ha già deciso che la risposta è lo **stato** e non il contenuto; i titoli delle finestre
(regola 36); `ExecutionResult.output`; `TaskStep.arguments`, che la regola 23 tiene fuori
dall'audit e per cui uno snapshot non è un'eccezione — **nemmeno `purpose`**, che è dichiarato
mostrabile dentro un `Approval` (ADR 0029 §6), cioè dentro **una domanda posta all'utente**, non
dentro un quadro composto.

**I due che entrano per decisione: `Task.goal` e `UserIntent.text`.** Sono parole dell'utente,
quindi contenuto — ma **dettate a ELA** (ADR 0029: «qualcosa che l'utente le aveva dettato»), e
`GET /tasks` le restituisce già oggi allo stesso lettore con lo stesso token. «Tre task in corso»
senza dire quali non risponde a §44. Sono **l'unico contenuto** dello snapshot, ed è asserito su
tutti i campi di tutti i modelli invece che promesso. Con loro entra il vincolo che li accompagna,
e non è una nota: è la regola 39 (§7).

## 6. Regola 38 — se rispondere richiede una capability, non è contesto

> **Se rispondere a una domanda di contesto richiede una capability, quella risposta non è
> contesto: è un'azione**, e passa dall'Executor.

È ADR 0029 §5 («osservare non è agire») esteso da chi osserva a chi compone, e rende automatica la
linea contenuto/stato invece di doverla ridiscutere campo per campo: tutto ciò che costa una
`PermissionDecision` è fuori per costruzione.

Scatta in due metà, perché ha due modi di essere rotta.

**La porta — il contratto quattordicesimo di import-linter**, il primo dopo ADR 0024:
`ela.context` non importa `ela.permissions`, `ela.tools`, `ela.executive`, `ela.providers`,
`ela.routing`, `ela.infrastructure`, `ela.api`, `ela.cli`, `ela.composition`. Un compositore che
non può raggiungere il Guardian non può chiedergli niente. `ela.perception` **non** è vietata: è
pura, sta nel gate, e osservare non è agire. `ela.devices` nemmeno, e per una ragione che è essa
stessa una regola: la disponibilità di un nodo è derivata e solo il registro può derivarla (regola
20), quindi la risposta va chiesta a lui.

**La maniglia — la regola 38 vera e propria**, un walk dell'AST: dentro `ela.context` nessuna
chiamata `self.<port>.<membro di scrittura>()`, sul vocabolario chiuso `add`, `add_plan`,
`append`, `append_event`, `authorize`, `consume`, `decide`, `execute`, `grant`, `register`,
`respond`, `save`, `transition`, `update`, `verify`. Esiste perché la prima metà non basta: **un
port arriva dal costruttore**, quindi un modulo può chiamare `save` su qualcosa che non ha mai
importato, e ogni contratto di import sarebbe muto. È la stessa lezione della regola 32, che dovette
leggere le chiamate e non solo gli import.

**Legge il ricevente, non solo il nome, e questa è una decisione.** Tre di quei nomi — `add`,
`append`, `update` — sono anche metodi di `list`, `set` e `dict`. Una regola che leggesse il nome
da solo scatterebbe su `answered.append(source)`, e l'unico modo di soddisfarla sarebbe scrivere
il compositore in modo strano invece che corretto.

> **Una regola che costringe il codice corretto a contorcersi insegna ad aggirare le regole.** Il
> ricevente non è una scorciatoia: un compositore tiene ciò che gli è stato dato come attributi di
> istanza, che è l'unica forma in cui potrebbe scrivere.

## 7. Regola 39 — uno snapshot non entra in un `AuditEvent` né in un `ProviderRequest`

> **Nessun modulo di `ela` che nomina `ContextSnapshot` può nominare `AuditEvent` o
> `ProviderRequest`.**

Le due direzioni che chiude sono due errori diversi, e nessuno dei due è ipotetico:

- **verso l'audit**: uno snapshot registrato riempirebbe la catena di §32 di cose che ELA non ha
  deciso (ADR 0028 §10) e ci porterebbe dentro `Task.goal`, che la regola 23 tiene fuori;
- **verso un provider**: è il giorno in cui il Planner vorrà mettere il contesto in un prompt.
  Quel giorno è un dato che esce, e vanno prima scritte le quattro risposte di §57 nella forma di
  ADR 0030 §17. **Deve trovare una porta chiusa e non una nota.**

Guarda nomi e attributi come le regole 34, 35 e 36, quindi non è esprimibile come divieto di
import e non aggiunge un contratto. È **muta sul tree di oggi**, e la mutezza è asserita: la regola
sorveglia una porta che nessuno ha ancora attraversato, che è l'unico momento in cui una porta del
genere si può ancora chiudere (ADR 0030 §15: una difesa scritta dopo la cosa che difende ha una
finestra in cui la cosa esiste e la difesa no).

**Conseguenza operativa, e non è un dettaglio:** il compositore non può digitare `AuditEvent`,
quindi **non può leggere l'audit log**. Vedi §11, che è la stessa decisione vista da un'altra parte.

## 8. Il compositore non causa niente: la vista della percezione è un argomento

`ContextCore.assemble(view: PerceptionView)`. La vista non viene presa chiamando `tick()` da
dentro: la prende la rotta e la passa.

Non è comodità. Se il compositore chiamasse `tick()` lancerebbe un sottoprocesso, cioè
**causerebbe** qualcosa, e la regola 38 sarebbe vera per le capability e falsa per il criterio che
le sta sotto. Con la vista come argomento, `assemble` è una funzione dei suoi ingressi più letture
di port: è la forma più forte di «non esegue», ed è anche la forma che si prova senza far girare
niente.

`PerceptionView` guadagna un terzo campo, `since` — l'istante dell'osservazione **da cui** i
cambiamenti sono misurati — prodotto lì perché è lì che si conosce. Vedi §10.

## 9. Le scadenze: due letture nuove, e nessun port nuovo

`TaskRepository` guadagna due membri, e sono le uniche aggiunte di superficie della milestone:

| Membro | Risponde |
|---|---|
| `due(states, limit)` | i task **che hanno** una scadenza, in ordine di scadenza, i primi `limit` |
| `due_count(states)` | quanti ne sono, senza riportarne nessuno |

- **Un metodo suo e non un flag su `tasks()`**, perché `tasks()` dichiara nel proprio docstring che
  l'ordine è *sempre* quello di inserimento, e quella frase è un'invariante che ogni implementazione
  rispetta. Un ordine diverso è una domanda diversa, e una domanda diversa ha un nome.
- **I task senza scadenza non ci sono**, non finiscono in fondo: la domanda è «quali scadenze
  esistono», e un task senza scadenza non è una scadenza tarda.
- **`due_count` esiste per la ragione per cui esiste `count`** (M8.3): contare i primi N di
  qualcosa non è un conteggio, e una sezione che mostra venti di centotrentasette deve poter dire
  centotrentasette senza caricarli. Comporre la risposta caricando tutti i task vivi e ordinandoli
  nel chiamante è ciò che la revisione di M8.1 ha tolto da `/diagnostics`.

Nessun campo derivato accanto: **niente `overdue`**. Lo snapshot porta l'istante e il proprio `at`,
e il confronto lo fa chi legge (§12).

## 9-bis. Il limite morde ad alta voce, e il numero è misurato

Un task vivo che cade fuori dai primi venti **non sparisce in silenzio**: `non ci sono altri task`
e `non te li sto mostrando` sono due fatti diversi, e consegnarli con la stessa faccia è la stessa
ambiguità che ADR 0030 §8 dice di spezzare *prima* di consegnare la lettura.

Ogni sezione che porta un elenco limitato porta `shown` e `total`, entrambi **obbligatori**, con un
validatore che rifiuta uno `shown` che non sia la lunghezza dell'elenco e un `total` più piccolo di
`shown`. `ela context` stampa `20 of 137` e mai un `20` nudo.

> **Un elenco troncato dichiara il proprio troncamento.** Un limite che nessuno vede è un limite
> che il lettore scambia per il mondo.

**La misura**, presa il **2026-09-08** su questa macchina (macOS 26.6, arm64, CPython 3.12.14),
contro SQLite su file, con un terzo dei task in `EXECUTING` — quelli che costano anche una lettura
del piano:

| Task nel database | Limite | Mediana | Massimo |
|---|---|---|---|
| 10 | 10 | 11,9 ms | 14,8 ms |
| 100 | 10 | 12,0 ms | 12,1 ms |
| **1000** | **10** | **12,0 ms** | 12,2 ms |
| 100 | 20 | 21,5 ms | 21,5 ms |
| **1000** | **20** | **21,5 ms** | 21,9 ms |
| 1000 | 50 | 50,4 ms | 57,0 ms |

Due fatti, e sono quelli che i limiti esistono per produrre:

1. **Il costo è piatto rispetto alla dimensione del database.** Mille task costano quanto cento
   allo stesso limite, il che è la prova che `count` e `due_count` non scandiscono e che `due`
   ordina nel database.
2. **Il costo è lineare nel limite**, circa 1 ms per task mostrato: un `events()` per task, e un
   `plan()` solo per i task che hanno davvero uno step avviato.

**I default: 20 task, 10 scadenze, 10 eventi.** A 20 la composizione costa 21,5 ms, contro i ~35 ms
che una sonda di percezione costa da sola (ADR 0028 §2): una lettura di `/context`, che fa
entrambe, è dominata dal guardare e non dal comporre. Tutti e tre sono `ELA_CONTEXT_*`.

**Una cosa trovata dalla misura e sistemata alla fonte:** la prima versione leggeva la traccia
degli eventi **due volte** per task — una per lo step in corso, una per gli eventi recenti — e
quella seconda lettura era metà del costo dello snapshot (31,8 ms contro 21,5 a limite 20). La
traccia si legge una volta e si passa a entrambi. Non l'aveva vista nessuna revisione: l'ha vista
la misura, che è la ragione per cui il numero si misura invece di sceglierlo.

## 10. «Prima» vuol dire secondi, e il campo che lo dice

`recent` porta **`since`**, l'istante dell'osservazione precedente, accanto ai `PerceptionChange`
dell'ultimo tick e agli ultimi eventi dei task vivi.

`since` non è decorazione: senza di esso «cosa stava facendo prima» avrebbe due significati — *è
successo poco* e *non guardo da poco* — che è precisamente l'ambiguità che ADR 0030 §8 dice di
spezzare **prima** di consegnare la lettura. Con `since` la portata dell'orizzonte è un dato e non
un'etichetta, e chi legge vede che «prima» qui vuol dire secondi. Al primo tick `since` coincide
con `observed_at` e i cambiamenti sono vuoti: una risposta vera, non una mancante.

**E nessun anello di osservazioni recenti viene costruito.** ADR 0028 §10 lo rifiutò come storico
non dichiarato; questa milestone lo conferma invece di riaprirlo, con la ragione di §4: uno storico
non si ricalcola, quindi non è contesto.

## 11. Il Context Core non legge l'audit

Segue dalla regola 39 come conseguenza di tipo — `AuditLog.read()` restituisce `AuditEvent`, e
nominarlo sarebbe una violazione — ma ha una ragione di merito che regge da sola:

> L'audit è la traccia della **responsabilità di ELA** (§32). Rileggerlo dentro un quadro composto
> è un secondo uso del registro, e un secondo uso è una decisione che merita la propria milestone,
> non un effetto collaterale di un compositore.

«Cosa è successo prima» si risponde con i `TaskEvent`, che sono ciò che è accaduto a un task.
`GET /audit` continua a esistere e a rispondere alla sua domanda.

## 12. Nessuna soglia, nessun punteggio: di §45 entra il vincolo, non il motore

Un Decision Engine che scelga fra osservare, aspettare, chiedere, agire, notificare, delegare,
trasferire e fermarsi senza avere niente da decidere sarebbe lo stesso stub del multimodale di
M10.3. Non entra.

Di §45 entra il **vincolo**, e vincola questa milestone:

> Il contesto porta **valori grezzi**, perché chi deciderà scelga le proprie soglie.

Niente `UserPresence`, niente `overdue`, niente `urgency`, niente ordinamento per rilevanza, niente
«il contesto suggerisce». Il precedente è `idle_seconds` come numero (ADR 0028 §5). E la domanda
`RELEVANT_INFORMATION` resta **senza fonte e nominata come tale**, che è la cosa onesta: la
rilevanza è un giudizio, e questa milestone non ne ha uno da dare.

## 13. Dove si legge

**Rotta aggiunta** alla tabella di ADR 0023 §6:

| Metodo | Rotta | Cosa risponde |
|---|---|---|
| `GET` | `/context` | attività, dispositivo, lavoro, scadenze, recente, e le sette domande di §44 con le loro risposte e le loro assenze |

`/context` **osserva**, per la ragione con cui `/perception` osserva: chi chiede cosa sta
succedendo vuole la risposta di adesso. `/diagnostics` **non cambia**, e la linea che glielo
impedisce è la sua, già scritta nel suo docstring: dice *a cosa ELA è collegata*, non *cosa ELA sta
facendo*. `/context` è l'altra metà di quella frase.

**Comandi aggiunti** alla tabella di ADR 0024 §3:

| Comando | Rotta | Uscite |
|---------|-------|--------|
| `ela context` | `GET /context` | `0` `1` `2` `3` |

**Variabili aggiunte** alla tabella di ADR 0024: `ELA_CONTEXT_TASKS_LIMIT`,
`ELA_CONTEXT_DEADLINES_LIMIT`, `ELA_CONTEXT_EVENTS_LIMIT`.

**Lo schema dell'API riusa i modelli di dominio invece di trascriverli**, ed è una deviazione
dichiarata dalla regola che `schemas.py` si dà. Quella regola esiste perché un campo aggiunto al
dominio non esca dalla macchina senza che nessuno se ne accorga; qui il modello ha **un lettore
solo** e la forma del dominio *è* la forma sul filo, quindi una trascrizione sarebbe la tabella di
traduzione che il docstring di quel file mette in guardia — due posti da tenere allineati. La
garanzia resta, derivata invece che copiata: `tests/api/test_context.py` asserisce l'insieme esatto
delle chiavi di ogni sezione, quindi un campo aggiunto al dominio fa fallire quel test finché
qualcuno non decide che può uscire.

## 14. Niente capability, niente tool, niente audit, niente cadenza

- **Nessuna capability.** Non c'è niente da decidere: il compositore non esegue e non legge
  contenuto che non gli sia già stato dettato. Il catalogo è immutabile alla costruzione (ADR
  0010) proprio perché non sia il posto dove si aggiungono cose «per dopo».
- **Nessun tool, nessun verifier.** Comporre non è agire.
- **Nessun evento di audit nuovo.** Comporre non è decidere (ADR 0028 §10): una lettura di
  `/context` scrive **zero** eventi, ed è una proprietà con un test.
- **Nessuna cadenza e nessun trigger.** Lo snapshot si compone quando qualcuno chiede. Chi lo
  comporrà da solo è il Proactive Core (§34), come per ADR 0029 §8.

## 15. Il gate

`ela.context` è puro: nessun ramo dipende dall'hardware, dal sistema operativo o dalla rete —
riceve la vista come argomento e legge port che i fake implementano. Per il criterio di ADR 0028
§1 e per la regola di CLAUDE.md entra in `CRITICAL_PACKAGES` **in questa milestone**, al 100%
branch. Il gate passa da tredici a quattordici package.

## 16. Le tabelle

`Regole aggiunte:`

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 38 `context-writes-nothing` | il compositore non chiama nessun membro di scrittura di un port | `ela.context` | nessuna esenzione |
| 39 `context-is-not-recorded` | chi nomina `ContextSnapshot` non nomina `AuditEvent` né `ProviderRequest` | tutto `ela` | nessuna esenzione |

`Contratto aggiunto:` il **quattordicesimo**, l'altra metà della regola 38 (§6).

Port estesi:

| Port | Spec | Modo | Membri |
|------|------|------|--------|
| `TaskRepository` | §14 | async | `due`, `due_count` |

## Alternative considerate

- **Rimandare il Context Core alla milestone del Planner**, dove il consumatore esiste davvero.
  Scartata, e non perché il componente serva subito: la parte che costa qui non è il codice, sono
  i tre confini — contenuto/stato, contesto/memoria, comporre/agire — e prenderli dentro la
  milestone del Planner significa prenderli mentre si ha fretta di far funzionare il Planner.
- **Una partizione risposta/assenza** invece delle due liste. Scartata dal caso `DEADLINES`, che è
  entrambe le cose insieme (§3).
- **Elencare a mano le fonti che mancano.** Scartata: sarebbe una seconda lista, e il giorno del
  calendario qualcuno dovrebbe ricordarsi di togliere una riga. La derivazione dai campi non ha
  quel giorno.
- **Leggere l'audit per «cosa stava facendo prima».** Scartata: è un secondo uso del registro di
  §32, e merita la propria decisione (§11).
- **Un anello di osservazioni recenti.** Scartata, di nuovo: ADR 0028 §10, e il test di §4 —
  uno storico non si ricalcola.
- **Un `overdue` accanto alla scadenza.** Scartata: è un confronto che chi legge sa fare, e il
  contesto porta valori grezzi (§12).
- **Un flag `with_deadline` su `tasks()`** invece di `due`. Scartata: cambierebbe l'ordine che
  `tasks()` dichiara invariante, e una lettura che significa due cose va spezzata.
- **Trascrivere i modelli del dominio in modelli dell'API.** Scartata con la sua garanzia
  sostituita da un test sulle chiavi (§13).
- **Una regola 38 che leggesse solo il nome del metodo.** Scartata: `append` è anche un metodo di
  `list`, e la regola avrebbe costretto il compositore a scriversi storto (§6).
- **Derivare «quali stati sono vivi» dentro `ela.context`.** Scartata: è conoscenza della state
  machine (ADR 0004), il compositore non può importarla (regola 10, contratto 7), e una seconda
  copia della lista è il modo in cui due liste divergono. Arriva dal composition root come dato,
  che è la forma di ADR 0026.

## Conseguenze

- ELA sa dire cosa sta succedendo adesso in un istante solo, e sa dire con il nome della cosa che
  manca a quale parte della domanda di §44 non può rispondere su questa macchina.
- Le assenze di §44 sono **derivate dai campi che lo snapshot ha**, quindi il giorno in cui una
  fonte arriverà l'assenza sparirà per costruzione e non per memoria di qualcuno.
- Il confine fra contesto e memoria è deciso **prima** che la memoria esista, con un test operativo
  e con la direzione della dipendenza già fissata.
- La strada che porta il contesto dentro un prompt è **chiusa da una regola**, non annotata: chi la
  vorrà aprire troverà le quattro domande di §57 da rispondere.
- Le regole di architettura passano da trentasette a **trentanove**, e i contratti di import-linter
  da tredici a **quattordici**: la 38 ha bisogno di entrambi — un import è una porta, una chiamata è
  una maniglia — e la 39 guarda nomi.
- I port restano **ventuno**; `TaskRepository` passa da nove a undici membri.
- Le capability di produzione restano **cinque**, quelle di v0.1 **tre**.
- `CRITICAL_PACKAGES` passa da tredici a **quattordici**.
- Nessun evento di audit nuovo, nessuna tabella nuova, nessuna migrazione.

### Vincoli dichiarati, da riaprire quando serviranno

- **Nessuna fonte nuova** (ADR 0032): calendario, email, documenti e progetti non esistono, e
  l'assenza è nominata invece che taciuta. Si riaprono con §39, §23 e §21.
- **Il Context Core non legge l'audit** (ADR 0032): un secondo uso del registro di §32 è una
  decisione sua.
- **«Prima» vuol dire secondi** (ADR 0032): nessun anello di osservazioni, ADR 0028 §10 confermata.
- **Uno snapshot non entra in un `AuditEvent` né in un `ProviderRequest`** (ADR 0032). Si riapre con
  le quattro risposte di §57 nella forma di ADR 0030 §17.
- **Nessuna rilevanza, nessun punteggio, nessuna soglia** (ADR 0032): il contesto porta valori
  grezzi perché §45 scelga le proprie.
- **Il contesto non persiste niente** (ADR 0032): si ricalcola a ogni lettura.
- **La memoria sarà una fonte del contesto, mai il contrario** (ADR 0032). Direzione fissata prima
  che la memoria esista.
- **Un nodo solo** (ADR 0032): «quale dispositivo sta usando» ha una risposta sola finché §56 non
  ne porta un secondo.
- **Nessuna cadenza e nessun trigger** (ADR 0032): lo snapshot si compone quando qualcuno chiede.
  Si riapre col Proactive Core, §34.
- **`Task.goal` e `UserIntent.text` sono l'unico contenuto dello snapshot** (ADR 0032).
- **Un elenco troncato dichiara il proprio troncamento** (ADR 0032). Criterio generale.
