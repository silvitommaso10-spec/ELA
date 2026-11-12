# 0066. I file dal browser, e la pagina del browser che non è un sito

- **Stato:** Accettata il **2026-11-11**, con un commit suo: la prova a mano — la sezione 30 di
  `docs/GETTING_STARTED.md`, con `scripts/prova_m13_13.py` — è passata sul Mac, sul branch e prima del merge, a
  `ead73aa`, l'ultimo commit del branch su `origin`, con l'albero pulito (`~/Downloads/prova-m13.13-20261111-124909.txt`:
  42 PASSATI, tutti al primo giro, 0 FALLITI, 0 GUARDATI con un no, 0 SALTATI — decisione 51 di
  `docs/milestones/M13.13.md`). **Che cosa la prova ha visto, e chi l'ha visto, scritto com'è**: la conferma del sito,
  «Upload successful!», ai passi 5 e 6 l'ha vista il verifier `browser.expect_visible`, perché lo step è COMPLETED; il
  file della prova riporta l'esito, non il testo. Le due domande che la prova mette all'occhio, ai passi 2 e 5 — quella
  di `browser.download`, con il percorso intero del file, che lo crea, e il sito; quella di `browser.upload`, con il
  percorso intero, la dimensione, l'impronta e il sito —, Tommaso le ha guardate sullo schermo, e la risposta è stata
  sì; le altre domande della prova le ha confrontate lo script con l'API e con il disco. **Le «Righe riviste» che
  questo ADR porta sono già scritte**, ciascuna con il suo marchio sulla riga «Stato:» dell'ADR che rivede — ADR 0047,
  ADR 0052, ADR 0063, ADR 0064 —; quella di ADR 0065 §6 si scrive alla fine del branch, con l'esito del debito
  (decisioni 44 e 52). Proposta il **2026-11-03**, con l'implementazione del branch `m13.13-i-file-dal-browser` —
  M13.9b, M13.9c, M13.10b e M13.13 —, per diventare Accettata con un commit suo quando quella prova fosse passata
  sull'ultimo commit del branch (decisione 11 del branch). *`ead73aa` era l'ultimo commit del branch quando la prova è
  girata: dopo, per la decisione 50, il branch porta solo `docs/`, `tests/` e `scripts/generate_stato.py`, che né `src/`
  né gli script della prova importano (decisione 43) — niente di ciò che la prova esercita.*
  ***Annotato il 2026-11-11, più tardi*** (decisione 52): **§10, il debito di ADR 0065 §6 ridichiarato a carico di
  M13.11**, con il conto chiuso a sei giri su otto, è scritto dopo l'accettazione, nel commit che scrive l'esito; con lui
  la riga rivista di ADR 0065 §6, in «Righe riviste», e il suo marchio sulla riga «Stato:» di ADR 0065 (decisione 44).
  **Rivista da ADR 0068 (M13.14)** il 2026-11-12: §4 — le quattro capability dei file chiedono a ogni uso fino a M13.15, non più «fino a M13.14» (ADR 0068).
- **Data:** 2026-11-03
- **Riferimenti spec:** §19, §33, §57, §58, §65
- **Milestone:** [M13.13](../milestones/M13.13.md), con [M13.9b](../milestones/M13.9b.md),
  [M13.9c](../milestones/M13.9c.md) e [M13.10b](../milestones/M13.10b.md)

## Contesto

L'ADR del branch che porta i file nel browser di ELA, e le tre riparazioni che vengono prima di loro sullo stesso
branch. Le decisioni — il prompt di Tommaso del 2026-11-02 (1–14) e la review delle SPEC a `5808ae5` (15–24) —, le
regole scritte prima dei numeri e le misure stanno nei documenti delle milestone; le sonde e le loro uscite in
`.git/m13.13-reference/`. Questo ADR cresce con il branch: una sezione per ciò che ciascun pezzo decide.

## Decisione

### 1. La pagina d'errore del browser è dove il browser ha provato ad andare (M13.9b)

Quando un sito prende una richiesta e non risponde, il browser mostra una pagina sua,
`chrome-error://chromewebdata/`, e il suo protocollo porta per la cornice principale **l'indirizzo che ha provato a
raggiungere**, `unreachableUrl`. Misurato il 2026-11-02 sui due browser: in 50 giri su 50 di pagina d'errore con
l'indirizzo chiesto, anche per un indirizzo di un altro sito; in 20 giri su 20 di `about:blank` e di un `blob:` niente;
e un rifiuto del cancello non fa nessuna pagina d'errore — la navigazione non parte e la pagina resta dov'era.

**Il predicato di ADR 0064 §4 chiede al confine dove il browser ha provato ad andare**, quando la pagina è la sua:
`ela.ports.tried`, una funzione sola per gli adapter e per ogni finto del port. Una pagina di un sito è dov'è e non costa
niente in più; una pagina a nessun sito costa una chiamata, `Page.getFrameTree` sulla sessione della pagina che il
cancello tiene, e **un browser che non sa dire dov'è la sua pagina ha fallito** (`BrowserFailed`): nel dubbio della pagina
non si dice niente. Lo stesso indirizzo è quello che l'adapter dice: all'apertura, alla ripresa, in `where` e in
`landed`.

- **Dentro il confine** il sito non ha risposto: nessuno stato, all'indirizzo chiesto. **La diagnosi sta nel
  risultato** (risposta 16): il membro nuovo del port `unanswered` dice l'indirizzo a cui il sito non ha risposto, lo
  dicono `Landed` e lo sguardo del verifier (`Glanced.unanswered`), e il risultato di un gesto e del login porta la
  chiave `unanswered`, con il luogo di quell'indirizzo. **Il verifier** di una lettura, di un gesto e del login, che
  nello sguardo trova la pagina del browser, fallisce con il codice della sua condizione — `browser.text_mismatch`,
  `browser.expect_missing`, e `browser.http_status` per il modulo del login che non c'è più —, e la sua frase dice che
  il testo è del browser, con la sola origine: anche quando il testo che il piano aspetta è su quella pagina.
- **Fuori dal confine** la pagina è di un altro sito: `browser.left_site`, con l'origine che il browser ha provato,
  non più `chrome-error://`.
- **`about:blank` e un `blob:` restano fuori da ogni confine**: non portano un indirizzo non raggiunto.

### 2. `landed` aspetta la fine della navigazione che il click ha avviato (M13.9b)

`AccountChrome.landed` diceva che il click aveva già aspettato la navigazione che aveva avviato — misurato il
2026-10-12 con un sito che risponde piano —, e leggeva l'indirizzo dopo `domcontentloaded`. **Per un `POST` che fallisce
non è vero**: il click torna prima che il browser mostri la sua pagina (10 giri su 10 il 2026-11-03), e `landed` leggeva
la pagina del modulo. Il test di M13.9 era verde quando lo leggeva — l'indirizzo del modulo coincideva con quello del
`POST` — e rosso con `chrome-error://` quando leggeva la pagina d'errore: verde per due ragioni diverse.

**Ora `landed` aspetta la fine della navigazione che il click ha avviato**, impegnata o fallita, senza un tempo suo:
quello del tool. La misura del 2026-11-03, sui due browser e otto casi, con la regola scritta prima dei numeri:
`Page.frameRequestedNavigation` della cornice principale arriva **prima che il click torni** in 60 navigazioni su 60, e
in nessuno dei 20 giri senza una navigazione — un click che non naviga, un'ancora della stessa pagina —; e
`Page.frameStoppedLoading` della cornice principale dice **la fine** in 60 su 60, con l'indirizzo già finale. L'adapter
le ascolta sulla sessione della pagina che il cancello tiene: un click che fa nascere una richiesta di navigazione prima di
tornare ha avviato una navigazione, e `landed` ne aspetta la fine; **un click che non ne fa nascere nessuna non aspetta
niente**.

### 3. Solo l'adapter del vault lancia il programma del vault (M13.9c)

L'adapter del vault lancia il suo programma con una lista chiusa di comandi (ADR 0063 §2). Un programma del terminale è
lanciato con gli argomenti di un piano (ADR 0047): **dichiarato anche lì, il programma del vault partirebbe con argomenti
che la lista chiusa non conosce**, e niente lo escludeva (censimento del 2026-11-02). La risposta 18 della review delle
SPEC lo dà a una riparazione sua, con la sua lettera.

**Il controllo è in due punti, e non dicono la stessa cosa.**

- **All'avvio**, una configurazione in cui il programma del vault è anche un programma del terminale **non avvia ELA**,
  e la frase nomina `ELA_VAULT_PROGRAM` ed `ELA_TERMINAL_PROGRAMS` (`refuse_the_vault_program` in
  `ela.composition.settings`). È il rifiuto di una configurazione che oggi si vede sbagliata.
- **Al lancio**, la tabella dei programmi del terminale — `ela.tools.programs.Programs`, a cui la composizione consegna
  il programma del vault — chiede **ogni volta che un lancio si decide**, quando la domanda è composta e di nuovo
  subito prima del lancio, se il programma, **risolto in quell'istante**, è il programma del vault: il comando è
  rifiutato con `terminal.vault_program`, prima della domanda quando si può e comunque prima del lancio. Lo dice anche
  il verifier, che legge la stessa tabella dopo la corsa.

*Perché due* (decisione 28 della review dopo la CI rossa di `56c672c`): **il controllo dell'avvio è una credenza sul
lancio, e una credenza non decide un'azione.** Un programma che all'avvio non c'è non si può confrontare per identità, e
ciò a cui un percorso porta cambia dopo. Misurato il 2026-11-10 sul codice di prima: il programma del vault nato dopo
l'avvio come secondo nome di un programma del terminale — che per la tabella non era cambiato: lo stesso file, lo
stesso contenuto — **era lanciato**; un programma del terminale assente all'avvio che diventa un secondo nome del
programma del vault era già rifiutato, come `terminal.program_changed`, ed è ora detto per ciò che è.

**Per identità e non per nome**, nei due punti con la stessa funzione, `ela.tools.programs.same_program`: lo stesso
percorso risolto — un link porta dove porta —, o lo stesso file — lo stesso dispositivo e lo stesso inode, un suo
secondo nome —. Un programma che non c'è è lo stesso solo per il percorso risolto.

- **Regola di architettura 72** (`the-vault-s-program-is-its-adapter-s`): il campo `vault_program` lo nominano solo le
  impostazioni, che lo dichiarano e lo controllano, e la composizione, che lo consegna **all'adapter del vault**, che
  lo lancia, **alla sua porta**, che ne fissa l'identità e non lancia niente — un tool non lancia processi (regola
  32) —, **e alla tabella dei programmi del terminale, che lo riceve per rifiutarlo**; a nessun altro. *Dove la review
  non diceva*: «solo l'adapter del vault riceve e lancia `ELA_VAULT_PROGRAM`» — lo *lancia* solo l'adapter; la porta
  lo riceve da M13.9, e la tabella del terminale dalla decisione 28. La regola nomina i tre per classe e costruttore.

Un ADR accettato non si riscrive: le righe del tool e del verifier di `terminal.run` in ADR 0047, che guadagnano il
codice nuovo, si riscrivono qui **per intero**, e la riga riscritta vince (la forma di ADR 0065 §1).

Righe dei tool, riscritte:

| Capability | Tool | Nome | Idempotente | Codici d'errore | Numeri nell'audit |
|---|---|---|---|---|---|
| `terminal.run` | `TerminalRunTool` | `terminal-run` | no | `arguments.invalid`, `fs.no_root`, `path.invalid`, `path.missing`, `path.outside_root`, `path.symlink`, `path.unreachable`, `terminal.arguments_unpassable`, `terminal.cwd_not_a_folder`, `terminal.no_program`, `terminal.not_declared`, `terminal.not_started`, `terminal.program_changed`, `terminal.program_gone`, `terminal.stopped`, `terminal.timeout`, `terminal.vault_program` | `argument_count`, `exit_code`, `signal`, `stderr.shown`, `stderr.total`, `stdout.shown`, `stdout.total` |

Righe dei verifier, riscritte:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `terminal.run` | `TerminalRunVerifier` | `terminal-run-verifier` | `terminal.exit_code_matches`, `terminal.output_whole`, `terminal.program_unchanged` | `terminal.exit_code_mismatch`, `terminal.no_program`, `terminal.not_declared`, `terminal.output_incomplete`, `terminal.program_changed`, `terminal.program_gone`, `terminal.vault_program` |

### 4. Quattro capability, e lo scope è il file (M13.13)

`browser.download` e `browser.upload` sul browser vuoto di ELA, `browser.download_as_you` e `browser.upload_as_you` sul
browser con gli account: capability loro, perché un consenso non si eredita (ADR 0034). Tutte `HIGH`: chiedono a ogni
uso, e nessuna policy le copre fino a M13.14. Nessuna viaggia, nessuna continua una pagina, nessuna ne lascia una allo
step dopo.

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `browser.download` | HIGH | `undeclared` | `file` | sì | `site: string`, `path: string`, `file: string`, `overwrite: boolean`, `purpose: string` | `click: string` |
| `browser.download_as_you` | HIGH | `undeclared` | `file` | sì | `site: string`, `path: string`, `file: string`, `overwrite: boolean`, `purpose: string` | `click: string` |
| `browser.upload` | HIGH | `undeclared` | `file` | sì | `site: string`, `path: string`, `file: string`, `file_field: string`, `expect_text: string`, `purpose: string` | `fill: array`, `click: string` |
| `browser.upload_as_you` | HIGH | `undeclared` | `file` | sì | `site: string`, `path: string`, `file: string`, `file_field: string`, `expect_text: string`, `purpose: string` | `fill: array`, `click: string` |

**Uno scaricamento è giudicato come un `fs.write`, un caricamento come un `fs.read`.** Una capability ha uno scope
solo, e il loro è `ELA_FS_SCOPE` su `file`: un file fuori dallo scope lo nega il Guardian, come per `fs.*`. Quindi
**il sito è il confine del tool**: un sito non dichiarato in `ELA_BROWSER_SITES` lo rifiuta il tool, prima della
domanda, con `browser.site_not_declared` — dove per ogni altro `browser.*` è un `DENIED` del Guardian.

**Tutto ciò che si può rifiutare prima della domanda si rifiuta lì**, senza spendere un sì (ADR 0045 §6-bis), in
quest'ordine: la forma (`arguments.invalid`); il sito; il browser e il profilo, come per gli altri tool del browser;
la radice (`fs.no_root`); il file, con la classificazione che `fs` condivide. Per uno scaricamento ciò che `fs.write`
rifiuta, con `overwrite` come asserzione sul mondo nei due versi (`fs.overwrite_mismatch`); per un caricamento ciò che
`fs.read` rifiuta, il file che manca compreso. *«Ciò che `fs.read` rifiuta» sono la sua radice e la sua
classificazione* (risposta 19): il rifiuto del testo che non è UTF-8 resta suo, perché è il testo che `fs.read` mette in
un risultato, e i byte di un caricamento non entrano in nessun risultato. **Un PDF si carica.** I codici sono quelli di
`fs`, chiesti a `fs` dai test sullo stesso disco: un percorso con `..` è `path.invalid`, e un link che porta fuori dalla
radice è `path.outside_root`.

`click` è facoltativo nei due schemi: senza, per uno scaricamento l'indirizzo **è** il file; per un caricamento la
pagina è una che carica da sé quando il file le è dato (risposta 22).

### 5. La domanda nomina il file, e il sito ha campi suoi (M13.13)

Il bersaglio della domanda resta **il file, risolto, con ciò che gli succede** — crea, sostituisce, è letto e dato al
sito —, come per `fs.*`. Il sito non è un secondo bersaglio: ha quattro campi suoi, tenuti a mondo chiuso sulle tre
superfici che rispondono, come `entry` e `username` di un login (ADR 0045 §11):

- `site`, il sito da cui il file viene o a cui è dato;
- `visits`, che cosa fa il sì su quel sito, nella frase della capability — accanto a `does`, che dice del file;
- `size` e `digest`, **per un file che esce**: la dimensione in byte e lo sha256 del file com'è quando la domanda è
  composta. Per uno scaricamento restano vuoti: non esce niente.

L'indirizzo, i gesti, il testo atteso e il tempo sono quelli di ogni domanda su una pagina (ADR 0052 §7). Sono contenuto
dell'utente, **sotto il tetto**: oltre il tetto di un task una superficie non legge né il file, né il sito, né
l'impronta.

**L'impronta sta sulle superfici e non nell'audit.** ADR 0045 §8 tiene gli hash fuori dai fallimenti dei verifier,
perché l'hash di un file breve si inverte per dizionario; qui lo sha256 è mostrato a chi dice sì — la console e il
telefono compresi — e non entra nella frase della domanda, che è ciò che l'audit registra. È dichiarato qui.

### 6. Un caricamento dà byte e nome, mai il percorso (M13.13)

1. **Alla domanda** ELA legge il file — un file regolare, mai attraverso un link — e la dimensione e lo sha256 viaggiano
   con il sì, in ciò che la domanda ha nominato (ADR 0065 §2). Un file sopra i **50 MiB** è rifiutato prima della
   domanda con `browser.file_too_large` (risposta 20): è il tetto di ciò che il motore dà a una pagina come byte, e una
   domanda si compone solo per ciò che riuscirebbe adesso. La dimensione è chiesta al disco prima di leggere un byte.
2. **Dopo il sì** ELA lo rilegge allo stesso modo: una dimensione o uno sha256 che non tornano sono
   `browser.file_changed`, con il sì speso, nessuna pagina aperta e niente uscito.
3. La pagina si apre con **il solo sito come confine**. Il campo che il sì ha nominato dev'essere **un elemento solo, un
   `input` di tipo `file`** (`browser.element_ambiguous`, `browser.not_a_file_field`): un altro campo file della pagina,
   che ELA non tocca, non rifiuta niente (risposta 24). *Il motore dà un file a un `input` di tipo `text` senza dire
   niente* (misura del 2026-11-10): che cosa sia l'elemento lo chiede alla pagina anche l'adapter.
4. **Dare il file è il primo gesto**: la fermata è ascoltata prima di lui, ed è il punto del tool. ELA dà alla pagina
   **i byte che ha letto e il nome** del file, mai il percorso; il tipo è quello che il nome dice (`mimetypes`), o
   `application/octet-stream` — un fatto che la pagina ricaverebbe dal nome.
5. Poi `fill` e `click` sono la sequenza di ADR 0065 §1, e il verifier è quello di un gesto: la pagina ha mostrato il
   testo atteso. **Dice ciò che la pagina ha mostrato, mai che il sito ha tenuto il file.** *Un testo che la pagina
   mostra per quattro secondi il verifier lo vede* (risposta 22: misurato sui due browser, con un sito locale che rifà
   la pagina scelta per la prova).

### 7. Il cancello di una pagina che tiene un file (M13.13)

ADR 0064 §1 dice che il confine «non impedisce a una pagina di caricare da altri siti»: guarda dove la pagina **va**,
non dove **manda**. Una pagina a cui è stato dato un file può mandarlo dove dice il suo script. Quindi, **dall'istante
prima che il file sia dato e finché la pagina vive, ogni richiesta della pagina che va a un sito fuori dal confine
fallisce** — non più solo i documenti della cornice principale (la domanda 23 di M13.10, decisa (a)). Ciò che la pagina
manda al suo sito arriva; ciò che aveva caricato da altri siti prima del file era partito, come per ogni pagina. Una
richiesta rifiutata così non è una navigazione della pagina: non resta scritta da nessuna parte, e lo step non fallisce
per lei. La pagina che tiene un file non passa allo step dopo: la guarda il verifier, e si chiude.

### 8. La porta degli scaricamenti (M13.13)

**Chiusa per ogni pagina e a ogni altro istante, e dice chi bussa.** Dall'apertura di ogni pagina una sessione del
protocollo del browser, accanto a quella del cancello, dice al browser `deny` con gli eventi accesi: niente è scritto,
e il browser **annuncia** comunque lo scaricamento, con il suo indirizzo (misura del 2026-11-10,
`.git/m13.13-reference/m13.13/h-door.txt`).

**Aperta per un gesto**, su una cartella:

1. ELA crea la cartella del bersaglio se non c'è, come `fs.write`, mai la radice;
2. la porta si apre **su quella cartella** con `allowAndName` — il browser scrive sotto un nome suo, che il sito non
   sceglie —, la fermata è ascoltata, e il gesto è fatto subito dopo: il click, o la navigazione all'indirizzo quando
   `click` non c'è. Il punto del tool è una parola sola per le due capability, «il gesto che avvia lo scaricamento»;
3. **si richiude alla prima parola di avanzamento del primo scaricamento annunciato** (misure (c) e (g) di M13.10:
   l'unico istante usabile). Ciò che è annunciato accanto al primo non è dello step: è annullato e tolto;
4. la fine si aspetta come un evento, entro il tempo del tool; poi il file prende **il nome del piano** — creando senza
   sostituire, o sostituendo quando `overwrite` lo dice — e **i permessi `600`**, anche quando sostituisce un file che
   c'era. Il risultato porta il file, la dimensione e lo sha256, letti dal file stesso;
5. uno scaricamento interrotto, fermato o scaduto è annullato, ed ELA toglie dalla cartella ciò che porta il suo
   identificativo — quello, e niente per somiglianza.

**Che cosa il gesto ha avviato lo dice il browser, non un tempo.** Uno scaricamento è annunciato dopo che il gesto è
tornato, e una navigazione che diventa uno scaricamento non impegna mai un documento: quindi la cornice principale che
ne impegna uno è «una pagina, non un file» — `browser.download_not_started`, niente scritto —, e un documento che il
cancello ha rifiutato è il sito che manda il browser fuori dal confine — `browser.left_site`, con la sola origine.

**Uno scaricamento che nessuno step ha chiesto** non scrive niente; l'adapter tiene l'indirizzo del primo annunciato, e
**ogni tool che tiene una pagina** lo dice nel risultato con la sola origine, nella chiave `download_refused` — la forma
di `another_page` —, senza far fallire lo step: i cinque di prima e le quattro nuove. È una chiave del risultato, non un
codice né un numero dell'audit: le righe dei tool di prima non cambiano.

**Un download che il suo verifier trova**: `browser.file_downloaded` — il file che il piano ha nominato c'è, è regolare,
è dentro la radice, e la sua dimensione e il suo sha256 sono quelli del risultato. Un fallimento dice le dimensioni,
mai gli hash (ADR 0045 §8). Non dice che i byte sono quelli che il sito intendeva: nessuno li conosce prima.

### 9. I tool, i verifier e dove ascoltano la fermata (M13.13)

I tool, in `ela/tools/browser_files.py`:

| Capability | Tool | Nome | Idempotente | Codici d'errore | Numeri nell'audit |
|---|---|---|---|---|---|
| `browser.download` | `BrowserDownloadTool` | `browser-download` | no | `arguments.invalid`, `browser.download_not_started`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.not_installed`, `browser.site_not_declared`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system`, `fs.no_root`, `fs.overwrite_mismatch`, `io.error`, `path.invalid`, `path.is_directory`, `path.outside_root`, `path.symlink` | `gestures`, `size`, `status` |
| `browser.download_as_you` | `AccountDownloadTool` | `browser-download-as-you` | no | `arguments.invalid`, `browser.download_not_started`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.site_not_declared`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system`, `fs.no_root`, `fs.overwrite_mismatch`, `io.error`, `path.invalid`, `path.is_directory`, `path.outside_root`, `path.symlink` | `gestures`, `size`, `status` |
| `browser.upload` | `BrowserUploadTool` | `browser-upload` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.file_changed`, `browser.file_too_large`, `browser.http_status`, `browser.left_site`, `browser.not_a_file_field`, `browser.not_installed`, `browser.secret_field`, `browser.site_not_declared`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system`, `fs.no_root`, `io.error`, `path.invalid`, `path.is_directory`, `path.missing`, `path.outside_root`, `path.symlink` | `gestures`, `status`, `stopped_at` |
| `browser.upload_as_you` | `AccountUploadTool` | `browser-upload-as-you` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.file_changed`, `browser.file_too_large`, `browser.http_status`, `browser.left_site`, `browser.not_a_file_field`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.secret_field`, `browser.site_not_declared`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system`, `fs.no_root`, `io.error`, `path.invalid`, `path.is_directory`, `path.missing`, `path.outside_root`, `path.symlink` | `gestures`, `status`, `stopped_at` |

I verifier, nello stesso modulo — quello di uno scaricamento legge il disco, quello di un caricamento guarda la pagina
nel browser che l'ha aperta:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `browser.download` | `FileDownloadedVerifier` | `browser-download-verifier` | `browser.file_downloaded` | `browser.file_mismatch`, `browser.file_unreadable`, `path.invalid`, `path.is_directory`, `path.missing`, `path.not_regular`, `path.outside_root`, `path.symlink`, `path.unreachable` |
| `browser.download_as_you` | `AccountFileDownloadedVerifier` | `browser-download-as-you-verifier` | `browser.file_downloaded` | `browser.file_mismatch`, `browser.file_unreadable`, `path.invalid`, `path.is_directory`, `path.missing`, `path.not_regular`, `path.outside_root`, `path.symlink`, `path.unreachable` |
| `browser.upload` | `UploadVerifier` | `browser-upload-verifier` | `browser.expect_visible` | `browser.another_page`, `browser.expect_missing`, `browser.left_site`, `browser.page_gone` |
| `browser.upload_as_you` | `AccountUploadVerifier` | `browser-upload-as-you-verifier` | `browser.expect_visible` | `browser.another_page`, `browser.expect_missing`, `browser.left_site`, `browser.page_gone` |

Dove ciascuno ascolta la fermata del suo task (ADR 0054 §3) — nessuno viaggia, quindi su un nodo nessuno:

| Capability | Qui | Su un nodo |
|---|---|---|
| `browser.download` | `the gesture that starts the download` | `None` |
| `browser.download_as_you` | `the gesture that starts the download` | `None` |
| `browser.upload` | `the first gesture` | `None` |
| `browser.upload_as_you` | `the first gesture` | `None` |

**Il gesto di uno scaricamento lo fa il browser** — apre la porta, ascolta la fermata e clicca o naviga, in una
chiamata sola —, quindi il tool sa due cose: prima di quella chiamata il gesto **non è fatto**, e da quando è cominciata
**può esserlo stato**. Da lì conta come fatto (`gestures: 1`), e il messaggio dice «may have been made»: un gesto
avvenuto non si riferisce mai come non avvenuto, e uno che non è avvenuto non si dice avvenuto.

### 10. Un debito datato: il debito di ADR 0065 §6, ridichiarato — un processo del browser lasciato su ubuntu da un test non identificato

**Debito a carico di M13.11, la milestone del browser sul PC**, dichiarato il **2026-11-11**, dalla regola che
`docs/milestones/M13.13.md` porta dal 2026-11-02, scritta prima di qualunque giro della CI di questo branch (decisione 5
della SPEC di M13.13), e dalle decisioni 21, 43, 45 e 52 del branch. *Scritta dopo l'accettazione di questo ADR*, nel
commit che scrive l'esito, perché la decisione 52 vuole il debito alla fine.

**La regola.** Si contano i giri completi del job ubuntu del branch — pytest arrivato al suo riepilogo —, ciascuno con
il suo commit e il suo run id. Con almeno otto, e nessuno con un errore del fixture `nothing_left_behind`, questo ADR
avrebbe pagato il debito di ADR 0065 §6. Con meno, il debito passa di mano. **Il conto si chiude all'ultimo giro completo
prima del commit che scrive l'esito**, e il giro di quel commit non conta per sé stesso (decisione 52). **Non si pusha e
non si rilancia niente per fare numero.**

**Il conto, chiuso al giro di `ead73aa`**: **6 giri completi**, nessuno con un errore di quel fixture. Il caso non si è
mostrato, e i giri non sono otto: **il debito è ridichiarato**, a carico di M13.11.

| # | Commit | Run | Il riepilogo di pytest su ubuntu | Errori del fixture |
|---|---|---|---|---|
| 1 | `5808ae5` | 41521638859 | 12057 passed, 158 skipped | 0 |
| 2 | `56c672c` | 41640819100 | 3 failed, 12110 passed, 163 skipped — rosso per tre test nuovi di M13.9b senza lo `skipif` del Mac | 0 |
| 3 | `89efd0e` | 42855676471 | 12162 passed, 168 skipped | 0 |
| 4 | `0bc3278` | 42903358334 | 1 failed, 12358 passed, 202 skipped — rosso per un test nuovo di M13.13, il conto delle domande al confine (decisione 41) | 0 |
| 5 | `7f6a494` | 42928151682 | 12358 passed, 202 skipped | 0 |
| 6 | `ead73aa` | 42935507350 | 12460 passed, 202 skipped | 0 |

Un giro, quello di `e072864` (41639384898), è stato annullato dal push successivo prima del riepilogo: non conta. Il
registro, giro per giro, con i log, è in `.git/m13.13-reference/ci/giri.txt`.

**La regola, per M13.11** (decisione 45). Lo paga con la stessa regola, e **il conto continua**: il caso e la sua
riparazione sono gli stessi. Ogni giro completo del job ubuntu senza errori del fixture conta fra gli otto, con il suo
commit e il suo run id — **su questo branch dopo il commit che porta questa sezione, il cui giro è il primo che conta per
M13.11, o sul branch di M13.11** —; con otto, l'ADR di M13.11 paga il debito, con la frase che STATO legge. **Un caso che
si mostra ferma e azzera**: ci si ferma senza rilanciare, si scrive il test rosso dalla riga che il fixture stampa, si
ripara, e il conto riparte dal commit della riparazione.

**Che cosa si sa**, com'è nella risposta 90 di M13.10: la causa è stata **trovata nel fixture `window`** (decisioni 84–86
di M13.10) e **riparata a `95874bd`**; **non è verificata su Linux**. **La difesa più piccola resta il fixture stesso**
(ADR 0065 §6): ciò che trova prima che un test cominci lo nomina con la riga di comando intera e con il test che girava
prima su quel worker.

`docs/STATO.md` conosce da questa sezione un terzo stato di un debito, oltre ad aperto e saldato: **ridichiarato in** —
letto dall'intestazione di una sezione che è a sua volta un debito datato, di un altro ADR, con la frase «il debito di
ADR NNNN §N, ridichiarato» (`scripts/generate_stato.py`, con i suoi test in `tests/scripts/test_generate_stato.py`). Una
frase così fuori da un'intestazione di debito non sposta niente, un ADR non ridichiara un debito suo, e un pagamento è
l'ultima parola. Il terzo stato nasce con la ridichiarazione per cui serve, nello stesso commit (decisione 43).
`tests/docs/test_adr_files.py` tiene questa sezione nella forma che STATO legge, il suo conto, e che il documento di
M13.11 la nomini fra ciò che eredita.

### Ciò che questo ADR dichiara e non risolve

1. **Il risultato di un gesto dice la pagina del browser se è già lì quando il tool guarda** (§1): un gesto non aspetta
   la fine della navigazione che il click avvia — lo fa `landed`, del login —, e per un `POST` che fallisce la pagina
   d'errore arriva dopo il ritorno del click. Lo sguardo del verifier, che viene dopo, la trova.
2. **Sul browser del profilo Chrome riprova da sé** un `GET` che è finito sulla sua pagina d'errore, un secondo dopo,
   senza un impegno nuovo (misura del 2026-11-03): il sito riceve la richiesta più volte.
3. **Un'altra copia della CLI di Bitwarden, in un altro file, non si riconosce** (§3): l'identità è del file, non del
   programma. E **che cosa farebbe un `bw` lanciato da `terminal.run`**, senza la chiave di sessione, **non è
   verificato**: `bw` non si lancia.
4. **La copia nella cache del profilo** (§8): uno scaricamento fatto con il browser del profilo resta anche in
   `Default/Cache/Cache_Data/`, e spegnere la cache sulla pagina non la toglie (misura del 2026-11-02, cinque giri su
   cinque nei due modi).
5. **`com.apple.quarantine` e `com.apple.macl`** sul file scaricato dal browser del profilo; lo shell non li mette.
6. **Il `.crdownload` che resta se ELA è uccisa a metà** di uno scaricamento: nessuno lo toglie.
7. **Il primo scaricamento annunciato è preso per quello dello step** (§8): se il sito ne avvia un altro prima, è
   quello che è scritto sotto il nome del piano.
8. **Nessun tetto alla dimensione di uno scaricamento** oltre il tempo del tool.
9. **La WebSocket** di una pagina che tiene un file (§7): nessun test con il cancello afferma che non parta.
10. **Un sito che carica il file su un altro suo indirizzo** — un'altra origine — non funziona con il cancello di §7: la
    richiesta fallisce, e il verifier non vede il testo.
11. **Il tipo del file è dedotto dal nome** (§6), e **l'impronta è sulle superfici della domanda** (§5).
12. **Una cartella creata per uno scaricamento che poi non comincia resta, vuota** — come fa `fs.write` quando la sua
    scrittura fallisce.
13. **Un click che non avvia né uno scaricamento né una pagina** finisce con il tempo del tool (`browser.timeout`), non
    con `browser.download_not_started`: nessun evento dice «niente» (§8).
14. **`download_refused` è nel risultato se il browser l'ha annunciato prima che lo step finisse** (§8): uno
    scaricamento annunciato dopo non lo dice nessuno step.
15. **Il conto del gesto di uno scaricamento è «al più»** (§9).

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0063** §5 — `landed` aspetta la fine della navigazione che il click ha avviato, e la pagina d'errore del browser è detta all'indirizzo che il browser ha provato a raggiungere (§1, §2).
- **ADR 0047** §9 — le righe del verifier e del tool di `terminal.run` guadagnano `terminal.vault_program`: riscritte per intero qui (§3).
- **ADR 0064** §4 — la riga «nessun confine ammette un indirizzo che non è di un sito»: la pagina d'errore del browser è chiesta al confine per l'indirizzo che il browser ha provato a raggiungere; `about:blank` e `blob:` restano fuori (§1). E §1, §2 — «non impedisce a una pagina di caricare da altri siti» e la riga «ogni altra richiesta di quella pagina … parte» non valgono per una pagina che tiene un file (§7).
- **ADR 0052** §4, §5, §7 — per le quattro capability dei file lo scope è il file e il sito è il confine del tool, che lo rifiuta prima della domanda; la domanda nomina il file, e il sito ha campi suoi (§4, §5).
- **ADR 0065** §6 — il debito del processo del browser lasciato su ubuntu non è più a carico di M13.13: sei giri puliti su otto, e passa di mano, con il conto che continua, a M13.11 (§10).

Le altre conseguenze:

- **Il port** `Browser` guadagna `unanswered`, e con i file `give`, `download`, `downloaded_from` e
  `refused_download`; `Landed` e `Glanced` guadagnano `unanswered`.

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `Browser` | §19 | async | `unanswered`, `give`, `download`, `downloaded_from`, `refused_download` |
| `AccountBrowser` | §19 | async | `unanswered`, `give`, `download`, `downloaded_from`, `refused_download` |

`unanswered` è del §1; `give` del §6; `download`, `downloaded_from` e `refused_download` del §8.
- **Regola di architettura 72** (§3): il programma del vault arriva al suo adapter e alla sua porta, e a nient'altro.
- **Regola di architettura 73** (§6, §8), su ciò che un test statico vede negli adapter: `set_input_files` riceve un
  solo carico di byte, scritto lì, mai un percorso né un elenco; e `Browser.setDownloadBehavior` si manda con il
  comportamento scritto accanto, `allowAndName` o `deny` — mai `allow`, mai `default`, mai un dizionario costruito
  altrove. Che la cartella sia quella del bersaglio e che la porta si richiuda lo affermano i test sul browser vero.
- **La domanda** guadagna quattro campi sulle superfici che rispondono: `site`, `visits`, `size`, `digest` (§5).

Con questo ADR le regole di architettura sono **settantatré** (la 72 e la 73); i contratti di import-linter restano
**quindici**, i port **trentasei**, le rotte dell'API **settantadue** e i comandi della CLI **trentanove**; le
capability diventano **ventidue**, le identità del middleware restano **sei**.
