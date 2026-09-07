# 0020. Provider Anthropic: stato dichiarato, chiave solo da ELA, retry proprio, costo stimato, vocabolario chiuso degli errori

- **Stato:** Accettata
- **Data:** 2026-09-07
- **Riferimenti spec:** §25, §26, §29, §32, §33, §50, §51, §57, §64

## Contesto

`ModelProvider` e `ProviderRegistry` esistono come port da ADR 0005, e fino a M7.0 il solo
implementatore è `FakeModelProvider`, che risponde con una stringa. §26 e §50 chiedono che il Core
parli con un'astrazione e che un provider vero stia dietro di essa; §25 chiede che un giorno si
possa scegliere il modello per qualità, costo, latenza e **disponibilità**.

Costruire il primo provider vero apre quattro domande che il fake non aveva mai posto:

1. **Che cosa fa ELA quando la chiave non c'è?** Un `KeyError` all'avvio renderebbe la mancanza di
   una credenziale un guasto del sistema, non un fatto del sistema.
2. **Chi decide che una chiamata va ritentata?** L'SDK ha già una politica; ELA ne vuole una che
   sia sua e verificabile.
3. **Che cosa esce da questa macchina?** È il primo modulo di ELA che manda contenuto dell'utente
   fuori (§57): serve un confine dichiarato, non una buona abitudine.
4. **Che cosa vede chi riceve un fallimento?** Se per capire che la chiave è sbagliata bisogna
   riconoscere una classe dell'SDK, il Core dipende dal provider e §26 è violata nei fatti.

## Decisione

### 1. Un adapter, un package, un solo import

`ela.providers.registry.ProviderRegistry` implementa il registro; `ela.providers.anthropic/` è
l'adapter ed è **l'unico posto in cui `import anthropic` compare** (regola di architettura 24 e
contratto import-linter 10, §11 di questo ADR). Importare `ela.providers` non importa nessun SDK:
l'adapter si prende con `from ela.providers.anthropic import anthropic_provider`.

### 2. Lo stato del provider è un dato del dominio

`ProviderStatus` (`AVAILABLE` / `UNAVAILABLE`) entra nel dominio e `status` entra in
`ModelProvider`. Senza chiave il provider **si costruisce, si registra** e dichiara `UNAVAILABLE`;
`complete` risponde con `provider.unavailable` **senza toccare la rete**. ELA parte su una macchina
senza chiave, e la mancanza è leggibile senza fare una chiamata — che è ciò che servirà al Model
Router di §25, dove «disponibilità» è uno dei criteri di scelta.

Lo stato è **statico in v0.1**: deriva dalla presenza della chiave, una volta, alla costruzione. Un
401 a runtime **non** lo cambia. Uno stato mutabile sarebbe una cache di un fatto remoto, e una
cache vuole una politica di invalidamento che nessuna sezione della spec detta oggi. Perché la cosa
resti azionabile, un 401 o un 403 sono un errore **nominato**
(`provider.authentication_error`, §7) e mai ritentabile: chi vorrà marcare il provider inutilizzabile
— il tool di M7.2, il router — lo farà da quel codice, senza rileggere l'SDK.

Nessun `UNKNOWN`: un provider che non sa dire di essere utilizzabile non è utilizzabile (§33).

### 3. La chiave arriva da `ELA_ANTHROPIC_API_KEY`, e da nient'altro

`AnthropicSettings` (pydantic-settings, prefisso `ELA_`, ADR 0001) tiene cinque variabili:

| Variabile | Tipo | Default | Perché |
|---|---|---|---|
| `ELA_ANTHROPIC_API_KEY` | `SecretStr \| None` | assente | assente ⇒ `UNAVAILABLE`; vuota o di soli spazi vale assente (§33) |
| `ELA_ANTHROPIC_MODEL` | `str` fra i modelli noti | `claude-sonnet-5` | il default è il profilo *balanced* (§4) |
| `ELA_ANTHROPIC_TIMEOUT_SECONDS` | `float` in `(0, 600]` | `60` | l'SDK aspetta dieci minuti: troppo per un assistente |
| `ELA_ANTHROPIC_MAX_RETRIES` | `int` in `[0, 10]` | `2` | quanti ritentativi, non quante chiamate |
| `ELA_ANTHROPIC_MAX_OUTPUT_TOKENS` | `int > 0`, ≤ max del modello | `4096` | budget di output di chi non ne chiede uno |

Il client SDK è costruito **solo** se la chiave c'è, e sempre con `api_key=` esplicito. La ragione
non è di stile: l'SDK, senza `api_key`, cerca da sé `ANTHROPIC_API_KEY`, poi `ANTHROPIC_AUTH_TOKEN`,
poi un profilo OAuth scritto su disco da `ant auth login`, poi la federazione di identità. Su una
macchina di sviluppo almeno una di queste c'è quasi sempre, e ELA finirebbe per spendere credenziali
che non le sono state date. `SecretStr` perché un `repr` di un oggetto di configurazione è la via
più corta perché una chiave finisca in un log.

### 4. I modelli di v0.1

Dalla documentazione ufficiale (letta il 2026-09-07):

| Modello | ID | Contesto | Max output | $/MTok input | $/MTok output | `effort` |
|---|---|---|---|---|---|---|
| Claude Opus 5 | `claude-opus-5` | 1M | 128000 | 5 | 25 | sì |
| Claude Sonnet 5 | `claude-sonnet-5` | 1M | 128000 | 2 | 10 | sì |
| Claude Haiku 4.5 | `claude-haiku-4-5` | 200K | 64000 | 1 | 5 | no |

`claude-fable-5-1` resta fuori: costa il doppio di un Opus e richiede una configurazione di
retention a 30 giorni sull'organizzazione, e nessun profilo di §25 lo chiede.

**Il default è `claude-sonnet-5`, non il modello più potente.** §25 assegna il modello caro a
pianificazione, coding e reasoning: sono scelte, e arriveranno come hint espliciti da chi instrada.
Il default è ciò che parte quando nessuno ha pensato al costo, e deve essere il profilo *balanced*.

### 5. `model_hint` è un profilo; i `parameters` sono una allowlist chiusa

`ProviderRequest.model_hint` non è un id di modello — il dominio non conosce i nomi di un vendor —
ma un profilo, e la traduzione è dell'adapter:

| `model_hint` | Modello |
|---|---|
| assente | `ELA_ANTHROPIC_MODEL` |
| `quality`, `reasoning`, `planning`, `coding`, `analysis` | `claude-opus-5` |
| `balanced` | `claude-sonnet-5` |
| `fast`, `cheap`, `classification`, `extraction`, `routine` | `claude-haiku-4-5` |
| un id della tabella §4 | sé stesso |
| qualunque altra cosa | `provider.unknown_model_hint`, **nessuna chiamata** |

`ProviderRequest.parameters` accetta due chiavi e nessun'altra: `max_output_tokens` (intero
positivo, non oltre il massimo del modello) ed `effort` (`low`…`max`, solo su un modello che lo
supporta). Tutto il resto è `provider.unsupported_parameter` **prima** della rete, con il **nome**
della chiave nel messaggio e mai il valore.

Il caso che decide la questione è `temperature`: è rimosso da tutti i modelli correnti e mandarlo è
un 400 garantito. Passarlo così com'è significherebbe pagare un round-trip — e far attraversare la
rete al testo dell'utente — per scoprire una cosa già nota (§57); ignorarlo in silenzio significa
rispondere con impostazioni diverse da quelle chieste, senza traccia (§33).

Il corpo mandato è esattamente: `model`, `max_tokens`, un messaggio utente con `input`, `system`
se ci sono `instructions`, `output_config.effort` se richiesto. Niente `thinking` (adattivo è ciò
che si ottiene omettendolo), niente campionamento, niente streaming, tool, cache o beta.

### 6. Il costo è una **stima**, in `Decimal`, e `None` quando non si sa

`cost = (input×p_in + output×p_out + cached×p_cache) / 1e6`, in USD, arrotondato a otto decimali,
sui prezzi della tabella §4 (`cache_read` = 10% dell'input su tutti e tre). Il prezzo si sceglie sul
modello che **ha davvero servito** la risposta, non su quello richiesto.

Un modello che la tabella non conosce dà `cost = None` e `currency = None`. Mai `0`: zero è un
numero e verrebbe sommato in un totale come se la chiamata fosse gratis; `None` dice «non lo so».
Zero token su un modello noto costano invece `0`, ed è vero.

La tabella è datata: quando i prezzi cambiano, cambia qui, e `tests/docs/test_adr_provider.py`
fallisce se il codice e questo ADR si separano. La fonte di verità della spesa reale resta la
Console.

### 7. Il vocabolario degli errori sta nel port, non nell'adapter

`ela.ports` dichiara dodici codici (`PROVIDER_ERROR_CODES`) ed è lì che stanno, non dentro
`ela.providers`, per la ragione per cui §26 esiste: chi riceve un fallimento deve poter distinguere
una credenziale rifiutata da un sovraccarico **senza importare — né conoscere — il provider che
l'ha prodotto**. Un secondo provider riporta gli stessi dodici codici o non è intercambiabile con
il primo.

| Eccezione SDK | HTTP | Codice | `retryable` |
|---|---|---|---|
| — (nessuna chiave) | — | `provider.unavailable` | no |
| — (hint sconosciuto) | — | `provider.unknown_model_hint` | no |
| — (parametro non ammesso) | — | `provider.unsupported_parameter` | no |
| `APITimeoutError` | — | `provider.timeout` | **sì** |
| `APIConnectionError` | — | `provider.unreachable` | **sì** |
| `RateLimitError` | 429 | `provider.rate_limited` | **sì** |
| `InternalServerError` | ≥500 (incl. 529, 504) | `provider.server_error` | **sì** |
| `AuthenticationError`, `PermissionDeniedError` | 401, 403 | `provider.authentication_error` | no |
| `BadRequestError` | 400 | `provider.bad_request` | no |
| `NotFoundError` | 404 | `provider.unknown_model` | no |
| altro `APIStatusError` 4xx, `APIResponseValidationError` | 4xx / — | `provider.rejected` | no |
| `stop_reason == "refusal"` | 200 | `provider.refusal` | no |

Il rifiuto del modello ha un codice **proprio** e non è un guasto: è informazione che il Memory
Core (§64) vorrà distinguere da un errore di sistema, e costa token come una risposta.

`retryable` descrive la **natura** del fallimento, non i tentativi rimasti: l'ultimo tentativo di un
500 riporta comunque `retryable=True`.

### 8. Il retry è di ELA, non dell'SDK

Il client è costruito con `max_retries=0` e la politica sta in `AnthropicProvider`:

- tentativi = `1 + ELA_ANTHROPIC_MAX_RETRIES`;
- si ritenta **solo** ciò che la tabella §7 marca ritentabile: 429, ≥500, connessione, timeout;
- attesa esponenziale deterministica `0.5 × 2ⁿ` secondi, con tetto **8 s**; se la risposta porta
  `retry-after` numerico vince quello, con lo stesso tetto; un `retry-after` in formato data non si
  interpreta e lascia il backoff al suo posto;
- nessun jitter: il jitter scaglia una folla di client, ELA è un client solo, e un'attesa
  prevedibile è un'attesa dimostrabile.

Perché non delegare all'SDK, che pure ritenta 429 e 5xx con backoff: (a) il retry dell'SDK vive
dentro il client, e nei test il client è un doppio — la regola «5xx e 429 sì, 4xx mai» non avrebbe
**nessun** test, e CLAUDE.md chiede che tutto ciò che gira in `make check` abbia il suo test;
(b) con due politiche sovrapposte il tempo massimo di una `complete` diventa `timeout × 3 × 3`;
(c) l'SDK ritenta il 409, ELA no — «mai su 4xx» è la regola scelta.

### 9. Gli otto esiti di `complete`, tutti risultati

| # | Situazione | Rete | `error.code` | `usage` |
|---|---|---|---|---|
| 1 | nessuna chiave | no | `provider.unavailable` | zero, `cost` assente, `model = ""` |
| 2 | hint sconosciuto | no | `provider.unknown_model_hint` | zero, `model = ""` |
| 3 | parametro non ammesso | no | `provider.unsupported_parameter` | zero, modello risolto |
| 4 | fallimento di trasporto | sì | `provider.timeout` / `provider.unreachable` | zero token, latenza reale |
| 5 | 429 o 5xx esauriti i tentativi | sì | `provider.rate_limited` / `provider.server_error` | zero token, latenza di tutti i tentativi |
| 6 | 4xx | sì | `provider.authentication_error` / `bad_request` / `unknown_model` / `rejected` | zero token |
| 7 | rifiuto del modello | sì | `provider.refusal` | **token reali** |
| 8 | risposta | sì | nessuno | token, costo, valuta, latenza |

In nessuno degli otto `complete` solleva un'eccezione. La latenza è misurata su un orologio
**monotono** e copre tutti i tentativi: `Clock.now()` è wall-clock e può tornare indietro
(ADR 0003 §4), e una durata negativa sarebbe un dato falso.

### 10. Che cosa non esce

L'input e le `instructions` vanno nel corpo della richiesta e in nessun altro posto: né in un
messaggio d'errore, né in `details`, né in `metadata`, né in un log. Di un fallimento ELA conserva
uno status code, il **tipo** di errore dell'API (vocabolario chiuso: `invalid_request_error`,
`rate_limit_error`, …), il `request-id` e il numero di tentativi — mai il testo libero del server,
che descrive la richiesta mandata. È la convenzione che i tool seguono già (ADR 0013 §7): un codice,
un nome di tipo, uno stato; mai contenuto.

Di un rifiuto si tiene la **categoria** (`cyber`, `bio`, …), che parla del genere di richiesta, e
non la `explanation`, che parla di *questa* richiesta.

### 11. Regola di architettura 24 e contratto import-linter 10

`anthropic` è importabile **solo** da `ela.providers.anthropic`. La regola 24
(`anthropic-import-isolation`) la verifica a mondo chiuso su tutto l'albero dei sorgenti; il
contratto 10 la verifica in `make lint`. Senza di esse «un solo modulo importa l'SDK» sarebbe una
frase in un README: il contratto 3 permette a *tutto* `ela.providers`, `ela.infrastructure` e
`ela.api` di importarlo.

`ela.providers` entra in `CRITICAL_PACKAGES` (100% branch coverage): è il confine da cui il
contenuto dell'utente esce da questa macchina (§57) e il posto dove si decide se un errore si
ritenta — le stesse ragioni per cui ci sono già `ela.tools` e `ela.devices`.

## Port

Port rinominati:

| Port | Perché | Modo | Membri |
|---|---|---|---|
| `ProviderRegistryPort` | rinomina `ProviderRegistry` (§50): era l'unica registry senza suffisso, e il nome nudo serve all'implementazione | sync | `register`, `get`, `names` |

Port estesi:

| Port | Riferimento | Modo | Membri aggiunti |
|---|---|---|---|
| `ModelProvider` | §25, §26 | async | `status` |

## Alternative considerate

- **Stato solo sulla classe concreta** (nessun cambio di port). Chi legge il registro vede
  `ModelProvider` e dovrebbe fare `isinstance` su una classe concreta per sapere se è utilizzabile:
  è la dipendenza dal provider che §26 vieta.
- **Non registrare il provider senza chiave.** Un registro vuoto non distingue «provider assente»
  da «provider senza credenziali», e la seconda è un'informazione che serve all'utente.
- **Retry dell'SDK** (§8, motivi a–c).
- **`model_hint` passato all'API così com'è.** Un hint sconosciuto diventerebbe un 404 pagato con
  un round-trip, e il campo indipendente dal provider si riempirebbe di stringhe Anthropic.
- **Parametri in pass-through o ignorati in silenzio** (§5).
- **Nessun costo, oppure prezzi da configurazione.** Il primo non soddisfa §32; il secondo aggiunge
  variabili d'ambiente che nessuno terrà aggiornate meglio di una tabella datata con un test.
- **Codici d'errore dentro l'adapter.** Renderebbero il riconoscimento di un fallimento un fatto
  del vendor (§7).

## Conseguenze

- ELA sa chiamare un modello. **Non** sa ancora farlo come conseguenza di una decisione del
  Guardian: il tool e il verifier di `model.complete` sono M7.2, e `ela.tools.registry` lo dice.
- Il dominio ha un enum in più (`ProviderStatus`) e il port `ModelProvider` un membro in più.
  `FakeModelProvider` li segue, e i contract test valgono su tre implementazioni: il fake,
  l'adapter senza chiave e l'adapter su un doppio.
- L'intera suite non può usare la rete: `tests/conftest.py` rende inutilizzabili i transport HTTP,
  e `tests/security/test_no_network.py` lo dimostra con un client vero.
- `anthropic` diventa una dipendenza di progetto. Il Core non la vede: contratti 1, 2, 3, 6, 8 e il
  nuovo 10 lo tengono fermo.

### Vincoli dichiarati, da riaprire quando serviranno

- **Lo stato non cambia a runtime** (§2). Quando il Model Router dovrà escludere un provider che ha
  appena risposto 401, servirà una politica di invalidamento: è una decisione, non un dettaglio.
- **Nessuna conversazione**: `ProviderRequest` è un testo singolo, e il multi-turno non esiste.
  Quando servirà, è un campo additivo sul dominio e un ADR.
- **Nessuno streaming**: con `max_tokens` nell'ordine delle migliaia non serve. Un output da 128K lo
  richiederà, e cambia la forma del port (`complete` restituisce un risultato, non un flusso).
- **I prezzi invecchiano** (§6). La tabella è datata e testata contro il codice, non contro il
  mondo: nessun test si accorge che Anthropic ha cambiato listino.
- **Nessun prompt caching**: `cached_input_tokens` viene letto e valorizzato se l'API lo riporta, ma
  ELA non chiede mai una cache. Chiederla è una decisione di costo, con il suo ADR.
