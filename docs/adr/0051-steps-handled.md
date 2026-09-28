# 0051. Gli step di una corsa sono quelli che ha trattato: la parola dice ciò che il campo contiene, e il vuoto non dice chi ha chiuso il task

- **Stato:** Proposta. SPEC di M6.3b decisa dal revisore il 2026-09-28, con le domande 1–10, tutte
  (a). Diventa **Accettata** quando la prova a mano di `docs/GETTING_STARTED.md` §19 è passata.
- **Data:** 2026-09-28
- **Riferimenti spec:** §14, §15, §32, §62
- **Milestone:** M6.3b

## Contesto

ADR 0019 §10 ha scritto `Run(task, outcome, steps, executions)`: «gli step eseguiti *da questa
chiamata*, in ordine, e la parola dell'executor su ciascuno». M8.1 l'ha ripetuto nella docstring di
`RunOut`, che è la `description` dello schema OpenAPI («which steps it executed»), e M8.2
nell'etichetta di `ela task run`, `steps executed`. Nella prova a mano di M17.2b e M17.2c
(2026-09-27) `ela task run`, finito in `waiting_approval`, ha stampato sotto `steps executed` lo step
che aspettava il sì: quello step non era stato eseguito.

Il censimento di M6.3b (2026-09-28, sonde in `.git/m6.3b-reference/`) ha misurato che cosa contiene il
campo, ramo per ramo: il runner aggiunge uno step dopo ogni `Execution` che l'executor gli
restituisce — da `execute` o da `finish` — e che non è un passaggio a un nodo. «Eseguiti» è falso
per `waiting_approval`, `denied`, un fallimento prima dell'atto, `execution.interrupted`, e per gli
step chiusi da `finish` o ripresi dopo un crash. **Nessun consumatore legge il campo come «eseguiti»**:
l'unico chiamante di `run` è la rotta, che lo copia; l'unico che lo mostra è la CLI. In un punto la
parola ha deciso il contenuto: M12.2 ha lasciato fuori lo step affidato a un nodo perché la chiamata
«non ne ha eseguito niente» (`docs/milestones/M12.2.md:723`) — mentre uno step negato, di cui non ha
eseguito niente nemmeno lui, c'è. E la frase dopo, nello stesso paragrafo di ADR 0019 §10, dice che
«`Run.steps` vuoto è ciò che dice» se il task è stato chiuso alla porta o dalla chiamata: è falsa
nelle riprese R5 e R6.

## Decisione

### 1. Gli step di una corsa sono quelli che ha trattato

**Uno step è trattato da una chiamata quando l'executor, in quella chiamata, ha dato la sua risposta
su di lui**: l'ha eseguito; l'ha chiuso da ciò che un nodo ha consegnato o da ciò che un crash ha
lasciato; l'ha fallito — prima dell'atto, dopo, o senza sapere se l'atto c'è stato —; il Guardian
l'ha negato; oppure si è fermato a chiedere il consenso. **Uno step affidato a un nodo non è
trattato**: la risposta la darà il nodo, e `reason` lo nomina. **Uno step che aspetta un nodo non è
trattato**: in questa chiamata l'executor non l'ha visto.

La riga della CLI si chiama **`steps handled`**; la prosa dice «gli step trattati». **Il campo non
cambia**: la definizione è vera per ogni esito perché è la condizione con cui il runner costruisce la
lista — `steps.append` dopo ogni `Execution` senza assegnazione, e `finish` non ne restituisce mai
una. Dopo `waiting_approval`, `denied` e `failed` l'ultimo step della lista è quello su cui la
chiamata si è fermata. Il contenuto che M12.2 ha scelto per `ASSIGNED` resta; cambia la sua ragione.

La definizione sta nella docstring di `RunOut` — la `description` dello schema —, in quella di `Run`
e nell'help di `ela task run`; quella inglese dice «ran» e mai «executed». La tengono
`tests/api/test_run_steps.py`, un caso per ramo a mondo chiuso su `RunOutcome` con lo schema, e
`tests/cli/test_run_steps.py`, lo stesso sulla CLI, con la parola scritta nel test e non letta dal
codice.

### 2. Il vuoto non dice chi ha chiuso il task

`Run.steps` vuoto dice che la chiamata **non ha trattato step**. Non dice se il task era già chiuso
quando `run` è stata chiamata: nelle riprese R5 e R6, e dopo una consegna che la rotta del nodo ha
già chiuso, la chiamata chiude il task senza trattare step, con la lista vuota come alla porta. Chi ha
chiuso il task sta nell'audit.

### 3. I nomi dei test

`test_a_run_executes_each_step_at_most_once` diventa `test_a_run_handles_each_step_at_most_once`, e
`test_every_executed_step_was_placed_and_started_on_the_same_node` diventa
`test_every_handled_step_was_placed_and_started_on_the_same_node`. La citazione di ADR 0019 §3 si
legge con il nome nuovo. `tests/docs/test_adr_run_steps.py` verifica che ogni test citato qui esista,
perché una citazione che non punta a niente è quella che ADR 0019 §3 ha tenuto per tre milestone.

### 4. La guida mostra ciò che la CLI stampa

Ogni blocco d'uscita di `ela task run` in `docs/GETTING_STARTED.md` è quello che la CLI produce: le
sue etichette, `RUN_LABELS`, nel suo ordine, alla sua larghezza, con le quattro righe che stampa
sempre. Lo confronta `tests/docs/test_getting_started.py`: un'etichetta che cambia nella CLI cambia
nella guida, o la suite si ferma. §6 aveva due id sotto `steps executed` e subito sotto la frase che
diceva che il secondo non era girato.

### 5. Le righe dei documenti vecchi da leggere con questa accanto

- **ADR 0019 §10**, «gli step eseguiti *da questa chiamata*»: si legge con §1.
- **ADR 0019 §10**, «`Run.steps` vuoto è ciò che dice quale dei due è successo»: si legge con §2.
- **ADR 0019 §10**, la riga `DENIED`, «il Guardian ha negato uno step; il task è DENIED e nulla è
  girato»: il task è negato dal Guardian **o dal no dell'utente**, e lo step negato non ha girato;
  quelli prima possono averlo fatto.
- **ADR 0019 §3**, il nome del test: si legge con §3.
- La riga «Stato:» di ADR 0019 nomina ADR 0038 §10, ADR 0038 §16 e questo ADR — le revisioni che ha,
  non solo l'ultima.

Nei documenti di milestone le frasi si annotano: `M6.3.md` (§7.6, l'Esito), `M8.1.md` (decisione 3a),
`M12.2.md` (la tabella di `ASSIGNED`, e la citazione del test).

## Alternative considerate

- **Restringere il campo agli step eseguiti** — la seconda strada della registrazione. Scartata dal
  revisore: il dato è vero, e in `waiting_approval` l'id dice su quale step ELA si è fermato a
  chiedere; il censimento non ha trovato un consumatore che la giustificasse.
- **Far entrare lo step affidato a un nodo.** Un cambio di contenuto, che rivede la scelta di M12.2
  per un dato che `reason` porta già.
- **Le altre parole**, ciascuna con un controesempio misurato: «eseguiti» (sopra), «tentati» (uno step
  chiuso da una consegna o ripreso: la chiamata non ha tentato, ha chiuso), «consegnati all'executor»
  (`assigned`: lo step passa per `execute` e resta fuori), «raggiunti» (`assigned` e `waiting_device`),
  «chiusi» (`waiting_approval`: lo step resta `RUNNING`). `answered` si scontra con la risposta
  dell'utente a una domanda; `decided` con la decisione del Guardian, e uno step ripreso non ne ha una
  in questa chiamata; `processed` dice che il lavoro è finito.
- **L'obiezione a `handled`**: vuol dire anche «sbrigato», e copre anche «passato ad altri», che è
  `assigned`. Di tutte le parole vere per ogni ramo è quella che promette meno; sta sotto una riga
  `outcome` che dice se la corsa aspetta, accanto a un `reason` che dice a chi è andato lo step; e la
  sua definizione sta dove un test la legge.

## Conseguenze

- La colonna di `ela task run` passa da 16 a 15 caratteri, e ogni blocco d'uscita della guida si
  riallinea. I blocchi di §12, che sono gli output della prova del 2026-09-17, sono riscritti come la
  CLI li stampa oggi, con una nota datata che continua la frase fissata da
  `tests/docs/test_adr_nodes_windows.py`; il trascritto ha l'uscita di allora.
- Le frasi vecchie negli stessi testi sono corrette con la parola (decisione 6 di M6.3b): la ragione
  di `run` — `RunOut.reason` e l'help — dice ciò che è vero oggi, cioè che `denied` e `failed` la
  portano **quando la chiamata l'ha ricevuta**; la `description` di `POST /tasks/{id}/run` nomina
  `assigned`; `RunOutcome.DENIED` e `Execution.assignment` non dicono più «nothing ran» e «ran
  something».
- Due riparazioni trovate e non prese, registrate con la loro proprietaria: **M13.1c** (in quattro
  rami di `run` la ragione di un diniego o di un fallimento manca) e **M6.3c** (un task fermato mentre
  il suo tool gira fa rispondere `run` con un `409` e lascia lo step `RUNNING`; l'effetto compiuto resta
  scritto).
- Nessuna regola architetturale nuova: è una parola, e la tengono i test sopra.
