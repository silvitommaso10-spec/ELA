# 0070. La porta degli scaricamenti si dice chiusa alla risposta del browser

- **Stato:** **Accettata** il **2026-11-17**, con un commit suo (decisione 111 dell'ultima review del branch
  `m9.5-la-pulizia-della-suite`): la prova a mano della sezione 33 di `docs/GETTING_STARTED.md` è passata a `fa3377a`,
  l'ultimo commit del branch su origin (`~/Downloads/prova-m9.5-20261117-133606.txt`: 21 PASSATI al primo giro, 0
  FALLITI). **Che cosa ha mostrato**: i passi 2 e 3 — nella cartella il file chiesto e nient'altro, con il browser vuoto
  e con quello del profilo. **Che cosa no**: il passo 4 è finito `browser.download_not_started` in meno di 30 secondi e
  l'interruzione non l'ha esercitata. **L'interruzione la prova il test, non la mano**:
  `test_a_download_that_is_cut_short_is_cancelled_and_nothing_of_it_stays`,
  `test_a_download_the_time_of_its_step_cuts_leaves_nothing_in_the_folder` e
  `test_what_is_announced_while_the_door_closes_is_cancelled_and_taken_away`, sui due browser
  (`tests/infrastructure/machine/test_the_files_of_a_page.py`). **Le «Righe riviste» che questo ADR porta sono
  scritte**, con il marchio sulla riga «Stato:» dell'ADR che rivede — ADR 0066.
- **Data:** 2026-11-17
- **Riferimenti spec:** §19, §33
- **Milestone:** [M13.13b](../milestones/M13.13b.md)
- **Rivede:** ADR 0066 §8, punto 5 — apertamente, qui sotto (§4). ADR 0066 è Accettata e non si riscrive.

## Contesto

Il 2026-11-12 un giro di `make check` a `4b0b11c` ha trovato, una volta, un `.crdownload` nella cartella dopo che
`test_a_download_that_is_cut_short_is_cancelled_and_nothing_of_it_stays` aveva cancellato lo scaricamento (M13.13b,
«Che cosa eredita»). L'ipotesi del revisore — la porta conosce il nome di uno scaricamento solo quando ha sentito
`Browser.downloadWillBegin`, e una cancellazione che cade fra il file nella cartella e l'annuncio sentito non toglie
niente — è stata **confermata costruendo la precondizione** il 2026-11-14: l'annuncio trattenuto dal test prima della
porta, la cancellazione, la cartella (`.git/m9.5-reference/m13.13b/`). Con il browser vuoto il file restava fino alla
chiusura della pagina; **con il browser del profilo restava a test finito**, ancora `.crdownload`. La promessa di ADR
0066 §8, punto 5 — «uno scaricamento interrotto, fermato o scaduto è annullato, ed ELA toglie dalla cartella ciò che
porta il suo identificativo» —, nella cartella di chi usa ELA con `browser.download_as_you`, lì era falsa. E l'annuncio
sentito dopo era preso per «uno scaricamento che nessuno ha chiesto»: una seconda parola falsa, dalla stessa causa.

**La causa era un ordine, non un tempo.** `done` fa già un'andata e ritorno sulla sessione della porta prima di
decidere che cosa togliere — il `deny` —, ma `shut` si diceva chiusa **prima** di mandarlo: un annuncio che arrivava
mentre la risposta viaggiava trovava la porta già chiusa.

## Decisione

### 1. Tre stati: aperta, in chiusura, chiusa

**La porta si dice chiusa alla risposta del browser al suo `deny`, non quando lo manda.** Fra le due cose è **in
chiusura**: ciò che il browser annuncia allora è ancora del gesto — il primo, se la porta non ne ha sentito nessuno — o
accanto a lui, ed è annullato e tolto con ciò che porta il suo identificativo; dopo la risposta è un rifiuto, come
prima. **Un `deny` solo per chiusura**: una chiusura si comincia solo da aperta, e una che viaggia si aspetta, non si
ridice — la guardia che stava in `_progressed`, che metteva la porta a chiusa per non mandare il `deny` due volte, ora
è lo stato. `done` chiude se è aperta e aspetta la chiusura; la stessa chiusura è quella alla prima parola di
avanzamento (ADR 0066 §8, punto 3), dove vuol dire che ciò che è annunciato mentre la chiusura viaggia va accanto al
primo, e si toglie. **Nessuna attesa**: un ordine; il tempo resta quello del tool.

### 2. Che cosa ELA garantisce, e che cosa dichiara

**Garantisce, per l'ordine del protocollo**: i messaggi di una sessione arrivano nell'ordine in cui il browser li
manda, quindi ciò che il browser ha annunciato prima di ricevere il `deny` arriva prima della risposta, a porta in
chiusura, ed è annullato e tolto prima che il gesto ritorni — con i due browser.

**Dichiara**: che il browser annuncia uno scaricamento **prima di scriverne il file**, o almeno prima di rispondere a un
comando mandato dopo. È ciò che le misure mostrano (§3), non una cosa che ELA possa costruire: un browser che
scrivesse e annunciasse dopo la risposta avrebbe di nuovo la finestra, fra il suo file e il suo annuncio — e quel file
resterebbe, con l'annuncio preso per un rifiuto. **La porta toglie solo ciò che il browser ha annunciato per quel
gesto**: mai «ogni `.crdownload`», mai la cartella, che è di chi usa ELA e può avere file suoi (decisione 14 di M9.5).

### 3. La misura

**Il 2026-11-14, a un carico di 1,5–4,3** (`natural.jsonl`): con il browser del profilo il file non è mai comparso
prima dell'annuncio, 0 su 100 (l'annuncio da −18,51 a −3,99 ms prima del file); con il browser vuoto 4 su 100, e in 4
su 4 un comando di andata e ritorno sulla sessione della porta ha portato l'annuncio prima della sua risposta.

**Il 2026-11-17, sotto carico** — la suite intera in ciclo, come la serie B di M13.4g, con la regola scritta prima
dei numeri e committata a `6f9e44a` (decisione 62; `.git/m9.5-reference/m13.13b/misura-62/`), il carico medio a un
minuto fra 10,7 e 23,1:

| | il file prima dell'annuncio | l'annuncio dopo la risposta | annuncio meno file (min / mediana / max) |
|---|---|---|---|
| browser del profilo, 100 turni | **0 su 100** | — (mai esercitato) | −39,52 / −9,93 / −5,40 ms |
| browser vuoto, 100 turni | **28 su 100** | **0 su 28** | −5,99 / −0,98 / +11,57 ms |

**La garanzia non è smentita**: in 28 casi su 28 in cui il file c'era prima dell'annuncio, l'annuncio è arrivato prima
della risposta. **Con il browser del profilo l'ordine annuncio–risposta non è stato esercitato**, in 200 turni in due
giorni e a due carichi: lì il file non è mai comparso prima dell'annuncio. Il test rosso (§5) costruisce l'ordine del
protocollo, non quello del browser, e lo dice.

### 4. Un fatto dichiarato: lo scaricamento continua mentre `_shut` chiude il browser del profilo

Nella stessa misura (decisione 62), **per parentela e mai per nome** — i discendenti del processo di pytest presi
prima della chiusura della pagina, guardati ogni 10 ms con il loro istante di partenza —, il caso trattenuto con il
browser del profilo, 20 turni sotto carico (`misura-62/bis/held-tree-2.jsonl`; il primo giro non ha guardato niente,
per un difetto dello strumento detto in `riassunto.txt`):

- **`_shut` — il contesto, il browser, il driver — è durata 30,0 s in 20 turni su 20** (da 30 019 a 30 058 ms) con
  uno scaricamento in corso;
- **durante `_shut` i processi del browser del profilo sono vivi, e lo scaricamento continua**: il `.crdownload` è
  passato da 102 400 a 204 800 byte a circa 19,9 s dall'inizio della chiusura, quando il sito della prova ha mandato il
  resto da sé; i processi di Chrome for Testing sono finiti lì (12 turni) o a circa 30 s (8 turni);
- **dopo `_shut`**, in 7 turni su 20 un processo di quell'albero era ancora vivo — **il driver di Playwright**, mai un
  processo di Chrome — per 20,5–37,6 ms; il file non è più cambiato: lo scaricamento non continua dopo `_shut`;
- **a test finito il file resta**, 204 800 byte, ancora `.crdownload`, in 20 turni su 20.

È il caso di uno scaricamento che la porta **non ha mai sentito** — l'annuncio trattenuto fino a dopo la cancellazione
—: con questa decisione, nel prodotto, la porta lo sente in chiusura e lo annulla e lo toglie **prima** di `_shut` (§1).
Se un browser annunciasse dopo la risposta (§2), quel file resterebbe così. **Non è riparato qui** (decisione 62): né
la durata di `_shut` con uno scaricamento in corso, né il driver che vive qualche decina di millisecondi dopo. **Resta
dichiarato qui, senza una milestone sua** (decisione 92 della review a `42bac98`): dopo la riparazione **nessun
cammino del prodotto ci arriva**, perché la porta annulla lo scaricamento prima di `_shut`. I numeri passano a M13.11,
fra ciò che eredita: la durata di `_shut`, con il meccanismo non misurato, e il driver, come indizio per il debito di
ADR 0066 §10 — un indizio, non una diagnosi.

### 5. I test

- `tests/infrastructure/machine/test_the_files_of_a_page.py::test_what_is_announced_while_the_door_closes_is_cancelled_and_taken_away`,
  sui due browser: il test toglie dalla sessione della porta i suoi due ascoltatori — l'annuncio e le parole di
  avanzamento — e ne mette uno suo che li trattiene; avvolge `send` della sessione perché, quando la cancellazione manda
  il `deny`, li consegni alla porta nell'ordine in cui sono arrivati, dopo la risposta del browser e prima che la
  risposta torni a chi l'ha mandata. Solo l'API pubblica di Playwright (`remove_listener`, `on`, `send`) e
  `door._session`, che i test della porta toccavano già (decisione 61). Afferma di aver trattenuto l'annuncio e di
  averlo consegnato durante il `deny`: se ciò su cui si appoggia cambia, è rosso. Nella cartella, prima del gesto, un
  file d'altri che finisce in `.crdownload`, che resta. **Rosso sul codice di prima**, sui due browser, per la causa
  (`.git/m9.5-reference/porta/rosso-prima.txt`).
- **I mutanti**, sette, tutti presi sui due browser (`.git/m9.5-reference/porta/mutanti.txt`): l'ordine di prima; in
  chiusura come chiusa; `done` che non aspetta la chiusura; una porta che toglie ogni `.crdownload` (il file d'altri
  sparisce); un `deny` a ogni parola di avanzamento mentre la porta si chiude; e **i due della decisione 41 C di
  M13.13** — richiusa alla fine dello scaricamento, mai richiusa —, che muoiono ancora sul test della chiusura,
  `test_while_a_file_arrives_the_door_is_closed_and_a_second_download_writes_nothing`.

## Alternative considerate

- **Un comando in più dopo il `deny`** (`Browser.getVersion`), che non cambia niente, prima di decidere che cosa
  togliere: la prima stesura della SPEC. Scartata dalla rilettura (R6): il `deny` è già un'andata e ritorno; un comando,
  non due.
- **Togliere ogni `.crdownload` della cartella** alla cancellazione: vietato dalla decisione 14 — la cartella è di chi
  usa ELA, e un file d'altri con quel nome sparirebbe (uno dei mutanti).
- **Aspettare un tempo** dopo la cancellazione, perché l'annuncio arrivi: una soglia che la macchina non può risolvere
  (`CLAUDE.md`), e un'attesa allargata (decisione 14).

## Conseguenze

- Nella cartella di chi usa ELA, uno scaricamento cancellato — dal tempo del tool o dalla fermata di ELA — non lascia
  il suo file, per ciò che il browser ha annunciato prima della risposta al `deny`; e l'annuncio sentito in chiusura non
  è più preso per un rifiuto.
- Ciò che il browser annuncia dopo la risposta resta un rifiuto, come prima: un browser che scrivesse prima di
  annunciare lascerebbe il file, e §2 lo dichiara.

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0066** §8, punto 5 — «uno scaricamento interrotto, fermato o scaduto è annullato, ed ELA toglie dalla cartella ciò che porta il suo identificativo»: vale per ciò che il browser ha annunciato prima di rispondere al `deny` della chiusura, che la porta sente in chiusura (§1, §2); il resto è dichiarato (§2, §4).
