# 0066. I file dal browser, e la pagina del browser che non è un sito

- **Stato:** Proposta il **2026-11-03**, con l'implementazione del branch `m13.13-i-file-dal-browser` — M13.9b,
  M13.9c, M13.10b e M13.13 —, per diventare Accettata con un commit suo quando la prova a mano — la sezione 30 di
  `docs/GETTING_STARTED.md` — sarà passata sull'ultimo commit del branch (decisione 11 del branch).
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

### Ciò che questo ADR dichiara e non risolve

1. **Il risultato di un gesto dice la pagina del browser se è già lì quando il tool guarda** (§1): un gesto non aspetta
   la fine della navigazione che il click avvia — lo fa `landed`, del login —, e per un `POST` che fallisce la pagina
   d'errore arriva dopo il ritorno del click. Lo sguardo del verifier, che viene dopo, la trova.
2. **Sul browser del profilo Chrome riprova da sé** un `GET` che è finito sulla sua pagina d'errore, un secondo dopo,
   senza un impegno nuovo (misura del 2026-11-03): il sito riceve la richiesta più volte.
3. **Un'altra copia della CLI di Bitwarden, in un altro file, non si riconosce** (§3): l'identità è del file, non del
   programma. E **che cosa farebbe un `bw` lanciato da `terminal.run`**, senza la chiave di sessione, **non è
   verificato**: `bw` non si lancia.

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0063** §5 — `landed` aspetta la fine della navigazione che il click ha avviato, e la pagina d'errore del browser è detta all'indirizzo che il browser ha provato a raggiungere (§1, §2).
- **ADR 0047** §9 — le righe del verifier e del tool di `terminal.run` guadagnano `terminal.vault_program`: riscritte per intero qui (§3).
- **ADR 0064** §4 — la riga «nessun confine ammette un indirizzo che non è di un sito»: la pagina d'errore del browser è chiesta al confine per l'indirizzo che il browser ha provato a raggiungere; `about:blank` e `blob:` restano fuori (§1).

Le altre conseguenze:

- **Il port** `Browser` guadagna `unanswered`; `Landed` e `Glanced` guadagnano `unanswered`.

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `Browser` | §19 | async | `unanswered` |
| `AccountBrowser` | §19 | async | `unanswered` |

`unanswered` è del §1.
- **Regola di architettura 72** (§3): il programma del vault arriva al suo adapter e alla sua porta, e a nient'altro.

Con questo ADR le regole di architettura sono **settantadue** (la 72); i contratti di import-linter restano
**quindici**, i port **trentasei**, le rotte dell'API **settantadue** e i comandi della CLI **trentanove**; le
capability restano **diciotto**, le identità del middleware **sei**.
