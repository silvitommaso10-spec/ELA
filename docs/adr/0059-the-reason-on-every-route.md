# 0059. La ragione di una fine su ogni rotta che porta lo stato di un task: una lettura sola nell'engine, chi ha detto no col nome del registro, e sotto il tetto solo parole di ELA

- **Stato:** **Proposta**. Aperta il 2026-10-08 con l'implementazione di M13.1e, dopo la SPEC decisa lo stesso giorno
  (le decisioni A–F della sessione e 1–8 della review, in `docs/milestones/M13.1e.md`). Si accetta quando la prova a
  mano della sezione 25 di `docs/GETTING_STARTED.md` passa sul Mac e sul telefono, con `scripts/prova_m13_1e.py` (§10).
- **Data:** 2026-10-08
- **Riferimenti spec:** §14, §32, §33, §57, §62, §64, §65
- **Milestone:** M13.1e

## Contesto

ADR 0045 §12-bis ha scritto la regola: **ogni superficie umana che riporta un fallimento o un diniego mostra il suo
perché**. ADR 0055 l'ha fatta mantenere a `ela task run`: la ragione di ogni fine che non è `completed` è il sommario
dell'evento d'audit della transizione che ha chiuso il task, letta da una funzione sola, `TaskRunner._reason`. Le
superfici che guardano il lavoro dopo — il riepilogo e la home della console, la home del telefono, `ela task show`,
`ela task finished`, `ela task list`, le risposte di `deny` e `cancel` — mostravano lo stato e basta: `TaskOut`,
`TaskDetail` e `FinishedTaskOut` non avevano un campo ragione, e una pagina compone solo ciò che una rotta le dà (la
regola 55), la CLI parla solo HTTP (la regola 28). `GET /tasks/{id}` la ragione la calcolava già, attraverso
`planner.view`, e la buttava.

Il no si riportava con l'id dell'identità che aveva risposto — «rejected by 6c38f1c5-…» —, che a una persona non dice
niente. Il censimento della SPEC ha trovato che la console e il telefono rispondono con la loro riga del registro dei
dispositivi, che le righe revocate restano, e che l'id di `LOCAL_USER` è l'id della riga `local`. E un fatto che la
registrazione non vedeva: **la ragione è contenuto**. Il diniego del Guardian nomina bersagli e scope, un errore
percorsi e siti, il «ferma» della CLI le parole dell'utente — ciò che il tetto del telefono, e della console da
lontano, tiene sul Mac (F2-a di ADR 0043).

## Decisione

### 1. Una lettura sola: `ela.tasks.ending`, composta da `TaskEngine.ending`

**La derivazione pura sta in `ela.tasks.ending`**, accanto a `ela.tasks.halt`: `REASONED` — ogni stato finale tranne
`COMPLETED`, l'insieme che il runner usava da M13.1c e che ora tutti leggono da qui —, `of_the_audit` e `of_the_trail`.
La regola è quella di ADR 0055 §1, invariata: l'evento d'audit il cui `payload.new_state` è lo stato del task, e senza
quella riga — la finestra di un crash fra la trail e l'audit — lo `STATE_CHANGED` della trail con il nome dell'operazione,
poi lo stato stesso. Mai vuota.

Dallo **stesso evento** escono, senza comporre niente: `reason`, il sommario; `operation`, chi ha chiuso il task;
**`code`, il codice che il payload porta, dovunque ne porti uno** — il codice di un fallimento, `orphaned`, lo
`spending.*` del tetto, e così ogni operazione che ne scriverà uno —, mai da un elenco di operazioni; `responded_by`, chi
ha detto no, dal payload di `deny_by_approval`.

**Il lettore con i port è `TaskEngine.ending(task)`**: l'engine ha il repository e l'audit, e scrive le parole e le
chiavi che legge. Per un task negato dalla sua pianificazione segue `planning_task_id` fino al figlio, e chi ha detto
no al figlio è chi ha detto no: per struttura, mai leggendo la stringa. **La chiamano il runner** (`_reason`, e
`_transition_reason` non c'è più), **il Planner** (`view` e `_close`, che leggevano `runner.answer(…).reason` e con lei
`halt`, che non serviva) **e le rotte**.

### 2. `end` su `TaskOut`, contro la decisione 3 di M6.3c

**`TaskOut.end: EndOut | None`**, su ogni rotta di `docs/outcomes.txt` — e quindi su `FinishedTaskOut`, `TaskDetail`,
`RunOut.task` e `PlanningOut` —; `None` per un task vivo o `COMPLETED`. `EndOut` porta `reason`, `operation`,
`reason_code` e `answered_by`. `TaskOut.of(task, end)` non ha un default: una rotta che lo dimenticasse è un errore di
mypy. `RunOut.reason` e `PlanningOut.reason` restano, uguali a `task.end.reason` per lo stesso task.

**Il codice sul filo si chiama `reason_code`**: la regola 46 tiene la parola nuda, nei modelli dello schema, per il
codice con cui un nodo si arruola, e una regola di sicurezza non si allarga per un nome.

**La decisione 3 di M6.3c si rivede per la ragione, apertamente**: `halt` non sta su `TaskOut` perché vale per un
`CANCELLED` solo e costa la trail, l'audit e una presa per riga, e per `halt` resta così. La ragione è ciò che rende
leggibile un `DENIED` o un `FAILED` a chi lo guarda dopo, `ela task deny` ed `ela task cancel` mostrano proprio quel
task, e la decisione A della sessione la vuole su ogni rotta. Il costo è misurato (§6).

### 3. Chi ha detto no: il nome del registro, risolto dalla rotta

**L'audit resta com'è**: «rejected by `<id>`» nella ragione, `responded_by` nel payload. L'engine non compone nomi.
La rotta risolve l'identità che `ending` le dà, in quest'ordine, in `AnswererOut` — `identity`, `name`, `role` —:

1. **l'id di `LOCAL_USER`** → il nome fisso **`the command line on the Core`** e il ruolo `LOCAL`, **prima** del
   registro, perché la riga `local` c'è e si chiama `local`;
2. **una riga del registro**, revocata compresa — la riga resta (ADR 0037), e il nome è quello che aveva quando ha
   risposto: i nomi di telefono e console non si riscrivono — → il suo nome e il suo ruolo, `CONSOLE` o `COMPANION`; una
   riga di un altro ruolo, che a una domanda non risponde, il nome e nessun ruolo;
3. **un id che il registro non ha, o un valore che non è un id** — `responded_by` prima di M12.1 era `ELA_USER_NAME`,
   «user» per default (ADR 0037 §15) — → l'id da solo, senza nome e senza ruolo.

**`LOCAL_USER` vuol dire chi ha il token del Core** — la CLI, gli script delle prove, qualunque processo di questa
macchina che legge il `.env` —, e **il nome fisso dice la riga di comando perché è da lì che una persona risponde**. È
nella lingua dell'API, come «rejected by».

### 4. Sotto il tetto solo parole di ELA, mai parole scritte da qualcuno

**La regola**: dove una pagina non può mostrare il contenuto di un task — il telefono per un task `LOCAL_ONLY`, la
console da lontano —, della sua fine mostra **l'operazione, il codice e il ruolo di chi ha risposto**, che sono il
vocabolario di ELA, e **niente che qualcuno abbia scritto**: non il messaggio della fine, che nomina bersagli, scope,
percorsi, siti e le parole di un fermo; non il nome di un dispositivo, che l'utente scrive all'arruolamento e che può
essere personale, come `machine` di una domanda. Sopra il tetto, la ragione intera, e il nome con il ruolo accanto.

Le pagine scrivono il ruolo nel loro vocabolario: `LOCAL` «la riga di comando», `CONSOLE` «la console», `COMPANION`
«il telefono». Sotto il tetto il telefono mostra, per esempio, «`deny_by_approval` · ha risposto: la console», o
«`fail · browser.element_missing`». **Il codice resta sempre**: nessun taglio lo toglie, è ciò che si cerca. Un'identità
senza ruolo, sotto il tetto, non dice chi ha risposto.

### 5. Che cosa mostra ogni superficie

- **La CLI**, sul Core e sopra ogni tetto: nelle righe di un task, dopo `state`, la riga `reason` — `—` per un task che
  non è finito con una ragione — e, per un no, `answered by`: il nome con il ruolo accanto, `<nome> (console)` o
  `<nome> (phone)`, il nome fisso da solo per il token del Core, l'id quando il nome manca. Sotto le tabelle di
  `finished` e `list`, che non cambiano, la tabella **`why`**: l'id, la ragione, chi ha risposto. `run` e `plan`
  prendono la riga `answered by` dopo `reason`, per un no soltanto; `RUN_LABELS` non cambia. L'help di `show`,
  `finished` e `list` dice la frase forte di M13.1c.
- **La console**: nel riassunto le coppie «Perché» e «Ha risposto» dopo «Stato»; nella home, la riga del task finito
  porta una didascalia con il perché e chi ha risposto. Da loopback tutto; da lontano la forma di §4.
- **Il telefono**: la stessa didascalia nella riga fra i «Finiti», nella forma che il tetto permette.

Una funzione sola per le due pagine, accanto a `halt_phrase` e `may_see`; un frammento nuovo, `why.html`, nelle due
cartelle di `apps/`, con la classe `ela-caption` di `halt`: nessuna classe nuova nel design system.

### 6. Il costo, e la risposta se pesa

Misurato il 2026-10-08 nella sessione cloud della SPEC, dentro il giro (ADR 0052 §16): circa **1,9 ms per ragione**,
una lettura dell'audit per task con una ragione — due per un padre negato dalla pianificazione —, lineare. Alle liste
delle pagine, da 11 a 19 ms; `ela task list` senza filtro cresce con la storia, e sul Mac al 2026-10-01 i task con una
ragione erano 28. **Un test conta le letture**, non i millisecondi: una lista fa al più una lettura dell'audit in più per
ogni task con una ragione, e una per un padre negato dalla pianificazione. Una soglia di tempo, su questa macchina, non
si fissa.

**Se pesa, la risposta che tiene la ragione derivata** — gli stati derivati e non memorizzati sono una decisione fissa
del design — è un parametro di `AuditLog.read`, `task_ids`, una query con `task_id IN (…)` sull'indice che c'è: un
parametro e non un membro, come `newest_first` (ADR 0025 §3). **Non è costruito.** Si riapre con la misura che la prova
prende sul database vero del Mac (§10).

### 7. La regola 64

**La regola 64, `the-end-has-one-reader`**: fuori da `ela.tasks.engine`, che scrive il payload delle transizioni, e da
`ela.tasks.ending`, che lo rilegge, nessun modulo di `src/` nomina la chiave `new_state` come stringa. Un'euristica sulle
stringhe come le regole 16, 17 e 62: `TaskEvent.new_state`, l'attributo della trail, è un nome, e `ela.tasks.halt` lo
legge per un altro fatto.

### 8. Il protocollo di `docs/outcomes.txt`, per la ragione

Come per `halt` (ADR 0054 §8): **ogni lettore del file mostra la ragione di un task finito, o il documento della
milestone dice perché no**, per il lettore intero o per uno stato che non raggiunge. Il test deriva i lettori dal file,
rende ogni pagina davvero, con l'identità che vuole, e fa girare ogni comando, con un task in ogni stato di `REASONED`
raggiunto come lo raggiunge la produzione; le righe «perché no» stanno in `docs/milestones/M13.1e.md`, «Le viste che non
dicono la ragione». E **un test chiuso sulla tabella `OPERATIONS`** dell'engine: ogni operazione che chiude un task in
uno stato di `REASONED` ha un caso che la produce e ne legge `end` attraverso la rotta.

### 9. Righe riviste

Gli ADR non si riscrivono: queste righe si leggono con questo accanto, e lo Stato di ciascuno rimanda qui.

- **ADR 0055 §1**: «Una fonte sola, `TaskRunner._reason`» — da M13.1e la lettura sola è `ela.tasks.ending`, composta da
  `TaskEngine.ending`, e il runner la chiama come le rotte; «il nome del dispositivo è la domanda aperta di M13.1e» —
  chiusa da §3 e §4.
- **ADR 0045 §12-bis**, come ADR 0055 §6 l'aveva riletto: «le altre superfici sono di M13.1e» — fatto: ogni lettore di
  `docs/outcomes.txt` mostra il perché, o dice perché no.
- **ADR 0054 §8**: il protocollo di `docs/outcomes.txt` vale anche per la ragione (§8).

E fuori dagli ADR, **la decisione 3 di M6.3c** (`docs/milestones/M6.3c.md`): `halt` resta fuori da `TaskOut`, la ragione
no (§2).

### 10. La prova a mano

La sezione 25 di `docs/GETTING_STARTED.md`, con lo script `scripts/prova_m13_1e.py`, **sul Mac e sul telefono, senza il
PC**: tre no — dalla riga di comando, dalla console, dal telefono —, un fallimento dopo un sì con `browser.act` su un
bottone che `example.com` non ha, un fermo con `ela task cancel`, e la misura del costo sul database vero; nessuna
chiamata al modello, nessuna voce. `EXPIRED` lo prova la suite. **Da fare.**

## Alternative considerate

- **La forma di `halt`**: il campo su `TaskDetail`, `FinishedTaskOut` e `RunOut`, non su `TaskOut`, con una riga «perché
  no» per `deny`, `cancel` e `list`. Scartata (domanda 1 della SPEC): `deny` e `cancel` mostrano proprio il task negato
  e fermato, e la decisione A vuole ogni rotta.
- **Il runner reso pubblico** come lettore, `ela.runner.reason(task)`. Scartata: la decisione A dice «si sposta», e un
  runner non ha niente da camminare in una lettura.
- **Il nome dentro la ragione**, composto dall'engine. Scartata (decisione D): l'audit resta il fatto, e i nomi sono del
  registro.
- **La ragione intera sotto ogni tetto.** Scartata (decisione 2 della review): il telefono vedrebbe bersagli, scope,
  percorsi e le parole di un fermo di un task che il tetto tiene sul Mac.
- **Il nome del dispositivo sotto ogni tetto**, come `halt`. Scartata (decisione 2): è scritto dall'utente e può essere
  personale.
- **Il parametro `task_ids` adesso.** Rimandato (§6): alle misure di oggi la lettura per task non pesa.
- **Un campo `code` sul filo**, come nel payload. Scartato (§2): la regola 46.

## Conseguenze

Con questo ADR le regole di architettura sono **sessantaquattro** (la 64), i contratti di import-linter restano
**quindici**, i port restano **trenta**, le rotte dell'API restano **cinquantuno** e i comandi della CLI restano
**ventotto**. Nessuna migrazione: la ragione si deriva a ogni lettura.

Ciò che questo ADR dichiara e non risolve:

- **`ela task list` senza filtro legge l'audit una volta per ogni task finito con una ragione**: lineare nella storia;
  la risposta, se pesa, è scritta in §6.
- **Una fine scritta nella finestra di un crash** ha la ragione della trail, senza codice e senza chi ha risposto: l'id
  resta dentro le parole.
- **Un nome non è unico**: l'id resta accanto, dentro la ragione.
- **Un gettone senza spazi più largo dello schermo del telefono** — un percorso molto lungo in una ragione mostrata
  sopra il tetto — va oltre il bordo della riga: la didascalia è quella di `halt`, e il design system non cambia.
- **Chi ha fermato un task** non ha un nome: le parole della console e del telefono dicono da dove, e per la CLI c'è
  l'`actor` dell'audit.
