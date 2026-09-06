# 0005. Forma dei ports: async dove c'è I/O, errori nominati, tool senza Guardian, fake in `ela.testing`

- **Stato:** Accettata. §2-ter (limit=0) superata da ADR 0006 §11. `TaskRepository` estesa da ADR 0008 §2 (`add_plan`, `plan`). `CapabilityRegistryPort` ridotta a `get`, `specs` da ADR 0010 §1 (niente `register`). `PermissionGuardianPort.decide` estesa con il keyword-only `authorization_uses` da ADR 0011 §5; il Guardian di §4 è consegnato da ADR 0011. `AuthorizationStore` estesa con `consume` e ridotta senza `record_use` da ADR 0012 §3–4. `AuthorizingGuardianPort` (async, `authorize`) e `ToolRegistryPort` (sync, `get`, `tools`) introdotti da ADR 0013 §10: i port sono tredici. `VerifierPort` (async, `capability_id`, `name`, `conditions`, `verify`) e `VerifierRegistryPort` (sync, `get`, `verifiers`) introdotti da ADR 0014 §1: i port sono quindici. `ApprovalStore` (async, `add`, `get`, `for_task`, `pending`, `respond`) ed `ExecutionResultStore` (async, `add`, `get`, `for_step`) introdotti da ADR 0015 §1: i port sono diciassette.
- **Data:** 2026-09-04
- **Riferimenti spec:** §14, §15, §16, §17, §26, §27, §28, §30, §32, §33, §34, §49, §50, §51, §52, §59
- **Milestone:** M1.3

## Contesto

§49 dice che i ports "definiscono le interfacce attraverso cui il Core comunica con il mondo
esterno" e §50 ne nomina due (`ModelProvider`, `ProviderRegistry`); non dice altro sulla loro
forma. Prima di scrivere `src/ela/ports.py` sono emerse scelte che ogni milestone successiva
erediterà — Guardian (M2), Task Engine ed executor (M3, M5), persistenza, API — e che sarebbero
rompenti da cambiare dopo, perché un port è per definizione ciò su cui si appoggiano due lati.
Sono state decise in review il 2026-09-04 (`docs/milestones/M1.3.md`).

## Decisione

### 1. Async dove c'è I/O, sync dove c'è solo computazione

**Regola:** un port che attraversa un confine di I/O — persistenza, rete, un nodo, un provider,
un'attesa — è `async`; un port che calcola a partire dai suoi argomenti è sincrono. È il criterio
con cui ogni port futuro sceglie da che parte stare.

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `TaskRepository` | §14, §15 | async | `add`, `save`, `get`, `tasks`, `append_event`, `events` |
| `AuditLog` | §32 | async | `append`, `read` |
| `DeviceRegistryPort` | §16 | async | `register`, `update`, `get`, `devices` |
| `AuthorizationStore` | §30, §59 | async | `grant`, `get`, `for_capability`, `uses`, `record_use` |
| `ToolPort` | §27, §28 | async | `capability_id`, `name`, `execute` |
| `ModelProvider` | §26, §50 | async | `name`, `complete` |
| `CapabilityRegistryPort` | §28, §29 | sync | `register`, `get`, `specs` |
| `PermissionGuardianPort` | §27, §33 | sync | `decide` |
| `ProviderRegistry` | §50 | sync | `register`, `get`, `names` |
| `Clock` | §51 | sync | `now` |
| `IdGenerator` | §49 | sync | `new_uuid` |

La tabella non è illustrativa: `tests/docs/test_adr_ports.py` la confronta con i membri dei
`Protocol` di `ela.ports` e con `inspect.iscoroutinefunction`. Chi cambia uno dei due senza
l'altro rompe `make check`.

Perché non sincrono ovunque (la proposta iniziale): il Core coordinerà chiamate a provider, nodi
remoti e attese di approvazione in parallelo (§15, §17, §34). Un Core sincrono lo farebbe con
thread, e i port andrebbero riscritti proprio nella fase distribuita, quando cambiarli costa di
più. Perché non `async` ovunque: il Guardian deve essere una funzione pura da (specifica,
contesto, autorizzazione) a decisione, senza I/O dentro; renderlo `async` inviterebbe a mettergli
uno store dentro. `CapabilityRegistryPort` e `ProviderRegistry` sono tabelle in memoria di oggetti
già costruiti: se un giorno faranno discovery remota cambieranno lato con un nuovo ADR.

Test: `pytest-asyncio` con `asyncio_mode = "auto"`; i fake sono `async` dove il port lo è.

### 2. Errori nominati, letture immutabili

`ports.py` definisce `PortError` e tre sottoclassi: `NotFoundError` (un `get` su una chiave
assente), `AlreadyExistsError` (un inserimento su una chiave già presente), `NotAllowedError` (un
tool che rifiuta di eseguire). Ogni `get` solleva `NotFoundError` invece di ritornare `None`: un
`None` non gestito diventa un `AttributeError` tre chiamate più avanti, un'eccezione nominata dice
subito cosa manca. Ogni inserimento su una chiave esistente solleva `AlreadyExistsError`: non
esiste sovrascrittura silenziosa, e dove sostituire è legittimo il metodo si chiama `save` o
`update` e pretende che la chiave esista.

Ogni lettura di collezione ritorna una `tuple`, coerente con ADR 0003 §5: ciò che esce da un port
è immutabile.

### 2-bis. Le scadenze sono chiuse (review 2026-09-04)

Ogni controllo di scadenza nel sistema — `PermissionDecision.expires_at`,
`Authorization.expires_at`, `Approval.expires_at`, gli heartbeat dei nodi — usa il verso chiuso:
**scaduto se `expires_at <= now`**. Una cosa che scade in questo istante è già scaduta.
Un'implementazione che usa `<` viola il contratto. È §33 applicato al bordo: nel dubbio, non
agire. Lo stesso verso vale per i filtri temporali in lettura: `AuditLog.read(since=)` è
inclusivo (`created_at >= since`).

Verifica: `tests/contracts/test_tool.py::test_expiry_is_closed`,
`tests/testing/test_fakes.py::test_tool_expiry_is_measured_on_its_own_clock` (istante esatto),
`tests/contracts/test_audit_log.py::test_read_since_is_inclusive`.

### 2-ter. Le letture che cresceranno hanno filtri e `limit` da subito (review 2026-09-04)

- `AuditLog.read(*, task_id=None, since=None, limit=None)`: M8.1 esporrà `/audit` e M2.2 farà
  `verify_chain` sull'intero log; entrambi hanno bisogno di leggere a finestre.
- `TaskRepository.tasks(*, states=None, limit=None)`: M3.1 recupera i task `EXECUTING` senza
  heartbeat e non deve caricare tutto. `states` è un `frozenset[TaskState]`.

In entrambi i casi l'ordine resta quello di inserimento, i filtri si applicano prima di `limit`,
e `limit=0` ritorna la tupla vuota. Cambiare queste firme dopo che esistono i consumatori
costerebbe più di fissarle ora.

### 3. I payload JSON sono `ela.domain.JsonMapping`

I port non importano `pydantic` (ADR 0002, regola 2) ma gli argomenti di un tool e di una
capability sono JSON. `JsonMapping` è già esportato dal dominio ed è, per mypy,
`Mapping[str, JsonValue]`. Nessuna modifica al dominio, nessun allentamento della regola 2.

Conseguenza sui contratti import-linter: `ela.ports` importa `ela.domain`, che importa `pydantic`.
Import-linter segue le catene indirette per default e segnalerebbe `ports → domain → pydantic`
come violazione del contratto 2. I contratti 2 e 6 (quello di `ela.testing`) hanno quindi
`allow_indirect_imports = "True"`: verificano gli import diretti, che è ciò che la regola dice
("ogni `import` presente nel sorgente", ADR 0002). Le regole pytest di `rules.py` leggono l'AST e
sono sempre state dirette. Un test in `test_import_linter.py` verifica che siano esattamente questi
due i contratti a import diretti.

### 4. Il Guardian è una funzione: riceve l'autorizzazione, non lo store

```python
def decide(
    self,
    capability: CapabilitySpec,
    arguments: JsonMapping,
    *,
    task: Task | None = None,
    step: TaskStep | None = None,
    authorization: Authorization | None = None,
) -> PermissionDecision: ...
```

Il Guardian "decide sulla base di specifiche e contesto" (§27): la specifica è la
`CapabilitySpec`, il contesto sono gli argomenti (per lo scope), il task e lo step che li
richiedono e, se esiste, l'`Authorization` che coprirebbe la chiamata. Chi lo chiama (l'executor,
M5.1) recupera l'autorizzazione dall'`AuthorizationStore` e gliela passa: il Guardian non possiede
né tool né store, ed è testabile senza fake.

Contratto per ogni implementazione, verificato in `tests/contracts/test_guardian.py`: una
capability per cui il Guardian non ha una regola produce `DENIED` con un motivo (§33). Il Guardian
vero di M2 sarà registrato in `tests/contracts/implementations.py` ed erediterà il test.

### 5. Un tool riceve la decisione come dato, e la verifica

```python
async def execute(
    self, decision: PermissionDecision, arguments: JsonMapping
) -> ExecutionResult: ...
```

La decisione è il primo parametro obbligatorio: "un Tool non può essere eseguito senza una
`PermissionDecision`" (CLAUDE.md, §27, §52) diventa una firma, non una convenzione. Il contratto,
per ogni implementazione: se `outcome` non è `ALLOWED`, se `capability_id` non è quello del tool o
se `expires_at` non è successivo a `now()` del `Clock` del tool, `execute` solleva
`NotAllowedError` **prima** di fare qualsiasi cosa. È difesa in profondità rispetto all'executor:
un tool che si fida di chi lo chiama è il bypass che §28 vuole impedire.

Un tool non riceve mai il Guardian né lo store: né il costruttore né `execute` hanno parametri
tipizzati con `PermissionGuardianPort` o `AuthorizationStore`, e nessun attributo dell'istanza
soddisfa quei due `Protocol` (`tests/contracts/test_tool.py`,
`tests/architecture/test_ports.py`).

### 6. `AuditLog` ha due membri

`append(event)` e `read(*, task_id=None, since=None, limit=None)`. Nessun update, delete, clear, replace: un architecture
test (`append_only_violations`) verifica che i membri del `Protocol` siano esattamente questi due e
che nessun nome contenga una parola di modifica; il contract test lo verifica sull'API pubblica di
ogni implementazione. `append` di un evento con un id già presente solleva `AlreadyExistsError`:
sovrascrivere è modificare.

### 7. I fake vivono in `src/ela/testing`, con due regole

`ela.testing.fakes` contiene un'implementazione in-memory di ogni port, tipizzata da
`mypy --strict` e coperta dagli stessi contract test degli adapter reali. Sta sotto `src/` perché i
test delle milestone successive — e un giorno una modalità di sviluppo dell'API — la importano come
un package normale.

- **Regola 6** (`check_testing_isolation`, contratto 5): nessun modulo di `src/ela` fuori da
  `ela.testing` importa `ela.testing`. Un fake che arriva in produzione è un bug di sicurezza: un
  `FakePermissionGuardian` configurato per permettere tutto non deve essere a un import di distanza
  dalla pipeline reale.
- **Regola 7** (`check_testing_imports`, contratto 6): `ela.testing` importa solo stdlib,
  `ela.domain` ed `ela.ports`. Un fake che dipende da un provider non è più un fake.

### 8. `IdGenerator.new_uuid()` e `Clock.now()`

Un solo metodo per gli id: i `NewType` non esistono a runtime (ADR 0003 §2), il chiamante avvolge
(`TaskId(ids.new_uuid())`). `Clock.now()` promette solo un istante aware in UTC: la monotonia resta
un vincolo del Task Engine (M1.2, rinvio registrato), perché un orologio di sistema può tornare
indietro e non è il port a doverlo nascondere.

## Alternative considerate

- **Sincrono ovunque** — proposta iniziale, più semplice da testare; scartata perché la fase
  distribuita (§15, §17, §34) l'avrebbe rovesciata su tutti i port insieme.
- **`async` ovunque** — uniforme, ma spinge il Guardian verso l'I/O e obbliga ogni test di pura
  computazione a un event loop.
- **`anyio` invece di `pytest-asyncio`** — equivalente per i test; `pytest-asyncio` è il plugin
  standard con `asyncio`, e nessun port ha bisogno di un backend diverso.
- **`get` che ritorna `None`** — vedi decisione 2.
- **Un tipo `PermissionRequest` per il Guardian** — un modello fuori da §49 o un dataclass nei
  port, entrambi da motivare con un ADR per un vantaggio che oggi non c'è; i keyword argument
  dicono la stessa cosa.
- **Il Guardian con l'`AuthorizationStore` dentro** — comodo per chi lo chiama, ma trasforma una
  funzione pura in un componente con I/O e lo rende `async`.
- **Un `TaskEventStore` separato dal `TaskRepository`** — costringerebbe ogni lettura del task a
  due port; gli eventi appartengono all'aggregato (§14).
- **`AuthorizationStore` senza conteggio degli usi** — `Authorization.max_uses` esiste già nel
  dominio (M1.1, decisione 4); uno store che non sa contare lo renderebbe un campo decorativo.
- **Quattordici metodi tipizzati nell'`IdGenerator`** — quattordici modi di scrivere la stessa
  riga.
- **Verifica della decisione solo nell'executor** — un solo punto di controllo; scartata per
  difesa in profondità (§28).
- **Fake in `tests/`** — non tipizzati da `mypy --strict src/` e non importabili da un package
  di sviluppo; e non ci sarebbe la regola 6 a impedire che finiscano in produzione.
- **Contratti import-linter con catene indirette anche per ports e testing** — fedele al default
  dello strumento, ma renderebbe impossibile a `ports.py` importare il dominio, che è esattamente
  ciò che la regola 2 permette.

## Conseguenze

- Ogni port futuro sceglie sync o `async` con il criterio della decisione 1 e viene aggiunto alla
  tabella sopra, altrimenti `tests/docs/test_adr_ports.py` fallisce; se non è tra gli undici di
  M1.3, anche `tests/contracts/test_protocols.py::test_ports_are_exactly_the_eleven_required` va
  aggiornato con motivazione.
- Ogni implementazione reale di un port viene registrata in `tests/contracts/implementations.py`
  e passa gli stessi contract test del fake.
- Il Guardian di M2 nasce sincrono e senza store; l'executor di M5 recupera l'autorizzazione e
  gliela passa.
- Ogni tool verifica la decisione prima di eseguire e non riceve mai Guardian o store.
- `ela.testing` non gira mai in produzione: la regola 6 lo garantisce staticamente.
- Aggiungere un parametro con default a un port è additivo; cambiare modalità, rimuovere un
  membro o cambiare una firma richiede un ADR.
