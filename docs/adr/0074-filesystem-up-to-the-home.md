# 0074. Il filesystem fino alla home di chi usa ELA: un elenco di cartelle, i posti di ELA a ogni uso, e un limite a ogni attesa del disco

- **Stato:** **Proposta** il **2026-11-19**, con il codice del branch `m13.17-i-file-di-tutto-il-computer`. Diventa
  Accettata con un commit suo, dopo che la prova a mano della sezione 35 di `docs/GETTING_STARTED.md`, con
  `scripts/prova_m13_17.py`, è passata sull'ultimo commit del branch. **Le «Righe riviste» di questo ADR hanno il loro
  marchio** sulle righe «Stato:» di ADR 0014, 0045, 0047, 0048, 0066, 0068 e 0071.
- **Data:** 2026-11-18
- **Riferimenti spec:** §29, §30, §32, §33, §57, §59, §65
- **Milestone:** [M13.17](../milestones/M13.17.md)

## Contesto

ADR 0045 ha dato a `fs.read` e `fs.write` **una cartella sola, fatta apposta**: una radice, `ELA_FS_ROOT`, e una cartella
dentro di essa, `ELA_FS_SCOPE`. La radice non poteva contenere, né stare dentro, ciò che ELA usa per esistere — «`~` è
rifiutata perché contiene `~/.ela`» (ADR 0045 §5) —, e il rifiuto `path.ela_s_own` a ogni uso era **una seconda linea**:
l'avvio aveva già tenuto i posti di ELA fuori dalla radice. M13.17 porta i file fino alla home di chi usa ELA, **che è
esattamente ciò che quella regola rifiutava**: questo ADR la rivede apertamente, e dice che cosa prende il posto di ciò
che il confine di prima garantiva per costruzione.

Il confine di prima garantiva quattro cose che dopo non ci sono più (SPEC di M13.17, «Che cosa cambia per la sicurezza»):
**niente di ELA sotto la radice**; **niente dell'altra vita di chi usa ELA** raggiungibile; **un disco che risponde**, perché
una cartella piccola su un disco locale risponde in millisecondi; **un file piccolo**, perché una cartella fatta apposta
non tiene un film. In una home i posti di ELA stanno sotto la radice, un file può essere enorme, e uno sguardo può
aspettare — una finestra di macOS che chiede un permesso, un file che il sistema tiene altrove —, e uno sguardo che non
torna fermava tutto il Core, perché girava nella coroutine.

**Il livello non si abbassa**: `fs.read` resta `MEDIUM` e chiede a ogni uso, `fs.write` resta `HIGH`; una policy di chi
usa ELA copre una scrittura come da ADR 0068, e nessuna policy copre una lettura.

## Decisione

### 1. La forma: una radice, un elenco

**`ELA_FS_SCOPE` è un elenco di cartelle, una riga di JSON**, ciascuna relativa a `ELA_FS_ROOT` nella grammatica di
sempre — senza `/` iniziale, senza `.` né `..` —: `ELA_FS_SCOPE=["Documents", "Desktop", "Downloads"]`. **Nessuna voce vuol
dire «tutto»**. Le sei capability dei file — `fs.read`, `fs.write` e le quattro dei file dal browser — ricevono l'elenco
come loro scope, e il Guardian lo legge con `within_scope` com'era: lo scope è più largo per configurazione, non per una
regola.

- **La riga di ieri si rifiuta all'avvio**: `ELA_FS_SCOPE=ELA`, senza le parentesi, ferma ELA con la frase che dice come
  scriverla, **con il valore di chi usa ELA**: «since M13.17 the scope is a list of folders, one line of JSON. Write
  `ELA_FS_SCOPE=["ELA"]` for the folder this line named until now». La riga di ieri e una cartella che si chiama `["ELA"]`
  non si distinguono senza indovinare.
- **`[]` si rifiuta all'avvio**, con la sua frase: lo scope apre almeno una cartella. Le sei non sono fra le capability che
  dichiarano uno scope vuoto, e nessun messaggio dice «or [] for none».
- **Una stringa non è un elenco** neanche nel codice: `folders()` rifiuta una stringa con un `TypeError` che lo dice, perché
  `"ELA"` diventerebbe in silenzio lo scope `('E', 'L', 'A')`.

### 2. La radice, fino alla home

`refuse_the_root(root, own, *, home)`, la stessa funzione sul Core e sul nodo, con la home iniettata. **La radice può
contenere i posti di ELA, e può essere la home**. È rifiutata se è un link, se non è una cartella, **se è un posto di ELA o
ci sta dentro**, e **se contiene la home senza esserla** — «ELA_FS_ROOT (/Users) holds your home (/Users/you): the folders
ELA may touch reach at most up to your home» —. Sul nodo la home è quella del nodo (`Path.home()`; sul PC `USERPROFILE`).

### 3. Ogni voce, all'avvio

Ogni voce dell'elenco è **guardata, aperta come una cartella e richiusa**, senza leggerne un nome, sotto la guardia del
disco (§7) con il suo limite. È rifiutata, con una frase che la nomina, se non c'è — ELA non crea mai una cartella che chi
la usa apre —, se è un file, se è un link, se il sistema non la lascia guardare — «the system did not let ELA look. The
permission is the terminal's, not ELA's» —, se il sistema non risponde entro il limite, e **se è, o sta dentro, un posto di
ELA**: «it would open nothing — every read and write there is refused as ELA's own».

### 4. Ciò che è aperto si dice e si vede

`ela serve` dice all'avvio la radice, le cartelle aperte e la cartella da cui parte un comando; **`ela diagnostics` e la
sua rotta** mostrano, nel blocco `files`, la radice, le cartelle aperte intere e nell'ordine, la cartella dei comandi, i
posti di ELA dentro la radice — «never read or written by fs.\*» —, le cartelle che si sovrappongono e **quante attese del
disco sono ferme adesso**; e accanto, nel blocco `scopes`, lo scope dichiarato di ogni capability che ne dichiara uno,
derivato dal catalogo. È lo stato di ELA, mai un nuovo sguardo al disco.

### 5. I posti di ELA, a ogni uso: da seconda linea a prima

Con la radice alla home il database, il `.env`, l'albero di ELA, `~/.ela`, il profilo del browser, il programma del vault e
il Python di ELA stanno sotto la radice: **il rifiuto `path.ela_s_own` a ogni uso è la prima linea e l'unica**, e arriva
dappertutto dove un file sotto la radice si guarda, si apre o si scrive:

- **i tool**, alla nascita di una policy (`prospect_place`), prima della domanda (`prospect`), prima della spesa
  (`prospect_covered`) e nell'esecuzione, sotto un sì e sotto una policy, in lettura e in scrittura, nei due versi — un
  bersaglio che è, contiene o sta dentro un posto di ELA —;
- **i loro verifier**, che ricevono la lista e rifiutano prima di leggere;
- **il terminale**, la cui cartella è rifiutata se **è, o sta dentro**, un posto di ELA — non se ne contiene uno: la
  cartella non è un confine (ADR 0047 §6), e una prima voce che contiene un posto di ELA non rifiuta nessun comando —;
- **lo scaricamento al momento di posare il file**, che riguarda il bersaglio con la funzione di `fs.write` prima del
  `replace`.

**Il mondo è chiuso**: un tool o un verifier dichiara `under_the_root`, `True` o `False`, senza un default, e un registro
rifiuta una classe che non lo dice (`SilentRootError`). I test derivano i tool e i verifier dai registri del Core e del
nodo e i membri dalle porte, e affermano il rifiuto su una radice di prova che contiene davvero i posti, con il disco che
non cambia.

**La lista guadagna** ciò che ELA usa e non nominava:

| Posto | Che cos'è |
|---|---|
| `the journal of the database (-wal)` | il file che SQLite tiene accanto al database |
| `the journal of the database (-shm)` | il file che SQLite tiene accanto al database |
| `the journal of the database (-journal)` | il file che SQLite tiene accanto al database |
| `the folders of the guided sessions` | le cartelle delle sessioni guidate, accanto alle catture |
| `the .env ELA read` | il `.env` della cartella da cui ELA parte, **anche quando non c'è**: uno scritto dopo l'avvio è quello che il prossimo avvio legge |

### 6. La lettura: la dimensione nella domanda, e un tetto

**La domanda di `fs.read` nomina la dimensione del file** come la dice il disco quando la domanda si compone, e le tre
superfici che rispondono la mostrano. **Un file sopra il tetto si rifiuta prima della domanda**, `fs.too_large`, con le
due dimensioni e mai un hash; **alla lettura** si legge al più il tetto e un byte, e un file cresciuto dopo lo sguardo è lo
stesso rifiuto. Il verifier di una lettura rilegge al più il tetto.

**Il sì a una lettura approva il percorso; la dimensione nella domanda è quella che il disco diceva alla domanda, e il tetto
chiude il caso peggiore. Un confronto della sola dimensione sarebbe mezza difesa con il nome di una intera — un file cambiato
con la stessa dimensione passerebbe — e rifiuterebbe ogni file che cresce fra la domanda e il sì. Per un caricamento è
diverso: lì i byte escono dalla macchina, e la domanda ne porta lo sha256. Il risultato dice già i byte letti.**

### 7. Le attese del disco: una guardia sola

`Disk`, in `ela/tools/disk.py`: ogni sguardo, lettura e scrittura sotto la radice gira **in un filo `daemon` fatto a mano**,
aspettato al più il limite. **Non `asyncio.to_thread`**: un filo dell'executor di default trattiene la fine di
`asyncio.run` finché la chiamata non torna (E3). **E non nella coroutine**: un `asyncio.timeout` non interrompe una chiamata
sincrona. Oltre il limite lo step riceve **`fs.no_answer`**, che **non si riprova da solo**, con la frase che dice che cosa
non ha risposto e che cosa può ancora succedere:

- uno sguardo o una lettura abbandonati non lasciano niente;
- **una scrittura abbandonata mentre guardava, o mentre faceva la sua cartella, non scrive mai**: il lavoro guarda il segno
  dell'abbandono prima di ogni passo che ha un effetto;
- **una scrittura abbandonata dentro `open` o `write` può ancora arrivare sul disco** dopo che lo step è fallito, e la frase
  lo dice: «the write may still happen when the disk answers».

**Al più quattro attese abbandonate alla volta**: oltre, ogni nuovo gesto sul disco è `fs.no_answer` subito, con la frase
che dice quante attese sono ferme e che finiscono quando il disco risponde. **Un «ferma» durante un'attesa** aspetta al più
il limite, mai di più. All'avvio, la variante sincrona della stessa guardia guarda le voci (§3).

| Costante | Valore |
|---|---|
| `DISK_LIMIT_SECONDS` | 10 |
| `ABANDONED_MOST` | 4 |
| `FS_READ_MAX_BYTES` | 8388608 |

**I numeri vengono dalle misure della SPEC**, con le regole committate prima dei numeri: il caso sano più lungo di uno
sguardo, 6,6 ms (E1); un tetto che la rotta dei risultati porta in tempo (E2) e la memoria del Core regge, un picco al più
doppio del riposo (E4) — 8 MiB passa, 16 no.

**La spesa, con il disco che non risponde** — le righe che la regola di ADR 0068 §6, nella tabella di ADR 0071 §7,
guadagna:

| Dove l'attesa è abbandonata | Spende un uso |
|---|---|
| allo sguardo prima della spesa (`prospect_covered`) | no: lo step fallisce con `fs.no_answer`, senza tool |
| nell'esecuzione, dopo il `consume` | sì: l'uso è speso su una chiamata partita, e `fs.no_answer` non si riprova |

### 8. Il terminale

**Un comando parte dalla prima cartella dell'elenco, o da una sotto (`cwd`)**: l'ordine dell'elenco è di chi usa ELA, e lo
dicono l'avvio, `ela diagnostics`, la guida e `.env.example`. Con una voce sola il comportamento è quello di prima. Mai da
una cartella che è, o sta dentro, un posto di ELA (§5).

### 9. Le policy di un file, se la radice cambia

Le cartelle di una policy sono scritte relative alla radice: **cambiare la radice ri-àncora le policy**. All'avvio, **una
policy viva** di una delle sei che porta la cartella intera mostrata alla sua nascita, e la cui cartella con la radice di
adesso si risolve altrove, **ferma l'avvio**, con la frase che nomina la policy, dove era, dove sarebbe e la strada:
rimettere la radice, revocare la policy, cambiare di nuovo. Il confronto è quello di `within`; una policy finita non conta.

### 10. La frase del diniego `SCOPE`

Le frasi che stampavano uno scope — la regola 4-bis del Guardian, il 4-ter del passo di una sessione guidata, il sì che
nomina bersagli fuori dallo scope — **nominano i bersagli e mai l'elenco**, e dicono dove lo scope si legge:
«targets ['Library/x.md'] of fs.write are not within its scope (uv run ela diagnostics shows it)». Un elenco di cartelle,
di siti o di programmi arrivava all'audit, alla console, al telefono e, per i siti, a un fornitore. **Gli eventi già
nell'audit tengono la frase di prima**: l'audit non si riscrive. `POLICY_VERSION` non si muove: cambia una ragione, non una
riga né un predicato.

### 11. I due punti della prova di M13.15

- **Le righe «why I ask»**: un giudizio solo, `would_cover`, letto dall'executor quando sceglie la policy che consegna al
  Guardian e dalle righe della domanda; una policy finita è una ragione solo se, viva, avrebbe coperto; la scelta viene
  prima del taglio, e la policy consegnata è nominata per prima a qualunque età. «no policy of yours for …» solo quando la
  capability non ne ha mai avuta una.
- **Lo script della prova**: uno `schermo` il cui comando esce con un errore — lo dice il codice d'uscita — fa il passo
  FALLITO e ferma la prova prima dell'`occhio`.

### 12. I codici

I codici che i tool aggiungono a quelli che gli ADR di prima scrivono:

| Tool | Codici aggiunti |
|---|---|
| `fs.read` | `fs.no_answer`, `fs.too_large` |
| `fs.write` | `fs.no_answer` |
| `terminal.run` | `fs.no_answer`, `path.ela_s_own` |
| `browser.download` | `fs.no_answer` |
| `browser.download_as_you` | `fs.no_answer` |
| `browser.upload` | `fs.no_answer` |
| `browser.upload_as_you` | `fs.no_answer` |

I codici di fallimento che i verifier aggiungono (ADR 0014 §2):

| Verifier | Codici aggiunti |
|---|---|
| `fs.read` | `fs.no_answer`, `path.ela_s_own` |
| `fs.write` | `fs.no_answer`, `path.ela_s_own` |
| `browser.download` | `fs.no_answer`, `path.ela_s_own` |
| `browser.download_as_you` | `fs.no_answer`, `path.ela_s_own` |

### Ciò che questo ADR dichiara e non risolve

In parole semplici:

- **Nessuna lista dei posti pericolosi.** Ciò che tiene chiuso un posto che ELA non conosce — dove il sistema, la shell o
  un altro strumento lanciano ciò che trovano; le chiavi, i gettoni e le sessioni di altri programmi; i `.env` di altri
  progetti; le cartelle che il sistema copia altrove — è che non stia nell'elenco. Se chi usa ELA lo elenca, ELA obbedisce,
  e chiede: una lettura sempre, una scrittura salvo una policy.
- **Le tre strade di ADR 0068, più larghe**: il limite «ELA non crea policy da sola» è vero quanto le cartelle scelte, e
  dentro una home ce ne sono di più. **Un'altra copia del repository o un altro `.env` sotto la radice** non sono di questo
  processo, e non sono fra i suoi posti.
- **La finestra fra lo sguardo e l'`open`** resta quella di `ela/tools/fs.py`; per uno scaricamento è fra l'ultimo sguardo e
  il `replace`.
- **Un programma che `terminal.run` lancia arriva ai posti di ELA**, sotto la radice o no: la cartella non è un confine
  (ADR 0047 §6). Ciò che §5 chiude è che **ELA** non li legga né li scriva, e che un comando non parta da una cartella di
  ELA; non ciò che un programma ammesso fa da sé.
- **I programmi che ELA lancia.** I programmi del sistema — `/bin/ps`, `/usr/sbin/screencapture`, `/usr/bin/say`,
  `/usr/bin/afplay`, `/usr/bin/pmset`, PowerShell sul PC — stanno fuori da ogni home. Il Python di ELA, con cui girano i suoi
  aiutanti, il binario della sessione guidata che il pacchetto del SDK porta e il driver di Playwright stanno nell'ambiente
  Python di ELA, che è fra i suoi posti; il programma del vault lo è da M13.14. **Non sono fra i posti**: i browser che
  Playwright scarica — di default in `~/Library/Caches/ms-playwright` sul Mac, `~/.cache/ms-playwright` su Linux,
  `%LOCALAPPDATA%\ms-playwright` sul PC, o dove dice `PLAYWRIGHT_BROWSERS_PATH` — e il trascrittore con il suo modello
  (`ELA_STT_BINARY`, `ELA_STT_MODEL`), dove chi usa ELA li dichiara, tenuti dal loro sha256 dichiarato. **Una scrittura di
  ELA li raggiunge solo se chi usa ELA apre la cartella che li contiene.** Derivarli a mondo chiuso da chi lancia un
  programma è [M13.20](../ROADMAP.md), riservata; la frase di ADR 0068 «solo ciò che il processo carica è fra i posti
  protetti» resta.
- **Il permesso di macOS non è di ELA**: è del processo responsabile, il terminale, e ciò che macOS concede perché ELA legga
  una cartella lo concede a ogni programma lanciato da lì. ELA non chiede, non aggira e non registra un permesso. **Che cosa
  macOS fa davvero** — se chiede, se ferma la chiamata, per quali chiamate —: NON MISURATO dalla suite; lo dice la prova.
- **Un file che iCloud tiene altrove**: NON MISURATO. Leggerlo può far partire uno scaricamento; lo copre il limite della
  guardia, e niente di suo.
- **Un'attesa abbandonata resta**: un filo fermo nella sua chiamata, che finisce quando il disco risponde e il cui esito
  nessuno ascolta più; al più quattro. Il tetto alle risorse di quei fili non è misurato.
- **Il tetto è di una lettura**: un task con più letture le somma sulla rotta dei risultati.
- **Su un nodo la domanda non dice la dimensione**: per uno step piazzato su un nodo la domanda nomina ciò che il piano
  afferma, e ELA non ha guardato quel disco (ADR 0048 §8); il tetto lo fa valere il tool del nodo, che è lo stesso codice.
- **Su un nodo non c'è uno scope suo né un Guardian**: l'elenco è del Core, posato sulla radice del nodo, e lo stesso
  percorso è un file sul Mac e un altro sul PC (M13.8).
- **Una cartella il cui nome è esso stesso una lista di JSON** non si può aprire con una riga che la nomini da sola: la
  riga è letta come l'elenco.
- **Il ritorno a un commit di prima**: il codice di prima rifiuta una radice alla home, e legge in silenzio un elenco come
  il nome di una cartella sola — ogni lettura e scrittura negata —. La guida lo dice, con le righe di prima per esteso.

## Alternative

- **Una lista dei posti pericolosi della home**: incompleta dal primo giorno, e insegnerebbe che ciò che non c'è è sicuro
  (ADR 0068, «Alternative»; ADR 0047 §1).
- **La riga di ieri letta come un elenco di una voce**: un valore che vuol dire due cose secondo come è scritto, e il
  ritorno a un commit di prima che lo legge in un modo e il codice nuovo nell'altro.
- **`[]` come risposta, come per i programmi e i siti**: sei capability negate in silenzio, e un terminale senza cartella.
- **`asyncio.to_thread` per le attese**: trattiene la fine del Core finché il disco non risponde (E3).
- **Un confronto della dimensione alla lettura** (`fs.file_changed`): mezza difesa con il nome di una intera (§6).
- **La radice sopra la home**: le home degli altri utenti della macchina, e nessuna ragione per chi usa ELA.

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0014** §2 — i codici di fallimento dei verifier: `fs.no_answer` e `path.ela_s_own` ai verifier dei file (§12).
- **ADR 0045** §4, §5, §8 — la colonna «Scope», un elenco; la coppia, con la radice che può contenere i posti di ELA e
  arrivare alla home, e «`~` è rifiutata» che non vale più; la dimensione di una lettura, anche nella domanda, e un tetto
  (§1, §2, §3, §6).
- **ADR 0047** §6 e le tabelle dei codici di `terminal.run` — la cartella dei comandi è la prima voce dell'elenco; «mai la
  cartella di ELA» tenuto dal controllo a ogni uso; `path.ela_s_own` e `fs.no_answer` (§5, §8, §12).
- **ADR 0048** §7 — la radice del nodo con le regole del Core cambiate, con il testo solo di `refuse_the_root` (§2).
- **ADR 0066** §8, §9 — il file posato da uno scaricamento: il bersaglio riguardato prima del `replace`; le tabelle dei
  codici dei tool e dei verifier (§5, §12).
- **ADR 0068** §6, §7 e «Ciò che questo ADR dichiara e non risolve» — la spesa con il disco che non risponde; la lista va
  anche ai verifier e al terminale, e guadagna ciò che ELA usa; le tre strade, più larghe, e un'altra copia del repository
  o un altro `.env` sotto la radice (§5, §7).
- **ADR 0071** §4, §7 — i posti protetti anche ai verifier; la riga `fs.no_answer` della spesa (§5, §7).

Le altre conseguenze:

- **Le parole del prodotto**: le descrizioni delle sei capability dei file, che arrivano al Planner, dicono «the authorised
  folders», al plurale; quella di `terminal.run` dice che `cwd` è relativo alla prima cartella.
- **`ela init`** e **`.env.example`** mostrano la forma nuova; `pydantic-settings` ha il pavimento alla versione del lock,
  `2.15.0`, per `NoDecode`.
- **Nessuna migrazione**, nessun port nuovo, nessun membro nuovo di un port.

**Che cosa prova solo il test**: il rifiuto `path.ela_s_own` a ogni uso — con l'elenco della prova nessuna cartella aperta
contiene un posto di ELA, e la mano non lo raggiunge —, in `tests/tools/test_ela_s_places_at_every_use.py`; la guardia e le
sue frasi, in `tests/tools/test_the_disk_that_does_not_answer.py` e
`tests/architecture/test_every_look_at_the_disk_passes_the_guard.py`; la lettura sopra il tetto, in
`tests/tools/test_fs_read_size.py`; le policy spostate, in `tests/composition/test_what_is_open.py`.

Con questo ADR le regole di architettura restano **settantaquattro**, i contratti di import-linter **sedici**, i port
**trentasei**, le rotte dell'API **settantadue**, i comandi della CLI **trentanove**, le capability **ventidue**, le
identità del middleware **sei**.
