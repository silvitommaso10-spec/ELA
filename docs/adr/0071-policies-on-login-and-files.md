# 0071. Le policy di chi usa ELA arrivano al login e ai file dal browser

- **Stato:** **Accettata** il **2026-11-18**, con un commit suo (decisione 127 dell'ultimo blocco del branch
  `m13.15-le-policy-al-login-e-ai-file`): la prova a mano della sezione 34 di `docs/GETTING_STARTED.md`, con
  `scripts/prova_m13_15.py`, è passata a `fe776f4`, l'ultimo commit del branch su origin, con l'albero pulito ed ELA
  riavviata dal branch (`~/Downloads/prova-m13.15-20261118-183240.txt`: 56 PASSATI al primo giro, 0 FALLITI, 0 no, 0
  SALTATI). **Che cosa ha visto la mano: i passi 2–13 e 15.**
  - Le cinque sotto le loro policy, senza domanda: lo scaricamento e lo scaricamento come te (2, 3), il caricamento e il
    caricamento come te (5, 6), il login di Hacker News con la voce della policy (10).
  - Le domande che una policy non toglie, ciascuna con la sua ragione: un sito fuori (4, 7), un file fuori (7), una voce
    fuori (11). A tutte Tommaso ha detto no.
  - Il file con due nomi coperto dalla policy (8); il vault chiuso, che fa fallire lo step coperto con `vault.locked`
    (12); la vista delle policy della console (13); e alla fine nessuna policy viva (15).
  
  **Chi ha visto che cosa.** Tommaso ha guardato le anteprime dei passi 2, 5 e 9 e la console del 13; ogni policy è nata
  dopo il suo sì a «crei la policy?»; i no sono suoi; il vault l'ha aperto e chiuso lui; dal sito è uscito lui, e l'id
  della voce l'ha dato lui. Il testo dopo il login l'ha visto il verifier. Lo script ha fatto i passi meccanici.
  
  **Che cosa prova solo il test**: il resto delle regole — la seconda dimensione nei due versi, i rifiuti alla nascita
  con il loro codice, la spesa di ciò che riuscirebbe, l'id della voce che nessuna superficie mostra —, in
  `tests/api/test_policies_on_login_and_files.py`, `tests/tools/test_files_and_login_under_a_policy.py` e in questo
  test dei documenti.
  
  **Le prove che non sono passate restano scritte** in M13.15: quella del 2026-11-17, appesa al passo 3 (M13.9d,
  M13.13c), e quella del 2026-11-18 alle 18:23, ferma al passo 9 perché l'id incollato a mano non era quello della voce.
  ELA ha rifiutato la nascita con `vault.no_entry`, senza creare niente e senza mostrare l'id. **Le «Righe riviste» di
  questo ADR hanno il loro marchio** sulle righe «Stato:» di ADR 0062, 0063, 0066 e 0068.
- **Data:** 2026-11-17
- **Riferimenti spec:** §19, §29, §30, §33, §57, §59, §65
- **Milestone:** [M13.15](../milestones/M13.15.md)

## Contesto

ADR 0068 ha portato le policy di chi usa ELA alle azioni `HIGH` che dichiarano termini — `fs.write`, `browser.act`,
`browser.act_as_you` — e ha lasciato a M13.15 il login e le quattro capability dei file dal browser, che «chiedono a
ogni uso fino a M13.15» (ADR 0068, «Ciò che questo ADR dichiara e non risolve»). Il taglio era passato lì per quattro
ragioni: una **seconda dimensione nominata per valore** — il sito di un file, la voce del vault di un login —; un
caricamento e un login che funzionavano solo dopo una domanda, perché ciò che la domanda nominava arrivava al tool con il
sì (`named`, ADR 0065 §2); la finestra del login, la cui ragione scritta era che chi approva è presente; e il vault, che
apre sempre chi usa ELA. Questo ADR dice che cosa prende il posto del sì su quei cammini, **a voce alta**: ciò che un sì
garantiva e una policy non ha, e ciò che c'è al suo posto.

**Il livello non si abbassa**: le cinque restano `HIGH`; `CRITICAL` resta `DENY`; `terminal.run` resta fuori, ed è
[M13.16](../milestones/M13.16.md). Solo chi usa ELA crea e revoca una policy; ELA non ne crea, non ne allarga, non ne
revoca e non ne propone.

## Decisione

### 1. Le cinque dichiarano i termini

`row_of` le legge `APPROVAL_UNLESS_POLICY` (ADR 0068 §1). Gli elenchi — le capability che una policy copre, quelle che
chiedono a ogni uso, ciò che l'anteprima dice che una policy non copre mai — restano derivati: dopo M13.15 l'unica
capability che chiede a ogni uso è `terminal.run`, e nessuno lo scrive.

| Capability | Tetti | Mai coperti | Liberi | Rotta |
|---|---|---|---|---|
| `browser.login` | — | — | `path`, `username_field`, `password_field`, `click`, `expect_text`, `purpose` | — |
| `browser.download` | — | — | `path`, `overwrite`, `click`, `purpose` | — |
| `browser.download_as_you` | — | — | `path`, `overwrite`, `click`, `purpose` | — |
| `browser.upload` | — | — | `path`, `file_field`, `fill`, `click`, `expect_text`, `purpose` | — |
| `browser.upload_as_you` | — | — | `path`, `file_field`, `fill`, `click`, `expect_text`, `purpose` | — |

| Capability | Per valore | Solo sul Core |
|---|---|---|
| `browser.login` | `entry` | sì |
| `browser.download` | `site` | sì |
| `browser.download_as_you` | `site` | sì |
| `browser.upload` | `site` | sì |
| `browser.upload_as_you` | `site` | sì |

**Nessun argomento mai coperto**: i confini li sceglie chi crea la policy. `overwrite` libero vuol dire che una policy
copre anche una sostituzione, e resta un'asserzione sul mondo nei due versi (`fs.overwrite_mismatch`). **Solo sul
Core**: le quattro dei file per la ragione di `fs.write` — la cartella è del Core, e lo stesso percorso su un'altra
macchina è un altro file —; il login perché la voce è del vault del Core, e un nodo non ha un vault (ADR 0068 §7). Oggi
nessuna delle cinque viaggia, e l'executor le piazza sul Core: la dichiarazione non costa niente, e il giorno in cui il
browser arriva su un nodo ([M13.11](../milestones/M13.11.md)) una policy del Core non copre uno step lì.

Le parole, in inglese, con «you», mai un nome:

| Capability | `does` | `goes` | `together` |
|---|---|---|---|
| `browser.login` | «signs in to these sites with these entries of your vault: a window of ELA's browser comes up on the screen and takes the keyboard while it types, and you may be elsewhere» | «the password goes from your vault to the site; only you open the vault, and with it closed nothing is typed; a wrong password leaves the site a failed attempt» | «every one of these sites with every one of these entries» |
| `browser.download` | «downloads whatever these sites send into these folders, on the Core, in ELA's own empty browser, and replaces a file there when the plan says so» | «what arrives is chosen by the site, not by the plan, and ELA has not looked at it: it goes into these folders, and wherever your system copies them; a file written there may be one your system runs» | «every one of these folders with every one of these sites» |
| `browser.download_as_you` | «downloads whatever these sites send into these folders, on the Core, as you, in the browser that keeps your accounts, and replaces a file there when the plan says so» | «what arrives is chosen by the site, not by the plan, and ELA has not looked at it: it goes into these folders, and wherever your system copies them; a file written there may be one your system runs; where you are signed in, what arrives is your own content» | «every one of these folders with every one of these sites» |
| `browser.upload` | «gives these sites any file of these folders, in ELA's own empty browser: nobody looks at the file before it leaves» | «the content of the file leaves this machine for these sites, and is not taken back: a revocation stops only what comes after» | «every one of these folders with every one of these sites» |
| `browser.upload_as_you` | «gives these sites any file of these folders as you, in the browser that keeps your accounts: nobody looks at the file before it leaves» | «the content of the file leaves this machine for these sites in your name, and is not taken back: a revocation stops only what comes after» | «every one of these folders with every one of these sites» |

**`POLICY_VERSION` passa da `v0.4` a `v0.5`**: un Guardian che permette ciò che prima non poteva non è quello di prima.
Le righe vecchie dell'audit continuano a dire la loro.

### 2. La seconda dimensione, nominata per valore

`PolicyTerms` guadagna **`by_value: str | None = None`**: l'argomento che una policy nomina per valore accanto allo
scope. **Un termine**, perché cambia ciò che una policy copre, e **la quinta classe del mondo chiuso** di ADR 0062 §1:
ogni argomento dello schema sta in una sola fra i tetti, i mai coperti, i liberi, quelli con lo scope e quello per
valore. Il catalogo rifiuta un `by_value` che non è una `string`, uno su una capability il cui scope è una lista, e
`PolicyWords.together` — la frase del prodotto — senza `by_value`, o `by_value` senza `together`. `PolicyBounds`
guadagna **`values: tuple[str, ...] = ()`**, nella colonna `bounds`, che è JSON: **nessuna migrazione**, e una riga di
prima legge i valori vuoti e termini che non nominano niente per valore — le policy di prima continuano a coprire.

I controlli della nascita, nel loro ordine:

| # | Controllo | Che cosa deve essere vero |
|---|---|---|
| 1 | `CATALOGUE` | la capability è nel catalogo |
| 2 | `ADMITS` | nessuna ragione di `no_policy_for` |
| 3 | `SCOPE` | lo scope non è vuoto, ogni voce valida e nello scope registrato |
| 4 | `VALUES` | i valori dell'argomento per valore, e solo loro: almeno uno, ciascuno valido per il suo schema, nessuno due volte — nessuno per una capability che non nomina niente per valore |
| 5 | `LIMITS` | i tetti dichiarati, validi |
| 6 | `USES` | nessuno, o un intero da 1 in su |
| 7 | `DAYS` | i giorni, da 1 a 90 |

Il predicato, con il gap nuovo:

| # | Gap | Che cosa manca | La frase, per una policy `3f2a1b2c` |
|---|---|---|---|
| 1 | `REVOKED` | `revoked_at` c'è | «policy 3f2a1b2c was revoked on 2026-11-17» |
| 2 | `EXPIRED` | `expires_at <= now` | «policy 3f2a1b2c expired on 2026-11-18» |
| 3 | `EXHAUSTED` | gli usi hanno raggiunto `max_uses` | «policy 3f2a1b2c was used 1 of its 1 use», «… 5 of its 5 uses» |
| 4 | `TERMS` | i termini non sono quelli con cui è nata | come in ADR 0068 |
| 5 | `ELSEWHERE` | `on_the_core` e lo step non è sul Core | come in ADR 0068 |
| 6 | `SITE` | lo scope non copre il bersaglio | «a value of file is not among those of policy 3f2a1b2c» |
| 7 | `VALUE` | l'argomento per valore manca, o il suo valore non è fra quelli della policy | «a value of site is not among those of policy 3f2a1b2c» |
| 8 | `LIMIT` | come in ADR 0062 | come in ADR 0062 |
| 9 | `ARGUMENT` | come in ADR 0062, con l'argomento per valore fra gli ammessi | come in ADR 0062 |

**Una chiamata è coperta solo se tutte le sue dimensioni stanno nella policy**: lo scope e il valore. La policy copre il
**prodotto** — ogni cartella con ogni sito, ogni sito con ogni voce —, e l'anteprima lo dice con `together`. **La frase
di `VALUE` nomina l'argomento e mai un valore**: un id di una voce è del piano (ADR 0063 §9). È la stessa per una
chiamata senza l'argomento — solo `entry`, l'unico facoltativo —: il valore della chiamata, che non c'è, non è fra quelli
della policy.

### 3. La nascita: la «partirebbe» per luogo, con i valori

`ToolPort.prospect_place(place, values=())` — la firma di ADR 0068 §6, con i valori: «potrebbe partire adesso una
chiamata il cui bersaglio sta in questo luogo, con ciascuno di questi valori?». Un tool che non nomina niente per valore —
`fs.write`, i gesti — rifiuta un valore.

| Tool | `prospect_place(place, values)` |
|---|---|
| i quattro dei file | ogni sito fra `ELA_BROWSER_SITES` (`browser.site_not_declared`); il browser, e per i due «come te» il profilo; la cartella con **la funzione sola** che chiede anche `fs.write` — la radice; c'è, è una cartella (`fs.not_a_folder`), non un link, non fuori dalla radice; **nessun posto protetto, nei due versi**, anche per i due caricamenti (`path.ela_s_own`). La risposta porta la cartella come la nomina il disco del Core |
| `browser.login` | il profilo e la finestra, come prima di ogni domanda di un login; poi, **per ogni voce**, `find` per l'indirizzo del sito — la lista chiusa dei comandi del vault non cambia, e nessuna password lascia l'adapter —: un id che il vault non trova per quel sito è `vault.no_entry` o `vault.entry_not_for_site`, e un vault chiuso o un programma che manca rifiutano con i loro codici. **Il vault lo apre chi usa ELA**: a vault chiuso nessuna policy di login nasce. La risposta porta, per ogni voce, **il nome e il nome utente mascherato** (`Prospect.entries`), mai l'id |

**I due caricamenti avevano già una `prospect_place`, ereditata da un gesto**, che guardava solo il browser: il giorno
in cui avessero dichiarato termini, una policy di caricamento sarebbe nata su qualunque cartella. Ne hanno una loro.
**Il prodotto alla nascita del login**: ogni coppia sito × voce deve essere trovata; una voce di un sito solo, in una
policy di due siti, non nasce. **L'id si salva come lo nomina il vault**: il confronto è per uguaglianza.

**Ciò che la nascita ha mostrato si salva con la policy**, nei metadati del grant — le cartelle risolte, e i valori come
una superficie li può mostrare: un sito com'è, una voce con il suo nome e il nome utente mascherato. Parole, non termini:
una voce rinominata nel vault non revoca niente, e le viste dicono ciò che è stato approvato. Vale per ogni policy che
nasce da M13.15 in poi **il cui scope è un valore per chiamata** — `fs.write`, i gesti, il login e le quattro —; una
policy di sessione guidata, il cui scope sono i siti di una sessione, non ha una cartella da risolvere né una seconda
dimensione e non salva niente, come una policy di prima: le viste dicono «—».

### 4. I caricamenti sotto una policy

**Ciò che il sì garantiva, e sotto una policy non c'è.** Un sì a un caricamento garantiva (a) che chi approva legga il
file, risolto, e che cosa gli succede; (b) la dimensione e lo sha256 del file com'è quando la domanda è composta, mostrati
a chi dice sì (ADR 0066 §5); (c) la rilettura dopo il sì, e `browser.file_changed` se non tornano (ADR 0066 §6); (d) il
sito, e che cosa fa il sì su quel sito. **Sotto una policy niente di questo c'è: nessuno guarda il file prima che esca,
e non c'è una dimensione né uno sha256 «della domanda» con cui confrontare.** `browser.file_changed` non ha un termine di
confronto su questo cammino, e non nasce lì.

**Che cosa prende il loro posto:**

1. **La cartella e il sito**, scelti alla nascita, con la cartella intera sul disco del Core accanto alla voce scritta;
   l'anteprima dice «dalla cartella al sito», che qualunque file di quelle cartelle può uscire verso quei siti, che il
   contenuto esce da questa macchina, e che ciò che è uscito non si riprende.
2. **La lettura unica all'uso**: il file si legge una volta, regolare, mai attraverso un link, **al più 50 MiB e un byte**
   — di più è `browser.file_too_large`: il file può crescere fra lo sguardo al disco e la lettura —; regolare e con un
   nome solo si afferma **sul descrittore che legge**, con `fstat`. I byte dati alla pagina sono **esattamente** quelli
   letti, e il risultato ne dice la dimensione e lo sha256, nelle chiavi `size` e `digest` — anche sotto un sì: una forma
   sola del risultato, che dice ciò che è uscito, e niente se niente è stato dato. **Mai nell'audit**: i numeri
   dell'audit restano `gestures`, `status`, `stopped_at` (ADR 0066 §5). **Nessun cammino porta il risultato di un
   caricamento a un fornitore del modello** (§57): non è un gesto di nessuna sessione, e il Planner legge solo il risultato
   della sua chiamata al modello.
3. **La «partirebbe» prima della spesa, senza leggere un byte** (ADR 0068 §6): **`ToolPort.prospect_covered(arguments,
   task)`**, la prospettiva di una chiamata che una policy copre, senza ciò che serve solo a una domanda. Il default di
   `Tool` è la sua `prospect`; i due caricamenti la riscrivono, con **la stessa funzione** dei controlli della domanda —
   la forma, il sito, il browser, la radice, la classificazione, i posti protetti, i nomi, la dimensione chiesta al disco
   —: lo stesso codice per lo stesso rifiuto, sui due cammini. L'executor la chiede prima del `consume`.
4. **I posti protetti e i file con più nomi anche in lettura**, alla nascita e a ogni uso: `path.ela_s_own`, con il
   confronto `_within` nei due versi, sotto un sì e sotto una policy — ADR 0068 §7 lo diceva di chi scrive —; e
   `path.hard_link`, anche sotto un sì: chi approva legge un percorso che non dice l'altro nome.
5. **Il cancello di ADR 0066 §7, invariato**: dall'istante prima che il file sia dato, ogni richiesta della pagina fuori
   dal confine fallisce. **È una garanzia dopo, non prima.**

**Come il tool sa che è sotto una policy.** Il Guardian scrive nella decisione **`approval_id`**, copiato dal grant —
l'invariante del dominio lega un sì alla sua approvazione —; una decisione con `authorization_id` e senza `approval_id`
poggia su una policy, e **solo lei** prende il cammino della lettura unica. Ogni altro caso — un sì, la parola di una
sessione, una decisione senza grant — prende il cammino del sì, che senza ciò che la sua domanda ha nominato rifiuta:
l'errore ricade sul lato sicuro.

**Il difetto C, con la data.** *Trovato il 2026-11-17 dal censimento della SPEC di M13.15*: un caricamento giudicava il
file con la sola radice e la classificazione, non riceveva la lista dei posti protetti e non guardava i nomi di un file —
**un file con due nomi, uno dentro la radice e uno fuori, componeva la domanda** con i byte dell'altro nome. Rosso prima
del fix (`tests/tools/test_files_and_login_under_a_policy.py`), riparato qui. **Lo stesso difetto in `fs.read`**, trovato
lo stesso giorno con la stessa precondizione (risposta 36 della review della SPEC): **riparato con la stessa funzione**,
`looked_for_a_read`, che `fs.read` e i caricamenti chiamano; `fs.read` riceve la lista come la ricevono le scritture — sul
Core `Settings.ela_s_own()`, su un nodo la lista del nodo.

I codici che i tool aggiungono a quelli che gli ADR di prima scrivono:

| Tool | Codici aggiunti |
|---|---|
| `browser.upload` | `path.ela_s_own`, `path.hard_link` |
| `browser.upload_as_you` | `path.ela_s_own`, `path.hard_link` |
| `fs.read` | `path.ela_s_own`, `path.hard_link` |

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ToolPort` | §59 | async | `prospect_covered` |

### 5. Gli scaricamenti sotto una policy

Si giudicano come `fs.write` (ADR 0066 §4), e il cammino di ADR 0068 funziona già: la loro «partirebbe» non legge niente
oltre il disco, e il loro tool non usa ciò che una domanda ha nominato. Restano `overwrite` come asserzione nei due versi,
`path.ela_s_own`, `path.hard_link`, il file `600`, e la porta di ADR 0070. **L'anteprima dice ciò che è diverso da
`fs.write`**: il contenuto lo sceglie il sito, non il piano, ed ELA non l'ha visto; e «a file written there may be one
your system runs» vale a maggior ragione. **Nessuna lista dei posti che il sistema lancia** (ADR 0068, «Alternative»).

### 6. Il login sotto una policy

**Ciò che il sì garantiva, e sotto una policy non c'è.** (a) Che chi approva sia **presente** — la ragione scritta della
finestra, ADR 0063 §5: «chi approva è presente, perché il login chiede a ogni uso»; (b) quale voce e di chi, in `entry` e
`username` mascherato (ADR 0063 §9); (c) che la voce sia quella che la domanda ha nominato, con `named` (ADR 0065 §2); (d)
un uso per sì. **Sotto una policy la presenza non c'è più: la frase «chi approva è presente» di ADR 0063 §5 è falsa su
questo cammino**, e questo ADR la rivede.

**Che cosa prende il loro posto:**

1. **La finestra resta, sempre**: nessun cammino del login parte senza (`browser.no_window`). **La sua ragione si
   riscrive**: non «chi approva è presente», ma il fatto misurato su un sito solo che un sito può rifiutare un browser
   senza finestra, e che un login che fallisce lascia al sito un tentativo sbagliato (ADR 0063 §5, decisione 143). **Non è
   un termine della policy**: un login «senza finestra» sarebbe un login che ELA sa già che può fallire. L'anteprima dice
   che una finestra compare e prende la tastiera, e che chi usa ELA può essere altrove.
2. **La voce, nominata per id** nella policy accanto al sito, e mostrata alla nascita con il suo nome e il nome utente
   mascherato.
3. **La chiamata porta `entry`, sempre**: senza, o con una voce che la policy non nomina, **chiede** (`VALUE`), con il
   cammino di oggi. Su questo cammino il tool legge la voce che il piano nomina — lo faceva già —, e
   `vault.entry_not_named` non può nascere. Il login figlio di una sessione guidata non porta `entry`: chiede sempre.
4. **Il vault lo apre sempre chi usa ELA**: nessuna policy copre l'apertura; a vault chiuso un login coperto non scrive
   niente, non spende un uso e fallisce `vault.locked` prima della spesa.
5. **Gli usi, se ci sono, e una scadenza sempre.**
6. **Il resto di ADR 0063 §5 com'è**: `browser.field_changed`, `browser.no_window` nel dubbio, la fermata ascoltata prima
   che il vault sia interrogato, il secondo fattore a mano, `ended_at` ed `ended_status`.

**Lo schermo bloccato — NON MISURATO.** La sonda della percezione legge già `screen_locked` nella famiglia della
sessione, e la domanda della finestra guarda solo che una sessione ci sia, bloccata o no. Misurato da dentro una sessione
sbloccata il 2026-11-17: `screen_locked` falso. Il caso bloccato non si costruisce senza bloccare lo schermo vero, e
**non si aggiunge nessun limite**: chi usa ELA ha deciso che ELA non impone confini più stretti di quelli che sceglie
(STATO, 5.14 (e)).

### 7. La spesa di ciò che riuscirebbe

Quando il Guardian permette su una policy, l'executor chiede al tool `prospect_covered` **prima del `consume`**; un
rifiuto chiude lo step con il codice del tool, senza uso speso, senza tool, senza una password data a una pagina, senza un
byte consegnato. Sotto un sì la domanda di oggi, con lo stesso codice dalla `prospect`: nessuna domanda per ciò che non
riuscirebbe.

| Rifiuto | Di chi |
|---|---|
| `arguments.invalid`, `browser.not_installed`, `browser.unsupported_system` | tutte e cinque |
| `browser.site_not_declared` | le quattro dei file |
| `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.profile_busy` | i tre «come te» |
| `fs.no_root`, `path.invalid`, `path.outside_root`, `path.symlink`, `path.is_directory`, `path.ela_s_own`, `path.hard_link` | le quattro dei file |
| `fs.overwrite_mismatch` | i due scaricamenti |
| `path.missing`, `browser.file_too_large` | i due caricamenti |
| `browser.no_window`, `vault.undeclared`, `vault.no_program`, `vault.program_gone`, `vault.program_changed`, `vault.program_is_a_script`, `vault.locked`, `vault.unauthenticated`, `vault.timeout`, `vault.failed`, `vault.no_entry`, `vault.entry_not_for_site`, `vault.no_password` | il login |

### 8. Un consenso non si eredita

Una policy di `browser.download` non copre `browser.download_as_you`, né il contrario; lo stesso per i due caricamenti;
nessuna delle cinque è coperta da una policy di `browser.act`, `browser.act_as_you`, `browser.guided` o
`browser.guided_as_you`, né il contrario (ADR 0034, ADR 0068 §8). Lo garantisce la scelta per capability, e il Guardian
nega una policy consegnata per un'altra.

### 9. Le superfici

**L'anteprima**, nell'ordine di ADR 0068 §9 — anche nella console, che metteva la scadenza prima degli usi —: il
livello; `does`; `goes`; lo scope con la cartella risolta; i valori — i siti, o le voci con nome e nome utente mascherato
—; il prodotto; i tetti; gli usi; la scadenza **con la data**; il Core; ciò che non copre mai. **`PolicyOut`** guadagna
`goes`, `resolved`, `by_value` e `values` — ciò che la nascita ha mostrato —; la console li mostra tutti, `goes` come
«Dove va» accanto a ciò che la policy fa, ed `ela policy list` le cartelle risolte e i valori, con `goes` nell'anteprima
e nel `--json`. **Nella CLI** `--site` e `--entry`, ripetibili; **nella console** le caselle dei siti dichiarati, o il campo
«Id della voce», che l'`input` nascosto fra l'anteprima e la creazione riporta alla stessa console: è il campo di
creazione, in una pagina `no-store`.

**L'id di una voce non si mostra mai sulle superfici delle policy**: né in una risposta delle rotte `/policies`, né in
un'uscita di `ela policy`, né nel testo della console, né in una frase di rifiuto — anche dove un `422` potrebbe ripetere
ciò che ha ricevuto —, né nell'audit. Il piano di un login coperto lo porta, e quello è del piano (sotto, «Ciò che questo
ADR dichiara e non risolve»).
**L'audit della nascita** porta lo scope e, per i file, i siti; per il login **quante voci**, né l'id né il nome.
Nessuna rotta serializza un grant intero. **Dichiarato**: l'id passato con `--entry` sta un istante nella riga di comando
della macchina di chi la lancia, e non è una credenziale.

### 10. I quattro punti di M13.14 e M9.5

1. **La frase sola della domanda nomina la policy finita per ultima.** Fra le policy che coprirebbero la chiamata, nessuna
   usabile, l'executor consegna quella il cui istante di fine è il più recente. **L'istante si deriva dai dati**: il primo
   fra la revoca, la scadenza se è passata, e l'istante dell'ultimo uso se gli usi sono finiti — il suo ultimo
   `TOOL_EXECUTED` nell'audit, o il suo `created_at` se non ne ha: **l'istante più vicino che i dati danno** (uno spreco
   senza un evento del tool — il tetto del mese, un tool che rifiuta la decisione — non lascia un istante). Le righe «why
   I ask» le dicono tutte.
2. **La revoca dice che cosa continua solo per una sessione**, derivato dalla dichiarazione: la frase della sessione per
   una policy che nomina una rotta del modello, quella delle letture per una che dichiara che cosa `covers`. Le letture di
   `browser.guided` sono `browser.read`, `LOW`, e non le copre niente.
3. **Il singolare si decide in un posto solo**, `noun` in `ela.domain`, che `amount` legge — «at most 1 use», «in 1
   day», «1 giorno», «1 rimasto», «was used 1 of its 1 use» —, e così il telefono. Gli altri plurali scritti a mano fuori
   dalle policy restano elencati nella SPEC.
4. **Lo scaricamento interrotto non ha un passo della prova**: `httpbin.org` rifiuta ogni durata sopra i 10 secondi — un
   `400` in JSON, che il browser apre come una pagina, e per il tool è `browser.download_not_started` —, e nessun sito
   dichiarato tiene uno scaricamento oltre i 30 secondi del tool. L'interruzione la provano i test di ADR 0070.

### Ciò che questo ADR dichiara e non risolve

In parole semplici:

- **Le tre strade di ADR 0068** restano: il limite «ELA non crea policy da sola» è vero quanto le cartelle, i siti e le
  voci scelti.
- **Un login sotto una policy entra in un account senza che chi usa ELA sia davanti**; la frase di ADR 0063 §5 si legge
  con questa accanto.
- **Nessuno guarda il file prima che esca**: i caricamenti sotto una policy non hanno una dimensione né uno sha256 «della
  domanda» con cui confrontare; **un file che esce non si riprende**, e una revoca ferma solo ciò che viene dopo.
- **Due policy — uno scaricamento in una cartella da un sito, un caricamento dalla stessa cartella verso un altro —
  spostano un contenuto fra due siti senza che nessuno lo guardi**, anche un contenuto che un sito ha scelto.
- **Il file che un sito ha scelto** può stare in una cartella da cui il sistema lo lancia.
- **Una password sbagliata, o una voce cambiata nel vault dopo la nascita**, lascia al sito un tentativo sbagliato: la
  policy nomina la voce, non l'account che la voce tiene oggi.
- **Gli usi contano le spese, non gli effetti** (ADR 0062 §2).
- **Lo schermo bloccato non è misurato** (§6).
- **Il piano di un login coperto porta l'id della voce** in `entry` (§6): l'id è del piano (ADR 0063 §9), e
  `ela task show` e `GET /tasks/{id}` mostrano gli argomenti di uno step, l'id compreso, come per ogni login con `entry`
  da M13.9. Le superfici delle policy non lo mostrano (§9); il file della prova lo maschera (`scripts/prova_m13_15.py`).
- **Ciò che ADR 0070 §2 e §4 dichiarano**: il browser annuncia uno scaricamento prima di scriverlo; la chiusura di 30
  secondi del browser del profilo con uno scaricamento in corso, passata a M13.11.
- **La finestra fra lo sguardo al percorso e l'`open`** resta quella di `ela/tools/fs.py`, per un posto protetto; per un
  secondo nome il descrittore la chiude.

## Alternative

- **La finestra del login come termine della policy**: un login che ELA sa già che può fallire.
- **Un limite per lo schermo bloccato**: un confine più stretto di quelli che sceglie chi usa ELA.
- **L'id della voce nel campo `scope`**, con ogni strada che lo legge che impara a toglierlo: sei posti da tenere, e uno
  dimenticato è un id su una superficie.
- **Un segno in `named`, o una chiave nei metadati della decisione**, per dire al tool che è sotto una policy: il campo
  del dominio c'era, e la decisione è il documento del Guardian.
- **Un parametro di `prospect`** al posto di `prospect_covered`: la firma di ogni tool.
- **La rilettura dopo la spesa con un confronto sulla prima lettura**: due letture, e un termine di confronto che nessuno
  ha guardato.

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0062** §1, §3, §4, §7 — la quinta classe del mondo chiuso, `by_value`; `PolicyRequest` con i valori e il controllo `VALUES`; il gap `VALUE`; la «partirebbe» con i valori (§2, §3).
- **ADR 0063** §2, §5, §9 — sotto una policy il sì è la spesa: prima della spesa nessuna password lascia l'adapter, e
  dopo la voce si legge una volta sola; la ragione della finestra, «chi approva è presente», falsa sotto una policy; «la domanda lo dice … e in nessun altro posto»: lo dice anche l'anteprima di una policy di login; e l'id della voce, che riceve anche il campo di creazione di una policy, e che nessuna superficie mostra (§6, §9).
- **ADR 0066** §4, §5, §6 — le quattro chiedono a ogni uso salvo una policy loro; sotto una policy un caricamento legge una volta, senza una domanda che fissi dimensione e sha256, e il risultato le dice; i posti protetti e i file con più nomi anche in lettura (§4).
- **ADR 0068** §2, §5, §6, §7, §9 e «Ciò che questo ADR dichiara e non risolve» — l'esempio del login senza termini;
  la frase di `EXHAUSTED` e del `409`, «… of its 5 uses», e il gap `VALUE`, che la tabella del suo giorno non ha; la
  firma di `prospect_place`; la lista dei posti va anche a chi legge; l'ordine dell'anteprima, con i valori e il
  prodotto; «il login e le quattro capability dei file chiedono a ogni uso fino a M13.15», che M13.15 compie (§1, §2,
  §3, §4, §9, §10).

Le altre conseguenze:

- **Il dominio**: `PolicyTerms.by_value`, `PolicyWords.together`, `PolicyBounds.values`, `amount` e `noun`.
- **I port**: `ToolPort` guadagna `prospect_covered`, e `prospect_place` riceve i valori; `Prospect` guadagna `entries`.
- **Nessuna migrazione**: `by_value` e `values` hanno il loro default, e `bounds` è JSON.

Con questo ADR le regole di architettura restano **settantaquattro**, i contratti di import-linter **sedici**, i port
**trentasei**, le rotte dell'API **settantadue**, i comandi della CLI **trentanove**, le capability **ventidue**, le
identità del middleware **sei**.
