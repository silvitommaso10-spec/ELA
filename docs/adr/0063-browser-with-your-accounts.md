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
il browser e prima di rilasciare il database, e ciascuno dei tre è raggiunto qualunque cosa abbia sollevato
quello prima. Una chiusura del custode che fosse in volo è finita quando la porta torna: il ciclo non si smonta
con un lancio di `bw` in corso.

**Lo stato è derivato, mai memorizzato**: `GET /vault` lo chiede a `bw status` a ogni richiesta. Per un vault
chiuso porta **la riga intera da incollare** (decisione 32), composta con il programma dichiarato — citato come
la shell vuole un percorso con uno spazio —, mai con un segnaposto: il `bw` da lanciare è quello di cui ELA ha
fissato l'identità. L'indirizzo dell'account, che `bw status` stampa, non lascia l'adapter.

Tre rotte nuove, in `ela/api/vault.py`, che raggiunge `CORE` con il token:

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
I due casi condividono il codice e si distinguono per lo stato: `403` è «non da qui», e il vault non è stato
interrogato.

Un gruppo nuovo della CLI, **`ela vault`**:

| Comando | Rotta | Uscite |
|---|---|---|
| `ela vault status` | `GET /vault` | `0` `1` `2` `3` |
| `ela vault open` | `POST /vault/session` | `0` `1` `2` `3` |
| `ela vault close` | `POST /vault/lock` | `0` `1` `2` `3` |

`ela vault open` esce con `2` senza mandare niente quando lo stdin è un terminale, o quando dalla pipe non arriva
nessuna chiave — `bw unlock` che ha fallito non ne stampa.

**L'audit**: due tipi d'evento nuovi, senza contenuto. `VAULT_OPENED` lo scrive la rotta che riceve la chiave,
firmato da chi l'ha consegnata, con l'istante in cui ELA la dimenticherà. `VAULT_CLOSED` lo scrive **il custode
della chiave**, che è chi vede ogni chiusura — un comando, l'ora, la fermata di ELA, una chiave finita altrove —:
firmato da chi l'ha chiesta, o da ELA quando nessuno l'ha chiesta, con il perché (`command`, `expired`,
`stopped`, `ended_elsewhere`), se il programma del vault è stato lanciato e ha chiuso, e il suo codice quando
non lo è stato. Una chiusura che nessuna rotta ha chiesto non resta senza riga.

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

Con questo ADR le regole di architettura sono **sessantotto** (la 67 e la 68), i contratti di import-linter restano
**quindici**, i port diventano **trentaquattro** (`Vault`), le rotte dell'API **sessantatré** e i comandi
della CLI **trentaquattro** (le tre del vault, e i suoi tre comandi); le
capability restano **quattordici**, le identità del middleware **sei**. *(I totali si aggiornano con le sezioni
che seguono: questo ADR si scrive con l'implementazione.)*
