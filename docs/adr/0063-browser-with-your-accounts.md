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
stanza, quando decide lo step; non la tiene. Una sessione chiusa non attesta niente: il suo figlio **chiede**,
come un `MEDIUM` ha sempre fatto. Una sessione è aperta nella stanza solo mentre il suo step gira, e quello step
gira perché è stato permesso: la stanza la apre con la prenotazione letta dal record `STARTED`.

**Il Guardian non conta: conta la stanza**, che ferma la sessione ai suoi `looks`.

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
aspetta più.

**Prima del sì nessuna password lascia l'adapter** (decisione 28, che rivede il secondo criterio della
registrazione — «senza il sì, la CLI non viene chiamata» — per mano di Tommaso e del revisore). `find` chiede lo
stato e l'elenco per l'indirizzo del sito, e restituisce l'id della voce, il nome, gli indirizzi, **il nome
utente mascherato** — il primo carattere, e per un indirizzo la parte dalla chiocciola (decisione 31) — e se c'è
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

**`bw lock` è di tutta la macchina**: `ela vault close` chiude anche ciò che Tommaso avesse aperto nel suo
terminale; e un `bw unlock` di Tommaso finisce la chiave di ELA (misurato, K2), che ELA scopre al controllo dopo.

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
modulo di ELA; nessun errore che esce dall'adapter ne porta il percorso. Prima di ogni lancio: se non c'è, ELA
la crea `0700` — esattamente, qualunque sia la umask —; se c'è, deve essere una cartella vera, di chi lancia
ELA, aperta a nessun altro, altrimenti `ProfileUnsafe`. **ELA non la stringe da sé.** Una cartella comparsa fra
lo sguardo e la creazione — due aperture insieme, la prima volta — è riguardata come ogni altra.

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
`--disable-sync`, `--allow-browser-signin=false`, e un indirizzo se c'è. ELA ne tiene una cosa sola: l'attesa
della fine. **Alla fermata di ELA è avvisata** — `SIGTERM`, a cui il browser esce da sé scrivendo i suoi cookie
—, **aspettata entro la stessa grazia** delle pagine, **poi uccisa con il suo gruppo**, e nominata. Mai lasciata
viva sulla cartella. *Misurato il 2026-10-11*: un processo fermo che non ha ancora detto che cosa fa di
`SIGTERM` ne è terminato subito, dal kernel; un browser fermo quando è già su resta fermo, e lo toglie la
grazia.

**La chiusura di ELA** porta a riposo questo adapter come quello del browser vuoto. Un browser del profilo
ucciso alla grazia **non perde la sua cartella**: l'adapter toglie solo i profili temporanei che Playwright
nomina, mai una cartella dichiarata. Ciò che un browser ucciso aveva imparato un momento prima non è scritto —
misurato, un cookie della pagina del browser ucciso non si ritrova —: è del browser, non di ciò che ELA toglie.

**Ciò che parte verso Google a ogni lancio** (§57: che cosa, verso chi, perché). Il browser stesso, non una
lettura di ELA, apre connessioni verso host di Google appena parte — misurato la notte del 2026-10-10:
`accounts.google.com` (`ListAccounts`) e `www.google.com` —, **con i cookie che il profilo ha per quegli host**
(letto, non misurato: la sonda non aveva un account). Non è un gesto, non passa dal confine, e niente di ciò
che è stato provato lo toglie. È il binario che parla con chi l'ha fatto; si dichiara, qui e nella guida.

**Solo sul Mac.** Su ogni altro sistema ogni uso solleva `BrowserUnsupported`, e nessuna cartella è creata.

## Alternative considerate

- **Un grant della sessione con lo scope dei suoi siti**: è la forma delle policy di §59, e ADR 0060 l'aveva
  scartata. Qui non nasce un grant: la copertura è un fatto letto dalla stanza, che finisce con la sessione.
- **Una policy per le letture singole**, con il solo scope e la scadenza (la strada B della domanda 29): una riga
  aprirebbe ogni lettura come Tommaso su quei siti per novanta giorni, da qualunque piano. Scartata dalla review.
- **Nessuna copertura** (la strada C da sola): una sessione con il profilo chiederebbe a ogni sguardo. Vale per
  le letture singole di un piano, che chiedono.

## Conseguenze

- **Si leggono con questo ADR accanto**: ADR 0045 §3 e ADR 0011 §6 — un terzo modo di coprire una riga che chiede
  a meno di un'autorizzazione —; ADR 0046 §3 — un sì copre al massimo un effetto: qui copre fino a `looks`
  letture —; l'alternativa scartata di ADR 0060; ADR 0062 §1, per il mondo chiuso esteso a `covers`; e ADR 0011,
  per la firma di `decide`.
- **Regola di architettura 67**: la parola della stanza la costruisce la stanza, e nessun altro — non un tool,
  non l'executor che la consegna, non una rotta.

- **Regola di architettura 68**: un `Secret` lo apre solo un adapter della macchina, o un finto — mai un tool,
  una rotta o l'executor.
- **Regola di architettura 69**: la cartella del profilo la nominano le impostazioni, che la dichiarano e la
  controllano, e il punto di composizione, che la consegna all'adapter — e nessun altro modulo: non una rotta,
  non un tool, non l'audit. Chi vuole sapere qualcosa del profilo chiede al port, che risponde con fatti.
- **`settle` resta un contratto del punto di composizione**, accanto ai due port e non dentro (decisione 57): ciò
  che un browser fa è il port; portarlo a riposo lo fa una volta sola chi l'ha costruito. La chiusura di ELA
  porta a riposo **ogni** browser che `build()` costruisce, insieme ed entro una grazia sola; un test lo tiene
  a mondo chiuso.
- **ADR 0052 §14 si legge con questa riga accanto**: dall'ambiente di ELA escono, oltre a ciò che comincia con
  `NODE_`, anche `DEBUG…` e `PWDEBUG`, dal prefisso — con loro il driver scrive sul suo stderr il valore di ogni
  `fill` (misurato), e da M13.9 un `fill` può portare una password.

Con questo ADR le regole di architettura sono **sessantanove** (la 67, la 68 e la 69), i contratti di import-linter restano
**quindici**, i port diventano **trentacinque** (`Vault` e `AccountBrowser`), le rotte dell'API **sessantatré** e i comandi
della CLI **trentaquattro** (quelle del vault, e i suoi comandi); le
capability restano **quattordici**, le identità del middleware **sei**. *(I totali si aggiornano con le sezioni
che seguono: questo ADR si scrive con l'implementazione.)*
