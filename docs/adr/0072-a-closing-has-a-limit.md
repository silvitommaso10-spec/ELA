# 0072. Una chiusura del browser ha un limite

- **Stato:** **Proposta** il **2026-11-18**, con l'implementazione di M13.9d (`docs/milestones/M13.9d.md`: la SPEC, la
  review della SPEC — le risposte 80–90 e le decisioni 91–97 —). Diventa Accettata con un commit suo dopo la prova a
  mano (decisioni 87 e 94), che ha due parti:
  - il browser che cade lo prova il test e non la mano: `tests/infrastructure/machine/test_a_closing_has_a_limit.py`,
    rosso sul codice di prima e verde dopo;
  - la sezione 34 di `docs/GETTING_STARTED.md` si rifà dall'inizio sull'ultimo commit del branch, con
    `scripts/prova_m13_15.py`, e il suo passo del «ferma» mostra sull'ELA vera uno step fermato mentre il file arriva.
  
  **La riga dirà chi ha visto che cosa**, come quella di ADR 0070. Un ADR non basta se la prova a mano non è passata.
- **Data:** 2026-11-18
- **Riferimenti spec:** §19, §33, §65
- **Milestone:** [M13.9d](../milestones/M13.9d.md)

## Contesto

Il 2026-11-17, nella prova a mano di M13.15, il browser del profilo è caduto 1,28 s dopo il lancio, con
`EXC_BAD_ACCESS` sul thread principale. Lo step di `browser.download_as_you` è rimasto `RUNNING` per mezz'ora:
- il tempo del tool, 30 s, non l'ha finito;
- il «ferma» del task non l'ha liberato;
- lo stop di ELA sì.

**La misura** ha costruito la precondizione su profili di prova (M13.9d, «La misura»). Un browser che muore mentre il
`deny` della porta viaggia e il file arriva lascia ELA appesa, con il quadro visto quella sera: il driver vivo,
addormentato, senza figli e senza pipe verso il browser, e `playwright.stop` mai chiamato. Succede con i due browser.

**Il meccanismo** ha due parti:
- Playwright 1.63.0 non rigetta una chiamata in volo su una sessione del browser quando il browser muore;
- la scadenza del tool cancella una volta sola, e il `finally` di `_downloaded` cominciava un'attesa nuova, senza
  limite, di quel `deny`.

Dopo la scadenza **nessuna attesa aveva un limite**: le chiusure della pagina, della porta, del driver, e l'`_abort`
di Playwright di una chiamata cancellata. Basta che una di quelle chiamate non risponda.

## Decisione

### 1. Una chiusura ha un limite, e al limite il driver si uccide

**Il limite** è `BROWSER_CLOSE_GRACE_SECONDS`, 5 s: quello dello stop di ELA, con lo stesso significato, «un browser a
cui è stato detto di chiudere, e che non ha chiuso». Una costante sola per le due cose (decisione 83). La composizione
lo dà ai due adapter, e nell'adapter non c'è un numero. **Nessun tempo è allargato**: il tempo del tool resta 30 s.

Una chiusura, o un membro del port cancellato, si aspetta **al più il limite**. Passato il limite:
1. il driver di quell'apertura, e ciò che ha avviato, sono uccisi per parentela: `SIGKILL`, mai `SIGTERM` prima (la
   forma di ADR 0060 §7). Con il driver morto ogni chiamata di Playwright in volo cade;
2. si toglie dal disco ciò che la chiusura avrebbe tolto (§4), quando il kernel non sa più niente dei processi uccisi;
3. si aspetta ancora al più il limite. Passato anche quello, il lavoro è **lasciato**: cancellato, fuori dalle chiusure
   che la chiusura di ELA aspetta, e detto (§5).

**La cartella del profilo resta**: l'adapter toglie solo i profili temporanei che Playwright nomina, come alla grazia
dello stop (ADR 0063 §4). **Un'apertura uccide solo il suo driver**: ogni apertura ne ha uno, e una seconda apertura
dello stesso adapter va avanti. **Due limiti che scadono insieme** — quello di una chiusura e quello del membro che la
aspetta — **dicono un'uccisione sola**.

**Il limite di una chiusura parte dal suo inizio**, non da una cancellazione. Così una chiusura che nessuno cancella —
la `close` che il tool fa dopo il suo tempo — ha il limite anche lei. E **un'operazione riuscita resta riuscita**:
uno scaricamento finito la cui chiusura incontra un driver che non risponde torna con il suo file, e l'uccisione è
detta.

**Il criterio**: nessuno step di un tool del browser resta `RUNNING` oltre il tempo del tool più una chiusura con il suo
limite scritto. Quel limite è il limite, l'uccisione — l'attesa del kernel ha la sua, `GONE_SECONDS` — e il limite di
nuovo, per ciò che l'uccisione non ha finito.

**Il «ferma» passa per la stessa strada** (decisione 82). Lo scaricamento che arriva lo sente e cancella; gli altri tool
lo sentono al loro punto (ADR 0054 §3), e l'operazione in volo finisce al tempo del tool. **Dal «ferma» alla fine dello
step, il caso peggiore** (risposta 107 della review di M13.9d) si scrive dalle costanti, e non come un numero:

il tempo del tool + `BROWSER_CLOSE_GRACE_SECONDS` + `GONE_SECONDS` + `BROWSER_CLOSE_GRACE_SECONDS`

È il caso di un tool che sente il «ferma» solo al suo punto, con una chiamata in volo su un driver che non risponde: la
chiamata finisce al tempo del tool, la chiusura aspetta il limite, l'uccisione aspetta il kernel, e ciò che nemmeno
l'uccisione finisce ha il limite di nuovo, poi è lasciato e detto. Quando l'uccisione finisce il lavoro — con il driver
morto ogni chiamata in volo cade (§6) — lo step finisce prima. Lo costruisce
`test_the_worst_case_after_the_stop_ends_within_the_written_formula`, sui due browser: il driver e il browser fermati
appena la pagina è aperta, e il «ferma» subito dopo. **La risposta 82 diceva «mai più del tempo del tool più il
limite»: era più stretta del vero**, ed è corretta apertamente in M13.9d.

### 2. Una guardia sola, a mondo chiuso

`_guarded` sta sopra ogni membro del port che chiede qualcosa al driver. Il membro gira in un task suo, e i driver che
avvia o usa sono scritti mentre va. Quando chi lo aspetta è cancellato — il tempo del tool, il «ferma» che il tool
sente, un task cancellato —, il task è cancellato e ha il limite di §1. **La cancellazione resta quello che è**: diventata
altro, il tempo del tool non scatterebbe. Un lavoro già finito quando la cancellazione arriva risponde con ciò che ha
fatto.

**Le chiusure stanno sotto lo stesso limite, dal loro inizio**:
- la pagina, `_shut`;
- ciò che un'apertura non consegna, `_dropped`;
- la porta, `_Door.done`;
- lo stop di un driver che un'apertura lasciata stava avviando.

**Esenti, con la loro ragione** — non chiedono niente al driver: `installed`, `another`, `refused_download`, `keep`,
`hold`, `can_show`, `occupied`, `linked`, `saved`, `profiles`, `window`, `shut`. La finestra è un processo che ELA
lancia da sé, con una grazia sua.

**La regola** è `tests/architecture/test_every_member_of_the_browser_passes_the_guard.py`. Deriva i membri dai due port
e afferma che ciascuno passa per la guardia o è esente con la sua ragione; un'esenzione tolta, o un membro aggiunto a un
port, la fa parlare.

### 3. Il browser che finisce da sé

L'adapter sente la fine del browser dalla chiusura del suo contesto. **Misurato il 2026-11-18 sui due browser**
(`m13.9d/sonda-81/`): il browser ucciso con il `deny` in volo e lo scaricamento in corso, e la chiusura del contesto
arriva 11 ms dopo con il browser del profilo e 4 ms dopo con quello vuoto, che dice anche `disconnected`. In tutti e due
i casi il `deny` era ancora senza risposta. Da quella fine:
- le attese degli eventi del browser (`_first_of`, `_stopped_or`) si svegliano, e lo step finisce **subito** con
  `browser.failed` «the browser ended by itself» (`ENDED`), invece di aspettare il tempo del tool;
- la porta non aspetta più la risposta di un browser finito. Il `deny` e la cancellazione dello scaricamento, mandati a
  un browser finito, falliscono subito (misurato), e non sono aspettati; ciò che il browser aveva annunciato si toglie dal
  disco (§4).

**Che cosa sveglia la morte del driver, e che cosa no.** Con il driver morto le chiamate di Playwright in volo cadono;
le attese di un evento (la fine di uno scaricamento) no. Le sveglia la fine del browser, oppure la cancellazione.

### 4. Ciò che il browser aveva annunciato, tolto dal disco (decisione 91)

Dopo un'uccisione al limite, e dopo un browser finito da sé, **ELA toglie dalla cartella ciò che il browser aveva
annunciato per quel gesto**:
- per identificativo, il nome che il browser gli ha dato e quel nome mentre arriva, **mai per somiglianza**: un file
  d'altri che finisce in `.crdownload` resta;
- con un lavoro solo del disco, `_Door.swept`, che non chiede niente al browser e sta fuori dall'attesa che il limite
  taglia. Lo chiama `done`, e lo chiama il limite dopo l'uccisione, qualunque cosa `done` stesse aspettando.

Ciò che il browser non aveva annunciato resta dichiarato, come in ADR 0070 §2.

### 5. L'uccisione detta

**Dove lo stop di ELA dice la sua**: su stderr di `ela serve`, nella stessa forma, i nomi dei processi con quanti di
ciascuno, mai una riga di comando:

`ela: a browser of a step did not close within 5 s: ELA killed what it had started — 1 Google Chrome for Testing, 1 node`

**La frase è una costante in un posto solo**, `KILLED` in `src/ela/composition/root.py`, e la usano le due righe. Un
lavoro lasciato è nominato accanto ai processi, `closing left unfinished` (`LEFT`). L'adapter riceve dalla composizione
chi è avvisato; `build` riceve `said`, che `ela serve` dà come la sua `_say`.

**Nell'esito dello step no, senza cambiare il port** (risposta 80): il port del browser non ha una strada per dire al
tool che una chiusura è finita con un'uccisione. Una chiamata cancellata finisce con la sua cancellazione, e una riuscita
torna con il dataclass del port. Il codice e le parole dello step restano quelli di ciò che l'ha finito:
`browser.timeout`, `browser.stopped`, `browser.failed`.

### 6. Un fatto dichiarato: Playwright 1.63.0 e una chiamata in volo su un browser morto

**Misurato** con il registro del protocollo del driver (M13.9d, «La misura», e la sonda di §3).
`CRConnection._onClose` scarta solo la sessione radice (`playwright/driver/package/lib/coreBundle.js:34953-34960`). Le
sessioni nate sotto di lei — `new_browser_cdp_session`, quelle della porta e del cancello — tengono le loro chiamate in
volo, e le rigettano solo al proprio `dispose`. **ELA non ripara Playwright: dà un limite alle sue attese.**

**Il test che ci poggia afferma di aver costruito la sua precondizione** (decisione 95). Quando ELA chiede al driver di
fermarsi, il `deny` deve essere ancora senza risposta. Se un aggiornamento di Playwright lo rigetta alla morte del
browser, il test è rosso e lo dice. Il test del driver che non risponde più non dipende da Playwright.

### 7. La misura del limite (decisione 92)

Regola scritta e committata prima dei numeri, a `0e751d5`. La suite intera, sotto il suo carico, con uno strumento
dell'officina che non entra nel commit (`m13.9d/misura-92/`): **13453 passed, 17 skipped** in 404,41 s, a batteria e
con il Low Power Mode spento, e 1322 chiusure misurate. **Le sane** — tornate, in un test passato, senza un segnale nel
test — sono 1282. **La più lunga è di 694,4 ms**, `_shut` del browser del profilo, sotto i 2,5 s della metà del
limite. Il limite resta 5 s. Il primo giro si era rotto per un difetto dello strumento, ed è detto nell'officina.

**ADR 0070 §4 misurava una chiusura di 30,0 s** del browser del profilo con uno scaricamento in corso. Con il limite,
quella chiusura è tagliata a 5 s, il driver ucciso, e il file annunciato tolto (§4). Il test di §4 costruisce proprio
quel caso: il driver e il browser fermati mentre il file arriva.

### 8. Allo stop di ELA il limite non corre contro la grazia

Quando lo stop di ELA è alzato, una chiusura che passa il suo limite non uccide. La uccide **la grazia dello stop**
(`settle`, M13.4e), che la dice come sua: «the browser did not close within 5 s of the stop». I due tempi sono lo stesso
numero, e partono quasi insieme: senza questa regola l'uccisione dello stop sarebbe stata detta come quella di uno step
(trovato da `tests/api/test_serving_signals.py`).

### 9. Che cosa trova il prossimo lancio su un profilo il cui browser è stato ucciso

Il lock di un processo che non c'è più. `lock_holder` (`src/ela/infrastructure/machine/account.py`) lo dice
libero, e Chrome for Testing lo riprende (misurato il 2026-11-18, 2 su 2). La preparazione della cartella
(`_prepared`) riscrive le preferenze e toglie i rapporti di Crashpad. È ciò che succede oggi dopo lo stop di ELA, che uccide
allo stesso modo, e il test apre una pagina di nuovo dopo l'uccisione.

### 10. Ciò che questo ADR dichiara e non risolve

- **Perché Chrome for Testing è caduto** il 2026-11-17: la serie della decisione 85, scritta in M13.9d, l'ha riprodotto
  dal terzo scaricamento con il browser del profilo sullo stesso profilo. È un difetto di `browser.download_as_you`, ed è
  di [M13.13c](../milestones/M13.13c.md) (decisione 103). ELA lo dice con il codice di §3 e non resta appesa.
- **L'uccisione al limite nell'esito dello step e nell'audit**: è detta su stderr di `ela serve`, nella forma dello stop
  (§5), e non nell'esito dello step né nell'audit. Portarla lì vuole una strada nel port del browser, ed è in conto a
  [M13.11](../milestones/M13.11.md), che lo tocca (risposta 98).
- **Il rosso di `4e4adc5`**, un lancio non arrivato in 180 s in un test: è di [M13.9e](../milestones/M13.9e.md), fuori
  dalla fila.
- **Un lavoro lasciato** resta nel ciclo finché non finisce da sé. Il limite gli ha già ucciso il driver; se non sente
  nemmeno la cancellazione, è un difetto di ELA, e la riga lo dice.
- **Uno stop alzato senza la chiusura di ELA dopo**: le chiusure aspettano la grazia che non viene. Nel prodotto lo
  stop è sempre seguito dalla chiusura (ADR 0038 §11).
- **L'avviso di asyncio dopo un'uccisione del driver** (risposta 108): «Future exception was never retrieved», con
  «Connection closed while reading from the driver». Il future è di Playwright, `on_error_future` del trasporto del client:
  quando il driver muore il trasporto vi mette l'eccezione, e se nessuna chiamata era in volo nessuno la guarda. Nella
  suite è una riga dell'uscita; nel prodotto andrebbe nel log di asyncio, su stderr di `ela serve` (letto, non misurato).
  **Non si zittisce** con un filtro né con un gestore globale, che nasconderebbero gli altri.

### 11. I test

- `tests/infrastructure/machine/test_a_closing_has_a_limit.py`, sui due browser dove il caso c'è, con un limite corto
  dato dal test, 2 s, quasi tre volte la chiusura sana più lunga. I casi:
  - il browser che muore con il `deny` in volo;
  - il driver e il browser fermati mentre il file arriva, con il tempo del tool e con il «ferma»;
  - il driver fermato al lancio;
  - un'apertura che uccide solo il suo driver;
  - uno scaricamento riuscito la cui chiusura è uccisa;
  - una chiusura che non finisce nemmeno dopo l'uccisione;
  - il browser che muore prima dell'annuncio dello scaricamento;
  - un uso di una pagina il cui driver non risponde più;
  - il file annunciato tolto anche quando la chiusura della porta non finisce;
  - il caso peggiore dopo il «ferma», contro la formula di §1 (risposta 107).
  
  **Rossi sul codice di prima**, ciascuno per la sua ragione: `m13.9d/rossi-prima-riassunto.txt`, e per i tre aggiunti
  dopo il ripasso dei mutanti — il browser che muore prima dell'annuncio, l'uso di una pagina, il file annunciato —
  `rossi-prima-2.txt` e `rossi-prima-3.txt`. Il caso peggiore della risposta 107 è un limite scritto, verde sul codice di
  allora: lo prova il mutante 12 di M13.13c, il primo limite quattro volte più lungo, che il test fa morire. Nessuno scrive un
  rapporto di crash sulla macchina: la morte si costruisce con `SIGSTOP` e `SIGKILL` (decisione 89).
- `tests/architecture/test_every_member_of_the_browser_passes_the_guard.py`, la regola di §2.
- `tests/composition/test_browser_wiring.py` e `tests/api/test_server.py`: la riga, la costante, e `said`.

## Alternative considerate

- **Un codice nuovo, `browser.killed`**: nasconderebbe la causa — il tempo, il «ferma», il browser — che è ciò che chi
  legge lo step vuole sapere (risposta 80).
- **Un limite suo per la chiusura di uno step, diverso da quello dello stop**: un secondo numero per la stessa cosa,
  «un browser a cui è stato detto di chiudere» (decisione 83).
- **Riparare Playwright**: non è di ELA, e il limite serve anche a un driver che non risponde per qualunque ragione.
- **Uccidere il driver alla scadenza del tool, senza limite**: toglierebbe a ogni chiusura sana il tempo di finire da
  sé, e con lei i cookie che il browser scrive chiudendo.

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0052** §10 — «una scadenza sola attorno a tutto il lavoro del port»: dopo la scadenza la chiusura ha il suo limite, che non è di Playwright ma di ELA (§1).
- **ADR 0054** §11 — il «ferma» a metà di uno step del browser chiude entro il caso peggiore di §1, la formula delle costanti, per la strada della scadenza (§1).
- **ADR 0063** §4 — l'uccisione non è solo alla grazia della chiusura di ELA: anche al limite di una chiusura, e la cartella del profilo resta come lì (§1, §9).
- **ADR 0066** §8, punto 4 — la fine di uno scaricamento si aspetta entro il tempo del tool; la chiusura della porta, dopo, ha il limite; e il browser che finisce da sé la sveglia (§1, §3).
- **ADR 0070** §1, §4 — «nessuna attesa: il tempo resta quello del tool»: la porta aspetta la risposta al suo `deny` al più il limite, e non aspetta un browser finito; la chiusura di 30,0 s con uno scaricamento in corso è tagliata al limite, il driver ucciso e il file annunciato tolto (§1, §3, §4, §7).

Le altre conseguenze:

- **Il port** non cambia: nessun membro e nessun campo. Cambiano gli argomenti con cui la composizione costruisce i due
  adapter — il limite e chi è avvisato di un'uccisione — e `build`, che prende `said`.
- **Ogni costruzione degli adapter**, nei test e negli script, passa un limite: quello di ELA, o uno corto che il test
  dà da sé (§11).

Con questo ADR le regole di architettura restano **settantaquattro**, i contratti di import-linter **sedici**, i port
**trentasei**, le rotte dell'API **settantadue**, i comandi della CLI **trentanove**, le capability **ventidue**, le
identità del middleware **sei**.
