# 0006. Persistenza: SQLAlchemy async su SQLite, ORM separato dal dominio, migrazioni alembic

- **Stato:** Accettata. Schema esteso da ADR 0008 §2 (`task_plans`, migrazione `0003`). `record_use` (§6) sostituito da `consume`, un `UPDATE` condizionale, da ADR 0012 §5. Schema esteso da ADR 0015 §3 (`approvals`, `execution_results`, migrazione `0004`); `respond` è un `UPDATE` condizionale come `consume`.
- **Data:** 2026-09-04
- **Riferimenti spec:** §14, §15, §30, §33, §48, §51, §52, §54, §55, §57, §59
- **Milestone:** M2.1

## Contesto

§54 elenca "persistence" tra i componenti della v0.1 e §55 la colloca subito dopo il dominio:
prima dei task, della sicurezza e dell'esecuzione. I port di M1.3 (ADR 0005) dicono *cosa* il
Core chiede a chi custodisce task e autorizzazioni, non *come* viene custodito. Prima del primo
adapter reale sono emerse scelte che ogni adapter successivo (l'`AuditLog` di M2.2, il registro
dei nodi) e ogni consumatore (executor, API) erediteranno. Sono state decise in review il
2026-09-04 (`docs/milestones/M2.1.md`).

## Decisione

### 1. SQLAlchemy 2 asincrono su SQLite, con alembic

Motore `AsyncEngine` con driver `aiosqlite`, perché i port di persistenza sono `async` (ADR 0005
§1); alembic per lo schema. Le dipendenze runtime sono `sqlalchemy[asyncio]`, `aiosqlite`,
`alembic`, `pydantic-settings`. In questa versione è ammesso **solo** il dialetto `sqlite`: un
altro URL solleva `ValueError` alla creazione del motore, prima di qualunque connessione (§33,
fail-fast). Un altro dialetto arriverà con un nuovo ADR, non per caso.

### 2. Dove sta il codice: `src/ela/infrastructure/`, non `infrastructure/`

§48 mostra `infrastructure/` alla radice del repo. La distinzione fissata qui: **`src/ela/
infrastructure/` contiene gli adapter Python dei port** (persistenza, e in futuro ciò che parla
con il mondo esterno senza essere un provider di modelli né l'API); **`infrastructure/` alla
radice è per il deployment** — container, servizi, script di installazione — e non contiene
codice importabile. ADR 0002 aveva già previsto `ela.infrastructure` come package esente dalla
regola 3 (può importare le librerie di infrastruttura) e vietato dalla regola 4 (il Core non lo
importa); i contratti import-linter lo nominano tutti.

### 3. Configurazione: `ELA_DB_URL`, senza driver

`PersistenceSettings` (pydantic-settings, prefisso `ELA_`, `.env` opzionale) ha un solo campo,
`db_url`, con default `sqlite:///<home>/.ela/ela.db` calcolato quando serve, mai all'import.
L'URL si scrive senza driver: è la forma che un utente conosce e quella che alembic usa con il
driver della libreria standard; `engine.async_url` deriva `sqlite+aiosqlite` per il motore. Un
`~` nel path viene espanso.

### 4. Il motore: directory privata, chiavi esterne accese, una transazione per chiamata

`make_engine(url)` crea la directory del file se manca con permessi `0o700` (§57: il file
conterrà task, autorizzazioni e, da M2.2, l'audit), esegue `PRAGMA foreign_keys=ON` a ogni
connessione (SQLite lo tiene spento per default e lo schema si appoggia alle FK) e, per
`:memory:`, usa `StaticPool` perché ogni sessione veda lo stesso database. Gli adapter ricevono
il motore e costruiscono la propria session factory; **ogni chiamata di port è una transazione**.
Non esiste unit-of-work fra port (task e audit atomici insieme): è una decisione dell'executor
(M5) e avrà il suo ADR.

### 5. L'ORM non è il dominio: righe separate, mapper esplicito, regola 8

`orm.py` definisce `TaskRow`, `TaskEventRow`, `AuthorizationRow` e **non importa `ela.domain`**.
`mappers.py` è l'unico ponte, con una funzione per verso e per entità, campo per campo. Niente
`model_dump()` in ingresso né `model_validate(row.__dict__)` in uscita: un campo aggiunto al
dominio deve essere mappato e migrato, e `tests/infrastructure/persistence/test_mappers.py`
fallisce se manca da una delle due parti.

**Regola 8** (`check_orm_separation` in `tests/architecture/rules.py`): nessun modulo di
`src/ela` importa sia `sqlalchemy.orm` sia `ela.domain`. Una riga ORM che vedesse il dominio
potrebbe ereditarne, e un modello di dominio potrebbe essere mappato imperativamente; tenendo i
due import in moduli diversi, il mapper esplicito è l'unico ponte possibile. I repository usano
`sqlalchemy` e `sqlalchemy.ext.asyncio`, non `sqlalchemy.orm`. Import-linter non sa esprimere
"non entrambi": la regola vive solo in pytest, come la regola 5. A runtime,
`test_layers.py::test_mapped_rows_are_not_domain_models` verifica che nessuna classe mappata sia
un `BaseModel`.

**Regola 5 e il mapper.** `row_to_task` costruisce un `Task` nello stato letto dal database, e la
regola 5 (ADR 0004) riporta ogni `Task(state=…)` fuori da `state_machine.py`. Reidratare non è
transire: `infrastructure/persistence/mappers.py` è esente per nome, come `state_machine.py`, e
il caso `state-task-constructed-in-persistence` prova che l'esenzione copre solo quel file.

### 6. Lo schema

| Tabella | Colonne |
|---|---|
| `tasks` | `seq`, `id`, `created_at`, `goal`, `state`, `intent_id`, `plan_id`, `parent_id`, `deadline`, `metadata` |
| `task_events` | `seq`, `id`, `task_id`, `created_at`, `event_type`, `step_id`, `previous_state`, `new_state`, `message`, `metadata` |
| `authorizations` | `seq`, `id`, `created_at`, `capability_id`, `scope`, `granted_by`, `approval_id`, `task_id`, `step_id`, `expires_at`, `max_uses`, `metadata`, `uses` |

La tabella non è illustrativa: `tests/docs/test_adr_persistence.py` la confronta con
`Base.metadata`. Chi cambia una delle due senza l'altra rompe `make check`.

- **`seq` è la chiave primaria, l'UUID è la chiave del dominio.** I port promettono letture "in
  ordine di inserimento"; `created_at` non basta (due entità nello stesso istante) e in SQLite un
  contatore auto-incrementale esiste solo come `INTEGER PRIMARY KEY`. `id` è UNIQUE ed è ciò che le
  FK referenziano; `sqlite_autoincrement` impedisce il riuso di un `seq`.
- **Chiavi esterne reali.** `task_events.task_id → tasks.id` e `tasks.parent_id → tasks.id`
  (decisione dell'utente: il Task Graph di M3.2 si appoggia su quell'integrità). Un padre
  sconosciuto in `add`/`save` è `NotFoundError` per il padre, per **ogni** implementazione: è un
  contract test e il fake lo applica. La docstring di `TaskRepository` in `ports.py` lo dice;
  nessuna firma cambia (aggiunta additiva, ADR 0005 "Conseguenze").
- **Il contatore `uses` è una colonna della grant.** Lo store conta per conto dell'entità frozen
  (ADR 0005 §11); `record_use` è `UPDATE … SET uses = uses + 1` seguito da una rilettura nella
  stessa transazione, mai read-modify-write: venti chiamate concorrenti contano venti.
- **Enum come `String`**, non `sa.Enum`/CHECK: aggiungere uno stato non richiede la migrazione
  di una constraint; il dominio valida al rientro. **Payload come `JSON`**; le tuple di stringhe
  (`scope`) come array JSON. **UUID con `sqlalchemy.Uuid`** (CHAR(32) su SQLite, `uuid.UUID`
  in Python).

### 7. `UtcDateTime`

SQLite non ha fusi orari e il `DateTime` di SQLAlchemy scarta il `tzinfo` in scrittura; il
dominio rifiuta un `datetime` naive in lettura. Il `TypeDecorator` `UtcDateTime` rifiuta un naive
in ingresso (`ValueError`: è un bug del chiamante), scrive l'istante UTC e rilegge aware UTC,
microsecondi compresi. Nelle migrazioni la colonna è `sa.DateTime()`: una migrazione non importa
codice applicativo, per restare rieseguibile quando quel codice sarà cambiato.

### 8. Errori dal database, non da un pre-check

`AlreadyExistsError` nasce dall'`IntegrityError` della UNIQUE su `id`: la constraint è la verità
anche con due chiamate concorrenti, e nessun `SELECT` precede l'`INSERT` (verificato con
l'elenco delle query). `NotFoundError` nasce da un `SELECT` vuoto o da `rowcount == 0` su
`UPDATE`. Dove due errori sono possibili — il padre in `add`/`save`, il task in `append_event` —
il riferimento viene verificato prima, nella stessa transazione, così un fallimento di FK non
viene mai scambiato per un duplicato e non si fa parsing dei messaggi di SQLite.

### 9. Alembic

`alembic.ini` alla radice (`script_location = %(here)s/migrations`, nessun `sqlalchemy.url`),
`migrations/env.py` sincrono che legge l'URL da `sqlalchemy.url` se impostato (test) altrimenti da
`PersistenceSettings`, crea la directory, e usa `Base.metadata` salvo
`config.attributes["target_metadata"]` (il gancio del test negativo di drift); `compare_type` e
`render_as_batch` attivi per le migrazioni future su SQLite. La revisione iniziale è `0001`,
scritta a mano dall'output di autogenerate. Nessuna DDL in produzione: `create_all` esiste solo
nel harness dei test in memoria, e `test_migrations.py` dimostra che migrazioni e ORM coincidono
(`alembic check`) e che il caso negativo viene rilevato. `alembic check` gira in pytest, non come
target del Makefile: una sola sede, con il caso negativo accanto.

### 10. Coverage

`ela.infrastructure.persistence` è in `CRITICAL_PACKAGES` (100% branch): lo store delle
autorizzazioni è la memoria del Guardian, e un `uses` contato male è un'autorizzazione single-use
riusata (§30); l'`AuditLog` di M2.2 vivrà nello stesso package. La configurazione di coverage
traccia anche i greenlet, perché l'adapter async di SQLAlchemy cambia greenlet dentro il listener
di connessione.

### 11. Aggiunte in review (2026-09-04)

- **`limit` è `None` oppure ≥ 1**, per `TaskRepository.tasks` e `AuditLog.read`: un limite non
  positivo è un bug del chiamante e solleva `ValueError` in ogni implementazione. Sostituisce la
  frase "`limit=0` ritorna la tupla vuota" di ADR 0005 §2-ter: una risposta vuota a una domanda
  sbagliata nasconde il bug, e in SQLite `LIMIT -1` significherebbe "nessun limite". Helper
  `ela.ports.check_limit`, contract test su fake e SQLite.
- **I bound vivono nel dominio.** `NAME_MAX_LENGTH = 255` in `domain.py` limita `CapabilityId` e
  `Authorization.granted_by`; le colonne `String(255)` corrispondenti sono verificate contro quel
  valore da `tests/infrastructure/persistence/test_orm_types.py`, così il database non può mai
  rifiutare ciò che il dominio ha accettato. `orm.py` non può importare la costante (regola 8):
  la ripete, e il test è il legame. Le enum persistite stanno in `String(32)`; un test verifica
  ogni membro contro la lunghezza della colonna.

### 12. Aggiunta in review M2.2 (2026-09-04): WAL è la modalità di journal richiesta

`make_engine` esegue `PRAGMA journal_mode=WAL` a ogni connessione (su `:memory:` è un no-op).
Motivo: `verify_chain` (ADR 0007 §4) legge l'intero log in **una** transazione, per vedere uno
snapshot coerente — con una transazione per finestra potrebbe mancare una riga appesa a metà.
Con il rollback journal un lettore con lo snapshot aperto blocca il commit di ogni scrittore, e un
`append` attenderebbe la fine della verifica; in WAL i lettori non bloccano gli scrittori e lo
snapshot resta quello dell'inizio. Un `append` durante una verifica lunga va a buon fine e la
verifica non lo vede: `tests/infrastructure/persistence/test_audit_log.py::
test_a_long_verification_does_not_block_an_append`, con il caso negativo su un motore senza il
PRAGMA (`test_without_wal_the_append_waits_for_the_verification`) e il test sul journal mode in
`test_engine.py`. Conseguenza: accanto al file `ela.db` vivono `ela.db-wal` e `ela.db-shm`, nella
stessa directory a `0o700`; un backup copia tutti e tre (o usa l'API di backup di SQLite).

## Alternative considerate

- **Motore sincrono dentro `asyncio.to_thread`** — mescola thread e loop e urta il
  `check_same_thread` di SQLite; i port sono `async` per decisione (ADR 0005).
- **`aiosqlite` nudo, senza ORM** — niente mapper esplicito né autogenerate; il prompt chiede
  SQLAlchemy e alembic.
- **UUID come chiave primaria** — non dà l'ordine di inserimento in SQLite; `created_at` non lo
  dà nemmeno.
- **`sa.Enum` o CHECK per gli stati** — ogni nuovo stato sarebbe una migrazione di constraint.
- **Contatore degli usi in una tabella separata** — un `JOIN` per ogni lettura, per un intero.
- **`parent_id` senza FK** (proposta iniziale) — scartata in review: l'integrità serve al Task
  Graph e non c'è ostacolo nel repository; l'unica scelta era quale errore produrre.
- **Check-then-insert per `AlreadyExistsError`** — una finestra fra il check e l'insert; la
  constraint non ne ha.
- **`model_dump()`/`model_validate()` come mapper** — un campo nuovo raggiungerebbe il database
  senza test né migrazione.
- **Migrazione automatica all'avvio** — comoda, ma una migrazione è un'operazione da eseguire
  consapevolmente; `uv run alembic upgrade head`.
- **`alembic check` come target del Makefile** — due sedi per la stessa verifica; il test lo
  copre e ha il caso negativo.

## Conseguenze

- Ogni adapter futuro nel package (l'`AuditLog` di M2.2) segue lo stesso schema: righe in
  `orm.py`, mapper esplicito, `seq` per l'ordine, migrazione alembic, registrazione in
  `tests/contracts/implementations.py` con `setup`/`teardown`, 100% branch.
- Cambiare una tabella significa: riga ORM, mapper, migrazione, tabella in questo ADR; i test
  `test_mappers.py`, `test_migrations.py` e `test_adr_persistence.py` ricordano ciascun passo.
- `infrastructure/` alla radice non ospiterà mai codice Python importabile; se dovesse servire,
  è un nuovo ADR.
- Un dialetto diverso da SQLite richiede un ADR che riveda `async_url`/`sync_url`, la
  gestione della directory e la migrazione `0001` (`sqlite_autoincrement` è specifico).
- Il padre di un task deve esistere prima del figlio, per ogni implementazione del port.
