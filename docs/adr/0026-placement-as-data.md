# 0026. Il piazzamento come dato: `PlacementDecision`, `ensure_placed`, `confirm`; il token a tempo costante; regole 30 e 31

- **Stato:** Accettata. SPEC di M9.1 approvata dall'utente: **forma B** per C1 (il piazzamento
  come dato, non il registro all'executor), con il limite dichiarato — un piazzamento non scade
  in v0.1 — e il rinvio scritto: quando i nodi saranno remoti (Fase 12) un piazzamento avrà una
  scadenza e la forma A tornerà in discussione. Una cosa è emersa implementando ed è argomentata
  dove vale: il ramo di **ripresa** di `Runner._node` non passava dall'orchestrator affatto (§4),
  e chiuderlo cambia un comportamento che un test documentava (§4, «Cosa cambia per chi guarda»).
- **Contesto:** M9.1, la prima metà della milestone di hardening: le difese.
- **Riferimenti spec:** §16, §17, §27, §28, §29, §33, §51, §52, §57, §58
- **Estende:** ADR 0002 (le regole di architettura: due nuove), ADR 0013 e ADR 0018 §4 (la firma
  di `execute`), ADR 0017 (il piazzamento), ADR 0019 §4 (come il runner sceglie il nodo),
  ADR 0023 §7 (il token dell'API).

## Contesto

M9.1 nasce da una domanda posta alla suite intera: *quali proprietà che crediamo garantite non
hanno un test che le dimostri?* L'elenco completo è in `docs/milestones/M9.1.md`. Questo ADR
registra le decisioni prese sulle voci di quell'elenco che cambiano o difendono codice di
produzione. Le altre — le liste che non sanno accorgersi di essere false — sono M9.3, e i rinvii
sono M9.2.

Il metodo che ha prodotto due delle voci qui sotto merita una riga, perché è ripetibile: otto
righe security-critical mutate una alla volta, con la suite intera rigirata per ognuna. Sette
mutazioni uccise, una sopravvissuta (§6). Una copertura al 100% branch dimostra che una riga
**viene eseguita**; non dimostra che qualcuno l'ha guardata.

## 1. L'anello senza doppia difesa

Ogni permesso in ELA è controllato due volte, e le due volte sono in posti diversi:

| Chi decide | Chi ricontrolla | Come |
|---|---|---|
| Il Guardian, su una capability | il tool | `ensure_allowed` prima di agire (ADR 0005 §5) |
| Il Guardian, su una capability | l'executor | l'esito prima di chiamare il tool (ADR 0013 §5) |
| L'orchestrator, su un nodo | **nessuno** | — |

`Executor.execute` prendeva un `DeviceId` e il suo docstring diceva «è il nodo che l'orchestrator
ha scelto». L'executor non aveva né registro né orchestrator per verificarlo. La decisione di
**privacy** — quale nodo può vedere questo contenuto (§57) — viveva in un posto solo,
`Runner._node` → `DeviceOrchestrator.place`, e chiunque chiamasse l'executor poteva nominare un
nodo che l'orchestrator aveva scartato. Non c'era un test che dimostrasse il rifiuto perché il
rifiuto non esisteva.

Un `DeviceId` dice «qui» senza dire «per cosa». È la forma sbagliata: un identificatore non porta
con sé la domanda a cui è la risposta, quindi chi lo riceve può solo credere a chi lo manda.

## 2. La forma: il piazzamento come dato

`PlacementDecision` è ciò che viaggia. Modellata su `PermissionDecision`, deliberatamente:
il Guardian decide, la decisione viaggia **come dato**, il tool la ricontrolla prima di agire.
Gli stessi tre pezzi, per l'altra domanda.

```python
class PlacementDecision(NamedTuple):
    created_at: datetime
    task_id: TaskId
    step_id: StepId
    requirements: Requirements
    device: Device | None
    scores: tuple[Score, ...]
    reason: str
```

`Placement` resta ciò che è: la risposta pura di `choose`, che non sa nulla di task e non deve
saperne. `PlacementDecision` è la risposta **più la domanda**: quale task, quale step, in quale
istante, e contro quali `Requirements` il nodo è stato giudicato.

**Non è un'entità di dominio.** Non si persiste e non attraversa un port, quindi resta un valore
di `ela.devices`: portarla nel dominio toccherebbe ORM e mapper per nulla (ADR 0003, il dominio
minimo).

Il punto che decide fra le due forme possibili è che **`refusals(device, requirements)` è già una
funzione pura su dati**. L'executor non ricalcola la politica: chiama la *stessa* funzione sugli
*stessi* dati che l'orchestrator ha giudicato — come `tools/base.py` chiama lo stesso
`ensure_allowed` che l'executor ha già chiamato. Una implementazione, due punti di chiamata.

## 3. `ensure_placed`, e dove viene chiamato

Specchio di `ensure_allowed`, e controlla le stesse tre specie di cosa: che la decisione sia di
*questa* chiamata, che abbia deciso a favore, e che ciò su cui ha deciso valga ancora.

| # | Rifiuto | Perché |
|---|---|---|
| 1 | la decisione è di un altro task o di un altro step | un piazzamento non è trasferibile |
| 2 | non nomina nessun nodo (`waits`) | non è stato scelto niente, quindi non gira niente |
| 3 | `refusals` sul nodo che nomina, contro i requisiti sotto cui è stato giudicato, non è vuoto | la decisione è in disaccordo con sé stessa |

Solleva `NotPlacedError`, che è una **precondizione** e non un esito: nessuna scrittura la
precede, quindi un chiamante che porta il piazzamento di un altro step non lascia traccia di
un'esecuzione mai iniziata. Il controspecchio di `NotAllowedError`: quella custodisce *cosa* può
succedere, questa *dove*.

**Dove, dentro `execute`.** Dopo le ricerche (capability, tool, verifier, condizioni di successo)
e prima della prima lettura dei risultati. Non per primo: uno step la cui capability non ha un
tool deve dirlo con il proprio errore — `CapabilityNotFound` — e non come un nodo che non può
ospitarlo, che sarebbe vero ma inutile a chi legge. Non più tardi: dopo quel punto si scrive.

## 4. La ripresa: `confirm` conferma e non sceglie

`Runner._node` ha due rami e solo uno passava dall'orchestrator. Uno step **RUNNING** — ripreso
dopo un crash o dopo un'approvazione — non viene piazzato di nuovo, e il motivo di ADR 0019 §4 è
giusto: chiedere una seconda volta potrebbe nominare un altro nodo mentre un tool ha girato sul
primo. Così il suo nodo si rileggeva dall'audit (`_started_on`, l'ultimo `STEP_STARTED`) e andava
all'executor **senza che nessuno lo giudicasse**. La stessa fiducia di §1, in forma più acuta: un
id che viene da un evento e diventa il posto dove gira un tool.

`DeviceOrchestrator.confirm(device_id, step, *, task_id, max_privacy)` legge quel nodo dal
registro, lo giudica contro gli stessi `Requirements` che lo step avrebbe oggi, e lo nomina solo
se `refusals` è vuoto. **Non scrive un evento di audit:** confermare non è scegliere, e un
secondo `DEVICE_SELECTED` affermerebbe una scelta che nessuno ha fatto — la scelta che conferma è
già nel log.

### Cosa cambia per chi guarda

Un nodo che ha smesso di rispondere fa **aspettare** anche lo step già RUNNING, dove prima lo
faceva ripartire. Il run esce `WAITING_DEVICE`, che è un esito che esiste già (ADR 0017 §6): lo
step resta RUNNING, non fallisce e non si perde, e la stessa camminata lo finisce appena il nodo
parla. Un test lo documentava al contrario — «il RUNNING riprende sul nodo su cui è stato
avviato: è un fatto nell'audit, non un piazzamento da rifare» — ed è stato riscritto con il
motivo scritto dentro, non cancellato.

È l'unico cambiamento di comportamento di questa milestone, ed è dichiarato qui perché è un
cambiamento e non un dettaglio. In pratica, oggi, non si vede: `POST /tasks/{id}/run` manda un
heartbeat al nodo `local` prima di ogni camminata (ADR 0023 §5-bis), quindi il nodo è idoneo
esattamente quando serve.

## 5. Regola 30: chi può costruire un piazzamento che nomina un nodo

Specchio esatto della regola 12 (fuori da `ela.permissions` nessuno costruisce una
`PermissionDecision` che potrebbe permettere). Una difesa che si può aggirare costruendo a mano
l'oggetto che difende non è una difesa: se qualunque modulo potesse coniare una
`PlacementDecision` con dentro un `Device`, `ensure_placed` verificherebbe una firma che chiunque
può falsificare.

**Nessuna esenzione.** `ela.testing` non ne ha bisogno — nessun fake costruisce un piazzamento — e
M9.1 non apre porte prima che qualcuno bussi: è la lezione dell'elenco critico, dove cinque
esenzioni su ventidue non avevano più codice dietro (M9.3, voce A1).

## 6. Il token a tempo costante: regola 31

`api/security.py` confronta il token con `secrets.compare_digest`, e il docstring dice «compared
in constant time». Sostituendo quel confronto con `==` la suite intera passa: 3551 test, nessuno
se ne accorge. È l'unica delle otto mutazioni sopravvissuta, ed è istruttiva perché quella riga è
coperta al 100% branch — la copertura dimostra che il confronto **avviene**, non che è a tempo
costante.

Un test a tempo non è la strada: misurerebbe la macchina, che è precisamente l'errore che M9.1 ha
appena finito di correggere altrove (ADR 0006 §13). La proprietà si difende dove vive, nella
forma del codice: **regola 31**, in `api/security.py` il token si confronta solo con
`compare_digest` e non compare mai come operando di un confronto.

## 7. Uno step del client può solo stringere

Il piano arriva dal client — `POST /tasks/{id}/plan` è superficie pubblica dichiarata (ADR 0023) —
e `StepIn` gli lascia `required_capabilities`, `requires_authorization`, `risk`, `arguments`.
È la prima cosa che un attaccante prova, e la proprietà che lo ferma viveva in due espressioni
booleane senza un test che la nominasse.

La proprietà, con un ordine esplicito sugli esiti (`DENIED < REQUIRES_APPROVAL < ALLOWED`):

> per ogni `TaskStep` costruibile da un client e per ogni `CapabilitySpec` che il client dichiara,
> l'esito del Guardian non è mai **più permissivo** dell'esito della stessa chiamata con la spec
> registrata e uno step che non dichiara niente.

Regge perché tutto ciò che la policy legge viene dal catalogo (`registered.risk`,
`registered.scope`) e lo step può solo aggiungere: `registered.requires_authorization or
step.requires_authorization`, e `required_capabilities` vuota è *nessuna dichiarazione*, non un
permesso. Il codice non cambia; cambia che ora qualcuno lo afferma.

### Il filtro `DEGRADED` è vacuo, e va detto

`Requirements.risk` viene da `step.risk`, cioè dal client, e alimenta l'unico filtro che legge il
rischio: un nodo `DEGRADED` è rifiutato da `UNGUARDED_RISK` (HIGH) in su. Ma il catalogo non
ammette capability sopra `MAX_RISK` (MEDIUM, ADR 0010), quindi **nessuna capability reale può
attivare quel filtro**: dichiarare un rischio più basso non allenta niente perché non c'era
niente di stretto, e dichiararlo più alto può solo stringere.

Il test lo dichiara vacuo invece di lasciarlo sembrare una difesa. **Una difesa che sembra attiva
e non può scattare è peggio di una difesa assente, perché chi legge smette di cercarne una vera.**
Il filtro tornerà vivo il giorno in cui il catalogo ammetterà capability HIGH — e quel giorno la
provenienza di `step.risk` andrà riesaminata, perché allora la differenza si vedrà.

## 8. I tre test di sicurezza

- **Il tool ostile** (§28). La regola 16 riporta ogni `.execute(` fuori dall'executor, ma è una
  regola sull'AST di `src/ela`: non dice niente su cosa un tool possa *raggiungere* a runtime. Un
  `ToolPort` ostile che prova a eseguire un secondo tool con la propria decisione viene fermato
  dal contratto che ogni tool applica a sé stesso, non solo dal divieto statico.
- **La capability HIGH** (§29). `CapabilityRegistry` rifiuta una spec sopra `MAX_RISK`, quindi nel
  sistema vero una HIGH non arriva mai al Guardian: la riga `HIGH → DENY` di `RISK_POLICY` è una
  **seconda** difesa che si può esercitare solo con un catalogo doppio. Il test la esercita
  deliberatamente, attraverso l'executor vero, con approvazione data e grant valido: sempre
  `DENIED`. Vale proprio perché dimostra che il Guardian non si appoggia al tetto del catalogo.
- **Il contratto sul tool di §57.** `ModelCompleteTool` e `ModelCompleteVerifier` non erano nella
  tabella dei contract test: il tool che porta il contenuto dell'utente fuori dalla macchina era
  l'unico su cui «niente esecuzione senza una decisione `ALLOWED`» non fosse mai stato verificato.
  La tabella ora si **deriva** da `tools_v01` e `verifiers_v01` per la parte derivabile, così il
  quarto tool non potrà entrare nello stesso silenzio del terzo.

## 9. Le tabelle

`Firma aggiornata:` — la riga di ADR 0018 §4, ripetuta qui perché cambia (ADR immutabile).

| Metodo | Firma |
|---|---|
| `Executor.execute` | `execute(task_id, step_id, *, placement: PlacementDecision)` |

`Metodi aggiunti:`

| Classe | Metodo | Cosa fa | Scrive audit |
|---|---|---|---|
| `DeviceOrchestrator` | `confirm` | giudica il nodo di uno step già avviato, invece di sceglierne uno | no |

`Errori aggiunti:`

| Errore | Modulo | Quando |
|---|---|---|
| `NotPlacedError` | `ela.devices.errors` | il piazzamento non copre questa chiamata (§3) |

`Regole aggiunte:`

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 30 `placement-decisions-built-only-by-the-orchestrator` | fuori da `ela.devices` nessuno costruisce una `PlacementDecision` che nomina un nodo | tutto `ela` | nessuna esenzione |
| 31 `token-compared-in-constant-time` | il token si confronta solo con `secrets.compare_digest` | `ela.api.security` | nessuna esenzione |

## Alternative considerate

- **Il `DeviceRegistry` all'executor**, che rilegge il nodo e lo rigiudica. Scartata, per tre
  motivi in ordine di gravità. *Uno:* giudicare vuole `Requirements`, che vuole `max_privacy` —
  la tolleranza del chiamante — quindi la fiducia si sposta di un campo invece di sparire; e
  fissarlo a `LOCAL_ONLY` per fail-safe rifiuterebbe ogni esecuzione legittima su un nodo più
  permissivo. *Due:* rileggere significa rileggere **dopo**, quindi un nodo che perde l'heartbeat
  fra `place` ed `execute` farebbe rifiutare un piazzamento che era legittimo — una milestone di
  hardening che inventa un fallimento nuovo ha sbagliato bersaglio. *Tre:* metterebbe la privacy
  in un secondo modulo, contro ADR 0017 («privacy da questo modulo soltanto»), e due
  implementazioni di una politica divergono in silenzio.
- **Una scadenza sul piazzamento**, come `PermissionDecision` ha. Scartata per v0.1: sarebbe una
  manopola di politica nuova, e oggi la freschezza è strutturale — il runner chiama `place` o
  `confirm` e `execute` nella stessa iterazione. Riaperta in Fase 12 (vincoli dichiarati).
- **Ripiazzare lo step ripreso** invece di confermarlo. Scartata: è esattamente ciò che ADR 0019
  §4 vieta, perché potrebbe nominare un altro nodo mentre un tool ha girato sul primo. `confirm`
  giudica il nodo che c'è, non ne cerca uno nuovo.
- **Un test a tempo per il confronto del token.** Scartata: misurerebbe la macchina. Una proprietà
  che si può stabilire solo cronometrando non ha un test, ha una scommessa (M9.1, «La lezione»).
- **Portare `PlacementDecision` nel dominio.** Scartata: non si persiste e non attraversa un
  port, quindi non è un'entità — sarebbe ORM e mapper toccati per nulla.

## Conseguenze

- Nominare un nodo che nessuno ha scelto ha smesso di essere esprimibile: il `device_id` che
  finisce nell'audit e nei risultati è quello che la decisione nomina.
- La catena dei permessi non ha più un anello con una difesa sola.
- Il ramo di ripresa cambia comportamento quando il nodo è silenzioso: aspetta invece di ripartire
  (§4). È l'unico cambiamento di comportamento della milestone.
- Le regole di architettura passano da ventinove a **trentuno**, e i contratti di
  import-linter restano **tredici**:
  nessuna delle due nuove è esprimibile come un divieto di import.
- Chi scriverà il primo nodo remoto trova qui il punto esatto in cui riaprire la questione: un
  piazzamento senza scadenza è sicuro finché il nodo è questo processo.

### Vincoli dichiarati, da riaprire quando serviranno

- **Un piazzamento non scade** (§2). `ensure_placed` verifica che la decisione sia di questa
  chiamata e che il nodo che nomina sia idoneo *secondo il giudizio registrato*; non vede il mondo
  muoversi fra la scelta e la corsa. Oggi è sicuro perché il nodo è questo processo e le due cose
  distano una iterazione. **Con i nodi remoti (Fase 12) un piazzamento avrà una scadenza**, e con
  essa la forma A — rileggere il registro al momento di eseguire — torna in discussione: allora
  rileggere non sarà «inventare un fallimento», sarà l'unico modo di sapere che la macchina
  dall'altra parte esiste ancora.
- **Il filtro `DEGRADED` è vacuo** (§7), e lo resta finché il catalogo si ferma a MEDIUM.
- **Il lock di `run` è in-process.** `POST /tasks/{id}/run` rifiuta un secondo run guardando un
  `set` in `app.state`: due processi ELA sullo stesso database eseguono lo stesso task insieme.
  È il gemello del lock in-process dell'engine, dichiarato da ADR 0008 §11 e mai da nessuno per
  l'API. Chiuderlo vuole un lock nel database, che è una decisione di persistenza.
- **La tamper-evidence è disponibile e non applicata.** `GET /audit/verify` esiste, la CLI lo
  espone, e niente lo chiama da sé: non all'avvio, dove gira `recover()` (ADR 0023 §11), non dopo
  una camminata. La catena è verificabile su richiesta, e nessuno verifica per conto dell'utente.
  È una scelta — verificare a ogni avvio costa una lettura dell'intero log — e chi la applicherà
  periodicamente è il Proactive Core (§34, Fase 15), per il criterio di ADR 0025 §1.
- **Il Guardian si fida di `authorization_uses`** (elenco critico, voce C2): il conteggio glielo
  passa il chiamante e non ha lo store per verificarlo. Rinviato a M9.2, e nominato qui perché è
  l'ultimo punto della catena dei permessi in cui qualcuno crede a un numero.
