# 0039. Il nodo macOS: dove vive il codice di un nodo, dove tiene il segreto, e che cosa fa quando il Core tace

- **Stato:** Accettata. SPEC di M12.3 approvata dall'utente il 2026-09-12, con le decisioni D1–D20
  di M12.1 e A–P di M12.2 come vincoli ereditati. Due decisioni dell'utente hanno cambiato la
  stesura: la revisione **non** si persiste sul nodo — nasce invece `GET /nodes/me` — e
  `ela node run` diventa una **terza specie** di comando invece di allargare un `==`.
- **Data:** 2026-09-12
- **Riferimenti spec:** §4, §5, §9, §16, §17, §25, §29, §48, §56, §57, §63
- **Continua:** ADR 0002 §3 (la regola 3); ADR 0013 §9 (la regola 16); ADR 0016 §3, §6; ADR 0017
  §5; ADR 0020 §2; ADR 0022 §7, §10; ADR 0023 §3, §10, §12; ADR 0024 §2, §3, §6, §7, §8; ADR 0026
  §7; ADR 0028 §1; ADR 0029 §1, §16; ADR 0030 §15; ADR 0031 §4, §6; ADR 0034 §5, §7; ADR 0035 §5;
  ADR 0037 §2, §4, §5, §7, §9, §12; ADR 0038 §4, §9, §11, §12, §13, §14, §18.
- **Estende:** ADR 0002 (una regola nuova, la 53; due allargate, la 3 e la 16; una stretta, la 28),
  ADR 0023 §2 (una sezione di configurazione nuova, `ELA_NODE_*`, e un secondo caricatore),
  ADR 0024 §3 (un comando nuovo, e **una terza specie** di comando), ADR 0037 §4 (una rotta che un
  nodo può chiamare, la sesta).

## Contesto

M12.1 ha dato a un nodo un'identità provabile e M12.2 il protocollo del lavoro, con una suite di
conformità e una prima implementazione: il **nodo finto**, in-processo, i cui tool girano nello
stesso interprete dei test. La sua mappa `UNSUPPORTED` è vuota, ed è il pin di M12.2 dec. P — il
protocollo è recitabile per intero da un'implementazione che esiste.

Questo ADR registra che cosa è successo quando la seconda implementazione è stata un **processo del
sistema operativo**: con un segreto su disco, un orologio suo, una connessione che può cadere e una
finestra di terminale che si può chiudere. Tre cose che decide sopravvivono a M12.3 e vincolano
M12.4 e M12.5 — dove vive il codice di un nodo, dove tiene il segreto, che cosa fa quando il Core
non risponde — e una quarta l'ha trovata il nodo vero e nessuno l'aveva vista prima.

## 1. Il codice di un nodo vive in `src/ela/node/`

La spec §48 disegna `nodes/macos/`, `nodes/windows/`, `nodes/ios/`, e quelle cartelle esistono, con
un `README.md` ciascuna. Il codice non va lì, e la ragione non è una preferenza: **è il livello di
verifica.** Misurato: `mypy` legge `files = ["src"]`, `coverage` legge `source = ["ela"]`,
import-linter ha `root_package = "ela"`, e ogni regola di architettura cammina
`REPO_ROOT/"src"/"ela"`. Un nodo in `nodes/macos/` sarebbe **fuori** da `mypy --strict`, fuori dalla
copertura, fuori dai quattordici contratti e fuori da tutte e cinquantatré le regole; l'unica cosa
che lo vedrebbe è `ruff`, perché il Makefile controlla l'intero repository. Sarebbe il codice meno
verificato di ELA, e terrebbe un segreto ed eseguirebbe tool.

Il precedente è del repository e non è un'analogia: le cartelle di primo livello di §48 sono
**tutte** segnaposto inerti — `voice/`, `memory/`, `vision/`, `networking/`, `security/` —, e il
codice della voce non è finito in `voice/`: sta in `src/ela/tools/voice.py`,
`src/ela/providers/elevenlabs/` e `src/ela/infrastructure/machine/darwin.py`. §48 dice «organizzata
in componenti **come**:», ed è un disegno che il repository ha già letto così nove volte.

Due conseguenze, decise dall'utente insieme alla collocazione:

1. **`nodes/` resta, e i suoi README puntano a `src/ela/node/`.** Una cartella della spec che non
   dice dove è finito il suo contenuto è una mappa che mente.
2. **Il codice comune a macOS e Windows sta dentro `src/ela/node/`**, e gli adapter di piattaforma
   nella forma di `infrastructure/machine/darwin.py`: un modulo per sistema dietro una porta, mai un
   `if platform.system()` dentro il ciclo. È la regola 37 applicata al package nuovo, ed è ciò che
   fa sì che M12.4 aggiunga **un modulo e non un ramo**.

## 2. `GET /nodes/me`: la revisione si chiede, non si ricorda

**Il buco che solo un nodo vero poteva mostrare.** Un processo che riparte ha in mano il suo file, e
quel file contiene l'id e il segreto. La **revisione** non c'è — e senza di essa non può annunciarsi,
perché `PUT /nodes/me` è condizionale (ADR 0037 §9). Fino a M12.2 nessuno se n'era accorto: la
«riavviata» del nodo finto è lo stesso oggetto Python, e la revisione gli sopravvive per costruzione.

Le tre strade senza una rotta nuova sono tutte e tre già scartate altrove dal repository:
persistere la revisione sul nodo (una cache che nessuno risincronizza: cambia la riga per mano di
qualcun altro e il nodo resta in `412` per sempre); **leggere il numero dalla prosa di un messaggio
d'errore**, che oggi è l'unico posto sul filo dove la revisione corrente compare; ri-arruolarsi,
cioè coniare una seconda identità per la stessa macchina, che è ciò contro cui esiste `O_EXCL`.

Quindi una rotta, **la sola di questa milestone**:

| Metodo | Percorso | Identità | Che cosa fa |
|---|---|---|---|
| `GET` | `/nodes/me` | un nodo | risponde la riga del nodo chiamante con la sua revisione nell'`ETag`; non scrive niente e non registra niente (ADR 0016 §6) |

Letterale e senza id, come tutte le rotte di un nodo: «l'identità **è** l'id, un nodo parla solo per
sé» (ADR 0037 §4). Il corpo è `DeviceOut`, lo stesso che `PUT /nodes/me`, l'heartbeat e la revoca già
rispondono; l'`ETag` è costruito dalla **stessa riga** che lo costruisce nell'annuncio, scritta una
volta sola, perché il nodo rimanda indietro come `If-Match` esattamente ciò che legge qui e una
differenza fra i due non sarebbe una questione di stile ma un nodo che non può annunciarsi. Le rotte
che un'identità di nodo può chiamare passano **da cinque a sei**: la tabella di ADR 0037 §4, quella
di ADR 0038 §11 e questa, **lette in unione**.

**Il `412` si rilegge una volta sola, e la seconda è il gemello.** Un nodo che rileggesse e
riannunciasse a ogni `412` toglierebbe ad ADR 0035 §5 la sua unica prova: due processi con la stessa
identità si rincorrerebbero all'infinito, ciascuno vincendo un annuncio e perdendo il successivo, e
nessuno dei due lo direbbe mai a nessuno. E **la rilettura sta sopra l'atto, non dentro**: il
contratto vuole che ogni atto restituisca ciò che il Core ha detto, e la storia 5 asserisce che il
secondo di due annunci è un `412`. Un `announce` che lo inghiottisse restituendo il `200` del
secondo tentativo è l'unica riga che romperebbe quella storia, ed è scritta qui perché è il modo
esatto in cui questa decisione si implementa male.

**Un fatto misurato che cambia la ragione e non la decisione.** Oggi **nessuna** causa lato Core
muove la revisione di un nodo: l'annuncio è l'unico scrittore (l'`UPDATE` condizionale di
`device_registry.py`), l'arruolamento l'unico a scriverla, e la revoca tocca solo `revoked_at`; non
esiste un percorso di restore né di ri-arruolamento, e la `privacy` si impone una volta sola. La
rotta non serve dunque, oggi, a risincronizzare dopo una mano altrui: serve perché **un processo
nuovo non ha nessuna revisione da cui partire**, che è il caso normale di ogni avvio e non un caso
limite. Le altre cause diventano vere il giorno in cui una di quelle strade esiste.

**Il contratto lo esercita, e `restart()` cambia significato.** Ciò che un nodo conserva è ciò che ha
scritto: l'id e il segreto — parole che il docstring di quell'atto aveva già. La revisione non è
nessuno dei due, quindi un driver che torna deve rileggerla. La storia 11 lo appunta, e la prova è
per sabotaggio: un `restart` che salta la lettura fallisce lì con
`412 identity_conflict`, «is at revision 1, not 0». **Le storie restano tredici.**

## 3. Chi esegue un tool su una macchina che il Core non è

La regola 16 diceva: solo `executive/executor.py` chiama `Tool.execute`. Si allarga di un modulo, e
la ragione è di M12.1 D1 e riguarda le **macchine**, non il codice: l'esecutore del Core resta
l'unico che esegue un tool **su questa macchina**, e il ciclo di un nodo è l'unico che ne esegue uno
**su una macchina che il Core non è**.

**Per percorso e per chiamante**, non per package: un solo modulo di `ela.node`, e dentro di esso un
solo ricevente, una locale chiamata `tool`. Un secondo modulo del nodo che eseguisse un tool, o un
ricevente diverso in quello esente, è riportato come tutto il resto — la porta è **una chiamata**, non
un file. È la forma che l'esenzione di `_executor` ha già (ADR 0019 §3), stretta di un giro.

Il nodo **non** costruisce un `ExecutionResult` e non ne manda uno: il Core lo ricostruisce dalla
busta (M12.1 D1). Gli istanti del nodo viaggiano come **dato riportato**, mai come istante della
catena.

## 4. La terza specie di comando

ADR 0024 §2 ne conosceva due: i **chiamanti**, la cui vita *è* una richiesta e che possono finire in
quattro modi, e i due **locali** — `ela init` e `ela serve` — che non aprono nessun client e quindi
«non possono né essere rifiutati né trovare la porta chiusa». `ela node run` non è né l'uno né
l'altro: un client lo apre eccome, e può essere revocato (`1`) o non trovare nessuno (`3`); ma la sua
vita non è una richiesta, e nessuna risposta lo fa tornare.

Il criterio che la definisce, che è dell'utente: **un comando la cui vita non è una richiesta.** Il
nome è `residente`, perché `locale` era preso e dice un'altra cosa e `chiamante` è preso due volte.

| Comando | Rotta | Uscite |
|---|---|---|
| `ela node run` | *(residente: il ciclo di un nodo)* | `0` `1` `2` `3` |

**Costa una parola e non una regex.** La tabella ammetteva già due forme per la colonna di mezzo — una
rotta, o una parentesi in corsivo — e **il testo della parentesi era già catturato e non lo leggeva
nessuno**. La terza specie è quella cattura che smette di essere buttata via.

**Le asserzioni si distinguono, non si allargano**, ed è il punto della decisione. `local` continua a
essere esattamente `{init, serve}` e continua a promettere due uscite, perché la ragione scritta nel
suo docstring — «`serve` avvia il processo, `init` gira prima che ce ne sia uno» — resta vera di quei
due e non lo è mai stata di questo. Allargare un `==` a un caso che la sua ragione non copre è il modo
in cui una regola smette di dire qualcosa.

Il comando non compare fra le rotte raggiungibili dalla riga di comando, perché le rotte che chiama
le chiama **da nodo**: sono classificate per nome in `NODE_ROUTES`, «non esentate per silenzio»
(ADR 0037 §4). E resta fuori dal mondo chiuso di `INVOCATIONS`, non perché non abbia uscite ma
perché **non finisce**: le tre prove parametrizzate di quel file guidano ogni comando fino alla sua
uscita, e le quattro di un residente si provano dove una condizione d'arresto c'è.

**Il codice di arruolamento non è un argomento.** `ela node run --join` lo **chiede** e lo legge da
stdin senza eco: ADR 0037 §5 lo scrive già («dal lato del nodo il codice si legge da stdin senza eco,
mai come argomento»), citando ADR 0024 §2 — «un segreto sulla riga di comando finisce nella
cronologia della shell e in `ps`».

## 5. Un nodo non conia scadenze

**Il tempo lo decide il Core** (M12.1 D6, D14). Un nodo chiede più tempo e gli viene detto; non
decide mai quando il proprio lavoro muore, perché il Core è l'unico posto che può sapere se un lavoro
si può ripiazzare o va chiuso `interrupted`, e quel giudizio poggia su un orologio che nessun altro
condivide. Un nodo che calcolasse la propria scadenza sarebbe una seconda opinione su quando una cosa
è finita, e le due andrebbero in disaccordo esattamente quando conta, su una rete lenta.

Regola 53: nessun modulo di `ela.node` costruisce un `timedelta` né passa un `expires_at=`. Leggere
il valore che l'ordine porta non è coniare — è essere informati — e la regola ne è cieca
deliberatamente. Senza questa regola «il Core decide il tempo» resterebbe una frase in un documento:
il ciclo di un nodo **legge** una scadenza, due volte, e nient'altro si accorgerebbe del giorno in cui
una di quelle letture diventasse un'aritmetica.

## 6. Il segreto di un nodo: un file, non il portachiavi

`~/.ela/node.json`, **due campi** — l'id e il segreto — creato con
`os.open(…, O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0o600)` e una `fchmod` **prima del primo byte**, in
una cartella `0o700`, fuori dall'albero di lavoro e mai dentro la workspace (ADR 0029 §1: la
workspace è ciò che §23 chiama sincronizzato). Mai stampato. `O_EXCL` non è una precauzione: un
secondo arruolamento sopra un file che c'è già butterebbe via un'identità di cui il Core ha ancora
la riga, lasciando un nodo che nessuno può revocare perché nessuno lo sa nominare.

**Non il Keychain, e per misura.** ADR 0037 §7 lasciava il punto in bianco e chiedeva a ciascuna
implementazione di riempirlo con un numero. Misurato il 2026-09-12 su macOS 26.6 (25G72), sei sonde
con un interprete `adhoc, linker-signed`, `TeamIdentifier=not set`:

| | Chi legge o scrive | Esito |
|---|---|---|
| A–B | l'interprete `uv` scrive e rilegge | **nessun dialogo**, 0,03 s e 0,02 s |
| C | una **copia byte a byte** dello stesso binario, in un altro percorso | **nessun dialogo**, 0,33 s |
| D–E | `/usr/bin/python3` e `/usr/bin/security`, firmati Apple | **dialogo, blocca** |
| F | un binario C compilato e firmato ad-hoc apposta | **dialogo, blocca** |

Il permesso non è dell'utente e non è del percorso: C legge da un percorso mai visto prima, F — un
binario diverso, dello stesso utente — viene fermato. Ciò che l'ACL riconosce è **l'identità di
codice**, il `cdhash`. Quindi ogni aggiornamento dell'interprete cambia i byte, cambia il `cdhash`, e
**il nodo smette di poter leggere il proprio segreto**, dietro un dialogo che un processo di sfondo
non ha nessuno a cui mostrare. È lo stesso muro che ADR 0029 §16 aveva già trovato per TCC, per
un'altra strada e su un altro sottosistema: TCC e il portachiavi sono due database diversi, e che si
comportino allo stesso modo era un'analogia e adesso è un fatto misurato su questa macchina.

**Il muro si abbatte una volta sola**, con un eseguibile firmato proprio di ELA — e allora tornano
insieme `launchd` e il Keychain. Fino ad allora il nodo è un comando in primo piano in un terzo
terminale, e **il prezzo è dichiarato: il nodo vive quanto la finestra.** È pagabile perché per il
Core una finestra chiusa è un nodo che tace, che è un caso che il protocollo già gestisce come
un'assegnazione che scade — non introduce nessuno stato che il Core non sappia già leggere.

## 7. Quando il Core non risponde

| Che cosa il nodo riceve | Che cosa fa |
|---|---|
| `204` sulla richiesta di lavoro | richiede, subito. Uno spegnimento pulito risponde `204` nell'istante invece di tenere la richiesta, ed è **lo stesso `204`**: il nodo non deve saperli distinguere |
| connessione rifiutata o caduta | aspetta e ritenta, con un tetto dichiarato; non si ri-arruola. Il conto si azzera a ogni risposta, così un Core che torna trova un nodo che ha dimenticato di essere stato solo |
| `401` | si ferma e lo dice: è una revoca, e un nodo revocato non ha niente da ritentare (M12.1 D13). Uno che continuasse scriverebbe un `DEVICE_REJECTED` a ogni ciclo |
| `412` sull'annuncio, la prima volta | rilegge `GET /nodes/me` e riannuncia **una volta** |
| `412` una seconda volta di fila | si ferma e lo dice: c'è un secondo processo con la sua identità (ADR 0035 §5) |
| `409` `already_running` sulla consegna | **tiene la busta** e riprova: il Core è occupato e non ha scritto niente, ed è il caso per cui D7 esiste |
| `409` `delivery.conflict`, `404`, `410` | lascia andare la busta: il Core ha già deciso, e tenerla sarebbe tenere il contenuto dell'utente per niente |
| `409` sul rinnovo | è il tetto: smette di chiedere tempo, e non si prende il tempo che gli è stato rifiutato |

I due `409` della consegna si distinguono su `error.code` e mai sullo stato, che è lo stesso.

**La busta vive in memoria e non su disco.** Scriverla significherebbe aggiungere una copia del
contenuto dell'utente su una macchina remota — con la sua vita, la sua cancellazione e le quattro
domande di §57 — per proteggere un caso che il protocollo già chiude: se il nodo muore prima di
consegnare, l'assegnazione scade e M12.1 D6 decide sull'idempotenza del tool. Il prezzo, dichiarato:
chiudere il terzo terminale fra l'esecuzione e la consegna perde una chiamata al modello già pagata.

## 8. Le regole

| N | Regola | Soggetto | Vincolo |
|---|---|---|---|
| 3 | Le librerie di infrastruttura restano ai bordi | tutto `ela` tranne `providers/`, `infrastructure/`, `api/`, `cli/`, `node/` | tutto tranne `anthropic`, `openai`, `httpx`, `sqlalchemy`, `fastapi`, `typer` |
| 16 | Solo l'esecutore chiama `Tool.execute` | tutto `ela` tranne `executive/executor.py` e, per un solo ricevente, `node/runner.py` | nessun `<x>.execute(...)` su un tool |
| 28 | La CLI parla attraverso l'API | tutto `cli/` | nessun nome che componga un mondo: `build`, `Ela`, `build_node`, `NodeWorld` |
| 53 | Un nodo non conia scadenze | tutto `node/` | nessun `timedelta(...)`, nessun `expires_at=` |

La 3 si allarga **per nome di package** e la 16 **per percorso e chiamante**: due porte, e sono il
numero che va guardato. La **27** sembrava la terza e **non serve** — `ela.node` non nomina nessun
concreto, perché a costruire i tool è `build_node()`, che sta in `ela.composition` e vi è già dentro.
Se in implementazione un nodo finisse per nominarne uno, il codice è nel package sbagliato: si
sposta, non si esenta.

## Alternative considerate

- **`nodes/macos/`, dove la spec lo disegna.** Scartata in §1: è il livello di verifica, non
  l'indirizzo.
- **Persistere la revisione accanto all'id e al segreto.** Era la stesura, e l'utente l'ha scartata:
  è una cache senza risincronizzazione, e il giorno in cui la riga cambia per mano di qualcun altro
  il nodo resta in `412` senza niente che possa toglierlo di lì. Una rotta di lettura costa una riga
  e non ha quel giorno.
- **Il Keychain.** Scartato per misura (§6), non per opinione.
- **`launchd` con `KeepAlive`.** Murato da ADR 0029 §16, che è un vincolo di Fase 12 — e questa è
  Fase 12. Sarebbe, oggi, tre cose insieme: un processo che TCC attribuisce all'interprete condiviso
  con ogni altro progetto Python di questo Mac, uno i cui permessi sparirebbero in silenzio al
  prossimo `uv python install`, e uno che riparte senza che nessuno lo sappia.
- **Allargare `local == {"init", "serve"}` a tre.** Scartata in §4: un `==` allargato a un caso che
  la sua ragione non copre è una regola che smette di dire qualcosa.
- **Un `if platform.system()` dentro il ciclo del nodo**, invece di un modulo per sistema. Scartata
  in §1: è la regola 37, e M12.4 deve aggiungere un modulo e non un ramo.
- **Una presa vera nella suite di conformità.** Scartata: `tests/conftest.py` vieta il TCP a tutta la
  suite (§57, §58), sei storie su tredici girano su un orologio finto che vive in questo processo, e
  aprire una presa vorrebbe dire toccare l'infrastruttura che M12.2 dec. P ha dichiarato «il
  contratto». Che una presa si apra e che un processo sopravviva a un segnale si prova a mano, in
  `GETTING_STARTED.md`, ed è la seconda metà del criterio di fine.

## Conseguenze

- Questo Mac è **anche** un nodo: un processo separato dal Core si arruola, legge la propria riga, si
  annuncia, chiede lavoro, esegue con i suoi tool, consegna e rinnova — e non decide niente.
- Le tredici storie del contratto passano con **due** kit, e la mappa `UNSUPPORTED` del secondo è
  **vuota**: una piattaforma vera recita il protocollo per intero.
- Il codice di un nodo vive in `src/ela/node/`, dentro `mypy --strict`, dentro la copertura, dentro i
  contratti e dentro le regole. `ela.node` entra in `CRITICAL_PACKAGES` nella stessa milestone in cui
  riceve codice.
- Le regole di architettura passano da cinquantadue a **cinquantatré**; due si allargano (3, 16), una
  si stringe (28).
- Le rotte dell'API passano da ventotto a **ventinove**, i percorsi serviti da ventinove a trenta; le
  rotte che un nodo può chiamare da cinque a **sei**.
- I comandi della CLI passano da venticinque a **ventisei**, e le specie di comando da due a **tre**.
- I contratti import-linter restano **quattordici**, nove modificati.
- Le capability di produzione **restano otto**, e le port **venticinque**: un nodo non ne introduce,
  consuma quelle che ci sono.
- Una sezione di configurazione nuova, `ELA_NODE_*`, e un **secondo caricatore**: un nodo legge
  cinque sezioni e non tredici, perché `ELA_API_TOKEN` — senza cui il caricatore del Core si rifiuta
  di partire — non è affare suo.

### Vincoli dichiarati, da riaprire quando serviranno

- **Un nodo vive quanto la sua finestra**: `launchd` richiede un eseguibile firmato proprio di ELA, e
  fino ad allora il nodo è un comando in primo piano (§6, ADR 0029 §16).
- **Il Keychain torna insieme a `launchd`**: è lo stesso muro del `cdhash`, e si abbatte una volta
  sola (§6).
- **Nessuna causa lato Core muove oggi la revisione di un nodo**: l'annuncio è l'unico scrittore, e
  `GET /nodes/me` serve oggi al processo che riparte senza niente, non a risincronizzare (§2).
- **La storia 11 non distingue un nodo che scrive la revisione da uno che la chiede**: solo un
  annuncio muove una revisione, quindi nessuna storia di un processo solo può far invecchiare un
  numero salvato — ci vuole un secondo processo, e ha una storia sua (§2).
- **La busta non consegnata vive in memoria**: chiudere il terminale fra l'esecuzione e la consegna
  perde una chiamata al modello già pagata (§7).
- **La conformità si recita in-processo**: che una presa si apra, che il processo sopravviva a un
  segnale e che il segreto si rilegga da un altro processo non li prova la suite (Alternative).
- **Le due capability per cui un secondo Mac avrebbe più senso non viaggiano**: lo schermo e il
  microfono restano sul Core, perché i loro verifier leggono *questa* macchina (M12.1 D15). È il
  prezzo di D1, già misurato, e M12.3 lo sapeva prima di cominciare.
- **Il nodo sulla stessa macchina nasconde tre accoppiamenti**: lo stesso `.env`, la stessa tabella
  di rotte, la stessa chiave. Su un secondo Mac sarebbero tre configurazioni da tenere allineate.
- **Il timeout della richiesta di lavoro è un tetto e non una misura**: un nodo non può leggere
  `ELA_NODE_POLL_SECONDS` del Core, quindi aspetta molto più a lungo del necessario (§7).
- **La finestra di long-poll del Core deve restare sotto il suo TTL di heartbeat**: un nodo manda
  un battito per giro e un giro dura quanto la finestra, quindi con una finestra più lunga del TTL
  un nodo vivo e in attesa risulterebbe `UNAVAILABLE`. Le due variabili sono entrambe del Core e
  oggi nessuno le confronta (§7; misurato il 2026-09-12: 25 s contro 60 s).
