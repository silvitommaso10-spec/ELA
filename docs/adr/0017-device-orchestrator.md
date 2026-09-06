# 0017. Device Orchestrator: filtri di idoneità, punteggio esplicito, attesa invece di fallimento

- **Stato:** Accettata
- **Data:** 2026-09-07
- **Riferimenti spec:** §13, §15, §16, §17, §32, §33, §57

## Contesto

§17 dice che il Device Orchestrator «decide dove eseguire un'attività» ed elenca dodici criteri
che «può considerare». Poi fissa il principio che spiega perché la decisione deve esistere come
oggetto separato:

> Il task appartiene a ELA, non al dispositivo.

§13 lo rende un vincolo sul piano: uno step dichiara *capacità*, non un nodo, e «il piano deve
essere indipendente dal dispositivo». Quindi la scelta non può stare nel piano. E non può nemmeno
essere improvvisata al momento dell'esecuzione: oggi l'executor scrive `device_id=None` e usa la
costante `LOCAL_DEVICE = "local"` come segnaposto, che è onesto finché c'è un nodo solo e diventa
una bugia appena ce ne sono due.

M6.1 ha dato al registro la parte che mancava — la disponibilità **derivata** dall'heartbeat — e
ha lasciato un impegno esplicito (ADR 0016 §3): l'orchestrator è il secondo lettore del
`DeviceRegistryPort` e il primo che avrebbe un motivo per fidarsi della colonna `availability`,
perché è indicizzata e a portata di `SELECT`. Quell'impegno si chiude qui.

## Decisione

### 1. L'orchestrator è un servizio di `ela.devices`, non un port

Come il registro (ADR 0016 §1): `ela.devices.orchestrator.DeviceOrchestrator` è un servizio del
Core, non un'interfaccia. Un port ha senso quando esistono implementazioni alternative da
scambiare; qui non c'è un secondo candidato all'orizzonte — c'è **una politica** che deve poter
essere letta, discussa e cambiata con un ADR. Un'interfaccia con un implementatore solo
nasconderebbe la politica invece di esporla.

La decisione è divisa in due metà che non si mescolano:

- una **metà pura** — `refusals`, `score`, `choose` — senza I/O, senza orologio, senza id
  generati: si prova a tabella ed è deterministica;
- una **metà con I/O** — `DeviceOrchestrator.place` — che legge dal registro, risolve le capacità
  in tool e scrive l'evento di audit.

`DeviceOrchestrator` prende un `DeviceRegistry` (non il port), un `ToolRegistryPort`, un
`AuditLog`, un `IdGenerator` e un `Clock`.

### 2. I tratti preferiti sono un punteggio, non un filtro

§13 dice «dispositivo **preferito**», e il dominio ha tradotto quella parola in
`TaskStep.preferred_device_traits` — nomi di tratti, mai un `DeviceId`. Una preferenza che scarta
è un requisito travestito: i tratti sono la componente più pesante del punteggio
(:data:`TRAIT_POINTS`, 40 su 105 possibili), quindi il nodo con la GPU vince il rendering di §15,
ma un nodo senza GPU resta idoneo e ci gira sopra se è l'unico. È la proprietà che tiene un
sistema a un nodo capace di eseguire tutto.

### 3. «Capacità richiesta» → nodo: si passa dal tool che la implementa

Tre vocabolari diversi devono incontrarsi in un punto solo:

| Chi | Campo | Cosa contiene |
|-----|-------|---------------|
| step | `required_capabilities` | `CapabilityId` (`workspace.write_note`) |
| nodo | `available_tools` | nomi di tool (`workspace_notes`) |
| nodo | `capabilities` | tratti hardware (`gpu.cuda`) |

L'orchestrator tiene un `ToolRegistryPort` — l'unico oggetto che sa quale tool implementa una
capability — e traduce ogni capability richiesta nel nome del suo tool, che poi cerca in
`available_tools`. La forma di `available_tools` è quella già fissata dall'impegno di M6.1 per
M8.1: `tuple(tool.name for tool in tools_v01(...).tools())`.

Conseguenza fail-safe **voluta**: una capability che nessun tool implementa non solleva, finisce
in `Requirements.unresolved` e rende **ogni** nodo non idoneo. Nessuno può eseguirla, quindi non
la si tenta da nessuna parte (§33), e il task aspetta.

### 4. I filtri di idoneità

Un nodo che ne fallisce anche uno solo è scartato e non può essere scelto, qualunque punteggio
abbia. L'ordine è quello in cui i rifiuti vengono riportati.

| # | Filtro | Regola | Rifiuto | Perché |
|---|--------|--------|---------|--------|
| F1 | disponibilità | il registro lo dà `AVAILABLE` | `UNAVAILABLE` | §17 disponibilità; la colonna non si legge (ADR 0016 §3) |
| F2 | privacy | `PRIVACY_ORDER[device.privacy] <= PRIVACY_ORDER[max_privacy]` | `PRIVACY` | §17 privacy, §57, §33 |
| F3 | capacità | nessuna capability richiesta è senza tool | `UNKNOWN_CAPABILITY` | §33: nessuno può eseguirla |
| F4 | software | ogni tool richiesto è in `available_tools` | `MISSING_TOOL` | §17 capacità richiesta e software installato |
| F5 | rischio | `risk >= UNGUARDED_RISK` ⇒ `status is not DEGRADED` | `DEGRADED` | §33 |

**Il rischio alza la soglia delle prove, non entra nel punteggio.** §17 non elenca il rischio fra
i criteri; il prompt di M6.2 sì. Il rischio è l'asse del Guardian (§27, §33), e un orchestrator
che scegliesse «il nodo più sicuro» in base al rischio costruirebbe un secondo sistema di permessi
— più debole, non auditato, e in grado di *concedere*. Qui il rischio può solo togliere: da
`UNGUARDED_RISK` (`HIGH`) in su, un nodo che si dichiara `DEGRADED` non è idoneo. Un nodo
`UNKNOWN` resta idoneo: in v0.1 nessuno osserva lo stato di `local`, e una regola che escludesse
l'inosservato renderebbe ineseguibile ogni step ad alto rischio.

### 5. Il punteggio

Solo fra i nodi idonei, più alto vince. Interi e non float: due valori quasi uguali non sono un
pareggio deterministico, e un pareggio deve essere risolto da una regola, non dall'aritmetica.

| Componente | Criterio §17 | Valore |
|-----------|--------------|--------|
| `traits` | dispositivo preferito (§13) | `40 × soddisfatti // richiesti`; 0 se lo step non ne chiede |
| `network` | latenza; local first (§57) | LOCAL +20, REMOTE +5, OFFLINE 0, UNKNOWN 0 |
| `performance` | CPU, GPU, RAM | HIGH +15, MEDIUM +10, LOW +5, UNKNOWN 0 |
| `power` | consumo energetico | AC +10, BATTERY 0, UNKNOWN 0 |
| `workload` | workload attuale (§16) | `round(10 × (1 − current_workload))`; assente → 0 |
| `status` | stato (§16) | IDLE +10, UNKNOWN 0, BUSY -10, DEGRADED -20 |

Due invarianti, entrambe con un test:

- **un fatto ignoto vale zero, mai un bonus.** `UNKNOWN` non supera mai un valore noto migliore, e
  un `current_workload` non riportato non vale «scarico»: il silenzio non è un'affermazione (§33).
- **il punteggio non concede idoneità.** Filtri e punteggio sono due passaggi, non una somma con
  una soglia: un nodo con 105 punti e un rifiuto perde contro un nodo idoneo con 0.

**Pareggio: vince il primo in ordine di registrazione**, l'ordine che `DeviceRegistryPort.devices`
promette. `max` restituisce il primo massimo, quindi lo stesso registro e lo stesso step danno
sempre la stessa risposta.

I pesi sono convenzionali; ciò che conta è l'ordine che producono, ed è quello a essere stato
scelto: i tratti pesano più di tutto perché sono *il motivo* per cui un task va su un nodo invece
che su un altro (§17, la GPU per il rendering di §15), mentre rete e potenza sono preferenze a
parità di capacità. Stanno in questa tabella e `tests/docs/test_adr_orchestrator.py` la confronta
con il codice: cambiarli è un cambio di ADR, non una riga di codice.

**I pesi sono da ritarare in Fase 12, con dati reali e non a occhio** (review di M6.2). Oggi non
c'è niente da misurare: un nodo solo, nessuna rete, nessuna latenza osservata, nessuno storico di
fallimenti. `NETWORK_POINTS` in particolare approssima la latenza con la distanza, e la latenza
conterà davvero quando ci saranno nodi remoti veri e misure vere — a quel punto la taratura è un
lavoro su numeri raccolti, non un'altra stima. Fino ad allora l'ordine di questa tabella è la
politica dichiarata, non una misura.

**L'ordine di `PrivacyLevel` sta qui, non nel dominio.** `RiskLevel` ha gli operatori di confronto
nel dominio perché il catalogo, il Guardian e l'executor confrontano rischi: tre chiamanti. La
privacy la confronta un modulo solo, e ADR 0003 tiene il dominio minimo. `PRIVACY_ORDER` è
`LOCAL_ONLY` < `TRUSTED` < `CLOUD_ALLOWED`; se comparirà un secondo confrontatore, si promuove nel
dominio nella forma di `RiskLevel`, che è un cambio additivo e senza migrazione.

### 5-bis. I criteri di §17 che il dominio non porta

| Criterio §17 | Campo | Stato |
|--------------|-------|-------|
| presenza dell'utente | — | non modellato: nessun campo di `Device` lo porta |
| costo | — | non modellato: serve un modello di costo per nodo (M7/M8) |
| affidabilità | — | non modellato: serve uno storico dei fallimenti per nodo (§64, M8) |

Dichiarati come assenze, non inventati — la stessa scelta di ADR 0016 §4 per `UNKNOWN`: meglio un
buco dichiarato che un numero finto in una decisione che nessuno può verificare.

### 6. Nessun nodo idoneo: il task **aspetta**, e chi riceve l'attesa ha un comportamento definito

`place()` restituisce un `Placement` con `device=None` e **non solleva mai**. Non esiste un
percorso di errore che un chiamante possa trasformare in un fallimento.

La garanzia non è una promessa nel docstring: **`ela.devices` non importa `ela.tasks`** (regola di
architettura 22 e contratto import-linter 9). Un package che non ha alcun cammino verso il Task
Engine non può muovere un task, qualunque cosa un `place` futuro decida di fare.

**Vincolo per M6.3.** «L'orchestrator è solo consiglio» è la proprietà giusta, ma chi riceve
`Placement.device is None` deve avere un comportamento definito, altrimenti il runner lo
reinventa. Il comportamento è questo:

1. **il task resta `QUEUED`** — lo stato di §14 che significa «pronto a partire, in attesa che un
   nodo lo prenda». `WAITING` non esiste in §14 e non va aggiunto: gli stati sono verbatim dalla
   spec. Un task in `EXECUTING` che si ritrova senza nodo torna a `QUEUED`
   (`TaskEngine.queue()`, transizione già nella tabella di ADR 0004);
2. **il task non fallisce e lo step non fallisce**: nessun `fail`, nessun `fail_step`, nessun
   `ErrorMetadata`. Un nodo che manca non è un errore dell'azione, è l'assenza di un posto dove
   eseguirla;
3. **il fatto è già nell'audit**: `place()` ha scritto `DEVICE_UNAVAILABLE` con il punteggio e i
   rifiuti di ogni candidato. Il runner **non** riscrive l'attesa: un secondo evento per lo stesso
   fatto è rumore nella catena di §32;
4. **riprovare è lecito e non lascia tracce doppie di stato**: `place()` è idempotente per
   costruzione (è pura più una `append`), quindi il runner può richiamarla al giro successivo.
   Ogni chiamata aggiunge il suo evento, perché ogni chiamata è una decisione presa in un istante
   diverso su un registro che può essere cambiato.

### 7. Il log: due `AuditEventType`, non una nota sul trail

Scegliere dove eseguire è un'azione di ELA con un attore che ne risponde: sta nella catena hash di
§32, non nel trail del task come `TaskEventType.NOTE` (testo libero, non interrogabile).

| Evento | Quando | `device_id` |
|--------|--------|-------------|
| `DEVICE_SELECTED` | un nodo è stato scelto | il nodo scelto |
| `DEVICE_UNAVAILABLE` | nessun nodo era idoneo | assente |

**Due tipi e non uno con un payload**, per la ragione di ADR 0008: «un log interrogabile per tipo
— ogni rifiuto, ogni approvazione — vale più di uno filtrato sul payload». "Quante volte ELA non
ha avuto dove eseguire qualcosa" è una domanda che il log deve saper rispondere per tipo.

Attore: `ORCHESTRATOR_ACTOR = Actor(kind=SYSTEM, id="device-orchestrator")`, sul modello di
`GUARDIAN_ACTOR`. Il payload porta le richieste (tool, tratti, rischio, privacy massima, capability
irrisolte) e **ogni candidato** con il suo punteggio scomposto e i suoi rifiuti: chi indaga deve
poter ricostruire perché un nodo ha perso, non solo chi ha vinto.

**Una scrittura per chiamata**, scelta o attesa che sia. Nessuna migrazione: gli `AuditEventType`
sono colonne stringa (ADR 0006). La cautela di ADR 0016 §6 — non aggiungere un tipo di evento
senza uno scrittore reale — è rispettata: lo scrittore è l'orchestrator, in questa milestone.

### 8. La privacy richiesta è un argomento, non un campo nuovo del dominio

`TaskStep` non ha un campo `privacy`, e §13 non lo elenca fra ciò che uno step può specificare. La
privacy in §16 e §57 è un attributo del **nodo**: «quali dati possono uscire da qui».

`place(step, *, task_id, max_privacy=PrivacyLevel.LOCAL_ONLY)`: chi chiama dichiara il livello più
permissivo che tollera, e il default è il più restrittivo — una privacy non dichiarata non è un
permesso (§33, §57). **Deviazione dichiarata**, nella stessa forma di ADR 0016 §4 per
`available_tools`: il valore esiste, ma non è `ela.devices` a calcolarlo.

### 9. Il vincolo di ADR 0016 §3 diventa architettura

L'impegno lasciato aperto da M6.1 si chiude con tre regole, ognuna con il suo caso negativo in
`tests/architecture/violations.py`:

| Regola | Cosa vieta | Esenzioni |
|--------|-----------|-----------|
| 20 `device-availability-readers` | leggere `.availability` o passarlo come keyword | `ela.devices`, il mapper di persistenza |
| 21 `device-port-readers` | nominare `DeviceRegistryPort` | `ela.ports`, `ela.devices`, l'adapter SQL |
| 22 `devices-isolation` | `ela.devices` che importa `ela.tasks` | nessuna |

La 20 vieta di leggere il campo vecchio; la 21 toglie la tentazione, tenendo il port grezzo fuori
dalle mani di chi decide; la 22 è la garanzia strutturale di §6. La 22 ha anche il contratto
import-linter 9, come le altre regole sugli import.

Le esenzioni della 21 sono **tre e non quattro**: ognuna corrisponde a codice che esiste oggi e
che nomina davvero il port. Il composition root di M8.1 dovrà probabilmente nominarlo per
costruire `SqlDeviceRegistry` e passarlo a `DeviceRegistry`, ma la sua esenzione **non** è stata
aggiunta in anticipo (review di M6.2): un'esenzione senza codice che la giustifichi è una porta
aperta prima che serva, e per di più aperta su un package — `ela.api` — che potrebbe non essere
quello dove il composition root finirà. Quando servirà sarà una riga con la sua motivazione
davanti.

La 20 è una regola sui nomi, quindi ampia: colpirebbe anche un `.availability` su un oggetto che
non è un `Device`. È voluto, come per le regole 5, 12, 15 e 16 — in un repository dove quella
parola ha un significato solo, il falso positivo costa meno del falso negativo.

## Alternative considerate

- **Un `DeviceOrchestratorPort`** (era previsto dall'«Out of scope» di M6.1) — scartata: nessuna
  implementazione alternativa esiste o è prevista, e ADR 0016 §1 ha già preso la stessa decisione
  per il registro. Un port qui nasconderebbe una politica invece di esporla.
- **Aggiungere `privacy` a `TaskStep`** — scartata: §13 non lo elenca, e CLAUDE.md vieta di
  inventare comportamenti non descritti nella spec (§8).
- **Derivare la privacy dal rischio** (HIGH/CRITICAL → LOCAL_ONLY) — scartata: lega implicitamente
  due assi che il sistema tiene separati apposta, e renderebbe il Guardian e l'orchestrator due
  metà di una politica che nessuno dei due documenta per intero.
- **Uno stato `WAITING_DEVICE`** — scartata: §14 fissa dieci stati verbatim, e `QUEUED` significa
  già «pronto, in attesa che un nodo lo prenda».
- **L'orchestrator che mette lui il task in `QUEUED`** — scartata: accoppierebbe `ela.devices` a
  `ela.tasks` (e quindi al Task Engine) per applicare una transizione che dipende dallo stato in
  cui il task si trova, cosa che solo chi lo sta eseguendo sa. §6 lo scrive come vincolo per M6.3
  invece di anticiparlo male qui.
- **Il rischio come componente del punteggio** — scartata: vedi §4. Un punteggio può concedere; un
  filtro può solo togliere.
- **Un solo `AuditEventType` con un payload che distingue** — scartata per la ragione di ADR 0008:
  un log interrogabile per tipo vale più di uno filtrato sul payload.
- **Pesi in virgola mobile, o un punteggio normalizzato 0–1** — scartata: un pareggio fra due
  float quasi uguali dipende dall'ordine delle somme, e la determinatezza qui è un requisito, non
  un'eleganza.
- **Rilevare latenza, costo e affidabilità veri** — scartata: richiedono nodi remoti (M7) e uno
  storico dei fallimenti (§64). Meglio tre assenze dichiarate in §5-bis che tre numeri finti.

## Conseguenze

- §17 è coperta per i nove criteri che il dominio porta; i tre che non porta sono dichiarati in
  §5-bis e assegnati a M7/M8.
- L'impegno di ADR 0016 §3 è chiuso: nessuno legge `Device.availability` arrivando dal port nudo,
  e ora è un test di architettura invece di una convenzione.
- Il comportamento di chi riceve un `Placement` vuoto è fissato in §6: M6.3 lo applica, non lo
  reinventa.
- `ela.devices` guadagna una dipendenza da `ToolRegistryPort` — un port, quindi lecita — e resta
  senza dipendenze da `ela.tasks`, `ela.executive` e `ela.infrastructure`.
- L'executor continua a scrivere `device_id=None`: collegare la scelta all'esecuzione è M6.3, e
  farlo qui significherebbe passare all'executor un id che nessuno calcola ancora.
- `ela.devices` era già nei `CRITICAL_PACKAGES`: il 100% di branch coverage vale da subito
  sull'orchestrator.
- `tests/docs/test_adr_orchestrator.py` verifica che le tabelle di §4, §5, §5-bis, §7 e §9 non
  driftino dal codice.
