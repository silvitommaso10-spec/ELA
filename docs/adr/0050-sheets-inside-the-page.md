# 0050. La pagina di chi non è ancora nessuno porta i suoi fogli: dentro la risposta, ammessi dal loro hash, e nessuna rotta che risponda a nessuno

- **Stato:** Proposta. SPEC di M17.2c decisa dall'utente il 2026-09-26, con le decisioni 7–10 — tutte
  (a) — e le correzioni C e D della sua review. Diventa **Accettata** quando la prova a mano di
  `docs/GETTING_STARTED.md` §18 è passata, in Chrome e in Safari sul Mac e in Chrome sull'iPhone.
- **Data:** 2026-09-26
- **Riferimenti spec:** §6
- **Milestone:** M17.2c

## Contesto

M12.5 (la sua decisione D) e ADR 0043 §5 hanno scelto fra due strade, e le hanno scritte: **servire
i fogli a chiunque**, che sarebbe stata la prima rotta anonima di ELA — un'esenzione, ADR 0037 §3 —,
oppure **nessuno stile**. Hanno scelto la seconda, e l'hanno dichiarata: la pagina d'arruolamento è
«senza identità visiva, con il carattere di default del browser» (ADR 0043 §10), e M17.2 l'ha
ereditata per la console (la sua decisione G). **La scelta ha funzionato esattamente come era
scritta.** Il suo prezzo: la prima pagina di ELA che un browser nuovo vede — quella che chiede il
codice — era una pagina bianca.

La terza strada non era fra le due perché la politica si leggeva come un dato: «la CSP vieta gli stili
in linea». La politica è di ELA, e un hash ammette esattamente i byte che ELA ha scritto e nessun
altro. E la pagina d'arruolamento non è la sola a raggiungere chi non è riconosciuto: la pagina
«rifiutata» ci arriva dal `403` di un modulo che non viene da ELA, e dall'`_handler` degli errori
sotto il prefisso di una rotta d'arruolamento, dove l'identità è un codice e un cookie non c'è.

## Decisione

### 1. I fogli viaggiano dentro la pagina

Le due pagine che possono arrivare a un browser non riconosciuto — **il modulo d'arruolamento e la
pagina «rifiutata»** — portano i due fogli del design system in un blocco `<style>`, **sempre**,
chiunque le riceva e in ogni modo in cui ci si arrivi (decisione 9). La regola è della pagina, non
della richiesta: decidere dalla richiesta sarebbe una seconda domanda su chi sta chiamando, fuori dal
middleware. Tutte le altre pagine collegano i fogli, come prima. **Nessuna rotta nuova**: le rotte dei
fogli restano dietro l'identità.

Il blocco è la concatenazione esatta dei testi di `STYLESHEETS`, nel loro ordine, letti **a ogni
risposta** dalla stessa funzione che serve i fogli a un browser riconosciuto (`sheet_text`), da una
cartella sola (`DESIGN_SYSTEM`): gli stessi file, nello stesso modo (decisione 7). Il suo markup sta
in un modello di ogni superficie, `style.html`, su una riga sola — ogni carattere dentro l'elemento
entra nel testo che il browser mette sotto l'hash —, ed entra crudo, come `Markup`: `html.escape`
cambierebbe il `>` e le `"` dei fogli.

**I byte dei fogli arrivano a chiunque bussi**, commenti compresi. Non sono un segreto: sono file di
un repository, e non nominano niente dell'utente. Ciò che resta dietro l'identità sono le rotte.

### 2. La politica si deriva da ciò che la pagina porta

Una pagina con i fogli dentro ha la sua politica, **uguale a quella costante in tutto tranne
`style-src`**, che ammette **solo** il `sha256` del testo del blocco, codificato in UTF-8 — ciò che un
browser mette sotto l'hash di un `<style>` (decisione 8):

```
default-src 'none'; style-src 'sha256-…'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'
```

Niente `'self'`, perché quella pagina non carica niente; niente `'unsafe-inline'`, niente
`'unsafe-hashes'`, niente `nonce`, nessuno `script-src`. Le pagine che collegano i fogli tengono
`CONTENT_SECURITY_POLICY`. **L'hash non è scritto da nessuna parte**: si calcola a ogni risposta dal
valore che diventa il blocco, e blocco e hash sono lo stesso valore. Le due produttrici di una
politica stanno in `pages.py`, l'unico posto dove nasce una pagina (regola 57): la costante e
`inside_policy`. Il test che le tiene lavora su di loro — su ogni testo, con `hypothesis` —, e un
campione di pagine dice soltanto che le pagine le usano (correzione D).

### 3. Il compositore non ha un default

`sheets` è obbligatorio: un prefisso collega i fogli, `INSIDE` li mette dentro. `None` avrebbe
cambiato senso in silenzio — ADR 0044 §4 aveva scritto che `sheets=None` non ha «un default che possa
vestire una pagina per distrazione», perché vestire una pagina voleva dire una rotta anonima.

### 4. Una regola sola per un foglio che chiuderebbe il blocco

**Una funzione sola di `pages.py`, `closes_the_block`, dice se un testo chiuderebbe il blocco**:
contiene `</style` senza distinzione di maiuscole — più della regola esatta del parser, che vuole dopo
uno spazio, `/` o `>`, e la contiene. La usano l'avvio e `tests/design/test_inline_block.py`, con i
casi limite; nessuno la riscrive più larga «per prudenza» (correzione C). **All'avvio**,
`ensure_readable` si ferma su un foglio che manca o che chiude il blocco, con l'uscita 2; **non** a
ogni risposta, perché lì un rifiuto sarebbe un `500` sull'unica porta d'ingresso.

### 5. La pagina, vestita

Il modulo prende i componenti che il design system ha e che le altre pagine della stessa superficie
usano: `ela-title`, `ela-body` ed `ela-caption` per il testo; `ela-field` per ogni campo, nella sua
struttura — `label.ela-field__label` e `input.ela-field__input` legati da `for` e `id`, al posto di
`<p><label>…<br><input>` —; `ela-button ela-button--primary` per il bottone (decisione 10). Nessun
componente nuovo, nessun token nuovo. I nomi dei campi non cambiano, e le rotte d'arruolamento nemmeno.

### 6. La scelta precedente, riletta

**ADR 0043 §5** si legge con questa accanto in tre capoversi. «Un compositore solo» scrive la
politica letterale, `style-src 'self'`, anche per «il `401` che è il modulo di arruolamento»: quella
pagina ha adesso la politica di §2. «L'escape è per costruzione»: ciò che entra crudo sono i modelli,
i frammenti del design system **e i suoi due fogli**, dentro un blocco. E l'ultimo: la pagina di
arruolamento **non è più senza stile**. **ADR 0043 §10**, il vincolo dichiarato «La pagina di
arruolamento è senza identità visiva», è rivisto — la lista di M12.5 resta uguale alla sua, come vuole
il test che le confronta, e la riga «Stato:» di ADR 0043 lo dice. **ADR 0044 §4** si legge con questa
accanto: la politica non è più una costante sola, e `sheets` non ha più un default.

**Il criterio di M17.4** — «Niente JavaScript, e la stessa `Content-Security-Policy`» — non diventa
falso: M17.4 non cambia nessuna delle due politiche, e «la stessa» è quella che questo ADR lascia.

Servire i fogli a chi non è ancora nessuno **era un'esenzione**, e la scelta di M12.5 di non farlo era
giusta con le strade che aveva. Questa strada non la apre: nessuna rotta risponde a nessuno, e la
politica ammette solo ciò che ELA ha scritto.

## Alternative considerate

- **Una rotta anonima per i fogli.** La prima esenzione dal middleware: ADR 0037 §3 la esclude.
- **`'unsafe-inline'`.** Ammetterebbe qualunque stile in linea, anche uno che un giorno sfuggisse
  all'escape: la politica perderebbe metà di ciò per cui c'è.
- **Un `nonce`.** Un valore nuovo a ogni risposta, da generare e da tenere fuori dalla cache: un
  secondo meccanismo per ottenere ciò che l'hash dà con i byte che ELA ha già.
- **Blocco e hash calcolati all'avvio.** Nessun costo per risposta — la misura dice circa 70 µs —, ma
  una seconda copia dei fogli, che divergerebbe da quella servita alle pagine riconosciute se un
  foglio cambiasse mentre ELA gira.
- **Una politica sola per tutte le pagine**, con `'self'` e l'hash: ogni pagina ammetterebbe ciò che
  non porta.

## Conseguenze

- `ela.api.pages` ha `DESIGN_SYSTEM`, `Sheets` e `INSIDE`, `sheet_text`, `closes_the_block` e
  `inside_policy`; `page` vuole `sheets`; `ensure_readable` guarda i fogli. Le due superfici hanno
  `style.html`, e i due `enrol.html` i componenti del design system.
- Il modulo d'arruolamento e la pagina «rifiutata» portano i fogli dentro in ogni modo in cui ci si
  arriva: il middleware (`enrolment`, `_page_401`, `_not_from_ela`), le due rotte d'arruolamento
  (`_again`), e l'`_handler` degli errori di `api/app.py`.
- Il `401` passa da circa 830 byte a circa 82 KB: i byte dei due fogli, che ogni pagina riconosciuta
  scarica già a ogni apertura.
- Nessuna rotta nuova, nessun comando nuovo, nessuna regola di architettura nuova: la regola del
  blocco è del design system, e il suo test sta nella sua cartella.
