# 0010. Catalogo delle capability v0.1: registro immutabile, port ridotto, validazione JSON Schema, rischio massimo MEDIUM

- **Stato:** Accettata
- **Data:** 2026-09-05
- **Riferimenti spec:** §26, §27, §28, §29, §33, §49, §50, §51, §52, §54, §57
- **Milestone:** M4.1

## Contesto

§28 separa la Capability (specifica: id, rischio, schema, scope, requisiti di autorizzazione)
dal Tool (implementazione) "per impedire che un tool possa bypassare il sistema di sicurezza".
§29 fissa le tre capability di produzione di v0.1 — `core.echo` (SAFE), `workspace.write_note`
(LOW, "solamente all'interno di uno scope autorizzato"), `model.complete` (MEDIUM) — e dice che
HIGH e CRITICAL non vengono introdotte. Fino a M3.2 esistevano il port `CapabilityRegistryPort`
(ADR 0005: `register`, `get`, `specs`) e un fake mutabile. Il Guardian (M4.2) deciderà "sulla base
di specifiche e contesto" (§27): deve poter fidarsi delle specifiche, quindi il catalogo che le
tiene è la prima delle proprietà di sicurezza, non un dettaglio. Le domande erano: chi può
aggiungere una capability e quando; come si valida ciò che entra e ciò che una chiamata porta;
cosa significa "scope" per la capability che ne ha uno.

## Decisione

### 1. Il registro è immutabile: il port perde `register`

`ela.permissions.capabilities.CapabilityRegistry(specs)` valida e congela alla costruzione.
L'istanza espone `get` e `specs`, nient'altro: nessun metodo pubblico muta lo stato, la mappa
interna è un `MappingProxyType`, la classe ha `__slots__`. Ciò che ELA può fare è deciso quando
il registro nasce; nulla che giri dopo — un planner, la risposta di un provider, un tool — può
allargarlo.

Un port che promette `register` a un'implementazione che lo rifiuta è una bugia nel contratto
(i test di contratto lo chiamerebbero e fallirebbero sul registro vero); un `register` che
funziona "finché non si congela" è un register pubblico a runtime. Quindi `CapabilityRegistryPort`
diventa `get`, `specs`. La riga sotto **sostituisce** quella di ADR 0005 per questo port;
`tests/docs/test_adr_ports.py` legge le righe sostitutive dopo le estensioni, con la regola che
una sostituzione può solo togliere membri (chi aggiunge scrive un'estensione, ADR 0008 §2):

Port sostituiti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `CapabilityRegistryPort` | §28, §29 | sync | `get`, `specs` |

`FakeCapabilityRegistry(specs=())` si allinea: costruttore, nessun `register`, stesso
`AlreadyExistsError` al doppione; non valida altro, così un test può registrare una capability
HIGH e vederla negata. Il contratto (`tests/contracts/test_capability_registry.py`) costruisce
ogni implementazione con lo stesso catalogo, legge, e verifica che *nessuna* implementazione
abbia membri pubblici oltre a quelli del port.

### 2. Validazione alla costruzione, tutta o niente

Per ogni specifica, nell'ordine: `risk <= MAX_RISK` con `MAX_RISK = RiskLevel.MEDIUM`
(`RiskNotAllowedError`: §29, "le capability HIGH e CRITICAL non vengono introdotte in produzione
nella prima versione"); `input_schema` è uno schema JSON valido del Draft 2020-12
(`Draft202012Validator.check_schema`); ogni voce di `scope` è un percorso POSIX relativo senza
segmenti vuoti, `.` o `..` e senza `\`; ogni nome in `scoped_arguments` è una proprietà di tipo
`string` dichiarata in `input_schema.properties`; scope e `scoped_arguments` sono entrambi
presenti o entrambi assenti — uno scope che non vincola nulla, o un argomento scoped senza
scope, è un dubbio (§33). Gli ultimi quattro sono `InvalidCapabilityError` con capability e
motivo. Un id già visto è `AlreadyExistsError`. Un errore qualsiasi ⇒ nessun registro: un
catalogo non è mai costruito a metà.

### 3. `CapabilitySpec.scoped_arguments` (campo additivo del dominio)

`scoped_arguments: tuple[str, ...] = ()` dice quali argomenti lo scope vincola (`("path",)` per
chi scrive note). Nel dominio è dato, come `scope` (ADR 0003 §8): la coerenza con lo schema è del
registro (§2). Additivo con default: nessuna migrazione, nessun cambiamento per chi non lo usa
(ADR 0003 §7). La semantica "il bersaglio è dentro lo scope" — prefisso di percorso — si applica
in M4.2; qui si fissa la sintassi delle voci (`is_valid_scope_entry`) perché il catalogo deve
poterla validare.

### 4. Validazione degli argomenti: funzione pura, con `jsonschema`

`validate_arguments(spec, arguments) -> None` (`InvalidArgumentsError(capability_id, errors)`)
valida gli argomenti di una chiamata contro `spec.input_schema`: ogni violazione, non solo la
prima, come `<json path>: <messaggio>` in ordine di percorso. È pura (nessun I/O, nessuno
stato) e non è un membro del port: il Guardian riceve la specifica e la chiama sullo schema
della specifica *registrata* prima di ogni altro controllo (M4.2). I payload congelati del
dominio (`MappingProxyType`, tuple) sono letti come JSON semplice da una copia locale.

Il validatore è `jsonschema` (Draft 2020-12), dipendenza del Core: libreria pura, non è fra
quelle che il Core non può importare (CLAUDE.md, contratto 3). Nessun `$ref` viene mai risolto in
rete: il validatore è costruito senza resolver, un riferimento remoto è un errore, non un fetch.
ADR 0001 prende nello stato il rimando.

### 5. Il catalogo v0.1

`catalogue_v01(*, notes_scope: str = DEFAULT_NOTES_SCOPE)` costruisce esattamente le tre
capability di §29, con `created_at = V01_INTRODUCED_AT` (costante UTC: il catalogo è dichiarato,
non nasce a runtime, quindi non ha orologio) e `DEFAULT_NOTES_SCOPE = "workspace/notes"`, una
convenzione finché la Configuration (M8.1) non lo leggerà dall'ambiente. La tabella è verificata
contro il codice da `tests/docs/test_adr_catalogue.py` (id, rischio, scope, argomenti scoped,
autorizzazione, argomenti obbligatori e opzionali con il loro tipo):

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Obbligatori | Opzionali |
|---|---|---|---|---|---|---|
| `core.echo` | SAFE | — | — | no | `message: string` | — |
| `workspace.write_note` | LOW | `workspace/notes` | `path` | no | `path: string`, `body: string` | — |
| `model.complete` | MEDIUM | — | — | sì | `input: string` | `purpose: string`, `instructions: string`, `model_hint: string`, `parameters: object` |

Tutti gli schemi hanno `"type": "object"` e `"additionalProperties": false`: un argomento non
previsto è un errore, non rumore (§33). `model.complete` ricalca `ProviderRequest` (§26, §50):
il tool (M7.2) costruirà la richiesta senza traduzioni e lo schema è il contratto che l'API
esporrà. `requires_authorization` segue §29 e la policy v0.1 del Guardian: `write_note` è
protetta dallo scope e non richiede autorizzazione; `model.complete` la richiede sempre, perché
il contenuto dell'utente esce verso un provider esterno (§29, §57).

### 6. Errori

In `ela.permissions.errors`: `PermissionsError` (base); `CapabilityNotFound(NotFoundError)` —
il port promette `NotFoundError`, chi vuole distinguere prende la sottoclasse;
`InvalidCapabilityError(capability_id, reason)`; `RiskNotAllowedError(InvalidCapabilityError)`
con `risk` e `max_risk`; `InvalidArgumentsError(capability_id, errors)`.

### 7. Regola architetturale 13 e contratto 8: `ela.permissions` importa solo stdlib, dominio, port e `jsonschema`

Il Guardian deve essere "sufficientemente indipendente dal resto del sistema da poter bloccare
ELA" (§47): il package che lo ospita non importa tool, provider, infrastruttura, engine, audit,
né pydantic direttamente. Regola AST closed-world `check_permissions_imports` in
`tests/architecture/rules.py` e contratto import-linter 8 (`allow_indirect_imports = "True"`,
come 2 e 6: il dominio porta pydantic e `jsonschema` porta le sue dipendenze). La regola
anticipa M4.2 di una milestone perché la dipendenza da `jsonschema` nasce qui e la sua lista di
import permessi va dichiarata insieme.

### 8. `ela.permissions` nel gate `cov-critical`

CLAUDE.md "Qualità": il package entra in `CRITICAL_PACKAGES` nella milestone in cui riceve
codice. 100% branch coverage da questa milestone.

## Alternative considerate

- **`register` nel port, `RegistryFrozenError` nel registro vero** — il contratto promette ciò
  che l'implementazione rifiuta; i test di contratto su `register` dovrebbero girare solo sul
  fake, contro "ogni implementazione passa gli stessi test" (ADR 0005 §6). Scartata.
- **`register` che funziona fino a `freeze()`** — è un register pubblico a runtime, finché
  qualcuno non chiama `freeze`; e chi dimentica di chiamarlo ha un registro aperto. Scartata.
- **Fidarsi della specifica passata al Guardian, nessun catalogo** — semplice, ma il contratto
  "capability ignota → DENIED" non regge e chiunque costruisca una `CapabilitySpec` con
  `risk=SAFE` per `model.complete` aggira il Guardian. Scartata (M4.2 decisione B).
- **Validatore JSON Schema scritto a mano per il sottoinsieme usato** — nessuna dipendenza, ma un
  validatore in più da mantenere e testare: esattamente il codice security-critical che non
  vogliamo scrivere noi. Scartata.
- **Validazione degli argomenti come metodo del registro** — fuori dal port, il Guardian
  dipenderebbe dalla classe concreta, o il port si allargherebbe con un membro che non legge lo
  stato. Funzione pura. Scartata.
- **Quale argomento lo scope vincola via `metadata` o parola chiave custom nello schema** — non
  tipizzato, o invisibile a chi legge la specifica. Campo tipizzato con default. Scartata.
- **`created_at` dall'orologio** — renderebbe il catalogo non deterministico e gli darebbe una
  dipendenza che non usa. Costante. Scartata.
- **Costante fissa per lo scope delle note, senza parametro** — la Configuration (M8.1) dovrebbe
  poi cambiare la firma. Parametro con default. Scartata.

## Conseguenze

- `CapabilityRegistry`, `catalogue_v01`, `validate_arguments`, `check_capability`,
  `is_valid_scope_entry`, `MAX_RISK`, `SCHEMA_VALIDATOR`, `DEFAULT_NOTES_SCOPE`,
  `V01_INTRODUCED_AT`, gli id `CORE_ECHO`/`WORKSPACE_WRITE_NOTE`/`MODEL_COMPLETE` e le tre
  funzioni di specifica sono l'API pubblica di `ela.permissions.capabilities`; i cinque errori
  quella di `ela.permissions.errors`.
- `CapabilityRegistryPort` ha due membri; ADR 0005 resta immutabile e prende nello stato il
  rimando a questo ADR. Il test doc-vs-code dei port conosce estensioni (aggiungono) e
  sostituzioni (tolgono), ciascuna con caso negativo.
- `jsonschema` (con `referencing`, `jsonschema-specifications`, `rpds-py`) è una dipendenza del
  Core; `types-jsonschema` di sviluppo per `mypy --strict`.
- La tabella di §5 e la riga di §1 sono verificate dal codice: cambiare una delle due senza il
  codice rompe `make check`.
- `CapabilitySpec.scoped_arguments`: additivo, nessuna migrazione (ADR 0003 §7). L'esempio
  `CAPABILITY_SPEC` dei test prende `scoped_arguments=("path",)`.
- Un tool che scrivesse altrove ignorando l'argomento scoped è un problema del tool (M7), non
  del catalogo: lo scope protegge ciò che la capability dichiara.
- Il Guardian (M4.2) eredita da qui il catalogo, la validazione degli argomenti come primo
  controllo, `CapabilityNotFound` e la sintassi delle voci di scope.
