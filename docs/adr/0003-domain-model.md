# 0003. Forma del domain model: identità, tempo, immutabilità, ordine del rischio

- **Stato:** Accettata. `Authorization` vincolata (grant da approvazione ⇒ monouso e legato) e `Approval.targets` aggiunto da ADR 0012 §1. `ExecutionResult.decision_id` e `authorization_id` aggiunti da ADR 0015 §2: un risultato sa da quale decisione e quale grant è nato. **ADR 0018 §2**: `TaskStep.arguments: JsonMapping` — gli argomenti della capability dello step stanno nel piano, non nella chiamata, perché ciò che viene autorizzato sia ciò che viene eseguito anche dopo un crash; il dominio li tiene come dati e non li valida contro `input_schema` (è del Guardian, §27).
- **Data:** 2026-09-04
- **Riferimenti spec:** §13, §14, §16, §17, §28, §29, §32, §33, §49, §51, §63, §64
- **Milestone:** M1.1

## Contesto

§49 elenca le entità fondamentali di ELA ma non ne fissa la forma. Prima di scrivere
`src/ela/domain.py` sono emerse cinque scelte che valgono per tutto il dominio e che sarebbero
costose da cambiare dopo, perché ogni milestone successiva (Task Engine, Guardian, Audit,
persistenza, API) ci si appoggia. Sono state decise in review il 2026-09-04 e sono elencate anche
in `docs/milestones/M1.1.md`.

## Decisione

### 1. Entità e value object

- **Entità**: ha identità e un ciclo di vita, quindi un id tipizzato e un `created_at`
  obbligatorio. Due entità con gli stessi valori restano cose diverse.
- **Value object**: è definito interamente dai suoi valori, non ha identità né ciclo di vita,
  vive dentro l'entità che lo contiene. Nessun id, nessun `created_at`.

Sono value object `DeviceCapability` (§16), `ProviderUsage` (§32), `ErrorMetadata` (§64) e
`Actor` (§32): "24 GB di VRAM", "1200 token in ingresso", "timeout del tool" e "l'utente
tommaso" non sono cose che si aggiornano, si sostituiscono insieme all'entità che le contiene. È
una deroga consapevole alla formula "ogni entità di §49 ha un id tipizzato": si applica alle
entità, non ai valori. `Actor.id` è un identificatore, non l'id di un'entità del dominio: dice
*quale* attore, mentre `kind` dice di che tipo di attore si tratta.

### 1-bis. `Actor` invece di una stringa libera (review M1.1)

§49 non elenca un attore, e la prima versione di `AuditEvent` aveva `actor: str`. Un audit log è
la risposta alla domanda "chi ha fatto cosa, con quale autorizzazione" (§32): con una stringa
libera `"ela"`, `"ELA"` ed `"ela@macbook"` sono tre attori diversi per il log e lo stesso attore
per chi legge, e non si può interrogare il log per "tutto ciò che ha fatto l'utente".

Quindi `Actor(kind: ActorKind, id: str)` con `ActorKind` = ELA, USER, DEVICE, SYSTEM. `SYSTEM`
copre ciò che nessuno ha chiesto: scheduler, retry, scadenze. `id` non può essere vuoto: un
evento di audit senza attore identificabile non è un evento di audit.

È un modello in più rispetto a §49 e come tale è dichiarato in
`tests/domain/test_spec_coverage.py::REVIEW_ADDITIONS`: aggiungere un modello che §49 non prevede
resta una decisione da argomentare, non un dettaglio implementativo. La scelta è stata presa in
review prima che l'audit venisse persistito, quando cambiarla costa un `sed`; dopo sarebbe
costata una migrazione.

### 2. Id tipizzati, con una eccezione

Ogni entità ha un id `NewType` su `UUID` (`TaskId`, `StepId`, `DeviceId`, …). Il `NewType` non
esiste a runtime: distingue `TaskId` da `StepId` solo per mypy. È esattamente ciò che serve —
scambiare due UUID è un errore da compilazione, non da produzione — e il limite è documentato da
un test (`test_ids_are_not_interchangeable_at_runtime`).

L'eccezione è `CapabilityId`, un `NewType` su `str` con nome dotted validato da
`^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`. §29 fissa nomi stabili e leggibili (`core.echo`,
`workspace.write_note`, `model.complete`): quello *è* l'identificatore della capability. Un UUID
aggiuntivo darebbe due identità alla stessa cosa e due modi di sbagliare chiave nell'audit.
`DeviceCapabilityName` usa lo stesso stile con almeno un segmento (`camera`, `gpu.cuda`).

### 3. Il piano non nomina i nodi (§13 letto insieme a §17)

§13 elenca "dispositivo preferito" tra i campi dello step e, tre righe dopo, dice che il piano
deve essere indipendente dal dispositivo; §17 assegna la scelta del nodo al Device Orchestrator.
Le due frasi si conciliano solo se la preferenza è espressa in *capacità*, non in nodi:
`TaskStep.preferred_device_traits: tuple[DeviceCapabilityName, ...]`.

ELA non pensa "questo task appartiene al Mac", pensa "questo task richiede queste capacità"; poi
l'orchestratore sceglie. La regola è verificata da
`tests/architecture/test_domain_models.py::test_plan_is_device_independent`, che ispeziona
ricorsivamente le annotazioni di `TaskPlan` e `TaskStep` e fallisce se compare `DeviceId`,
`Device`, `OperatingSystem` o un enum di stato del dispositivo.

Conseguenza pratica: `DeviceCapability` (tratto hardware/software di un nodo) e `CapabilitySpec`
(azione autorizzabile dal Guardian) sono concetti diversi con nomi simili. Le docstring di
entrambi rimandano all'altro.

### 4. Il dominio non legge l'orologio

`created_at` è obbligatorio in ogni entità e non ha `default_factory`. Un
`default_factory=lambda: datetime.now(UTC)` sarebbe I/O dentro il dominio: renderebbe i test
dipendenti dall'ora reale e impedirebbe di ricostruire un'entità da un log o da un database senza
trucchi. Il `Clock` arriva come port in M1.3; chi costruisce l'entità passa l'istante.

Tutti i datetime sono timezone-aware e normalizzati a UTC (`UtcDatetime`): un datetime naive è
rifiutato. Un istante senza fuso in un sistema distribuito su tre nodi è un bug che aspetta.

### 5. Immutabilità profonda

`frozen=True` protegge il campo, non ciò a cui il campo punta: con un `list` o un `dict` il
modello resterebbe mutabile dall'interno. Quindi:

- le sequenze sono `tuple`, mai `list` o `set`;
- i payload JSON liberi usano `JsonMapping`, che valida come JSON e congela ricorsivamente
  (`MappingProxyType` per le mappe, `tuple` per gli array) e riserializza in contenitori JSON
  normali.

Limite noto e accettato: chi legge un payload trova tuple dove il JSON aveva array. È il prezzo
dell'immutabilità reale, ed è visibile solo dentro i payload liberi, non nei campi tipizzati.

### 6. `RiskLevel` è ordinato

L'ordine SAFE < LOW < MEDIUM < HIGH < CRITICAL è semantica di §29, non logica applicativa: il
Guardian ragionerà per soglie ("al massimo MEDIUM"). `RiskLevel` resta uno `StrEnum` per la
serializzazione, ma i confronti sono ridefiniti esplicitamente perché quelli ereditati da `str`
sarebbero alfabetici — CRITICAL < HIGH < LOW < MEDIUM < SAFE — cioè esattamente il contrario del
significato. Un confronto con qualcosa che non è un `RiskLevel` solleva `TypeError` invece di
ricadere silenziosamente sull'ordine alfabetico di `str`.

### 7. Evoluzione degli enum

Aggiungere un valore a un enum di evento (`TaskEventType`, `AuditEventType`) o di stato è una
modifica **additiva** e non richiede un ADR, anche quando l'audit log sarà persistito: il log
memorizza stringhe, i valori già scritti restano validi e nulla di ciò che è stato registrato
cambia significato.

Rinominare o rimuovere un valore è invece una modifica **rompente**: le righe già scritte
continuerebbero a contenere il vecchio nome, che nessun enum saprebbe più leggere. Richiede un
ADR e una migrazione esplicita.

Gli enum fissati dalla spec — `TaskState` (§14), `RiskLevel` (§29), `PermissionOutcome` (§27),
`ApprovalStatus` (§30), `ExecutionStatus` (§63) — sono chiusi: aggiungere un valore lì significa
cambiare la spec, e i test in `tests/domain/test_enums.py` lo rendono visibile.

### 8. Nessun comportamento

I modelli sono dati. `TaskState` è un campo: quali transizioni siano legali lo decide il Task
Engine (M1.2). `PermissionDecision.outcome` è obbligatorio e senza default: il fail-safe "nel
dubbio DENIED" di §33 è una decisione del Guardian (M1.3), e un default silenzioso nel modello
nasconderebbe un bug del chiamante invece di farlo emergere.

## Alternative considerate

- **`preferred_device: DeviceId | None` come hint non vincolante** — fedele alla lettera di §13,
  ma mette un riferimento a un nodo dentro il piano: la prima ottimizzazione che lo legge lo
  trasforma in un vincolo di fatto, e §13 non è più verificabile.
- **Omettere del tutto la preferenza** — perde informazione che il planner conosce ("questo step
  vuole una GPU") e che l'orchestratore dovrebbe reinventare.
- **UUID anche per `CapabilitySpec`, con `name` separato** — due identità per la stessa cosa, e
  ogni riga di audit dovrebbe scegliere quale usare.
- **`default_factory=now` su `created_at`** — comodo, ma introduce I/O e non determinismo nel
  livello che deve restarne privo, e rende impossibile ricostruire fedelmente un'entità passata.
- **`dict` normale nei payload, con l'immutabilità documentata** — più semplice, ma "immutabile
  tranne dove conta" non è immutabile; il Guardian legge `input_schema` e `scope`.
- **Un wrapper `FrozenDict` esplicito** — equivalente, più codice; `MappingProxyType` con
  `AfterValidator`/`PlainSerializer` fa lo stesso con quattro righe e uno schema JSON corretto.
- **`actor: str` con una convenzione di formato** (per esempio `"user:tommaso"`) — nessuna
  validazione, nessun tipo, e il primo `"tommaso"` scritto senza prefisso resta nel log per
  sempre.
- **`IntEnum` per `RiskLevel`** — ordinabile per costruzione, ma serializza numeri: un audit log
  con `risk: 3` è illeggibile e fragile a un'aggiunta in mezzo alla scala.
- **Lasciare l'ordine di `RiskLevel` a M1.3** — significherebbe che nel frattempo `SAFE < HIGH` è
  `False` senza che nulla lo segnali: un confronto sbagliato e silenzioso su un dato di sicurezza.

## Conseguenze

- Ogni nuovo modello del dominio deve essere frozen, chiuso (`extra="forbid"`), senza collezioni
  mutabili e senza default che leggono l'orologio: quattro architecture test in
  `tests/architecture/test_domain_models.py` lo verificano, ognuno con il proprio caso negativo.
- Ogni nuovo modello deve comparire in `ela.domain.__all__`, in `tests/domain/examples.py` e in
  `tests/domain/strategies.py`, altrimenti `tests/domain/test_spec_coverage.py` fallisce.
- Un modello che §49 non prevede va dichiarato in `REVIEW_ADDITIONS` con la sua motivazione: oggi
  contiene solo `Actor`.
- Aggiungere un'entità non prevista da §49 fa fallire
  `test_every_public_model_belongs_to_section_49`: è una modifica alla spec, non un dettaglio
  implementativo.
- `pydantic` diventa dipendenza runtime (ADR 0001 lo prevedeva "quando `domain.py` avrà
  contenuto"). Resta l'unica libreria di terze parti ammessa nel dominio dal contratto
  import-linter 1.
- Chi costruisce un'entità deve procurarsi l'istante: finché il `Clock` port non esiste (M1.3), i
  chiamanti passano `datetime.now(UTC)` esplicitamente.
- Modificare un'entità significa costruirne un'altra (`model_copy(update=...)`): il Task Engine di
  M1.2 produrrà nuovi `Task`, non muterà quelli esistenti.
