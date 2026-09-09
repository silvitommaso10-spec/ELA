# 0035. La riga di un nodo ha due metà: una ri-registrazione ne rifà una sola, e la dice

- **Stato:** Accettata
- **Data:** 2026-09-09
- **Riferimenti spec:** §16, §17, §32, §33, §54, §57
- **Continua:** ADR 0016 §4, §5, §6; ADR 0017 §6; ADR 0026 §7 e §10; ADR 0030 §8 e §15

## Contesto

`DeviceRegistry.ensure_local` esiste da M6.1 e ha sempre fatto due cose: registrare il nodo
`local` se non c'è, restituirlo se c'è. La seconda metà è il difetto, e si legge in una riga:

```python
try:
    return await self.get(LOCAL_DEVICE_ID)
except NotFoundError:
    pass
```

Restituisce la riga che trova e non guarda mai se ciò che il chiamante dichiara è ancora ciò che
la riga dice. La lista dei tool viene scritta **la prima volta** e non più: una capability aggiunta
dopo il primo avvio non diventa mai eseguibile su un'ELA che girava già.

Trovato il 2026-09-08 verificando M11.3 su questa macchina, non da un test. Uno step
`voice.speak_online` rispondeva `waiting_device` con `state QUEUED` e nessuno step eseguito; nel log
c'era la diagnosi che l'utente non ha visto —
`DEVICE_UNAVAILABLE  place step 4f1d4b3e…: no eligible node among 1: 1 MISSING_TOOL` — e il nodo
`local` dichiarava sei tool mentre il processo ne aveva sette. Su un database nuovo lo stesso step
passava al primo colpo.

**Non è un difetto della voce.** Vale identico per `perception.capture_screen` (M10.2) e
`perception.read_screen_text` (M10.3): nessuno ci era passato perché nessuno aveva mai aggiunto una
capability a un'ELA che girava già. Con la Fase 12 — nodi che vanno, vengono e cambiano capacità —
smette di essere un incidente e diventa la condizione normale.

## Decisione

### 1. Il numero dice dove sta il difetto

La riparazione è **M6.1b** e non M11.1b: la lettera dice *riparata dopo*, il numero dice *dove il
difetto vive*. Chi cerca «perché il registro non si aggiorna» deve trovarlo nella Fase 6, non
archiviato sotto la voce che è stata la prima a inciamparci.

### 2. La riga ha due metà, e `ensure_local` riconcilia

| Metà | Campi | Chi la scrive | Alla ri-registrazione |
|---|---|---|---|
| Dichiarato | `name`, `os`, `network`, `privacy`, `capabilities`, `available_tools` | chi compone ELA | sostituita |
| Osservato | `availability`, `last_seen_at`, `status`, `current_workload` | l'heartbeat | mai toccata |

La metà dichiarata è ciò che chi compone ELA sa **senza sondare niente**, ed è un'affermazione sul
codice che sta girando. La metà osservata dice cosa è stato visto del nodo, e la scrive solo
l'heartbeat.

`ensure_local(...)` riceve la verità e riconcilia: legge la riga, confronta la metà dichiarata,
**scrive solo se è diversa**. Il nome regge già — «ensure» promette di rendere vero, e finora
rendeva vera soltanto l'esistenza.

**Non solo i tool**, e la ragione è che il difetto non è dei tool: se il database viene copiato su
un'altra macchina la riga dice `MACOS` su un Linux e l'orchestratore decide su una bugia. È lo
stesso difetto con un altro campo, e ripararne uno solo vorrebbe dire tornarci. `created_at` non è
in nessuna delle due metà — una riga nasce una volta sola — e nemmeno `performance` e
`power_source`: nessuno può dichiararli senza sondare, quindi nessuno li ri-dichiara (ADR 0016 §4).

**Chi dichiara e chi decide restano separati.** Le regole 20 e 21 tengono `DeviceRegistryPort` e
`Device.availability` dentro `ela.devices`: la composition root non può leggere la riga per
confrontarla, e non deve. Chi compone continua a dire *quali tool esistono* (ADR 0016 §4); chi
decide *che la riga va cambiata* è l'unico che può leggerla.

La riga confrontata è quella del port e non quella di `get`: una `availability` derivata portata
fin lì finirebbe scritta nella colonna che può contenere solo ciò che un heartbeat ha osservato
(ADR 0016 §3). E la riconciliazione va **prima** dell'heartbeat in `build`, così la scrittura di
ELA non può perdere il segno di vita che ELA stessa sta per scrivere.

**Meno tool di prima è la risposta giusta, e arriva subito.** Una lista più corta è una lista più
corta: al primo riavvio dopo il ritiro di una capability il nodo smette di essere idoneo e uno step
che la chiede aspetta. È il comportamento voluto. E non ci sono falsi positivi da temere:
`production_tools` costruisce tutti i tool sempre, anche senza credenziali — `voice-speak-online` è
nella lista anche con `ELA_ELEVENLABS_API_KEY` assente, e fallisce a runtime con `speech.no_key` —
quindi `available_tools` è una funzione del **codice** e non della configurazione.

### 3. Due eventi di audit, col diff completo — il debito di ADR 0016 §6, pagato

ADR 0016 §6, il 2026-09-07: *«nel momento in cui `register`/`update` smettono di essere chiamati
solo dal Core sulla propria macchina, la registrazione di un dispositivo **deve** diventare un
evento di audit»*. Una scrittura automatica all'avvio è quel momento, per la ragione che §32 dà:
chi indaga su un'azione deve poter ricostruire quali nodi potevano fare cosa **allora**.

| Evento | Quando | Attore |
|---|---|---|
| `DEVICE_REGISTERED` | un nodo che ELA non conosceva | `SYSTEM` |
| `DEVICE_REFRESHED` | la metà dichiarata è cambiata | `SYSTEM` |

Due tipi e non uno con un flag, per l'argomento che ADR 0008 dà per l'engine: «una macchina è
entrata nel mondo di ELA» e «una macchina che ELA già usava adesso può fare cose diverse» sono due
domande a cui il log deve rispondere per tipo.

Il sommario porta il **diff completo** e non un conteggio: «un tool in più» non è una diagnosi, e
con sette tool *quale* è tutta la diagnosi. Quindi i nomi aggiunti e i nomi rimossi, e per gli
altri campi il prima e il dopo (`os MACOS -> LINUX`).

Lo scrive il registro: `ela.devices` è già uno scrittore di audit — l'orchestratore scrive
`DEVICE_SELECTED` e `DEVICE_UNAVAILABLE` — quindi `DeviceRegistry` guadagna un `AuditLog` come suo
fratello. L'attore è `SYSTEM` e non `DEVICE`: `DEVICE` è per un nodo che annuncia **sé stesso**, e
il giorno in cui esisterà firmerà la propria riga — che è l'identità della §5.

**Se non cambia niente non si scrive niente**: nessuna `UPDATE`, nessun evento. È ciò che rende
leggibile l'oscillazione della §5 invece che invisibile, ed è verificato contando le scritture e
non guardando la riga.

L'heartbeat resta fuori dall'audit, come ADR 0016 §6 aveva deciso: un segno di vita non è
un'azione, non ha un attore che ne risponde, e la sua assenza è già visibile in `last_seen_at`.

### 4. La regola 44: la metà osservata non si scrive per configurazione

| Regola | Nome | Su |
|---|---|---|
| 44 | `a-refresh-touches-only-what-is-declared` | `devices/refresh.py` |

Perché l'errore che qualcuno rifarà ha una forma precisa e prevedibile: ricostruire la riga con
`local_device(...)`. Quella funzione è giusta per una **nascita** — mette `availability=UNKNOWN` e
`last_seen_at=None` perché non si è ancora sentito niente — e su un **aggiornamento** cancella la
metà osservata: il nodo risulterebbe non disponibile fino all'heartbeat successivo, all'avvio che
esisteva per tenerlo utilizzabile.

Quindi il modulo che costruisce la riga riconciliata non nomina `availability`, `last_seen_at`,
`status`, `current_workload`, e non nomina `local_device`. Closed-world sui nomi come le regole 5,
12, 15, 16, 20 e 23 — costante, attributo, keyword o nome nudo — perché un campo si scrive in tutti
e quattro i modi. Nessuna esenzione. Scritta **nel commit precedente** a quello che riconcilia
(ADR 0030 §15, quarta volta).

### 5. L'identità di un nodo non è un'ultima scrittura (vincolo per la Fase 12)

Oggi due ELA con codice diverso sullo stesso database fanno **oscillare** la riga, e questa
milestone non lo impedisce: l'ultima scrittura vince, come ovunque, e l'evento di audit della §3
rende l'oscillazione leggibile invece che invisibile. Va bene finché il nodo è uno e lo scrittore è
il processo che *è* quel nodo.

> La riga di un nodo la scrive **quel nodo**. Due processi che dicono di essere lo stesso nodo non
> sono un'ultima-scrittura-vince: sono un **conflitto di identità**, e vanno trattati come tale —
> rilevati, nominati e rifiutati, non risolti dall'ordine di arrivo.

Da cui discende, per chi scriverà la Fase 12: un nodo remoto che si registra deve provare di essere
sé stesso (un'identità, non un id indovinabile — e l'id di `local` è deterministico proprio perché
è *questa* macchina); e la scrittura deve essere condizionale su ciò che il nodo credeva di aver
scritto l'ultima volta, che è la `UPDATE` condizionale che ADR 0016 §5 tiene già in tasca per il
giorno in cui l'heartbeat porterà dati che si possono perdere.

### 6. La ragione arriva all'utente, e `/diagnostics` confronta

`RunOutcome.WAITING_DEVICE` viaggiava senza ragione mentre l'orchestratore ne aveva già scritta una
precisa nell'audit. Adesso la ragione viaggia col risultato: `Run.reason`, `RunOut.reason`, la riga
di `ela task run`. `None` per ogni altro esito — un esito che si spiega da sé non ha bisogno di una
frase sotto.

**Vale per ogni motivo, non per uno.** `_summary` conta i rifiuti iterando su **tutto** l'enum
`Refusal` — `UNAVAILABLE`, `PRIVACY`, `UNKNOWN_CAPABILITY`, `MISSING_TOOL`, `DEGRADED` — quindi un
nodo scartato per privacy o per disponibilità era già reso così. Ciò che è stato aggiunto è la
**prova che resti vero**: un test che itera sull'enum e pretende, per ogni membro, un rifiuto che lo
nomini. Un membro nuovo senza una resa fallisce lì.

E una cosa sola è stata davvero costruita: **quale tool manca.** I nomi si calcolano dove la ragione
nasce (`requirements.tools - set(device.available_tools)`), che è l'unico punto che ha entrambe le
metà — in `choose` e in `confirm`, che sono i due punti in cui una ragione nasce.

`/diagnostics` porta, accanto ai tool, i nomi che questo processo ha e che la riga di `local` non
ha. Dopo la §2 il nodo non può essere indietro — *quasi* mai: può esserlo se la scrittura fallisce
(database in sola lettura) o se due ELA con codice diverso condividono il database. Quindi il
confronto ha qualcuno dietro (ADR 0026 §7) e vale la pena averlo: vuoto quasi sempre, e quando non
lo è dice esattamente cosa manca.

## Alternative considerate

- **Riparare sotto M11.1b**, dove il difetto è stato trovato — scartata: archivierebbe sotto la voce
  un difetto del registro, e chi lo cerca lo cerca nella Fase 6 (§1).
- **Riconciliare solo `available_tools`** — scartata: il difetto non è dei tool, e un database
  copiato su un'altra macchina lo rifà con `os` (§2).
- **Un `refresh_local` accanto a `ensure_local`** — scartata: due funzioni per una promessa sola, e
  la seconda sarebbe quella che qualcuno dimentica di chiamare. «Ensure» già promette di rendere
  vero.
- **Far leggere la riga a chi compone, per decidere se chiamare `update`** — scartata: le regole 20
  e 21 esistono per impedirlo, e il confronto ha bisogno di dati che solo il registro può leggere.
- **Sanare le righe già scritte con una migrazione** — scartata: non serve, la riconciliazione le
  sana al primo avvio, che è il punto.
- **Un evento di audit anche per l'heartbeat** — scartata di nuovo (ADR 0016 §6): rumore nella
  catena hash, e §32 vuole azioni con un attore.

## Conseguenze

- Una capability aggiunta dopo il primo avvio è eseguibile al riavvio successivo, e una rimossa
  smette di esserlo allo stesso riavvio. La riproduzione del 2026-09-08 ha un test, nei due versi.
- Il log di un'ELA appena costruita non è più vuoto: il primo evento di ogni database è la
  registrazione di `local`. Tre test che dicevano «catena di lunghezza zero» adesso dicono questo;
  la genesi di una catena davvero vuota resta in `tests/audit/test_chain.py`.
- `DeviceRegistry` prende un `AuditLog` e un `IdGenerator` nel costruttore, come
  `DeviceOrchestrator`: nove punti di costruzione, nessuno dei quali può ottenere un registro che
  non scrive.
- `Run`, `RunOut` e `ela task run` guadagnano un campo. Nessuna rotta nuova, nessun comando nuovo.
- La Fase 12 eredita un vincolo scritto (§5) invece di un difetto da scoprire.
- `tests/docs/test_adr_devices.py` verifica che le tabelle di §2, §3 e §4 non driftino dal codice,
  nella forma che le tabelle di ADR 0016 usano già.

### Vincoli dichiarati, da riaprire quando serviranno

- **L'identità di un nodo non è un'ultima scrittura**: due ELA sullo stesso database continuano a
  far oscillare la riga. Reso visibile, non impedito — impedirlo è la Fase 12 e vuole un'identità,
  non un lucchetto (§5).
- **Nessuna ri-registrazione periodica**: l'avvio basta, perché è quando il codice cambia. Un ciclo
  sarebbe un processo di cui la correttezza di una lettura dipende, che è ciò che ADR 0016 §3 ha già
  rifiutato per la disponibilità.
- **Una capability ritirata non riparte da sola**: uno step che aspetta un tool che non c'è più
  aspetta, ed è giusto — la decisione di ritirare una capability è di chi ha cambiato il codice.
- **L'heartbeat resta fuori dall'audit**, come ADR 0016 §6 aveva deciso e questa milestone conferma.
- **La riconciliazione scrive la riga intera**, perché il port ha solo `update(device)`: un
  heartbeat concorrente fra la lettura e la scrittura è la sovrascrittura che ADR 0016 §5 ha già
  analizzato. All'avvio precede il primo heartbeat, quindi la finestra è quella di ADR 0016 §5 e non
  una nuova; la `UPDATE` condizionale resta la forma da adottare quando servirà davvero.
