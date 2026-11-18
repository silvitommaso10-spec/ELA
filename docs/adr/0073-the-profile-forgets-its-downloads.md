# 0073. Il browser del profilo dimentica i suoi scaricamenti prima di ogni lancio guidato

- **Stato:** **Proposta** il **2026-11-18**, con l'implementazione di M13.13c (`docs/milestones/M13.13c.md`: la
  registrazione, le misure delle decisioni 104 e 114, la SPEC e la sua review, le risposte 107–113 e le decisioni dalla
  114). Diventa Accettata con un commit suo dopo la prova a mano (decisione 118). **La prova a mano del criterio 2 è il
  passo 3 della sezione 34 di `docs/GETTING_STARTED.md`**, rifatta dall'inizio sull'ultimo commit del branch con
  `scripts/prova_m13_15.py`, sul profilo vero, che è con ogni probabilità già nello stato che fa cadere il browser. Prima
  del passo 3 non si pulisce niente a mano, e lo script lo chiede. Il criterio 1 e la finestra li provano il test e la
  misura A5-S1, non la mano. **La riga dirà chi ha visto che cosa**, come quella di ADR 0070.
- **Data:** 2026-11-18
- **Riferimenti spec:** §19, §33, §57
- **Milestone:** [M13.13c](../milestones/M13.13c.md)

## Contesto

Il 2026-11-17 alle 23:30, nella prova a mano di M13.15, il browser del profilo è caduto al passo 3, uno scaricamento con
`browser.download_as_you`. Era il terzo scaricamento sul profilo vero, contando i file delle prove. M13.9d ha fatto sì che
ELA lo dica subito, `browser.failed` «the browser ended by itself», invece di restare appesa (ADR 0072 §3). La serie della
decisione 85 l'ha riprodotto su un profilo di prova: due scaricamenti riusciti, poi il crash a ogni corsa. Dei cinque
rapporti, uno ha la firma del crash vero, `EXC_BAD_ACCESS` a `0xcdcdcdcdcdcdcdcd` sul thread principale del browser, e
gli altri quattro sono `EXC_BREAKPOINT` sullo stesso cammino.

## Decisione

### 1. L'innesco, misurato

Le misure delle decisioni 104 e 114, e A5, tutte su profili di prova (`docs/milestones/M13.13c.md`): ogni braccio su tre
profili, fino a dieci corse, con la regola scritta prima dei numeri.

- **Chrome for Testing 153.0.8010.12 cade a uno scaricamento nuovo quando, al lancio, `Default/History` ha scaricamenti
  completi.** Con il tool di ELA il primo crash viene dalla seconda alla quarta corsa, su ogni profilo, senza finestra e
  **con la finestra** (A5). Cade **anche senza la porta di ELA**, con lo scaricamento di Playwright com'è, alla terza o
  alla settima (A7). L'innesco è del browser.
- **Non è il file che manca** (A1), **né il file del piano** (A2), **né lo stesso indirizzo** (A4).
- **Con le righe degli scaricamenti tolte da `History` prima di ogni lancio, il browser non cade**: 0 crash in 60 corse
  su profili nuovi (A3 due volte). **Un profilo che era già caduto torna a funzionare**: 0 in 30 corse (M1), e 0 in 12 con
  la finestra (A5-S1).
- **Il browser rimette le righe da sé**, al lancio dopo, dal suo archivio degli scaricamenti (`Default/shared_proto_db/`):
  letto il guid, non misurato chi le rimette. Quindi ciò che conta è la storia **al lancio**.
- **Una lettura su un profilo caduto non cade**: 0 in 30 (M2b). Cade lo scaricamento.
- **I due candidati che non toccano `History`**, presi leggendo il sorgente di Chromium al tag della versione, cadono e
  non guariscono: `history.saving_disabled` (A8) e `DeferredDownloadHistoryLoading` (A9).

### 2. Che cosa fa ELA

**Prima di ogni lancio guidato del browser del profilo**, nel posto dove prepara già la cartella (`_prepared`, ADR 0063
§4), ELA toglie le righe delle tre tabelle degli scaricamenti di `Default/History`:
`downloads`, `downloads_url_chains`, `downloads_slices` (`DOWNLOAD_TABLES`). Ogni lancio guidato, e non solo quello di uno
scaricamento, perché lo scaricamento cade anche con la finestra (decisione 116). Le condizioni:
- **a cartella libera**: l'apertura l'ha guardata, e questo viene prima del lancio;
- **il file è un file suo**: un link, una cartella, ogni cosa che non è un file non si segue e non si tocca;
- **tre istruzioni e nient'altro**, `FORGET`, `DELETE FROM` senza `WHERE`, in una transazione sola. Se le tabelle non sono
  quelle attese, la transazione torna indietro e **non si tocca niente**;
- **nessun'altra tabella** di `History`, e **`shared_proto_db` non si tocca**;
- **un `History` che non c'è**, un profilo nuovo, non è niente da dimenticare, e non è un errore.

**Se non si può**, il lancio va avanti (decisione 112): un browser che poi cade lo dice già ADR 0072 §3, e un rifiuto
fermerebbe anche letture, gesti e login che non cadono. **ELA lo dice dove dice le altre righe del browser**, su stderr di
`ela serve`, con il tipo di ciò che l'ha fermato e mai un percorso:

`ela: the downloads the browser of the profile remembers were not forgotten before a launch (OperationalError): the launch goes on`

### 3. Che cosa ELA non legge, ancora e sempre

**Nessuna riga di `History` è letta**: né degli scaricamenti, che si tolgono senza leggerli, né di un'altra tabella. Dalla
storia l'adapter non fa uscire niente, né un indirizzo né un nome di file; al più il tipo di un errore. Un test lo tiene
con l'autorizzatore del database, che dice che cosa fa ogni istruzione. Il resto di ciò che ELA legge nella cartella resta
com'è in ADR 0063 §4: il lock, il file delle preferenze, il conto delle righe del gestore delle password.

### 4. Che cosa vede chi apre la lista degli scaricamenti nella finestra — misurato

**La stessa lista di prima.** La misura della lista (`m13.13c/misura-lista/`): tre profili di prova, due scaricamenti con
il tool di ELA e S1, poi la pagina `chrome://downloads` aperta da un lancio senza S1, come quello della finestra. La lista
ha **2 elementi**, e dopo S1 ne ha ancora **2**, sui tre profili: il browser rimette gli scaricamenti da sé. Contati, mai
letti. È la stessa pagina che mostra la finestra; la misura l'ha aperta senza finestra.

### 5. Il lancio della finestra non la fa

La finestra del login a mano non è un lancio guidato (ADR 0063 §8): non la fa, come non toglie i service worker. Il login
di ELA parte con la finestra ed è guidato, e la fa.

### 6. Ciò che questo ADR dichiara e non risolve

- **Perché Chrome for Testing cade**: senza simboli pubblici per quella build (decisione 99), i nomi delle funzioni non ci
  sono. La riparazione la decide la misura.
- **Chi rimette le righe**, e se un aggiornamento del binario cambierà l'innesco o le tabelle. Se le tabelle cambiano,
  l'operazione non diventa un niente silenzioso: non tocca niente, e lo dice (§2); e il test del criterio 1 sul binario del
  lock torna rosso.
- **I rapporti di crash del sistema**: il sistema non ne scrive uno per ogni crash — 4 per i 24 crash della seconda
  misura —, e ne ha tolti di vecchi, tre dei cinque della serie della decisione 85, copiati prima nell'officina. Il giro
  rosso dei test di questo ADR ne ha scritto uno (`m13.13c/rapporti-dopo-i-rossi.txt`).

### 7. I test

- `tests/infrastructure/machine/test_the_profile_forgets_its_downloads.py`:
  - sul binario vero, solo sul Mac, i criteri 1 e 2, rossi sul codice di prima: dieci scaricamenti e l'undicesimo, con i
    file che restano, una riga sentinella di `urls` che resta, e il cookie del sito che torna; e un profilo con uno
    scaricamento completo fatto da Playwright, sul quale i dieci dopo riescono;
  - l'operazione: le sole tre tabelle; nessuna riga letta; la finestra che non la fa; il profilo nuovo; il link; le
    tabelle che non sono quelle attese; la ragione detta e il lancio che va avanti.
- `tests/composition/test_browser_wiring.py`: la riga, dove la scrive la chiusura di ELA.
- `tests/docs/test_adr_the_profile_forgets_its_downloads.py`: questo ADR, il suo marchio, le sue costanti.

## Alternative considerate

- **S2, una preferenza o un argomento del lancio**, senza aprire `History` (decisioni 113–115). I due candidati letti nel
  sorgente cadono e non guariscono (§1). La regola della decisione 115 sceglieva S2 se un candidato passava; nessuno è
  passato.
- **S3, un'altra versione di Chrome for Testing**: toccherebbe il binario di ogni capability del browser, e non è misurata.
- **La pulizia a mano dalla finestra**: non ripara il criterio 1, e che cosa tolga dall'archivio del browser non è
  misurato.
- **Nascondere il crash**, per esempio rifacendo lo scaricamento: esclusa (decisione 105).

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0063** §4 — prima di un lancio guidato ELA scrive anche in un database del profilo, `Default/History`: toglie le
  righe delle tre tabelle degli scaricamenti, senza leggerne nessuna, e nient'altro (§2, §3).

Le altre conseguenze:

- **Il port** non cambia. L'adapter del browser del profilo prende dalla composizione chi è avvisato quando gli
  scaricamenti non si sono potuti dimenticare, e `build` lo dà con `said`.
- **ADR 0066 §8 resta com'è**: la porta e il nome del piano non cambiano. Era la sua capability a cadere, non la porta.
- **La prova della sezione 33**, passata il 2026-11-17 al secondo scaricamento del profilo vero, resta vera per ciò che
  ha mostrato (M13.13c, «Che cosa resta vero, e che cosa no»).
