# 0064. Il confine del browser: guardare, non rifare

- **Stato:** Accettata il **2026-10-13**, con un commit suo, come ADR 0063: la prova a mano di M13.9 — la
  sezione 28 di `docs/GETTING_STARTED.md` — è passata per intero sul Mac a `6d3c470`, l'ultimo commit del branch,
  che porta questa riparazione (`~/Downloads/prova-m13.9-20261013-181603.txt`: 52 PASSATO, tutti al primo giro,
  0 FALLITI, nessun no — decisione 130 di `docs/milestones/M13.4f.md`, decisioni 159 e 160 di
  `docs/milestones/M13.9.md`). Proposta il **2026-10-12**, con l'implementazione di M13.4f, per diventare
  Accettata quando quella prova fosse passata su un commit con questa riparazione. *`6d3c470` era l'ultimo commit
  del branch quando la prova è girata: i commit venuti dopo, questo compreso, portano solo documenti e i test dei
  documenti.*
  **Rivista da ADR 0065 (M13.10)** il 2026-10-14: §1, il confine di una pagina che continua è quello dello step che continua, non più solo quello consegnato all'apertura (ADR 0065 §3).
- **Data:** 2026-10-12
- **Riferimenti spec:** §19, §33, §57
- **Milestone:** M13.4f

## Contesto

Il cancello del browser di M13.4 (ADR 0052 §6) era una route di Playwright: per ogni navigazione della cornice
principale scaricava lui il documento, dal processo del driver, e lo consegnava alla pagina. La prova a mano di
M13.9 del 12 ottobre 2026 è fallita sul login dal vault, e le misure fatte dopo, con server su questa macchina,
hanno trovato che quel modo di fare il cancello **non tiene il confine e toglie al browser ciò che è suo**. Le
decisioni — dalla 109 alla 138 —, le regole scritte prima dei numeri e le misure stanno in
`docs/milestones/M13.4f.md`; le sonde e le loro uscite in `.git/m13.4f-reference/`.

**Il perché non è il login della prova** (decisione 109): è ciò che segue, e M13.9 — la milestone che mette le
sessioni vere nel profilo — non entra in `main` con quel cancello.

## Decisione

### 1. I fatti misurati, e che cosa il confine è

1. **Il confine non fermava la richiesta del secondo salto.** Playwright non chiama una route per una richiesta
   nata da un rimando: in una catena — dentro, dentro, fuori — la richiesta arrivava al sito di fuori, con ciò
   che il suo indirizzo porta; con il profilo, con i cookie dell'utente. E nessun tool, salvo `browser.login`,
   guardava dove la pagina era: una lettura portava nel risultato il testo di quella pagina, e un gesto
   scriveva su di lei.
2. **I cookie di un documento li sceglieva anche il driver.** Su un modulo inviato da un altro sito, dove il
   browser non manda nessun cookie, attraverso il cancello arrivavano: ELA toglieva al browser una sua difesa.
3. **Il sito vedeva un client che porta il nome del browser senza esserlo**: altre intestazioni e, su TLS, il
   primo messaggio di un altro programma.
4. **Con una route il driver risponde da sé alla domanda che il browser fa a un altro sito prima di certe
   richieste**, e dice di sì: quel sito riceveva ciò che avrebbe rifiutato (misura 7). È la ragione per cui
   nemmeno una route «solo per le altre pagine» è rimasta.

**Che cosa il confine è, e che cosa non è.** Il confine è la funzione che il tool costruisce e consegna a
`open`: quali siti. **Impedisce a ELA di andare, leggere e scrivere fuori**: una richiesta di documento della
cornice principale fuori dal confine non parte, e su una pagina che non è dentro ELA non legge, non scrive e non
guarda. **Non impedisce a una pagina di caricare da altri siti**: un'immagine, uno script, una cornice interna
vengono da dove la pagina vuole, com'è da M13.4 (ADR 0052 §6).

### 2. Il cancello: una sessione del browser, che guarda

`ela/infrastructure/machine/browser.py`, `_Gate`. Accanto alla sessione di Playwright ce n'è una del protocollo
del browser, **attaccata al browser e non a una pagina**, che chiede di essere avvisata di **ogni richiesta di
ogni pagina prima che parta** e di ogni cosa che il browser apre. A ciascuna richiesta risponde: lasciata andare
**com'è**, o fatta fallire. **Non ne fa nessuna, e non ne cambia nessuna.**

| La richiesta | Che cosa ne è |
|---|---|
| Un documento della cornice principale della pagina su cui ELA lavora — il primo indirizzo o il salto di un rimando, con qualunque metodo; un link che scarica; avanti e indietro nella storia | lo giudica il confine: fuori **fallisce** e l'adapter ne tiene l'indirizzo (`Opened.left`, `left`); dentro **parte** |
| Ogni altra richiesta di quella pagina: ciò che carica, i documenti delle sue cornici, ciò che chiede un suo worker dedicato | parte |
| Una richiesta la cui cornice non è di quella pagina: un'altra pagina, una sua cornice, un worker condiviso, un service worker | **fallisce**, qualunque sia |
| Qualunque richiesta, da quando la fermata di ELA è alzata | fallisce: la fermata è guardata per ultima, subito prima di lasciar andare |
| Una richiesta su cui chi giudica solleva | fallisce, e l'uso successivo della pagina dice `browser.failed` |

**Di chi è una richiesta.** La sessione è avvisata di una richiesta con la sua cornice, e niente della pagina.
Una cornice è della pagina se sta nell'albero che la sessione della pagina conosce, o nell'albero della sessione
di una cornice che ne ha una sua: nel browser del profilo le cornici dentro una cornice di un altro sito stanno
solo lì (misura 12). **Una cornice che non si trova è rifiutata.** E ciò che il browser ha **annunciato** come
un'altra cosa — una pagina, un worker — è rifiutato **senza chiedere niente alla pagina**: l'annuncio arriva
prima della prima richiesta di quella cosa (`told-of-a-page-opened.txt` per una pagina, in ogni giro;
`workers-and-targets.txt` per un worker, in ciò che è stato guardato), e la pagina non sempre può rispondere
(§6). *Se un annuncio arrivasse dopo, la richiesta sarebbe rifiutata lo stesso, chiedendo alla pagina.*

**Ciò che il cancello non fa mai**: spegnere l'avviso — ciò che era in pausa partirebbe (misura 6) — e staccare
la sessione. Se il driver muore il browser muore con lui, e ciò che era in pausa non è mai partito. Nel modulo
dell'adapter non resta nessuna route, e lo tiene la regola d'architettura 70.

**Le risposte del cancello sono attività sue**, una per richiesta, tenute finché finiscono. *La chiusura di ELA
non le aspetta*: chiude il browser, e una richiesta a cui il cancello non aveva ancora risposto non è mai
partita.

**I certificati li giudica il browser**: nessun documento è più scaricato dal driver, e le variabili con cui
l'ambiente di ELA faceva accettare un certificato al driver (ADR 0052 §14) non cambiano più che cosa una pagina
apre. Che il Core le tolga dal suo ambiente resta: il driver gira ancora.

### 3. La prova prima della prima navigazione

Prima di chiedere l'indirizzo del sito, ogni pagina chiede `http://127.0.0.1:9/ela-gate-check`: un indirizzo che
**il browser stesso rifiuta di aprire**, così che con l'avviso spento non possa arrivare una richiesta a nessuno,
nemmeno su questa macchina. Con l'avviso acceso il cancello ne è avvisato, e la fa fallire lui. **Se non ne è
avvisato, `open` chiude ciò che ha avviato e solleva**: l'indirizzo del sito non è mai chiesto. Fra la prova e la
navigazione vera non c'è nessun uso della pagina.

*Che cosa non copre*: è dell'istante in cui è fatta. Se l'avviso smettesse dopo, una richiesta non sarebbe
guardata; il predicato di §4 ferma ELA su una pagina finita altrove, non la richiesta. Un avviso acceso con
nessuno che ascolta lascia in pausa la richiesta della prova: la chiude il tempo del tool, e lo step fallisce
senza lasciare niente acceso.

### 4. Il predicato: chi tiene la pagina chiede al confine dove è

**Un predicato solo** — lo stesso confine con cui il cancello decide —, **e lo applica l'adapter**, a ogni uso
della pagina: contare un elemento, leggerne gli attributi, scrivere, cliccare, leggere il testo e il titolo, dire
che cosa il cancello ha rifiutato, scrivere un segreto, dire dove la pagina è finita, **e lo sguardo del
verifier**. **Prima dell'uso**, che allora non avviene; **e di nuovo dopo**, e allora ciò che è stato letto si
butta: una lettura fatta su una pagina che nel frattempo è finita fuori non entra in nessun risultato. *Chi
dice ciò che il cancello ha rifiutato (`left`) chiede prima e non dopo: della pagina non legge niente, e non
c'è niente da buttare.*

**E all'apertura, prima di dire qualunque cosa della pagina**: `open` chiede al confine dove la pagina è prima di
restituirla. Lo stato del suo documento e il suo indirizzo sono detti di una pagina dentro il confine, o non
sono detti: una pagina che ha risposto `404` altrove è `browser.left_site`, non `browser.http_status`.

Fuori dal confine l'uso solleva `LeftSite`, che porta l'indirizzo — mai nella sua frase — e se l'uso era già
stato fatto: **un gesto avvenuto è contato come avvenuto**. Così anche quando chi giudica ha sollevato sulla
richiesta di quel gesto: il cancello lo dice **prima** di un uso, mai dopo — il gesto torna come fatto, ed è
l'uso successivo a dire `browser.failed`. Il tool risponde `browser.left_site` con la sola
origine, e il verifier lo stesso codice. Vale per `browser.read`, `browser.act`, `browser.read_as_you`,
`browser.act_as_you`, `browser.login` — i cui due confronti erano questo —, e per ogni gesto di una sessione
guidata, che è una chiamata di quegli stessi tool. Ogni finto del port lo applica come l'adapter, e un test
dell'architettura trova quello che non lo fa.

**È un secondo sguardo, non il primo.** «Dove la pagina è» è l'indirizzo della cornice principale come l'adapter
lo conosce: può essere indietro di un istante sul browser, e fra il confronto e l'uso la pagina può muoversi. Chi
impedisce che una pagina fuori dal confine esista è il cancello; il predicato ferma ELA se il cancello ha
mancato. `browser.left_site` ha perciò due frasi, mai una per tutte e due: «la pagina ha provato ad andare
altrove, e non è partito niente», e «la pagina è altrove, ed ELA non ne ha letto niente».

**Una pagina che non è su nessun sito.** Una pagina può lasciare il suo sito **senza nessuna richiesta**: andando
su `about:blank`, o su un documento che il suo stesso script ha fatto (`blob:`). Il cancello non è avvisato di
niente — non c'è niente di cui avvisarlo —, ed è il predicato a trovarla: nessun confine ammette un indirizzo
che non è di un sito. Il gesto che l'ha mandata lì è contato come fatto, e di quella pagina ELA non legge niente
(`a-page-at-no-site.txt`, con il controllo del browser da solo; un test lo tiene sui browser veri). Il tool lo
dice con lo schema soltanto — `about://`, `blob://` —, che è ciò che resta dell'origine di un indirizzo senza
un sito.

### 5. Una pagina sola

ELA lavora su una pagina. **Di una pagina che non è quella non parte nessun documento**: né la sua navigazione,
né un link, né un modulo, né una cornice scritta lì; ed ELA non ne legge, non ne scrive e non ne guarda niente.
Nemmeno un indirizzo dentro il confine è chiesto da quella pagina.

**Su che cosa poggia** (decisione 126): l'avviso è sul browser, non su una pagina. Una pagina appena aperta non
ha niente da accendere e nessuno deve arrivare prima di lei; la sua prima richiesta resta in pausa finché non
risponde chi ha acceso l'avviso, e Playwright, senza una route, non ne accende uno suo (letto nel codice del suo
driver). Misurato con 250 giri per ciascun modo di aprire una pagina, e 50 con dieci finestre aperte da un click
solo, sui browser veri: il rifiuto in ogni giro, e nessuna richiesta arrivata (`hundreds-of-rounds.txt`).

**Ciò che la prima pagina fa caricare in una pagina vuota che ha aperto è una richiesta della prima pagina**
(decisioni 132 e 133). Un'immagine messa in una pagina vuota aperta dalla prima — o aperta con `javascript:`, o
aperta dentro il confine e poi riscritta — il browser la carica come della prima pagina: la sessione ne è
avvisata con la cornice della prima pagina, e arriva **con ogni intestazione che avrebbe dal suo documento —
nome, valore e ordine, cookie compresi —, niente di più**; una pagina aperta con `javascript:` non dice nemmeno
da dove viene, ed è il solo scarto (`own-and-written-every-header.txt`; il test lo afferma accanto al suo
controllo). Per la pagina vuota e scritta lo stesso è misurato, sui cookie, di uno script e di una `fetch`
(misura 14). È ciò che una pagina può già fare da sé. Una pagina aperta su un `blob:` è un documento suo: di lei
non parte nemmeno un'immagine (misura 15).

**Lo step lo dice sempre, e non fallisce per questo** (decisione 123): un sito che apre una finestra da sé
farebbe fallire una lettura riuscita. Il browser dice alla sessione che una pagina è stata aperta, e da chi,
prima di ciò che vi è scritto; l'adapter lo tiene (`another`), con la prima richiesta di quella pagina quando ne
fa una. Il risultato porta `another_page` — la sola origine, o che la pagina non aveva chiesto niente —, anche
quando lo step è fallito per altro; se il testo atteso non compare, il verifier risponde
`browser.another_page` al posto di `browser.expect_missing`, e per un modulo inviato in un'altra pagina la frase
dice che il modulo non è stato inviato. *Misurato prima: senza questo codice il verifier diceva «ciò che il
click ha inviato può essere arrivato lo stesso», e non era partito niente.*

**Ciò che il risultato dice è ciò che il browser aveva annunciato quando lo step è finito.** Quando è il click
dello step ad aprire la pagina, l'annuncio è arrivato prima che il click tornasse in ogni giro misurato, con un
link e con un modulo, sui browser veri (`a-click-that-opens-another-page.txt`): il risultato portava l'origine,
o — con il browser del profilo, in alcuni giri — che la pagina non aveva ancora chiesto niente. Niente lo
garantisce; il verifier guarda dopo, e ha risposto `browser.another_page` in ogni giro.

### 6. I service worker

**Di una navigazione a cui risponde un service worker la sessione non è avvisata**: il browser la manda al sito
accanto al suo worker (misura 13, e di nuovo con l'adapter). La pagina è quella del worker in ogni giro, anche
con un worker che prima aspetta una sua richiesta (`what-the-reread-asked.txt`), e il sito riceve la navigazione
lo stesso, senza che nessuno ne sia avvisato (`a-worker-in-charge-and-the-site.txt`; un test lo afferma). Perciò
**togliere i worker del profilo prima di ogni lancio che ELA guida, e bloccarli, resta necessario** (ADR 0063
§4). La difesa è nominata dove scatta:
`test_a_launch_ela_drives_finds_no_worker_in_the_profile_and_the_gate_sees_the_request`, in
`tests/infrastructure/machine/test_account_browser.py`.

Il cancello aggiunge, misurato: **un worker non si può registrare attraverso il cancello** — la
richiesta del suo script non ha una cornice della pagina —, e **ciò che un worker chiede da sé è rifiutato**.

*Un test si è fermato qui, e si sa dove* (decisione 128; `a-test-that-stopped.txt`): con un worker al comando
della navigazione il cancello chiedeva alla sessione della pagina le sue cornici, e la pagina non rispondeva
mentre aspettava il worker, che aspettava il cancello. Per questo un worker è rifiutato da ciò che il browser ha
annunciato di lui (§2), e non da una domanda alla pagina. Dopo la riparazione, otto giri su otto
(`a-test-that-stopped-after.txt`).

### 7. Che cosa un sito vede di diverso dal browser da solo

Scritto com'è, **e niente è aggiunto per nasconderlo** (decisione 118): nessuna intestazione aggiunta o
cambiata, nessuno script di ELA nella pagina.

- **Senza finestra il browser si chiama `HeadlessChrome`**, e una pagina legge che è guidato
  (`navigator.webdriver`).
- **Il documento dopo un rimando** ha le intestazioni di sempre, con gli stessi valori, **in un altro ordine**
  (misura 1): un salto guardato arriva nell'ordine di una prima richiesta.
- **Con il browser del profilo, un sito fuori dal confine verso cui la pagina prova ad andare può vedere una
  connessione e il proprio nome**, e nessuna richiesta (misura 4).
- **Un sito che chiude la connessione sotto una richiesta senza rispondere la riceve più di una volta**: il
  browser del profilo la rimanda da sé — due volte da solo, **tre attraverso il cancello**, in ogni giro
  (`a-site-that-answers-nothing.txt`); lo shell una e una. Vale anche per il `POST` di un login. Con il cancello
  di prima era una, perché la mandava il driver. *Che cosa cambia con il cancello, visto dal sito*
  (`why-one-more-time.txt`): mentre la richiesta è in pausa il browser apre una seconda connessione, e quando la
  prima cade rimanda la richiesta su quella, e poi su una terza; da solo ne ha una sola pronta, e rimanda una
  volta.
- **Le richieste di un worker condiviso sono rifiutate**: hanno una cornice loro, che non è della pagina. Il suo
  script parte, ed è la pagina a chiederlo; quelle di un worker dedicato portano la cornice della pagina, e
  partono. Con il cancello di prima partivano tutte, come con il browser da solo (`what-the-reread-asked.txt`).
- **Il browser del profilo chiede l'icona del sito**, come ogni browser: con una route Playwright la abortiva da
  sé.
- **La cache del browser torna a essere quella del browser**: con una route era spenta.
- **Una pagina è giudicata dal browser per ciò che è**: con una route il documento consegnato gli risultava
  venuto da un indirizzo pubblico, e una cornice verso un indirizzo di questa macchina era bloccata (misura 3).
- **Ciò che Playwright fa da sé a ogni lancio** e che una pagina può vedere — fra cui il blocco dei service
  worker, che è uno script nella pagina — resta com'è.

### 8. Ciò che non è stato misurato, per nome

- **Un sito vero.** Ogni misura è con server su questa macchina: ELA non manda richieste di accesso a siti veri
  per provarsi. Che un sito riconosca un browser guidato, prima e dopo, questa milestone non lo cambia.
- **Ciò che non passa da un avviso**: una WebSocket, e ciò che il browser fa per conto suo senza una pagina.
  Com'era.
- **Altri modi di riempire una pagina aperta** oltre a quelli camminati (§5): una pagina aperta da una cornice
  interna; una aperta da una pagina aperta; un documento messo in una pagina con le API che non passano da
  `document.write`.
- **Una risposta presa dalla cache del browser**: se passa dall'avviso prima di essere servita.
- **Perché il browser attribuisca alla prima pagina** ciò che essa scrive in una pagina vuota: non è stato letto
  nel suo codice, è ciò che la sessione dice in ogni giro.
- **La regola con cui il browser decide di rimandare una richiesta** la cui connessione è caduta: ciò che è
  misurato è quante volte un sito la riceve e su quali connessioni (§7), non la regola.
- **Un avviso che smette a pagina aperta**: non è stato visto succedere, e non si sa provocarlo senza spegnerlo.
- **Ciò che del corpo di una richiesta resta nel processo di ELA.** Il driver consegna al client di Playwright,
  che gira nel processo di ELA, ogni richiesta della pagina con il suo corpo: letto nel codice del driver e del
  client, non misurato. L'adapter non lo legge e non lo tiene; ma dopo il click di un login ciò che il modulo
  manda passa di lì, com'era con il cancello di prima. Quanto vi resti non è misurato. *ADR 0063 §5 diceva che
  dopo il click il valore non ripassava più da quel processo: è corretto lì.*
- **Una versione nuova di Playwright**: la sessione del browser dipende da ciò che Playwright accende da sé nel
  browser; il lock fissa le versioni, e una versione nuova va rimisurata.

### 9. Il port, i codici, e ciò che un risultato porta

**Il port `Browser` guadagna un membro**, `another`, e `AccountBrowser` lo eredita. Nel suo contratto entra che
ogni uso di una pagina chiede al confine dove la pagina è, che di un'altra pagina non parte nessun documento, e
che cosa il confine non è. I nomi nuovi: `LeftSite`, `AnotherPage`; `Glanced` porta `another`.

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `Browser` | §19 | async | `another` |

*La riga di `AccountBrowser` è in ADR 0063 §2, che si scrive ancora con la sua implementazione e porta `another`
fra i suoi membri; quella di `Browser` in ADR 0052 §11 resta com'era, e si legge con questa accanto.*

**I verifier**: `browser.left_site` per ogni verifier del browser — lo sguardo su una pagina che è altrove, prima
dell'attesa o dopo —, e `browser.another_page` per quelli che aspettano un testo dopo un gesto.

Codici aggiunti ai verifier:

| Capability | Verifier | Codici di fallimento aggiunti |
|---|---|---|
| `browser.read` | `BrowserReadVerifier` | `browser.left_site` |
| `browser.act` | `BrowserActVerifier` | `browser.left_site`, `browser.another_page` |
| `browser.read_as_you` | `AccountReadVerifier` | `browser.left_site` |
| `browser.act_as_you` | `AccountActVerifier` | `browser.left_site`, `browser.another_page` |
| `browser.login` | `LoginVerifier` | `browser.left_site`, `browser.another_page` |

- **I risultati**: la chiave `another_page` in ciò che restituiscono `browser.read`, `browser.act`,
  `browser.read_as_you`, `browser.act_as_you` e `browser.login`, e fra ciò che una sessione guidata legge del
  risultato di un gesto. **Non entra nell'audit**: non è un numero.
- **I codici d'errore dei tool non cambiano**: `browser.left_site` c'era, e ha una frase in più.

## Alternative considerate

- **Una route di Playwright che lascia passare solo le richieste della prima pagina**, accanto alla sessione
  della pagina. Era la prima stesura della SPEC: scartata dal quarto fatto di §1, misurato.
- **La sessione della pagina soltanto.** Non ferma una pagina aperta da una pagina: la richiesta arriva, in
  ogni modo (misura 2).
- **Lanciare il browser perché non apra pagine nuove.** L'argomento ha effetto sullo shell e non sul browser
  del profilo (misura 2).
- **Chiudere una pagina nuova appena il browser la annuncia.** Poggia su chi arriva prima, e con lo shell
  perde (misura 2).
- **Far fallire lo step quando una pagina ne apre un'altra.** Un sito che apre una finestra da sé farebbe
  fallire una lettura riuscita (decisione 123).
- **Da quando la prima pagina ne ha aperta un'altra, non lasciarle caricare più niente da fuori dal confine.**
  Era la strada (b) della domanda 132: avrebbe retto la frase «nessuna richiesta» verso i siti fuori, al prezzo
  di togliere a una pagina ciò che prende altrove. La frase prometteva più del confine, e si è corretta la
  frase.
- **Il predicato nei tool, nei punti nominati.** Un tool potrebbe dimenticarlo; nell'adapter non può.
- **Un travestimento**: un altro nome, `navigator.webdriver` nascosto. ELA non lo aggira (decisione 118).

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo
dice, con la sezione di questo ADR a cui guardare.

- **ADR 0052** §6, §9, §10, §11 e §14 — **rivista apertamente** (decisione 109). §6: il documento della cornice principale non lo prende più una route, e la route non è più il driver: resta che cosa il confine è e chi lo decide, e il cancello è quello di §2; il confine regge a ogni salto. §9: i verifier guadagnano `browser.left_site` e `browser.another_page`, e i risultati `another_page` — le righe di quell'ADR restano, e si leggono con le tabelle di §9 accanto. §10 e M13.4c: «da quando la fermata è alzata niente parte più» vale per ogni richiesta di cui la sessione è avvisata, e ogni richiesta è lasciata andare allo stesso modo. §11: il port ha `another`. §14: ogni richiesta la fa il browser e ogni certificato lo giudica il browser; che il Core tolga le variabili del driver resta.
- **ADR 0063** §2, §4, §5 e §11 — §2: `AccountBrowser` ha `another`. §4: il cancello non è più una rotta di Playwright; la misura sui service worker è rifatta, e la difesa resta (§6). §5: i due confronti di `browser.login` — all'apertura e dopo il click — sono il predicato dell'adapter (§4), e i suoi verifier guadagnano i due codici. §11: la strada «misurata e non presa» è presa, in un'altra forma (§2).

Le altre conseguenze:

- **Regola di architettura 70**: il cancello guarda le richieste del browser e non ne fa nessuna — nel modulo
  dell'adapter della macchina non c'è una route di Playwright, né ciò che una route fa di una richiesta, né lo
  stacco di una sessione; e nemmeno le stesse cose dette nel protocollo del browser: il comando che spegne
  l'avviso (`Fetch.disable`), una risposta data al posto del sito (`Fetch.fulfillRequest`) o cambiata per strada
  (`Fetch.continueResponse`), una sessione staccata dal suo target (`Target.detachFromTarget`). **Ciò che la
  regola non vede** è una richiesta lasciata andare con qualcosa di cambiato — lo stesso comando che il cancello
  manda, con più cose dentro: lo tiene il test che confronta ciò che un sito riceve attraverso il cancello con
  ciò che il browser manda da solo (`test_what_a_site_receives_through_the_gate_is_what_the_browser_alone_sends`).
- **Una regola di comportamento, tenuta chiamando**: ogni membro del port che riceve una pagina e la usa chiede
  al confine dove la pagina è — trovato dalle firme del port, mai elencato
  (`tests/architecture/test_every_use_of_a_page_asks_the_boundary.py`); con i browser veri in
  `tests/infrastructure/machine/test_the_boundary.py`.
- **Un nodo che un giorno porterà il browser** (M13.11) eredita il cancello e deve saper dire `browser.left_site`
  e `browser.another_page`.
- **La prova di M13.9 si rifà per intero** sul commit di questa riparazione; il passo 6 com'è scritto, e la
  sezione 28 della guida porta, fuori dai passi, la misura con la finestra da fare solo se quel passo fallisce
  (decisione 119). *Annotato il 2026-10-13: rifatta tre volte quel giorno; la terza, per intero e sul commit che
  era allora l'ultimo, `6d3c470`, è passata, ed è quella che accetta questo ADR — la riga dello stato.*

Con questo ADR le regole di architettura sono **settanta** (la 70); i contratti di import-linter restano
**quindici**, i port **trentacinque**, le rotte dell'API **settantadue** e i comandi della CLI **trentanove**; le
capability restano **diciotto**, le identità del middleware **sei**.
