# 0018. Gli `arguments` di uno step stanno nel piano: `TaskStep.arguments`, regola 23

- **Stato:** Accettata
- **Data:** 2026-09-07
- **Riferimenti spec:** §13, §27, §28, §30, §32, §33, §57
- **Milestone:** M6.3

## Contesto

`Executor.execute(task_id, step_id, arguments)` prendeva gli argomenti **dal chiamante**. Nel
dominio non esisteva nessun posto dove vivessero: `TaskStep` ha `goal`, `expected_result` e
`success_conditions` — testo — e non un payload per il tool. Finché l'executor è stato chiamato
dai test, il chiamante li ha inventati; un runner (M6.3) non può.

Non è una domanda di dettaglio. Gli argomenti sono ciò che il Guardian valida contro
`CapabilitySpec.input_schema`, ciò su cui si applica lo scope (`scoped_arguments` → `targets_of`,
ADR 0010) e ciò che finisce nei `targets` di un'approvazione (ADR 0012 §6). Decidere dove
vivono è spostare un confine di sicurezza.

Vincolo posto dall'utente: **la scelta deve reggere quando il Planner arriverà** e produrrà i
piani da solo, senza che il posto degli argomenti cambi di nuovo.

## Decisione

### 1. La motivazione principale: la finestra 7b, e il legame `Approval` → `targets`

Questa è la ragione per cui la decisione è quella che è, non una nota a margine.

ADR 0015 §5 fa riprendere una chiamata interrotta. Sulla **finestra 7b** — il risultato è nello
store, `TOOL_EXECUTED` no — l'executor scrive l'evento mancante con
`targets = targets_of(spec, arguments)` presi **dalla chiamata di retry**, mentre il tool è
girato con gli argomenti della chiamata precedente. Finché gli argomenti erano un parametro,
nulla garantiva che fossero gli stessi: bastava un chiamante distratto perché §32 registrasse
targets che il tool non ha mai visto.

Lo stesso vale un livello più su, ed è più grave. Un'`Approval` è legata ai `targets` della
decisione che l'ha chiesta (ADR 0012 §6, ADR 0011 §10): il «sì» dell'utente è un sì *a quei
target*. Se gli argomenti possono cambiare fra la richiesta e l'esecuzione — fra due chiamate,
dopo un crash, fra un piano e il suo retry — il consenso a scrivere *quella* nota copre la
scrittura di un'altra. `scope_covers` intercetterebbe i casi fuori scope, **non** quelli dentro
lo stesso scope, che sono esattamente quelli che l'approvazione serviva a distinguere.

Quindi la proprietà da garantire è:

> **Gli argomenti sono un fatto del piano approvato, non della chiamata.** Ciò che viene
> autorizzato è ciò che viene eseguito, e un retry esegue ciò che il run ha eseguito.

Solo un posto la garantisce per costruzione invece che per convenzione: il piano stesso, che il
retry rilegge identico.

### 2. `TaskStep.arguments: JsonMapping = {}`

```python
arguments: JsonMapping = _json_payload(
    "The arguments of the capability this step requires (§27; ADR 0018): …"
)
```

Additivo, default `{}` — una capacità senza argomenti non ne ha, e ogni piano già scritto resta
valido. **Nessuna migrazione**: gli step sono già serializzati come colonna JSON di `task_plans`
(`plan_values`, ADR 0006), quindi il campo entra dentro un valore che il database non interpreta,
e una riga scritta prima di M6.3 si rilegge con il default.

**Nessuna validazione contro `input_schema` nel dominio.** ADR 0003 tiene il dominio minimo e la
validazione è del Guardian al momento della decisione (§27): validare due volte metterebbe il
catalogo dentro il dominio e darebbe due punti in cui sbagliare la stessa cosa.

**L'indipendenza dal dispositivo di §13 non è toccata**: gli argomenti non nominano nodi, e la
regola di modello che vieta `DeviceId` nelle annotazioni di `TaskStep` resta verde. Che una
`JsonMapping` possa *contenere* a runtime la stringa di un id è la stessa apertura che
`TaskPlan.metadata` ha già: una questione di dati, non di tipi.

### 3. §13 non elenca gli argomenti, e questo non discrimina fra le alternative

§13 elenca ciò che uno step «può specificare» e gli argomenti non ci sono. Ma §13 non elenca
nemmeno un `ExecutionRequest`, né una chiamata al Planner al momento dell'esecuzione: **nessuna**
delle tre alternative è letteralmente nella spec, quindi «non è in §13» non sceglie fra loro.

Ciò che sceglie è §27, che mette il Planner in cima alla catena:

```
Planner → Capability → Guardian → Authorization → Tool → Device → Audit
```

Qualcuno deve produrre ciò che il Guardian valida contro `input_schema`, e §27 nomina un solo
componente a monte. C'è anche un precedente: ADR 0003 §3 ha letto «dispositivo preferito» di §13
insieme a §17 e l'ha tradotto in `preferred_device_traits`. §13 si legge con i suoi vicini.

### 4. L'executor non prende più gli argomenti, e prende il nodo

`execute(task_id, step_id, *, device_id: DeviceId)`. Il parametro `arguments` **sparisce**: gli
argomenti sono `step.arguments`, letti dal grafo che l'executor già carica. Con un parametro la
proprietà di §1 resterebbe una convenzione del chiamante — un chiamante che passa altro produce
un audit falso e nessun test lo impedisce; senza, è impossibile da esprimere. È la forma che
questo repository preferisce: la garanzia sta nella struttura, non nel docstring (ADR 0017 §6).

Precedente: il parametro `approval` di ADR 0013 §1 è sparito allo stesso modo in ADR 0015 §4.
ADR 0013 e ADR 0015 prendono nello stato il rimando.

`device_id` è keyword-only e **obbligatorio** (ADR 0019 §4): un'esecuzione senza un nodo scelto
non deve essere esprimibile, e un default `None` sarebbe il segnaposto `LOCAL_DEVICE` di prima
sopravvissuto sotto un altro nome.

### 5. Regola di architettura 23: gli argomenti non entrano mai nell'audit

Gli argomenti possono contenere contenuto dell'utente — il corpo di una nota, il testo di un
messaggio — e §57 lo tiene nel database privato: lo tengono il piano e l'`ExecutionResult`;
l'audit registra i **targets** che lo scope vincola e la decisione che li ha permessi. Fino a
M6.3 era una frase nel docstring dell'executor. Ora gli argomenti sono un campo persistito che
tre moduli leggono, e una frase non è una garanzia.

| Regola | Cosa vieta | Esenzioni |
|--------|-----------|-----------|
| 23 `audit-arguments` | il nome `arguments` dentro una costruzione di `AuditEvent` | nessuna |

Riportato, ovunque nel sottoalbero di una chiamata `AuditEvent(...)`: `arguments` come variabile,
come attributo, come keyword o come stringa letterale (una chiave di payload). È una regola sui
nomi, quindi ampia, come le 5, 12, 15, 16 e 20: in un repository dove quella parola ha un
significato solo, il falso positivo costa meno del falso negativo. Il caso negativo è in
`tests/architecture/violations.py`.

### 6. Il limite: argomenti che dipendono dall'output di uno step precedente

Un piano in cui lo step 2 deve operare su ciò che lo step 1 ha prodotto — l'id del file appena
creato, il testo appena letto — non è esprimibile con argomenti statici. §13 non descrive alcun
flusso di dati fra step e nessuna capability di v0.1 ne ha bisogno (`core.echo`,
`workspace.write_note`).

**La strada prevista è additiva dentro `arguments`**: un *valore di riferimento* nella mappa (una
forma tipo `{"path": {"$from": {"step": …, "output": …}}}`) al posto di un valore letterale. Non
uno spostamento degli argomenti altrove: il posto resta questo.

**Con una condizione che non è negoziabile: la risoluzione avviene PRIMA del Guardian.** Il
riferimento va sostituito con il suo valore prima che `authorize` sia chiamato, così che ciò che
viene autorizzato sia ciò che viene eseguito — la proprietà di §1, applicata al caso nuovo. Un
riferimento risolto **dopo** la decisione sarebbe un bypass: il Guardian avrebbe validato uno
schema e calcolato dei `targets` su un segnaposto, e il tool riceverebbe un valore che nessuna
decisione ha visto. Sarebbe esattamente il buco che questo ADR chiude, riaperto da dentro.

Fuori scope da M6.3, assegnato alla milestone che porterà la prima capability che ne ha bisogno.

## Alternative considerate

- **B. Un `ExecutionRequest` separato** — scartata perché **non è una terza risposta**. Gli
  argomenti dovrebbero comunque arrivare da qualche parte: da un campo dello step (allora A basta
  e B è un'indirezione), o da un componente che non esiste (allora B ha i problemi di C, più
  un'entità, un port, una tabella, un mapper e una migrazione). E duplicherebbe `ExecutionResult`,
  che già lega uno step a `task_id`, `step_id`, `capability_id`, `decision_id` e
  `authorization_id`, per aggiungere un solo campo.
- **C. Argomenti prodotti dal Planner al momento dell'esecuzione** — scartata per tre ragioni,
  in ordine di peso: (1) **rompe la proprietà di §1** — due chiamate al modello possono dare due
  argomenti diversi, quindi la finestra 7b scriverebbe nell'audit targets che il tool non ha
  visto e un'approvazione coprirebbe un'azione diversa da quella per cui è stata data;
  (2) richiederebbe **oggi** un segnaposto per un Planner che non esiste, vietato da CLAUDE.md;
  (3) l'audit di §32 perderebbe la possibilità di dire con quali argomenti un tool è stato
  chiamato, se non ricostruendolo dal risultato.
- **Validare gli argomenti contro `input_schema` nel dominio** — scartata: ADR 0003 tiene il
  dominio minimo, e la validazione con il suo audit è del Guardian (§27, ADR 0011).
- **Tenere il parametro `arguments` su `execute` e passargli `step.arguments`** — scartata: la
  proprietà di §1 resterebbe una convenzione di chi chiama, e questo ADR esiste per non doversi
  fidare di chi chiama.

## Conseguenze

- Un retry esegue con gli argomenti del run, per costruzione: la finestra 7b di ADR 0015 §8
  scrive i `targets` che il tool ha davvero visto, e nessuna riga di quella tabella cambia.
- Un'`Approval` copre l'azione per cui è stata data, anche attraverso un crash: i `targets` della
  decisione nascono da argomenti che non possono cambiare sotto di essa.
- `ela.domain` perde un modello dalla lista di quelli senza payload JSON: `TaskStep` ne ha uno, e
  come ogni payload è congelato (`tests/domain/test_immutability.py`). Un piano modificabile in
  posto dopo che il Guardian lo ha letto sarebbe un piano su cui nessuno ha deciso.
- Nessuna migrazione, nessuna tabella nuova, nessun port nuovo.
- La regola 23 rende l'invariante di §57 verificabile invece che ricordata.
- I test costruiscono piani completi: `tests/permissions/support.ARGUMENTS` dà a ogni capability
  del catalogo gli argomenti che la soddisfano, così nessun test inventa un payload suo.
- ADR 0003 (il campo), ADR 0013 e ADR 0015 (la firma di `execute`) prendono nello stato il
  rimando a questo documento.
