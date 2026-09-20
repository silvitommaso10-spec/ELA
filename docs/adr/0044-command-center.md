# 0044. Il Command Center: una terza identità nel registro, un tetto derivato dal socket, due regole che smettono di nominare un file, e un'impronta che suona

- **Stato:** **Proposta**. Scritta con il codice di M17.2, e cresce a ogni commit come ADR 0043:
  ogni sezione entra con ciò che la difende. Diventa **Accettata** quando la prova a mano di
  `docs/milestones/M17.2.md` è passata sul Mac vero, ai due indirizzi.
- **Data:** 2026-09-20
- **Riferimenti spec:** §6, §16, §46, §48, §57, §58, §65
- **Riferimenti design:** `docs/spec/ELA_design.md` — §2, §3, §6, §7, §8, §10, §11, §12, §14, §26,
  §29, §34 voce 9 del design.
- **Milestone:** M17.2, la seconda della Fase 17 (`docs/STATO.md`, voce 5.10).
- **Continua:** ADR 0024 §2 (la CLI è un client, non un secondo ELA); ADR 0042 (il design system
  che ogni superficie eredita); ADR 0043 (il ruolo imposto, il cookie come portatore, le pagine
  servite dal Core, le regole 55 e 57); ADR 0016 §3 (la disponibilità è derivata); ADR 0037 §5,
  §12, §15 (la metà imposta, la revoca, chi firma).

## Contesto

M12.5 ha dato a ELA la sua prima superficie che non è un terminale, e con essa la forma: le pagine
le compone `ela.api`, il browser è il client, l'identità di un browser viaggia in un cookie, i
modelli stanno in `apps/<superficie>/`. M17.2 eredita quella forma e ci costruisce il Command
Center — la dashboard di §2 del design —, e nel farlo scopre le tre cose che la forma aveva
lasciato aperte: **chi è il browser del Mac**, **quanto vede**, e **che cosa tiene vera la
promessa che ogni milestone aggiunga la sua vista**.

Le decisioni sono del revisore, prese in tre giri il 2026-09-20 sulla SPEC della milestone, e sono
scritte lì con le loro alternative. Qui sta ciò che ne discende nell'albero.

## 1. Un terzo ruolo, e nessuna migrazione

`DeviceRole` prende `CONSOLE`. Il portatore fa parte del ruolo, come in ADR 0043 §1:

| Ruolo | Chi | Portatore della credenziale | Rotte |
|---|---|---|---|
| `WORKER` | ogni nodo, e `local` | l'header `Authorization` | `NODE_ROUTES` |
| `COMPANION` | il browser predefinito dell'iPhone | il cookie `ela_companion` | le pagine di `/companion` |
| `CONSOLE` | il browser del Mac | il cookie `ela_console` | le pagine di `/console` |

**Non si riusa il cookie del companion.** `COMPANION` è una restrizione — vede e risponde, non
comanda (M12.5, punto fermo 3) — e una console che cresce a ogni milestone la renderebbe finta: il
giorno in cui il Command Center saprà avviare un task, quel potere sarebbe arrivato al telefono
senza che nessuno l'abbia deciso. Un'identità per browser, come per il telefono.

**Nessuna migrazione, e il perché.** `devices.role` ed `enrollments.role` sono `String(32)`, non
nulle, con `server_default='WORKER'` (`0011_device_role.py`): non c'è un `CHECK`, non c'è un tipo
enumerato nativo, e un terzo valore è una stringa nuova in una colonna che c'è già. Nessuna riga
esistente cambia significato, e il `server_default` resta giusto per la ragione di `0010` e di
`0011`: una riga scritta da qualcosa che non è il mapper di ELA è un nodo che lavora, e una console
nata per difetto sarebbe una console per cui nessuno ha coniato un codice.

**I rifiuti sono quelli di ADR 0043 §3, e arrivano gratis**: il ruolo è già una condizione della
`UPDATE` che spende il codice, ed è parametrico. Un codice presentato sulla rotta di un altro ruolo
non tocca nessuna riga, quindi **non si consuma**.

**Nessun sistema dichiarato è rifiutato, `IOS` compreso.** La prima stesura rifiutava `IOS` per una
console; la ragione non reggeva, e il revisore l'ha tolta. Il sistema dichiarato **non governa
niente** in una console — non le rotte, non il tetto, non le pagine — e il cookie funziona da
qualunque browser: quel rifiuto non avrebbe impedito a un iPhone di usare la console, avrebbe
impedito solo di **dichiararlo**, lasciando nel registro una riga che dice `MACOS` dove c'è un
telefono. E che un telefono non veda il contenuto locale lo tiene §2, che guarda il socket e non la
dichiarazione. **Un rifiuto che non può raggiungere ciò che nomina rende il registro meno vero, non
più sicuro.**

**Una console non è mai disponibile**, e non è stato scritto niente per ottenerlo: `is_available`
dice già `device.role is DeviceRole.WORKER`, al positivo (ADR 0043 §1). Ciò che M17.2 aggiunge è la
prova che non serve — un test che cammina **ogni** membro di `DeviceRole` che non è `WORKER` — così
un quarto ruolo è già camminato il giorno che esistesse.

**L'attore è `USER` con l'id della console** (ADR 0037 §15), e **non si eredita**: `Identity.actor`
diceva `USER if kind is COMPANION else DEVICE`, e un quinto `Kind` avrebbe preso l'`else` firmando
`DEVICE` in silenzio. È diventata una corrispondenza **esaustiva** sui membri di `Kind`, senza ramo
di scarto: un membro nuovo rompe `mypy --strict`, e un test cammina i membri — il tipo ferma chi ne
aggiunge uno, il test ferma chi gli dà il ramo sbagliato.

## 2. Il tetto di una console si deriva dal socket, non dal registro

Il livello efficace di un'identità `CONSOLE` è `LOCAL_ONLY` **quando i due capi del socket sono di
loopback** — il peer *e* il sockname —; altrimenti è quello che l'utente le ha imposto
all'arruolamento.

- **`may_see()` non cambia**, e il fail-safe nemmeno: un livello assente, da una delle due parti,
  resta un no. Ciò che cambia è il **valore** che `Identity.privacy` porta.
- **Il calcolo sta dove l'identità si risolve**, nel middleware: chi sta chiamando è una domanda
  sola e ha già un posto solo (regola 47). Una pagina che guardasse il socket sarebbe una seconda
  risposta alla stessa domanda.
- **Il validatore dell'arruolamento non si tocca, e non prende esenzioni**: nessun codice porta
  `LOCAL_ONLY`, console compresa. La ragione scritta in `EnrollmentIn` parla della **collocazione
  del lavoro** — «un nodo remoto a quel livello riceverebbe ogni task» — e non copre un'identità
  che lavoro non ne prende; ma **un livello inciso nel registro non sa dove sia il browser, e il
  socket sì**. Allargare ciò che si può scrivere in una riga risponderebbe alla domanda sbagliata:
  la domanda non è «di chi è questo browser», è «da dove sta chiamando adesso».
- **È vincolata al ruolo**: solo una `CONSOLE` viene promossa. Un `WORKER` su loopback no, un
  `COMPANION` su loopback no. Una promozione che valesse per chiunque arrivi da lì sarebbe una
  porta, non una derivazione.
- **La condizione è la coppia, e non il peer da solo.** P0 ha misurato che una connessione entrata
  dall'interfaccia della tailnet porta l'indirizzo della tailnet su **entrambi** i capi: un
  pacchetto con la partenza falsificata a `127.0.0.1` lascerebbe il sockname a `100.76.92.39`, e la
  coppia non combacia. Il sockname non lo sceglie chi chiama: lo scrive il sistema operativo quando
  accetta la connessione. Niente di ciò che il chiamante **dichiara** viene letto — nessun header,
  nessun `Host`, nessun `X-Forwarded-For`.

**Chi legge `Identity.privacy`**, censito con una ricerca sull'albero perché questa decisione gli fa
portare un valore che nel registro non c'è:

| Dove | Che cosa fa |
|---|---|
| `api/security.py`, la costruzione dell'`Identity` | l'**unico** posto che lo scrive, ed è dove il livello efficace si calcola |
| `api/companion.py`, `may_see` | l'**unico** lettore in produzione, per tutte e due le superfici |
| `tests/api/test_companion.py` | costruisce un'`Identity` con un tetto per provare `may_see` |

Uno scrittore e un lettore: è ciò che rende questa decisione una riga e non una politica sparsa.
Chi aggiungerà un lettore deve sapere che quel valore è **della richiesta** e non della riga — e
che il registro non cambia: dopo una richiesta promossa la riga porta ancora il livello imposto, e
l'audit di quella richiesta non scrive `LOCAL_ONLY` da nessuna parte. Un tetto che si scrivesse da
qualche parte sarebbe un tetto cambiato senza che l'utente l'abbia deciso.

**E la pagina dice quale tetto è in vigore, nei due versi.** Dalla tailnet, che il contenuto resta
sul Mac; su loopback, che si vede **perché si sta leggendo da questa macchina**. Non solo quando
nasconde: una pagina che parlasse solo mentre nasconde lascerebbe credere che il tetto non esista
quando non nasconde. È anche l'unico modo di vedere a occhio il rischio che nessun test può vedere
— se un giorno qualcosa inoltrasse le connessioni attraverso il loopback, una console aperta dal
telefono direbbe «si vede perché stai leggendo da questa macchina», e chi la guarda se ne accorge.

## 3. Due regole smettono di nominare un file

Le regole 55 e 47 camminavano un nome scritto a mano, e con due superfici sarebbero diventate due.
Adesso **derivano il loro insieme**, e alla terza superficie non si toccano.

**La regola 55 — le pagine leggono le rotte.** Un modulo di pagine è un modulo di `api/` che
**dichiara un `APIRouter` e nomina il compositore**: serve pagine come rotte. È la stessa forma che
lascia fuori il middleware **senza un'esenzione** — `api/security.py` compone due rifiuti ma non
dichiara nessun router e non serve niente, ed è l'unico modulo che *deve* leggere il mondo, perché
risponde a «chi sta chiamando» (regola 47). Il compositore non è nell'insieme per la stessa ragione
e senza nessuna riga: non importa sé stesso e non costruisce un router.

**La regola 47 — chi decide chi sta chiamando è uno solo.** I nomi dei cookie si leggono dalla
**tavola delle superfici** del middleware: il `cookie=` di ogni `Surface(...)`, risolto anche
attraverso le costanti del modulo. Statico, perché i rilevatori non importano `ela` — il caso
negativo si prova su un albero sintetico — e un cookie nuovo è camminato il giorno in cui la
superficie che lo porta viene scritta.

**Una derivazione che smette di derivare è un fallimento**, per tutte e due: `tests/architecture/test_layers.py`
pretende che l'insieme dei moduli di pagine non sia vuoto e che i cookie siano quelli delle
superfici, e ha il caso negativo di ciascuna — un albero senza moduli di pagine, un middleware
senza tavola. Una regola che non cammina nessun file passa sempre.

## 4. Le pagine: undici rotte, un compositore che impara la superficie

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/console/` | la home: la presenza, che cosa sta succedendo, le tre tessere |
| `GET` | `/console/approvals` | l'Approval Center: le domande che aspettano |
| `GET` | `/console/approval` | una domanda, con le sue parti; `?id=` |
| `POST` | `/console/answer` | il sì o il no, e dopo un sì il `run` |
| `GET` | `/console/devices` | il Device Center |
| `GET` | `/console/task` | l'execution summary di un task; `?id=` |
| `GET` | `/console/cancel` | la conferma di fermare un task; `?id=` |
| `POST` | `/console/cancel` | il modulo della conferma |
| `POST` | `/console/enroll` | il modulo con il codice: `303` e il `Set-Cookie` |
| `GET` | `/console/tokens.css` | i token del design system, da `apps/` |
| `GET` | `/console/components.css` | i componenti del design system, da `apps/` |

Nessun id nel percorso: nella query o nel corpo, per la ragione di ADR 0038 §11. `/console` senza
la barra è terreno della console come tutto ciò che gli sta sotto, e **il `Path` del cookie si
scrive senza la barra** — misurato in C1 su Chrome 152 e Safari 26.6: con `Path=/console` il cookie
arriva a `/console`, `/console/` e `/console/sotto/x`, e non a `/consolex`, a `/` e a
`/favicon.ico`.

**Il compositore resta uno** (regola 57) e impara la superficie: la cartella dei modelli, il
prefisso con cui scrive l'`href` dei fogli, il controllo d'avvio che cammina **tutte** le cartelle,
e una cache per superficie invece di una sola. La `Content-Security-Policy` resta una costante, la
stessa per tutte e due, e `sheets=None` — la pagina di arruolamento, l'unica servita prima che
un'identità esista — non ha un default che possa vestire una pagina per distrazione.

**Il middleware cammina la tavola** invece di conoscere le superfici per nome: `surface_of(path)`
dice di chi è un percorso, e da lì vengono il cookie da leggere, il ruolo da pretendere, le rotte
ammesse e i modelli con cui comporre il rifiuto. `COMPANION_PREFIX`, `COMPANION_HOME`,
`COMPANION_ROUTES`, `COMPANION_CODE_ROUTES` e `COMPANION_COOKIE` **restano**: sono i campi della
prima voce, non una seconda copia, e i test di ADR 0040 e ADR 0043 li importano per nome.

**Il «sì» ha una condotta sola.** «Rispondi, e se il task è tornato `QUEUED` percorrilo» vive in
`api/approvals.py` — il modulo che possiede il «sì», l'unica esenzione per percorso della regola 19
— e le due pagine la chiamano. Una funzione dalla parte delle rotte è ciò che una pagina ha il
diritto di chiamare (regola 55); un terzo modulo senza router sarebbe un posto che la regola 55 non
cammina.

**Il contatore dei rifiuti anonimi ha una voce sola per un fatto solo**, e si rinomina:
`core_on_a_companion_route` diventa **`core_on_a_page`**. Il fatto è «il token del Core su una
pagina», e non diventa due fatti perché ci sono due prefissi; ma il nome di ieri, con due
superfici, direbbe una cosa falsa a chi legge `/diagnostics`. **Il nome vecchio è superato**:
`docs/milestones/M12.5.md` lo nomina tre volte e resta com'è — è la storia di quella milestone — e
si legge con questa riga accanto.

## 5. Le quattro viste, e le assenze che si dichiarano

La home con la presenza e le tre tessere (§7, §8 del design), l'Approval Center (§14, §29),
il Device Center (§11, §12) e un task come **execution summary** (§10). Ogni vista mostra solo ciò
che sta già in una rotta, e in v1 **nessuna rotta è cresciuta**.

Ciò che non si mostra, con la ragione, perché un'assenza taciuta è indistinguibile da un vuoto:

- **il dispositivo in una domanda**, perché quando la domanda nasce il piazzamento non è deciso e
  il livello sì (ADR 0038 §16); **le conseguenze** e **la reversibilità**, perché il catalogo non le
  dichiara (ADR 0043, dec. F); **`EDIT`**, perché modificare una domanda non esiste in ELA;
- **CONTEXT** e **MODEL** dell'esempio di §10 del design: il contesto di §44 è quello della
  macchina e non di un task, e nessuna rotta dice quale modello ha eseguito uno step —
  `ProviderUsage` non ha il nome del modello, e `ErrorMetadata.model` esiste solo dopo un
  fallimento;
- **il contenuto di un risultato**, che resta sulla sua rotta con la sua regola 29 — **e il
  riassunto lo dice**: nomina che il risultato c'è e dove si legge, invece di finire con
  «completato» come se il task non avesse prodotto niente. La milestone che darà la vista del
  contenuto trova scritto qui che qui mancava;
- **la vista dell'orchestrazione** di §12 del design: nessuna rotta espone un `Assignment`, e
  ADR 0043 §9 ha già dato quella casa alla Fase 13. Di §12 la console mostra i due fatti separati —
  la disponibilità derivata e l'ultimo contatto.

Le tre etichette di §11 del design — WORK NODE, **POWER NODE**, COMPANION NODE — **non** sono i tre
ruoli: il Mac e il PC sono tutti e due `WORKER`, e ciò che li distingue là è la potenza, che il
registro tiene in `performance`. La vista mostra il ruolo *e* quella, e non inventa un'etichetta
che il registro non ha.

**Gli stati della presenza restano tre** — `WAITING APPROVAL`, `WORKING`, `IDLE` — e l'elenco si
estende di zero: la console legge le stesse rotte del telefono più `/devices` e `/tasks/{id}`, e
nessuna porta un fatto nuovo sullo stato di ELA. I dieci perché no sono scritti, uno per uno con la
loro fonte, in `docs/milestones/M17.2.md` (dec. H). Nessuno stato è memorizzato e nessuno entra nel
dominio.

**Il tema è scuro, sempre.** ADR 0042 §6 dice che seguire `prefers-color-scheme` è «una riga di
ogni superficie»; quella riga non può essere una riga, e lo diciamo qui. I token del tema chiaro
sono emessi solo sotto `[data-theme="light"]`, e una custom property che contiene `var()` si
risolve dove è dichiarata (ADR 0042 §2): una superficie che volesse seguire il sistema dovrebbe
riemettere l'intero blocco chiaro dentro una `@media`, cioè tenere una copia del design system
dentro una superficie — il rischio per cui M17.1 genera i suoi file per intero. La media query va
**derivata dal generatore**, ed è un cambio al design system, non una scelta di una superficie.

## 6. L'impronta: la regola della vista diventa un allarme

`scripts/generate_command_center.py` scrive `apps/command-center/capabilities.txt` — gli id delle
capability di `production_catalogue()`, in ordine — e un test lo riconfronta **byte per byte** a
ogni `make check`. Una capability nuova fa fallire la suite.

**Che cosa dimostra, e che cosa no**, scritto nell'intestazione del file perché lo legga chi ci
arriva con la suite rossa: nessuna delle capability di oggi ha una vista propria fra le quattro di
v1 — si vedono di riflesso, nella domanda dell'Approval Center e nello step di un task —, quindi
un'impronta che dicesse «ognuna ha la sua vista» nascerebbe falsa. È **l'elenco di ciò che ELA
sapeva fare quando il Command Center è stato costruito**: un allarme, non una dimostrazione.

**E l'allarme ha una risposta scritta**: quando suona, la risposta va nel **documento della
milestone che l'ha fatto suonare** — la vista che aggiunge, oppure la riga che dice perché quella
capability non ne ha una — e solo dopo si rigenera. Rigenerare e basta riporterebbe il file a
decorazione: un file che cambia senza che nessuno abbia detto niente.

Il generatore **importa `ela`**, e non è il primo: `generate_stato.py` importa già `ela.api` e
`production_catalogue` per contare. Quello che non importa `ela` è `generate_design_system.py`, per
una ragione che qui non vale — il design system non è parte del Core, l'impronta sì.

## 7. Vincoli dichiarati

Ciò che M17.2 **non** fa, o fa a un prezzo, detto una volta e per intero:

- **La console non prende lavoro e non manda heartbeat**: non è mai disponibile, per costruzione e
  per ruolo, qualunque sia il suo ultimo contatto.
- **Un'identità per browser e per indirizzo**: il cookie non attraversa né i browser né gli host, e
  chi apre il Command Center a due indirizzi ha due console (misurato, C1).
- **Il cookie porta una credenziale durevole**, senza rotazione, per 400 giorni; `Secure` no, perché
  è `http` sulla tailnet (la cifratura è di WireGuard, ADR 0037 §2).
- **Chi ha il cookie può fermare i task dell'utente e leggere ciò che il tetto gli concede**; la
  revoca è il rimedio.
- **La console aperta sull'indirizzo della tailnet mostra ciò che mostra il telefono**: il tetto
  efficace è quello imposto all'arruolamento, e solo su loopback diventa `LOCAL_ONLY`. È il prezzo
  della derivazione dal socket, ed è voluto.
- **La promozione crede alla coppia degli indirizzi del socket** — peer *e* sockname — e a niente
  che chi chiama dichiari. Vale finché niente **inoltra** le connessioni attraverso il loopback; su
  questa macchina Tailscale non lo fa, misurato in P0 su tre casi.
- **Il Command Center v1 osserva e risponde**: approva, rifiuta, ferma. Non avvia task, non mette in
  pausa, non cambia dispositivo né priorità: quelle rotte non esistono.
- **Il tema è scuro sempre**, anche su un Mac in tema chiaro.
- **La presenza mostra tre stati**, e i dieci restanti hanno la loro ragione scritta.
- **L'Approval Center non nomina il dispositivo, le conseguenze e la reversibilità**, e non ha
  `EDIT`.
- **L'execution summary non porta CONTEXT né MODEL**, perché nessuna rotta li ha.
- **Non porta nemmeno l'`output`** — e lo **dice**: nomina che il risultato esiste e dove si legge,
  invece di finire con «completato» come se non ci fosse niente. La milestone che darà la vista del
  contenuto trova qui scritto che qui mancava.
- **Un «sì» dalla console fa ripartire il task nella stessa richiesta**, dalla stessa funzione del
  telefono, e il browser può smettere di aspettare: il `run` continua (ADR 0043 §6).
- **Il prefisso `/console` si vede da chi bussa senza credenziali**, come `/companion`.
- **Il contatore dei rifiuti anonimi ha una voce sola per «il token del Core su una pagina»**, e si
  chiama `core_on_a_page`: `core_on_a_companion_route` è superato.
- **ELA gira dal repository**: il percorso di `apps/` si deriva dal package.
- **`apps/command-center/` non entra in `CRITICAL_PACKAGES`**: non è Python, e le sue regole vivono
  nei test della sua cartella (ADR 0042 §10).

## Conseguenze

- **Un terzo membro di `DeviceRole`**, senza migrazione, e il mondo chiuso su **tutti** i membri
  passa a questo ADR: ADR 0043 continua a documentarne due, che sono quelli che ha visto.
- **Un quinto `Kind`** nel middleware, e `Identity.actor` esaustivo senza ramo di scarto.
- **Una tavola di superfici** in `api/security.py`, da cui il middleware, la regola 47 e i due
  conteggi delle rotte derivano ciò che prima era scritto a mano.
- **Undici rotte nuove** sotto `/console/`, e `/openapi.json` non le descrive: una pagina non è una
  forma del filo.
- **Nessuna regola di architettura nuova**: due estese, la 55 e la 47, e tutte e due hanno perso il
  nome scritto a mano. Una regola nuova con lo stesso contenuto sarebbe una seconda difesa della
  stessa porta.
- **Nessun port nuovo**, **nessun tipo di evento nuovo**, **nessuna variabile d'ambiente nuova**, e
  `uv.lock` non si muove: solo libreria standard, niente JavaScript.
- **Una cartella nuova**, `apps/command-center/`, con il suo README che nomina ogni regola con il
  test che la difende; i controlli che le due superfici condividono stanno in
  `tests/design/surface.py`, perché due copie sarebbero due regole alla prima che qualcuno stringe.
- **Un generatore nuovo** e un file derivato, riconfrontati byte per byte come i tre di M17.1.
- I totali di oggi: **cinquantasette** regole, **ventisei** port, **quarantotto** rotte. Li appunta
  `tests/docs/test_adr_command_center.py`, che è l'ADR più recente che li muove.
