# 0021. Protocollo STARTED, `ProviderUsage` fino all'audit, `Outcome.retryable`, tool e verifier di `model.complete`, regola 25

- **Stato:** Accettata
- **Data:** 2026-09-07
- **Riferimenti spec:** §26, §27, §28, §29, §32, §33, §57, §62, §63, §64
- **Milestone:** M7.2 (decisioni dell'utente del 2026-09-07: **1a**, **2a**, **8a**, **9a**,
  **10b** ridotta alla sola condizione `model.answered`)

## Contesto

`model.complete` è nel catalogo da M4.1 e il provider Anthropic esiste da M7.1, ma la capability
non è eseguibile: `ela.tools.registry` dichiara «`model.complete` has no tool yet (M7.2)» e
l'executor solleva `ToolNotFound` prima di qualunque decisione. Scrivere quel tool apre quattro
questioni che i due tool esistenti non avevano mai posto.

1. **Un tool che non si può rifare.** ADR 0015 §8 ha lasciato aperta la finestra di crash 7a —
   l'istante fra l'effetto del tool e l'`INSERT` del suo risultato — con una riparazione sola:
   «il tool riesegue». Regge finché due volte è come una. Per una chiamata a un modello non lo è:
   si paga due volte, il contenuto dell'utente esce due volte (§57), e la seconda risposta non è
   la prima. ADR 0015 §8 aveva già iscritto il debito a questa milestone: «È l'ADR di quel tool
   (M7.2 `model.complete`, o il primo con un costo non ripetibile) a portarlo».
2. **Il costo di una chiamata non arriva da nessuna parte.** §32 chiede che l'audit log tenga
   «provider usage metadata», e `AuditEvent.usage` esiste dal dominio di M1.1 — **mai
   valorizzato**, perché l'executor vede solo un `ExecutionResult` e un `ExecutionResult` non
   porta un usage.
3. **La natura di un fallimento si perde.** `Tool.execute` costruiva l'`ErrorMetadata` con
   `retryable=False` sempre. Un `provider.rate_limited` — che ADR 0020 §7 ha appena definito
   ritentabile — sarebbe arrivato nell'audit come definitivo.
4. **Da dove esce il contenuto dell'utente.** È il primo tool che manda qualcosa fuori da questa
   macchina, e la garanzia che lo faccia solo dietro una decisione del Guardian non è una
   proprietà di `ModelProvider.complete`, che risponderebbe a chiunque.

## Decisione

### 1. Il protocollo STARTED: una riga prima dell'azione

`ExecutionStatus` guadagna **`STARTED`**, l'unico valore che non descrive una fine. `ToolPort`
guadagna **`idempotent`**: era già su `ela.tools.base.Tool` e letto da un `getattr` dentro
`ToolRegistry`, ma è l'executor a doverne decidere, e ciò che l'executor legge sta nel port.

Per un tool che dichiara `idempotent = False`, l'executor — dopo la decisione, dopo il `consume`,
**prima** della chiamata — scrive un `ExecutionResult` con stato `STARTED` che porta tutto ciò
che porterà l'esito tranne l'esito: quale decisione, quale grant, quale nodo. Nessun evento di
audit: non è ancora successo niente, e `TOOL_EXECUTED` si scrive all'esito.

L'esito è una **seconda riga, con un id proprio**, che nomina la prima in
`metadata["started_id"]`. Lo store resta *insert-only* — «a result is a fact» — e non guadagna
nessuna operazione: due righe raccontano due fatti diversi («stavo per agire», «ecco com'è
andata»), e riscriverne una sola avrebbe reso mutabile la cosa che ADR 0015 §1 ha reso immutabile
apposta. `for_step` restituisce quindi al più due righe per uno step, e il suo contratto lo dice.

Un tool idempotente non produce nessuna STARTED: la sua riparazione resta quella di ADR 0015 §8,
rifarlo.

### 2. Il retry non richiama il tool: `execution.interrupted`

Un `execute` che trova una STARTED **senza esito** non chiama il tool. Non ne inventa nemmeno
l'esito: una seconda riga che dicesse FAILED affermerebbe che il tool è girato ed è fallito,
mentre l'unica cosa nota è che stava per girare. Quindi la STARTED resta com'è, `TOOL_EXECUTED`
la nomina con `execution.interrupted` e un payload il cui `status` è `STARTED`, e lo step è
FAILED con lo stesso errore. Il task resta EXECUTING: il fallimento di un tool è una domanda per
chi orchestra (ADR 0013 §5).

`retryable=True`: ciò che è fallito è il crash, non la richiesta, e uno step FAILED non riparte
comunque — «un retry di uno step fallito è uno step nuovo» (ADR 0009). Il flag descrive la natura
del fallimento, non un permesso a rieseguire questo step.

Il ramo che ADR 0015 §8 immaginava prima dell'«altrimenti» — «verifica se il tool ha lasciato un
effetto verificabile» — **non è implementato, ed è una scelta**: un verifier rifiuta per contratto
un risultato che non è SUCCEEDED (`verification.not_succeeded`, ADR 0014 §3), e una completion non
lascia comunque nulla da guardare su questa macchina. Il giorno in cui un tool non idempotente
lascerà un effetto ispezionabile, quel ramo sarà il suo ADR.

L'audit dell'interruzione è protetto come quello di un resume: un crash fra l'evento e
`fail_step` riporta la chiamata qui, e l'evento si scrive una volta sola.

### 3. `ProviderUsage` da `Outcome` all'audit

`Outcome` guadagna `usage`, `ExecutionResult` guadagna `usage` (colonna `execution_results.usage`,
migrazione `0006`, JSON nullable), e l'executor lo copia in `AuditEvent.usage` del
`TOOL_EXECUTED`. È l'unico posto dove ELA scrive quel campo.

`None` non è `0`: un tool che non chiama nessun provider non ha un usage, una chiamata da zero
token è costata zero. La distinzione è la stessa che ADR 0020 §6 fa per il costo di un modello
sconosciuto, e per la stessa ragione — un `None` sommato in un totale si nota, uno zero no.

L'usage viaggia **su tutti e due i rami**, riuscito e fallito: una chiamata fallita è costata
comunque latenza, e un rifiuto del modello è costato token (ADR 0020 §9, esito 7). Un audit che
registrasse il costo solo delle chiamate riuscite sotto-riporterebbe esattamente quelle su cui
vale la pena indagare.

### 4. `Outcome.retryable`

`Outcome` guadagna `retryable: bool = False`, e `Tool.execute` lo riporta nell'`ErrorMetadata`.
Il default è `False` perché un dubbio non è un sì (§33); il tool di `model.complete` ci mette il
`retryable` che il provider ha dichiarato, così che i tredici codici di ADR 0020 §7 arrivino
nell'audit con la natura che avevano — che è la distinzione che il Memory Core (§64) dovrà fare
fra «riprova più tardi» e «così non funzionerà mai».

### 5. Il tool, e la regola 25

`ela.tools.model.ModelCompleteTool` tiene **un** `ModelProvider` come dato, come tiene un clock.
Valida di nuovo i suoi argomenti (§28), costruisce la `ProviderRequest`, chiama, e traduce il
`ProviderResult` in un `Outcome`. **Non sceglie niente**: quale modello risponde lo decide il
`model_hint` degli argomenti o, in sua assenza, il default del provider (ADR 0020 §5). Scegliere
è del Model Router (§25), che è M7.3.

Un `ProviderResult` senza errore e **senza testo** è `provider.no_output` — non uno dei tredici
codici di ADR 0020 §7, che descrivono un fallimento *riportato dal provider*, ma un risultato
inutilizzabile: una risposta vuota che si dichiara riuscita arriverebbe al verifier come un
successo senza niente dentro, e lo step fallirebbe uno strato più in là con meno da dire.

**Regola di architettura 25** (`provider-complete-callers`): fuori da `ela/tools/model.py` nessun
modulo di `src/ela` chiama `.complete(` su un ricevente. La garanzia «il contenuto dell'utente
esce solo dietro una decisione del Guardian» non è una proprietà della chiamata — un provider
risponde a chiunque — ma dell'unico modulo che la fa, un `Tool` la cui classe base controlla la
decisione per prima. È l'argomento della regola 16 per `Tool.execute`. Un'esenzione, per
ricevente e non per modulo: `self._engine.complete(...)` è il Task Engine che chiude un task
(ADR 0008), omonimo e nient'altro.

### 6. Il verifier verifica ciò che la corsa ha lasciato

`ModelCompleteVerifier`, una condizione: **`model.answered`** — il risultato porta un testo, il
provider e il modello che l'hanno prodotto, e la `ProviderUsage` della chiamata.

Non può verificare che la risposta sia *giusta*: niente in v0.1 può, ed è scritto invece che
sottinteso. Non può nemmeno richiedere: guardare il mondo, qui, vorrebbe dire richiamare il
modello — un secondo addebito e il contenuto dell'utente in rete una seconda volta (§57). Ciò che
può rifiutare è un successo di cui nessuno sa rendere conto (`model.unaccounted`), che è la
domanda di §32. La seconda condizione della decisione 10b, `model.routed_as_asked`, arriva con il
router in M7.3: senza una rotta non c'è niente da confrontare.

### 7. Che cosa non esce

L'`input`, le `instructions` e il testo della risposta stanno nell'`ExecutionResult` — quindi nel
database privato — e in nessun `AuditEvent` (§57, regola 23). Il verifier riporta che *manca*
qualcosa, mai che cosa c'era. Vale il confine che ADR 0020 §10 ha già posto per l'adapter, un
livello più su.

### 8. Port estesi

Port estesi:

| Port | Riferimento | Modo | Membri aggiunti |
|---|---|---|---|
| `ToolPort` | §28, §63 | async | `idempotent` |

Il modo è quello del port, non del membro aggiunto: `idempotent` è una proprietà, come `status`
lo era per `ModelProvider` (ADR 0020).

### 9. Tool aggiunti

Tool aggiunti:

| Capability | Tool | Nome | Output | Codici di errore |
|---|---|---|---|---|
| `model.complete` | `ModelCompleteTool` | `model-complete` | `output`, `provider`, `model`, `finish_reason` | `arguments.invalid`, `provider.no_output`, `provider.unavailable`, `provider.unknown_model_hint`, `provider.unsupported_parameter`, `provider.authentication_error`, `provider.bad_request`, `provider.unknown_model`, `provider.rejected`, `provider.malformed_response`, `provider.rate_limited`, `provider.server_error`, `provider.unreachable`, `provider.timeout`, `provider.refusal` |

### 10. Verifier aggiunti

Verifier aggiunti:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `model.complete` | `ModelCompleteVerifier` | `model-complete-verifier` | `model.answered` | comuni, `model.no_answer`, `model.unaccounted` |

### 11. Colonne aggiunte

Colonne aggiunte:

| Tabella | Colonne |
|---|---|
| `execution_results` | `usage` |

`ExecutionStatus.STARTED` non ha bisogno di migrazione: `status` è una `String(32)` senza vincolo,
e il vocabolario della colonna vive nell'enum del dominio, non nello schema.

### 12. Gli esiti di `execute` per un tool non idempotente

| # | Situazione | Righe nello store | Audit | Step |
|---|---|---|---|---|
| 1 | corsa normale | STARTED, poi l'esito | `TOOL_EXECUTED` sull'esito | COMPLETED o FAILED |
| 2 | crash fra la STARTED e l'esito | solo la STARTED | `TOOL_EXECUTED` con `execution.interrupted` | FAILED |
| 3 | crash fra l'esito e `TOOL_EXECUTED` | STARTED e esito | scritto al retry con `recovered` | come 1 |
| 4 | crash fra `TOOL_EXECUTED` e `fail_step` (caso 2) | solo la STARTED | già scritto, non riscritto | FAILED al retry |
| 5 | crash fra il `consume` e la STARTED | nessuna | nessuno | il grant è speso, nessun effetto: finestra 6 di ADR 0015 §8, invariata |

## Alternative considerate

- **`model.complete` dichiarato idempotente.** Nulla è scritto su questa macchina, quindi «il
  mondo» sarebbe lo stesso. Ma una chiamata si paga, esce (§57) e risponde altro: sarebbe far
  passare per ripetibile una cosa che non lo è, nel punto esatto in cui ADR 0015 §8 aveva detto
  il contrario. Scartata (decisione 1a).
- **Una riga sola, «chiusa» da una nuova operazione dello store** (o riusata con un `UPDATE`).
  Lo store smetterebbe di essere insert-only, e con esso l'invariante che rende un risultato un
  fatto. Scartata (decisione 2a).
- **L'usage dentro `ExecutionResult.metadata`.** Nessuna migrazione, ma il campo tipizzato
  `AuditEvent.usage` resterebbe vuoto per sempre, `Decimal` e `None` diventerebbero stringhe
  senza schema, e «quanto è costato» smetterebbe di essere una domanda che si può fare al
  dominio. Scartata (decisione 8a).
- **Lasciare `retryable=False` per tutti.** Il codice arriverebbe nell'audit, la natura del
  fallimento no. Scartata (decisione 9a).
- **Un verifier che richiama il modello per confrontare.** Un secondo addebito e il contenuto
  dell'utente in rete due volte, per confrontare due risposte che non devono essere uguali.
  Scartata.
- **Nessuna regola 25.** «Un solo modulo manda fuori il contenuto dell'utente» sarebbe una frase
  in un docstring: il contratto 3 permette a mezzo albero di importare un provider.

## Conseguenze

- La **finestra 7a di ADR 0015 §8** passa da «non riparabile per costruzione» a «riparata per i
  tool non idempotenti»: non nel senso che l'esito si recupera — non si recupera — ma nel senso
  che non si paga due volta e non si manda fuori due volte. Per i tool idempotenti la
  riparazione resta quella di prima.
- `ToolRegistry` **accetta un `False` dichiarato** e continua a rifiutare il silenzio: quello che
  era «solo `True`» diventa «un booleano, dichiarato».
- Il dominio ha un valore di enum in più, un campo in più su `ExecutionResult`, e una migrazione.
  `TaskRunner` scarta le righe STARTED prima di contare i risultati di uno step: un record di
  un'intenzione non chiude un task.
- ELA sa chiamare un modello sotto il Guardian. **Non** sa ancora scegliere quale: il Model Router
  di §25 è M7.3, e fino ad allora `model_hint` o il default del provider.

### Vincoli dichiarati, da riaprire quando serviranno

- **L'esito di una corsa interrotta resta ignoto** (§2). ELA sa che il tool stava per agire e non
  sa se ha agito; se ha agito, quei token sono stati spesi e non compaiono in nessun usage. È il
  limite di due sistemi che non condividono una transazione, ridotto a un istante e dichiarato.
- **Nessun ramo «verifica invece di rifare»** (§2): quando esisterà un tool non idempotente con un
  effetto ispezionabile, servirà, e il contratto del verifier dovrà accettare un risultato che non
  è SUCCEEDED.
- **`model.answered` è tutto ciò che si verifica** (§6): che la risposta serva a qualcosa non lo
  dice nessuno. `model.routed_as_asked` in M7.3; una valutazione della qualità è §64, non §63.
- **Nessun budget** (§3): l'usage si registra, non si somma e non si confronta con un tetto.
  Un tetto di spesa è §30 e il suo ADR.
