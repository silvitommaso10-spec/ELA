# 0007. Audit log persistente: hash chain, quattro livelli di append-only

- **Stato:** Accettata
- **Data:** 2026-09-04
- **Riferimenti spec:** §28, §32, §33, §48, §49, §51, §52, §54, §57, §58, §65
- **Milestone:** M2.2

## Contesto

§32 vuole un audit log "append-only" che dica cosa ELA ha fatto, perché, con quale autorizzazione
e con quale risultato; §65 vuole che ELA resti controllabile, e un log che chiunque può riscrivere
non controlla nulla. Il port `AuditLog` (ADR 0005 §6) ha due membri e un fake in memoria; M2.1
(ADR 0006) ha fissato come si persiste. Restava da decidere come rendere evidente una manomissione
e come chiudere, a ogni livello del software, la strada dell'update e del delete. Le decisioni
sono state approvate in review il 2026-09-04 (`docs/milestones/M2.2.md`).

## Decisione

### 1. La tabella `audit_events`

Una riga per `AuditEvent`, con le convenzioni di ADR 0006 §6. `Actor` è spezzato in `actor_kind`
e `actor_id` perché ADR 0003 lo ha reso un value object proprio per interrogare "chi"; `usage` ed
`error` sono value object senza identità e stanno in una colonna JSON ciascuno (dump in modalità
JSON: `Decimal` e UUID come stringhe), rivalidati dal dominio in lettura. "Risultato" di §32 è
`summary` + `payload` e "tool" è `tool_name`, i campi che il dominio ha dal M1.1: `result` e
`tool_id` del prompt erano i nomi di §32, non campi nuovi (decisione dell'utente). **Nessuna
chiave esterna** verso `tasks` o `authorizations`: il log è evidenza indipendente e non deve mai
rifiutare di registrare perché un'altra tabella non ha la riga (§32, §33); non c'è unit-of-work
fra port (ADR 0006 §4); e i contract test di M1.3 appendono già eventi di task mai salvati.

| Tabella | Colonne |
|---|---|
| `audit_events` | `seq`, `id`, `created_at`, `event_type`, `actor_kind`, `actor_id`, `summary`, `task_id`, `step_id`, `capability_id`, `decision_id`, `authorization_id`, `device_id`, `tool_name`, `usage`, `error`, `payload`, `prev_hash`, `row_hash` |

Come in ADR 0006, la riga è verificata contro `Base.metadata` da
`tests/docs/test_adr_persistence.py`, che da questa milestone raccoglie la tabella dello schema da
ogni ADR che ne ha una: un ADR è immutabile e ogni ADR documenta le tabelle che introduce.

### 2. La catena

`prev_hash` è il `row_hash` della riga precedente in ordine di `seq`; per la prima riga è
`GENESIS_HASH` (64 zeri). `row_hash = SHA-256(canonical(prev_hash, contenuto))` in esadecimale
minuscolo, dove il contenuto sono le colonne qui sotto — tutte tranne `seq`, che assegna il
database, e le due della catena. La forma canonica è JSON con chiavi ordinate, separatori compatti
e `ensure_ascii`, del documento `{"previous_hash": …, "record": …}`; UUID come stringa canonica,
istanti come ISO 8601 in UTC con microsecondi, colonne JSON come il loro valore, `NULL` come
`null`.

| # | Colonna hashata |
|---|---|
| 1 | `id` |
| 2 | `created_at` |
| 3 | `event_type` |
| 4 | `actor_kind` |
| 5 | `actor_id` |
| 6 | `summary` |
| 7 | `task_id` |
| 8 | `step_id` |
| 9 | `capability_id` |
| 10 | `decision_id` |
| 11 | `authorization_id` |
| 12 | `device_id` |
| 13 | `tool_name` |
| 14 | `usage` |
| 15 | `error` |
| 16 | `payload` |

L'elenco è `HASHED_COLUMNS` in `orm.py` e `tests/docs/test_adr_audit.py` lo confronta con questa
tabella. Si hasha **la forma di storage, non l'entità di dominio**: `verify_chain` ricalcola dalle
righe senza passare dal dominio (una riga con un `event_type` che l'enum non avesse più resta
verificabile) e un aggiornamento di pydantic che cambiasse la serializzazione di un `datetime` non
può invalidare un log scritto ieri. **`UNIQUE(prev_hash)`** rende impossibile un fork a livello di
database: due righe non possono avere lo stesso predecessore, e il genesis esiste una volta sola.
`UNIQUE(row_hash)` è la conseguenza (contenuti diversi, hash diversi) e costa un indice.

### 3. L'algoritmo è del Core: `ela.audit.chain`

`GENESIS_HASH`, `Link`, `ChainFault` (`BROKEN_LINK`, `ALTERED_ROW`), `ChainSummary(length,
head_hash)`, `AuditChainError(position, fault)`, `canonical_bytes`, `link_hash`,
`verify_links(links, *, after=EMPTY_CHAIN)`: funzioni pure, solo stdlib. Cosa significa
"manomesso" è una regola di sicurezza del Core, non un dettaglio di SQLite: è la separazione
capability/implementazione di §28 applicata all'audit, e §48 prevede `audit/` nel Core (decisione
dell'utente). L'adapter converte le righe in record e chiama il Core; la direzione è
`ela.infrastructure → ela.audit`, mai il contrario (regola 4, contratto 4). `verify_links` accetta
`after` per continuare da una finestra all'altra. `ela.audit` entra in `CRITICAL_PACKAGES`.

### 4. L'adapter espone solo il port; `verify_chain` è una funzione

`SqlAuditLog(engine)` ha `append` e `read` e nient'altro — nemmeno la property `engine` degli
adapter di M2.1, perché il contract test pretende che l'API pubblica sia *esattamente* quella del
port. Il harness dei contract test tiene il motore per conto suo (`SqlAuditLogHarness`).
`verify_chain(engine, *, batch_size=1000) -> ChainSummary` legge a finestre keyset per `seq` in
una sola transazione di lettura, non carica mai tutto il log (ADR 0005 §2-ter), e **solleva**
`AuditChainError` con il `seq` della prima riga incoerente (§33: un valore di ritorno si ignora,
un'eccezione no). Log vuoto: `ChainSummary(0, GENESIS_HASH)`. `read` non verifica: una lettura a
finestra non può controllare i legami fuori dalla finestra.

### 5. `append` prende il lock di scrittura prima di leggere la coda

La transazione di `append` è `BEGIN IMMEDIATE` → `SELECT row_hash … ORDER BY seq DESC LIMIT 1`
→ `INSERT`. Dimostrazione (probe del 2026-09-04, SQLite 3.53, SQLAlchemy 2.0.52, aiosqlite): con
la transazione deferred di default due `append` concorrenti da due connessioni leggono la stessa
coda e il secondo `INSERT` fallisce con `UNIQUE constraint failed: prev_hash`; con
`BEGIN IMMEDIATE` il secondo scrittore attende il lock e poi legge la coda aggiornata. Sotto il
lock nessun altro scrittore può intervenire fra lettura e insert, quindi l'unico `IntegrityError`
raggiungibile è la UNIQUE su `id`, che diventa `AlreadyExistsError` senza pre-check
(ADR 0006 §8); `UNIQUE(prev_hash)` resta il backstop contro chi scrive senza l'adapter. Funziona
perché pysqlite in modalità legacy non emette un proprio `BEGIN` se la connessione è già in
transazione; un futuro `autocommit`/`isolation_level=None` nel motore andrebbe riconsiderato, e i
test "primo statement è `BEGIN IMMEDIATE`" e "due append concorrenti su file" lo sorvegliano.

### 6. Append-only a quattro livelli, ciascuno con test negativo (§58)

1. **Adapter.** Nessun membro oltre `append`/`read` (contract test) e **regola architetturale 9**
   (`check_audit_adapter_append_only` in `tests/architecture/rules.py`): `audit_log.py` non
   importa né nomina `update`, `delete`, `merge` — come import, nome, attributo — né passa a
   `text(...)` una stringa che contenga `update`, `delete`, `replace`, `drop`. Casi in
   `violations.py`; `task_repository.py` può usare `update` (la regola guarda solo l'adapter
   dell'audit).
2. **ORM.** Un listener `before_flush` sulla classe `Session` (registrato in `orm.py`, quindi
   attivo per ogni sessione del processo, anche `AsyncSession`) solleva `AppendOnlyViolation` se
   in `dirty` o `deleted` c'è un `AuditEventRow`: la modifica muore prima di produrre SQL. Vincolo
   della review: rifiuta solo righe di `audit_events`; un test modifica un task nella stessa
   configurazione e passa.
3. **Database.** Trigger `audit_events_no_update` e `audit_events_no_delete` (`BEFORE UPDATE` /
   `BEFORE DELETE`, `RAISE(ABORT, 'audit_events is append-only')`), creati da `create_all` (DDL
   agganciata ad `after_create`) e, con lo stesso testo, dalla migrazione; un test confronta
   `sqlite_master`, perché `alembic check` non guarda i trigger. **`PRAGMA recursive_triggers=ON`
   a ogni connessione**, accanto a `foreign_keys=ON`. Dimostrazione: con il PRAGMA spento
   `INSERT OR REPLACE` su un `id` esistente ha sostituito la riga senza far scattare il trigger di
   DELETE (SQLite fa scattare i trigger di delete della risoluzione REPLACE solo con i trigger
   ricorsivi); con il PRAGMA acceso è rifiutato. Test negativi con SQL raw: `UPDATE`, `DELETE`,
   `INSERT OR REPLACE`, `REPLACE INTO`, `UPDATE OR REPLACE`, più il caso "senza trigger la riga
   cambia" e "con un motore senza PRAGMA `REPLACE` aggira il trigger".
4. **Migrazione.** `0002_audit_events.py` non ha downgrade: `downgrade()` solleva
   `NotImplementedError`. Cancellare l'audit non è mai un'operazione da tooling: chi vuole davvero
   eliminarlo lo fa a mano, con intenzione esplicita (decisione dell'utente). È la prima migrazione
   non reversibile, e la regola generale da qui in poi: **le migrazioni che toccano `audit_events`
   non hanno downgrade.** `alembic downgrade base` funziona solo da `0001`.

### 7. Cosa la catena dimostra e cosa no (§65)

Rende evidente una riga modificata sul posto, tolta dal mezzo, inserita nel mezzo o riordinata.
**Non** rileva il troncamento della coda (togliere le ultime N righe lascia una catena valida) né
una riscrittura completa da una riga in poi da parte di chi ha accesso in scrittura al file e
ricalcola gli hash. Entrambi richiedono un'àncora esterna — l'ultimo `head_hash` e `length`
custoditi fuori dal database, o un HMAC con chiave fuori dal database — ed è per questo che
`ChainSummary` espone esattamente quei due valori. La chiave e il dove sono un ADR futuro. Il
limite ha un test documentale (`test_a_truncated_tail_is_not_detected`).

## Alternative considerate

- **Hash dell'entità di dominio (`model_dump_json`)** — legherebbe la verifica alla
  serializzazione di pydantic e alla validità della riga nel dominio di oggi.
- **`seq` nell'hash** — la posizione è già codificata dal legame; `seq` non è noto prima
  dell'insert senza un'altra lettura.
- **`verify_chain` come metodo del log** — romperebbe "esattamente `append` e `read`".
- **`verify_chain` che ritorna `False`** — un booleano si ignora (§33).
- **Retry in `append` sulla UNIQUE di `prev_hash`** — con il lock il caso non si presenta; un
  retry avrebbe aggiunto un ramo non raggiungibile in produzione.
- **Chiave esterna su `task_id`** — un audit che non scrive perché manca un task è peggio di un
  audit senza integrità referenziale.
- **Downgrade che droppa la tabella** — scartato: è un delete a livello di migrazione.
- **Guardia ORM in una session factory dedicata** — non proteggerebbe una sessione costruita
  altrove.
- **HMAC con chiave** — richiede gestione di un segreto (§58): ADR futuro.

## Conseguenze

- `ela.audit` e `ela.infrastructure.persistence` sono in `CRITICAL_PACKAGES` (100% branch).
- Aggiungere una colonna ad `audit_events` cambia `HASHED_COLUMNS` e quindi gli hash delle
  righe nuove; le righe esistenti restano verificabili solo se la colonna nuova, per esse, non
  entra nel record (per esempio: la migrazione la lascia `NULL` e il record omette i `NULL` delle
  colonne aggiunte dopo). È il vincolo da risolvere nell'ADR di quella migrazione; oggi il record
  include ogni colonna hashata, `NULL` compresi.
- Ogni migrazione futura che tocca `audit_events` nasce senza downgrade.
- Un chiamante che vuole rilevare il troncamento custodisce `ChainSummary` fuori dal database.
- Il listener `before_flush` costa un `isinstance` per oggetto sporco a ogni flush del processo.
- I `PRAGMA` per connessione sono ora due; un dialetto diverso da SQLite (ADR 0006
  "Conseguenze") dovrà rivedere trigger, `BEGIN IMMEDIATE` e `recursive_triggers`.
