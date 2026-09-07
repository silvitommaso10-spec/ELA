# 0022. Model Router: tabella di rotte, fallback sulla disponibilità, `task_type` come argomento

- **Stato:** Accettata.
- **Data:** 2026-09-07
- **Riferimenti spec:** §25, §26, §29, §32, §33, §57
- **Milestone:** M7.3 (decisioni dell'utente del 2026-09-07: **3a**, **4a**, **5a**, **6a**,
  **7b**, **11a**, **12a**, più le quattro risposte alla SPEC: provider nominati in codice,
  «piccoli task» = `routine`, provider assente rifiutato in costruzione, contratto 11)

## Contesto

Dopo M7.2 ELA chiama un modello dietro una decisione del Guardian, ma **quale** modello lo decide
il `model_hint` scritto a mano negli argomenti, o il default del provider (ADR 0021 §5). §25
chiede altro: «Il Model Router decide quale modello utilizzare in base a: tipo di task; qualità
necessaria; latenza; costo; privacy; capacità; disponibilità», e dà due liste — un modello potente
per pianificazione, coding, reasoning e analisi; uno economico per classificazione, estrazione,
piccoli task e routine.

Scrivere quella politica apre cinque domande che il `model_hint` non poneva:

1. **Su che cosa si instrada?** Un campo nuovo, o la rilettura di uno che c'è già.
2. **Su che cosa si mappa?** Un id di modello — che il Core non può conoscere (§26) — o un
   profilo.
3. **Chi vince fra la politica e chi ha scritto un hint?**
4. **Che cosa succede quando il provider scelto non è utilizzabile?** E *quando* lo si scopre:
   prima di chiamare, o dopo aver mandato fuori il contenuto dell'utente (§57)?
5. **Che cosa succede con un `task_type` che la tabella non conosce?**

Dei sette criteri di §25 questa versione ne usa **due**: tipo di task e disponibilità. Gli altri
cinque chiedono un secondo provider da confrontare e misure che oggi non esistono (§10).

## Decisione

### 1. Un package del Core, e la decisione è un dato del dominio

`ela.routing` (`policy.py`, `router.py`, `settings.py`) tiene la politica; `ModelRouterPort` sta
in `ela.ports`; `FakeModelRouter` in `ela.testing`. `ela.routing` entra nel contratto
import-linter 4 — non importa `ela.providers` né `ela.infrastructure` — e nei
`CRITICAL_PACKAGES`: è il modulo che decide **dove va** il contenuto dell'utente.

Il router raggiunge i provider fra cui sceglie attraverso `ProviderRegistryPort`, e ciò che
restituisce è `ela.domain.ModelRoute`: `task_type`, `provider` (il **nome** nel registro),
`profile`, `skipped`. È la forma che ha già la decisione del Guardian — il Guardian decide,
`PermissionDecision` è il dato, il tool esegue — e la ragione è la stessa più una: un dato si
confronta, si scrive in un risultato e si **ricalcola**, e ricalcolarlo dagli argomenti è
esattamente ciò che fa il verifier di `model.routed_as_asked` (§9). Un oggetto vivo non si
ricalcola. Il port, del resto, può importare solo `ela.domain` (contratto 2): un tipo di
`ela.routing` nella firma non sarebbe stato possibile comunque.

Il nome si risolve nel tool, che tiene il `ProviderRegistryPort` accanto al router.

**Regola di architettura 26** (`tools-routing-isolation`) e **contratto import-linter 11**:
`ela.tools` non importa `ela.routing`. Il tool e il verifier ricevono un port; quale tabella sia
in vigore lo decide chi compone (M8.1). Un tool che importasse la politica potrebbe costruirsene
una — una seconda tabella, che decide dove va il contenuto dell'utente, accanto a quella che un
operatore ha configurato.

### 2. `task_type` è un argomento nuovo della capability

`task_type` entra nell'`input_schema` di `model.complete` (ADR 0010 §5) come argomento
**opzionale**, ed è la chiave di routing. `purpose` resta la descrizione umana che finisce nella
`ProviderRequest` e nell'audit: un campo documentato come descrizione non deve poter cambiare il
modello di una chiamata solo perché qualcuno lo ha riscritto.

Lo schema dichiara `{"type": "string"}` e **nessun `enum`**: il vocabolario dei tipi è quello
della tabella di routing, che è configurabile (§8), mentre il catalogo è una costante datata
(`V01_INTRODUCED_AT`). Un tipo fuori tabella è quindi rifiutato dal router, con un codice suo e
prima della rete (§6), non dal Guardian come `arguments.invalid`.

Capability estese:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `model.complete` | MEDIUM | — | — | sì | `input: string` | `purpose: string`, `instructions: string`, `task_type: string`, `model_hint: string`, `parameters: object` |

### 3. La tabella mappa un **profilo**, e un `model_hint` esplicito vince

Una rotta è `(lista ordinata di provider, profilo)`, e il profilo è uno del vocabolario di
ADR 0020 §5 (`quality`, `balanced`, `cheap`, …). Il Core non nomina mai `claude-opus-5`: la
traduzione è dell'adapter (§26, §50). Il Core non **valida** nemmeno il profilo — il vocabolario è
del provider, e un profilo che non esiste è già `provider.unknown_model_hint` senza toccare la
rete.

Chi scrive un `model_hint` negli argomenti ha scelto: l'hint diventa il profilo della rotta, e la
tabella riempie il vuoto di chi non ha scelto. Il `task_type` sceglie comunque il **provider** —
un hint nomina un profilo, non un fornitore. Ignorare l'hint risponderebbe con impostazioni
diverse da quelle chieste, senza traccia, che è ciò che ADR 0020 §5 ha già rifiutato per
`temperature`. Un hint vuoto è nessun hint, come una chiave vuota è nessuna chiave (ADR 0020 §3).

Il profilo è sempre valorizzato: «nessun profilo, decida il provider» sarebbe una scelta non
presa, e la scelta è del router.

### 4. La tabella di default: le due liste di §25

| `task_type` | Provider | Profilo |
|---|---|---|
| `planning` | `anthropic` | `quality` |
| `coding` | `anthropic` | `quality` |
| `reasoning` | `anthropic` | `quality` |
| `analysis` | `anthropic` | `quality` |
| `classification` | `anthropic` | `cheap` |
| `extraction` | `anthropic` | `cheap` |
| `routine` | `anthropic` | `cheap` |
| *(assente)* | `anthropic` | `balanced` |

Sette tipi più la rotta di default. La lista economica di §25 dice «classificazione, estrazione,
**piccoli task**, routine»: «piccoli task» è letto come `routine` e non ha una voce propria,
perché una *dimensione* non è un tipo di task e le due avrebbero nominato la stessa rotta.

Il provider è nominato in codice. È una chiave del registro, non un import — `ela.routing` non
può importare `ela.providers` (§1) — e con un provider solo una variabile in più sarebbe
configurazione senza scelta. `tests/routing/test_policy.py` verifica che quella stringa sia il
nome con cui l'adapter si registra: è l'unico posto dove i due si possono confrontare senza
rompere il contratto.

**È un'opinione, datata.** «planning → quality» è una lettura ragionevole delle due liste di §25,
non un fatto misurato, come il listino di ADR 0020 §6: si rivede qui, e
`tests/docs/test_adr_routing.py` fallisce se il codice e questa tabella si separano.

- **Tabella scritta il:** 2026-09-07 (fonte: spec §25)

### 5. Il port, e i codici

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ModelRouterPort` | §25, §26 | sync | `route` |

Sincrono: scegliere legge una tabella e uno stato **dichiarato**, e leggere uno stato dichiarato
non è I/O — è tutto il senso di `ProviderStatus` come proprietà della configurazione
(ADR 0020 §2). Stessa scelta di `ProviderRegistryPort`.

Un fallimento è un'**eccezione** (`RoutingError(PortError)`) e non un risultato, al contrario di
`ModelProvider.complete`: là il chiamato è oltre una rete, dove guastarsi è ordinario e un
risultato è ciò che permette a chi chiama di registrarlo; qui il chiamato è una tabella in questo
processo, e ELA dice già «chi ha chiamato ha sbagliato» con un `PortError` (`NotFoundError`,
`AuthorizationNotUsableError`). Il tool traduce l'eccezione in un `Outcome` fallito con lo stesso
codice, quindi ciò che arriva nell'audit non cambia.

| Codice | Quando | Rete | Dove nasce |
|---|---|---|---|
| `routing.unknown_task_type` | la politica non ha una rotta per quel `task_type` | mai toccata | `route` |
| `routing.unknown_provider` | una rotta nomina un provider che il registro non ha | mai toccata | costruzione del router |
| `provider.unavailable` | nessun provider della rotta è utilizzabile | mai toccata | `route` |

Tre codici e uno è **preso in prestito**: una rotta i cui provider sono tutti inutilizzabili
finisce in `provider.unavailable`, il codice che ADR 0020 §7 ha già dato a «questo provider non si
può chiamare». Coniarne uno accanto darebbe due nomi a un fatto solo, e chi legge un fallimento
dovrebbe conoscerli entrambi per riconoscere lo stesso muro. I due codici nuovi stanno in
`ela.ports` con gli altri, per la ragione della review di M7.2: un codice fuori dal vocabolario è
ciò che il vocabolario vieta.

### 6. Un `task_type` sconosciuto è un errore, senza rete

`routing.unknown_task_type`, nessuna chiamata. Il vocabolario dei `task_type` è **chiuso** come
quello degli hint (ADR 0020 §5): un tipo sconosciuto è un bug del Planner, non un caso da coprire
con un default. Quando il Planner (§13) esisterà, produrrà tipi da un enum; fino ad allora i piani
scritti a mano li scrivono giusti o falliscono prima della rete.

La rotta di default **non** è una rete di sicurezza per un tipo sbagliato: è la rotta di chi non
dichiara **nessun** tipo, che è un'altra cosa. Rispondere a un tipo sbagliato con la rotta di
default manderebbe il contenuto dell'utente a un modello che nessuno ha scelto, senza traccia
(§33).

### 7. Il fallback guarda solo `ProviderStatus`, e un provider assente si scopre all'avvio

`route` scorre i provider della rotta **in ordine** e prende il primo `AVAILABLE`; quelli saltati
finiscono in `ModelRoute.skipped` e da lì nell'`ExecutionResult`. Un fallimento *dopo* una
chiamata non cambia provider: rimanderebbe il contenuto dell'utente fuori una seconda volta (§57),
pagherebbe due volte una risposta che potrebbe arrivare, e si sommerebbe al retry di ADR 0020 §8.
Se nessun provider della rotta è `AVAILABLE`, il router non sceglie: `provider.unavailable`, senza
toccare la rete.

**Assente è diverso da `UNAVAILABLE`.** Un provider registrato senza chiave è *noto*, dichiara
`UNAVAILABLE` (ADR 0020 §2) e viene saltato: è il fallback che §25 chiede. Un provider che il
registro non ha è un refuso in `ELA_MODEL_ROUTES`, e il `ModelRouter` lo rifiuta **in
costruzione** con `routing.unknown_provider` e il nome sbagliato nel messaggio. Un refuso ferma
ELA prima che lavori, invece di deviare in silenzio su ciò che viene dopo nella lista o di far
fallire uno step ore più tardi, quando nessuno collegherà più le due cose.

### 8. Le variabili, e una che se ne va

| Variabile | Tipo | Default | Perché |
|---|---|---|---|
| `ELA_MODEL_ROUTES` | JSON `{task_type: {providers, profile}}` | la tabella di §4 | la tabella di un'installazione è una cosa sola e visibile |
| `ELA_MODEL_DEFAULT_ROUTE` | JSON `{providers, profile}` | `anthropic`, `balanced` | la rotta di chi non dichiara un tipo, che §6 tiene distinta da un tipo sbagliato |

Entrambe sostituiscono ciò che nominano **per intero**: una tabella metà opinione di ELA e metà
dell'operatore non si leggerebbe da nessun documento solo. Una tabella **vuota** è legale e
significa ciò che dice — si instrada solo ciò che non dichiara un tipo — perché rifiutarla
sarebbe negare a un operatore il diritto di dire «nient'altro che la rotta di default».

I due campi si chiamano `model_routes` e `model_default_route`, e `model_` è un namespace
riservato di pydantic: `RoutingSettings` dichiara `protected_namespaces=()`. Rinominare le
variabili per schivare l'avviso avrebbe chiamato la stessa cosa in un altro modo.

Variabili ritirate:

| Variabile | Ritirata in | Al suo posto |
|---|---|---|
| `ELA_ANTHROPIC_MODEL` | M7.3 | `ELA_MODEL_ROUTES`, `ELA_MODEL_DEFAULT_ROUTE` |

`ELA_ANTHROPIC_MODEL` sceglieva il modello di una chiamata senza hint (ADR 0020 §3, §5). Da M7.3 il
router nomina un profilo su **ogni** chiamata che fa, quindi la variabile non avrebbe più deciso
niente: un bottone morto. Ed è **rifiutata**, non ignorata — `AnthropicSettings` la dichiara come
lapide e alza un errore di validazione che nomina il rimpiazzo, da qualunque fonte arrivi
(ambiente, `.env`, argomento). Una configurazione che smette di funzionare in silenzio lascia chi
l'ha scritta convinto che funzioni ancora (§33). La migrazione: chi aveva
`ELA_ANTHROPIC_MODEL=claude-opus-5` scrive `ELA_MODEL_DEFAULT_ROUTE={"providers":
["anthropic"], "profile": "quality"}`, o la rotta del `task_type` che gli interessa.

Il default dell'adapter resta la costante `DEFAULT_MODEL` (`claude-sonnet-5`), che ora risponde
solo a una `ProviderRequest` costruita fuori dal tool di `model.complete`.

### 9. Il tool

Il tool valida gli argomenti (§28), instrada, risolve il nome nel registro e chiama. Tutto ciò che
precede l'ultimo passo avviene **senza rete**, e l'ordine non è casuale: argomenti che non
tipizzano sono rifiutati prima che al router si chieda qualcosa, così un fallimento di routing
significa sempre che gli argomenti andavano bene ed è la *politica* ad aver detto no. Un
`NotFoundError` dal registro — che dopo §7 non può venire dal `ModelRouter` — è
`provider.unavailable`: il tool non si fida nemmeno dei suoi collaboratori.

Una rotta che fallisce lascia comunque la riga **STARTED** che l'executor ha scritto prima di
chiamare il tool: è l'esito 1 di ADR 0021 §12 (corsa normale, esito FAILED), non una finestra
nuova. Insegnare il routing all'executor per spostare quella riga sarebbe stato peggio.

Tool sostituiti:

| Capability | Tool | Nome | Output | Codici di errore |
|---|---|---|---|---|
| `model.complete` | `ModelCompleteTool` | `model-complete` | `output`, `provider`, `model`, `finish_reason`, `profile`, `skipped` | `arguments.invalid`, `routing.unknown_task_type`, `routing.unknown_provider`, `provider.no_output`, `provider.unavailable`, `provider.unknown_model_hint`, `provider.unsupported_parameter`, `provider.authentication_error`, `provider.bad_request`, `provider.unknown_model`, `provider.rejected`, `provider.malformed_response`, `provider.rate_limited`, `provider.server_error`, `provider.unreachable`, `provider.timeout`, `provider.refusal` |

`profile` e `skipped` sono la rotta che la chiamata ha preso. Stanno nell'`ExecutionResult` e in
nessun evento di audit (§57, regola 23): un salto che nessuno può vedere dopo è una sostituzione
silenziosa, ed è ciò che §33 vieta.

### 10. La seconda condizione del verifier: `model.routed_as_asked`

Verifier sostituiti:

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `model.complete` | `ModelCompleteVerifier` | `model-complete-verifier` | `model.answered`, `model.routed_as_asked` | comuni, `model.no_answer`, `model.unaccounted`, `model.misrouted` |

`model.routed_as_asked` è la seconda condizione della decisione 10b di M7.2, rinviata qui perché
«senza una rotta non c'è niente da confrontare». Il verifier **ricalcola** la rotta dagli
argomenti — non la legge da ciò che il tool ha scritto, o verificherebbe il referto del tool — e
la confronta con il risultato: `route.provider` contro `output["provider"]`, che è il nome che il
provider ha messo lui nel suo risultato, e `route.profile` contro `output["profile"]`.

Due limiti, dichiarati:

- **Il confronto forte è sul provider.** Il modello che ha davvero risposto è un id di vendor che
  il Core non traduce (§26): sul profilo il confronto è con ciò che il tool dichiara.
- **Il ricalcolo regge perché `ProviderStatus` è statico** (ADR 0020 §2): la stessa domanda dà la
  stessa risposta, salti compresi. Il giorno in cui lo stato diventerà mutabile, questa condizione
  dovrà leggere la rotta dal risultato invece di rifarla.

Una politica che non instrada più quegli argomenti fa **fallire** la condizione
(`model.misrouted`, con il codice di routing nei dettagli): una corsa che oggi non si sa più
giustificare non è una corsa verificata.

### 11. Che cosa questo router non fa

- **Gli altri cinque criteri di §25** — qualità, latenza, costo, privacy, capacità — restano
  fuori: servono un secondo provider da confrontare e misure che non esistono.
- **Nessun secondo adapter.** La tabella sa parlare di più provider, ma ne esiste uno: il
  fallback si dimostra su dei fake, ed è una prova della *politica*, non di un'integrazione.
- **Nessun ritentativo su un altro provider dopo una chiamata fallita** (§7).
- **Nessun `task_type` nel dominio**: resta una chiave negli argomenti finché il Planner (§13) non
  produrrà un enum.
- **Nessun budget** (§30): la `ProviderUsage` si registra, non si somma e non si confronta con un
  tetto — invariato da ADR 0021.

## Alternative considerate

- **Instradare su `purpose`** (3b). Nessun campo nuovo, ma un campo documentato come descrizione
  umana avrebbe cambiato il modello di una chiamata perché qualcuno lo ha riscritto. Scartata
  (decisione 3a).
- **La tabella mappa un id di modello** (4b). Il Core avrebbe nominato `claude-opus-5`, che è la
  dipendenza dal vendor che §26 toglie. Scartata (decisione 4a).
- **La tabella vince sull'hint** (5b). Risponderebbe con impostazioni diverse da quelle chieste,
  senza traccia. Scartata (decisione 5a).
- **Fallback dopo un fallimento di chiamata** (6b). Manderebbe il contenuto dell'utente fuori una
  seconda volta (§57) e pagherebbe due risposte, sommandosi al retry dell'adapter. Scartata
  (decisione 6a).
- **Un `task_type` sconosciuto usa la rotta di default** (7a). Comodo, e manda il contenuto a un
  modello che nessuno ha scelto. Scartata (decisione 7b).
- **Un provider della rotta che il registro non ha, saltato come un `UNAVAILABLE`.** Trasformerebbe
  un refuso in una deviazione silenziosa: la traccia direbbe «saltato», ma non che quel provider
  non esiste. Scartata in review della SPEC: si rifiuta in costruzione (§7).
- **Una variabile `ELA_MODEL_PROVIDERS` per l'elenco dei provider**, lasciando in codice solo
  `task_type → profilo`. Con un provider solo è configurazione senza scelta, e la tabella di
  un'installazione smetterebbe di essere leggibile in un posto solo. Scartata.
- **Lasciare `ELA_ANTHROPIC_MODEL` come variabile ignorata.** Zero righe da scrivere, e chi
  l'aveva impostata avrebbe continuato a credere che scegliesse il modello. Scartata (§8).
- **Il router restituisce l'oggetto provider.** Il port non potrebbe dichiararlo insieme al
  profilo senza un tipo suo, e soprattutto una decisione che non è un dato non si ricalcola: il
  verifier di `model.routed_as_asked` non avrebbe niente da confrontare. Scartata (§1).

## Conseguenze

- ELA **sceglie** il modello: `model.complete` senza `task_type` va sul profilo `balanced`, con
  `task_type` sulla rotta della tabella, e il `model_hint` resta la via di chi vuole decidere a
  mano.
- `ELA_ANTHROPIC_MODEL` non esiste più e la sua presenza ferma l'avvio; `DEFAULT_MODEL` resta una
  costante dell'adapter.
- Le firme di `tools_v01` e `verifiers_v01` cambiano: il router e il registro dei provider al
  posto del provider singolo. Nessun composition root esiste ancora (M8.1), quindi il fan-out è
  tutto nei test.
- Il verifier di `model.complete` ha **due** condizioni, e la seconda dipende da una politica: un
  cambio di `ELA_MODEL_ROUTES` fra la corsa e la verifica fa fallire la verifica. È corretto — la
  corsa non è più giustificabile — ed è la ragione per cui il vincolo di ADR 0020 §2 è ora un
  vincolo anche di §63.

### Vincoli dichiarati, da riaprire quando serviranno

- **Cinque criteri di §25 su sette non sono usati** (§10).
- **Lo stato del provider è statico** (ADR 0020 §2), e ora anche `model.routed_as_asked` ci
  appoggia (§9).
- **`model.routed_as_asked` confronta il profilo con la dichiarazione del tool**, non con il
  modello che ha risposto (§9).
- **La tabella di §4 è un'opinione datata**, da rivedere quando ci sarà da confrontare qualcosa.
