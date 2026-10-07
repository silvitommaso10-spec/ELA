# 0057. Il tetto di spesa: una riga del Core, il caso peggiore prenotato nella `STARTED`, e i modelli 5.5

- **Stato:** Proposta. Aperta il 2026-10-06 con la SPEC di M14.1 e le decisioni della review dello stesso giorno
  (A–L della sessione, 1–18 della review, in `docs/milestones/M14.1.md`); diventa Accettata quando la prova a mano di
  `docs/GETTING_STARTED.md` §23 è passata. **Rivista il 2026-10-07**, prima della prova, sulla console vera: il secondo
  tetto è il limite mensile dell'organizzazione, non quello della workspace, e il codice di §10 si rinomina
  (`docs/milestones/M14.1.md`, «Le decisioni del 2026-10-07»). **Corretta lo stesso giorno**, dalla review di
  `be7f131`: l'azzeramento alle 00:00 UTC la documentazione lo scrive per il tetto del livello, non per il limite scelto,
  e il mese di ELA resta dichiarato (§4); il `429` del tetto del livello entra in `provider.spend_limit`, e la ragione
  dice il fatto e il conto di ELA, non la causa (§10).
- **Data:** 2026-10-06
- **Riferimenti spec:** §25, §26, §30, §32, §33, §57, §63, §64
- **Milestone:** M14.1

## Contesto

Fino a M14.1 ELA registra quanto costa ogni chiamata al modello e non lo somma: ADR 0021 e ADR 0022 lo dicono con la
stessa riga, «**Nessun budget**: l'usage si registra, non si somma e non si confronta con un tetto». Era vero finché la
chiave non c'era. Con la chiave del Mac e quella del PC, una chiamata a Opus costa fino a quattro dollari, e un lavoro
che si ripete o un nodo che tace possono spenderne molti prima che qualcuno guardi la console.

§30 vuole che un'azione che spende passi dal Guardian e dal suo contesto; §32 vuole che lo usage arrivi all'audit. Nessuno
dei due dice **quanto** il mese può spendere. Lo dice chi paga, e M14.1 gli dà il posto dove scriverlo e il cancello
che lo fa valere: prima della chiamata, mai dopo.

La documentazione ufficiale (letta il 2026-10-06, e riletta il 2026-10-07 per le risposte dei limiti) dice sei cose
che questo ADR usa:

- il **tetto del livello** è ciò che l'organizzazione può spendere **ogni mese del calendario**; raggiunto, si riparte
  alle **00:00 UTC del primo del mese dopo**, e la risposta è un `429 rate_limit_error` senza `retry-after`, con
  `error.details.error_code` `enforced_spend_limit_reached`. Il limite che si sceglie, sulla pagina Billing, sta sotto
  quel tetto, e **del suo azzeramento la documentazione dice solo che la risposta indica quando l'accesso riprende**;
- un limite che si è scelto, raggiunto, risponde un `400 invalid_request_error` il cui messaggio comincia con «You have
  reached your specified API usage limits» — quello dell'organizzazione — o con «You have reached your specified
  workspace API usage limits» — quello di una workspace —, e dice quando l'accesso riprende (`api/rate-limits`);
- finito il credito prepagato non si chiama più l'API finché non lo si ricarica, e **la documentazione non scrive con
  quale risposta** (`api/errors`, `api/rate-limits` e la pagina d'aiuto sul pagamento, lette il 2026-10-07);
- il conteggio dei token prima di una chiamata è una **stima**, e manda il contenuto fuori una volta in più;
- un `429` e un `529` dicono che la richiesta non è stata eseguita: il primo per i limiti di frequenza — o per il tetto
  del livello, che il suo `error_code` distingue —, il secondo per il sovraccarico dell'API.

## Decisione

### 1. Il tetto è una riga del Core: `ELA_SPENDING_CAP_USD`

Una riga del `.env` del Core, in dollari come il listino e la console, scritta da chi paga (decisione A): **nessun
numero dell'autore nel codice**. Il default è **nessun tetto**, e senza tetto **nessuna chiamata che spende parte**
(decisione B): ELA parte lo stesso, e ogni chiamata che spenderebbe è negata prima, con la riga nominata nella ragione.
Vuota è nessun tetto, come una chiave vuota è nessuna chiave; **zero è un tetto**, e non si spende niente. Un valore
che non è un importo finito e non negativo ferma l'avvio con la variabile nominata.

La sezione è del Core soltanto: `SpendingSettings`, che `NodeConfig` non legge. **Un nodo non ha un tetto suo**:
spende solo ciò che il Core ha prenotato per il lavoro che gli manda (§6).

**I tetti sono due.** Il secondo è il **limite mensile dell'organizzazione**, quello che chi paga sceglie nella pagina
Billing della console: copre ogni chiave dovunque stia, anche ciò che le chiavi spendono fuori da ELA. Il tetto di ELA
sta sotto, con un margine: la guida lo fa impostare, e la prova lo verifica. **Fino al 2026-10-07 questo ADR diceva il
limite della workspace**: nella console vera Tommaso non è riuscito a impostarlo (decisione 1 del 2026-10-07).

Le due chiavi — del Mac e del PC — stanno nella stessa workspace (decisione K), con una ragione che non è più il limite:
**la workspace tiene insieme le due chiavi di ELA**, e la sua spesa nella console resta quella di ELA. La prova lo
verifica con l'id della workspace che ogni risposta porta (§10).

**Il credito prepagato è un fermo anche lui**: con la ricarica automatica spenta, finito il credito le chiamate si
fermano, e se è più piccolo del tetto scatta per primo. ELA non lo conta — il libro è la spesa del mese, non il saldo —
e non riconosce la sua risposta, che la documentazione non scrive (§10).

### 2. Il caso peggiore di una chiamata: dalla stessa funzione che costruisce il payload

Prima della chiamata ELA calcola il **caso peggiore**, `WorstCase`: l'output è il `max_tokens` che `build_payload` mette
nella richiesta — la stessa funzione, non una copia —, l'input è la **finestra di contesto del modello meno l'output**
(decisione 1 della review), e l'importo è

```
(contesto − max_tokens) × prezzo d'ingresso + max_tokens × prezzo d'uscita
```

arrotondato in su all'ottavo decimale. La finestra è l'unico limite dell'input che la documentazione scrive; il
conteggio dei token sarebbe una stima, un'altra uscita del contenuto, e un nodo non avrebbe niente con cui confrontarlo.

Il prezzo di questa scelta è scritto come **vincolo dichiarato**: con il `max_tokens` di default, 4096, il caso peggiore
di una chiamata è

| Modello | Caso peggiore |
|---|---|
| Opus 5.5 | 4,065536 $ |
| Sonnet 5.5 | 2,032768 $ |
| Haiku 4.5 | 0,216384 $ |

e con un tetto di 30 $ stanno in volo al più sette chiamate a Opus. **La misura per rivederlo è lo usage di un mese**: i
token d'ingresso veri delle chiamate di ELA, confrontati con i byte dell'input che le ha fatte — non una credenza sul
tokenizzatore.

Un modello che la tabella dei prezzi non conosce ha un caso peggiore **senza importo**, e la chiamata è negata
(`spending.unpriced`): una chiamata il cui costo non si può limitare non si fa. Una richiesta che il provider
rifiuterebbe prima della rete — un hint sconosciuto, un parametro non ammesso, **nessuna chiave** — non ha caso
peggiore ma lo stesso errore che `complete` darebbe, nello stesso ordine; e una richiesta che il tool rifiuta prima del
provider — gli argomenti, la rotta — lo stesso. Tutte sono negate con `spending.unbounded`.

### 3. I modelli 5.5, e il listino che dice la sua età

ADR 0020 §4 è rivisto: i profili puntano ai modelli 5.5, e Haiku ha l'id fissato — `claude-haiku-4-5-20251001`, non
l'alias, che un giorno punterebbe altrove senza che il listino lo sappia. La documentazione dà al ritiro di Haiku 4.5
una data non anteriore al 2026-10-15 e un preavviso di almeno sessanta giorni.

| Modello | ID | Contesto | Max output | $/MTok input | $/MTok output | `effort` |
|---|---|---|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | 1M | 128000 | 4 | 20 | sì |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 1M | 128000 | 2 | 10 | sì |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | 200K | 64000 | 1 | 5 | no |

La lettura dalla cache costa **il 5% dell'input su Opus 5.5 e il 10% sugli altri due** (ADR 0020 §6 diceva il 10% su
tutti e tre). Il default è `claude-sonnet-5-5`, non il modello più potente.

- **Listino verificato il:** 2026-10-06 (fonte: `platform.claude.com/docs/en/about-claude/pricing`)

Il promemoria del listino scende **da 180 a 30 giorni** (decisione 9): da M14.1 il prezzo non è più un'informazione ma
il numero con cui il cancello decide, e un listino vecchio di sei mesi sarebbe un tetto sbagliato per sei mesi.
`tests/docs/test_adr_provider.py` legge questa tabella e questa data. **Il prezzo non si controlla da sé**: nessun
test si accorge che il listino del mondo è cambiato; lo fa una persona, ogni trenta giorni.

#### I profili

| `model_hint` | Modello |
|---|---|
| `quality`, `reasoning`, `planning`, `coding`, `analysis` | `claude-opus-5-5` |
| `balanced` | `claude-sonnet-5-5` |
| `fast`, `cheap`, `classification`, `extraction`, `routine` | `claude-haiku-4-5-20251001` |

### 4. La prenotazione è la `STARTED`, e il libro del mese si deriva

La prenotazione **è** il record `STARTED` di ADR 0021 §1, con un importo: la colonna nuova `worst_case` di
`execution_results`, che solo una `STARTED` porta, e solo quella di una chiamata che spende. Scritta prima della
chiamata, chiusa dall'esito che la nomina (`metadata["started_id"]`), lasciata aperta quando l'esito non arriva.

**Il libro non si tiene, si deriva** (decisione D): speso e prenotato sono una funzione delle sole righe del mese — le
`STARTED` con un `worst_case` e gli esiti che le chiudono —, e nessuno li aggiorna. **Legge un fatto, non dei codici**
(decisione 14): l'esito dice se la richiesta è partita (`usage.sent`) e quanto è costata (`usage.cost`), e lo scrive chi
lo sa — l'adapter, e il nodo che rifiuta (§6).

- Non partita: **0**.
- Partita con un costo: **il costo**.
- Partita senza un costo, e dovunque il fatto manchi — nessun esito, nessuno usage —: **il caso peggiore**, fino al
  primo del mese dopo.

I codici restano per la ragione, non per il conto.

Il mese è **il mese del calendario, in UTC**, **dichiarato** (decisione F). La documentazione scrive questo confine per
il tetto del livello; del limite che si sceglie — il secondo tetto — dice solo che la risposta indica quando l'accesso
riprende. **Il 2026-10-07 questo ADR lo aveva scritto come «un confine documentato del secondo tetto»**: leggeva come
detta del limite scelto una frase scritta del tetto del livello, e la correzione è dello stesso giorno (review di
`be7f131`). Quindi il mese del fornitore può non essere quello di ELA, e il secondo tetto può scattare con ELA in regola
con il suo (§10). Una chiamata conta nel mese della sua `STARTED`.

Colonne aggiunte:

| Tabella | Colonne |
|---|---|
| `execution_results` | `worst_case` |

La migrazione `0013` aggiunge la colonna e l'indice `ix_execution_results_created_at`, che il libro legge; è
reversibile.

### 5. Controllo e prenotazione: un'operazione sola

La lettura del libro e la scrittura della `STARTED` stanno **sotto lo stesso lock di scrittura** del database
(`BEGIN IMMEDIATE`, come il registro), in `ExecutionResultStore.reserve`: due chiamate in parallelo non passano sullo
stesso margine. La regola è una sola, **speso + prenotato + caso peggiore ≤ tetto**, in `Decimal`. La corsa è provata
con due connessioni vere (`tests/infrastructure/persistence/test_reservation_race.py`): con margine per una, ne passa una.

### 6. Il cancello sta dove nasce la `STARTED`

- **Sul Core**, dopo il Guardian e il consumo del grant, prima della `STARTED` e della chiamata.
- **Alla presa di un nodo**: prima della presa il Core guarda il mese (`foresee`, in sola lettura) e, se la chiamata non
  ci sta, nega il task, ritira l'offerta, chiude lo step e risponde al nodo `WITHDRAWN`: **il nodo non riceve l'ordine**.
  Se il margine se ne va fra lo sguardo e la prenotazione — un'altra chiamata nello stesso istante —, il task è negato e
  nessuna `STARTED` è scritta; al nodo non va nessun ordine, e la sua presa scade senza niente fatto.
- **Prima di una domanda** (decisione 7): una chiamata che un «sì» non farebbe passare è negata senza chiedere, e nessuno
  è svegliato. Dopo il sì il cancello guarda il mese di nuovo: i numeri della domanda erano di quell'istante.

**La prenotazione viaggia con l'ordine, e il nodo non spende oltre**: `WorkOrderOut` porta il `worst_case` prenotato, e
prima di agire il nodo chiede al suo tool il caso peggiore — con la sua rotta, il suo `max_tokens`, i suoi prezzi. Se è
più di quello del Core, o il nodo non sa limitarlo, o l'ordine non ne porta uno, **non chiama**, e consegna
`spending.over_reservation` con `usage.sent` falso: il libro la chiude a zero. Non è un tetto del nodo: è il nodo che
tiene il numero del Core.

Perché le due strade abbiano entrambe la `STARTED`, un tool che spende è **non idempotente e non ripiazzabile**: è la
regola 60, `a-tool-that-spends-is-neither-repeated-nor-moved`. E chi chiama il provider dice quanto può costare la
chiamata: la regola 61, `who-calls-the-model-bounds-the-call`. **La regola 61 vede solo chi chiama `.complete(`**
(decisione 15): una sessione di Claude Code, che arriva con M14.3, spende sulla stessa chiave senza chiamarlo, e la
regola non la vede. Il tetto di quella strada è di M14.3, che riceve un'annotazione datata.

### 7. Il diniego del tetto: una transizione con la sua ragione

Il tetto non è un permesso, e un «sì» non lo alza (decisione G): il diniego viene **dopo** un `ALLOWED` del Guardian —
o, prima di una domanda, dopo un `REQUIRES_APPROVAL` —, ed è un'operazione sua dell'engine:

| Operazione | Da | A | Audit | Chiave |
|---|---|---|---|---|
| `deny_by_cap` | EXECUTING | DENIED | `TASK_DENIED` | `decision_id` |

La ragione nomina la riga, sempre. Le quattro frasi, ciascuna con il suo codice nel payload dell'audit:

- `spending.no_cap`: «no monthly cap: ELA_SPENDING_CAP_USD in the Core's .env sets it, in USD»;
- `spending.unbounded`: «this call cannot be bounded: <codice>: <messaggio>»;
- `spending.unpriced`: «<modello> has no price in ELA's table: a call whose cost cannot be bounded is not made
  (ELA_SPENDING_CAP_USD)»;
- `spending.over_cap`: «the monthly cap would be crossed: spent S + reserved R + this call's worst case W > cap C USD
  (ELA_SPENDING_CAP_USD, AAAA-MM)».

Il `TASK_DENIED` porta i numeri — mese, tetto, speso, prenotato, caso peggiore, valuta — come stringhe di `Decimal`, mai
il contenuto dell'utente. **Il denaro non entra nell'audit della domanda** (decisione 6): il taglio di M13.2 resta.

### 8. La domanda nomina il caso peggiore e ciò che resta del mese

La domanda di una chiamata che spende porta due pezzi in più, letti con la funzione del cancello (decisione H):
`worst_case` — «4.065536 USD, claude-opus-5-5, up to 995904 tokens in and 4096 out» — e `left`, «26.2 of 30 USD left in
2026-10». La CLI li stampa come `worst case` e `left this month`; la console e il companion come «Costo massimo» e «Resta
nel mese». Assenti, non vuoti, per ogni altra domanda.

### 9. `ela spend`, in sola lettura

Ciò che Tommaso legge è ciò che il cancello confronta (decisione I): una rotta e un comando, sulla stessa funzione.

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/spend` | il mese, quando riparte, il tetto e la sua riga, lo speso, il prenotato e il resto |

| Comando | Rotta | Uscite |
|---|---|---|
| `ela spend` | `GET /spend` | `0` `1` `2` `3` |

Gli importi sono quelli del cancello, esatti: una frazione di centesimo si stampa, non si arrotonda a zero. Senza tetto
la riga dice che nessuna chiamata che spende parte e quale riga lo cambia, e il comando esce `0`: un tetto che manca è
una configurazione, non un errore del comando.

### 10. Gli errori: `provider.spend_limit`, e un ritentativo solo per ciò che non è partito

ADR 0020 §7 ha un quindicesimo codice (decisione 10): `provider.spend_limit`, **un limite di spesa del fornitore
raggiunto**. Tre risposte lo danno:

- il `400` di un limite che chi paga ha scelto nella console — **quello dell'organizzazione**, il secondo tetto, o quello
  di una workspace, che la documentazione scrive ancora e che resta riconosciuto —, dall'inizio del messaggio che la
  documentazione scrive per ciascuno; il messaggio del server **si legge e non si conserva** (ADR 0020 §10);
- il `429` del **tetto del livello**, riconosciuto da `error.details.error_code` `enforced_spend_limit_reached` — un
  campo, non un testo — (review di `be7f131`).

Se una frase o il campo cambiassero, la risposta tornerebbe `provider.bad_request` o `provider.rate_limited`, com'era
prima: nessun danno. **Si chiamava `provider.workspace_limit`** fino al 2026-10-07, quando la console vera ha mostrato
che il limite che tiene è quello dell'organizzazione (decisione 3 del 2026-10-07); il branch non era ancora unito, e il
nome si è potuto cambiare.

**La ragione dice il fatto, non la causa.** Il mese del fornitore può non essere quello UTC di ELA (§4): 50 $ a fine mese
e 50 all'inizio del dopo stanno nella stessa finestra del fornitore, e il suo limite scatta con ELA in regola. «Il conto
di ELA è indietro», che questo ADR scriveva il 2026-10-07, sarebbe una diagnosi falsa. La ragione dice quale limite —
dell'organizzazione, di una workspace, del livello — e **quanto ELA ha contato del suo tetto** nel suo mese: lo aggiunge
il Core (`SpendingGate.counted`) dove l'esito si scrive, sul Core e alla consegna di un nodo, con il libro del mese e
questo esito dentro, perché l'adapter il libro non lo vede. Le cause le elenca §23 della guida: il conto di ELA indietro
rispetto alla fattura, una spesa con un'altra chiave dell'organizzazione, il mese del fornitore diverso da quello UTC di
ELA.

**Il credito esaurito non ha un codice suo**: la documentazione non scrive con che risposta arriva, e un evento il cui
messaggio non è scritto non si indovina. Resta dove cade — `provider.bad_request`, se è un `400` —; e un `402` ha il tipo
`billing_error`, che il messaggio che ELA conserva porta già (ADR 0020 §10), sotto `provider.rejected`. §23 della guida
dice che un fallimento con il tipo `billing_error`, o un `provider.bad_request` mentre `ela spend` mostra margine, vuol
dire guardare il credito e il pagamento nella console.

**La prova a mano non raggiunge né l'uno né l'altro**: servirebbe spendere fino al limite, o fino all'ultimo centesimo
del credito. Il primo lo prova la suite, con una risposta costruita sulle parole della documentazione.

| Eccezione SDK | HTTP | Codice | `retryable` |
|---|---|---|---|
| — (nessuna chiave) | — | `provider.unavailable` | no |
| — (hint sconosciuto) | — | `provider.unknown_model_hint` | no |
| — (parametro non ammesso) | — | `provider.unsupported_parameter` | no |
| `APITimeoutError` | — | `provider.timeout` | **sì** |
| `APIConnectionError` | — | `provider.unreachable` | **sì** |
| `RateLimitError` con `error_code` `enforced_spend_limit_reached` | 429 | `provider.spend_limit` | no |
| `RateLimitError` | 429 | `provider.rate_limited` | **sì** |
| `InternalServerError` | ≥500 (incl. 529, 504) | `provider.server_error` | **sì** |
| `AuthenticationError`, `PermissionDeniedError` | 401, 403 | `provider.authentication_error` | no |
| `BadRequestError` con il messaggio di un limite di spesa scelto | 400 | `provider.spend_limit` | no |
| `BadRequestError` | 400 | `provider.bad_request` | no |
| `NotFoundError` | 404 | `provider.unknown_model` | no |
| altro `APIStatusError` 4xx (409, 422, …) | 4xx | `provider.rejected` | no |
| `APIResponseValidationError` e ogni altro `APIError` | — | `provider.malformed_response` | no |
| `stop_reason == "refusal"` | 200 | `provider.refusal` | no |
| — (risposta senza testo) | 200 | `provider.no_output` | no |

La colonna `retryable` è la natura dell'errore, che passa al chiamante e non cambia. **ADR 0020 §8 è rivisto
apertamente** (decisione 2): ELA rimanda la stessa richiesta **solo** per il `429` di frequenza e il `529`, che dicono che
il lavoro non è stato fatto e che potrebbe farsi poco dopo — non per il `429` del tetto del livello, che tiene fino al
mese dopo (review di `be7f131`). Un timeout, una connessione caduta, ogni altro `5xx` e una risposta illeggibile possono arrivare dopo
che il lavoro è stato fatto e pagato: nessuno lo sa, e un esito ignoto **non si paga due volte**. Per questi l'esito è
«partita, costo ignoto», e il libro tiene il caso peggiore. **Che un `529` non si paghi è una lettura del nome**,
«overloaded»: la documentazione non lo scrive. `ELA_ANTHROPIC_MAX_RETRIES` conta i ritentativi di quei due.

L'adapter scrive anche **l'id della workspace** in cui la chiave ha lavorato, dall'intestazione della risposta: il tool
lo mette nell'output, `workspace` (decisione 12). È ciò che fa vedere alla prova che le due chiavi di ELA stanno nella
stessa workspace (§1).

Tool sostituiti:

| Capability | Classe | Nome | Output | Codici d'errore |
|---|---|---|---|---|
| `model.complete` | `ModelCompleteTool` | `model-complete` | `output`, `provider`, `model`, `finish_reason`, `profile`, `skipped`, `workspace` | `arguments.invalid`, `routing.unknown_task_type`, `routing.unknown_provider`, `routing.empty_routes`, `provider.no_output`, `provider.unavailable`, `provider.unknown_model_hint`, `provider.unsupported_parameter`, `provider.authentication_error`, `provider.bad_request`, `provider.unknown_model`, `provider.rejected`, `provider.malformed_response`, `provider.rate_limited`, `provider.server_error`, `provider.unreachable`, `provider.timeout`, `provider.refusal`, `provider.spend_limit` |

### 11. Righe riviste

Gli ADR non si riscrivono: queste righe si leggono con questo accanto.

- **ADR 0020 §4, §5, §6**: i modelli, i profili, la cache e la data del listino sono quelli di §3 qui sopra; il
  promemoria è a trenta giorni.
- **ADR 0020 §7**: quindici codici, non quattordici (§10).
- **ADR 0020 §8**: si ritentano solo il `429` di frequenza e il `529`; il `429` del tetto del livello no (§10).
- **ADR 0021 «Nessun budget»** e **ADR 0022 «Nessun budget»**: l'usage si somma, nel libro derivato di §4, e si
  confronta con il tetto di §1, prima della chiamata.
- **ADR 0040, due vincoli dichiarati** che ADR 0043 §9 manda qui — la negativa delle due tabelle di rotte e il task il
  cui nodo tace a metà lavoro — si chiudono con i passi 7 e 6 di §23, **quando la prova passa**.

### 12. La prova a mano

`docs/GETTING_STARTED.md` §23, con lo script `scripts/prova_m14_1.py`, sul Mac e sul PC: il PC sullo stesso commit, il
secondo tetto — il limite dell'organizzazione, sopra il tetto di ELA —, i tre modelli con la chiave vera, il tetto che
scatta, una chiamata del PC con la stessa workspace, il nodo che tace con la sua prenotazione aperta, e la negativa
`model.misrouted`. **Da fare.**

## Alternative considerate

- **Un contatore della spesa**, aggiornato a ogni chiamata. Rifiutato: un numero che si aggiorna è un numero che può
  sbagliare in silenzio — un crash fra la chiamata e l'aggiornamento —, e il libro derivato non ha niente da aggiornare.
- **Il conteggio dei token prima della chiamata** per un caso peggiore più stretto. Rifiutato (decisione 1): è una stima
  e manda il contenuto fuori una volta in più.
- **Il tetto anche sul nodo.** Rifiutato (decisione B): due tetti su due macchine sono due mesi, e nessuno dei due vede
  l'altro. Il nodo tiene il numero del Core.
- **Ritentare ogni `5xx` come prima.** Rifiutato (decisione 2): un `500` dopo il lavoro è un lavoro pagato due volte.
- **Un tetto in euro.** Rifiutato: il listino e la console sono in dollari, e una conversione sarebbe un'altra credenza.

## Conseguenze

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ExecutionResultStore` | §30, §32 | async | `spending`, `reserve` |
| `ModelProvider` | §25, §30 | async | `worst_case` |
| `ToolPort` | §27, §30 | async | `worst_case` |

Con questo ADR le regole di architettura sono **sessantuno** (la 60 e la 61), i port restano **trenta**, le rotte
dell'API sono **cinquanta** (`GET /spend`) e i comandi della CLI **ventotto** (`ela spend`).

Ciò che questo ADR dichiara e non risolve:

- **Il caso peggiore è la finestra di contesto**: una chiamata a Opus prenota 4,07 $ anche quando ne costa un
  centesimo, e il tetto si riempie di prenotazioni prima che di spesa. La misura per rivederlo è lo usage di un mese (§2).
- **Una prenotazione rimasta aperta resta al caso peggiore fino al primo del mese dopo**: un nodo che tace, o un esito
  che non arriva, tengono fermo il margine (§4).
- **La presa persa nella corsa resta presa fino alla sua scadenza**: il nodo non riceve niente e non fa niente, e
  intanto non prende altro lavoro (§6).
- **Il mese di ELA è dichiarato**: la documentazione scrive la ripresa alle 00:00 UTC del primo del mese per il tetto
  del livello, e del limite scelto dice solo che la risposta «states when access resumes» (§4). Il secondo tetto può
  scattare con ELA in regola: la ragione dice il fatto e il conto di ELA, non la causa (§10).
- **Il credito esaurito non si riconosce**: la documentazione non scrive la sua risposta, e resta
  `provider.bad_request` se è un `400` (§10).
- **Che un `529` non si paghi è la lettura del nome** (§10).
- **Il prezzo non si controlla da sé**: lo controlla una persona ogni trenta giorni (§3).
- **La regola 61 non vede una sessione di Claude Code** (§6), che M14.3 porterà.
- **Il confronto fra la somma di ELA e il costo della console è una misura da fare dopo un mese d'uso**: le chiamate di
  prova costano meno di un centesimo, e la console arrotonda ai centesimi.
