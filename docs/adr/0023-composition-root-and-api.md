# 0023. Composition root, configurazione unificata e API locale: `ela.composition`, `ela.api`, token statico su loopback, regola 27

- **Stato:** Accettata. Review del 2026-09-07, tre punti applicati nel commit
  `chore(m8.1): review fixes`: lo **schema OpenAPI è servito**, dietro il token, perché il limite
  del piano sia leggibile da chi *usa* l'API e non solo da chi legge questo documento (§6, §7);
  la risposta **identica** a un'approvazione già applicata è idempotente e non un conflitto
  (§8, terza riga); il debito «`count` per stato nel `TaskRepository`» che `/diagnostics` porta
  è scritto in `docs/milestones/M8.3.md` invece di restare in una nota (§6). Più un difetto
  trovato scrivendo la tabella degli endpoint per la review: una richiesta il cui **task si è
  mosso** — fermato (§65), scaduto — restava nell'inbox, e rispondere ci **scriveva** una
  risposta che non muoveva niente. Corretto in §8: `/approvals` non la mostra, e `approve`/`deny`
  la rifiutano **prima di scrivere**.
- **Data:** 2026-09-07
- **Riferimenti spec:** §12, §27, §30, §32, §33, §46, §47, §48, §54, §57, §58, §62, §65
- **Milestone:** M8.1 (decisioni dell'utente del 2026-09-07: divisione approvata con la CLI
  spostata a **M8.2**, decisioni **2–16** come proposte, più le quattro risposte alla SPEC e tre
  note riportate qui in §4, §8 e §12)

## Contesto

ELA ha tutti i pezzi di §27 — catalogo, Guardian, autorizzazioni, executor, tool, verifier,
device registry, orchestrator, runner, provider, router, cinque adapter SQL — e **nessun posto
che li metta insieme**. Ogni test costruisce il suo mondo a mano; fuori dai test ELA non esiste
come processo. §54 chiede per la v0.1 «Configuration; Health; Diagnostics; API», e nove ADR
precedenti hanno rinviato qui un impegno preciso: costruire il router e passarlo ai tool
(ADR 0022), chiamare `ensure_local` con i nomi dei tool (ADR 0016, 0017), unificare cinque
`BaseSettings` con lo stesso prefisso (ADR 0013, 0020), rendere i TTL configurabili entro un
tetto (ADR 0012, 0013), decidere **chi risponde** a un'approvazione (ADR 0015 §9) e **chi
richiama `run()`** (ADR 0019).

Leggendo il codice per scrivere la SPEC sono emersi due prerequisiti che nessun ADR aveva
nominato:

1. **ELA non ha un orologio.** Le uniche implementazioni di `Clock` e `IdGenerator` sono
   `FakeClock` e `FakeIdGenerator` in `ela.testing`, che il contratto 5 vieta al codice di
   produzione. Senza un orologio vero non si costruisce niente.
2. **`TaskEngine.__init__` richiede `orphan_after` senza default**: finora il valore lo
   sceglievano i test.

E una condizione che l'API eredita: **il Planner (§13) non esiste**. Un task senza piano non ha
grafo da percorrere, quindi o l'API accetta un piano scritto a mano, o dall'API non gira niente.

## Decisione

### 1. `ela.composition`: la prima cartella non prevista da §48, e perché

Il composition root è un package nuovo, `ela.composition`, con tre moduli: `settings.py` (la
configurazione), `system.py` (l'orologio e gli id) e `root.py` (`build` e il contenitore).

§48 elenca la struttura iniziale di `src/ela/` e non lo prevede: **questa è la prima cartella
aggiunta**, e §48 stessa dice come si fa («la struttura può evolvere, ma ogni modifica
architetturale significativa deve essere documentata»). Il motivo è che la cosa che manca non
appartiene a nessuno dei package esistenti: mettere `build` in `ela.api` legherebbe la
costruzione di ELA a FastAPI — e la CLI di M8.2, che costruisce lo stesso mondo, non ha nessun
bisogno di un web framework; metterlo in `ela.executive` lo farebbe importare `ela.providers` e
`ela.infrastructure`, che il contratto 4 vieta e deve continuare a vietare. Il composition root
è per definizione il modulo che sa tutto: o è un posto suo, o inquina un posto d'altri.

**`ela.api` non è il composition root**: riceve il mondo già costruito (§6) e non sa da dove
viene.

### 2. La configurazione: un aggregato che compone, non una classe piatta

`Settings` è un modello **immutabile** che tiene i cinque oggetti già esistenti —
`PersistenceSettings`, `WorkspaceSettings`, `DeviceSettings`, `AnthropicSettings`,
`RoutingSettings` — più i due nuovi di questa milestone, `ApiSettings` e `CoreSettings`.
`Settings.load()` è l'**unico** posto in cui ELA legge l'ambiente.

Non una classe piatta che sostituisca le cinque: la validazione di ogni pezzo — la chiave che
non deve stamparsi, il budget di output confrontato con il modello più capiente, la tabella di
rotte vuota rifiutata, il TTL dell'heartbeat strettamente positivo — è stata decisa dall'ADR che
possiede quel pezzo, e vive accanto al codice che la usa. Ciò che era sparso non era la
validazione: era il **punto di lettura**. Adesso è uno.

`Settings` non è a sua volta un `BaseSettings`: legge attraverso i sette, non al posto loro, e i
sette restano costruibili da soli — è ciò che tiene in piedi i test che li conoscono.

### 3. Le sette variabili nuove

| Variabile | Tipo | Default | Vincolo |
|---|---|---|---|
| `ELA_API_TOKEN` | `SecretStr` | *(nessuno: obbligatorio)* | almeno 32 caratteri |
| `ELA_API_HOST` | `str` | `127.0.0.1` | solo loopback |
| `ELA_API_PORT` | `int` | `8351` | fra 1 e 65535 |
| `ELA_USER_NAME` | `str` | `user` | non vuoto |
| `ELA_AUTHORIZATION_TTL_SECONDS` | `int` | `3600` | fino a `MAX_AUTHORIZATION_TTL` (24 ore) |
| `ELA_APPROVAL_TTL_SECONDS` | `int` | `86400` | fino a `MAX_APPROVAL_TTL` (7 giorni) |
| `ELA_TASK_ORPHAN_AFTER_SECONDS` | `int` | `900` | maggiore di zero |

I due TTL erano già costanti con il loro tetto (ADR 0012, ADR 0013): qui diventano configurabili
**dentro** quel tetto, perché un TTL senza tetto è una porta che si può lasciare aperta per
sempre scrivendo un numero grande.

`ELA_TASK_ORPHAN_AFTER_SECONDS` è **900** e la ragione va scritta accanto al numero: `run` è
sincrono dentro una richiesta HTTP (§9), quindi un task EXECUTING può stare legittimamente in
silenzio quanto dura una chiamata al modello. Un default corto farebbe fallire come orfano, a
ogni riavvio, un task ancora vivo.

`ELA_API_PORT` è **8351** e non `8000`: una porta poco comune collide meno con ciò che gira già
su una macchina da sviluppo, e resta configurabile.

### 4. `SystemClock` e `UuidGenerator`: ELA prende un orologio

`ela.composition.system` porta le due implementazioni di produzione che non c'erano:
`SystemClock.now()` è `datetime.now(UTC)` — aware, come il contratto pretende — e
`UuidGenerator.new_uuid()` è `uuid4()`. Stanno accanto a chi è l'unico a costruirle, e sono
registrate in `tests/contracts/implementations.py`: da oggi i contratti di `Clock` e
`IdGenerator` girano anche sulle implementazioni vere, non solo sui fake.

`ELA_USER_NAME` (§3) è chi firma una risposta a un'approvazione (§8). **Vincolo dichiarato:** va
bene per un sistema a **utente singolo su loopback**. Quando arriverà l'iPhone (Fase 12),
`responded_by` diventerà un'**identità autenticata** e quel giorno il setting **sparisce**. È un
vincolo per i nodi, non una scelta permanente.

### 5. `build`: l'ordine, e ciò che ferma l'avvio

`build(settings) -> Ela` costruisce **in quest'ordine**, e ogni passo ha una ragione:

1. `SystemClock`, `UuidGenerator`;
2. il motore del database (`make_engine`), la sua directory (`0o700`), e il **controllo dello
   schema**;
3. i cinque adapter SQL e il registro dei nodi;
4. `catalogue_v01()` → `PermissionGuardian`;
5. `anthropic_provider(clock, ids, settings=…)` → `ProviderRegistry((provider,))` →
   `ModelRouter(settings.routing.policy(), registry)` — l'ordine di ADR 0022 §7, e il costruttore
   del router è il punto in cui un refuso in `ELA_MODEL_ROUTES` ferma ELA;
6. `tools_v01(root, clock, ids, router, providers)` e `verifiers_v01(root, router)` con lo
   **stesso oggetto** router: il verifier di `model.routed_as_asked` ricalcola la rotta, e due
   router con due tabelle farebbero fallire ogni verifica (ADR 0022 §10);
7. `devices.ensure_local(available_tools=tuple(t.name for t in tools.tools()))`: senza i nomi,
   l'orchestrator non trova nessun nodo idoneo e ogni task resta in attesa (ADR 0016 §4);
   e subito dopo `devices.heartbeat(LOCAL_DEVICE_ID)` — vedi §5-bis;
8. `TaskEngine`, `DeviceOrchestrator`, `Executor`, `TaskRunner`.

**Un errore di configurazione è un messaggio, non uno stack trace.** `ConfigurationError` nomina
la variabile e cosa farne, e ferma l'avvio prima di ogni lavoro: token assente o corto, host non
di loopback, `ELA_ANTHROPIC_MODEL` ancora presente (ADR 0022 §8), `ELA_MODEL_ROUTES={}`, una
rotta che nomina un provider non registrato, uno schema non migrato.

**Lo schema non viene migrato dall'avvio** — ADR 0006 l'ha già escluso, «una migrazione è
un'operazione da eseguire consapevolmente» — ma la sua assenza viene **detta**: `missing_tables`
in `ela.infrastructure.persistence` elenca le tabelle che mancano e il messaggio nomina
`uv run alembic upgrade head`. La directory del database e il workspace vengono invece creati:
crearli è già il comportamento dichiarato di ADR 0006 §3 e ADR 0013 §12.

Un provider **senza chiave non ferma niente**: si registra `UNAVAILABLE`, `/diagnostics` lo dice,
e uno step `model.complete` fallisce con `provider.unavailable` senza toccare la rete
(ADR 0020 §2). Una macchina senza chiave è una macchina su cui ELA parte.

### 5-bis. Il nodo `local` è questo processo, e lo dice

Scoperto costruendo: `ensure_local` registra il nodo `local` con `last_seen_at = None`, e un nodo
mai sentito **non è disponibile** (ADR 0016 §3). Nessuno mandava mai un heartbeat, perché
l'heartbeat lo manda il nodo — e il nodo `local` è il processo che sta leggendo questa frase.
Senza, l'orchestrator non trova mai un nodo idoneo e **ogni** task resta `waiting_device`: ELA
composta correttamente non eseguirebbe niente.

ELA lo dichiara quindi di sé stessa, e solo di sé stessa: `build` manda un heartbeat per `local`
dopo averlo registrato, e `POST /tasks/{id}/run` ne manda un altro prima di percorrere il piano —
una richiesta che viene servita è la prova che il processo è vivo. Nessuna affermazione su nodi
che ELA non è.

**Vincolo dichiarato:** un heartbeat **periodico**, e i nodi remoti che riportano sé stessi, sono
M8.3 e la storia dei nodi (§56). Fino ad allora il TTL di `ELA_DEVICE_HEARTBEAT_TTL_SECONDS` è
rinnovato solo quando ELA fa qualcosa, ed è coerente con ciò che l'heartbeat significa.

### 6. L'API: dodici rotte, su loopback

| Metodo | Percorso | Cosa fa |
|---|---|---|
| `GET` | `/health` | ELA è viva e il database risponde |
| `GET` | `/diagnostics` | com'è composta ELA adesso |
| `POST` | `/tasks` | crea un task da un intent |
| `GET` | `/tasks` | i task, filtrabili per stato |
| `GET` | `/tasks/{task_id}` | il task e lo stato dei suoi step |
| `POST` | `/tasks/{task_id}/plan` | attacca il piano e mette il task in coda |
| `POST` | `/tasks/{task_id}/run` | percorre il piano fin dove arriva |
| `POST` | `/tasks/{task_id}/approve` | il «sì» dell'utente |
| `POST` | `/tasks/{task_id}/deny` | il «no» dell'utente |
| `POST` | `/tasks/{task_id}/cancel` | ferma il task |
| `GET` | `/approvals` | le richieste che aspettano una risposta |
| `GET` | `/audit` | il registro append-only |

**Il piano entra dall'API perché il Planner non esiste** (§13): `POST /tasks/{id}/plan` fa
`start_planning` → `plan` → `queue`, e il giorno in cui il Planner arriverà prenderà esattamente
quel posto. Gli step arrivano con i loro id e le `dependencies` li citano; che formino un DAG lo
verifica `TaskGraph.from_plan` dentro `engine.plan`, come per qualunque altro piano.

**Il piano lo dice di sé stesso.** La `description` OpenAPI di `POST /tasks/{task_id}/plan` —
`PLAN_IS_TEMPORARY`, una costante, non una frase in un docstring — dice che quella forma è
temporanea, che esiste perché il Planner non esiste, e che il giorno in cui il Planner arriverà
potrà cambiare **senza un cambio di versione**. Un test di documentazione la tiene lì finché il
Planner non c'è, e fallisce apposta il giorno in cui c'è: quella frase va rivista allora, non
lasciata a promettere un cambiamento già avvenuto.

**I DTO sono espliciti**, mai `model_dump()` di un'entità del dominio: la forma sul filo è una
decisione, e un campo aggiunto al dominio domani non deve uscire dall'API perché nessuno se n'è
accorto.

**`/approvals` passa sempre `now`**: una richiesta scaduta non compare, perché `respond` la
rifiuterebbe e mostrare all'utente una domanda che non può più ricevere risposta sarebbe chiedere
l'impossibile (ADR 0015 §1, §33).

**`GET /tasks/{id}` mostra gli argomenti degli step.** Sono contenuto dell'utente (§57) che torna
**all'utente**, su loopback, dietro il suo token, e senza argomenti il dettaglio di un task non
dice che cosa quel task fa. L'audit è un'altra cosa, e la regola 23 continua a tenerli fuori di
lì. `/diagnostics` non ne mostra nessuno: dice com'è composta ELA, non che cosa sta facendo — e per
contare i task per stato li **legge tutti**, che va bene per la v0.1 e non per sempre: il debito
(`count` per stato nel `TaskRepository`) è scritto in `docs/milestones/M8.3.md`.
L'`ExecutionResult` — l'output di un tool — **non** esce dall'API in questa milestone.

**`/health` fa un giro vero al database** attraverso il port (`repository.tasks(limit=1)`): un
health che risponde senza toccare niente dice solo che il processo è acceso.

### 7. Il token: uno, statico, su ogni rotta

`ELA_API_TOKEN` è **obbligatorio**: assente o più corto di 32 caratteri, ELA non parte. Un'API
personale senza token è un'API aperta a ogni processo della macchina (§33: nel dubbio, no).
Si presenta come `Authorization: Bearer <token>` e si confronta con `secrets.compare_digest`.

Il controllo è un **middleware**, non una dipendenza per rotta: una dipendenza si può dimenticare
su una rotta nuova, un middleware no. Ne segue che anche un percorso inesistente risponde **401**
e non 404: chi non ha il token non impara nemmeno quali rotte esistono.

**Correzione della decisione 6a** (review del 2026-09-07, confermata dall'utente). La decisione
approvata spegneva *tutta* la documentazione automatica di FastAPI, schema compreso, con due
ragioni in una: che uno schema pubblico racconta la forma dell'API a chi scansiona la porta, e
che un browser non può comunque autenticarsi. Sono due cose diverse, e valgono per due oggetti
diversi.

Lo **schema** è servito, a `/openapi.json`, ed è **protetto dal middleware come ogni altro
percorso**: senza token risponde 401 esattamente come `/health` e come un percorso che non
esiste. Il lettore contro cui la decisione difendeva — quello *senza credenziali* — dietro il
middleware non esiste, e la prima ragione cade con lui. Restava un costo senza un beneficio: ciò
che il chiamante trova nello schema non è decorazione, è dove `POST /tasks/{task_id}/plan`
dichiara che la **propria forma è temporanea e senza versione** (§6), e un limite che vive solo
in un ADR è un limite che chi usa l'API non vede mai.

Le **pagine HTML** (`/docs`, `/redoc`) restano spente, e la seconda ragione basta da sola: un
browser non manda un header `Authorization`, quindi dietro il token risponderebbero 401 e
nient'altro — una pagina che non può funzionare non è una pagina da servire.

Token assente e token sbagliato ricevono **lo stesso 401**: un 403 distinguerebbe «esisti ma no»
da «non esisti».

**`/health` è protetta come tutto il resto.** È più stretto del solito, ed è voluto: siamo su
loopback, e nulla di esterno deve sapere se ELA è viva. **Vincolo dichiarato:** se un giorno
servirà un health pubblico — un supervisore, un container — sarà un **endpoint separato e senza
dettagli**, non questo aperto.

L'indirizzo è `127.0.0.1` e **solo un indirizzo di loopback è accettato**: `0.0.0.0` o un IP di
rete fermano l'avvio con un messaggio che dice perché. ELA sulla rete è la storia dei nodi (§56),
non di questa API; e un bind che vive solo in una riga di comando non è un vincolo, è
un'abitudine.

### 8. Chi risponde a un'approvazione, e la finestra 5c

`POST /tasks/{id}/approve` e `POST /tasks/{id}/deny` — due percorsi, perché un «no» è dell'utente
quanto un «sì» (§62) e non merita di essere un booleano dentro una rotta che si chiama *approve*.
Il corpo porta l'`approval_id`; `responded_by` **non** viene dal corpo ma da `ELA_USER_NAME`: un
chiamante che si desse un nome scriverebbe quel nome nell'audit, e l'audit è ciò con cui si
ricostruisce chi ha detto sì (§32).

La sequenza è quella di ADR 0015 §9, e l'ordine è la decisione:
`approvals.respond(...)` **prima**, `engine.approve` / `engine.deny` **dopo**. Se l'engine si
muovesse per primo e `respond` cadesse, il task sarebbe QUEUED con una richiesta ancora PENDING e
il retry dell'executor la richiederebbe in un ciclo.

**La finestra 5c di ADR 0015 §8 è riparata qui**, dov'era stata rinviata. Se `respond` alza
`ApprovalAlreadyAnsweredError`, l'endpoint rilegge la richiesta:

* se lo stato memorizzato è **quello che si sta chiedendo adesso** e il task è ancora
  WAITING_APPROVAL, chiama `approve`/`deny` e risponde 200: è esattamente il crash fra le due
  scritture, e la seconda chiamata lo completa;
* se lo stato memorizzato è **l'altro**, è 409: una richiesta si risponde una volta, e la seconda
  risposta non riscrive la prima;
* se lo stato memorizzato è quello chiesto ma il task **non** è più WAITING_APPROVAL, la risposta
  era già stata registrata *e* applicata: non c'è niente da completare, e l'endpoint ritorna 200
  con il task com'è. Ripetere una risposta identica non è un errore: è la stessa risposta.

**Una richiesta il cui task si è mosso non è più una domanda** (review di M8.1). Se il task è
stato fermato (§65) o è scaduto mentre aspettava, la sua richiesta resta PENDING nello store — il
record è immutabile (ADR 0015 §6) — ma rispondere non farebbe più niente: l'engine rifiuterebbe
il passaggio, e nello store resterebbe la traccia di una decisione senza effetto. Quindi
`/approvals` **non la mostra** — la stessa ragione per cui non mostra una richiesta scaduta, e lo
store non può saperlo perché tiene richieste, non task — e `approve`/`deny` la rifiutano **prima
di scrivere**, con 409. Lo stato del task si legge una volta, all'inizio, ed è lo stesso controllo
che governa le tre righe qui sopra.

Il modulo che chiama `respond` — `ela/api/approvals.py` — è l'**unica esenzione** della regola di
architettura 19, per percorso, come ADR 0015 §9 aveva promesso. Un secondo chiamante, ovunque,
resta una violazione.

### 9. Chi richiama `run()`

`POST /tasks/{id}/run`: percorre il piano fin dove arriva e ritorna l'esito. Niente in background,
nessun loop. Il `TaskRunner` ritorna e non dorme (ADR 0019 §5); questa milestone dà il **modo** di
richiamarlo, non il **momento**.

Due `run` sullo stesso task non si sovrappongono: un lock per task, e se è occupato la risposta è
**409** subito, senza mettersi in coda. L'executor non ha un lock proprio (limite in-process di
ADR 0008 §11) e due runner sullo stesso task sono un bug del chiamante, non un'attesa.

`run` manda anche l'heartbeat del nodo `local` prima di percorrere il piano (§5-bis).

**Limite dichiarato:** `run` è sincrono dentro la richiesta HTTP, quindi una `model.complete`
lenta tiene aperta la connessione. Su loopback, per un utente solo, è accettabile — ed è il primo
motivo per cui il loop autonomo (M8.3, poi il Proactive Core di §34) vorrà esistere.

### 10. Gli errori

| Situazione | Eccezione | HTTP |
|---|---|---|
| token assente o sbagliato | *(il middleware)* | `401` |
| entità inesistente | `NotFoundError` | `404` |
| id già usato | `AlreadyExistsError` | `409` |
| stato o transizione sbagliata | `TaskError` | `409` |
| lo step non è eseguibile adesso | `ExecutorError` | `409` |
| il piano non si può percorrere | `RunnerError` | `409` |
| richiesta già risposta, o scaduta | `ApprovalNotAnswerableError` | `409` |
| un `run` è già in corso su quel task | `TaskAlreadyRunningError` | `409` |
| il piano non può essere un grafo | `GraphError` | `422` |
| il corpo della richiesta non è valido | `RequestValidationError` | `422` |
| un valore che il dominio rifiuta | `ValueError` | `422` |
| il database non risponde a `/health` | `DatabaseUnavailableError` | `503` |

`GraphError` sta **sopra** la sua base `TaskError`, e non è ordine per pulizia: un `TaskError`
dice che il task non è in uno stato in cui la cosa può succedere (409), un `GraphError` dice che
il piano arrivato non può essere un grafo (422) — il chiamante deve cambiare **che cosa** manda,
non **quando**. La base resta in tabella perché `IllegalTransitionError` vive in
`ela.tasks.state_machine`, che `ela.api` non può importare (contratto 7) e non ha bisogno di
importare.

Il corpo di un errore è `{"error": {"code": …, "message": …}}`. Un errore di **configurazione**
non compare in questa tabella: non diventa mai una risposta HTTP, perché ELA con una
configurazione sbagliata non arriva ad ascoltare.

### 11. `recover()` all'avvio

Il lifespan chiama `engine.recover()` **una volta**, e il risultato finisce in `/diagnostics`. È
ciò per cui `recover` esiste: un processo che riparte dopo un crash chiude gli orfani e fa
scadere i task che aspettano una richiesta scaduta (ADR 0008 §6, ADR 0015 §6), e finora non lo
chiamava nessuno.

Ne segue che **l'avvio di ELA non è un'operazione di sola lettura**, e va detto: far ripartire il
processo fallisce i task EXECUTING silenziosi da più di `ELA_TASK_ORPHAN_AFTER_SECONDS`. È il
motivo del default lungo (§3).

**Vincolo dichiarato:** una volta all'avvio va bene per la v0.1. Il **richiamo periodico è del
Proactive Core** (§34, Fase 15), ed è un rinvio, non una dimenticanza.

### 12. Regola 27, e l'esenzione della regola 19

**Regola di architettura 27** (`concretes-named-only-by-the-composition-root`) e **contratto
import-linter 12**: fuori da `ela.providers`, `ela.infrastructure` e `ela.composition`, **nessun
modulo importa `ela.providers` o `ela.infrastructure`** — `ela.api` compreso, che riceve il mondo
costruito e non lo costruisce.

È la generalizzazione della regola 4, che oggi vale per cinque package soltanto perché erano gli
unici a cui la domanda si poneva. Con un composition root la domanda si pone a tutti, e la
risposta è che i concreti li nomina un modulo solo: è ciò che rende vera §50 («provider
abstraction») senza doverci pensare ogni volta.

**Regola 19** guadagna la sua unica esenzione, per percorso: `ela/api/approvals.py`. Resta una
regola chiusa — un secondo modulo che chiami `.respond(` è ancora una violazione, e il caso
negativo lo dimostra.

`ela.api` e `ela.composition` entrano in `CRITICAL_PACKAGES` **in questa milestone**, come chiede
CLAUDE.md: l'API è l'unica porta da cui un «sì» dell'utente entra nel sistema e l'unica che
controlla il token; il composition root decide chi parla con chi e rifiuta una configurazione
sbagliata.

## Alternative considerate

- **Il composition root dentro `ela.api`** — legherebbe la costruzione di ELA a FastAPI, e la CLI
  di M8.2 costruisce lo stesso mondo senza web framework.
- **Una classe `Settings` piatta al posto delle sette** — unificherebbe davvero, ma sposterebbe
  la validazione lontano dal codice che la usa e riaprirebbe cinque ADR per un guadagno di
  leggibilità che `Settings.load()` dà già.
- **Il token come dipendenza FastAPI invece che come middleware** — una dipendenza si dimentica
  su una rotta nuova; e le rotte della documentazione automatica non la riceverebbero comunque.
- **`/health` senza token** — comodo per un supervisore, ma su loopback non c'è nessun
  supervisore, e una rotta che risponde senza credenziali dice a chiunque scansioni la porta che
  ELA è qui.
- **`0.0.0.0` permesso con un avviso** — un avviso non è un confine; ELA sulla rete è la storia
  dei nodi, e avrà il suo ADR.
- **Un endpoint unico `/approve` con `granted: true|false`** — un «no» dell'utente merita un
  percorso, non un booleano.
- **`responded_by` dal corpo della richiesta** — chi si dà un nome scrive quel nome nell'audit.
- **`run` in background con risposta 202** — introdurrebbe lavoro che nessuno sta guardando
  dentro una milestone di composizione; il loop autonomo è M8.3.
- **Migrazione automatica all'avvio** — già scartata da ADR 0006; qui si aggiunge solo il
  messaggio che dice quale comando eseguire.
- **Nessun controllo dello schema** — trasformerebbe un errore di installazione in un
  `no such table` alla prima richiesta, lontano dalla causa.
- **La quarta esenzione della regola 21** (`DeviceRegistryPort` nominato dal composition root) —
  non serve: il root costruisce l'adapter e lo passa senza nominare il port. Un'esenzione con
  nessun codice dietro resta una porta aperta prima che qualcuno bussi.

## Conseguenze

- ELA **esiste come processo**: `uv run alembic upgrade head`, poi `python -m ela.api`, e un giro
  completo — task, piano, esecuzione, approvazione, registro — si fa da fuori senza importare
  niente.
- I contratti di `Clock` e `IdGenerator` girano anche su implementazioni vere, e non solo su
  fake: era la sola coppia di port a non averne una.
- `ela.composition` va aggiunto alle liste dei contratti import-linter come ogni package nuovo;
  `test_contracts_cover_current_packages` lo pretende da solo.
- Ogni rotta nuova è protetta senza che nessuno debba ricordarsene, e un test enumera le rotte
  dell'app per dimostrarlo.
- `uvicorn` entra fra le dipendenze e `httpx` fra quelle di sviluppo (il client ASGI dei test):
  nessun test apre un socket, e `tests/security/test_no_network.py` resta vero.

### Vincoli dichiarati, da riaprire quando serviranno

- **Lo schema del piano è superficie pubblica dell'API** finché non esiste il Planner (§13).
  Quando arriverà, `POST /tasks/{id}/plan` andrà o mantenuta come porta di servizio o chiusa con
  un ADR: oggi è l'unico modo di far girare qualcosa.
- **`ELA_USER_NAME` sparisce con l'identità autenticata dei nodi** (Fase 12).
- **`/health` protetta**: un health pubblico sarà un endpoint separato e senza dettagli.
- **`recover()` una volta all'avvio**: il richiamo periodico è del Proactive Core (Fase 15).
- **`run` sincrono dentro la richiesta**: il loop autonomo è M8.3.
- **Un token statico è un segreto in un file**, senza scadenza e senza rotazione. È il livello di
  sicurezza che questa milestone dichiara: loopback, un'identità, nessun TLS.
- **L'`ExecutionResult` non esce dall'API** (M8.3): oggi ciò che un tool ha prodotto si legge
  dove il tool l'ha scritto.
- **L'heartbeat del nodo `local` è legato a ciò che ELA fa** (§5-bis): periodico in M8.3.
