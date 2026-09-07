# 0025. I debiti di Fase 8: tre port che non riportano righe inutili, `ELA_NOTES_SCOPE` e `ELA_DECISION_TTL_SECONDS`, l'output di un tool che esce dall'API, regola 29

- **Stato:** Accettata. SPEC di M8.3 approvata dall'utente: decisioni **1a, 2a, 3a, 4a, 5, 6a
  (un'ora), 7a, 8a, 9a** come proposte, con la chiave del commento chiamata `_nota` invece di
  `_perche` e `extra="ignore"` **dichiarato** e non ereditato. Le due esclusioni (8b, 9b)
  confermate, con la richiesta di scrivere qui (§9) che il passaggio di dati fra step è il primo
  limite che un utente incontra davvero. Due cose sono cambiate in implementazione, ed entrambe
  sono argomentate dove valgono: `ELA_NOTES_SCOPE` sta in `CoreSettings` e non in
  `WorkspaceSettings` (§5), e il lettore unico della regola 29 è `api/schemas.py` e non
  `api/results.py` (§4).
- **Contesto:** M8.3, la milestone che paga i rinvii di Fase 8.
- **Riferimenti spec:** §13, §14, §16, §25, §27, §29, §32, §34, §54, §57, §58, §63
- **Sostituisce:** ADR 0010 §5 nella sola affermazione che `DEFAULT_NOTES_SCOPE` sia una
  costante — la riga del catalogo non cambia, cambia da dove viene il valore (§5 qui sotto).

## Contesto

Fase 8 ha dato a ELA un processo (M8.1, ADR 0023) e una riga di comando (M8.2, ADR 0024). Le ha
date rinviando, ogni volta con il rinvio scritto in un vincolo dichiarato, ciò che avrebbe
trasformato quelle due milestone in contenitori. `docs/milestones/M8.3.md` ha raccolto quei
rinvii; questo ADR registra quali sono stati pagati e con quale forma.

## 1. Il criterio: che cosa è un debito

**Entra un rinvio se oggi c'è codice che fa la cosa nel modo sbagliato. Resta fuori se oggi non
c'è codice affatto — allora non è un debito, è una milestone.**

È il criterio con cui M8.3 ha scelto, ed è scritto qui perché serva di nuovo. Con quel criterio
il **loop autonomo che richiama `run()`** resta fuori: nessuna riga di ELA oggi lo fa male,
semplicemente non c'è, ed è il primo pezzo del Proactive Core (§34). Un ciclo che esegue senza
che nessuno abbia appena chiesto qualcosa merita la sua milestone e la sua discussione sul
Guardian come unica cosa in mezzo (§47), non una riga in una milestone di manutenzione. Con lui
restano fuori `recover()` periodico, l'heartbeat periodico del nodo `local` e `--follow` nella
CLI, che sono tutti lo stesso ciclo visto da tre parti. La registrazione dei nodi via API resta
fuori per lo stesso motivo, con una ragione in più: porta con sé l'autenticazione **per nodo**,
che è la Fase 12 per intero.

## 2. `TaskRepository.count`: contare senza portare indietro le righe

`GET /diagnostics` contava i task per stato **leggendoli tutti** (`repository.tasks()`), il che va
bene con dieci task e non con diecimila. Il port lo dice adesso da sé:

```python
async def count(self, *, states: frozenset[TaskState] | None = None) -> Mapping[TaskState, int]
```

**Contratto.** Una voce per ogni stato che ha **almeno un** task, mai una voce a zero: la risposta
dice che cosa c'è, e uno stato che nessuno ha raggiunto non è un fatto che meriti una riga.
`states` restringe la domanda (`None` la fa su tutti); un `frozenset()` **vuoto** è una domanda su
nessuno stato e risponde con una mappa vuota — l'unico caso in cui `frozenset()` e `None` non si
equivalgono, e il motivo per cui il contratto lo scrive. Nessun `limit`: contare i primi N di
qualcosa non è un conteggio.

L'adapter SQL fa `GROUP BY state`, quindi uno stato senza task non produce nessun gruppo e il
contratto è ciò che il database restituisce, non ciò che l'adapter filtra dopo.

**Ciò che `/diagnostics` stampa non cambia di un carattere.** È così che si riconosce un debito:
la correzione è invisibile a chi la usa.

## 3. `AuditLog.read(newest_first=…)`: la coda è l'altro capo

`ela audit tail -n 20` vuole gli **ultimi** venti; `read(limit=)` dava i **primi** venti in ordine
di append, e la CLI leggeva la finestra filtrata per intero e ne tagliava la coda (vincolo
dichiarato di ADR 0024 §6). Su un registro che per definizione non si accorcia mai, quello è il
debito gemello del §2.

Un **parametro**, non un membro:

```python
async def read(self, *, task_id=None, since=None, limit=None, newest_first: bool = False)
```

**Contratto.** I filtri si applicano prima, come già facevano. `newest_first` sceglie da **quale
capo** comincia la lettura, e la tupla è sempre nell'ordine in cui è stata letta: ordine di append
per default, quindi `limit` tiene le **prime** voci; dalla fine quando è `True`, quindi `limit`
tiene le **ultime** e la tupla va dalla più recente alla più vecchia. Nell'adapter la direzione è
l'`ORDER BY`, così il `LIMIT` prende le righe dal capo giusto e il database non legge mai l'altro.

**Un parametro e non un terzo membro** perché il docstring del port, ADR 0007 e un architecture
test promettono che `AuditLog` abbia `append` e `read` e nient'altro. Quella promessa vale perché
il numero è piccolo; un terzo membro *di lettura* la indebolirebbe senza dare niente che il
parametro non dia. La promessa regge: `AuditLog` ha ancora due membri.

`GET /audit` prende `newest_first` come query parameter e lo passa. `ela audit tail` chiede
`limit=n&newest_first=true` e **inverte per stampare**, perché una coda si legge dal vecchio al
nuovo anche quando la si prende dal nuovo al vecchio.

## 4. Gli `ExecutionResult` escono dall'API, e la regola 29

ADR 0023 rinviava la domanda dicendo: «va deciso **dove** esce, perché è contenuto dell'utente
(§57) e non è audit». Questa è la risposta.

Il motivo per cui si decide adesso è concreto e viene dal primo giro a mano dell'utente. M8.3
aggiunge `docs/examples/ask-model.json`, un piano con uno step `model.complete`. Con la chiave,
quel piano **completerebbe e non mostrerebbe niente**: la risposta del modello finisce in
`ExecutionResult.output`, nel database privato, e nessun comando la legge. Un utente che chiede a
ELA di rispondere a una domanda e non vede la risposta non conclude che manca una rotta: conclude
che ELA non funziona.

**Tre pezzi.**

1. **Un membro sul port:** `ExecutionResultStore.for_task(task_id) -> tuple[ExecutionResult, ...]`
   in ordine di inserimento, vuota se non c'è niente. È un membro e non un giro su `for_step`
   perché l'alternativa è una query per ogni step del piano. Un id di task che non esiste dà una
   risposta vuota e non `NotFoundError`: questo store tiene risultati, non task.
2. **Una rotta:** `GET /tasks/{task_id}/results`, in `ela/api/results.py`. Legge **prima** il task,
   così un id che nessuno conosce è un `404` e non una lista vuota — «questo task non ha
   risultati» e «questo task non esiste» sono risposte diverse, e chi non può distinguerle deve
   indovinare.
3. **Un comando:** `ela task results <id>`. La tabella dice quale step ha prodotto che cosa e come
   è finito; sotto, ogni risultato che ha un output lo mostra **per intero**. Niente viene
   accorciato: la risposta di un modello è la ragione per cui il comando esiste, e una risposta
   troncata non lo è.

**Regola 29 — dentro `ela/api/`, ciò che un tool ha prodotto ha un modello solo e un lettore
solo.** Sono riportati: un campo di classe chiamato `output` in qualunque modulo di `ela.api` che
non sia `ExecutionResultOut`, e il nome `output` — attributo, variabile, keyword o stringa — in
qualunque modulo di `ela.api` che non sia `schemas.py`.

È il **rovescio della regola 23**: la 23 dice dove il contenuto dell'utente non può *entrare* (un
`AuditEvent`), la 29 dice da dove può *uscire*. Senza di lei, un campo `output` aggiunto domani a
`StepOut` o a `AuditEventOut` porterebbe lo stesso contenuto fuori attraverso una rotta che non è
mai stata pensata per portarlo, e nessun tipo protesterebbe.

**Perché il lettore unico è `schemas.py` e non `results.py`**, che è quello che la SPEC diceva:
`ela/api/schemas.py` è il posto dove **ogni** forma sul filo è dichiarata, e il suo docstring
spiega perché — «la forma sul filo è una decisione». `ExecutionResultOut` sta lì con tutte le
altre; spostarla nella rotta per far tornare la regola avrebbe piegato un principio dichiarato a
una comodità di verifica. La rotta resta un modulo suo, perché la ragione per cui questa è
l'unica che restituisce contenuto merita un docstring e non un paragrafo dentro `tasks.py`.

**Obiezione onesta:** oggi la regola 29 protegge una riga sola, e sembra sproporzionata. La regola
23 esisteva prima che ci fosse un secondo posto da cui gli `arguments` potessero uscire, ed è per
questo che quel secondo posto non è mai esistito.

## 5. `ELA_NOTES_SCOPE`: lo scope del catalogo diventa configurazione

ADR 0010 §5 dichiarava `DEFAULT_NOTES_SCOPE = "workspace/notes"` una **convenzione finché la
Configuration non la legge dall'ambiente**. M8.1 non l'ha presa perché è una modifica al catalogo
e non alla composizione. M8.3 la prende: il composition root passa
`catalogue_v01(notes_scope=settings.core.notes_scope)`, che è il parametro che
`catalogue_v01` accettava già.

**La riga del catalogo non cambia.** Scope, argomento sotto scope, rischio, schema e flag di
`workspace.write_note` sono quelli di ADR 0010: cambia da dove viene il valore, non quale valore
è. Per questo non c'è nessuna tabella «Capability estese:» qui — non c'è niente da riscrivere — e
quello che ADR 0010 §5 dice sulla costante è l'unica frase che questo ADR sostituisce.

**Dove sta la variabile, e perché non dove sembrerebbe.** `notes_scope` è un percorso dentro il
workspace e starebbe bene accanto a `ELA_WORKSPACE_DIR` in `WorkspaceSettings`. Sta invece in
`CoreSettings` perché ciò che configura è il **catalogo**: validarla vuol dire chiedere a
`is_valid_scope_entry` se è una voce di scope ben formata, e `ela.tools` importa oggi soltanto
`ela.domain` e `ela.ports` — un tool implementa una capability, non possiede il catalogo. Copiare
la regola dentro `ela.tools` per evitare l'import lascerebbe **due definizioni** di «scope
valido», che è peggio di una variabile nella seconda classe migliore.

**Un valore malformato ferma l'avvio**, non viene corretto: relativo, nessun segmento vuoto,
nessun `.` o `..`, nessun backslash. Il messaggio nomina la variabile, perché chi lo legge ha
scritto un `.env` e non una capability.

**Conseguenza da dichiarare:** cambiare `ELA_NOTES_SCOPE` su un'ELA che ha già girato **non
sposta le note già scritte** e mette fuori scope le autorizzazioni date per percorsi nel vecchio
scope. Il Guardian farà la cosa giusta — nega ciò che è fuori scope — e lo farà senza spiegare
che è colpa di una variabile cambiata. Sta nel `.env.example` accanto alla variabile, perché è il
tipo di sorpresa che si scopre alla prima negazione.

## 6. `ELA_DECISION_TTL_SECONDS`, con un tetto di un'ora

`DEFAULT_DECISION_TTL` sono cinque minuti (ADR 0011 §9) e `PermissionGuardian` accettava già il
parametro. Diventa `ELA_DECISION_TTL_SECONDS` in `CoreSettings`, con un tetto —
`MAX_DECISION_TTL`, **un'ora** — accanto al default in `guardian.py`, come per gli altri due
(`MAX_AUTHORIZATION_TTL` 24 ore, ADR 0012; `MAX_APPROVAL_TTL` 7 giorni, ADR 0013).

**Perché un'ora, per esteso.** Una `PermissionDecision` è una risposta data **in un contesto**, e
un contesto che dura un'ora è già più lungo di qualunque cosa ELA stia facendo adesso. Oltre, non
è più una decisione: è un permesso — e i permessi hanno già un'entità loro, che è
`Authorization`, con il suo grant, il suo conteggio degli usi e il suo audit. Un TTL senza tetto
lascerebbe la più effimera delle due sopravvivere in silenzio alla più duratura.

## 7. Le due letture dalla riga di comando

`ela audit tail` chiede gli ultimi `n` all'API invece di leggere tutto e tagliare (§3), e
`ela task results` è il diciottesimo comando (§4). Nessun altro cambiamento alla CLI: resta un
client dell'API, con gli stessi quattro codici di uscita di ADR 0024 §6.

## 8. Gli esempi e la guida: i tre debiti del primo giro a mano

Nessuna review li aveva visti. Li ha visti l'utente, la prima volta che ha seguito
`docs/GETTING_STARTED.md` su una macchina vera — che è l'unica volta in cui ELA è stata usata da
qualcuno che non l'aveva scritta.

**8.1 — I segnaposto.** La guida scriveva `ela task run <id>` e non diceva da nessuna parte che
le parentesi angolari non si incollano. L'utente le ha incollate, ed è un difetto della guida, non
della lettura. Adesso un riquadro **prima** della prima sezione dichiara la convenzione una volta,
e la prima occorrenza è mostrata **già sostituita** con l'id vero stampato due righe sopra: la
convenzione si vede oltre a leggersi. Un test raccoglie ogni `<…>` dai blocchi di codice della
guida e pretende che sia uno di quelli che il riquadro nomina, così un segnaposto nuovo e non
spiegato fa fallire `make check` invece di aspettare il prossimo lettore.

**8.2 — Il rischio dichiarato dall'esempio.** `docs/examples/first-task.json` dichiarava
`"risk": "MEDIUM"` sullo step `workspace.write_note`, mentre §29 e il catalogo dicono **LOW**.
Vale la pena scrivere che cosa fa davvero quel campo, perché non è ovvio:

- **Il Guardian non lo legge mai.** Prende il rischio dal catalogo (`risk = registered.risk`) e
  rifiuta perfino una `CapabilitySpec` che differisca da quella registrata (ADR 0011 §2).
- **Chi lo legge è il Device Orchestrator**, che da `UNGUARDED_RISK` (HIGH) in su scarta un nodo
  DEGRADED (ADR 0017 §4) e scrive quel valore nei metadati della collocazione.
- Quindi il `MEDIUM` non cambiava nessun comportamento, ma era una **dichiarazione falsa** che
  finiva nella tabella di `ela task show` e nell'audit di una scelta.

E ciò che ferma davvero lo step è l'altra cosa: `workspace.write_note` è LOW con
`requires_authorization=False` — è lo **scope** che la protegge — e il consenso viene chiesto
perché lo **step** lo chiede, con il proprio `requires_authorization`. Il Guardian domanda
un'autorizzazione quando la spec **o** lo step ne vogliono una. È la cosa più interessante del
sistema di permessi, ed è quella che l'esempio adesso dice di sé: **un piano può alzare
l'asticella su sé stesso, non abbassarla.** La guida diceva «scrivere è MEDIUM (§29)» tre sezioni
sopra un registro che stampa `ALLOWED workspace.write_note (LOW)`; adesso dice la cosa giusta,
che è anche la più istruttiva della pagina.

**8.3 — Il commento dentro un file JSON.** JSON non ha commenti, e questi file sono mandati
all'API **byte per byte** da un test, quindi la spiegazione deve sopravvivere al viaggio. Una
chiave di primo livello **`_nota`** è quella spiegazione. Perché è sicuro farlo: `PlanIn` e
`StepIn` dichiarano `model_config = ConfigDict(extra="ignore")` — **dichiarano**, non ereditano
il default di pydantic — perché un comportamento su cui un file su disco fa affidamento non può
essere un default che qualcun altro può cambiare. Un test manda il file *con* la chiave.

**8.4 — `docs/examples/ask-model.json`.** Un piano con un solo step `model.complete`, per quando
il provider avrà la chiave: `task_type` è una delle rotte della tabella di §25 (uno fuori tabella
fallisce con `routing.unknown_task_type` **prima** della rete), il rischio dichiarato è quello del
catalogo, e `requires_authorization` non serve dichiararlo perché la capability lo richiede già da
sé — il contenuto esce da questa macchina. Il test lo manda com'è e percorre il task **senza
chiave**: si ferma all'approvazione e, dopo il «sì», fallisce con `provider.unavailable`. Che non
abbia toccato la rete non è simulato: `tests/conftest.py` rende inutilizzabili i transport di rete
di `httpx`, quindi una chiamata vera farebbe fallire il test da sola.

## 9. Il limite che un utente incontrerà davvero: dati fra step

Un piano che chiede al modello e **salva la risposta** in una nota è la cosa più ovvia da provare,
e in v0.1 non è esprimibile: gli `arguments` di uno step stanno nel piano (ADR 0018) e nessun dato
passa da uno step al successivo. `ask-model.json` ha un solo step per questo.

Va scritto qui perché non è un dettaglio interno: è **il primo limite che un utente incontrerà da
solo**, subito dopo aver ottenuto la chiave. La risposta è «non ancora», non «non serve».

**La strada è quella additiva già scritta in ADR 0018 §6:** un *valore di riferimento* dentro
`arguments` — una forma tipo `{"path": {"$from": {"step": …, "output": …}}}` — al posto di un
valore letterale. Non uno spostamento degli argomenti altrove: il posto resta quello.

**Con la condizione non negoziabile di ADR 0018 §6: la risoluzione avviene PRIMA del Guardian.**
Il riferimento va sostituito con il suo valore prima che `authorize` sia chiamata, così che ciò
che viene autorizzato sia ciò che viene eseguito. Un riferimento risolto **dopo** la decisione
sarebbe un bypass: il Guardian avrebbe validato uno schema e calcolato dei `targets` su un
segnaposto, e il tool riceverebbe un valore che nessuna decisione ha visto. Sarebbe il buco che
ADR 0018 chiude, riaperto da dentro.

Resta assegnato alla milestone che porterà la prima capability che ne ha bisogno.

## 10. Le tabelle

Un ADR non si riscrive: ciò che questo documento aggiunge alle tabelle di ADR 0005, 0023 e 0024
è ripetuto qui sotto sotto la sua etichetta, nella forma della tabella che estende.

Port estesi:

| Port | Spec | Modo | Membri |
|------|------|------|--------|
| `TaskRepository` | §14 | async | `count` |
| `ExecutionResultStore` | §63 | async | `for_task` |

`AuditLog` **non** è in questa tabella, ed è voluto: `newest_first` è un parametro di `read`, non
un membro nuovo. La firma è coperta da un test suo, come ADR 0011 ha fatto per `decide`.

**Rotte aggiunte** alla tabella di ADR 0023 §6:

| Metodo | Percorso | Cosa fa |
|---|---|---|
| `GET` | `/tasks/{task_id}/results` | ciò che i tool di questo task hanno prodotto, output compreso |

Le rotte diventano **quindici**.

**Variabili aggiunte** alla tabella di ADR 0023 §3:

| Variabile | Tipo | Default | Vincolo |
|-----------|------|---------|---------|
| `ELA_DECISION_TTL_SECONDS` | `int` | `300` | fino a `MAX_DECISION_TTL` (1 ora) |
| `ELA_NOTES_SCOPE` | `str` | `workspace/notes` | voce di scope ben formata |

**Comandi aggiunti** alla tabella di ADR 0024 §3:

| Comando | Rotta | Uscite |
|---------|-------|--------|
| `ela task results` | `GET /tasks/{task_id}/results` | `0` `1` `2` `3` |

**Regola aggiunta**, nella forma della tabella di ADR 0002:

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 29 | L'output di un tool esce da un solo modello | `ela.api` | solo `ExecutionResultOut` dichiara un campo `output`, solo `schemas.py` ne legge il nome |

Registrata come `tool-output-readers` in `tests/architecture/rules.py`. Le regole diventano
**ventinove**.

## Alternative considerate

- **`count(states=…) -> int`, un numero solo** — scartata: `/diagnostics` dovrebbe farne sette
  chiamate per avere la stessa risposta.
- **`count()` con tutti gli stati e gli zeri** — scartata perché cambierebbe ciò che
  `/diagnostics` stampa oggi (solo gli stati presenti, `—` quando non ce n'è nessuno) e quindi la
  guida: una correzione invisibile è la prova che era un debito, e questa non lo sarebbe stata.
- **Un terzo membro `tail(...)` su `AuditLog`** — scartata: rompe «due membri e non di più» senza
  dare niente che il parametro non dia (§3).
- **Lasciare il taglio lato client** — scartata: onesta solo finché il registro è piccolo, ed è
  l'unica cosa che non si accorcia mai.
- **`ExecutionResult` fuori da M8.3** — scartata perché lascerebbe `ask-model.json` un esempio che
  gira e non mostra niente (§4).
- **`ExecutionResultOut` dentro `results.py`, per far tornare la regola 29 alla lettera** —
  scartata: `schemas.py` è dove ogni forma sul filo è dichiarata, e piegare un principio a una
  comodità di verifica è il verso sbagliato (§4).
- **`notes_scope` in `WorkspaceSettings`** — scartata dal codice, non dal gusto: costringerebbe
  `ela.tools` a importare `ela.permissions`, o a tenere una seconda definizione di «scope valido»
  (§5).
- **Rifiutare al momento del piano uno step il cui `risk` differisce dal catalogo** — scartata:
  uno step può richiedere **più** capability, e in ELA non esiste una regola che dica che il
  rischio di uno step è il massimo di quelli delle sue capability. Inventarla in una milestone di
  manutenzione vorrebbe dire decidere una cosa che appartiene al Planner (§13).
- **Un secondo step in `ask-model.json` che salva la risposta** — impossibile in v0.1, e il
  perché è §9: è la strada di ADR 0018 §6, non una dimenticanza.
- **La spiegazione degli esempi in un `docs/examples/README.md`** — scartata: l'utente legge il
  file che incolla, e il README lo legge dopo, se lo legge.

## Conseguenze

- `AuditLog` ha ancora **due** membri; `TaskRepository` ne ha nove ed `ExecutionResultStore`
  quattro. ADR 0005 e ADR 0015 prendono nello stato il rimando a questo documento.
- Le rotte sono **quindici**, i comandi **diciotto**, le variabili di ADR 0023 §3 **nove**, le
  regole architetturali **ventinove**.
- `GET /audit` senza `newest_first` si comporta esattamente come prima: il default è il
  comportamento documentato da ADR 0023 §6, e nessun chiamante esistente cambia.
- Il contenuto dell'utente esce dall'API da **un** posto, e la regola 29 rende quel «uno»
  verificabile invece che ricordato.
- Il `cov-critical` non si estende: dopo M8.2 i `CRITICAL_PACKAGES` sono già tutti i package che
  M8.3 tocca, quindi nessuna riga nuova può restare scoperta.
- Nessuna migrazione, nessuna tabella nuova, nessun campo nuovo nel dominio.

### Vincoli dichiarati, da riaprire quando serviranno

- **Il loop autonomo, `recover()` periodico e l'heartbeat periodico del nodo `local`** restano
  fuori: sono il Proactive Core (§34, Fase 15), non un debito (§1). Con loro resta il limite che
  li rende urgenti, dichiarato da ADR 0023: **`run` è sincrono dentro la richiesta HTTP**.
- **La registrazione e l'heartbeat dei nodi via API** restano alla Fase 12, con l'autenticazione
  per nodo e `ELA_USER_NAME` che sparisce (ADR 0023 §4).
- **Nessun dato passa fra due step** (§9): la strada è ADR 0018 §6, la milestone è quella della
  prima capability che ne avrà bisogno.
- **`GET /tasks/{task_id}/results` non pagina.** Un task ha gli step del suo piano e al più due
  righe per step (ADR 0015): la finestra la chiederà il giorno in cui un piano sarà grande, non
  prima — che è la stessa risposta data a `verify_chain` in ADR 0024 §4.
- **`ELA_NOTES_SCOPE` cambiato a caldo non sposta niente e invalida i grant vecchi** (§5).
- **Due ELA con scope diversi sullo stesso database decidono diversamente sugli stessi percorsi.**
  È corretto — è ciò che «configurazione» significa — ma è una sorpresa se non è scritta.
- **`ask-model.json` non è eseguibile senza una chiave**, quindi il suo test è un test del
  fallimento pulito. È accettabile solo perché il fallimento pulito è esattamente ciò che
  ADR 0020 §2 promette.
