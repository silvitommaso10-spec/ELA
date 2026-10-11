# 0063. Il browser con i tuoi account: un Chrome di ELA che dura, le password che restano in Bitwarden, e una sessione che copre le sue letture

- **Stato:** Proposta il **2026-10-11**, con l'implementazione di M13.9. Diventa Accettata con un commit suo, quando la
  prova a mano della sezione 28 di `docs/GETTING_STARTED.md` passa sul Mac, sul branch e prima del merge.
- **Data:** 2026-10-11
- **Riferimenti spec:** §19, §27, §29, §30, §32, §33, §39, §57, §59, §62, §63
- **Milestone:** M13.9, con M13.4b, M13.4c e M13.4e sullo stesso branch

## Contesto

Fino a M13.9 il browser di ELA è vuoto per scelta (ADR 0052 §3): un profilo nuovo per ogni step, e una domanda
che dice «il sito vede un visitatore». M13.9 aggiunge **accanto** a quello un Chrome con un profilo di ELA che
dura, in cui Tommaso entra a mano nei suoi siti, e le password prese una alla volta da Bitwarden. Le misure, le
decisioni della review — dalla 1 alla 71 — e le proposte stanno in `docs/milestones/M13.9.md`; ciò che M13.4b,
M13.4c e M13.4e hanno riparato sullo stesso branch sta nei loro documenti.

Questo ADR si scrive con l'implementazione, una sezione alla volta, nell'ordine in cui il codice arriva: **il
Guardian per primo** (decisione 66).

## Decisione

### 1. Una sessione copre le letture che il suo modello scrive

Dentro una sessione guidata ogni gesto è un task figlio, deciso sul livello del catalogo (ADR 0060 §4). Una
lettura con il profilo è `MEDIUM`: chiederebbe a ogni sguardo, fino a trenta volte. **Ciò che la copre è la
sessione stessa** — il sì o la policy con cui è partita —, per la strada che la review ha deciso (decisione 29,
«A con C»), e che ADR 0060 aveva scartato nella forma di un grant: qui **non nasce nessun grant**.

**Che cosa copre, e quando.** Il Guardian permette uno step `MEDIUM` senza un'autorizzazione quando riceve due
fatti, e li ricontrolla tutti e due dal suo catalogo:

- **chi ha scritto il piano** (`author`): una sessione, e proprio quella;
- **la parola della stanza** (`session`, un `SessionCover`): quella sessione è aperta, in quel task, è una
  sessione di quella capability, su quei siti.

E allora controlla, nell'ordine: che non ci sia anche un'autorizzazione — due fatti per una chiamata sono uno di
troppo —; che il piano sia stato scritto da quella sessione; che il task sia un figlio del task della sessione;
che la capability della sessione sia nel catalogo, **e che chieda**; che dichiari di coprire proprio questa
capability, **con lo schema di oggi**; che la riga della capability coperta sia «chiede a meno di
un'autorizzazione»; che il bersaglio sia un sito della sessione. Una parte che non torna è un'incoerenza di chi
chiama, e si nega — come un grant che non copre (ADR 0011 §6).

**La parola della stanza si legge al momento della decisione, mai da una copia.** La chiede l'executor, alla
stanza, quando decide lo step; non la tiene. Una sessione chiusa non attesta niente: un suo figlio che viene
deciso dopo **chiede**, come un `MEDIUM` ha sempre fatto — e **dal momento in cui ELA la sta chiudendo**, per un
«ferma», per un suo limite o perché i suoi secondi sono finiti, la stanza non la attesta più e non fa altri
gesti: a un gesto risponde che la sessione è finita. Una sessione è aperta nella stanza solo mentre il suo step gira, e quello step
gira perché è stato permesso: la stanza la apre con la prenotazione letta dal record `STARTED`.

**Il Guardian non conta.** I gesti li numera la stanza, e a fermare la sessione ai suoi `looks` è il tool che
la ospita, che al gesto oltre risponde che sono finiti: il Guardian decide su un fatto che l'executor gli porta,
non su un contatore suo.

**Che cosa una sessione dichiara di coprire** è un fatto del catalogo, `covers`, **fuori da `PolicyTerms`**: la
capability coperta, e **una copia del suo schema**. I `PolicyTerms` di `browser.guided` restano quelli che una
policy nata con M13.12 ha copiato.

**Due difese contro un `HIGH` coperto**, ciascuna con il suo caso negativo costruito:

1. **il catalogo** rifiuta un `covers` verso una riga che non è «chiede a meno di un'autorizzazione» — e verso
   una capability che non c'è, verso se stessa, con una copia dello schema che non è lo schema, o dichiarato da
   una capability che non chiede;
2. **il Guardian** nega una copertura presentata per una riga che non è quella, qualunque cosa il catalogo
   abbia lasciato passare. È la difesa del giorno in cui la prima viene aggirata da una dichiarazione scritta
   male.

**L'executor consegna la parola della stanza solo per la capability che la sessione dichiara.** Un `act` della
sessione è `HIGH`: la parola non gli viene consegnata, e **chiede** come sempre — consegnarla sarebbe
un'incoerenza che il Guardian nega, e l'`act` finirebbe negato invece che chiesto.

**La regola ha un nome suo**, `SESSION`, e non quello di un grant; la sua negazione è `SESSION_MISMATCH`.
`POLICY_VERSION` diventa `v0.3`: un Guardian che sa permettere ciò che non sapeva non è quello della versione
prima. La decisione e l'evento `PERMISSION_DECIDED` dicono **quale sessione** ha coperto — lo step della
sessione, un identificativo —, e nessun'altra decisione porta quel campo.

Righe di consumo aggiunte:

| Regola | Consuma |
|---|---|
| `SESSION` | no |

Un `ALLOWED` sotto `SESSION` non poggia su nessun grant, e non ne spende nessuno.

Firma rivista:

```python
def decide(
    self,
    capability: CapabilitySpec,
    arguments: JsonMapping,
    *,
    task: Task | None = None,
    step: TaskStep | None = None,
    authorization: Authorization | None = None,
    authorization_uses: int = 0,
    author: PlanAuthor | None = None,
    session: SessionCover | None = None,
) -> PermissionDecision: ...
```

**Il mondo chiuso di ADR 0062 §1 si estende a `covers`.** Una policy porta una copia di ciò che la sua
capability dichiarava di coprire il giorno in cui è nata, accanto alla copia dei termini; il giorno in cui lo
schema della capability coperta cambia la dichiarazione è un'altra, e la policy **smette di coprire da sé**, con
la ragione dei termini cambiati. Una policy nata prima di M13.9 non porta quel campo, e si legge com'era.

**Un piano che non viene dalla stanza non può dirsi scritto da una sessione**: l'autore lo scrive chi attacca il
piano, mai il corpo della richiesta — la rotta del piano a mano scrive `HAND`, il Planner `PLANNER` o `MODEL`, e
solo la stanza scrive `SESSION`.

**Che cosa costa, detto.** Un sì copre fino a `looks` effetti `MEDIUM`, e non uno. Una policy di sessione non ha
un numero massimo di sessioni: regge perché **l'avvio è di Tommaso** — una sessione nasce da un piano che lui ha
chiesto —, e il giorno in cui ELA parte da sola si riesamina (annotazione per la Fase 15). **Una revoca non
ferma una sessione già partita**: le sue letture continuano fino ai suoi tetti, e l'uscita della revoca lo dice.

### 2. Il vault: le password restano in Bitwarden, e ELA tiene una chiave sola

**La password principale non entra mai in ELA.** Lo sblocco lo fa Tommaso, con `bw`, nel suo terminale; a ELA
arriva la chiave della sessione sbloccata, dentro un `Secret`, e vive **in memoria, nell'adapter**: mai su
disco, in un log, in `argv`, nell'ambiente di ELA.

**`Secret`** (`ela.ports`) è un valore che non si stampa, non si serializza, non si copia, non si confronta, e
si apre con un metodo solo. Non è una difesa contro chi legge la memoria del processo: è una difesa contro il
codice di ELA che lo scrive da qualche parte.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `Vault` | §19, §57 | async | `status`, `unlock`, `lock`, `forget`, `find`, `take` |
| `AccountBrowser` | §19, §57 | async | `installed`, `open`, `count`, `field`, `fill`, `click`, `text`, `title`, `left`, `keep`, `glance`, `close`, `occupied`, `window`, `linked`, `saved`, `fill_secret` |

**I comandi che l'adapter compone sono un elenco chiuso**: `status`; `list items --url <indirizzo>`; `get item
<id>`; `lock`. Mai `unlock`, `login`, `export`, `get totp`, `get uri`, `serve`, `sync`, né `--session`: la chiave
va nell'ambiente del figlio, `BW_SESSION`, con `BW_NOINTERACTION`, oltre alle quattro variabili dell'ambiente
chiuso (ADR 0047 §6, che si legge con questa riga accanto). Lo stdin del figlio è la fine di un file, il suo
stderr non va a nessuno; nasce in un gruppo suo ed è ucciso con il gruppo allo scadere, o quando nessuno lo
aspetta più. *Misurato il 2026-10-11*: a chi chiede di uccidere un gruppo il cui unico processo è finito e non
è ancora stato raccolto macOS risponde «non permesso»; è un gruppo senza più niente da uccidere, e ciò che esce
resta l'errore dell'adapter.

**Ciò che `bw` risponde male, o che non si può nemmeno lanciare, è un errore del vault**: uno stato che non è
una delle sue parole — nemmeno un testo —, un NUL nella chiave o nell'indirizzo, che nessun ambiente e nessun
argomento può portare. Mai un'eccezione che una rotta non conosce, e mai con il valore dentro.

**Prima del sì nessuna password lascia l'adapter** (decisione 28, che rivede il secondo criterio della
registrazione — «senza il sì, la CLI non viene chiamata» — per mano di Tommaso e del revisore). `find` chiede lo
stato e l'elenco per l'indirizzo del sito, e restituisce l'id della voce, il nome, gli indirizzi, **il nome
utente mascherato** — il primo carattere, e per un indirizzo la parte dalla chiocciola (decisione 31); di un
nome che comincia con la chiocciola, che è un handle e non un indirizzo, solo la chiocciola — e se c'è
una password: ogni valore è buttato lì. **Il costo, dichiarato**: per un istante passano dalla memoria
dell'adapter tutte le voci che Bitwarden fa corrispondere a quell'indirizzo, intere — misurato, l'elenco porta
la password.

**Dopo il sì la voce si legge una volta sola** (decisione 64): `get item`. Da quella lettura escono gli
indirizzi, per il riconfronto con la pagina aperta, e il nome utente e la password dentro un `Secret`; **tutto
il resto si butta** — l'adapter tiene ciò che nomina, non toglie ciò che conosce. Riconfronto e presa stanno
sullo stesso dato.

**L'uscita di `bw` non entra in un'eccezione**, nemmeno per catena: un errore nomina il comando, ed è sollevato
quando niente di ciò che è stato letto è più a portata.

### 3. La chiave: come arriva, quanto dura, chi la dimentica

**Il programma è configurazione, e ha un'identità.** `ELA_VAULT_PROGRAM`, un percorso assoluto, facoltativo e
senza default; mai cercato nel `PATH`. Davanti all'adapter sta **la porta dei tool** (`ela.tools.vault`): fissa
all'avvio l'identità del programma — il file a cui il percorso porta e il suo sha256, `Identity` di ADR 0047 §4 —
e la riconfronta **prima di ogni uso**. Cambiato è `vault.program_changed`, sparito `vault.program_gone`, mai
stato lì `vault.no_program`, non dichiarato `vault.undeclared`; un programma che comincia con `#!` è
`vault.program_is_a_script`: ciò che si fisserebbe è un lanciatore, non il codice che riceve la chiave.

**La chiave arriva da una pipe, e solo da questa macchina.**

```
<il programma dichiarato> unlock --raw | ela vault open
```

`ela vault open` legge la chiave dallo stdin e **rifiuta un terminale**: una chiave non si scrive e non si
incolla. La manda a `POST /vault/session`, che la riceve **solo se i due capi del socket sono di loopback**
(`from_this_machine`, la coppia di ADR 0044): la tailnet non consegna una chiave, qualunque token porti. La rotta
la tiene solo se il programma del vault, con quella chiave, dice che il vault è aperto; altrimenti è
`vault.key_refused`, e la chiave è dimenticata. **Non torna indietro in nessuna risposta**, né in un rifiuto: il
corpo è un campo solo, e un corpo malformato è rifiutato senza essere ripetuto.

**Dura un'ora dall'apertura**, mai dall'ultimo uso (`VAULT_OPEN_SECONDS`). Allo scadere la dimentica **un compito
della porta** — non una rotta: nessuno la sta chiamando — e chiede al vault di chiudersi; con un programma che nel
frattempo è cambiato o sparito la dimentica e **non lancia niente**, e la riga dell'audit lo dice. Ogni uso
riconfronta l'ora sull'orologio: una chiave scaduta non serve un uso, chiunque abbia o non abbia chiuso.
**L'ora è dell'orologio, non del ciclo**: il compito aspetta un minuto alla volta (`WATCH_SECONDS`) e chiede
all'orologio se è l'ora, perché il tempo di un'attesa non avanza mentre il Mac dorme — un'attesa sola di un'ora
sarebbe un'ora di veglia. Un Mac che si sveglia dimentica entro un minuto.

**Alla porta passa una cosa alla volta.** Una chiusura è fatta di più passi, e finché il vault non ha risposto
il suo adapter tiene ancora la chiave: un'apertura, una chiusura, un uso e lo stato tengono la porta mentre
chiedono, e chi arriva in mezzo aspetta. Solo la fermata di ELA non aspetta il suo turno: dimentica, e non
lancia niente.

**Una chiusura arriva in fondo anche se chi l'ha chiesta se ne va**: un uso ha la scadenza del suo step, e la
fermata di ELA finisce il custode. Ciò che resta da fare è fatto sulla via d'uscita — la chiave dimenticata, la
riga scritta —, e una chiusura tagliata lo dice: al vault non è stato chiesto di chiudersi, o non ha risposto.
**Un'apertura la cui riga non si scrive non resta**: la chiave è dimenticata, al vault è chiesto di chiudersi, e
l'errore dell'audit è la risposta.

**`bw lock` è di tutta la macchina**: `ela vault close` chiude anche ciò che Tommaso avesse aperto nel suo
terminale; e un `bw unlock` di Tommaso finisce la chiave di ELA (misurato, K2), che ELA scopre **al primo uso
che la incontra**: la dimentica lì, e lo dice. Se nessun uso la incontra prima dell'ora, allo scadere il custode
chiede comunque `bw lock`, che chiude anche ciò che Tommaso avesse aperto dopo *(è la domanda 81 della
milestone)*.

**La fermata di ELA la dimentica, e non lancia niente**: `Ela.aclose` chiama la porta prima di portare a riposo
il browser e prima di rilasciare il database, e ogni passo è raggiunto qualunque cosa abbia sollevato quello
prima. Una chiusura del custode che fosse in volo è finita quando la porta torna: il ciclo non si smonta
con un lancio di `bw` in corso.

**Lo stato è derivato, mai memorizzato**: `GET /vault` lo chiede a `bw status` a ogni richiesta. Per un vault
chiuso porta **la riga intera da incollare** (decisione 32), composta con il programma dichiarato — citato come
la shell vuole un percorso con uno spazio —, mai con un segnaposto: il `bw` da lanciare è quello di cui ELA ha
fissato l'identità. L'indirizzo dell'account, che `bw status` stampa, non lascia l'adapter.

Rotte nuove, in `ela/api/vault.py`, che raggiunge `CORE` con il token:

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/vault` | lo stato del vault, chiesto al suo programma; per un vault chiuso, la riga da incollare |
| `POST` | `/vault/session` | la chiave della sessione, da questa macchina soltanto |
| `POST` | `/vault/lock` | la chiave dimenticata, e `bw lock` |

Errori aggiunti, nella forma della tabella di ADR 0023 §10:

| Caso | Eccezione | Stato |
|---|---|---|
| il vault non prende la chiave, o non si chiude | `VaultRefusedError` | `409` |
| la chiave arriva da un socket che non è di loopback ai due capi | `VaultKeyNotLocalError` | `403` |

Codici aggiunti a `ela.ports.WireCode`:

| Codice | Membro | Quando |
|---|---|---|
| `vault.refused` | `VAULT_REFUSED` | il vault non ha preso la chiave o non si è chiuso: il messaggio comincia con il codice del vault |

**Un codice sul filo, non uno per ragione** (ADR 0062 §9): il codice del vault — `vault.key_refused`,
`vault.program_changed`, `vault.not_local`… — è la prima parola del messaggio, e nessuno decide leggendola.
I casi della tabella condividono il codice e si distinguono per lo stato: `403` è «non da qui», e il vault non è stato
interrogato.

Un gruppo nuovo della CLI, **`ela vault`**:

| Comando | Rotta | Uscite |
|---|---|---|
| `ela vault status` | `GET /vault` | `0` `1` `2` `3` |
| `ela vault open` | `POST /vault/session` | `0` `1` `2` `3` |
| `ela vault close` | `POST /vault/lock` | `0` `1` `2` `3` |

`ela vault open` esce con `2` senza mandare niente quando lo stdin è un terminale, o quando dalla pipe non arriva
nessuna chiave — `bw unlock` che ha fallito non ne stampa.

**L'audit**: tipi d'evento nuovi, senza contenuto. `VAULT_OPENED` lo scrive la rotta che riceve la chiave,
firmato da chi l'ha consegnata, con l'istante in cui ELA la dimenticherà. `VAULT_CLOSED` lo scrive **il custode
della chiave**, che è chi vede ogni chiusura — un comando, l'ora, la fermata di ELA, una chiave finita altrove —:
firmato da chi l'ha chiesta, o da ELA quando nessuno l'ha chiesta, con il perché (`command`, `expired`,
`stopped`, `ended_elsewhere`), se il programma del vault è stato lanciato e ha chiuso, e il suo codice quando
non lo è stato. Una chiusura che nessuna rotta ha chiesto non resta senza riga.

### 4. Il browser con il profilo: Chrome for Testing su una cartella di Tommaso

**Il port è `AccountBrowser`** (la riga è nella tabella dei port introdotti, §2): i membri di `Browser`, con lo
stesso contratto del gesto, della consegna e della fermata, e ciò che il profilo aggiunge — chi tiene la
cartella (`occupied`), la finestra del login a mano (`window`), se il browser conosce un account Google
(`linked`), quante password ha salvato il suo gestore (`saved`), e il campo riempito da un `Secret`
(`fill_secret`). Il suo adapter, `ela/infrastructure/machine/account.py`, **eredita** l'adapter del browser
vuoto: un driver e un browser per pagina, il cancello di ADR 0052 §6, la fermata di M13.4c, la chiusura che
arriva in fondo di M13.4b, l'uccisione alla grazia di M13.4e. Cambia **quale** browser una pagina riceve, e che
cosa si fa alla cartella prima che parta.

**Il binario** è Chrome for Testing della versione del lock, dal registro di Playwright — mai il Chrome
installato, il cui profilo ELA non apre, non legge, non copia e non elenca. **Con il sandbox**, che Playwright
spegne di default. **Nessun lancio tocca il portachiavi**: `--use-mock-keychain` sta fra gli argomenti che ELA
scrive, non fra quelli che spera da un default altrui; con lui `--disable-sync` e
`--allow-browser-signin=false`. Le opzioni del lancio sono un insieme chiuso: niente HAR, niente tracing, niente
video. **ELA non si traveste**: nessuno user agent, nessuno script iniettato, niente che tocchi
`navigator.webdriver`.

**La cartella** è `ELA_BROWSER_PROFILE_DIR`, facoltativa e senza default. La legge l'adapter e nessun altro
modulo di ELA; nessun errore che esce dall'adapter ne porta il percorso — **nemmeno ciò che ne dice il
sistema**: un `OSError` porta il percorso nel suo testo, ed esce come un errore del browser che ne dice il tipo.
**Al primo sguardo, e prima di ogni lancio**: se non c'è, ELA la crea `0700` — esattamente, qualunque sia la
umask, e mai più larga nemmeno per un istante —; se c'è, deve essere una cartella vera, di chi lancia ELA, con i
bit del modo aperti a nessun altro, altrimenti `ProfileUnsafe`. **ELA non la stringe da sé.** Una cartella
comparsa fra lo sguardo e la creazione — due aperture insieme, la prima volta — è riguardata come ogni altra.

**Anche sotto la cima.** `Default`, dove il browser tiene ciò che ELA conta, riscrive e toglie, è una cartella
sua e mai un link a un'altra: attraverso un link ELA farebbe le stesse cose alla cartella a cui porta — il
profilo di un altro browser, se è lì che porta. Il file nuovo delle preferenze non è mai scritto attraverso un
link. Una cartella che porta il nome dei profili temporanei che ELA toglie dopo un'uccisione è rifiutata. *Ciò
che non è guardato*: una ACL sulla cartella, e i profili che Tommaso aggiungesse da dentro la finestra *(sono le
domande 78 e 79 della milestone)*.

**Chi tiene la cartella si legge dal lock, per il pid**: solo ciò che può essere il pid di un browser — cifre,
sopra il primo processo del sistema, entro il massimo di un pid — è chiesto al kernel. Un lock che nomina
altro non l'ha lasciato un browser che gira, e non tiene niente. *Il limite*: un lock rimasto da un browser
ucciso, il cui pid il sistema ha poi dato a un altro processo, tiene la cartella finché qualcuno non lo toglie
*(è la domanda 82 della milestone)*.

**Ciò che il profilo non tiene** si riscrive prima di **ogni** lancio, sopra ciò che il file dice — misurato
sul file che Chrome stesso ha scritto:

| Preferenza | Valore |
|---|---|
| `credentials_enable_service`, `credentials_enable_autosignin` | `false` |
| `profile.password_manager_leak_detection` | `false` |
| `autofill.profile_enabled`, `autofill.credit_card_enabled` | `false` |
| `signin.allowed`, `signin.allowed_on_next_startup` | `false` |

Sono loro, con i flag, a tenere il browser lontano da un account Google e dal salvare password — non il
binario (misurato, G4 e G5). Dopo un login su una pagina di prova le tabelle del gestore sono vuote e la
password non è in chiaro in nessun file della cartella. `linked` rilegge il file a ogni domanda, mai una copia;
`saved` conta le righe del gestore senza leggerne nessuna, sul file com'è sul disco.

**I service worker si tolgono prima di ogni lancio guidato**, e i nuovi sono bloccati. Il cancello è una rotta
di Playwright, e un worker registrato nel profilo risponde senza che la rotta sia chiamata. *Misurato il
2026-10-11 sul binario vero, con un worker lasciato*: la pagina è quella del worker, **il confine non è stato
interrogato**, e il sito ha ricevuto lo stesso la richiesta — mandata dal browser per conto suo, accanto al suo
worker. La finestra non li toglie: non ha un cancello, e i siti di Tommaso tengono i loro.

**Un processo alla volta.** Chi tiene la cartella è derivato a ogni domanda, in quest'ordine: ciò che l'adapter
ha in volo — una pagina, un'apertura, una chiusura —, la sua finestra, e poi il lock della cartella
(`SingletonLock`). **Il lock si legge dal pid, non dal nome della macchina che porta davanti**: il nome di un
Mac cambia con la rete su cui sta — misurato, un Mac che si chiamava con un indirizzo —, e un browser che gira
sotto il nome di ieri gira lo stesso. Un lock lasciato da un processo che non c'è più non tiene niente. Su una
cartella trovata occupata `open` e `window` sollevano `ProfileBusy` e **non lanciano niente**: è il secondo
lancio che può uccidere il primo. Fra lo sguardo e il conto dell'apertura non c'è un'attesa: di due aperture
insieme ne parte una. **Quando `close` torna la cartella è libera, chiunque l'abbia chiesto**: chi arriva mentre
un altro sta già chiudendo aspetta quella chiusura.

**Ciò che dura è la cartella.** Il browser si apre e si chiude con lo step; al lancio dopo passa ciò che la
cartella tiene. Un cookie a cui il sito ha dato una scadenza si ritrova; **un cookie di sessione no**: un login
su un sito che non ne dà altri vale per quello step. È dichiarato, e un test lo tiene.

**Ciò che il port dice in più.** `Field.method`: come manda il modulo di un elemento, letto **dagli attributi,
attraverso il prototipo** — un modulo risponde a `form.method` con un suo campo che si chiami `method`, e una
pagina che volesse far passare un `get` per un `post` non dovrebbe fare altro —; un bottone che invia porta il
suo `formmethod` sopra quello del modulo, un campo no. `Glanced.second_factor`: se la pagina mostra un campo
`one-time-code` visibile. `fill_secret`: **l'eccezione del motore non esce, nemmeno come contesto di quella che
esce** — misurato, il suo messaggio nomina la chiamata con ciò che è stato scritto.

**La finestra** è lo stesso binario sulla stessa cartella **senza niente attaccato**: nessun driver, nessuna
pipe, nessuna porta; l'uscita non va a nessuno; nasce in un gruppo suo, con l'ambiente chiuso. I suoi argomenti
sono un elenco chiuso — la cartella, `--use-mock-keychain`, `--no-first-run`, `--no-default-browser-check`,
`--disable-sync`, `--allow-browser-signin=false`, e un indirizzo se c'è. **L'elenco lo chiude l'adapter,
chiunque lo chiami**: ciò che non è l'indirizzo di un sito — `http` o `https`, con un host, senza un nome né
una parola dentro — non è passato al binario, dove sarebbe un suo argomento o aprirebbe ciò che non è un sito.
Che sia `https`, e di un sito dichiarato, lo dice la rotta (§8). ELA ne tiene una cosa sola: l'attesa
della fine. **Alla fermata di ELA è avvisata** — `SIGTERM`, a cui il browser esce da sé scrivendo i suoi cookie
—, **aspettata entro la stessa grazia** delle pagine, **poi uccisa con il suo gruppo**, e nominata. Mai lasciata
viva sulla cartella: **il lancio è un compito dell'adapter**, che arriva in fondo anche se chi l'ha chiesto se
ne va, e che la chiusura aspetta prima di dire libera la cartella. *Misurato il 2026-10-11*: un processo fermo
che non ha ancora detto che cosa fa di `SIGTERM` ne è terminato subito, dal kernel; un browser fermo quando è
già su resta fermo, e lo toglie la grazia. *Ciò che resta fuori*: un browser che si rilancia da sé da dentro la
finestra finisce il processo che ELA aspetta e ne avvia uno che ELA non ha conosciuto — di lui resta il lock
*(è la domanda 80 della milestone)*.

**La chiusura di ELA** porta a riposo questo adapter come quello del browser vuoto. Un browser del profilo
ucciso alla grazia **non perde la sua cartella**: l'adapter toglie solo i profili temporanei che Playwright
nomina, mai una cartella dichiarata. Ciò che un browser ucciso aveva imparato un momento prima non è scritto —
misurato, un cookie della pagina del browser ucciso non si ritrova —: è del browser, non di ciò che ELA toglie.

**Ciò che ELA lascia fuori dalla cartella del profilo** (decisione 47; misurato il 2026-10-11, con la finestra
lanciata dall'adapter su una cartella di prova). La lista di preferenze di macOS di Chrome for Testing,
`~/Library/Preferences/com.google.chrome.for.testing.plist`: è dell'applicazione, non di Tommaso, porta una
chiave sola — `LastRunAppBundlePath` —, e un lancio non la cambia. E la cartella del raccoglitore dei crash,
`~/Library/Application Support/Google/Chrome for Testing/Crashpad/`, di cui ogni lancio riscrive
`settings.dat`: nessun rapporto vi è stato scritto, e **le regole della cartella del profilo non la coprono**
*(è la domanda 74 della milestone)*.

**Ciò che parte verso Google a ogni lancio** (§57: che cosa, verso chi, perché). Il browser stesso, non una
lettura di ELA, apre connessioni verso host di Google appena parte — misurato la notte del 2026-10-10:
`accounts.google.com` (`ListAccounts`) e `www.google.com` —, **con i cookie che il profilo ha per quegli host**
(letto, non misurato: la sonda non aveva un account). Non è un gesto, non passa dal confine, e niente di ciò
che è stato provato lo toglie. È il binario che parla con chi l'ha fatto; si dichiara, qui e nella guida.

**Solo sul Mac.** Su ogni altro sistema ogni uso solleva `BrowserUnsupported`, e nessuna cartella è creata.

### 5. Le capability, i loro tool e i loro verifier

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `browser.read_as_you` | MEDIUM | `undeclared` | `site` | sì | `site: string`, `path: string`, `purpose: string` | `selector: string` |
| `browser.act_as_you` | HIGH | `undeclared` | `site` | sì | `site: string`, `path: string`, `fill: array`, `click: string`, `expect_text: string`, `purpose: string` | — |
| `browser.login` | HIGH | `undeclared` | `site` | sì | `site: string`, `path: string`, `username_field: string`, `password_field: string`, `click: string`, `expect_text: string`, `purpose: string` | `entry: string` |
| `browser.guided_as_you` | MEDIUM | `undeclared` | `sites` | sì | `goal: string`, `sites: array`, `max_cost_usd: string`, `looks: integer`, `seconds: integer` | `task_type: string` |

**«As you» è la cosa che chi approva deve sapere, ed è la parola della domanda.** Gli schemi delle prime due sono
quelli di `browser.read` e di `browser.act`, con le loro grammatiche e i loro limiti (ADR 0052 §5 e §8): ciò che
cambia è il browser e la frase, non la forma della chiamata — «con il profilo» non è un argomento (ADR 0026 §7).
Lo scope è `ELA_BROWSER_SITES`, e le capability stanno in `DECLARES_AN_EMPTY_SCOPE`. Nessuna viaggia, nessuna è
ripiazzabile.

**I livelli.** `browser.read_as_you` è `MEDIUM`: ciò che legge è contenuto di Tommaso (§57), e parte con le sue
credenziali. Chiede a ogni uso: nessuna policy di §59 copre una lettura singola, e ciò che copre le letture
scritte dal modello di una sessione è la sessione (§1). `browser.act_as_you` e `browser.login` sono `HIGH`:
mandano qualcosa a nome suo, e ciò che è mandato non si riprende.

**Le frasi**, che la domanda mostra: una lettura e un gesto dicono «where you are signed in» — ELA non sa, prima
di aprire la pagina, se in quel sito c'è un login —; «il sito vede un visitatore» resta nelle frasi del browser
vuoto, dove è vero. La frase del login dice «ELA keeps the password nowhere», e **non** «nowhere else»: dopo il
click il modulo lo rimanda il cancello dell'adapter, e il valore ripassa dal processo di ELA.

I tool, in `ela/tools/account.py`:

| Capability | Tool | Nome | Idempotente | Codici d'errore | Numeri nell'audit |
|---|---|---|---|---|---|
| `browser.read_as_you` | `AccountReadTool` | `browser-read-as-you` | sì | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `shown`, `status`, `total` |
| `browser.act_as_you` | `AccountActTool` | `browser-act-as-you` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.secret_field`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `gestures`, `status` |
| `browser.login` | `LoginTool` | `browser-login` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.login_form_get`, `browser.not_a_password_field`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.secret_field`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system`, `vault.entry_ambiguous`, `vault.entry_forgotten`, `vault.entry_not_for_site`, `vault.failed`, `vault.locked`, `vault.no_entry`, `vault.no_password`, `vault.no_program`, `vault.program_changed`, `vault.program_gone`, `vault.program_is_a_script`, `vault.timeout`, `vault.unauthenticated`, `vault.undeclared` | `gestures`, `status` |
| `browser.guided_as_you` | `BrowserGuidedTool` | `browser-guided-as-you` | no | `arguments.invalid`, `guided.cache`, `guided.cap_below_one_call`, `guided.cost`, `guided.duration`, `guided.failed`, `guided.folder_changed`, `guided.looks`, `guided.max_tokens`, `guided.model_changed`, `guided.not_installed`, `guided.permission_asked`, `guided.route_changed`, `guided.session_gone`, `guided.stopped`, `guided.tools_changed`, `guided.unchecked`, `guided.unreserved`, `provider.authentication_error`, `provider.bad_request`, `provider.malformed_response`, `provider.no_output`, `provider.rate_limited`, `provider.refusal`, `provider.rejected`, `provider.server_error`, `provider.spend_limit`, `provider.timeout`, `provider.unavailable`, `provider.unknown_model`, `provider.unknown_model_hint`, `provider.unreachable`, `provider.unsupported_parameter`, `routing.empty_routes`, `routing.unknown_provider`, `routing.unknown_task_type` | `acts`, `calls`, `input_minus_bytes_max`, `input_tokens`, `looks`, `output_tokens`, `refused`, `unknown_calls` |

I verifier, nello stesso modulo — guardano la pagina nel browser che l'ha aperta:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `browser.read_as_you` | `AccountReadVerifier` | `browser-read-as-you-verifier` | `browser.text_matches` | `browser.page_gone`, `browser.text_mismatch` |
| `browser.act_as_you` | `AccountActVerifier` | `browser-act-as-you-verifier` | `browser.expect_visible` | `browser.expect_missing`, `browser.page_gone` |
| `browser.login` | `LoginVerifier` | `browser-login-verifier` | `browser.expect_visible` | `browser.expect_missing`, `browser.page_gone`, `browser.second_factor` |
| `browser.guided_as_you` | `BrowserGuidedVerifier` | `browser-guided-as-you-verifier` | `guided.closed`, `guided.gestures_audited`, `guided.reservations_closed` | `guided.gesture_unaudited`, `guided.left_running`, `guided.reservation_open` |

Dove ciascuno ascolta la fermata del suo task (ADR 0054 §3) — nessuno viaggia, quindi su un nodo nessuno:

| Capability | Qui | Su un nodo |
|---|---|---|
| `browser.read_as_you` | `the navigation` | `None` |
| `browser.act_as_you` | `the first gesture` | `None` |
| `browser.login` | `the first gesture` | `None` |
| `browser.guided_as_you` | `the launch of the session` | `None` |

Per il login il punto sta **prima che il vault sia interrogato**: un task fermato non prende nessuna password.

**Prima della domanda** («partirebbe»), nell'ordine e ciascuno con il suo codice: gli argomenti; il sistema, la
cartella del profilo, il binario, e chi tiene la cartella (`browser.unsupported_system`,
`browser.profile_undeclared`, `browser.profile_unsafe`, `browser.not_installed`, `browser.profile_busy`); e, per
un login, il programma del vault, lo stato del vault e la voce. Un rifiuto nato lì non costa un sì, e **non
nomina mai una voce**. `browser.profile_busy` è ritentabile: ciò che tiene la cartella finisce.

**Una lettura con il profilo non lascia il sito che nomina**: il confine della navigazione è l'origine di quel
sito — quello di `browser.act` —, non ogni sito dichiarato. Un rimando verso un altro host, anche dichiarato, è
`browser.left_site`: seguirlo porterebbe le credenziali di un secondo sito in una lettura che ne ha nominato
uno.

**`browser.login`, dopo il sì.** Il tool apre la pagina nel browser del profilo; guarda che sia sul sito della
domanda, che i tre elementi ci siano una volta sola, che `password_field` sia `type="password"` —
altrimenti `browser.not_a_password_field` —, che non si dichiari una password nuova, un codice a tempo o una
carta, che `username_field` non si dichiari segreto, e che il modulo mandi con `POST` — altrimenti
`browser.login_form_get`: mandata con `GET`, la password sarebbe in un indirizzo. **Solo allora** ascolta la
fermata del suo task, al suo punto, e chiede al vault: una lettura sola della voce, riconfrontata con il sito
su quella stessa lettura. **Il vault è un'attesa, e dopo si guarda di nuovo**: la fermata — arrivata mentre il
vault rispondeva, la password è buttata e niente è scritto — e il campo, che con il modulo in cui sta deve
essere ancora quello guardato prima, altrimenti `browser.not_a_password_field`. Poi due `fill_secret` e un
click. Ciò che fallisce dopo il sì ha il suo codice: il sì è speso, e niente è stato scritto in nessun campo.

**La voce che il sì copre è quella che la domanda ha nominato.** Il piano può nominarla con `entry`, il suo id;
senza, è la sola il cui host è quello del sito, e il tool **ricorda** — in memoria, per le domande che
aspettano — quale voce ha trovato componendo la domanda. Dopo il sì legge quella, non quella che il vault
terrebbe adesso. Se ELA è ripartita fra la domanda e il sì il tool non lo sa più: `vault.entry_forgotten`,
niente è scritto, e lo step si richiede. **Il ricordo è per la chiamata, non per la domanda**: due domande
nate dalla stessa chiamata che hanno nominato voci diverse — il vault è cambiato in mezzo — non si
distinguono, e il tool non indovina: lo stesso codice, e niente è scritto. *(È la domanda 73 della milestone.)*

**Il secondo fattore** non entra in ELA: nessun codice a tempo, né preso dal vault. Se dopo il click la pagina
mostra un campo `one-time-code` e il testo atteso non compare, il verifier fallisce con
`browser.second_factor` — «do it by hand in ELA's window» — invece che con `browser.expect_missing`. Il
riconoscimento è parziale, come quello dei campi segreti.

**Il valore non viene mai dal piano**, e non entra nel modulo dei tool: il tool riceve due `Secret` dalla porta
del vault e li passa all'adapter del browser — a nessun altro, in nessun esito, messaggio o evento.

### 6. La sessione guidata con il profilo

`browser.guided_as_you` è la sessione di ADR 0060 — la stanza, il gateway, il bilancio, un task figlio per ogni
gesto, il «ferma» — con queste differenze, e nessun'altra:

- **È un'altra capability**: una policy di `browser.guided` non la copre, e viceversa — il Guardian nega un grant
  presentato per un'altra capability.
- **Nomina un sito solo** (decisione 30): lo schema ha `sites` di un elemento, e una chiamata che ne porta di più
  è negata prima della domanda. Con un sito solo ciò che il modello legge non può finire nell'indirizzo di un
  altro: non c'è un altro sito a cui la sessione possa mandare qualcosa. Lo scope di una policy può elencarne più
  d'uno; ogni sessione ne sceglie uno.
- **I suoi gesti sono quelli del profilo**: gli strumenti che il modello vede restano `read` e `act`; ciò che
  chiedono è `browser.read_as_you` e `browser.act_as_you`. **La capability e i gesti di una sessione sono un
  dato** — `SessionKind` nel tool, `SessionGestures` consegnato alla stanza quando la sessione si apre —, dove
  fino a M13.9 erano costanti in due moduli. **Nessun gesto di login**: un modello non vede gli attributi dei
  campi; la strada è la finestra, o uno step `browser.login` di un piano.
- **Un `act` chiede sempre**: è `HIGH`, e il figlio aspetta il sì di Tommaso.
- **Le sue letture le copre la sessione** (§1): `covers` nomina `browser.read_as_you`, fuori da `PolicyTerms`.

Dichiarazioni aggiunte, nella forma della tabella di ADR 0062 §1:

| Capability | Tetti | Mai coperti | Liberi | Rotta |
|---|---|---|---|---|
| `browser.guided_as_you` | `max_cost_usd`, `looks`, `seconds` | `task_type` | `goal` | `browsing` |

**Che cosa esce** (§57), riscritto per questa sessione: il fornitore e il perché sono quelli di ADR 0060 §8; i
dati sono la frase, il sito, le istruzioni di ELA, e **il testo delle pagine lette come Tommaso — contenuto
suo**. **La policy del fornitore, riletta il 2026-10-11**: la cancellazione entro trenta giorni e le sue
eccezioni sono quelle di ADR 0060 §8; l'articolo nomina in più i modelli che il fornitore chiama *Covered
Models*, per i quali la conservazione e una revisione valgono anche dove un accordo le avrebbe tolte, e i
punteggi di una violazione segnalata, che restano più a lungo degli ingressi. *La rilettura è stata fatta con
uno strumento che riporta le frasi che gli si chiedono, non con il testo intero: che cosa ha trovato, e che
cosa non ha trovato, è la domanda 75 della milestone, e questo ADR non esce da Proposta prima che Tommaso abbia
letto la pagina.* La domanda e l'anteprima di una policy lo dicono nel campo `sends`. Le istruzioni al modello guadagnano
una riga: non aprire un indirizzo che conferma, cancella, disiscrive o esce se la frase non lo chiede. **Dentro
quel sito un modello può aprire qualunque indirizzo come Tommaso**, e la descrizione della capability lo dice.

**Una policy della sessione non ha un numero massimo di sessioni**, e regge perché l'avvio è di Tommaso. *Si
riesamina il giorno in cui ELA parte da sola (annotazione per la Fase 15).* Una revoca non ferma una sessione
già partita: le sue letture come Tommaso continuano fino ai suoi tetti, e l'uscita della revoca lo dice.

### 7. Mentre Tommaso entra a mano, ELA non guarda e non ascolta

ELA apre una finestra perché Tommaso entri in un sito con le sue mani, e di quella finestra non legge niente
attraverso il browser: nessun driver, nessuna pipe, nessuna porta (§8). **Quella garanzia è del browser, e
finisce lì.** Lo schermo e il microfono sono un'altra strada verso ciò che viene scritto in quella finestra: una
fotografia, una lettura o una registrazione fatte nel frattempo porterebbero la password.

Perciò le capability che guardano lo schermo o ascoltano **si rifiutano finché una mano può essere sul profilo**
(decisione 41), ciascuna con un codice suo, ritentabile — ciò che rende sbagliato il momento finisce:

| Capability | Tool | Codice | Che cosa dice di non fare |
|---|---|---|---|
| `perception.capture_screen` | `CaptureScreenTool` | `screen.login_window_open` | `ELA does not photograph the screen meanwhile` |
| `perception.read_screen_text` | `ReadScreenTextTool` | `screen.login_window_open` | `ELA does not read the screen meanwhile` |
| `perception.listen` | `ListenTool` | `listen.login_window_open` | `ELA does not listen meanwhile` |

**Prima della domanda** — il loro «partirebbe», che questi tool non avevano: rifiutavano solo
dentro la corsa, dopo che il sì era speso —, **e dentro la corsa**, dopo gli argomenti e prima di ogni altra
cosa: una decisione che un grant o una policy ha già permesso non passa dalla domanda. Prima della domanda non
si guarda nient'altro: il permesso del sistema e lo spazio restano della corsa, com'erano.

**Ciò che è cominciato prima non è fermato.** Il rifiuto guarda il profilo quando una cattura o un ascolto
comincia: un ascolto già in corso quando la finestra si apre arriva in fondo, e scrive ciò che ha sentito *(è
la domanda 77 della milestone)*.

**I tool non imparano che cos'è la finestra.** Ricevono dal punto di composizione una domanda sola — «non
adesso?» —, che risponde con la ragione o con niente, e la dicono com'è arrivata. La domanda guarda chi tiene il
profilo **a ogni chiamata**, mai da un ricordo:

| Chi tiene il profilo | La ragione |
|---|---|
| `window` | `the window of ELA's browser where you sign in by hand is open` |
| `process` | `a browser ELA did not start now is open on the profile of its browser, and you may be signing in there` |

**Anche un browser che questa ELA non ha lanciato.** La finestra di un'ELA uccisa resta aperta, ed è la stessa
finestra: di lei resta solo il lock della cartella, che nomina un processo vivo. Uno step di ELA sul profilo
non è qui: in una pagina che ELA guida nessuno sta scrivendo una password.

**Dove non c'è un profilo non c'è una finestra da aspettare**: senza una cartella dichiarata, o su un sistema
dove quel browser non parte, la domanda risponde niente, e guardare e ascoltare restano com'erano. **Ogni altro
sguardo che fallisce è un dubbio, e un dubbio rifiuta**: una cartella è dichiarata, ed ELA non sa dire se una
mano c'è sopra. È un dubbio anche chi tiene il profilo con un nome per cui ELA non ha una frase: il solo
tenitore che lascia guardare e ascoltare è uno step di ELA, detto per nome.

**Nessun codice nel Perception Core** (decisione 49). La sonda legge stato e non contenuto — l'applicazione
davanti, quante finestre, mai un titolo —, non lo manda a un modello né in un registro, e con la finestra
aperta direbbe solo ciò che ELA sa già, perché la finestra l'ha aperta lei. *Con la finestra del login aperta
ELA non legge il contenuto dello schermo e non ascolta; sa che la finestra c'è.*

### 8. La finestra, e le rotte del browser

**Con una finestra o senza è di Tommaso** (decisioni 18a e 34). Non è un argomento di nessuna capability e
nessun tool lo decide: è uno stato di ELA accesa, che cambia solo da una rotta di Tommaso, vale per gli step
con il profilo che partono da quel momento, e **torna «senza finestra» a ogni avvio**. Il browser vuoto resta
senza finestra.

**La finestra del login a mano** (decisione 18b). ELA lancia il binario, da solo, sulla cartella del profilo,
con gli argomenti dell'elenco chiuso di §4 e, se c'è, l'indirizzo `https` di un sito **dichiarato**. Non c'è
un driver, non c'è una pipe né una porta di debug, lo stdout e lo stderr del processo non vanno a nessuno: di
quella finestra ELA tiene una cosa sola, **l'attesa della sua fine**. Dentro la finestra il confine dei siti
non c'è — sono le mani di Tommaso —; dove ELA la apre è un sito dichiarato, o nessuno. **La finisce Tommaso,
uscendo dal browser** (Cmd-Q): sul Mac chiudere la finestra lascia il processo acceso, ed ELA di quella finestra
conosce solo la fine del processo — le frasi del prodotto dicono di uscire, non di chiudere. Alla
fermata di ELA riceve un `SIGTERM`, ed entro la grazia della chiusura è uccisa con il suo gruppo (§4). Non è
una capability: nessun piano e nessun modello la apre. Finché è aperta ELA non comincia a guardare né ad
ascoltare (§7).

**Un processo alla volta sul profilo** (decisione 18c). Chi tiene la cartella è derivato a ogni domanda, mai
ricordato: uno step di ELA, la finestra, o un processo che il lock della cartella nomina. La finestra che
trova la cartella tenuta non si apre: ELA non lancia un secondo processo su una cartella che ha trovato
occupata, perché è il lancio che può uccidere il primo.

Rotte nuove, in `ela/api/browser.py`, che raggiunge `CORE` con il token:

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/browser` | che cosa è il profilo, guardato attraverso il suo port: usabile o no e perché, libero o tenuto e da chi, con o senza finestra, collegato o no a un account |
| `POST` | `/browser/window` | con la finestra, o senza: l'interruttore di Tommaso |
| `POST` | `/browser/open` | la finestra del login a mano, su un sito dichiarato o su nessuno |

**Lo stato è il rifiuto dei tool, o chi tiene la cartella.** `GET /browser` risponde `free`; oppure il nome di
chi tiene il profilo, come lo dice il port — `step`, `window`, `process` —; oppure perché nessun browser può
partirci, con il codice che uno
step riceverebbe prima della sua domanda, senza il prefisso — una definizione sola, in `ela/tools/account.py`,
per i tool e per le rotte. `linked` e `saved` sono ciò che il browser dice di sé — se conosce un account di chi
l'ha fatto, quante password tiene il suo gestore —, **riletti a ogni richiesta, mai da una copia** (decisione
63), e «non letto» dove la cartella non si è potuta leggere: non «no», e non «nessuna».

**Una rotta non apre la cartella e non ne riceve il percorso** (decisione 35): chiede al port, che risponde
con fatti. Lo tiene la regola 69.

Errori aggiunti, nella forma della tabella di ADR 0023 §10:

| Caso | Eccezione | Stato |
|---|---|---|
| la finestra non si apre: un sito non dichiarato, un profilo su cui nessun browser può partire, o tenuto | `BrowserRefusedError` | `409` |

Codici aggiunti a `ela.ports.WireCode`:

| Codice | Membro | Quando |
|---|---|---|
| `browser.refused` | `BROWSER_REFUSED` | la finestra del login a mano non si è aperta: il messaggio comincia con il codice dei tool |

Il messaggio comincia con `browser.site_undeclared` per un sito che non è fra quelli dichiarati — il solo
codice che è di queste rotte e non dei tool —, e altrimenti con il codice che uno step con il profilo
riceverebbe: `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.unsupported_system`,
`browser.not_installed`, `browser.profile_busy`, `browser.failed`.

Un gruppo nuovo della CLI, **`ela browser`**:

| Comando | Rotta | Uscite |
|---|---|---|
| `ela browser status` | `GET /browser` | `0` `1` `2` `3` |
| `ela browser window show` | `POST /browser/window` | `0` `1` `2` `3` |
| `ela browser window hide` | `POST /browser/window` | `0` `1` `2` `3` |
| `ela browser open` | `POST /browser/open` | `0` `1` `2` `3` |

`ela browser open` prende un sito, o niente.

**L'audit**: tipi d'evento nuovi, senza contenuto. `BROWSER_WINDOW_OPENED` lo scrive la rotta che apre la
finestra, firmato da chi l'ha chiesta, con il sito se c'era. `BROWSER_WINDOW_CLOSED` lo scrive **chi aspetta la
fine del processo**, che è chi vede ogni fine di una finestra che questa ELA ha aperto — Tommaso che esce dal
browser, ELA che si ferma —, firmato da ELA: nessuna rotta la chiede, e una fine che nessuno ha chiesto
resterebbe senza riga. Porta il sito, se c'era — l'host, senza nome né porta —, e quanti secondi interi la
finestra è rimasta aperta: mai un indirizzo, e niente di ciò che vi è stato fatto — ELA non lo sa. *Restano
senza riga* la finestra di un'ELA uccisa, che nessuno aspetta più, e una fine la cui riga non si scrive: questa
è detta nel log, con il tipo dell'errore, e non ferma la chiusura di ELA. L'interruttore della finestra non è
un evento: non apre niente.

### 9. La domanda di un login: quale voce, e di chi

Prima di dire sì a un login Tommaso deve poter leggere **quale voce** del suo vault ELA userebbe, e **di chi**.
La domanda le porta in due campi suoi, accanto ai fatti di una pagina:

| Campo | Che cosa porta | Quando manca |
|---|---|---|
| `entry` | il nome della voce; per una voce che Tommaso non ha nominato, una frase che lo dice | la domanda non è un login |
| `username` | il nome utente della voce, mascherato | la voce non ne ha uno, o la domanda non è un login |

Le righe dei gesti nominano i campi della pagina — «types the username of that entry into …» — e non ripetono la
voce: quale voce è un fatto suo, non una parola dentro una frase.

**Ogni superficie che offre un sì li mostra tutti e due, o non risponde** (ADR 0045 §11): la console e il
telefono con «La voce» e «Nome utente», `ela approvals` con `entry` e `username`. Lo tiene la regola chiusa sui
campi di una domanda, che non conosce questi due per nome: li trova perché la domanda li dichiara.

**Sono contenuto di Tommaso, e stanno sotto il tetto**, come l'indirizzo e lo scopo di uno step: una superficie
oltre il tetto del task non li legge. **Ciò che nessuna superficie riceve mai**: il nome utente intero e la
password, che prima di un sì non lasciano l'adapter del vault, e l'id della voce, che è del piano. I due campi
stanno accanto alla domanda, non nel suo testo: l'audit della domanda non li porta.

### 10. La vista della console: «Il browser di ELA»

La risposta all'impronta di ADR 0044 §6: le capability nuove non hanno una vista propria delle loro chiamate —
una lettura, un gesto e un login con il profilo sono domande nell'Approval Center, con la loro frase e i campi
di §9, e passi nella vista del task; una sessione con il profilo si guarda come quella di ADR 0060. **La vista
che questo ADR aggiunge è «Il browser di ELA»**, la sesta: il profilo e il vault come `GET /browser` e
`GET /vault` li dicono, la finestra che si accende e si spegne, la finestra del login a mano che si apre su un
sito dichiarato o su nessuno, e il vault che si chiude. **Non lo apre**: una chiave non si incolla in una
pagina, e nessun campo della vista potrebbe portarne una. Il telefono non ha questa vista.

Rotte nuove, in `ela/api/console.py`, che raggiunge il cookie di una console:

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/console/browser` | il profilo e il vault, e i moduli di ciò che questa console può fare |
| `POST` | `/console/browser/window` | l'interruttore della finestra, dal Mac |
| `POST` | `/console/browser/open` | la finestra del login a mano, dal Mac |
| `POST` | `/console/browser/lock` | il vault chiuso, da qualunque console |

**Ciò che cambia qualcosa sullo schermo del Mac si fa dal Mac.** L'interruttore e la finestra del login li usa
una console il cui tetto è `LOCAL_ONLY` — i due capi del socket in loopback, come lo decide il middleware —;
da fuori la vista dice gli stati e fa una cosa sola, quella che toglie: chiude il vault, come la revoca di una
policy. Da fuori non si leggono nemmeno i siti dichiarati, né le frasi dei tool e del vault, che possono
nominare una cartella o un programma del Mac.

**La pagina non raggiunge niente attraverso ELA** (regola 55): chiama le funzioni delle rotte — quelle di
`ela/api/browser.py`, e quelle che `ela/api/vault.py` espone per lei, `vault_of` e `vault_locked`.

**Ogni modulo nomina ciò che chiede.** Un `POST` senza il suo campo — `shown`, `site`, `vault` — non è una
richiesta da indovinare: `422`, e niente cambia. Il sito vuoto è «nessun sito», ed è una risposta.

Errori aggiunti, nella forma della tabella di ADR 0023 §10:

| Caso | Eccezione | Stato |
|---|---|---|
| la finestra o il suo interruttore chiesti da una console che non è al Mac | `BrowserOutOfReachError` | `409` |

## Alternative considerate

- **Un grant della sessione con lo scope dei suoi siti**: è la forma delle policy di §59, e ADR 0060 l'aveva
  scartata. Qui non nasce un grant: la copertura è un fatto letto dalla stanza, che finisce con la sessione.
- **Una policy per le letture singole**, con il solo scope e la scadenza (la strada B della domanda 29): una riga
  aprirebbe ogni lettura come Tommaso su quei siti per novanta giorni, da qualunque piano. Scartata dalla review.
- **Nessuna copertura** (la strada C da sola): una sessione con il profilo chiederebbe a ogni sguardo. Vale per
  le letture singole di un piano, che chiedono.

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo
dice, con la sezione di questo ADR a cui guardare.

- **ADR 0011** §6 — una riga che chiede a meno di un'autorizzazione ha un terzo modo di essere coperta; e la
  firma di `decide` (§1).
- **ADR 0028** §9 — ciò che ELA guarda senza una capability non cambia: si rifiutano le capability, e la sonda
  resta com'è (§7).
- **ADR 0029** — ciò che deve essere vero prima di una cattura ha una cosa in più, chiesta anche prima della
  domanda (§7).
- **ADR 0030** §1 — il tool che legge il testo di una cattura si rifiuta come la cattura (§7).
- **ADR 0032** — ciò che il contesto riceve dalla percezione non cambia con la finestra aperta (§7).
- **ADR 0036** — ciò che deve essere vero prima che un microfono si apra ha una cosa in più (§7).
- **ADR 0038** §11 — il timeout di spegnimento rifiutato non è la grazia entro cui la chiusura porta a riposo i
  browser: quello interromperebbe un handler che può essere avvisato, questa chiude un figlio che è stato
  avvisato e non è uscito. E il gestore del segnale è di ELA, da quando c'è un'ELA da chiudere a quando la
  chiusura è finita: non quello che uvicorn installa (`docs/milestones/M13.4e.md`, «La misura dei segnali»).
- **ADR 0044** §4 e §5 — le rotte della console e le sue viste, con «Il browser di ELA» (§10).
- **ADR 0045** §3 — il terzo modo di coprire una riga che chiede a meno di un'autorizzazione, che non è un
  grant (§1).
- **ADR 0046** §3 — «un sì copre al massimo un effetto»: il sì a una sessione con il profilo copre le letture
  che il suo modello scrive, fino ai `looks` della sessione; e la riga di consumo della copertura di sessione
  (§1).
- **ADR 0047** §6 — il programma del vault riceve, oltre all'ambiente chiuso, `BW_NOINTERACTION` e, quando c'è
  una chiave, `BW_SESSION` (§2).
- **ADR 0052** §1, §3, §4, §6, §7, §8, §10 e §14 — ciò che lì è detto del browser è detto del browser vuoto:
  quello con il profilo ha un altro binario, il sandbox acceso, una cartella che dura, un confine più stretto
  per le letture, un tool che riempie un campo segreto, e un ambiente da cui esce anche ciò che fa scrivere il
  driver (§4, §5, e la riga qui sotto).
- **ADR 0060** §1, §4, §8 e §9 — una seconda capability di sessione, i suoi gesti, le sue risposte di §57; e
  l'alternativa scartata, che torna come una copertura che non è un grant (§1, §6).
- **ADR 0062** §1 — il mondo chiuso dei termini esteso a `covers` (§1).

Le altre conseguenze:

- **Regola di architettura 67**: la parola della stanza la costruisce la stanza, e nessun altro — non un tool,
  non l'executor che la consegna, non una rotta.

- **Regola di architettura 68**: un `Secret` lo apre solo un adapter della macchina, o un finto — mai un tool,
  una rotta o l'executor.
- **Regola di architettura 69**: la cartella del profilo la nominano le impostazioni, che la dichiarano e la
  controllano, e il punto di composizione, che la consegna all'adapter — e nessun altro modulo: non una rotta,
  non un tool, non l'audit. Chi vuole sapere qualcosa del profilo chiede al port, che risponde con fatti.
- **`settle` resta un contratto del punto di composizione**, accanto ai port dei browser — `Browser` e
  `AccountBrowser` — e non dentro (decisione 57): ciò
  che un browser fa è il port; portarlo a riposo lo fa una volta sola chi l'ha costruito. La chiusura di ELA
  porta a riposo **ogni** browser che `build()` costruisce, insieme ed entro una grazia sola; un test lo tiene
  a mondo chiuso.
- **ADR 0052 §14 si legge con questa riga accanto**: dall'ambiente di ELA escono, oltre a ciò che comincia con
  `NODE_`, anche `DEBUG…` e `PWDEBUG`, dal prefisso — con loro il driver scrive sul suo stderr il valore di ogni
  `fill` (misurato), e da M13.9 un `fill` può portare una password.

Con questo ADR le regole di architettura sono **sessantanove** (la 67, la 68 e la 69), i contratti di import-linter restano
**quindici**, i port diventano **trentacinque** (`Vault` e `AccountBrowser`), le rotte dell'API **settanta** e i comandi
della CLI **trentotto** (quelle del vault e del browser con i loro comandi, e quelle della vista della console); le
capability diventano **diciotto** (quelle di §5), le identità del middleware restano **sei**. *(I totali si aggiornano con le sezioni
che seguono: questo ADR si scrive con l'implementazione.)*
