# 0012. Autorizzazioni: nascita da un'Approval, consumo atomico, invariante del grant monouso

- **Stato:** Accettata
- **Data:** 2026-09-05
- **Riferimenti spec:** §27, §30, §31, §32, §33, §49, §57, §59, §62, §65
- **Milestone:** M4.3

## Contesto

§30: "un semplice 'Sì' fuori contesto non deve automaticamente autorizzare un pagamento
critico". Fino a M4.2 il dominio aveva `Approval` e `Authorization` (ADR 0003), lo store SQLite
contava gli usi con un incremento incondizionato (`record_use`, ADR 0006) e il Guardian giudicava
se un grant *copre* una chiamata ed è *usabile* (ADR 0011 §5–6). Mancavano due cose: **come**
un'`Approval` diventa un'`Authorization` — solo se cita esattamente il task, lo step, la capability
e i bersagli che si stanno per eseguire — e **come** un grant monouso viene consumato una volta
sola anche con due executor concorrenti. Le domande erano: dove vive l'invariante "un grant nato
da un'approvazione è monouso e legato" (nel tipo o nella funzione); quanto è largo lo scope di un
grant approvato ("questa nota" o "la cartella"); quanto vive; chi conta gli usi e come lo store
rifiuta di spendere ciò che non si può spendere; in che ordine l'executor decide, consuma ed
esegue; chi può costruire un'`Authorization`.

## Decisione

### 1. L'invariante del grant monouso vive nel dominio

`Authorization` ha un `model_validator`: se `approval_id is not None` allora `task_id` e `step_id`
sono impostati e `max_uses == 1`, altrimenti `ValueError`. Un grant di policy (§59,
`approval_id=None`) non è vincolato. Era la docstring di M1.1: ora è il tipo. Un grant costruito
a mano, letto da un database manipolato o rivalidato dopo un `model_copy` che lo allarga viene
rifiutato (`model_copy` non esegue i validatori: per questo esiste la regola 15, §7).
`Approval` prende il campo **additivo** `targets: tuple[str, ...] = ()`: i bersagli su cui
l'utente ha detto sì, cioè i bersagli della `PermissionDecision` `REQUIRES_APPROVAL` che ha
generato la richiesta (`metadata["targets"]`, ADR 0011 §8). ADR 0003 prende nello stato il
rimando. Nessuna tabella `approvals`: l'`Approval` non è persistita in questa milestone.

### 2. `authorization_from_approval`: una funzione pura, otto controlli in ordine

`ela.permissions.authorizations.authorization_from_approval`:

```python
def authorization_from_approval(
    approval: Approval,
    *,
    task: Task,
    step: TaskStep,
    capability: CapabilitySpec,
    now: datetime,
    authorization_id: AuthorizationId,
    ttl: timedelta = DEFAULT_AUTHORIZATION_TTL,
) -> Authorization: ...
```

`capability` è la specifica *registrata* (il Guardian ricontrolla il catalogo al momento della
decisione). `now` e `authorization_id` sono fatti del chiamante (orologio e generatore
dell'executor, M5), come `authorization_uses` in ADR 0011 §5: la funzione non ha orologio, id né
store, e ogni suo ramo è esauribile dai test. I controlli, **il primo che fallisce vince**, sono la
tupla `CHECKS` (enum `Check`), confrontata con questa tabella da
`tests/docs/test_adr_authorizations.py`:

| # | Controllo | Cosa deve essere vero |
|---|---|---|
| 1 | `STATUS` | `approval.status is GRANTED`: PENDING, REJECTED, EXPIRED non generano nulla |
| 2 | `RESPONDER` | `responded_by` non vuoto e `responded_at` presente: qualcuno ha firmato il sì |
| 3 | `TIMELY` | `expires_at is None or responded_at < expires_at`: risposta prima della scadenza della richiesta (verso chiuso, ADR 0005 §2-bis: all'istante esatto è tardiva) |
| 4 | `TASK` | `approval.task_id == task.id` |
| 5 | `STEP` | `approval.step_id == step.id` |
| 6 | `CAPABILITY` | `approval.capability_id == capability.id` |
| 7 | `STEP_COHERENCE` | `step.required_capabilities` vuota o contenente `capability.id` (ADR 0011 §15: stringe soltanto) |
| 8 | `TARGETS` | `approval.targets` vuoti, oppure la capability ha `scoped_arguments` e `scope_covers(capability.scope, targets)` (ADR 0011 §4: voci valide, dentro lo scope registrato) |

Ogni fallimento è `ApprovalMismatchError(approval_id, check, reason)` (sottoclasse di
`PermissionsError`), **prima** che esista un grant: mai un grant parziale. Il `reason` nomina id e
percorsi, mai il `prompt` (§57).

Il grant: `id=authorization_id`, `created_at=now`, `capability_id`, **`scope = approval.targets or
capability.scope`** (decisione B dell'utente: "sì a scrivere questa nota" autorizza quella nota, non
la cartella; senza bersagli — `model.complete` — vale lo scope del catalogo), `granted_by =
responded_by`, `approval_id`, `task_id`, `step_id`, **`max_uses = 1`**, `expires_at = now + ttl`,
`metadata = {"origin": "approval", "decision_id": ...}`.

```python
DEFAULT_AUTHORIZATION_TTL = timedelta(hours=1)
MAX_AUTHORIZATION_TTL = timedelta(hours=24)
```

`ttl` fuori da `(0, MAX_AUTHORIZATION_TTL]` → `ValueError` (decisione C: errore di
configurazione, non di contesto). Un'ora copre una coda lunga senza lasciare un titolo al
portatore aperto per giorni; in M8.1 diventa una setting con default 1 ora e massimo 24.

### 3. `AuthorizationStore.consume(authorization_id, *, now) -> int` ed errori nominati

Spende un uso e ritorna il nuovo totale **solo se** il grant esiste, non è scaduto (`expires_at is
None or expires_at > now`, verso chiuso) e non è esaurito (`max_uses is None or uses < max_uses`).
Altrimenti non conta nulla e solleva, nell'ordine del Guardian (ADR 0011 §5: scaduto prima di
esaurito): `NotFoundError`, `AuthorizationExpiredError(authorization_id, expires_at)`,
`AuthorizationExhaustedError(authorization_id, uses, max_uses)`. I due nuovi errori sono
`PortError` in `ela.ports` con base comune `AuthorizationNotUsableError(authorization_id, reason)`
(decisione D: errori nominati, ADR 0005 §2, così il chiamante distingue "chiedi di nuovo" da
"qualcun altro è arrivato prima"). `now` è un fatto del chiamante: lo store non ha orologio (ADR
0005). `uses` e `for_capability` restano: il Guardian ha bisogno del conteggio per *decidere*,
`consume` lo *applica*.

### 4. `record_use` è rimosso: due righe di port

Con `consume` l'incremento incondizionato resta senza chiamanti e sarebbe un membro morto del port
(decisione E). Le due tabelle sotto sono lette da `tests/docs/test_adr_ports.py`, ciascuna nella
propria sezione (§8): la prima **estende** la riga di ADR 0005, la seconda la **sostituisce** con i
membri che restano.

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `AuthorizationStore` | §30, §59 | async | `consume` |

Port sostituiti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `AuthorizationStore` | §30, §59 | async | `grant`, `get`, `for_capability`, `uses`, `consume` |

ADR 0005 e ADR 0006 prendono nello stato il rimando; la nota di ADR 0006 §6 su `record_use` resta
storica.

### 5. Atomicità su SQLite

`SqlAuthorizationStore.consume` è **un solo** `UPDATE`:

```sql
UPDATE authorizations SET uses = uses + 1
WHERE id = :id
  AND (max_uses IS NULL OR uses < max_uses)
  AND (expires_at IS NULL OR expires_at > :now)
```

La condizione e l'incremento sono nella stessa istruzione, che SQLite esegue sotto il lock di
scrittura: due `consume` concorrenti su un grant monouso non possono entrambe vedere `uses = 0`.
`rowcount == 1` → rilettura del totale nella stessa transazione; `rowcount == 0` → una `SELECT`
diagnostica nella stessa transazione decide quale errore sollevare. La sicurezza sta
nell'`UPDATE`, la `SELECT` serve solo al nome dell'errore. Il confronto su `expires_at` avviene in
SQL sulla colonna `UtcDateTime` (naive UTC, ADR 0006 §7) con il parametro legato dallo stesso tipo;
il test verifica entrambi i lati dell'istante esatto. Test di concorrenza su file: venti `consume`
simultanee su `max_uses=1` → esattamente una ritorna `1`, diciannove sollevano
`AuthorizationExhaustedError`; su `max_uses=5` → totali `{1..5}`. Il fake ha la stessa semantica
(single-thread: atomico per costruzione). Nessuna migrazione: la colonna `uses` esiste da `0001`.

### 6. Vincoli per l'executor (M5): `authorize` → `consume` → tool, e chi scrive l'audit

L'ordine è **`authorize` → `consume` → tool** (decisione G). Il grant è speso *prima* dell'azione:
se `consume` solleva, nessun tool gira e l'esito è "non agire" (§33). `consume` è chiamato solo con
una decisione `ALLOWED` che si regge su quel grant (`decision.authorization_id` uguale); una
decisione che non lo usa (SAFE con grant inutile, ADR 0011 §6) non consuma nulla. **Conseguenza
accettata:** se il tool fallisce dopo il `consume`, il grant è speso e serve una nuova
approvazione. Meglio chiedere due volte che eseguire due volte. ADR 0011 (Conseguenze, "registra
l'uso dopo l'esecuzione") è superato da questo paragrafo: rimando nel suo stato.

**Un solo `now` per chiamata (review del 2026-09-05).** `authorize` e `consume` della stessa
chiamata ricevono lo **stesso istante**, letto una volta sola dal `Clock` dell'executor. Due letture
diverse aprirebbero una finestra in cui il grant è valido per il Guardian e scaduto per lo store, o
viceversa: nel primo caso il tool non gira per un grant appena giudicato buono, nel secondo un grant
già scaduto per il Guardian verrebbe speso. Il fatto è uno e viaggia con la chiamata.

Nessun servizio audited in questa milestone (decisione F): chi chiama
`authorization_from_approval` è chi salva il grant nello store (`grant`) e scrive
`AUTHORIZATION_GRANTED` — con `approval_id`, `authorization_id`, `task_id`, `step_id`,
`capability_id`, payload con `expires_at`, `max_uses` e `targets`, mai il `prompt` (§57) — cioè
l'executor, che possiede l'unità di lavoro fra i port, come l'engine scrive `APPROVAL_REQUESTED`
(ADR 0008). L'executor riempie `Approval.targets` dai `metadata["targets"]` della decisione
`REQUIRES_APPROVAL` che l'ha originata: `targets` è un fatto di chi crea l'`Approval`, e il legame
`Approval.decision_id` → decisione è verificabile lì.

### 7. Regola architetturale 15: fuori da `ela.permissions` nessuno costruisce un'`Authorization`

Regola AST closed-world `check_authorization_builders` in `tests/architecture/rules.py`
(decisione H): segnala ogni chiamata `Authorization(...)` — per nome o come attributo — e ogni
`x.model_copy(update={...})` il cui dizionario letterale nomina un campo che può allargare un grant
(`max_uses`, `expires_at`, `scope`, `capability_id`, `approval_id`, `task_id`, `step_id`), in ogni
modulo di `src/ela` fuori da `ela.permissions` e `ela.testing` (la regola 6 e il contratto 5 tengono
i fake fuori dalla produzione). Un'esenzione puntuale per percorso esatto:
`infrastructure/persistence/mappers.py`, che *legge* un grant da una riga e non ne conia uno. Ogni
grant di produzione nasce da `authorization_from_approval` (o, in futuro, da una factory di policy
§59 nello stesso package). Casi in `violations.py`, entry in `RULES`, test di vacuità
(`authorizations.py` e il mapper costruiscono davvero un'`Authorization`). Nessun contratto
import-linter: non è un import. Specchio della regola 12 (ADR 0011 §11).

### 8. `tests/docs/test_adr_ports.py` legge le tabelle per sezione

Un ADR può portare due tabelle di port, una sotto l'etichetta "Port estesi:" e una sotto "Port
sostituiti:" (questo ADR, §4). Il test legge un file per intero quando ha una sola tabella (ADR 0005,
0008, 0010, 0011) e **fallisce se uno stesso port compare in due righe** dello stesso testo; con
un'etichetta legge solo le righe fra quell'etichetta e la fine della tabella. Questo ADR è in
`EXTENDING_ADRS` con "Port estesi:" e in `REPLACING_ADRS` con "Port sostituiti:". La terza
categoria "firma modificata" registrata come debito in M4.2 non è questo caso e resta debito.

## Alternative considerate

- **Invariante solo nella funzione generatrice** — un grant costruito a mano o letto da un DB
  manipolato sarebbe accettato dal tipo. Nel dominio, con la regola 15 a chiudere `model_copy`.
  Scartata.
- **Scope del grant = scope registrato della capability** (prima proposta) — "sì a scrivere questa
  nota" avrebbe autorizzato, per quel task/step e una volta, qualunque percorso della cartella.
  L'utente ha scelto di stringere subito: `targets` sull'`Approval`. Scartata.
- **Bersagli fuori scope o su capability senza bersagli → grant con quello scope** — un grant che
  il Guardian non potrebbe mai applicare (ADR 0011 §4) è un'approvazione che non può valere: dubbio
  → `ApprovalMismatchError`. Scartata.
- **`ttl` senza tetto** — un TTL configurabile senza limite allunga a piacere la finestra in cui un
  grant monouso resta al portatore. Tetto 24 ore (utente). Scartata.
- **Tenere `record_use` accanto a `consume`** — innocuo (conta solo in più) ma membro morto del
  port, e una seconda via di scrittura del contatore da spiegare per sempre. Rimosso. Scartata.
- **`consume` che rilegge e poi aggiorna in due istruzioni** — fra la lettura e la scrittura un
  secondo executor può consumare lo stesso grant: è esattamente la corsa che §30 vieta. Un solo
  `UPDATE` condizionale. Scartata.
- **Lo store con un orologio** — gli darebbe un port che non deve possedere (ADR 0005); il
  chiamante porta `now`, come porta `authorization_uses` al Guardian. Scartata.
- **Un solo errore `consume` con un campo `reason`** — meno leggibile nei test e nei log; due
  sottoclassi nominate con base comune. Scartata.
- **Consumo dopo l'esecuzione** (ADR 0011, Conseguenze) — se il tool agisce e il processo cade
  prima di contare, il grant resta spendibile e l'azione può ripetersi. Prima dell'azione: meglio
  chiedere due volte che eseguire due volte. Scartata.
- **`AuthorizationService(store, audit, clock, ids)` in `ela.permissions` ora** — anticiperebbe
  l'unità di lavoro dell'executor (M5), che possiede store, audit e ordine delle scritture. La
  funzione pura è l'unico pezzo che appartiene alle permissions. Scartata.
- **Verificare che lo step appartenga al piano del task** — la funzione non ha il piano; il
  chiamante (M5) legge lo step dal piano del task e il Guardian ricontrolla il contesto. Fuori
  dalla funzione. Scartata.
- **Regola 15 senza esenzione per il mapper** — il mapper deve poter ricostruire un grant da una
  riga; l'alternativa (un `model_validate` sul dizionario della riga) è la stessa costruzione con
  un altro nome. Esenzione per percorso esatto, testata. Scartata.

## Conseguenze

- Un'`Approval` fuori contesto (altro task, altro step, altra capability, altri bersagli, non
  concessa, non firmata, tardiva) non genera alcuna `Authorization`: §30 è una funzione con test
  esaustivi e una proprietà hypothesis (⇔), non una convenzione.
- Il tipo `Authorization` rifiuta un grant che dichiara un'approvazione ma è riusabile o non legato;
  `tests/domain/strategies.py` genera i due rami coerenti.
- `AuthorizationStore` perde `record_use` e prende `consume`; fake e SQLite passano lo stesso
  contratto (`tests/contracts/test_authorization_store.py`), la concorrenza è provata su file.
- **Per M5**: `authorize` → `consume` → tool, con **un solo `now`** letto dal `Clock` e passato a
  entrambi (§6); un tool che fallisce dopo il `consume` costa una nuova approvazione, mai
  un'azione doppia. M5 salva il grant, scrive `AUTHORIZATION_GRANTED`, riempie `Approval.targets`
  dalla decisione e legge lo step dal piano del task.
- **Per M8.1**: `DEFAULT_AUTHORIZATION_TTL` e `MAX_AUTHORIZATION_TTL` diventano setting (default 1
  ora, massimo 24), come `decision_ttl` (default 5 minuti, massimo 15).
- `now` è un fatto del chiamante sia per `consume` sia per la generazione: un orologio sbagliato
  allunga una scadenza. Il chiamante è codice del Core con il `Clock` del Core; stessa fiducia già
  accordata ad `authorization_uses` (ADR 0011).
- `targets` è un fatto di chi crea l'`Approval`: se copiasse bersagli diversi da quelli della
  decisione, l'utente approverebbe una cosa e il grant ne coprirebbe un'altra. La funzione rifiuta
  bersagli fuori dallo scope registrato o malformati; il resto è responsabilità di M5, dichiarata.
- Regola 15 in `tests/architecture/rules.py` con casi positivi e negativi; le tabelle di §2 e §4 e
  le costanti di §2 sono verificate dal codice (`tests/docs/test_adr_authorizations.py`,
  `tests/docs/test_adr_ports.py`), con casi negativi.
