# 0067. Il listino senza Haiku 4.5: tre modelli, un id che non nomina niente, e un budget che sta in ogni modello

- **Stato:** Proposta il **2026-11-11**, con l'implementazione di M14.6b sul branch `m14.6b-haiku-4-5-fuori-dal-listino`,
  dal prompt di Tommaso dell'11 novembre (decisioni 1–17) e dalla review della SPEC dello stesso giorno (risposte 18–24),
  in `docs/milestones/M14.6b.md`. Diventa Accettata con un commit suo quando la prova a mano della sezione 31 di
  `docs/GETTING_STARTED.md` è passata sull'ultimo commit del branch (decisione 14). **Le «Righe riviste» che questo ADR
  porta sono scritte**, ciascuna con il suo marchio sulla riga «Stato:» dell'ADR che rivede — ADR 0020, ADR 0057,
  ADR 0061.
- **Data:** 2026-11-11
- **Riferimenti spec:** §25, §26, §30
- **Milestone:** [M14.6b](../milestones/M14.6b.md)

## Contesto

ADR 0061 §1 ha tenuto Haiku 4.5 nel listino, senza profilo, per il mese: c'erano costi da contare e prenotazioni da
chiudere sul suo nome, e un modello sparito dal listino avrebbe fatto di una prenotazione aperta una chiamata senza
prezzo. **Il mese è passato.** Nessun profilo nomina Haiku 4.5 da M14.6, dal 2026-11-01 il libro del mese non ha
prenotazioni di ottobre, e la data «Not sooner than October 15, 2026» della sua pagina è passata (la registrazione di
M14.6b, 2026-11-02).

**Haiku 4.5 esce dal listino di ELA per la decisione di Tommaso sui modelli nuovi, non perché il fornitore l'abbia
ritirato.** Il 2026-11-11 le pagine dei prezzi e dei modelli lo nominano ancora, con il suo prezzo e non segnato come
ritirato (§1): i profili sono dei modelli 5.5, e un modello che nessun profilo nomina e che il mese non conta più è
un modello da cui ELA non ha niente da leggere.

Due strade del codice esistevano per lui solo: il campo `Model.supports_effort`, con il rifiuto «does not support effort»,
e il taglio `min(default, model.max_output_tokens)` del budget di default. Haiku 4.5 era l'unico modello senza `effort` e
con un'uscita di 64 000 token: senza di lui sono strade che nessun modello prende.

E il listino si rilegge: ADR 0061 §1 voleva una persona entro il 2026-11-28, e la rilettura della politica del fornitore
di ADR 0063 §6 va con la sua.

## Decisione

### 1. Il listino

ADR 0061 §1 è rivisto: **Haiku 4.5 esce**. Tre modelli, quattro righe.

| Modello | ID | Contesto | Max output | Fascia, token d'ingresso del prompt | $/MTok input | $/MTok output | $/MTok lettura dalla cache | `effort` |
|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | 1M | 128000 | — | 4 | 20 | 0,2 | sì |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 1M | 128000 | — | 2 | 10 | 0,1 | sì |
| Claude Haiku 5.5 | `claude-haiku-5-5` | 1M | 128000 | fino a 100000 | 0,10 | 0,50 | 0,01 | sì |
| Claude Haiku 5.5 | `claude-haiku-5-5` | 1M | 128000 | oltre 100000 | 0,50 | 2,50 | 0,05 | sì |

La lettura dalla cache costa **il 5% dell'input su Opus 5.5 e Sonnet 5.5, il 10% su Haiku 5.5**, in ogni fascia. ELA non
scrive in cache (ADR 0057 §2), quindi le colonne della scrittura restano fuori. Il default resta `claude-sonnet-5-5`.

**La colonna `effort` resta**, «sì» su ogni riga: ELA non chiede più a un modello se lo prende (§5), e
`tests/docs/test_adr_provider.py` la legge contro il corpo della chiamata — per ogni riga, `build_payload` manda `effort` a
quel modello. Una riga «no» fa fallire il test: un modello senza `effort` vuole indietro il rifiuto che M14.6b ha tolto.

- **Listino verificato il:** 2026-11-11 (fonte: `platform.claude.com/docs/en/about-claude/pricing` e
  `platform.claude.com/docs/en/models/overview`)

***Riletto il 2026-11-11.*** Tommaso ha letto le due pagine nel suo Chrome e ne ha portato il testo al revisore — il
testo Markdown della pagina, con l'indirizzo nell'intestazione —, che l'ha confrontato riga per riga con la sezione
«Che cosa rilegge Tommaso» di `docs/milestones/M14.6b.md`. La pagina dei prezzi dà i prezzi della tabella qui sopra,
modello per modello e fascia per fascia, con la soglia a «100,000», e la lettura dalla cache a 0.05x su Opus 5.5 e
Sonnet 5.5 e a 0.1x sugli altri. La frase delle fasce oggi è scritta «a request whose prompt is over 100,000 tokens pays
higher prices», dove ADR 0061 citava «a prompt of over 100,000 tokens pays higher prices»; la frase di «Long context
pricing» che ADR 0061 riporta è uguale, e continua con «and earlier requests keep the prices they were billed at». La
pagina dei modelli dà gli stessi id — per tutti e tre l'id e l'alias sono lo stesso nome —, un milione di token di
contesto, 128K d'uscita e il pensiero adattivo. **La colonna `effort` la pagina non la ha**: il «sì» si legge dalla
riga «Default effort», medium per Opus 5.5, high per Sonnet 5.5, medium per Haiku 5.5. Fuori dai tre modelli, e fuori
dal listino: le due pagine nominano Claude Fable 5.2 (8 $ e 40 $ per milione), che ELA non usa; e Haiku 4.5 c'è ancora
in tutte e due, con il suo prezzo, non segnato come ritirato.

**Le date di ritiro**, come la pagina dei modelli le mostra il 2026-11-11: «Not sooner than» September 22, 2027 per
Opus 5.5, September 28, 2027 per Sonnet 5.5, October 7, 2027 per Haiku 5.5.

`tests/docs/test_adr_provider.py` legge il listino, i profili e la data da questo ADR, che è il più recente a scriverli; la
scadenza la deriva `tests/composition/test_policy_wiring.py` dalla data e dai trenta giorni del promemoria, e vuole che
questa sezione, le Conseguenze e ADR 0063 §6 la nominino.

**Il prezzo non si controlla da sé**: lo rilegge una persona entro il 2026-12-11, e con lui la politica del fornitore
di ADR 0063 §6.

#### I profili

| `model_hint` | Modello |
|---|---|
| `quality`, `reasoning`, `planning`, `coding`, `analysis` | `claude-opus-5-5` |
| `balanced` | `claude-sonnet-5-5` |
| `fast`, `cheap`, `classification`, `extraction`, `routine` | `claude-haiku-5-5` |

Le rotte non cambiano: nominano profili, non modelli (ADR 0022). I profili sono quelli di ADR 0061.

### 2. I casi peggiori di oggi

La funzione di ADR 0057 §2, come ADR 0061 §4 l'ha rivista — d'ingresso la finestra meno `max_tokens`, e la fascia più cara
che quell'ingresso raggiunge —, sui modelli del listino: ognuno a 4096, il default, e a 8192, l'uscita del piano lungo
della sezione 23. I numeri sono quelli che `worst_cost` dà. Il modello è scritto come id, e
`tests/docs/test_adr_three_models.py` vuole una riga per ogni modello di `MODELS` e per ognuna delle due uscite, e nessun'altra.

| Modello | Uscita | Caso peggiore |
|---|---|---|
| `claude-opus-5-5` | 4096 | 4,065536 $ |
| `claude-opus-5-5` | 8192 | 4,131072 $ |
| `claude-sonnet-5-5` | 4096 | 2,032768 $ |
| `claude-sonnet-5-5` | 8192 | 2,065536 $ |
| `claude-haiku-5-5` | 4096 | 0,508192 $ |
| `claude-haiku-5-5` | 8192 | 0,516384 $ |

**Le tabelle di ADR 0057 §2 e di ADR 0061 §4 restano la storia del loro giorno**: i due test che le confrontavano con il
codice leggono questa.

### 3. Un id fuori dal listino non nomina niente

Nessuna lapide e nessuna lista di modelli ritirati (decisione 5): per ELA `claude-haiku-4-5-20251001` è un suggerimento
come un altro, che non nomina un modello. **Nel `model_hint` di uno step risponde ADR 0022 §3**: il Planner non filtra e
il router non valida; il provider non sa dire il caso peggiore di un suggerimento che non nomina un modello —
`provider.unknown_model_hint` —, e il cancello di ADR 0057 §2 nega la chiamata prima della prenotazione. Nessuna
`STARTED`, niente prenotato, nessuna domanda, niente mandato.

**La risposta dice dove sta l'id.** Il provider sa il suggerimento e non da dove viene; il tool di `model.complete` sa tutti
e due, e dopo le parole del provider aggiunge dove è scritto:

- «…: it is the step's model_hint»;
- «…: it is the profile of the route of task type 'routine' (ELA_MODEL_ROUTES)»;
- «…: it is the profile of the default route (ELA_MODEL_DEFAULT_ROUTE)».

La ragione del diniego diventa «this call cannot be bounded: provider.unknown_model_hint: no model for hint
'claude-haiku-4-5-20251001': it is the step's model_hint». Stesso codice, stesso `retryable`; nessuno decide leggendo il
messaggio (ADR 0023 §10). **Solo nel caso peggiore**: l'esecuzione non incontra mai un suggerimento sconosciuto, perché il
cancello lo chiede prima, sul Core e sul nodo, e un ramo lì sarebbe un rifiuto senza produttore.

Lo prova la pipeline intera, dall'API, con `docs/examples/ask-model-gone.json`: un piano che ELA accetta e nega al cancello.

### 4. La rotta del `.env`, all'avvio e alla chiamata

**All'avvio** la composizione legge la tabella — `ELA_MODEL_ROUTES` e `ELA_MODEL_DEFAULT_ROUTE` — contro i profili e gli id
del provider, con `default_route_model`, e se una rotta ha un profilo a cui nessun modello risponde ferma ELA con un
`ConfigurationError` che nomina la variabile, il tipo, il profilo scritto, e i profili e gli id che esistono, letti da
`PROFILES` e `MODELS` e ordinati:

> ELA_MODEL_ROUTES cannot be used: the route of task type 'routine' names the profile 'claude-haiku-4-5-20251001', which
> no model answers. The profiles are analysis, balanced, cheap, classification, coding, extraction, fast, planning,
> quality, reasoning, routine; the model ids are claude-haiku-5-5, claude-opus-5-5, claude-sonnet-5-5.

Lo fanno il Core e il nodo, con la stessa funzione, in `src/ela/composition/routes.py` (risposta 21): la tabella del nodo
deve essere quella del Core (M12.2, decisione L), e un nodo con la rotta di Haiku 4.5 si ferma all'avvio invece di
rifiutare ogni chiamata.

**Alla chiamata**, il rifiuto di §3 con la rotta nominata: per `model.complete` e per la sessione guidata, che chiede il
caso peggiore sulla rotta del suo `task_type` — `browsing`, se non ne nomina un altro —, con le stesse parole.

**Il controllo all'avvio è una credenza; la difesa è il rifiuto alla chiamata**, e la suite prova tutti e due. **Non rivede
ADR 0022 §3**, che parla del Core: il Core continua a non validare un profilo; lo fa la composizione, che conosce il
provider. Il vocabolario è quello dell'unico provider di ELA: un secondo provider porterà i suoi profili, e questa funzione
si rilegge quel giorno.

### 5. Le due strade che escono con il modello

**`effort`.** Esce il campo `Model.supports_effort`, e con lui il rifiuto «does not support effort»: il corpo controlla solo
che il livello sia uno di `EFFORT_LEVELS`. La colonna di §1 resta, e la legge il test.

**Il budget di default.** Esce il taglio `min(default, model.max_output_tokens)`: con `max_output_tokens` assente,
`max_tokens` è il default, e basta. **Il default è limitato all'avvio dall'uscita del modello più piccolo del listino**,
derivata: `SMALLEST_OUTPUT_TOKENS`, il minimo di `max_output_tokens` su `MODELS`, che `AnthropicSettings` legge al posto del
massimo che leggeva («exceeds the N tokens the smallest model can produce»). Un default sotto il più piccolo sta sotto
ognuno, e nessun taglio serve. **Il rifiuto di un `max_output_tokens` esplicito sopra il modello resta**: lo produce un
piano che lo scrive.

Nessun `Model` finto nei test tiene vive le due strade (decisione 8): i modelli dei test sono quelli di `MODELS`, e
l'arrotondamento in su del caso peggiore si prova su Opus 5.5 con un prezzo del test.

### 6. Un mese passato si legge con gli importi scritti

Le righe di ottobre stanno nel database: `STARTED` sull'id di Haiku 4.5 con il loro caso peggiore scritto, chiuse da un
costo scritto o aperte. Il libro del mese, la ripresa all'avvio, `ela spend` e i risultati di un task le leggono **con gli
importi scritti**: niente le riprezza da `PRICES`, dove Haiku 4.5 non c'è più. Lo tiene
`tests/composition/test_a_month_gone_by.py`, sugli store veri e su un database di una cartella sua, con due mutanti che
riprezzano — il libro e la vista dei risultati —, rossi tutti e due. Nessuna vista mostra il caso peggiore di una
`STARTED`: lo conta solo il libro. `GET /tasks/{id}` e `ela task show` non mostrano né modello né costo; li mostra
`ela task results`.

### 7. La prova a mano

La sezione 31 di `docs/GETTING_STARTED.md`, con `scripts/prova_m14_6b.py`: il controllo del mondo; `ela spend` e un task
di ottobre su Haiku 4.5 letti dal database vero; il piano di §3, negato, con il libro uguale prima e dopo; una chiamata vera
sulla rotta `routine`, con il costo nel libro uguale alla fascia bassa ricalcolata. Lo script non tocca il `.env`, il
database né `ela serve`. **Chi vede che cosa**: la ragione del diniego al passo 3 la guarda Tommaso, l'unico `occhio`; il
resto lo confronta lo script con l'API. **Il rifiuto all'avvio lo prova solo la suite.** **Il task di ottobre non è una
precondizione che ferma** (risposta 28): se il database non ne ha uno, il suo passo è SALTATO con la ragione scritta, e la
prova continua; che cosa la prova ha visto e che cosa no, questo ADR lo scrive quando diventa Accettata.

## Alternative considerate

- **Una lapide, o una lista di modelli ritirati**: scartata (decisione 5). Un id che ELA riconoscesse come ritirato sarebbe
  un vocabolario in più da tenere, e la risposta non cambierebbe: quell'id non nomina un modello. Il rifiuto dice dove sta,
  ed è ciò che serve per cambiarlo.
- **Il Planner che filtra i modelli che non ci sono**: scartata. Per ADR 0022 §3 il rifiuto è del provider, che conosce i
  suoi modelli, e il cancello lo obbedisce prima della prenotazione.
- **Un `Model` finto che tiene vive le due strade**: scartata (decisione 8). Una strada che nessun modello vero prende è un
  rifiuto senza produttore.
- **Riscrivere le tabelle di ADR 0057 e ADR 0061**: scartata. Gli ADR non si riscrivono: le tabelle di oggi stanno qui, e
  quelle sono la storia del loro giorno.

## Conseguenze

Nessuna regola di architettura, nessun contratto di import-linter, nessun port, nessuna rotta e nessun comando nuovo: i
conteggi di oggi restano nel test che li tiene. Nessuna migrazione: le righe di ottobre restano come sono.

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice, con
la sezione di questo ADR a cui guardare.

- **ADR 0020** §3, §5 — la riga di `ELA_ANTHROPIC_MAX_OUTPUT_TOKENS`: «≤ max del modello» è «≤ l'uscita del modello più piccolo del listino, derivata», e nessun taglio per modello; `effort` non è più «solo su un modello che lo supporta»: lo prendono tutti, e la colonna di §1 lo tiene (§1, §5).
- **ADR 0057** §2 — la tabella dei casi peggiori di oggi è quella di §2 qui; un id fuori dal listino è `provider.unknown_model_hint`, negato prima della prenotazione, e la risposta dice dove sta (§2, §3).
- **ADR 0061** §1, §4 — Haiku 4.5 non resta nel listino: il listino, la cache, i profili e la data sono quelli di §1 qui, e la tabella dei casi peggiori di oggi è quella di §2 qui (§1, §2).

**ADR 0063 §6 non è una riga rivista**: la sua nota è quella di una rilettura, nella forma del 29 ottobre, che sulla riga
«Stato:» non lascia un marchio.

Ciò che questo ADR dichiara e non risolve:

- **Il minimo e il massimo coincidono oggi**: i tre modelli producono 128 000 token, e un mutante che prendesse il massimo
  invece del minimo resterebbe verde. Il test «il budget di default sta in ogni modello» diventa rosso, con quel mutante, il
  giorno che un modello con un'uscita più piccola entra nel listino.
- **Il controllo all'avvio è una credenza**: legge la tabella e il vocabolario dell'unico provider. La difesa resta il
  rifiuto alla chiamata, che la suite prova a parte.
- **Il ramo `None` di `worst_cost` e `spending.unpriced` non hanno un produttore in produzione** (risposta 23): li tengono
  vivi un `Model` del test senza prezzo e un listino vuoto del test. Non si toccano qui: li prende
  [M14.1c](../milestones/M14.1c.md), registrata, che decide se il ramo esce o trova il suo produttore (risposta 30).
- **Il prezzo non si controlla da sé**: lo rilegge una persona entro il 2026-12-11.
