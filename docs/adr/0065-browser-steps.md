# 0065. Il browser a più passi: ogni elemento aspettato, ciò che il sì ha nominato, la pagina che dura fra gli step, il login chiesto dal modello

- **Stato:** Accettata il **2026-10-29**, con un commit suo, **per decisione di Tommaso di quel giorno** (decisione
  76 di `docs/milestones/M13.10.md`): la prova a mano della sezione 29 di `docs/GETTING_STARTED.md` è passata sul
  Mac, sul branch e prima del merge, a `4490e15`, l'ultimo commit (`~/Downloads/prova-m13.10-20261029-082557.txt`:
  33 PASSATI, tutti al primo giro, 0 FALLITI, nessun no, nessun SALTATO). **Scritto com'è**: la domanda `4.occhio`
  chiedeva della «risposta del modello, nel file», e né il file né lo schermo l'hanno portata — `fine` stampa solo
  l'uscita della corsa in sfondo, e prima della domanda non c'è un blocco `schermo`, che il passo 2 ha —; il sì vale
  per la decisione di Tommaso, perché ciò che quella riga proteggeva la macchina l'ha verificato nella stessa prova:
  il figlio `browser.login` COMPLETED con il suo verifier su «logout», la sessione COMPLETED con 4 figli dentro i
  suoi siti. Proposta il **2026-10-14**, con l'implementazione di M13.10, per diventare Accettata con un commit suo
  quando la prova fosse passata sull'ultimo commit del branch (decisione 48 della review della SPEC di M13.10).
  *`4490e15` era l'ultimo commit del branch quando la prova è girata: i commit venuti dopo, questo compreso,
  portano solo documenti.* ***Annotato il 2026-10-29, più tardi (decisione 87 di M13.10)***: non più solo
  documenti. Dopo questo commit — `e2d105d` — sono venuti `fbaf94b` e `35ce5fa`, documenti; `4ef3506` e `95874bd`,
  solo `tests/`: i test rossi delle decisioni 85 e 86 e la loro riparazione — il fixture `window` di
  `tests/infrastructure/machine/test_account_window.py` aspetta dentro il ciclo del test ciò che ha finito, e
  `nothing_left_behind` nomina il test prima di qualunque modulo e raccoglie un figlio del worker già finito —; e il
  commit che porta questa nota, documenti. Niente di `src/` né di `scripts/`: ciò che la prova ha visto non cambia,
  e la riga resta su `4490e15` (la decisione 58 (e) di M13.10, rivista apertamente in questo punto solo). **Il caso
  di §6 si è mostrato a `35ce5fa`**, e la causa misurata sta in quel test; il pagamento del debito aspetta la
  domanda 89 di M13.10, perché la forma che STATO legge vuole un ADR diverso da questo.
- **Data:** 2026-10-14
- **Riferimenti spec:** §19, §33, §57
- **Milestone:** [M13.10](../milestones/M13.10.md)

## Contesto

Fino a M13.10 un lavoro nel browser era **un gesto**: `browser.act` apriva la pagina, controllava ogni elemento
prima del primo gesto (ADR 0052 §8), riempiva e cliccava, e il browser si chiudeva con lo step (ADR 0052 §3,
ADR 0063 §4). Un elemento che compare dopo un gesto — un menu, un secondo campo, il pulsante che la scrittura
di un messaggio fa comparire — non si poteva controllare prima del primo gesto. La SPEC di M13.10 e la review
del 14 ottobre 2026 hanno deciso di cambiarlo. Le misure sono nella SPEC, con la regola scritta prima dei
numeri; i file stanno nell'officina di Tommaso.

## Decisione

### 1. Ogni elemento è aspettato quando serve

**Ogni gesto aspetta il suo elemento** — presente, uno solo, visibile —, insieme alla fermata del task, entro
il tempo del tool, che resta l'unica scadenza: ELA non scrive nessuna durata (ADR 0006 §13). Una lettura con un
selettore aspetta il suo elemento allo stesso modo: una regola sola (decisione 43 della review). Rivede
apertamente ADR 0052 §8, «controlla ogni elemento prima del primo gesto», e la decisione 7 di M13.4.

- **Chi aspetta è il motore, chi decide è il tool.** Il port guadagna `appeared`: l'attesa del motore,
  **stretta**, sul selettore stesso, che finisce quando il selettore trova un elemento visibile e solleva
  subito quando ne trova più di uno — anche se uno è nascosto —; allora risponde quanti. Il conto,
  l'ambiguità, il campo segreto e la fermata restano nel tool.
- **Il ritardo del motore, dichiarato** (decisione 40, misura (a) della SPEC): il motore riguarda la pagina a
  intervalli suoi, che si allungano fino a mezzo secondo. Misurato su otto giri per riga, sui due browser,
  ritardo dopo che l'elemento c'è — mediana: **6 ms** quando compare subito, **52 ms** dopo 30 ms, **498 ms**
  dopo 300 ms, **309 ms** dopo due secondi; il massimo misurato è 507,5 ms. Nei test l'elemento compare subito.
- **Per ogni gesto, in quest'ordine**: l'elemento aspettato insieme alla fermata; più di uno è
  `browser.element_ambiguous`; un campo che si dichiara segreto è `browser.secret_field`, **prima del gesto che
  lo riempirebbe**, non più prima del primo; lo sguardo alla fermata — al primo gesto è il punto del tool, agli
  altri `is_set()` —, e fra lo sguardo e il gesto nessuna attesa; il gesto, contato quando è fatto.
- **Un punto dichiarato, la fermata ascoltata ovunque** (decisione 41): il punto della porta resta «il primo
  gesto», e la tabella di ADR 0054 §3 non cambia; la fermata è ascoltata prima di ogni gesto e dentro ogni
  attesa. Dopo un gesto fatto il tool chiude lo step da sé con `browser.stopped` e il conto dei gesti: mai la
  frase dell'executor che dice il task fermato prima che il tool agisse.
- **Il tempo che scade mentre un elemento è aspettato** è `browser.element_missing`, e la frase dice quale
  gesto, di quanti, e quanti erano fatti; in ogni altro momento resta `browser.timeout`.
- **Il risultato** di una sequenza che non arriva in fondo dice `stopped_at`, il numero del primo gesto non
  fatto: è un numero dell'audit di `browser.act` e di `browser.act_as_you`.
- **Le frasi**: «no gesture was made» solo quando è vero; dopo un gesto fatto nessuna frase dice che niente è
  stato inviato (la regola del 13 ottobre).
- **Lo schema non cambia forma**: `fill` è la sequenza, `click` l'ultimo gesto; «un sì copre al massimo un
  effetto» (ADR 0046 §3) regge, perché il click è uno.
- **Che cosa cambia per chi c'è già** (decisione 45): un elemento che non c'è costa il tempo dello step, e i
  gesti prima di lui sono fatti. Dentro una sessione guidata i selettori li scrive un modello che non vede gli
  attributi: la descrizione dei due strumenti glielo dice.

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `Browser` | §19 | async | `appeared`, `hold`, `resume`, `where` |
| `AccountBrowser` | §19 | async | `appeared`, `hold`, `resume`, `where`, `forms` |

`hold`, `resume` e `where` sono del §3, `forms` del §4.

**Righe dei tool, riscritte.** Un ADR accettato non si riscrive: le righe di un tool che M13.10 cambia — un
codice d'errore in più o in meno, un numero dell'audit in più — si riscrivono qui **per intero**, e la riga
riscritta vince su quella dell'ADR che ha introdotto il tool, come la tabella delle capability estese fa per uno schema
(decisione 44 della review). I test delle righe degli ADR vecchi la leggono accanto alla loro. Ci sono anche
le righe del §3: `browser.no_page_to_continue` sui quattro tool che continuano.

Righe dei tool, riscritte:

| Capability | Tool | Nome | Idempotente | Codici d'errore | Numeri nell'audit |
|---|---|---|---|---|---|
| `browser.read` | `BrowserReadTool` | `browser-read` | sì | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.no_page_to_continue`, `browser.not_installed`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `shown`, `status`, `total` |
| `browser.act` | `BrowserActTool` | `browser-act` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.no_page_to_continue`, `browser.not_installed`, `browser.secret_field`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `gestures`, `status`, `stopped_at` |
| `browser.read_as_you` | `AccountReadTool` | `browser-read-as-you` | sì | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.no_page_to_continue`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `shown`, `status`, `total` |
| `browser.act_as_you` | `AccountActTool` | `browser-act-as-you` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.no_page_to_continue`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.secret_field`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `gestures`, `status`, `stopped_at` |
| `browser.login` | `LoginTool` | `browser-login` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.field_changed`, `browser.http_status`, `browser.left_site`, `browser.login_form_get`, `browser.no_window`, `browser.not_a_password_field`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.secret_field`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system`, `vault.entry_ambiguous`, `vault.entry_not_for_site`, `vault.entry_not_named`, `vault.failed`, `vault.locked`, `vault.no_entry`, `vault.no_password`, `vault.no_program`, `vault.program_changed`, `vault.program_gone`, `vault.program_is_a_script`, `vault.timeout`, `vault.unauthenticated`, `vault.undeclared` | `gestures`, `status` |

### 2. Ciò che il sì ha nominato arriva al tool con il sì

**Il secondo bag, `named`**, sta accanto ad `asked` nei metadati dell'approvazione, in una chiave sua della
colonna che c'è — nessuna colonna nuova, nessuna migrazione. Lo scrive l'executor quando compone la domanda,
da ciò che il tool ha trovato componendola e deve usare dopo il sì (`Prospect.named`); lo legge **solo**
dall'approvazione che ha generato il grant, e lo consegna a `Tool.execute`. **Nessun tool ricorda più niente
fra la domanda e il sì**: il sì resta legato a ciò che Tommaso ha letto anche attraverso un riavvio di ELA.
Rivede apertamente ADR 0063 §5 (la voce ricordata in memoria) e ADR 0045 §6-bis («non serve un secondo
canale per far viaggiare il fatto approvato»: per ciò che la domanda nomina e il piano non porta, serve).

- **Per un login** `named` porta l'id della voce del vault che la domanda ha nominato, che nessuna superficie
  mostra (ADR 0063 §9). Dopo il sì il tool legge **quella** voce, confrontata di nuovo con il sito sulla stessa
  lettura: un host che non torna è `vault.entry_not_for_site`. `vault.entry_forgotten` è ritirato. Un sì dato a
  una domanda che non nominava una voce — una domanda composta prima di M13.10 — è `vault.entry_not_named`, e
  lo step si richiede (decisione 38: non `NotAllowedError`, perché la decisione è `ALLOWED`).
- **`named` non entra nell'audit e nessuna rotta lo serve**: la regola d'architettura 71 lo tiene, ancorata
  alla costante.
- **`named` non viaggia**: i tool di un nodo sono chiamati senza niente dell'approvazione, e `fs.read` e
  `fs.write` non cambiano contratto.
- **Il disco**: l'id di una voce del vault, che fino a M13.10 stava in memoria, sta nella riga
  dell'approvazione quanto la riga. Il driver del database, al livello DEBUG, copia nelle sue righe i
  parametri di ogni scrittura, e quindi anche quell'id: è il database un'altra volta, a un livello che ELA
  non accende — nessun modulo di `src/` abbassa un livello sotto il WARNING di partenza, fuori dall'INFO del
  server. Il test dei sette posti di M13.9 lo afferma così.

### 3. Dentro un task, la pagina di uno step può essere quella del successivo

**Rivede apertamente «un browser nuovo per step»** — ADR 0052 §3, e ADR 0063 §4 per il profilo —: dentro un
task la pagina che uno step lascia può essere quella su cui lavora lo step dopo. Fra due task niente passa,
come prima: per il browser con gli account solo la cartella del profilo, per quello vuoto niente.

- **Non è una capability.** Nessuna riga del catalogo, nessun rischio, nessuna regola del Guardian: ogni step
  è giudicato dalla sua capability come prima. ADR 0060 §1 chiamava «`browser.session`» ciò che questa
  milestone avrebbe portato: non ha quel nome, e non è una capability.
- **L'argomento `continues`**, `true`, su `browser.read`, `browser.act`, `browser.read_as_you` e
  `browser.act_as_you` (decisioni 28 e 29 della review): **esattamente uno fra `continues` e `path`** — lo
  schema lo dice con un `oneOf`, e il tool lo ricontrolla —; `site` resta, perché è il bersaglio del
  Guardian e il confine. `browser.login` non continua mai: apre sempre la sua pagina, con la finestra.
  **Le policy di `browser.guided_as_you` nate prima smettono di coprire**: la loro copia dello schema di
  `browser.read_as_you` non è più quella di oggi (ADR 0063 §1), e si ricreano una volta. Il 14 ottobre 2026
  non ce n'era nessuna viva.
- **La stanza delle pagine**, `ela.executive.pages`, dietro il port `TaskPages`, costruita prima dei tool e
  che non riceve niente dopo: «l'unico legame tardivo del grafo» (ADR 0060 §4) resta l'unico. **Una pagina
  per task, e la chiave è il task**: due task con lo stesso piano — gli stessi id degli step — non hanno mai
  la stessa pagina. La stanza **tiene** la pagina che uno step riuscito le lascia solo se **lo step subito
  dopo** nel piano continua, e la consegna a quello step, sullo stesso browser: una pagina dell'altro browser
  è chiusa, e lo step non la trova. Uno step in mezzo che non continua non la riceve: aprirebbe la sua
  pagina, e la stanza chiude quella tenuta prima.
- **Continuare.** Il tool chiede alla stanza la pagina del suo task — il task e lo step vengono dalla
  decisione, mai da un argomento —; l'adapter la riprende con **il confine dello step che continua** al posto
  di quello con cui era stata aperta, nel cancello e in ogni uso dopo (misura (g) della SPEC: una navigazione
  verso il sito nuovo parte, una verso il vecchio no), e chiede a quel confine dove la pagina è: fuori dal
  `site` dello step è `browser.left_site`, e niente della pagina è letto. Una pagina che non c'è è
  **`browser.no_page_to_continue`**: prima della domanda, senza spendere un sì — `prospect` riceve il task
  (decisione 25), facoltativo: la rotta delle policy non lo passa, e un tool che non continua non lo legge
  —; e dopo il sì, con il sì speso e niente fatto.
- **Il punto** di uno step che continua è quello della sua capability: per una lettura subito prima che la
  pagina sia ripresa, per un gesto al primo gesto, come su una pagina aperta. Nel risultato `status` è lo
  stato del documento su cui la pagina è adesso, `address` dove è adesso.
- **La domanda** dice che lo step continua — la frase dello strumento cambia: «opens no page» — e **dov'è
  adesso** la pagina: host e percorso, mai la query (decisione 26).
- **Ciò che è successo nell'attesa non è dello step dopo**: un rimando rifiutato mentre nessuno usava la
  pagina non fa fallire lo step che continua, e il suo risultato lo dice con l'origine sola, in
  `left_while_waiting`, nella forma di `another_page`. Fuori dall'audit: non è un numero.
- **Lo sguardo del verifier non chiude** una pagina tenuta, e la scadenza dell'adapter per una pagina
  consegnata e mai guardata non vale per lei: da quando la stanza la tiene, chi la chiude è la stanza.
- **Chi chiude, e quando** — un posto solo: la stanza. Quando il task arriva a uno stato finale, che la
  stanza **sente** dalla fermata del task che il motore alza per ogni fine, senza che nessuno la chiami;
  quando lo stesso task apre un'altra pagina; e quando **finisce ciò che il task aspetta** (decisione 26): la
  domanda dello step che continua finché non ha risposta, e dopo il sì il grant (`expires_at`) finché lo step
  non gira. Un no chiude subito. L'orologio è quello del custode del vault: un'attesa di un minuto alla volta
  che chiede all'orologio, mai al tempo del loop, che si ferma mentre il Mac dorme. Il task resta com'è. Alla
  fermata di ELA chiudono i browser stessi (ADR 0038 §11), e la stanza dimentica. **Nessuno spazzino dei
  browser all'avvio** (decisione 42): una pagina vive in memoria, e un'ELA uccisa non lascia niente da
  spazzare (misura (g)); lo step che continua e non trova la pagina ha il suo codice.
- **Il profilo.** Una pagina tenuta sul browser con gli account lo tiene: l'adapter lo dice con un nome
  nuovo, **`task`**, accanto a `step` (decisione 27: la decisione 148 di M13.9 resta, e la percezione non si
  rifiuta per una pagina di ELA a cui nessuno scrive). Un altro task riceve `browser.profile_busy`,
  ritentabile, con **l'id del task** che tiene la pagina, fino a quando, e il comando che lo ferma; lo stesso
  task no (decisione 44). Uno step che continua eredita la finestra, o la sua assenza, del lancio che ha
  aperto la pagina.
- **Le parole.** `GET /browser` dice `task` nello stato del profilo e, in `waiting`, ogni pagina tenuta su
  uno dei due browser: il task, fino a quando, e il comando che la chiude; `ela browser status` e la console
  «Il browser di ELA» lo stesso. Il comando è **`ela task cancel`**: le frasi dicevano `ela task stop`, un
  comando che non c'è, e la frase della chiusura del profilo è riparata con loro.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `TaskPages` | §19 | async | `leave`, `take`, `where`, `release`, `waiting` |

Capability estese:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `browser.read` | LOW | `undeclared` | `site` | no | `site: string`, `purpose: string` | `path: string`, `selector: string`, `continues: boolean` |
| `browser.act` | HIGH | `undeclared` | `site` | sì | `site: string`, `fill: array`, `click: string`, `expect_text: string`, `purpose: string` | `path: string`, `continues: boolean` |
| `browser.read_as_you` | MEDIUM | `undeclared` | `site` | sì | `site: string`, `purpose: string` | `path: string`, `selector: string`, `continues: boolean` |
| `browser.act_as_you` | HIGH | `undeclared` | `site` | sì | `site: string`, `fill: array`, `click: string`, `expect_text: string`, `purpose: string` | `path: string`, `continues: boolean` |

| `browser.login` | HIGH | `undeclared` | `site` | sì | `site: string`, `path: string`, `username_field: string`, `password_field: string`, `click: string`, `purpose: string` | `entry: string`, `expect_text: string` |

`path` e `continues` sono facoltativi uno per uno ed esattamente uno dei due c'è: la tabella non ha una
colonna per un `oneOf`, e lo dice qui. La riga di `browser.login` è del §4.

### 4. Il login chiesto dal modello

**Una sessione con il profilo offre al suo modello un terzo strumento, `login`** (decisioni 12, 22, 31, 32,
43 e 45 della review). Il modello dà il sito, e facoltativi il percorso — la radice, senza — e un testo da
aspettare; niente altro, e ciò che non è quello la stanza lo rifiuta da sé. **Mai la password**: né nel
prompt, né in un risultato, né in un errore; il modello non la dà e non la riceve, e non vede mai la voce del
vault né il nome utente.

- **Gli strumenti di una sessione sono un dato**: ognuno è nome, descrizione e schema (`SessionTool`), il
  piano della sessione li porta, l'adapter li offre come sono scritti, e l'insieme che il budget controlla a
  ogni chiamata è **calcolato da quel dato** (misura (f) della SPEC: il binario vero ne elenca tre).
  `SessionGestures` guadagna `login`, che è `browser.login` per la sessione con il profilo e niente per
  l'altra. `AgentSession.tools` diventa la funzione che dà i nomi di quegli strumenti, asincrona come il port.
- **Un gesto di login sono due figli**, e **conta due gesti** fra quelli che il sì ha concesso (decisione 45):
  la descrizione dello strumento lo dice. (1) **La lettura**: un `browser.read_as_you` della pagina, coperto
  dalla sessione come ogni sua lettura. **Ogni lettura con il profilo riporta il modulo di accesso** della
  sua pagina — o perché non c'è, o perché è ambiguo — in campi suoi del risultato, `login_form` e
  `no_login_form`, fuori dall'audit e da ciò che la sessione legge (decisione 43 (ii)); nessun argomento
  nuovo. (2) **Il login**: solo se il modulo è stato trovato, un `browser.login` con quei selettori — `HIGH`,
  chiede a ogni uso, e vale tutto ADR 0063 §5: una policy di `browser.guided_as_you` non lo copre. Senza un
  modulo — `browser.login_form_not_found`, `browser.login_form_ambiguous` — il secondo figlio non nasce:
  nessuna domanda, nessun sì speso. Un login riuscito conta fra gli atti della sessione.
- **La regola** (decisione 22) conta i campi password che `browser.login` riempirebbe — `type="password"`,
  visibili, che non si dichiarano `new-password`, `one-time-code` o di una carta — e ne vuole uno; il modulo
  è quello che lo contiene, il campo del nome è il campo di testo o email visibile prima di lui nello stesso
  modulo, l'elemento che invia è il solo di quel modulo. Su Hacker News (misura (e)) trova il modulo di
  accesso e lascia quello di registrazione, il cui campo si dichiara `new-password`. **I selettori si
  scrivono dallo stesso fatto**, mai dalla posizione: il campo password per ciò che dichiara, gli altri due
  per il loro nome o il loro tipo, dentro il modulo che contiene quel campo (`form:has(…)`); ognuno è
  contato sulla pagina prima di essere scritto — uno, o il modulo è ambiguo —, e il tool del login li
  ricontrolla tutti dopo il sì. L'adapter legge dei moduli solo ciò che ogni elemento dichiara di sé — il
  tag, il tipo, il nome, `autocomplete`, se è visibile —, mai un valore o un'etichetta (`forms`).
- **`expect_text` è facoltativo** per ogni login (decisione 31). Senza, la condizione è
  **`browser.login_form_gone`**: la pagina sul sito dello step, nessun elemento per il selettore del campo
  password, lo stato del documento sotto 400. Il nome dice ciò che il verifier guarda, non «entrato». Lo
  sguardo guadagna quanti elementi trova il selettore e lo stato del documento (`Glanced.found`,
  `Glanced.status`). **La stanza sceglie le condizioni dal fatto** — con `expect_text`
  `browser.expect_visible`, senza `browser.login_form_gone` —, non più tutte quelle del verifier.
- **Che cosa vede il modello** di un login (decisione 12): una lista della stanza, sua e chiusa — lo stato
  del figlio, il codice, `ended_at`, `ended_status`, `password_field_still_there`; il codice dice anche
  `browser.second_factor` quando è il verifier a dirlo. **Mai la frase** di una fine, che per ogni altro
  gesto la stanza mostra intera; un no è «denied», e niente altro.
- **La domanda della sessione con il profilo** dice in `sends` (decisione 32): «the text of the pages read as
  you, and of a login where its page ended, its status and whether its form was still there — never the
  entry, the username or the password».
- **Una pagina può dire al modello di chiedere un login.** Resta `HIGH`, chiede a Tommaso ogni volta, la
  domanda nomina il sito e la voce, e il modello non può dire altro che un percorso del solo sito della
  sessione. Dichiarato.

Righe dei verifier, riscritte:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `browser.login` | `LoginVerifier` | `browser-login-verifier` | `browser.expect_visible`, `browser.login_form_gone` | `browser.expect_missing`, `browser.page_gone`, `browser.second_factor`, `browser.left_site`, `browser.another_page`, `browser.login_form_still_there`, `browser.http_status` |

### 5. Ciò che questo ADR dichiara e non risolve

1. **Il ritardo del motore** (§1): un elemento è visto fino a circa mezzo secondo dopo che c'è (misura (a)); nei
   test l'elemento compare subito. Una soglia di tempo su quel ritardo non si fissa: questo Mac non la risolve.
2. **Un selettore sbagliato costa il tempo dello step** (§1): i gesti prima di lui sono fatti. Dentro una
   sessione il modello lo sa dalla descrizione dello strumento.
3. **Una pagina che aspetta e un task che non aspetta niente che finisca** (§3): uno step che continua senza
   domanda — una lettura — e una corsa che si ferma prima di lui lasciano la pagina viva finché il task non
   finisce. Lo stato del browser e la console dicono quale task la tiene e come si ferma.
4. **Un gesto di file dentro una sessione, e `continues` dentro una sessione**, non sono di nessuna milestone
   (decisione 39): una sessione apre le sue pagine, e i file sono di [M13.13](../milestones/M13.13.md) con il
   loro piano.
5. **La lettura di un login gira come dice l'interruttore, il login sempre con la finestra** (§4): un sito può
   servire due pagine diverse. Se dopo il sì i selettori non tornano, il login finisce con il suo codice, il sì
   è speso e niente è scritto.
6. **Una pagina può dire al modello di chiedere un login** (§4): resta `HIGH`, chiede ogni volta, la domanda
   nomina il sito e la voce, e il modello non può dire altro che un percorso del solo sito della sessione.
7. **Nessuno spazzino dei browser all'avvio** (§3): con la finestra non è misurato che cosa resta di un'ELA
   uccisa con una pagina che aspetta; lì vale ciò che ADR 0063 dice di un browser che sopravvive a ELA, e lo
   chiude `ela browser close`.
8. **Una risposta del cancello che non si scrive** (decisione 53 della review dell'implementazione): quando il
   driver la rifiuta con un'eccezione — è morto, o sta morendo, alla fine di uno step, di un task, alla fermata di
   ELA —, la richiesta resta sospesa, e una richiesta sospesa non parte (ADR 0064 §2). Non in silenzio: una riga
   al livello WARNING dice il tipo dell'eccezione e se la risposta lasciava andare la richiesta o la rifiutava,
   mai l'indirizzo. **Con un driver vivo, una risposta non scritta lascia la pagina ad aspettare, e lo step
   finisce in `browser.timeout`**: nessuna lista dei messaggi di Playwright distingue i due casi, e la riga
   dice quale è stato.
9. **WhatsApp Web, con il profilo di ELA, non è andato oltre la barra di caricamento** (decisioni 61, 62 e 65
   della review dell'implementazione). Nella prima misura di Tommaso, il 2026-10-14 — il file
   `misura-m13.10-20261014-184951.txt`, nella sua cartella `~/Downloads` e copiato in
   `.git/m13.10-reference/misura-whatsapp/` —, dopo la scansione del codice la barra è rimasta ferma e vuota per
   due ore, e nessuna chat è comparsa; se il collegamento sul telefono sia riuscito non è ancora noto. **I
   candidati, per nome, e nessuno è misurato**: il service worker che il sito vuole, che ELA toglie e blocca a
   ogni lancio che guida (ADR 0064 §6); un worker condiviso, le cui richieste il cancello rifiuta (ADR 0064 §2);
   altro. **Nessuna milestone senza la causa**: la misura, da M13.10, la cerca — le origini che il cancello ha
   rifiutato, i target che il browser ha annunciato con il tipo, i tipi degli errori della console, mai un testo
   (decisione 63) —, e si rifà un altro giorno, dopo il controllo sul telefono. Fino ad allora **WhatsApp esce
   dalla prova di M13.10** (sezione 29 della guida), e il piano esce dal repository; la decisione 23 di M13.9 —
   sul numero di Tommaso, un solo messaggio a se stesso — resta valida per la milestone che lo riprenderà.

### 6. Un debito datato: un processo del browser lasciato su ubuntu da un test non identificato

**Debito a carico di M13.13, la milestone dei file dal browser**, dichiarato il **2026-10-14**, dalla review
dell'implementazione di M13.10 (decisione 56).

**Il fatto**: nella CI di ubuntu, a `fc8983f` e a `73473d2`, una dozzina di test di
`tests/infrastructure/machine/test_browser.py` hanno trovato fra i discendenti del loro worker un processo del
browser lasciato da un test prima di loro, nominato con i suoi primi quindici caratteri soltanto — «Google
Chrome f» — e da nessun test; e il fixture `nothing_left_behind` è caduto al teardown di sei di loro con «Set of
Tasks/Futures is empty», un'attesa chiesta su un insieme vuoto. Nei giri di `0e09ca1`, `b6b9658` e `35a922f` non
c'è; su questo Mac non si riproduce; dalla CI com'era nessuno poteva nominare il test.

**Non si ripara qui**: il merge non lo aspetta — gli ultimi due giri sono puliti (decisione 56). **La difesa più
piccola è il fixture stesso**, riparato in M13.10: un insieme vuoto non è più un'attesa, e ciò che il fixture
trova prima che un test cominci lo nomina con la riga di comando intera letta dal sistema — `/proc/<pid>/cmdline`
su Linux, e, per un processo finito che nessuno ha raccolto, che lì non ne ha, il suo stato e il genitore che
avrebbe dovuto raccoglierlo — e con il test che girava prima su quel worker
(`tests/infrastructure/machine/test_nothing_left_behind.py`). **La prossima volta che il caso si mostra, la CI
nomina il test**: M13.13 lo ripara da quella riga, o scrive che nei suoi giri il caso non si è mostrato.
`tests/docs/test_adr_steps.py::test_the_debt_of_the_process_left_on_ubuntu_is_dated_charged_and_named_by_who_pays_it`
tiene questa sezione nella forma che `docs/STATO.md` legge, e che il documento di M13.13 la nomini fra ciò che
eredita. Il giorno in cui è pagato, il pagamento si scrive in un ADR, e il test si gira.

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo
dice, con la sezione di questo ADR a cui guardare.

- **ADR 0045** §4 e §6-bis — §6-bis: per ciò che la domanda nomina e il piano non porta serve un secondo canale, `named` (§2). §4: `prospect` riceve il task, facoltativo (§3).
- **ADR 0052** §3, §4, §5, §7, §8 e §9 — §3: dentro un task la pagina di uno step può essere quella del successivo (§3). §4, §5 e §7: uno step che continua non ha `path`, e la domanda nomina dov'è la pagina. §8: ogni elemento è aspettato quando serve (§1). §9: lo sguardo non chiude una pagina tenuta (§3).
- **ADR 0060** §1, §2, §4, §5 e §8 — §1: non c'è una capability `browser.session` (§3). §2, §4 e §5: gli strumenti sono un dato, e un login sono due figli (§4). §8: ciò che il modello legge di un login (§4).
- **ADR 0063** §1, §4, §5, §6 e §8 — §1: le policy di `browser.guided_as_you` nate prima smettono di coprire (§3). §4: la pagina con il profilo dura fra due step (§3). §5: la voce viaggia con il sì (§2), `expect_text` è facoltativo (§4). §6: il gesto di login (§4). §8: `task` (§3); e la frase che dice come fermare il task che tiene il profilo nomina `ela task cancel` — scriveva `ela task stop`, che non c'è —: riparato in M13.10 senza lettera, con un test che guarda la CLI (§3; decisione 52 della review dell'implementazione).
- **ADR 0064** §1 — il confine di una pagina che continua è quello dello step che continua (§3).
- **La registrazione di M13.10**, per i file: i due criteri che la nominano passano parola per parola a [M13.13](../milestones/M13.13.md), con le misure (c) e (d) e le domande 23, 24, 30 e 36 (decisioni 21 e 48 della review).

Le altre conseguenze:

- **Regola di architettura 71**: ciò che una domanda ha nominato arriva al tool con il sì, e da nessun'altra
  parte. Nessun modulo nomina la costante dell'executor `NAMED` dentro la costruzione di un `AuditEvent` — il
  registro che non si oscura mai, e per un login il bag porta l'id di una voce del vault —, e nessun modulo
  dell'API la nomina affatto. È ancorata alla costante e non alla parola: `named` è anche il nome di una
  funzione di `ela.ports` e di un membro di `SessionGestures`, e una regola sulla parola li troverebbe.

Con questo ADR le regole di architettura sono **settantuno** (la 71); i contratti di import-linter restano
**quindici**, i port diventano **trentasei** (`TaskPages`), le rotte dell'API restano **settantadue** e i comandi
della CLI **trentanove**; le capability restano **diciotto**, le identità del middleware **sei**.

**Ciò che non è misurato, per nome**: perché WhatsApp Web, con il profilo di ELA, non va oltre la barra di
caricamento (§5, punto 9; `scripts/misura_m13_10.py`, decisioni 47 e 63); un login chiesto dal modello su un sito
vero, fino alla prova (passo 4 della sezione 29); che cosa resta, con la finestra, di un'ELA uccisa con una pagina
che aspetta.
