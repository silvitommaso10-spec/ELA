# 0065. Il browser a più passi: ogni elemento aspettato, ciò che il sì ha nominato, la pagina che dura fra gli step, il login chiesto dal modello

- **Stato:** Proposta il **2026-10-14**, con l'implementazione di M13.10, per diventare Accettata con un commit
  suo quando la prova a mano — la sezione 29 di `docs/GETTING_STARTED.md` — sarà passata sull'ultimo commit del
  branch (decisione 48 della review della SPEC di M13.10).
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
| `Browser` | §19 | async | `appeared` |
| `AccountBrowser` | §19 | async | `appeared` |

**Righe dei tool, riscritte.** Un ADR accettato non si riscrive: le righe di un tool che M13.10 cambia — un
codice d'errore in più o in meno, un numero dell'audit in più — si riscrivono qui **per intero**, e la riga
riscritta vince su quella dell'ADR che ha introdotto il tool, come `Capability estese:` fa per uno schema
(decisione 44 della review). I test delle righe degli ADR vecchi la leggono accanto alla loro.

Righe dei tool, riscritte:

| Capability | Tool | Nome | Idempotente | Codici d'errore | Numeri nell'audit |
|---|---|---|---|---|---|
| `browser.act` | `BrowserActTool` | `browser-act` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.not_installed`, `browser.secret_field`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `gestures`, `status`, `stopped_at` |
| `browser.act_as_you` | `AccountActTool` | `browser-act-as-you` | no | `arguments.invalid`, `browser.element_ambiguous`, `browser.element_missing`, `browser.failed`, `browser.http_status`, `browser.left_site`, `browser.not_installed`, `browser.profile_busy`, `browser.profile_undeclared`, `browser.profile_unsafe`, `browser.secret_field`, `browser.stopped`, `browser.timeout`, `browser.unreachable`, `browser.unsupported_system` | `gestures`, `status`, `stopped_at` |
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

## Conseguenze

- **Regola di architettura 71**: ciò che una domanda ha nominato arriva al tool con il sì, e da nessun'altra
  parte. Nessun modulo nomina la costante dell'executor `NAMED` dentro la costruzione di un `AuditEvent` — il
  registro che non si oscura mai, e per un login il bag porta l'id di una voce del vault —, e nessun modulo
  dell'API la nomina affatto. È ancorata alla costante e non alla parola: `named` è anche il nome di una
  funzione di `ela.ports` e di un membro di `SessionGestures`, e una regola sulla parola li troverebbe.

Con questo ADR le regole di architettura sono **settantuno** (la 71); i contratti di import-linter restano
**quindici**, i port **trentacinque**, le rotte dell'API **settantadue** e i comandi della CLI **trentanove**; le
capability restano **diciotto**, le identità del middleware **sei**.

*Il resto si scrive con il resto dell'implementazione.*
