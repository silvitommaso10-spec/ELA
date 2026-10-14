# 0063. Il browser con i tuoi account: un Chrome di ELA che dura, le password che restano in Bitwarden, e una sessione che copre le sue letture

- **Stato:** Accettata il **2026-10-13**, con un commit suo: la prova a mano della sezione 28 di
  `docs/GETTING_STARTED.md` è passata sul Mac, sul branch e prima del merge, a `6d3c470`, l'ultimo commit
  (`~/Downloads/prova-m13.9-20261013-181603.txt`: 52 PASSATO, tutti al primo giro, 0 FALLITI, nessun no —
  decisione 159 di `docs/milestones/M13.9.md`), e lo stesso giorno Tommaso ha letto per intero le pagine del
  fornitore, nelle parole della review: «le due pagine del fornitore che ADR 0063 §6 cita» (decisione 160; §6).
  **Quali, lo dice la decisione 164**: i due articoli sulla conservazione, e lo stesso giorno quello
  sull'addestramento; i termini del contratto restano citati e non letti per intero (§6).
  **Con un debito datato**, dalla stessa sera: il costo dei suoi test, sopra la soglia di ADR 0052 §16, a carico
  di M9.5 (§12; decisione 165).
  *`6d3c470` era l'ultimo commit del branch quando la prova è girata: i commit venuti dopo, questo compreso,
  portano solo documenti e i test dei documenti, niente di ciò che la prova esercita (sezione 25, punto 1, di
  quella SPEC).*
  Proposta il **2026-10-11**, con l'implementazione di M13.9, per diventare Accettata con un commit suo quando
  quella prova fosse passata.
  **La prova del 12 ottobre non è passata**, per il login dal vault: che cosa si è misurato da allora è in §11, e
  ciò che un login lascia da leggere quando non riesce in §5.
  **Rivista da ADR 0064 (M13.4f)** il 2026-10-12: §2, il port ha `another`; §4, il cancello non è più una rotta di
  Playwright, e la misura sui service worker è rifatta — la difesa resta —; §5, i due confronti di `browser.login`
  sono il predicato dell'adapter, e i verifier dicono anche `browser.left_site` e `browser.another_page`; §11, la
  strada «misurata e non presa» è presa.
  **La prova del 13 ottobre**, sul commit di ADR 0064, non è passata per il solo login, che il sito ha rifiutato
  senza finestra e accettato con: dalla review di quel giorno (decisioni 143–146) `browser.login` parte sempre
  con la finestra e rilegge i due campi prima del click (§5, §8), la riga che apre il vault entra da sé nella
  cartella di ELA e la frase di `ela vault open` non indovina una causa (§3).
  **La prova delle 15:28 dello stesso giorno, a `c1d0ef8`, è passata — 48 su 48 —, e non è quella che accetta
  questo ADR**: non era sull'ultimo commit, e le risposte a occhio sono arrivate in meno di quanto serve a
  guardare. Dalla review di quel pomeriggio (decisioni 148–153): la chiusura della finestra torna quando nessun
  processo di quel browser nomina più la cartella (§8), un campo che porta solo un inizio è detto così (§5), e
  la vista della console dice del login (§10). La prova si rifà per intero. **Rifatta alle 18:16 dello stesso
  giorno, sul commit di quel giro: è quella in testa a questa riga.**
  **Rivista da ADR 0065 (M13.10)** il 2026-10-14: §1, `continues` sullo schema coperto fa smettere di coprire le policy nate prima (ADR 0065 §3); §4, la pagina con il profilo può durare fra due step di un task (ADR 0065 §3); §5, la voce non è più ricordata in memoria — `named` (ADR 0065 §2) —, `expect_text` è facoltativo e i tre fatti vanno anche al modello di un login che ha chiesto lui (ADR 0065 §4); §6, la sessione con il profilo ha il gesto di login (ADR 0065 §4); §8, chi tiene il profilo può essere `task`, e lo dice la stanza (ADR 0065 §3).
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
| `AccountBrowser` | §19, §57 | async | `installed`, `open`, `count`, `field`, `fill`, `click`, `text`, `title`, `left`, `another`, `keep`, `glance`, `close`, `occupied`, `window`, `shut`, `linked`, `saved`, `profiles`, `fill_secret`, `landed`, `can_show`, `open_shown`, `holds` |

*`another` è di ADR 0064 (M13.4f), §5, ed è del port `Browser`: questo lo eredita.*

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
<il programma dichiarato> unlock --raw | <il comando di questa ELA> vault open
```

**Tutte e due le metà sono percorsi assoluti** (decisione 98, review dell'11 ottobre a `1666739`: *corretto
apertamente*). Fino a quel giorno la metà di destra era il nome `ela`, cercato nel `PATH` di chi incollava la
riga: **proprio ciò che questo ADR rifiuta per la metà di sinistra**, ed è il programma che riceve la chiave del
vault. Sul Mac della prova `ela` non è in nessun `PATH` — ELA si avvia con `uv run ela` —, e la riga, incollata
com'era, rispondeva «command not found»: «la riga intera, mai con un segnaposto» (decisione 32) era
letteralmente falsa.
- **Il comando di ELA si deriva, non si scrive**: è quello installato **accanto all'interprete che esegue il
  Core**. *Misurato l'11 ottobre con `ps` sull'ELA che gira*, avviata con `uv run ela serve`: il Core è
  `<ambiente>/bin/python3 <ambiente>/bin/ela serve`. **L'interprete si prende com'è nominato, mai risolto**:
  quello di un ambiente virtuale è un link a quello da cui è nato, e il comando sta accanto al link. **Niente
  ricerca nel `PATH`.** *Su Windows* il comando porta la sua estensione, `ela.exe`, nella cartella degli script
  dell'ambiente — accanto al suo interprete lo stesso —: **misurato l'11 ottobre sul job di Windows della CI**,
  dove il test del comando gira: `<ambiente>\Scripts\ela.exe`, accanto a `python.exe`, ed è il comando di ELA.
  **Il Core su Windows non è supportato** (ADR 0040), e lì questa riga non viene mai composta: la misura dice
  dove sta il comando, non che la riga funzioni su un PC (domanda 102 di `M13.9.md`).
- **Citati come li vuole una shell**: un percorso con uno spazio è una parola sola, in tutte e due le metà.
- **Se ELA non sa nominare il proprio comando lo dice, e non stampa nessuna riga**: accanto all'interprete non
  c'è — ELA avviata in un altro modo —, e una riga che può non funzionare non è una riga. La frase dice che cosa
  mandare a che cosa; `opens_with` è vuoto.
- **Da quale cartella.** Il comando di ELA legge il token dell'API dal `.env` della cartella in cui è lanciato,
  o dall'ambiente. Quando ELA ha letto un `.env`, **la frase accanto alla riga nomina quella cartella**; la riga
  resta la riga, e funziona incollata nel Terminale in cui `ela vault status` l'ha appena stampata.
  ***Rivista dalla review del 13 ottobre 2026 (decisione 145), su un fatto***: due volte, il 12 e il 13 ottobre,
  la riga è stata incollata in una finestra che non era nella cartella di ELA — la frase accanto è letta dopo.
  **Ora la riga entra da sé in quella cartella, dentro una sottoshell**:

  ```
  (cd <la cartella del .env> && <il programma dichiarato> unlock --raw | <il comando di questa ELA> vault open)
  ```

  Funziona da qualunque cartella e **non sposta il terminale di chi la incolla**; i due percorsi assoluti sono
  quelli di prima, e la cartella è citata come li vuole una shell. Dove ELA non ha letto nessun `.env` la riga
  resta senza sottoshell. **La frase accanto dice di lanciarla nel proprio terminale, e non più dove.**
  *Misurato il 13 ottobre in `zsh` 5.9 e in `bash` 3.2, ciascuna una shell interattiva su un terminale suo,
  partita in un'altra cartella* (`the_line_from_any_folder.py`, con la sua uscita, in
  `.git/m13.9-reference/review-0d4455a/`): la domanda arriva sul terminale, la risposta scritta lì arriva al
  primo programma senza essere mostrata, il secondo riceve da un tubo ciò che il primo ha stampato e gira nella
  cartella di ELA, e dopo la riga la shell è dov'era. *Con la riga di prima, lanciata dalla stessa cartella, il
  secondo programma gira lì e non trova nessun `.env`: è il fatto.* **Né `bw` né il comando di ELA sono stati
  lanciati dalla sonda**: al loro posto due programmi suoi, che fanno con i loro flussi ciò che fanno quei due.
  Con `bw` vero la sottoshell non è misurata, e non in altre shell.
- **Vale ovunque la riga compare**, perché nasce in un posto solo, la porta del vault: `ela vault status`, il
  messaggio di `vault.locked` nell'esito di un task, la vista della console. `ela vault open`, se riceve un
  terminale al posto di una pipe, rimanda a `vault status` e non scrive una mezza riga.
- **Il test che mancava**: il comando, com'è derivato, **lanciato davvero** da una cartella che non è di ELA e
  in un ambiente che non ha `ela` nel `PATH`, è il comando di ELA. Fino a qui i test affermavano la stringa.

`ela vault open` legge la chiave dallo stdin e **rifiuta un terminale**: una chiave non si scrive e non si
incolla. **Prima di leggere guarda di avere il token** (decisione 107, dalla prova del 12 ottobre): lanciato dove
il token non c'è lo dice subito, mentre il programma del vault sta ancora chiedendo la password principale, e
non prende una chiave che nessuno riceverà. **Quando sul tubo non arriva nessuna chiave dice il fatto, e non
indovina una causa** (decisione 146, dalla prova del 13 ottobre): il programma del vault non ne ha stampata
nessuna, ciò che ha scritto è sopra quella riga, e a ELA non è stato mandato niente. Chiedeva «a wrong master
password?»; quel giorno `bw` non aveva raggiunto il suo server, e l'aveva scritto lui. *Fra le misure*: **`bw
unlock` ha chiesto il suo server, e senza rete è caduto** — visto da Tommaso nel suo terminale il 13 ottobre,
non da una sonda —; **che cosa faccia da scollegati non è misurato**. La manda a `POST /vault/session`, che la riceve **solo se i due capi del socket sono di loopback**
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
che la incontra**: la dimentica lì, e lo dice. **Allo scadere dell'ora il custode chiede prima lo stato, con
la sua chiave** (decisione 81, review dell'11 ottobre): se quella chiave non apre più — un `unlock` di Tommaso
che nessun uso aveva ancora incontrato —, **la dimentica senza chiudere**, e la riga dice «finita altrove»;
`bw lock` avrebbe chiuso la sessione che Tommaso ha aperto dopo. **Se lo stato non si legge, chiude**: è il
lato sicuro. Vale dove l'ora scade — nell'attesa del custode, e a un uso che guarda l'orologio —, e non per un
comando: `ela vault close` è Tommaso che dice «chiudi», e chiude.

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
(`fill_secret`). *Dal 13 ottobre 2026 (decisioni 143 e 144)*: una pagina aperta **con la finestra qualunque
cosa dica l'interruttore** (`open_shown`), se una finestra si può avere adesso (`can_show`), e se un campo porta
ancora ciò che un `Secret` contiene (`holds`) — §5 e §8. Il suo adapter, `ela/infrastructure/machine/account.py`, **eredita** l'adapter del browser
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

**Ogni lancio nomina il profilo che ELA prepara** (decisione 79, review dell'11 ottobre):
`--profile-directory=Default`, con il driver e nella finestra. *Misurato lo stesso giorno*, su una cartella con
due profili del browser di cui il secondo usato per ultimo — ciò che resta dopo che Tommaso ne ha aggiunto uno
da dentro la finestra —: **senza un nome il browser apre l'ultimo profilo usato**, e un cookie lasciato da un
passo di ELA finiva nel secondo, le cui preferenze ELA non riscrive e i cui service worker non toglie. Con il
nome finisce in `Default`, nei tre lanci — la finestra, il lancio guidato, il lancio guidato con la finestra.
ELA non prepara e non usa gli altri profili; ne conta le password salvate, e lo stato dice quanti sono (§8).
*Misurato insieme*: **un lancio guidato non ripristina pagine** — né con «continua da dove eri rimasto», né con
«apri queste pagine», né dopo una finestra uccisa, là dove una finestra riaperta la pagina di prima la richiede
—: niente carica prima che il cancello esista, e la tabella delle preferenze non guadagna una riga. Poggia sugli
argomenti con cui Playwright lancia questa versione, che ELA non può togliere: `ignore_default_args` non è fra
le opzioni dell'elenco chiuso.

**I rapporti di un crash stanno dentro la cartella del profilo** (decisione 74, la stessa review):
`--breakpad-dump-location=<cartella>/Crashpad`, composto dall'adapter con la cartella — il solo altro argomento
che la nomina, con `--user-data-dir`. *Misurato lo stesso giorno, facendo cadere il browser*: **in questa
versione nessun argomento spegne il raccoglitore dei crash** — `--disable-breakpad`, che Playwright passa già
da sé, sul Mac non è ascoltato: il raccoglitore girava accanto al browser, e un crash scriveva **un minidump di
più di un megabyte — memoria del processo** — nella cartella predefinita del binario, fuori dal profilo. Con
questo argomento il suo database nasce nella cartella del profilo e un crash scrive lì e non altrove; il
raccoglitore parte senza un indirizzo a cui mandare. Le regole della cartella — `0700`, fuori da ciò che si
sincronizza, mai letta da chi non è il suo adapter — valgono allora anche per ciò che un crash lascia. **Ciò
che un crash ha lasciato non passa al lancio dopo** (decisione 90, review del pomeriggio dell'11 ottobre): prima
di ogni lancio, guidato o della finestra, l'adapter toglie quella cartella — di un link il link, mai ciò a cui
porta —, e il browser la ricrea. Un rapporto è memoria del processo che teneva le sessioni, e non serve a
nessuno: ELA non lo legge mai. Fra un crash e il lancio dopo sta nella cartella, sotto le sue regole.

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
che non è guardato* (decisione 78: dichiarato): **una ACL sulla cartella**. «Aperta a nessun altro» è guardato
sui bit del modo, e una cartella `0700` con una ACL che lascia leggere ad altri passa: leggerla vorrebbe un
programma del sistema lanciato a ogni sguardo, che sono anche quelli di ogni cattura e di ogni ascolto.

**Chi tiene la cartella si legge dal lock, per il pid**: solo ciò che può essere il pid di un browser — cifre,
sopra il primo processo del sistema, entro il massimo di un pid — è chiesto al kernel. Un lock che nomina
altro non l'ha lasciato un browser che gira, e non tiene niente. **E un pid che il kernel conosce tiene la
cartella solo se la riga di comando di quel processo la nomina** (decisione 82): un lock rimasto da un browser
ucciso, il cui pid il sistema ha poi dato a un altro processo, non tiene niente — la tabella è in §8.

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

***Rivista da ADR 0064 (M13.4f), il 2026-10-12.*** *Il cancello non è più una rotta di Playwright: è una sessione
del browser, avvisata di ogni richiesta (ADR 0064 §2). La misura è rifatta con quel cancello, e dice lo stesso:
**di una navigazione a cui risponde un worker la sessione non è avvisata**, e toglierli prima di ogni lancio
guidato resta necessario. In più, attraverso il cancello un worker non si può nemmeno registrare, e ciò che
chiede da sé è rifiutato (ADR 0064 §6).*

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
sono un elenco chiuso — la cartella, dove vanno i rapporti di un crash, `--use-mock-keychain`,
`--no-first-run`, `--no-default-browser-check`, `--disable-sync`, `--allow-browser-signin=false`,
`--profile-directory=Default`, e un indirizzo se c'è. **L'elenco lo chiude l'adapter,
chiunque lo chiami**: ciò che non è l'indirizzo di un sito — `http` o `https`, con un host, senza un nome né
una parola dentro — non è passato al binario, dove sarebbe un suo argomento o aprirebbe ciò che non è un sito.
Che sia `https`, e di un sito dichiarato, lo dice la rotta (§8). ELA ne tiene una cosa sola: l'attesa
della fine. **Alla fermata di ELA è avvisata** — `SIGTERM`, a cui il browser esce da sé scrivendo i suoi cookie
—, **aspettata entro la stessa grazia** delle pagine, **poi uccisa con il suo gruppo**, e nominata. Mai lasciata
viva sulla cartella: **il lancio è un compito dell'adapter**, che arriva in fondo anche se chi l'ha chiesto se
ne va, e che la chiusura aspetta prima di dire libera la cartella. *Misurato il 2026-10-11*: un processo fermo
che non ha ancora detto che cosa fa di `SIGTERM` ne è terminato subito, dal kernel; un browser fermo quando è
già su resta fermo, e lo toglie la grazia. **Un browser che si rilancia da sé da dentro la finestra** finisce
il processo che ELA aspetta e ne avvia uno che ELA non ha conosciuto: di lui resta il lock, lo stato dice
`process`, e lo chiude il comando di §8 — non la chiusura di ELA, che avvisa solo ciò che ha avviato. *Il
rilancio da dentro la finestra non è misurato* — non ci sono mani su quella finestra —: ciò che è provato, con
il binario vero, è una finestra che un'altra ELA ha avviato, vista come `process` e chiusa dal comando.

**La chiusura di ELA** porta a riposo questo adapter come quello del browser vuoto. Un browser del profilo
ucciso alla grazia **non perde la sua cartella**: l'adapter toglie solo i profili temporanei che Playwright
nomina, mai una cartella dichiarata. Ciò che un browser ucciso aveva imparato un momento prima non è scritto —
misurato, un cookie della pagina del browser ucciso non si ritrova —: è del browser, non di ciò che ELA toglie.

**Ciò che ELA lascia fuori dalla cartella del profilo** (decisione 47; misurato il 2026-10-11, con la finestra
lanciata dall'adapter su una cartella di prova). La lista di preferenze di macOS di Chrome for Testing,
`~/Library/Preferences/com.google.chrome.for.testing.plist`: è dell'applicazione, non di Tommaso, porta una
chiave sola — `LastRunAppBundlePath` —, e un lancio non la cambia. **La cartella predefinita del raccoglitore
dei crash**, `~/Library/Application Support/Google/Chrome for Testing/Crashpad/`, di cui fino alla review
dell'11 ottobre ogni lancio riscriveva `settings.dat`: con l'argomento qui sopra **un lancio di ELA non la tocca
più**, e ciò che vi fosse rimasto è di prima. **E il rapporto che il sistema scrive da sé** quando il processo
del browser cade: un file in `~/Library/Logs/DiagnosticReports`, come per ogni applicazione — i nomi delle
funzioni di ogni thread, i registri di quello caduto, le librerie caricate; **niente della memoria del
processo, non la riga di comando, non il percorso della cartella** (letto su quelli della sonda). Nessun
argomento del browser lo sposta o lo spegne: si dichiara, e la guida dice come si toglie.

**Dopo un crash della finestra il sistema può riaprire il browser senza gli argomenti di ELA** — misurato una
volta, l'11 ottobre: cinque secondi dopo il crash provocato della finestra girava un Chrome for Testing senza
nessun argomento, figlio di `launchd`, sulla sua cartella predefinita e senza `--use-mock-keychain`. Non è sulla
cartella del profilo, e non è un processo di ELA: lo stato non lo vede e nessun comando lo chiude. Se sia stato
il sistema da sé o un «Riapri» premuto in un suo dialogo, la sonda non lo distingue. **Dichiarato, e non si
rimisura** (decisione 88): un browser ricomparso dopo un crash non è di ELA, e si chiude a mano; rimisurarlo
riaprirebbe un browser senza il portachiavi finto.

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
click il modulo lo rimanda il cancello dell'adapter, e il valore ripassa dal processo di ELA. *Rivista da ADR 0064
(M13.4f), il 2026-10-12: il modulo lo manda il browser, e il cancello lo guarda senza rifarlo. **Il valore passa
ancora dal processo di ELA dopo il click**: il driver consegna al client di Playwright, che gira lì, ogni
richiesta della pagina con il suo corpo — letto nel codice del driver e del client, non misurato (ADR 0064 §8).
L'adapter non lo legge e non lo tiene. La frase resta com'è, e resta vera. (Una prima stesura di questa nota
diceva che il valore non ripassava più: l'ha trovata falsa la rilettura critica di M13.4f.)*

I tool, in `ela/tools/account.py`:

| Capability | Tool | Nome | Idempotente | Codici d'errore | Numeri nell'audit |
|---|---|---|---|---|---|
| `browser.read_as_you` | `AccountReadTool` | `browser-read-as-you` | sì | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `shown`, `status`, `total` |
| `browser.act_as_you` | `AccountActTool` | `browser-act-as-you` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.secret_field`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `gestures`, `status` |
| `browser.login` | `LoginTool` | `browser-login` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.field_changed`, `browser.http_status`, `browser.left_site`, `browser.login_form_get`, `browser.no_window`, `browser.not_a_password_field`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.secret_field`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system`, `vault.entry_ambiguous`, `vault.entry_forgotten`, `vault.entry_not_for_site`, `vault.failed`, `vault.locked`, `vault.no_entry`, `vault.no_password`, `vault.no_program`, `vault.program_changed`, `vault.program_gone`, `vault.program_is_a_script`, `vault.timeout`, `vault.unauthenticated`, `vault.undeclared` | `gestures`, `status` |
| `browser.guided_as_you` | `BrowserGuidedTool` | `browser-guided-as-you` | no | `arguments.invalid`, `guided.cache`, `guided.cap_below_one_call`, `guided.cost`, `guided.duration`, `guided.failed`, `guided.folder_changed`, `guided.looks`, `guided.max_tokens`, `guided.model_changed`, `guided.not_installed`, `guided.permission_asked`, `guided.route_changed`, `guided.session_gone`, `guided.stopped`, `guided.tools_changed`, `guided.unchecked`, `guided.unreserved`, `provider.authentication_error`, `provider.bad_request`, `provider.malformed_response`, `provider.no_output`, `provider.rate_limited`, `provider.refusal`, `provider.rejected`, `provider.server_error`, `provider.spend_limit`, `provider.timeout`, `provider.unavailable`, `provider.unknown_model`, `provider.unknown_model_hint`, `provider.unreachable`, `provider.unsupported_parameter`, `routing.empty_routes`, `routing.unknown_provider`, `routing.unknown_task_type` | `acts`, `calls`, `input_minus_bytes_max`, `input_tokens`, `looks`, `output_tokens`, `refused`, `unknown_calls` |

I verifier, nello stesso modulo — guardano la pagina nel browser che l'ha aperta:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `browser.read_as_you` | `AccountReadVerifier` | `browser-read-as-you-verifier` | `browser.text_matches` | `browser.page_gone`, `browser.text_mismatch`, `browser.left_site` |
| `browser.act_as_you` | `AccountActVerifier` | `browser-act-as-you-verifier` | `browser.expect_visible` | `browser.expect_missing`, `browser.page_gone`, `browser.left_site`, `browser.another_page` |
| `browser.login` | `LoginVerifier` | `browser-login-verifier` | `browser.expect_visible` | `browser.expect_missing`, `browser.page_gone`, `browser.second_factor`, `browser.left_site`, `browser.another_page` |
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
`browser.login_form_get`: mandata con `GET`, la password sarebbe in un indirizzo. **Solo allora** chiede al
vault — un task già fermato è ascoltato qui, prima, e non prende nessuna password —: una lettura sola della
voce, riconfrontata con il sito su quella stessa lettura. **Il vault è un'attesa, e il punto del tool viene
dopo.** Il campo, con il modulo in cui sta, deve essere ancora quello guardato prima, altrimenti
`browser.not_a_password_field`; poi il tool **ascolta la fermata al suo punto, l'ultimo istante prima del primo
gesto** (ADR 0054 §3): una fermata arrivata mentre il vault rispondeva è ascoltata lì — ciò che il vault ha
dato è buttato, niente è scritto, e lo step si chiude come ogni step fermato prima del suo punto. Poi due
`fill_secret` e un click, con uno sguardo alla fermata fra l'uno e l'altro. Ciò che fallisce dopo il sì ha il
suo codice: il sì è speso, e niente è stato scritto in nessun campo.

**La voce che il sì copre è quella che la domanda ha nominato.** Il piano può nominarla con `entry`, il suo id;
senza, è la sola il cui host è quello del sito, e il tool **ricorda** — in memoria, per le domande che
aspettano — quale voce ha trovato componendo la domanda. Dopo il sì legge quella, non quella che il vault
terrebbe adesso. Se ELA è ripartita fra la domanda e il sì il tool non lo sa più: `vault.entry_forgotten`,
niente è scritto, e lo step si richiede. **Il ricordo è per la chiamata, non per la domanda**: due domande
nate dalla stessa chiamata che hanno nominato voci diverse — il vault è cambiato in mezzo — non si
distinguono, e il tool non indovina: lo stesso codice, e niente è scritto. *Decisa l'11 ottobre (domanda 73):
resta così — ogni ramo finisce al sicuro, e un sì perso dopo un riavvio è un costo accettato. La forma giusta,
ciò che il sì ha nominato consegnato al tool con il sì, è un'annotazione di M13.10, la cui SPEC la decide.*

**Il secondo fattore** non entra in ELA: nessun codice a tempo, né preso dal vault. Se dopo il click la pagina
mostra un campo `one-time-code` e il testo atteso non compare, il verifier fallisce con
`browser.second_factor` — «do it by hand in ELA's window» — invece che con `browser.expect_missing`. Il
riconoscimento è parziale, come quello dei campi segreti.

**Che cosa lascia da leggere un login che non riesce** (decisione 106, 2026-10-12). La prova del 12 ottobre è
finita su `browser.expect_missing`, e nessuno sapeva che cosa il sito avesse risposto. **Il risultato** di
`browser.login` porta tre cose della pagina com'era quando il tool l'ha lasciata: `ended_at`, dove è finita —
**host e percorso**, mai la query né il frammento, mai un utente scritto prima dell'host, mai ciò che un sito
scrive dopo un punto e virgola in un passo del percorso —; `ended_status`, lo stato dell'ultimo documento chiesto
dalla cornice principale, quello della pagina e non del rimando che ci ha portato, **vuoto se a ciò che è stato
inviato non è tornato niente**; e se il campo della password del piano c'era ancora. **Nel risultato e in nessun
altro posto**: la frase di un fallimento del verifier va nell'audit, dove un percorso non entra (ADR 0052 §12),
e dice solo dove leggerle; `ended_status` non è fra i numeri che l'audit prende da un risultato. **Le legge il
tool, dopo il click** — che ha già aspettato la navigazione che ha avviato: misurato con un sito lento —, **e
dopo che il documento è arrivato**, un evento della pagina: la pagina dopo un rimando la chiede il browser, e il
suo indirizzo è già quello quando il suo modulo non c'è ancora. **Si leggono insieme**: il modulo di nuovo, con
il suo campo, è un sito che ha rifiutato l'invio; un'altra pagina con `200` e senza il campo è un sito che l'ha
accettato; nessuno stato è un sito che non ha risposto; uno stato d'errore senza il campo è una pagina d'errore
o di blocco, e non un accesso. *Ciò che non dicono*: un sito che accede senza navigare. **Una pagina finita su
un altro sito non è raccontata**: dopo il click il tool confronta dove la pagina è con il sito della domanda, e
altrove è `browser.left_site` con la sola origine — la pagina è chiusa, non consegnata al verifier (§11).
**Un costo**: una pagina il cui documento non finisce di arrivare nel tempo del tool chiude lo step con
`browser.timeout` dopo i tre gesti, dove prima passava al verifier.

***Rivista da ADR 0064 (M13.4f), il 2026-10-12.*** *«Dopo il click il tool confronta dove la pagina è» non è più
un confronto del tool: è il predicato che l'adapter chiede a ogni uso della pagina, prima e dopo, per ogni tool
(ADR 0064 §4). L'esito è lo stesso — `browser.left_site` con la sola origine, e la pagina non consegnata —, e
così il confronto all'apertura. Se la pagina ne ha aperta un'altra il risultato lo dice (`another_page`), e il
verifier risponde `browser.another_page` quando il testo non compare (ADR 0064 §5).*

**`browser.login` parte sempre con la finestra, qualunque cosa dica l'interruttore** (decisione 143 della
review del 13 ottobre 2026: *rivede apertamente §8*, «nessun tool lo decide»). **Il fatto**: nella prova del 13
ottobre, sul commit del cancello di ADR 0064, il login dal vault senza finestra ha fatto i suoi tre gesti e il
sito ha ridato il modulo — `ended_at` sul percorso del login, `200`, il campo della password ancora lì —; lo
stesso piano, subito dopo, con `ela browser window show`, è finito sulla prima pagina del sito senza il campo; e
una lettura fatta poi senza finestra ha trovato il nome utente e «logout» (`docs/milestones/M13.9.md`, sezione
23). È la seconda riga della regola scritta prima dei numeri (decisione 119): **un sito può rifiutare un
browser che si dice senza finestra**. *Misurato su un sito solo, con un login per modo*: non dice quanti siti lo
facciano, né che cosa quel sito guardi. **Il perché della decisione**: un login che fallisce spende un sì e una
lettura del vault, e lascia al sito un tentativo sbagliato; chi approva è presente, perché il login chiede a
ogni uso; **e non è un travestimento** — il browser non dice di sé niente di diverso da ciò che è: con la
finestra si chiama `Chrome` perché ha una finestra (§11). **Le altre capability con il profilo restano come
dice l'interruttore**: senza finestra funzionano, misurato dalla stessa prova.

- **La domanda lo dice**, nella frase del tool — ciò che la domanda mostra come «che cosa fa» — e in nessun
  altro posto: mentre ELA entra, sullo schermo compare una finestra del suo browser, e finché c'è non si scrive.
- **Se una finestra non si può avere il login non parte senza** — `browser.no_window`. ELA lo chiede al sistema
  con la lettura che la percezione fa già: se questo processo sta dentro una sessione dello schermo. Una
  sessione letta è una sessione, bloccata o no, davanti o no; **una sessione non letta è un dubbio, e nel dubbio
  il login non parte**. Prima della domanda è un rifiuto che non costa un sì e non chiede niente al vault; dopo
  il sì — la sessione è andata via nel frattempo — lo dice l'apertura stessa: il sì è speso, nessun browser è
  partito, e il vault non è stato aperto. **Non c'è un cammino del login che lanci senza finestra.** *Misurato
  da dentro la sessione di Tommaso, dove la lettura dice di sì e il lancio con la finestra riesce*
  (`a-session-of-the-screen.txt`); **il caso senza una sessione dello schermo non è misurato**: su questo Mac
  non si costruisce senza uscire da quella sessione, e i test lo costruiscono consegnando la risposta. *Deciso
  il 13 ottobre (decisione 149)*: resta così — nel dubbio non parte —, e il caso senza sessione si misura il
  giorno che ELA gira così. Che
  cosa faccia il binario lanciato con la finestra fuori da una sessione, ELA non lo prova.
- **I due campi sono riletti subito prima del click** (decisione 144) — `browser.field_changed`. *Misurato il
  13 ottobre* (`does_the_window_take_the_keyboard.py`, con la sua uscita): il browser di un lancio con la
  finestra **viene davanti** — in due giri su tre: nel terzo davanti è rimasta un'altra applicazione —, e
  dentro il browser il fuoco è sul campo appena scritto; un tasto premuto in quei secondi finisce nel modulo.
  Perciò, scritti i due valori, il tool chiede al browser se ciascun campo porta ancora ciò che è stato
  scritto: **il confronto lo fa l'adapter**, a cui i `Secret` sono consegnati come gli sono consegnati per
  scrivere, e al tool torna un sì o un no. Se uno dei due è cambiato — **o non c'è più** — **non clicca**: i
  due gesti sono contati, la pagina è chiusa, e nessuna frase porta un valore. **ELA sa di non aver cliccato;
  non sa se un tasto ha inviato il modulo**: un Invio premuto in quei secondi lo invia da sé, e la frase lo
  dice così — «niente è stato inviato» era più di ciò che ELA può dire (*corretto dalla rilettura critica, lo
  stesso giorno*). Lo stesso vale se il tempo del tool finisce **mentre** i campi sono riletti: la frase dice
  che ELA non ha cliccato, e non «il click è stato chiesto». **Il confronto è intero**: un campo che tiene meno
  di ciò che riceve — una lunghezza sua — o che la pagina riscrive non porta ciò che è stato scritto, e un
  login lì finisce `browser.field_changed` senza essere inviato; *non so quanti siti lo facciano*.
  ***Deciso il 13 ottobre (decisione 152): resta il confronto con ciò che è stato scritto***, e il caso è detto
  per ciò che è: l'adapter risponde una di tre cose — il campo porta ciò che è stato scritto, **ne porta solo
  un inizio**, o non lo porta —, e per «solo un inizio» la frase dice che è la pagina a tenere meno di ciò che
  riceve, non una tastiera, **senza dire quanto**: una lunghezza è qualcosa di una password. Un campo vuoto non
  è un inizio. *Che cosa non è misurato*: un tasto vero — mandarne uno al sistema
  chiede un permesso che ELA non chiede: la sonda ha un modo in cui aspetta il tasto di chi è al Mac, non
  lanciato —; ciò che il documento dice del fuoco non basta da solo, perché lo dice uguale senza finestra: ciò
  che decide è quale applicazione è davanti. *E fra la rilettura e il click resta un istante.*

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
suo**. **La policy del fornitore, riletta il 2026-10-11, frase per frase, ognuna con la pagina da cui viene e
la data che quella pagina mostra** (decisione 75):

| Che cosa dice | La pagina | La data che mostra |
|---|---|---|
| «we automatically delete inputs and outputs on our backend within 30 days of receipt or generation» — per chi usa l'API, con le sue eccezioni: una conservazione più lunga scelta da chi usa il servizio, un accordo diverso, la Usage Policy, la legge | `privacy.claude.com/en/articles/7996866`, «How long do you store my organization's data?» | 1 luglio 2026 |
| per ciò che è segnalato come violazione: «We retain inputs and outputs for up to 2 years and trust and safety classification scores for up to 7 years» | la stessa | 1 luglio 2026 |
| «Additionally, for Covered Models, we require limited data retention and review as a part of our safety work» | la stessa, che rimanda alla pagina qui sotto | 1 luglio 2026 |
| quali sono: «Mythos-class models and future models with similar capabilities that we designate as covered models»; per loro «Prompts submitted to, and outputs generated by, covered models are retained for 30 days», anche dove un accordo aveva tolto la conservazione; «By default, no Anthropic personnel can read your retained conversations», e una persona le legge solo per un percorso controllato, quando un sistema automatico le segnala; «For all other models, everything you use is unaffected and stays under the current terms» | `privacy.claude.com/en/articles/15425996`, «Data retention practices for Covered Models» | 5 settembre 2026 |
| **l'addestramento**: «By default, we will not use your inputs or outputs from our commercial products (e.g. Claude for Work, Anthropic API, Claude Gov, etc.) to train our models», salvo ciò che chi usa il servizio segnala espressamente o sceglie di lasciar usare | `privacy.claude.com/en/articles/7996868`, «Is my data used for model training?» | 18 agosto 2026 |
| lo stesso, nei termini del contratto: «Anthropic may not train models on Customer Content from Services» | `anthropic.com/legal/commercial-terms`, sezione B | in vigore dal 17 giugno 2025 |

**La frase sull'addestramento non sta più dove ADR 0060 §8 l'aveva letta**: sull'articolo della conservazione,
oggi, non c'è nessuna frase sull'addestramento — tre letture, due dell'11 ottobre con uno strumento che
riassume e una terza lo stesso giorno, che ha chiesto le frasi fra virgolette —; sta nelle due pagine delle
ultime due righe, ed è citata da lì. **ADR 0060 §8 si legge con questa tabella accanto.**

**Nessun elenco dei modelli che il fornitore conserva è scritto in ELA**: quali modelli sono «covered» lo dice
una pagina che cambia, e una copia a mano sarebbe sbagliata il giorno dopo. Ciò che ELA tiene è il modello
della rotta nei termini di una policy, e **il test che lo tiene dice, nel messaggio con cui fallisce, che chi
cambia il modello della rotta rilegge la policy del fornitore** per quel modello e la ridata qui. **La
rilettura sta con quella del listino** (ADR 0061): una persona, entro il **2026-11-07**.

*Come è stata letta*: con uno strumento che scarica la pagina e ne riporta le frasi che gli si chiedono, non
con il testo intero davanti; le frasi fra virgolette sono quelle che lo strumento ha riportato. **Questo ADR
non esce da Proposta prima che la prova a mano sia passata e Tommaso abbia letto le pagine per intero.**
***Il 13 ottobre 2026 la prova è passata, e Tommaso le ha lette per intero*** — la review a `6d3c470` lo dice
così: «Tommaso ha letto per intero, il 13 ottobre 2026, le due pagine del fornitore che ADR 0063 §6 cita»
(decisione 160 di `docs/milestones/M13.9.md`) —: da quel giorno l'ADR è Accettata. *La tabella qui sopra nomina
più di due indirizzi: quali due la review intenda non è scritto, ed è la domanda 164 di quella SPEC. Quando la
condizione è nata — la domanda 75 della stessa SPEC, decisa (a) — gli articoli da leggere erano due: quello
della conservazione, e quello dei modelli «covered» a cui rimanda; le due righe sull'addestramento sono entrate
nella tabella dopo, con la stessa decisione.* ***Decisa la stessa notte, dalla review a `c4ed681`*** (decisione
164): **le due pagine sono i due articoli sulla conservazione** — `privacy.claude.com/en/articles/7996866`,
«How long do you store my organization's data?», e `privacy.claude.com/en/articles/15425996`, «Data retention
practices for Covered Models» —, **letti per intero da Tommaso il 13 ottobre 2026**. Lo stesso giorno ha letto
per intero anche l'articolo sull'uso per l'addestramento, `privacy.claude.com/en/articles/7996868`, «Is my data
used for model training?», da cui questa sezione prende la frase. **I termini del contratto**
(`anthropic.com/legal/commercial-terms`, sezione B) **restano citati, e non letti per intero.** La
domanda e l'anteprima di una policy lo dicono nel campo `sends`, che dice che cosa esce e verso chi, non per
quanto resta. Le istruzioni al modello guadagnano
una riga: non aprire un indirizzo che conferma, cancella, disiscrive o esce se la frase non lo chiede. **Dentro
quel sito un modello può aprire qualunque indirizzo come Tommaso**, e la descrizione della capability lo dice.

**Una policy della sessione non ha un numero massimo di sessioni**, e regge perché l'avvio è di Tommaso. *Si
riesamina il giorno in cui ELA parte da sola (annotazione per la Fase 15).* Una revoca non ferma una sessione
già partita: le sue letture come Tommaso continuano fino ai suoi tetti, e l'uscita della revoca lo dice.

### 7. Mentre Tommaso entra a mano, ELA non comincia a guardare né ad ascoltare

ELA apre una finestra perché Tommaso entri in un sito con le sue mani, e di quella finestra non legge niente
attraverso il browser: nessun driver, nessuna pipe, nessuna porta (§8). **Quella garanzia è del browser, e
finisce lì.** Lo schermo e il microfono sono un'altra strada verso ciò che viene scritto in quella finestra: una
fotografia, una lettura o una registrazione fatte nel frattempo porterebbero la password.

***Dal 13 ottobre 2026 (decisione 143): per il login vale questa stessa regola, non una nuova.*** *Uno step di
ELA che tiene il profilo — con la finestra o senza — non è «una mano»: i tool qui sotto non si rifiutano. Con la
decisione 143 lo step che ha sempre la finestra è il login, e in quei secondi sullo schermo c'è il modulo con il
nome utente in chiaro e la password come puntini: una cattura chiesta da un altro task lo fotografa.*
***Deciso il 13 ottobre (decisione 148): resta com'è.*** *Una cattura dello schermo chiede il suo sì.*

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

**Ciò che è cominciato prima non è fermato** (decisione 77, review dell'11 ottobre: dichiarato). Il rifiuto
guarda il profilo quando una cattura o un ascolto comincia: un ascolto già in corso quando la finestra si apre
arriva in fondo, e scrive ciò che ha sentito. *La frase della decisione 41 — «non guarda e non ascolta» — è
corretta apertamente, l'11 ottobre 2026: con la finestra aperta ELA **non comincia** a guardare né ad
ascoltare.* Il titolo di questa sezione, la guida, l'aiuto di `ela browser` e la didascalia della vista dicono
così. **I rifiuti dei tool non sono cambiati**: dicono, a chi ha chiesto adesso una cattura o un ascolto, che
ELA intanto non fotografa, non legge lo schermo, non ascolta — della richiesta che rifiutano, che non parte.

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
ELA non comincia a leggere il contenuto dello schermo né ad ascoltare; sa che la finestra c'è* (la frase della
decisione 49, con la correzione della 77).

### 8. La finestra, e le rotte del browser

**Con una finestra o senza è di Tommaso** (decisioni 18a e 34). Non è un argomento di nessuna capability e
nessun tool lo decide: è uno stato di ELA accesa, che cambia solo da una rotta di Tommaso, vale per gli step
con il profilo che partono da quel momento, e **torna «senza finestra» a ogni avvio**. Il browser vuoto resta
senza finestra.

***Rivista apertamente il 13 ottobre 2026 (decisione 143).*** *«Nessun tool lo decide» ha un'eccezione, ed è
scritta: **`browser.login` parte con la finestra qualunque cosa dica l'interruttore** (§5). Non è un argomento
della capability e un piano non lo sceglie: è com'è fatto il tool. L'interruttore resta di Tommaso, e resta ciò
che decide per ogni altro step con il profilo. **`ela browser status` lo dice**, in una riga sua accanto a
quella dell'interruttore: un login parte con la finestra, e — quando è così — che adesso ELA non ha potuto dire
di poterne aprire una, o che non ha potuto chiederlo; `GET /browser` porta lo stesso fatto in `login_window`.*

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

**Il comando che la finisce** (decisione 80, review dell'11 ottobre). Con il pulsante rosso la finestra si
chiude e il processo resta: lo stato dice ancora `window`, ogni step con il profilo è rifiutato e la percezione
pure. `ela browser close` — con la sua rotta e il suo pulsante nella vista — **avvisa** il browser su cui può
esserci una mano, **lo aspetta, e solo allo scadere della grazia lo uccide**: la stessa grazia della chiusura di
ELA, consegnata all'adapter come attesa. Vale per la finestra che questa ELA ha avviato, uccisa con il suo
gruppo, che è di ELA; e per **un processo che ELA non ha avviato solo se la sua riga di comando è il binario del
lock sulla cartella del profilo** — una finestra che si è rilanciata da sé, quella lasciata da un'ELA uccisa. È
il controllo che dice anche se la cartella è tenuta: **una funzione sola**, `on_the_folder`, per le due domande
(sotto) — **con due risposte** (decisione 89): chi nomina la cartella la tiene, ed ELA non ci lancia sopra; solo
il binario del lock sulla cartella riceve un segnale. Un processo che ELA non ha avviato è ucciso **per pid, mai per gruppo**, e solo se il sistema,
richiesto di nuovo allo scadere **di quel processo — non di ciò che il lock nomina in quel momento** —, dice
che è ancora quel browser. **Che cosa il comando non fa**: non finisce uno
step di ELA — quello finisce con il suo task —, e non segnala niente che non sia il browser di ELA: una riga di
comando che non si è potuta leggere è un dubbio, e il dubbio non riceve segnali. **Alla sua chiusura ELA avvisa
solo ciò che ha avviato**: la (c) della domanda 80 non è presa; una fermata di ELA arrivata mentre il comando
chiedeva al sistema che cosa fosse quel processo non manda nessun segnale, e una arrivata durante la grazia la
finisce senza uccidere.

**Un browser è avvisato una volta sola, chiunque lo chieda** (rilettura critica del giro; *misurato l'11
ottobre*, su un lancio senza finestra): un secondo `SIGTERM` arrivato venti millisecondi dopo il primo **uccide
il browser** — esce con il segnale, dove con uno solo esce da sé —: ha una sola occasione di chiudersi scrivendo
i suoi cookie. Due click sul pulsante, il comando due volte, o il comando e poi la fermata di ELA sarebbero
stati un'uccisione prima della grazia, detta «uscito». L'adapter ricorda chi ha avvisato finché non lo vede
finito; chi chiede di nuovo aspetta con il primo, e riceve la stessa risposta.

**Tre esiti, e un quarto che non è un esito.** `quit`: avvisato, è uscito. `killed`: non è uscito, ed è stato
ucciso allo scadere. **`told`: è stato avvisato, ed ELA non sa dire che sia uscito** — allo scadere il sistema
non ha saputo dire che cosa fosse quel processo, o ELA si stava fermando —: non è stato ucciso, perché ELA non
uccide ciò che non sa nominare, **e non è detto uscito**; il profilo può essere ancora tenuto, e la riga di
comando dice di guardare lo stato. `nothing`: nessun browser teneva il profilo, e nessuno è stato avvisato.

**Un processo alla volta sul profilo** (decisione 18c). Chi tiene la cartella è derivato a ogni domanda, mai
ricordato: uno step di ELA, la finestra, o un processo che il lock della cartella nomina. La finestra che
trova la cartella tenuta non si apre: ELA non lancia un secondo processo su una cartella che ha trovato
occupata, perché è il lancio che può uccidere il primo.

**Un binario che esce subito** (decisione 83: dichiarato). `window` torna appena il processo è avviato: se
esce subito — bloccato dal sistema, caduto all'avvio — la rotta ha già scritto l'apertura e la riga di comando
ha già detto che la finestra è aperta. La riga della chiusura, scritta subito dopo da chi aspetta il processo,
è vera, e la traccia dice una finestra durata zero secondi. Aspettare prima di dirla aperta vorrebbe una soglia
di tempo che questa macchina non sa fissare con un fatto.

**Quando una chiusura della finestra torna, nessun processo di quel browser nomina più la cartella**
(decisione 153 della review del 13 ottobre 2026; *rivede apertamente la decisione 82*, qui sotto: il sistema
non è più chiesto solo quando un lock nomina un processo). **Il fatto**: sulla CI di macOS, a `77b4bfe` e a
`eba94c8`, due test di questa sezione hanno trovato — alla fermata di ELA e al comando — il processo principale
della finestra uscito da sé, la chiusura tornata, e nella tabella ancora uno o due processi che il browser aveva
avviato per sé. *Due giri rossi su tre, sullo stesso codice; sul Mac, in trentasei giri della stessa chiusura a
macchina quieta e carica, non è successo* (`what-names-the-folder-when-the-close-returns-before.txt`, in
`.git/m13.9-reference/review-c1d0ef8/`). *Annotato il 2026-10-13, la sera: dei trentasei, trenta sono di una
pagina guidata che si chiude da sé e sei della finestra alla fermata di ELA; la chiusura dal comando la sonda
non la fa.* La chiusura aspettava il processo principale, e non ciò che quello
aveva avviato. **Ora**, uscito il principale, la chiusura — `settle` alla fermata, `shut` al comando — chiede al
sistema i processi di questo utente con il gruppo e la riga di comando di ciascuno (`/bin/ps`, con le regole
dell'altro lancio), e va avanti **entro la stessa grazia, con il passo che c'è già, senza un tempo nuovo**
finché nessuno, **nel gruppo di quel browser**, nomina la cartella: letto con **la stessa funzione**,
`on_the_folder`. Passata la grazia vale la regola che c'era:

- *la finestra che ELA ha avviato*: il suo gruppo è di ELA, ed ELA lo uccide, e lo dice — `killed` dal comando,
  il nome della finestra fra ciò che la chiusura di ELA ha ucciso;
- *un browser che ELA non ha avviato*: ELA uccide per pid solo ciò che il sistema dice ancora essere quel
  browser; **ciò che quello aveva avviato non lo sa nominare, non lo uccide, e risponde `told`, non `quit`**;
- *una lettura dei processi che non riesce* è un dubbio, mai «nessuno»: la chiusura aspetta la sua grazia, ed
  ELA non dice la cartella libera.

Una finestra che il suo utente ha chiuso da sé, senza che ELA l'avvisasse, non è di nessuna chiusura: ELA non
la cerca dopo. ***Dove si scosta dalla lettera della decisione, e perché*** (misurato scrivendola): «nessun
processo nomina più la cartella» è letto **dei processi del gruppo di quel browser**, non di ogni processo
dell'utente. `on_the_folder` conta un dubbio — una riga di comando che nomina una cartella da dove sta il suo
processo — come un processo che la nomina: è giusto del solo processo che un lock nomina, e su una tabella
intera ha fatto aspettare ogni chiusura a una shell la cui riga di comando conteneva il testo di quell'argomento:
**ventiquattro test rossi in un giro**, ognuno una chiusura che aspettava la sua grazia per un processo che non
era di nessun browser. Era la domanda 158 di `docs/milestones/M13.9.md`, **decisa (a) il 13 ottobre 2026** dalla
review a `6d3c470`: **la promessa è dei processi di quel browser, e il predicato resta uno**. *Un browser guidato
che si chiude da sé*: misurato sul Mac,
in trenta giri nessun processo nominava la cartella quando la chiusura della pagina è tornata; sulla CI non è
misurato, e la chiusura di una pagina resta com'è.

**Un lock tiene la cartella solo se la riga di comando del suo processo la nomina** (decisione 82, review
dell'11 ottobre). Un browser ucciso lascia il lock, e il sistema dà quel pid a chi parte dopo: un processo che
dura avrebbe tenuto la cartella finché qualcuno non toglieva il link a mano. Quando il lock nomina un pid che
il kernel conosce — **e solo allora: un lancio in più, mai a ogni cattura** — l'adapter chiede al sistema la
riga di comando di quel processo (`/bin/ps`, al suo percorso assoluto, con l'ambiente chiuso del browser), e
`on_the_folder` la legge:

| Che cosa dice la riga di comando | La cartella | `ela browser close` |
|---|---|---|
| non nomina nessuna cartella, o ne nomina un'altra con un percorso che parte dalla radice; o il processo non c'è più | **libera**: il lock è un resto | niente da chiudere |
| è il binario del lock, su questa cartella, non un suo aiutante, **senza niente attaccato**, e il nome della cartella finisce in modo chiaro | tenuta | lo avvisa |
| nomina la cartella ed è un altro programma; o è il binario del lock **con un driver o una porta attaccati** — un passo di qualcuno, un'altra ELA sulla stessa cartella | tenuta | rifiuta: non è il browser su cui può esserci una mano |
| nomina una cartella **da dove quel processo sta** — un percorso che non parte dalla radice | **tenuta: il dubbio rifiuta** | rifiuta |
| non si è potuta leggere; o il sistema non dice niente di un processo che il kernel conosce ancora | **tenuta: il dubbio rifiuta** | rifiuta |

**La cartella è riconosciuta come posto, comunque sia scritta** (rilettura critica del giro): con lo slash che
una shell lascia in fondo, attraverso un link sopra di lei, con altre maiuscole su un volume che le ignora —
chiesto al sistema quando le due ci sono, confrontato sui percorsi resi piani quando no. Letta come solo testo,
un browser lanciato a mano con un'altra grafia non la teneva. *Il limite, e da che parte cade*: il sistema
stampa gli argomenti uniti da spazi, e dove finisce il nome della cartella si prova a ogni spazio. **Finisce in
modo chiaro quando lo segue uno switch, o niente: solo allora quel processo riceve un segnale**; in ogni altro
caso tiene la cartella e non è avvisato. Il programma del sistema finisce allo stesso modo per un processo che
non c'è e per ogni suo errore (misurato): «niente» è creduto solo di un processo che il kernel non conosce più.
Ciò che l'adapter stesso ha in volo viene prima del lock, ed è **riguardato dopo la risposta del sistema**: fra
quello sguardo e chi agisce non c'è nessuna attesa.

Rotte nuove, in `ela/api/browser.py`, che raggiunge `CORE` con il token:

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/browser` | che cosa è il profilo, guardato attraverso il suo port: usabile o no e perché, libero o tenuto e da chi, con o senza finestra, collegato o no a un account |
| `POST` | `/browser/window` | con la finestra, o senza: l'interruttore di Tommaso |
| `POST` | `/browser/open` | la finestra del login a mano, su un sito dichiarato o su nessuno |
| `POST` | `/browser/close` | il browser su cui può esserci una mano, fatto uscire: avvisato, aspettato, ucciso solo allo scadere della grazia |

**Lo stato è il rifiuto dei tool, o chi tiene la cartella.** `GET /browser` risponde `free`; oppure il nome di
chi tiene il profilo, come lo dice il port — `step`, `window`, `process` —; oppure perché nessun browser può
partirci, con il codice che uno
step riceverebbe prima della sua domanda, senza il prefisso — una definizione sola, in `ela/tools/account.py`,
per i tool e per le rotte. `linked` e `saved` sono ciò che il browser dice di sé — se conosce un account di chi
l'ha fatto, quante password tiene il suo gestore —, **riletti a ogni richiesta, mai da una copia** (decisione
63), e «non letto» dove la cartella non si è potuta leggere: non «no», e non «nessuna». **`saved` conta in
ogni profilo del browser che la cartella contiene, e `profiles` dice quanti sono** (decisione 79): ELA ne
prepara e ne usa uno, `Default`, che ogni lancio nomina (§4); un secondo è uno che Tommaso ha aggiunto da
dentro la finestra, e le superfici lo dicono quando c'è. **I profili sono quelli che il browser stesso elenca**
— i nomi sotto `profile.info_cache` del suo `Local State`, letti come presenza, mai come il nome di un profilo
o di chi è —: non ogni cartella con un `Preferences`, perché il browser tiene accanto ai profili cartelle sue
che non lo sono. Le password si contano in ogni cartella della cartella che ha il suo file. **Ciò a cui porta un
link non è letto, e non è detto «nessuna»**: un profilo che è un link, o un file delle password che lo è, il
browser li seguirebbe — per ELA è ciò che non si è potuto contare, e le superfici dicono «non letto».

**Una rotta non apre la cartella e non ne riceve il percorso** (decisione 35): chiede al port, che risponde
con fatti. Lo tiene la regola 69.

Errori aggiunti, nella forma della tabella di ADR 0023 §10:

| Caso | Eccezione | Stato |
|---|---|---|
| la finestra non si apre: un sito non dichiarato, un profilo su cui nessun browser può partire, o tenuto; o il browser non si chiude: un profilo di cui ELA non sa dire niente, uno step che lo tiene, un processo che non è il browser di ELA, ELA che si ferma, o un errore del browser | `BrowserRefusedError` | `409` |

Codici aggiunti a `ela.ports.WireCode`:

| Codice | Membro | Quando |
|---|---|---|
| `browser.refused` | `BROWSER_REFUSED` | la finestra del login a mano non si è aperta, o il browser non si è chiuso: il messaggio comincia con il codice dei tool |

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
| `ela browser close` | `POST /browser/close` | `0` `1` `2` `3` |

`ela browser open` prende un sito, o niente. `ela browser close` non prende niente, e dice che cosa è stato del
browser: è uscito quando avvisato; è stato ucciso; è stato avvisato ed ELA non sa dire che sia uscito; o non
c'era niente da chiudere — che non è un errore.

**L'audit**: tipi d'evento nuovi, senza contenuto. `BROWSER_WINDOW_OPENED` lo scrive la rotta che apre la
finestra, firmato da chi l'ha chiesta, con il sito se c'era. `BROWSER_WINDOW_CLOSED` lo scrive **chi aspetta la
fine del processo**, che è chi vede ogni fine di una finestra che questa ELA ha aperto — Tommaso che esce dal
browser, ELA che si ferma —, firmato da ELA: nessuna rotta la chiede, e una fine che nessuno ha chiesto
resterebbe senza riga. Porta il sito, se c'era — l'host, senza nome né porta —, e quanti secondi interi la
finestra è rimasta aperta: mai un indirizzo, e niente di ciò che vi è stato fatto — ELA non lo sa. *Restano
senza riga* la finestra di un'ELA uccisa, che nessuno aspetta più, e una fine la cui riga non si scrive: questa
è detta nel log, con il tipo dell'errore, e non ferma la chiusura di ELA. L'interruttore della finestra non è
un evento: non apre niente. `BROWSER_CLOSE_ASKED` lo scrive la rotta del comando che chiude, firmato da chi
l'ha chiesto, **quando un processo è stato avvisato**, con che cosa ne è stato — uscito, ucciso, o solo
avvisato — e **con chi teneva il profilo quando il comando ha guardato**: la finestra di ELA, o un processo che
ELA non aveva avviato. Per la finestra che ELA ha avviato la fine è una riga in più, di chi la aspetta, **e
viene prima di questa**: la riga del comando è scritta quando il browser è stato avvisato e aspettato, perché
porta l'esito. Per un processo che ELA non ha avviato è la sola riga che c'è. *Un segnale non si ritira*: se la
riga non si scrive, l'errore dell'audit è la risposta a chi ha chiesto, e il segnale è partito.

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
sito dichiarato o su nessuno, quel browser che si fa uscire, e il vault che si chiude. **Non lo apre**: una
chiave non si incolla in una pagina, e nessun campo della vista potrebbe portarne una. Il telefono non ha
questa vista.

***Dal 13 ottobre 2026 (decisione 150).*** *La vista diceva «senza finestra» mentre un login ne avrebbe avuta
una: accanto alla riga dell'interruttore ne ha una del login — «Un login» —, con lo stesso fatto che
`GET /browser` porta in `login_window`: con finestra, qualunque cosa dica l'interruttore; che ELA adesso non ha
potuto dire di poterne aprire una; o che non ha potuto chiederlo. La riga non si muove con l'interruttore.*

Rotte nuove, in `ela/api/console.py`, che raggiunge il cookie di una console:

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/console/browser` | il profilo e il vault, e i moduli di ciò che questa console può fare |
| `POST` | `/console/browser/window` | l'interruttore della finestra, dal Mac |
| `POST` | `/console/browser/open` | la finestra del login a mano, dal Mac |
| `POST` | `/console/browser/close` | il browser su cui può esserci una mano, fatto uscire, dal Mac |
| `POST` | `/console/browser/lock` | il vault chiuso, da qualunque console |

**Ciò che cambia qualcosa sullo schermo del Mac si fa dal Mac.** L'interruttore, la finestra del login e il
pulsante che la fa uscire — offerto quando lo stato è `window` o `process`, accanto alla frase che spiega il
pulsante rosso — li usa
una console il cui tetto è `LOCAL_ONLY` — i due capi del socket in loopback, come lo decide il middleware —;
da fuori la vista dice gli stati e fa una cosa sola, quella che toglie: chiude il vault, come la revoca di una
policy. Da fuori non si leggono nemmeno i siti dichiarati, né le frasi dei tool e del vault, che possono
nominare una cartella o un programma del Mac.

**La pagina non raggiunge niente attraverso ELA** (regola 55): chiama le funzioni delle rotte — quelle di
`ela/api/browser.py`, e quelle che `ela/api/vault.py` espone per lei, `vault_of` e `vault_locked`.

**Ogni modulo nomina ciò che chiede.** Un `POST` senza il suo campo — `shown`, `site`, `browser`, `vault` — non è una
richiesta da indovinare: `422`, e niente cambia. Il sito vuoto è «nessun sito», ed è una risposta.

Errori aggiunti, nella forma della tabella di ADR 0023 §10:

| Caso | Eccezione | Stato |
|---|---|---|
| la finestra, il suo interruttore o la sua chiusura chiesti da una console che non è al Mac | `BrowserOutOfReachError` | `409` |

### 11. Che cosa vede un sito, e ciò che il cancello non ferma — misurato il 2026-10-12

Il cancello è quello di ADR 0052 §6, e il browser del profilo lo eredita. **Misurato dopo la prova del 12
ottobre**, con server su questa macchina e nessuna richiesta di ELA a un sito vero; le sonde, i test rossi
parcheggiati e le loro uscite sono in `.git/m13.9-reference/review-d1bce52/`, e `docs/milestones/M13.9.md`,
sezione 21, li racconta uno per uno.

- **Il primo documento di ogni navigazione lo manda il processo del driver, non il browser** — un indirizzo
  aperto, un link, il `POST` di un modulo. Porta il nome del browser, e **non è il browser**: le intestazioni
  hanno un altro ordine e nomi minuscoli, mancano `Sec-Fetch-*` e `Accept-Language`, e su TLS il suo primo
  messaggio è di un altro client — senza ALPN, con altri cifrari. ADR 0052 §6 diceva già che «la route è il
  driver»; non diceva che cosa ne vede un sito.
- **Senza finestra il browser si chiama `HeadlessChrome`**, con il cancello e senza, e una pagina legge che è
  guidato: non è del cancello, e ELA non lo cambia (decisione 19). Con la finestra — l'interruttore
  dell'utente — si chiama `Chrome`.
- **Un sito può rispondere a un login in modo diverso** per l'una o per l'altra cosa: sono le cause candidate
  del login non riuscito della prova, **e nessuna è un fatto**, perché nessun sito vero è stato interrogato.
  **Nessun travestimento si aggiunge**, né si aggiungerà: non si imita ciò che non si è.
- **Il documento dopo un rimando lo manda il browser, e il cancello non è chiamato.** La forma di un login vero
  — un `POST`, un rimando con il cookie dell'accesso, la pagina dopo, un secondo lancio — **passa lo stesso**, e
  un test del browser vero la tiene, senza finestra e con.
- **Ma il cancello guarda così una sola risposta per navigazione**: in una catena, **un secondo rimando che esce
  dal confine è seguito**. Misurato: la richiesta arriva all'altro sito, con ciò che il suo indirizzo porta e
  **con il cookie che il profilo tiene per lui**; **una lettura porta nel risultato il testo di quella
  pagina**, e un gesto **scrive su di lei** ciò che il piano dice — perché uno step risponde
  `browser.left_site` quando il cancello ha rifiutato una navigazione, e nessun tool confronta dove la pagina
  è. Fa eccezione `browser.login`, quando apre la pagina e, da questa milestone, dopo il click. È di M13.4 —
  il cancello, e i tool `browser.read` e `browser.act` da cui quelli del profilo ereditano —, vale per tutti e
  due i browser, e **non è riparato qui**.
- **I cookie di un documento li scelgono due programmi**: su un modulo inviato da un altro sito, dove
  `SameSite` dice di no e il browser non ne manda nessuno, attraverso il cancello arrivano.

***Rivista da ADR 0064 (M13.4f), il 2026-10-12.*** *Ciò che questa sezione misura è il cancello di allora, ed è
riparato: le richieste sono del browser, il confine regge a ogni salto, e ogni tool trova la pagina dove è.
**La strada qui sotto è presa**, in un'altra forma — la sessione è del browser e non della pagina, e il confronto
sta nell'adapter e non nei tool (ADR 0064 §2 e §4).*

**La strada misurata, e non presa in questa milestone**: che ogni tool confronti dove la pagina è con il suo
confine; e lasciare al browser le sue richieste, guardandole prima che partano — ogni richiesta di documento, i
salti di un rimando compresi — con il protocollo di debug del browser. Una sonda, sul browser del profilo, dice
che il confine regge anche al secondo rimando — l'altro sito non riceve una richiesta né una connessione —, che
il sito riceve ciò che riceve dal browser da solo, e che i cookie tornano a essere del browser. È una
riparazione di M13.4, con la sua lettera e il suo ADR: la proposta è la domanda 109 di `M13.9.md`, e la 110 dice
del secondo rimando.

### 12. Un debito datato: il costo dei test di M13.9, sopra la soglia di ADR 0052 §16

**Debito a carico di M9.5, la milestone sulla disciplina della suite**, dichiarato il **2026-10-13**, dalla
review del giro conforme del costo (decisione 165 di `docs/milestones/M13.9.md`).

**Il fatto**, misurato nel giro conforme del 13 ottobre 2026 — un `make check` nelle condizioni di ADR 0052 §16,
348,42 s d'orologio (`docs/milestones/M13.9.md`, sezione 25, punto 2) —: **M13.9 da sola allunga il giro del
12,65 %** — i soli suoi test, 39,11 s, contro un `make check` senza di lei —, **e del 16,19 % con ciò che non è
diviso per milestone** — le parti di `make check` che non sono la suite, e la costruzione del Core più lenta —,
**contro una soglia del 10 %**. Perché torni sotto, a quel giro vanno tolti **8,18 s**. **Le due voci più
grandi**: i test del browser vero con il profilo (`test_account_browser.py` e `test_account_login.py`), 9,65 s
di quel giro; e i casi che le regole d'architettura di questa milestone aggiungono ai test vecchi, in
`tests/architecture/`, 6,52 s.

**Non si ripara qui**: il merge si fa (decisione 165, (c)). **La soglia di ADR 0052 §16 resta com'è**: se una
regola diversa per le milestone che portano un binario vero ha senso, la propone M9.5, con i suoi numeri, non
questa. **Che cosa lo pagherebbe senza togliere una difesa**: raggruppare i lanci del browser vero, dove un
lancio può servire più di un test senza che uno dipenda dall'altro; e misurare per milestone ciò che oggi non è
diviso — è ciò che porta il numero dal 12,65 % al 16,19 %.

*Un fatto accanto, che non è un debito*: M13.4f, sullo stesso branch, sta sotto la soglia con i suoi test, di
2,55 s (ADR 0064; la stessa sezione di quella SPEC).

**La difesa più piccola**:
`tests/docs/test_adr_accounts.py::test_the_debt_of_the_cost_is_dated_charged_and_named_by_who_pays_it` tiene
questa sezione nella forma che `docs/STATO.md` legge, con i suoi numeri, e tiene che il documento di M9.5 la
nomini fra ciò che eredita. Il giorno in cui è pagato, il pagamento si scrive in un ADR, e il test si gira.

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
- **ADR 0052** §6 — **corretta, non rivista**: la pagina non ripassa dalla route per seguire un rimando ammesso,
  e il confine non regge al secondo rimando di una catena; che cosa un sito vede del documento che il driver
  scarica (§11). Una misura del 12 ottobre, non una decisione: la riparazione è di M13.4 — fatta, in M13.4f (ADR 0064).
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
  *Dal 13 ottobre 2026*: per lo stesso tempo un segnale sveglia il loop **qualunque thread lo riceva** — consegnato
  a un altro thread durante la chiusura, un secondo segnale non era sentito (misurato; «La terza parte»).
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
  l'alternativa scartata, che torna come una copertura che non è un grant (§1, §6). **La quarta risposta di §8,
  la policy del fornitore, si legge con la tabella di §6 accanto**: la frase sull'addestramento ha oggi un'altra
  pagina, e l'articolo della conservazione dice cose che lì non c'erano.
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
**quindici**, i port diventano **trentacinque** (`Vault` e `AccountBrowser`), le rotte dell'API **settantadue** e i comandi
della CLI **trentanove** (quelle del vault e del browser con i loro comandi, e quelle della vista della console); le
capability diventano **diciotto** (quelle di §5), le identità del middleware restano **sei**. *(I totali si aggiornano con le sezioni
che seguono: questo ADR si scrive con l'implementazione.)*
