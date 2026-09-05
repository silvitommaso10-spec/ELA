# 0011. Permission Guardian: catalogo, policy v0.1 per rischio, scope, autorizzazioni, fail-safe, audit delle decisioni

- **Stato:** Accettata
- **Data:** 2026-09-05
- **Riferimenti spec:** §13, §27, §28, §29, §32, §33, §47, §49, §51, §52, §56, §57, §59, §62, §65
- **Milestone:** M4.2

## Contesto

§27 mette il Guardian fra il Planner e ogni Tool: "ELA decide cosa sarebbe utile fare, il
Guardian decide se ELA è autorizzata a farlo" (§47). Fino a M4.1 esistevano il port
`PermissionGuardianPort` (ADR 0005 §4: sincrono, puro, riceve l'`Authorization` e non lo store)
e un fake a tabella; il catalogo di §29 è arrivato con ADR 0010. Questa decisione consegna il
Guardian vero. Le domande erano: come il Guardian conosce le capability e perché deve fidarsi solo
del catalogo; cosa vuol dire "rispettare lo scope"; quando un'`Authorization` copre una chiamata e
cosa succede quando non la copre; come una decisione arriva nell'Audit Log senza che esista una via
non registrata; quanto vive una decisione; cosa del contenuto dell'utente può finire nel log; come
il Guardian resta fail-safe (§33) anche quando qualcosa dentro di lui si rompe.

## Decisione

### 1. Nomi degli esiti

`PermissionOutcome.ALLOWED` / `DENIED` / `REQUIRES_APPROVAL` (M1.1). Nessuna rinomina.

### 2. Il Guardian conosce le capability da un catalogo, e la specifica ricevuta deve coincidere

`ela.permissions.guardian.PermissionGuardian(registry, clock, ids, audit, *, decision_ttl)`
riceve un `CapabilityRegistryPort` (§28; port sincrono e dichiarativo: non è un tool né uno store,
ADR 0005 §4 resta vero). In `decide` la `CapabilitySpec` passata dal chiamante è confrontata con
quella registrata sotto lo stesso id: id ignoto → `DENIED` ("no rule", il contratto di
`tests/contracts/test_guardian.py`); specifica diversa da quella registrata in qualsiasi campo (un
`risk` abbassato, uno scope allargato, uno schema diverso) → `DENIED` con motivo "differs from
the catalogue". Senza questo controllo chiunque potesse costruire una `CapabilitySpec` con
`risk=SAFE` per `model.complete` aggirerebbe il Guardian (§47, §65). Da qui in avanti il Guardian
ragiona sulla specifica *registrata*: rischio, schema, scope, `requires_authorization`.

### 3. Policy v0.1 per livello di rischio, e l'ordine dei controlli

La tabella è dato (`RISK_POLICY` in `guardian.py`, `Mapping[RiskLevel, Rule]` immutabile) ed è
confrontata con questa da `tests/docs/test_adr_guardian.py`:

| Rischio | Regola | Esito |
|---|---|---|
| SAFE | `ALLOW` | `ALLOWED` |
| LOW | `ALLOW_WITHIN_SCOPE` | `ALLOWED` se ogni bersaglio è nello scope della capability, altrimenti `DENIED` |
| MEDIUM | `APPROVAL_UNLESS_AUTHORIZED` | `ALLOWED` con un'autorizzazione che copre la chiamata, non scaduta e non esaurita; `REQUIRES_APPROVAL` senza autorizzazione, con una scaduta o esaurita; `DENIED` con una che non copre (§6) |
| HIGH | `DENY` | `DENIED` sempre (§29: non in produzione in v0.1) |
| CRITICAL | `DENY` | `DENIED` sempre |

Un `RiskLevel` assente dalla tabella (impossibile oggi, ma la tabella è dato) → `DENIED`.

L'ordine dei controlli, **il primo che nega vince**, e i dinieghi precedono la domanda:

1. catalogo (§2);
2. argomenti validi contro lo schema della specifica registrata (`validate_arguments`, ADR 0010
   §4): violazione → `DENIED`, anche per SAFE;
3. coerenza con lo step (§15): `DENIED`;
4. riga della tabella: HIGH/CRITICAL → `DENIED`; LOW fuori scope → `DENIED`;
5. autorizzazione, quando la riga è MEDIUM oppure quando la specifica registrata o lo step
   richiedono un'autorizzazione (§7): valida → `ALLOWED`; assente, scaduta o esaurita →
   `REQUIRES_APPROVAL`; che non copre → `DENIED`.

Il passo 4 precede il 5 di proposito: a un utente non si chiede di approvare ciò che sarebbe
negato comunque (LOW fuori scope che richiede autorizzazione è `DENIED`, non "chiedi"). Ogni
decisione porta in `metadata["rule"]` il controllo che l'ha stabilita (`Rule`: le quattro regole
della tabella più `CATALOGUE`, `ARGUMENTS`, `STEP_MISMATCH`, `AUTHORIZATION_REQUIRED`,
`INTERNAL_ERROR`). Niente viene eseguito o scritto prima della decisione.

### 4. Scope: cosa vuol dire "rispettato"

Modulo puro `ela.permissions.scope`. Una voce di scope è un percorso POSIX relativo senza
segmenti vuoti, `.` o `..` (sintassi di ADR 0010 §3, `is_valid_scope_entry`). Un *bersaglio*
(target) è il valore di uno degli argomenti che la capability dichiara in `scoped_arguments`
(`targets_of`, uno per nome, `None` se assente). Un bersaglio è dentro una voce (`within_scope`)
se è una stringa con la stessa sintassi e le sue parti iniziano con quelle della voce:
`workspace/notes` e `workspace/notes/a/b.md` sì; `workspace/notes-old/x`, `../workspace/notes/x`,
`/workspace/notes/x`, `workspace/./notes/x` no. Il confronto è per segmenti, non per prefisso di
stringa.

`scope_covers(scope, targets)`, tutto fail-safe (§33): un bersaglio assente o non stringa non è
coperto; uno scope non vuoto senza bersagli (una capability con `scope` e `scoped_arguments` vuoto,
che il catalogo vero rifiuta ma un fake può contenere) non è coperto — un confine che non vincola
nulla è un dubbio; scope vuoto e nessun bersaglio è coperto (`core.echo`, `model.complete` non
dichiarano confini); scope vuoto con bersagli non copre nulla. Una voce malformata protegge
niente: è saltata. La stessa funzione si applica allo scope di un'`Authorization` sui bersagli
della chiamata: un'autorizzazione con scope vuoto copre solo chiamate senza bersagli, una con
scope su una capability senza bersagli non copre (§6).

### 5. Validità di un'`Authorization`

Copre la chiamata se: `capability_id == spec.id`; se porta `task_id`/`step_id` (nata da
un'`Approval`, ADR 0003) il contesto ha lo stesso task/step — un contesto assente non basta; il
suo scope copre i bersagli (§4). Non è scaduta se `expires_at is None or expires_at > now`:
**verso chiuso**, `expires_at <= now` è scaduta (ADR 0005 §2-bis; il test verifica l'istante
esatto). Non è esaurita se `max_uses is None or authorization_uses < max_uses`.

**`authorization_uses` è un fatto del chiamante** (decisione D dell'utente): `decide` riceve il
keyword-only `authorization_uses: int = 0`, che il chiamante (l'executor, M5) legge dallo
`AuthorizationStore` (`uses`). Il chiamante fornisce fatti, il Guardian decide. Un conteggio
negativo non può essere vero: è un dubbio, `DENIED`. Firma additiva del port, con default: il
fake e il contratto si allineano; la riga sotto **estende** quella di ADR 0005 per questo port
(`tests/docs/test_adr_ports.py` la legge come estensione; nessun membro nuovo, cambia la firma
di `decide`, che `tests/docs/test_adr_guardian.py` confronta con il codice):

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `PermissionGuardianPort` | §27, §33 | sync | `decide` |

```python
def decide(
    self,
    capability: CapabilitySpec,
    arguments: JsonMapping,
    *,
    task: Task | None = None,
    step: TaskStep | None = None,
    authorization: Authorization | None = None,
    authorization_uses: int = 0,
) -> PermissionDecision: ...
```

### 6. Autorizzazione che non copre → `DENIED`, non `REQUIRES_APPROVAL`

Nessuna autorizzazione, una scaduta o una esaurita è il caso normale ("chiedi", §62). Una per
un'altra capability, per un altro task o step, o con uno scope che non copre i bersagli è un
grant sbagliato messo nelle mani del Guardian: dubbio, non mancanza (§33) → `DENIED`. I
disallineamenti sono controllati prima della scadenza: un grant sbagliato che è anche scaduto
resta sbagliato. L'`authorization_id` è comunque riportato nella decisione (contratto "echo" di
M1.3); il motivo dice se e perché non è stata applicata.

### 7. `requires_authorization` stringe soltanto

Se la specifica registrata o lo step (`TaskStep.requires_authorization`) richiedono
un'autorizzazione, anche SAFE e LOW passano dal passo 5: senza un'autorizzazione valida
`REQUIRES_APPROVAL` (`rule = AUTHORIZATION_REQUIRED`), con una valida `ALLOWED`. Mai allenta:
HIGH resta `DENIED`, LOW fuori scope resta `DENIED`.

### 8. Ogni decisione nell'Audit Log, e nessuna via non registrata

`decide` resta il port: sincrono e puro (ADR 0005 §4, contratto `test_decide_is_synchronous`),
non tocca l'audit. L'ingresso audited è
`async authorize(capability, arguments, *, task, step, authorization, authorization_uses)`:
chiama `decide`, scrive un `AuditEvent` `PERMISSION_DECIDED` e ritorna la decisione. L'evento ha
attore `Actor(SYSTEM, "permission-guardian")` (`GUARDIAN_ACTOR`), `created_at` della decisione,
`summary = "decide: <esito> <capability> (<rischio>): <motivo>"`, `task_id`/`step_id`/
`capability_id`/`decision_id`/`authorization_id`, e un payload con `outcome`, `risk`, `policy`,
`rule`, `reason`, `targets`, `expires_at` (ISO 8601 o `null`) e `error` quando c'è. Se `append`
solleva, l'eccezione esce e la decisione non viene consegnata: una decisione non registrata non
esiste. ADR 0008 §3 prende nello stato il rimando: `PERMISSION_DECIDED` lo scrive il Guardian.

**Gli argomenti non finiscono nel payload, i bersagli sì** (decisione H dell'utente). Gli
argomenti portano contenuto dell'utente — il testo di una nota, il prompt di `model.complete`:
documenti, email, codice, informazioni personali (§57) — e l'Audit Log è append-only e
concatenato per hash (ADR 0007): ciò che entra non si redige più. Per la stessa ragione il
`reason` di un diniego per argomenti nomina solo i percorsi JSON delle violazioni (`$.message`),
mai i valori, e quello di un errore interno il *tipo* dell'eccezione, mai il messaggio. I bersagli
sono i percorsi su cui la decisione di scope si è basata: senza di essi il log non risponde a
"perché lo ha fatto" (§32) per LOW. Sono nel payload e, quando un diniego li riguarda, nel
`reason`.

**Regola architetturale 14** (`check_decide_callers`, `tests/architecture/rules.py`): fuori da
`ela.permissions` nessun modulo di `src/ela` contiene una chiamata `<qualcosa>.decide(`. Nessuna
esenzione: il fake *definisce* `decide`, non lo chiama; il Guardian chiama `self.decide` dentro
il package. Chi vuole una decisione chiama `authorize`. Nessun contratto import-linter: non è un
import.

### 9. Scadenza della decisione

Una decisione `ALLOWED` scade: `expires_at = now + decision_ttl`, e non oltre
`authorization.expires_at` se si regge su un'autorizzazione (il minimo dei due). `decision_ttl`
è un `timedelta` del costruttore, default `DEFAULT_DECISION_TTL = 5 minuti`; zero o negativo →
`ValueError` alla costruzione (un Guardian che emette decisioni già scadute non permette mai
nulla: errore di configurazione, non policy). `DENIED` e `REQUIRES_APPROVAL` non scadono
(`None`): non autorizzano nulla, non c'è replay da impedire.

Perché una scadenza: una decisione `ALLOWED` è un titolo al portatore — il tool la accetta come
dato (ADR 0005 §5) e non richiama il Guardian. Senza scadenza una decisione conservata potrebbe
eseguire dopo che l'autorizzazione è scaduta o revocata, e il contratto del tool di M1.3
("rifiuta una decisione scaduta") resterebbe senza oggetto. Il verso è chiuso anche qui:
`expires_at <= now` è scaduta (ADR 0005 §2-bis), e il test del tool verifica l'istante esatto.
Perché cinque minuti: il TTL deve coprire il tragitto decisione → esecuzione; in-process sono
millisecondi, ma nel sistema distribuito (§56) la decisione viaggia fino a un nodo Mac/Windows/
iPhone, e un minuto è poco con un nodo lento. Cinque minuti coprono il tragitto e tengono corta la
finestra di replay; un deployment può stringerli.

### 10. Forma della decisione

`id` dal generatore, `created_at` dall'orologio (entrambi letti *prima* della valutazione, §11),
`capability_id` della chiamata, `risk` della specifica registrata (quello passato solo se l'id è
ignoto), `outcome`, `reason` leggibile, `task_id`/`step_id`/`authorization_id` dal contesto,
`expires_at` (§9), `metadata = {"policy": "v0.1", "rule": <Rule>, "targets": [...]}` più
`"error"` per un errore interno.

### 11. Fail-safe

`decide` non solleva mai per ciò che accade dentro la valutazione: un registro che solleva,
argomenti malformati, un bug, producono `DENIED` con `rule = INTERNAL_ERROR`, motivo
`"internal error: <TipoEccezione>"` e `metadata["error"] = <TipoEccezione>`. L'orologio e il
generatore di id sono letti prima della valutazione: se sollevano, l'eccezione esce e non esiste
nessuna decisione — che è ancora "non agire" (§33). Se `authorize` non riesce a scrivere l'audit,
idem (§8).

### 12. Regola architetturale 12: fuori da `ela.permissions` nessuno costruisce una decisione `ALLOWED`

Regola AST closed-world `check_decision_builders`: segnala `PermissionDecision(...)` il cui
`outcome` non è il letterale `PermissionOutcome.DENIED` / `"DENIED"` — una variabile, un altro
membro, o nessun `outcome` (`**kwargs`) sono dubbi — e `x.model_copy(update={"outcome": ...})`,
in ogni modulo di `src/ela` fuori da `ela.permissions` **e** fuori da `ela.testing`. L'esenzione di
`ela.testing` (decisione I dell'utente) non apre nulla che la regola voglia chiudere: la regola
serve a impedire che codice di *produzione* conii un `ALLOWED`, e la regola 6 con il contratto
import-linter 5 garantiscono che nessun modulo di produzione importi i fake (ADR 0005); il fake a
tabella deve poter rispondere `ALLOWED` perché i test dell'executor (M5) esercitino il ramo felice
senza legarsi a policy e catalogo. L'elenco dei prefissi esenti è chiuso (due) e ha casi positivi
e negativi in `violations.py`. `tests/` sta fuori da `src/ela` e non è toccato. Nessun contratto
import-linter: non è un import.

### 13. Regola 13 e contratto 8 (ADR 0010 §7), registrazione, gate

`guardian.py` e `scope.py` importano solo stdlib, `ela.domain`, `ela.ports`, il package stesso;
nessuna esenzione. `ela.domain` esporta `JsonValue` (riesportazione additiva di un tipo che il
dominio già usava) perché il Guardian tipizzi i payload senza importare pydantic. In
`tests/contracts/test_guardian.py` un test speculare a `test_tool_holds_no_guardian_and_no_store`:
nessun attributo dell'istanza e nessun hint di `__init__`/`decide` è `ToolPort`, `ModelProvider`,
`ProviderRegistry`. `PermissionGuardian` è registrato in `tests/contracts/implementations.py`
sul `CapabilityRegistry` vero costruito con lo stesso catalogo del contratto del registro
(`REGISTRY_CATALOGUE`), con `FakeClock`, `FakeIdGenerator`, `FakeAuditLog`: eredita i test di
contratto del port. `ela.permissions` è in `CRITICAL_PACKAGES` da M4.1: 100% branch coverage.

### 14. Struttura del package

`ela.permissions.scope` (`targets_of`, `within_scope`, `scope_covers`) e
`ela.permissions.guardian` (`PermissionGuardian`, `Rule`, `RISK_POLICY`, `POLICY_VERSION`,
`GUARDIAN_ACTOR`, `DEFAULT_DECISION_TTL`), riesportati da `ela.permissions`.

### 15. Coerenza con lo step

Se `step` è passato e `step.required_capabilities` è una tupla non vuota che non contiene la
capability, `DENIED` con `rule = STEP_MISMATCH` e motivo `"step <id> does not require
<capability>"`. `step=None` o tupla vuota non vincolano: §13 dice che uno step *può* dichiarare le
capacità necessarie, una tupla vuota è "non dichiarato". Il piano approvato (`WAITING_APPROVAL`,
§14) è l'unico punto in cui l'utente vede *quali* capability userà ogni step: una chiamata a una
capability che lo step non ha dichiarato è una deviazione dal piano approvato, la deviazione per cui
il Guardian esiste (§47, §65 "bypassare autorizzazioni"). Come §7, il contesto stringe soltanto:
uno step che dichiara la capability non allenta nulla. `step.risk` non è usato: il rischio della
decisione è quello della specifica registrata, un piano non può abbassarlo.

## Alternative considerate

- **Fidarsi della specifica passata, nessun catalogo nel Guardian** — semplice; ma "capability
  ignota → DENIED" non regge e una `CapabilitySpec` con `risk=SAFE` costruita da chiunque
  aggirerebbe la policy. Scartata (già in ADR 0010).
- **Controllare solo id e rischio, non l'intera specifica** — uno scope allargato o uno schema
  permissivo sarebbero passati. Uguaglianza completa. Scartata.
- **Scope come prefisso di stringa** — `workspace/notes-old` passerebbe per `workspace/notes`.
  Per segmenti. Scartata.
- **Autorizzazione che non copre → `REQUIRES_APPROVAL`** — tratta un grant sbagliato come una
  mancanza, e l'utente riceverebbe una richiesta per una chiamata che qualcuno ha già provato a
  coprire con il grant di un'altra. Dubbio → `DENIED`. Scartata.
- **Il Guardian legge il conteggio degli usi dallo store** — gli darebbe I/O e un port che non
  deve possedere (ADR 0005 §4). Il chiamante porta il fatto. Scartata.
- **`decide` scrive l'audit** — il port diventerebbe async e impuro, e ogni test di policy
  avrebbe bisogno di un log. Due ingressi, uno puro e uno audited, con la regola 14 a chiudere
  quello puro. Scartata.
- **Domanda di approvazione prima dei dinieghi della tabella** — chiederebbe all'utente di
  approvare ciò che sarà negato comunque. I dinieghi precedono. Scartata.
- **Coerenza con lo step in forma stretta (tupla vuota → `DENIED`)** — legge in §13 un obbligo
  che non c'è ("può specificare") e romperebbe ogni piano senza capability dichiarate. Solo
  restrizione. Scartata.
- **Nessuna coerenza con lo step in v0.1** — era la posizione iniziale ("non è nel prompt"); il
  controllo è puro, usa solo dati già nel contesto e chiude l'unica via per cui un'esecuzione può
  discostarsi dal piano approvato senza che il Guardian se ne accorga. Adottata (§15).
- **Nessuna scadenza della decisione** — farebbe di un `ALLOWED` un titolo permanente e del
  contratto del tool di M1.3 una clausola senza oggetto. Scartata. **Un minuto** — troppo poco
  per il tragitto Core → nodo remoto (§56). Scartata.
- **Digest SHA-256 degli argomenti nel payload, per legare decisione ed esecuzione** — su
  argomenti a bassa entropia (`core.echo` con un testo breve) il digest si inverte per dizionario;
  il legame decisione → esecuzione lo dà già `decision_id`, che M5 riporterà in `TOOL_EXECUTED`.
  Scartata.
- **Messaggi di `jsonschema` nel `reason` dei dinieghi per argomenti** — contengono il valore che
  ha violato lo schema, cioè contenuto dell'utente, e il `reason` va nell'audit (§57). Solo i
  percorsi JSON. Scartata.
- **Nessuna esenzione dalla regola 12, fake che non risponde mai `ALLOWED`** — i test
  dell'executor dovrebbero usare il Guardian vero con registro e autorizzazioni per il ramo felice
  e ogni test si legherebbe a policy e catalogo. Il fake esiste per quello; la regola 6 lo tiene
  fuori dalla produzione. Scartata.
- **Conteggio negativo trattato come zero** — un fatto che non può essere vero è un dubbio, non
  un default. `DENIED`. Scartata.

## Conseguenze

- `PermissionGuardian`, `Rule`, `RISK_POLICY`, `POLICY_VERSION`, `GUARDIAN_ACTOR`,
  `DEFAULT_DECISION_TTL`, `targets_of`, `within_scope`, `scope_covers` sono l'API pubblica in più
  di `ela.permissions`. `ela.domain` esporta `JsonValue`.
- `PermissionGuardianPort.decide` ha il keyword-only `authorization_uses: int = 0`: ADR 0005 resta
  immutabile e prende nello stato il rimando; il fake e il contratto sono allineati.
- **L'Audit Log non è un canale neutro** (precisazione dell'utente, 2026-09-05). I bersagli sono
  path e possono contenere informazioni personali dell'utente nel nome (§57):
  `workspace/notes/<qualcosa di privato>.md` finisce in un log append-only e concatenato per
  hash, da cui non si redige più. Registrarli è una scelta di privacy consapevole, presa perché
  senza di essi il log non spiega le decisioni di scope. Il Memory Core e il Context Core (fasi
  future) devono saperlo prima di leggere l'audit o di alimentarlo: ciò che vi scrivono è
  permanente e ciò che vi leggono può essere personale. Gli argomenti, il corpo delle note e i
  prompt non vi entrano mai dal Guardian; i messaggi delle eccezioni e dei validatori nemmeno.
- La tabella di §3 e la firma di §5 sono verificate dal codice (`tests/docs/test_adr_guardian.py`,
  con casi negativi); la riga di §5 è letta da `tests/docs/test_adr_ports.py` come estensione.
- Regole 12 e 14 in `tests/architecture/rules.py` con casi in `violations.py`; nessun nuovo
  contratto import-linter. Un test di vacuità verifica che `guardian.py` costruisca decisioni e
  chiami `self.decide`, altrimenti le due regole varrebbero a vuoto.
- **Bersagli solo per nome di argomento**: uno scope protegge ciò che la capability dichiara in
  `scoped_arguments`; un tool che scrivesse altrove ignorando l'argomento è un problema del tool
  (M5/M7), non del Guardian (già in ADR 0010).
- **`authorization_uses` è un fatto del chiamante**: un conteggio falso inganna il Guardian. Il
  chiamante è l'executor (M5), codice del Core; lo store conta (ADR 0005). Il Guardian rifiuta
  solo ciò che non può essere vero (negativo).
- L'executor (M5) chiama `authorize`, registra l'uso (`record_use`) dopo l'esecuzione e scrive
  `TOOL_EXECUTED` con il `decision_id`; chi ottiene `REQUIRES_APPROVAL` crea l'`Approval`
  (engine, `APPROVAL_REQUESTED`): il Guardian decide, non chiede (§27).
- Un piano i cui step dichiarano `required_capabilities` è vincolato a esse in esecuzione (§15):
  il Planner (M6.2) deve dichiarare tutto ciò che uno step userà, o non dichiarare nulla.
