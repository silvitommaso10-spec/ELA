# 0016. Device Registry: disponibilità derivata dall'heartbeat, nodo `local` deterministico, tabella `devices`

- **Stato:** Accettata
- **Data:** 2026-09-07
- **Riferimenti spec:** §16, §17, §32, §33, §54, §57

## Contesto

`DeviceRegistryPort` esiste da ADR 0005 con quattro operazioni — `register`, `update`, `get`,
`devices` — e un solo implementatore, `FakeDeviceRegistry`, che vive in memoria. Mancano due
cose perché §16 sia soddisfatta.

La prima è la persistenza: un registro che dimentica i nodi a ogni riavvio non è un registro.

La seconda è più sottile. §16 dice che ELA deve conoscere la **disponibilità** di un dispositivo,
e §17 dice che l'orchestratore la userà per decidere dove eseguire un task. Ma `Device.availability`
è un campo: dice cosa era vero quando qualcuno l'ha scritto, e continua a dirlo dopo che il nodo ha
smesso di rispondere. Un campo `ONLINE` su un nodo spento tre ore fa non è un dato mancante: è un
dato **sbagliato**, e §33 (nel dubbio, no) vieta di trattarlo come un sì. Serve un modo di
trasformare il silenzio in una risposta.

## Decisione

### 1. Il registro è un servizio sopra il port, non un port nuovo

`ela.devices.registry.DeviceRegistry` prende un `DeviceRegistryPort`, un `Clock` e un TTL. Il port
resta CRUD puro — è archiviazione — e la logica di §16 sta sopra. Nessuna riga di ADR 0005 cambia,
il contract test di `DeviceRegistryPort` resta valido parola per parola, e `SqlDeviceRegistry` lo
passa senza modificarlo.

`DeviceRegistry` **non** è un'implementazione del port e non è utilizzabile come tale: `register` e
`update` restituiscono il `Device` come si legge, non `None`, quindi mypy rifiuta di passarne uno
dove è atteso il port. Sono due oggetti che rispondono a due domande diverse: il port dice cosa c'è
scritto nella riga, il registro dice com'è il nodo adesso.

### 2. Il vocabolario di §16 mappato sul dominio

§16 parla di dispositivi disponibili e non disponibili; il dominio ha `DeviceAvailability` con
quattro valori. La mappatura sta in un posto solo, `ela.devices.registry.AVAILABLE` e
`UNAVAILABLE`:

| §16 | `DeviceAvailability` | Perché |
|-----|----------------------|--------|
| disponibile | `ONLINE` | il nodo ha risposto entro il TTL: è evidenza diretta |
| non disponibile | `UNREACHABLE` | silenzio: non sappiamo che sia spento, sappiamo che non parla |

`OFFLINE` sarebbe un'affermazione più forte di quanto l'assenza di un heartbeat autorizzi. Non
aggiungiamo `AVAILABLE`/`UNAVAILABLE` all'enum: sarebbero due nomi per informazioni che il dominio
già distingue, e ADR 0003 tiene gli enum minimi.

### 3. La disponibilità è **derivata in lettura**, non riscritta da uno sweeper

`DeviceRegistry.get` e `.devices` non restituiscono la colonna: calcolano
`is_available(device, now, ttl)` e sostituiscono `availability` prima di consegnare il nodo. Il
confronto usa il verso chiuso di ADR 0005 §2-bis — scaduto quando `last_seen_at + ttl <= now` — e
un nodo con `last_seen_at` assente **non** è disponibile: registrare un nodo dichiara che esiste,
non che risponde.

La conseguenza è quella che ci interessa: **non esiste un istante in cui un lettore può ricevere
`ONLINE` per un nodo silenzioso**, perché non c'è nessun processo periodico da cui dipendere. La
colonna resta come ultimo stato osservato — l'heartbeat ci scrive `ONLINE` — ma nessuno la legge da
sola, e il vincolo è che nessun chiamante fuori dal mapper legga `Device.availability` arrivando
dal port nudo: chi decide passa da `DeviceRegistry`, e l'orchestratore di M6.2 farà lo stesso.

**Impegno per M6.2.** In M6.1 questo vincolo vale per convenzione e per un test di comportamento
(`test_the_stored_row_is_not_what_a_reader_gets`), perché `DeviceRegistry` è l'unico lettore del
port. Il Device Orchestrator (§17) è il secondo lettore, ed è il primo che avrebbe un motivo per
fidarsi della colonna: gli serve sapere quali nodi sono disponibili, e `availability` è lì, indicizzata
e a portata di `SELECT`. **M6.2 rende il vincolo un test di architettura**: nessun modulo fuori da
`ela.devices` e dal mapper legge `Device.availability` arrivando da `DeviceRegistryPort`. La regola
arriva a quella milestone già assegnata, non da riscoprire.

Il TTL è un'impostazione:

| Variabile | Default | Verso |
|-----------|---------|-------|
| `ELA_DEVICE_HEARTBEAT_TTL_SECONDS` | 60 s | chiuso: scaduto quando `last_seen_at + ttl <= now` |

Un TTL nullo o negativo è rifiutato dal costruttore: renderebbe ogni nodo non disponibile
nell'istante stesso in cui riporta.

### 4. Il nodo `local`

In v0.1 esiste un solo nodo (§54). Il suo id è un UUIDv5 su un namespace fisso e il nome `local`,
quindi è lo stesso id in ogni processo e a ogni avvio: `ensure_local()` registra una volta sola,
anche dopo un riavvio, ed è idempotente per costruzione invece che per convenzione.

`local` dichiara solo ciò che si può sapere senza sondare l'hardware:

| Campo | Valore | Perché |
|-------|--------|--------|
| `name` | `local` | costante, come l'id |
| `network` | `LOCAL` | il Core gira su questo nodo |
| `privacy` | `LOCAL_ONLY` | fail-safe: una privacy non dichiarata non è un permesso (§33, §57) |
| `availability` | `UNKNOWN` | nessun heartbeat è ancora arrivato |
| `status` | `UNKNOWN` | nessuno lo osserva in v0.1 |
| `performance` | `UNKNOWN` | non sondiamo CPU, GPU né RAM |
| `power_source` | `UNKNOWN` | non sondiamo la batteria |
| `capabilities` | vuoto | idem: nessun trait rilevato |
| `available_tools` | dal chiamante | quali tool esistano dipende dal workspace root |
| `current_workload` | assente | nessuno lo calcola in v0.1 |
| `last_seen_at` | assente | mai visto: infatti nasce non disponibile |

Il sistema operativo si deduce da `platform.system()`:

| `platform.system()` | `OperatingSystem` | Nota |
|---------------------|-------------------|------|
| `Darwin` | `MACOS` | il Mac di §4 |
| `Windows` | `WINDOWS` | il PC di §5 |
| `Linux` | `LINUX` | un server |

Qualunque altro valore solleva `UnsupportedOperatingSystemError`: `OperatingSystem` non ha
`UNKNOWN` (ADR 0003) e inventare un valore metterebbe un fatto falso nel registro che l'orchestratore
legge. `IOS` non è in tabella perché nessun Core gira su un iPhone: quel nodo si registrerà dalla
rete (M7), non viene rilevato in locale.

`available_tools` è un parametro e non una chiamata a `tools_v01()`: quali tool esistano dipende
dalla radice del workspace, che il registro dei dispositivi non ha motivo di conoscere. Chi compone
il sistema (M8.1) passa i nomi; in M6.1 nessun compositore esiste ancora, e il default è vuoto.
**Deviazione dichiarata rispetto alla decisione D**: i valori sono quelli dei tool di `tools_v01`,
ma non è `ela.devices` a calcolarli.

`ensure_local()` è esplicita, non nel costruttore: un costruttore che scrive su disco è una
sorpresa, e `DeviceRegistry` deve poter essere costruito anche solo per leggere.

### 5. L'heartbeat è read-modify-write, e il rischio è circoscritto

`heartbeat(device_id)` fa `get` e poi `update` attraverso il port: due statement, non uno. Non è
la `UPDATE` condizionale di `consume` (ADR 0012 §5) o di `respond` (ADR 0015), e la differenza è
voluta, perché il rischio è di un ordine di grandezza diverso.

**Cosa può andare storto, esattamente.** Un heartbeat non scrive nulla di suo tranne `last_seen_at`
e `availability`. Se due heartbeat concorrenti sullo stesso nodo si sovrappongono, l'ultima
scrittura vince e l'unico danno possibile è che `last_seen_at` resti **il più vecchio di due istanti
entrambi recenti**: nessun campo diverso da `last_seen_at` viene perso, perché nessun altro campo è
in gioco, e il nodo resta `ONLINE` in ogni interleaving — la differenza fra i due istanti è al
massimo la durata di un heartbeat, incommensurabile rispetto a un TTL di sessanta secondi. Un
`update` di configurazione concorrente a un heartbeat è invece una vera sovrascrittura, ed è per
questo che `update` è un'operazione distinta e rara, non la via per riportare un segno di vita.

Il test `test_twenty_concurrent_heartbeats_lose_nothing_but_last_seen_at` esegue venti heartbeat
simultanei e verifica esattamente questo: ogni campo diverso da `last_seen_at` sopravvive identico,
`last_seen_at` è uno degli istanti riportati, e il nodo è disponibile.

Se un giorno l'heartbeat dovesse portare con sé dati che si possono perdere — `status` e
`current_workload` scritti da nodi diversi, o un contatore — la forma da adottare è la `UPDATE`
condizionale sul port, già progettata due volte in questo repository.

### 6. Nessun audit per l'heartbeat; la registrazione di un nodo è un fatto auditabile

Un heartbeat ogni sessanta secondi per nodo riempirebbe la catena hash di §32 di righe che non
raccontano nulla: un segno di vita non è un'azione, non ha un attore che ne risponde, e la sua
assenza è già visibile in `last_seen_at`. **L'heartbeat non si audita.**

`register` e `update` di un dispositivo sono un'altra cosa: sono cambi di configurazione — quali
macchine ELA può usare, con che livello di privacy, con che tool — e chi indaga su un'azione deve
poter ricostruire quali nodi esistevano allora. `AuditEventType` non ha oggi eventi adatti, e non
li aggiungiamo in M6.1: in v0.1 l'unico nodo è `local`, registrato dal Core stesso, e un tipo di
evento senza uno scrittore reale sarebbe uno stub.

**Vincolo per la milestone dei nodi remoti (M7).** Nel momento in cui un nodo si registra o cambia
configurazione dall'esterno — cioè quando `register`/`update` smettono di essere chiamati solo dal
Core sulla propria macchina — la registrazione di un dispositivo **deve** diventare un evento di
audit, con il suo `AuditEventType`, il suo attore (`DEVICE` per un nodo che si annuncia, `USER` per
una configurazione manuale) e il suo ADR. L'heartbeat resta fuori dall'audit anche allora.

### 7. `status` e `current_workload` arrivano dall'heartbeat

Sono campi di §16 e nessuno li calcola in v0.1. `heartbeat(device_id, *, status=None,
current_workload=None)` li accetta e li scrive **solo se dati**: un heartbeat che non dice nulla su
di essi non cancella ciò che si sapeva. Gli argomenti passano dalla validazione del dominio — il
`Device` viene rivalidato, non copiato — quindi un `current_workload` fuori da `0.0..1.0` è
rifiutato qui e non entra nel registro.

### 8. Lo schema

| Tabella | Colonne |
|---------|---------|
| `devices` | `seq`, `id`, `created_at`, `name`, `os`, `availability`, `status`, `capabilities`, `available_tools`, `performance`, `network`, `power_source`, `privacy`, `current_workload`, `last_seen_at`, `metadata` |

Forma di ADR 0006: `seq` intero autoincrementale come chiave primaria (l'ordine di registrazione
che il port promette), `id` UUID UNIQUE, enum come stringhe, `capabilities` e `available_tools`
come array JSON, `metadata` JSON. Nessuna foreign key: come `authorizations` e `approvals`, è uno
store separato dal repository. Un indice su `availability` per l'orchestratore di M6.2, con la
riserva di §3: quella colonna è l'ultimo stato osservato, non la risposta.

Migrazione `0005`, reversibile (non tocca `audit_events`, quindi la regola di `0002` non si applica).

## Alternative considerate

- **Uno sweeper periodico che riscrive le righe scadute** — scartata: introduce un processo di cui
  la correttezza di una lettura dipende, e fra due passaggi il registro mente. La derivazione in
  lettura non ha finestra.
- **`heartbeat` dentro `DeviceRegistryPort` come `UPDATE` condizionale** — scartata per M6.1: paga
  un cambio di port, di contract test e di fake per eliminare una perdita il cui danno massimo è
  qualche millisecondo di `last_seen_at` (§5). Resta la forma da adottare se l'heartbeat acquisirà
  dati che si possono perdere davvero.
- **Aggiungere `AVAILABLE`/`UNAVAILABLE` a `DeviceAvailability`** — scartata: due valori nuovi per
  distinzioni che l'enum già fa, e un dominio che cresce per adattarsi al vocabolario di un
  servizio invece del contrario.
- **Id di `local` generato con `IdGenerator`** — scartata: un id casuale per un nodo che è "questa
  macchina" produce un dispositivo nuovo a ogni avvio, e nessun `ensure` può accorgersene.
- **Rilevare capacità, RAM e GPU alla registrazione** — scartata: richiede librerie di sistema e
  produce dati che nessuno legge finché l'orchestratore non esiste (M6.2). Meglio `UNKNOWN`
  dichiarato che un numero inventato.
- **Auditare gli heartbeat** — scartata: rumore nella catena hash, e §32 vuole azioni con un attore.

## Conseguenze

- §16 è coperta: tutti gli undici aspetti sono nel `Device` persistito, e la disponibilità è
  l'unico che non poteva essere un campo statico — ora non lo è.
- M6.2 (Device Orchestrator) legge da `DeviceRegistry`, non dal port: la disponibilità che riceve
  è già giudicata, e non deve conoscere il TTL.
- `ela.devices` entra in `CRITICAL_PACKAGES` (100% di branch coverage): il registro decide se un
  nodo può essere usato, ed è la stessa famiglia di decisioni del Guardian.
- Il vincolo di §3 — nessuno legge `Device.availability` arrivando dal port nudo — oggi vale per
  convenzione e per un test di comportamento, ed è assegnato a M6.2 come test di architettura:
  l'orchestratore è il secondo lettore del port e il primo che potrebbe fidarsi della colonna.
- Il vincolo di §6 è un debito dichiarato a carico di M7, non di M6.1.
- `tests/docs/test_adr_devices.py` verifica che le tabelle di §2, §3, §4 non driftino dal codice,
  e `tests/docs/test_adr_persistence.py` che §8 e `Base.metadata` descrivano la stessa tabella.
