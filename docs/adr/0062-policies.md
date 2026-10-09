# 0062. Le policy di §59: una riga che Tommaso scrive, con i suoi confini e una fine, rende autonoma un'azione `MEDIUM` senza abbassarne il livello

- **Stato:** **Proposta** il 2026-10-09, con l'implementazione di M13.12, dopo la SPEC decisa (le decisioni 1–15 della
  sessione e 16–23 della review, in `docs/milestones/M13.12.md`). Diventa Accettata con un commit suo, quando la prova a
  mano della sezione 27 di `docs/GETTING_STARTED.md` passa sul Mac (§15).
- **Data:** 2026-10-09
- **Riferimenti spec:** §19, §27, §29, §30, §32, §33, §57, §59, §62
- **Milestone:** M13.12

## Contesto

§59 vuole «autonomia senza trasformare ELA in un processo onnipotente». Fino a M13.12 la forma di una policy c'era — un
`Authorization` senza `approval_id`, che il Guardian accettava (ADR 0011 §6, ADR 0012 §1) — ma **nessun percorso di
produzione la creava**: ogni grant nasceva da un sì, con il suo task e il suo step. La 5.11 di `docs/STATO.md` aveva deciso
che un'azione `MEDIUM` diventa autonoma solo con una policy che Tommaso crea, mai abbassando il livello, e che la prima
milestone della fila che ne avesse bisogno avrebbe aperto, prima di sé, quella del percorso. Con M14.3 ogni sessione di
`browser.guided` chiede un sì (ADR 0060 §1): è la prima azione `MEDIUM` che vuole girare senza domanda, e Tommaso ha aperto
M13.12 il 2026-10-09, prima di M13.9.

Un grant permanente com'era — uno scope e nient'altro — sarebbe stato troppo: per `browser.guided` avrebbe coperto una
sessione di qualunque costo, di qualunque durata, su qualunque modello, per sempre. Questo ADR dice che cosa una policy
deve limitare, come nasce, quando copre, come si toglie e che cosa dice di sé.

## Decisione

### 1. La dichiarazione: `policy_terms`

Il meccanismo è generale, e **quali capability lo ammettono lo dichiara la capability**: `CapabilitySpec.policy_terms`, un
`PolicyTerms` nullo per default, che **classifica ogni argomento dello schema** in quattro classi — i tetti (`limits`), gli
argomenti che una policy non copre mai (`uncovered`), quelli che lascia liberi (`free`) e quelli con lo scope
(`scoped_arguments`, che ci sono già) — e porta **la rotta** della sessione e **il modello** che la rotta di default legge
oggi. In M13.12 lo dichiara solo `browser.guided`; le altre `MEDIUM` lo ricevono nella milestone che ne ha bisogno, con le
sue ragioni.

| Capability | Tetti | Mai coperti | Liberi | Rotta |
|---|---|---|---|---|
| `browser.guided` | `max_cost_usd`, `looks`, `seconds` | `task_type` | `goal` | `browsing` |

Il modello lo passa il punto di composizione, come i siti: `default_route_model` legge la tabella delle rotte e i profili
del fornitore — senza rete e senza chiave — e dà `claude-haiku-5-5` con la tabella di oggi; il catalogo costruito senza
impostazioni porta `undeclared`, la forma di `UNDECLARED_SITES`, e sotto quel nome nessuna policy nasce, perché la
prospettiva del tool rifiuta prima (§7). **Una policy nomina un modello solo**: la rotta di default di una capability con
`policy_terms` ha un fornitore, e un test fallisce il giorno in cui ne ha due (`tests/permissions/test_policy_terms.py`),
con il suo caso negativo — chi aggiunge un fornitore decide con un ADR se il modello passa dai termini a un fatto della
chiamata (la forma di ADR 0045 §13).

**Il catalogo rifiuta la dichiarazione alla costruzione**, con `InvalidCapabilityError` e la ragione, quando: la riga della
capability, letta da `RISK_POLICY`, non è `APPROVAL_UNLESS_AUTHORIZED` — «no policy reaches a HIGH (ADR 0045 §3)», «it does
not ask: it needs no policy»; una `CRITICAL` il catalogo la rifiuta prima, con il suo tetto —; i tetti sono vuoti; un tetto
non è un argomento obbligatorio `integer`, o `string` con `COST_PATTERN`; un argomento mai coperto è obbligatorio; un
argomento libero e obbligatorio non è una `string`; **le quattro classi non sono una partizione dello schema**; la
capability non ha argomenti con lo scope. La partizione a mondo chiuso è ciò che fa smettere da sé le policy vecchie quando
lo schema cresce: un argomento nuovo deve dire in quale classe sta, e la dichiarazione cambia (§4, `TERMS`).

`RISK_POLICY`, `Rule`, `ASKING_RULES` e `asks_at_every_use` stanno in un modulo loro, `ela/permissions/rows.py`, che il
catalogo legge senza un ciclo con il Guardian; **i valori non cambiano**, e nemmeno `POLICY_VERSION`.

### 2. I termini sul grant, e le due invarianti

`Authorization` guadagna **`bounds: PolicyBounds | None`** — i tetti, un nome per valore, ogni valore un testo che
`Decimal` legge e mai un `float`, con **una copia dei termini sotto cui la policy è nata** — e **`revoked_at`**. Le
invarianti del dominio, accanto a quella di ADR 0012 §1, nello stesso validatore:

- un grant **senza** `approval_id` ha `expires_at`: **una policy scade sempre**;
- un grant **con** `approval_id` non ha `bounds`: un sì ha il suo task e il suo step, non dei tetti.

Che le chiavi dei tetti siano quelle dei termini è un controllo del predicato (§4, `TERMS`), non del tipo: una riga che il
tipo rifiutasse fermerebbe ogni grant della capability alla lettura, e lo step finirebbe in un errore invece che in una
domanda. `max_uses` di una policy resta nullo, e gli usi si contano: **contano le spese, non le sessioni** — un grant si
spende prima della `STARTED` (ADR 0046 §3), quindi una sessione rifiutata dopo, dal tetto del mese, conta un uso. **Una
policy non si modifica**: la regola 15 aggiunge `bounds` ai campi che un `model_copy` fuori da `ela.permissions` non può
nominare; `revoked_at` no, perché anche un `Device` ha quel campo e lo store finto dei nodi lo scrive — la revoca di una
policy la tiene la regola 66 (§3), che lascia `.revoke(` sulle autorizzazioni alla sola rotta.

Colonne aggiunte:

| Tabella | Colonne |
|---|---|
| `authorizations` | `bounds`, `revoked_at` |

La migrazione `0015` aggiunge le due colonne, nullabili, e nessun'altra tabella cambia. **Prima conta le righe senza
`approval_id` e senza `expires_at`**: nessun codice le ha mai scritte, ma una scritta a mano sarebbe una riga che il mapper
non sa leggere, e la migrazione si ferma con un messaggio che dice quante sono e che cosa fare invece di lasciare un
database che ELA non legge. I grant di prima restano con le due colonne vuote.

### 3. La nascita, e la regola 66

Una funzione pura di `ela/permissions/policies.py`:

```python
def authorization_from_policy(
    request: PolicyRequest,
    *,
    catalogue: CapabilityRegistryPort,
    granted_by: str,
    now: datetime,
    authorization_id: AuthorizationId,
) -> Authorization: ...
```

`PolicyRequest` porta la capability, lo scope, i tetti come testi e i giorni. I controlli sono la tupla `POLICY_CHECKS`
dell'enum `PolicyCheck` — il nome `Check` è dei controlli di un sì —, **il primo che fallisce vince**, e ogni fallimento è
`PolicyRefusedError(check, reason)` prima che esista un grant:

| # | Controllo | Che cosa deve essere vero |
|---|---|---|
| 1 | `CATALOGUE` | la capability è nel catalogo |
| 2 | `ADMITS` | la capability ammette una policy: la ragione di `no_policy_for` — una `HIGH`, una che non chiede, una `MEDIUM` che nessuna milestone ha dichiarato |
| 3 | `SCOPE` | lo scope non è vuoto, ogni voce è valida e sta nello scope registrato della capability (ADR 0011 §4) |
| 4 | `LIMITS` | i tetti sono esattamente quelli dichiarati, e ognuno, letto con il tipo del suo argomento, è valido per il suo schema |
| 5 | `DAYS` | i giorni sono un intero, dal minimo al massimo |

Il grant: nessun `approval_id`, nessun task né step, `expires_at = now + days`, `max_uses` nullo, i tetti con i termini di
oggi, `metadata = {"origin": "policy"}`. **I giorni non hanno default**, né nella funzione né nella rotta. Le costanti:

```python
MIN_DAYS = 1
MAX_DAYS = 90
WHY_DAYS = 30
WHY_MAX = 3
SHORT_ID = 8
```

**Chi la chiama è chi salva e scrive l'audit**, come per un sì (ADR 0012 §6): la rotta della creazione scrive
`AUTHORIZATION_GRANTED` con `origin: "policy"`, lo scope, i tetti, i termini, `expires_at` e i giorni, firmato `USER` con
l'id che il middleware ha risolto — il nome e il ruolo li legge chi elenca (ADR 0059 §3).

**La regola 66, `a-policy-is-born-at-its-route`**, in tre parti con i loro casi negativi in `violations.py` e la sua
vacuità: (1) fuori da `api/policies.py` nessuno chiama `authorization_from_policy`; (2) nessuno salva un grant — `.grant(` su
un ricevente delle autorizzazioni — fuori dalla rotta e dall'executor, e **l'executor salva solo un grant legato, nella
stessa funzione, a `authorization_from_approval`**: non salva mai un grant senza `approval_id`; (3) nessuno revoca fuori
dalla rotta, e nessun modulo di `ela.tools` nomina `AuthorizationStore`: **nessuna capability crea o revoca una policy**. Il
ricevente decide, come nelle regole 16 e 62: la revoca di un nodo non è quella di una policy.

### 4. Il predicato: `shortfall`

Una funzione sola dice la prima ragione per cui una policy non copre una chiamata, o nessuna —
`shortfall(policy, capability, arguments, *, now, gaps=GAPS) -> Shortfall | None`, sulla specifica **registrata** —, e la
leggono il Guardian, l'executor e la domanda. L'ordine è la tupla `GAPS`:

| # | Gap | Che cosa manca | La frase, per una policy `3f2a1b2c` |
|---|---|---|---|
| 1 | `REVOKED` | `revoked_at` c'è | «policy 3f2a1b2c was revoked on 2026-10-09» |
| 2 | `EXPIRED` | `expires_at <= now`, verso chiuso (ADR 0005 §2-bis) | «policy 3f2a1b2c expired on 2026-10-10» |
| 3 | `TERMS` | la capability non dichiara termini; la policy non ha tetti; i suoi termini — la classificazione e il modello — non sono quelli di oggi; o i nomi dei tetti non sono quelli dei termini | «browser.guided declares other terms than those policy 3f2a1b2c was created under» |
| 4 | `SITE` | lo scope della policy non copre ogni bersaglio della chiamata | «a value of sites is not among those of policy 3f2a1b2c» |
| 5 | `LIMIT` | un tetto alla volta, nell'ordine della dichiarazione: il valore della chiamata è sopra, o uno dei due non è un numero | «max_cost_usd 2.00 is above the 1.10 of policy 3f2a1b2c» |
| 6 | `ARGUMENT` | la chiamata porta un argomento che non è un tetto, lo scope o libero nei termini della policy: il mondo è chiuso | «task_type is never covered by a policy: policy 3f2a1b2c does not cover this call» |

**Due fette nominate della stessa tupla**: `UNUSABLE` (revocata, scaduta) e `UNCOVERED` (termini, sito, tetti, argomento) —
la distinzione di ADR 0011 §6 fra *usabile* e *copre*, e ogni ragione sta da una parte sola. Il confronto dei tetti è con
`Decimal`: `1.1` e `1.10` sono lo stesso tetto, un `bool` non è un numero, e un valore che non si converte **non copre** — una
frase, mai un'eccezione. Il goal non è guardato: è il punto della policy. **La frase nomina la policy con l'id breve e con i
numeri, mai con un sito né con le parole della chiamata**: è ciò che la lascia stare sopra il tetto di ogni pagina (§8).
**Termini cambiati vuol dire policy che smettono di coprire da sé**: la copia sul grant non è più quella della capability.

### 5. Il Guardian e l'executor

Per un grant senza `approval_id`, il Guardian legge il predicato e **solo il predicato**: `_mismatch` — dopo la capability,
il task, lo step e gli usi non negativi — nega prima una policy presentata per una riga che chiede a ogni uso, con la
ragione di ADR 0045 §3, poi legge `UNCOVERED`; `_unusable` legge `UNUSABLE` — revocata o scaduta è il «chiedi» di §62, una
domanda —, poi gli usi. Quando permette su una policy, la ragione dice **«covered by policy <id>»**. `RISK_POLICY`,
`POLICY_VERSION` e i membri di `Rule` non cambiano.

`select_authorization` riceve la specifica registrata e gli argomenti al posto del solo rischio, e *copre* e *usabile* per
una policy sono le due fette; il resto della scelta è quello di ADR 0013 §3. Una proprietà con hypothesis
(`tests/executive/test_select_policies.py`) lo tiene, con un oracolo che non è `shortfall`: la strategia sa quale policy ha
costruito perché copra. Il grant scelto non è mai un `AUTHORIZATION_MISMATCH`; se c'è una policy che copre ed è usabile la
decisione è `ALLOWED`; se c'è solo una policy che copre e non è usabile, la decisione è una domanda che ne nomina la ragione.

### 6. La revoca

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `AuthorizationStore` | §30, §59 | async | `revoke` |

`revoke(authorization_id, *, at)` scrive `revoked_at` **una volta**, con una `UPDATE … WHERE id = :id AND revoked_at IS
NULL`; un id ignoto è `NotFoundError`, la seconda volta `AuthorizationAlreadyRevokedError` con l'istante della prima. `at` è
del chiamante: lo store non ha orologio (ADR 0012 §3). **`consume` rifiuta un grant revocato nella stessa `UPDATE`** della
scadenza e degli usi, e la lettura che nomina l'errore guarda la revoca prima della scadenza: `AuthorizationRevokedError`,
sottoclasse di `AuthorizationNotUsableError`, quindi l'executor **chiede**. `AUTHORIZATION_REVOKED`, un tipo d'evento nuovo,
lo scrive la rotta della revoca, firmato `USER`, con `origin`, `revoked_at`, `expires_at` e gli usi fino a lì.

**La revoca non ferma una sessione già partita**: il grant è già speso e la decisione è data; l'uscita lo dice, sulla CLI e
sulla console — «a session already running under it goes on until it ends: to stop it, ela task cancel <id>». Si revoca una
policy viva: una scaduta è un `409` con la sua scadenza; una già revocata è la risposta dello store, un `409` con l'istante
della prima revoca — la stessa che si siano rincorse o no —; un grant nato da un sì non è una policy, `404`.

### 7. «Partirebbe», e l'anteprima

Dopo i controlli puri e prima di ogni scrittura, la rotta chiede al tool **la stessa prospettiva che precede una domanda**
(ADR 0045 §6-bis), con gli argomenti di una chiamata **ai tetti e sui siti della policy** — `prospect_arguments` —, ogni
argomento libero e obbligatorio con una frase fissa di ELA che non si salva, `POLICY_PROSPECT`, e nessun argomento mai
coperto: la rotta di default. **Un rifiuto del tool è il rifiuto della creazione, con il suo codice** davanti alla ragione:
un tetto di costo di 0,05 $ è `guided.cap_below_one_call`. E se il modello che la prospettiva nomina non è quello della
dichiarazione, la creazione è rifiutata con `policy.model_changed`.

**L'anteprima è la stessa strada senza scrittura**, e nomina ciò che si approva: la capability e i siti; i tetti e la
scadenza con la data; il modello della rotta di default di oggi e che le pagine vanno al fornitore; che il tetto di costo
**è sulla prenotazione e non sulla spesa vera**, con il caso peggiore di una chiamata — `Guided.one_call` —; e ciò che la
policy non copre mai, derivato dal catalogo: ogni capability che chiede a ogni uso, una chiamata oltre un tetto o fuori dallo
scope, una chiamata con un argomento mai coperto. **La conferma salva ciò che l'anteprima ha mostrato**: porta il modello
dell'anteprima, e se la prospettiva di adesso ne nomina un altro è un `409`, `policy.preview_changed`.

### 8. La riga «perché te lo chiedo»

La domanda di una capability con `policy_terms` resta quella di prima e guadagna **`why`**, scritta dall'executor con gli
altri fatti della domanda, in `_ask`, che legge lo store una seconda volta all'istante della decisione: le policy della
capability nate prima della decisione, vive o finite da meno di `WHY_DAYS` giorni, al più `WHY_MAX`, la più recente prima,
ciascuna con la prima ragione di `shortfall`; «no policy of yours for browser.guided» se non ce n'è; e una policy che copre —
lo step ha già un sì, e l'executor usa il suo grant (ADR 0015 §6) — è detta tale, perché un sì dato a uno step resta la sua
risposta. **ADR 0045 §11**: la console, il telefono e `ela approvals` la mostrano tutti e tre, nella riga «why I ask» e
nella coppia «Perché te lo chiedo», o non rispondono. Sta sopra il tetto: id brevi e numeri.

### 9. L'API

Quattro rotte nuove, in `ela/api/policies.py`, che raggiunge `CORE` con il token:

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/policies` | le policy vive, e con `all=true` anche le finite; e le capability che ne ammettono una, con i loro termini |
| `POST` | `/policies/preview` | l'anteprima: gli stessi rifiuti della creazione, nessuna scrittura |
| `POST` | `/policies` | la creazione, con il modello che l'anteprima ha nominato |
| `POST` | `/policies/{policy_id}/revoke` | la revoca |

Una policy sul filo porta l'id e l'id breve, la capability, lo scope, i tetti, i termini, la scadenza, `revoked_at`, lo stato,
gli usi, `created_at` e chi l'ha creata. **Ogni identità del middleware sta da una parte** (`tests/api/test_policy_kinds.py`,
una riga per membro di `Kind`, a mondo chiuso): `CORE` le rotte JSON, `CONSOLE` le pagine, gli altri niente.

Errori aggiunti, nella forma della tabella di ADR 0023 §10:

| Caso | Eccezione | Stato |
|---|---|---|
| un controllo della nascita fallisce | `PolicyRefusedError` | `422` |
| il tool rifiuta la chiamata ai tetti e sui siti della policy | `PolicyWouldNotStartError` | `422` |
| la conferma nomina un modello che la prospettiva di adesso non nomina | `PolicyPreviewChangedError` | `409` |
| la revoca di una policy scaduta | `PolicyNotLiveError` | `409` |
| la revoca di una policy già revocata | `AuthorizationAlreadyRevokedError` | `409` |
| una console sotto il tetto `LOCAL_ONLY` chiede l'anteprima o la creazione | `PolicyOutOfReachError` | `409` |

Codici aggiunti a `ela.ports.WireCode`:

| Codice | Membro | Quando |
|---|---|---|
| `policy.refused` | `POLICY_REFUSED` | un controllo della nascita: il messaggio comincia con il suo nome |
| `policy.would_not_start` | `POLICY_WOULD_NOT_START` | un rifiuto del tool: il messaggio comincia con il suo codice |
| `policy.preview_changed` | `POLICY_PREVIEW_CHANGED` | l'anteprima va rifatta |
| `policy.not_live` | `POLICY_NOT_LIVE` | la revoca di una policy che non è più viva |

Un codice per controllo, come la SPEC scriveva (`policy.catalogue`, `policy.scope`…), avrebbe aperto il vocabolario chiuso
del filo per una distinzione che il messaggio già porta; e la console sotto il tetto risponde `not_answerable`, come per una
domanda che non può mostrare.

### 10. La CLI

Un gruppo nuovo, **`ela policy`**. `create` chiede l'anteprima e la stampa; con `--confirm` crea; **in un terminale** — stdin
e stdout — chiede «Create this policy? (s/N)», e crea solo con «s», «si» o «sì»; fuori da un terminale e senza `--confirm`
mostra, non crea, e lo dice. `--limit nome=valore` e `--scope` sono generici e ripetibili: la CLI non conosce i nomi, li
giudica la rotta, e `ela policy list` li elenca. `revoke` prende l'id intero o gli otto caratteri dell'id breve, quando una
policy sola comincia così.

| Comando | Rotta | Uscite |
|---|---|---|
| `ela policy create` | `POST /policies/preview` | `0` `1` `2` `3` |
| `ela policy create` | `POST /policies` | `0` `1` `2` `3` |
| `ela policy list` | `GET /policies` | `0` `1` `2` `3` |
| `ela policy revoke` | `GET /policies` | `0` `1` `2` `3` |
| `ela policy revoke` | `POST /policies/{policy_id}/revoke` | `0` `1` `2` `3` |

`ela task show` stampa, per uno step coperto, la riga `policy` con l'id breve: `StepOut.policy` lo legge la rotta del task
dai risultati e dallo store, senza comporlo, e un grant che non c'è più dà `None`.

### 11. La console

Una vista nuova, **`/console/policies`**, la quinta, raggiunta da `CONSOLE` con il suo cookie e con il controllo d'origine
di ogni `POST` sotto il prefisso, senza JavaScript; le pagine chiamano le funzioni delle rotte (regola 55):

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/console/policies` | l'elenco, e il modulo di creazione derivato dal catalogo e dalla dichiarazione |
| `POST` | `/console/policies/preview` | la pagina dell'anteprima, con «Crea» |
| `POST` | `/console/policies` | la creazione, e di nuovo l'elenco |
| `POST` | `/console/policies/revoke` | la revoca, con l'id nel modulo |

**Il tetto di una policy.** Una policy non ha un task, quindi non ha un livello: **i suoi siti sono contenuto
`LOCAL_ONLY`**. Li vede una console il cui tetto è `LOCAL_ONLY`; sotto un tetto più stretto l'elenco tace i siti e lo dice,
il modulo e l'anteprima non ci sono — l'anteprima è una domanda, e una superficie che non la mostra tutta non crea (ADR 0045
§11) —, e **la revoca resta possibile**: toglie, non allarga. Lo step coperto, nella vista del task, dice «Coperto dalla
policy» con l'id breve. Il telefono ha solo la riga di §8: creare e revocare dal telefono non entrano.

### 12. Che cosa non cambia

- **Una policy toglie la domanda, non l'avvio**: un task lo fa partire ancora Tommaso. ELA che parte da sola è la Fase 15.
- **Il tetto del mese, la prenotazione nella `STARTED`, il gateway, i figli dei gesti e `within`** (ADR 0060 §2–§4): una
  sessione coperta da una policy prenota, pesa e chiude come una approvata con un sì. **Una policy di `browser.guided` non
  copre mai un gesto**: `browser.act` chiede a ogni invio.
- **Un piano scritto dal Planner è coperto come uno scritto a mano**: la policy guarda gli argomenti dello step, non chi li
  ha scritti. Un piano che porta un `task_type` chiede.
- **Un effetto per step**, per una policy con più usi, lo garantiscono l'indice unico dei record `STARTED` e il lock di
  `run` (ADR 0021 §1-bis, ADR 0048), non l'uso singolo di ADR 0046 §3.

### 13. Uno store che non risponde

Uno store delle autorizzazioni che non risponde **ferma la corsa con il suo errore, prima del Guardian e di ogni tool**: la
regola è «mai un'esecuzione» (la decisione 10 della SPEC, corretta dalla review con la 20). Un tetto che non si converte è
una domanda (§4); una dichiarazione illeggibile non esiste a runtime, perché il catalogo la rifiuta alla costruzione.

### 14. Righe riviste

Gli ADR non si riscrivono: queste righe si leggono con questo accanto, e ognuno lo dice nella sua riga «Stato:».

- **ADR 0011 §3 e §14**: `RISK_POLICY` sta in `ela/permissions/rows.py`, che il Guardian riesporta; i valori sono gli
  stessi.
- **ADR 0011 §5**: la validità di un grant conosce la revoca, prima della scadenza.
- **ADR 0011 §6**: per una policy, *copre* e *usabile* sono le due fette del predicato (§4).
- **ADR 0012 §1** e la docstring di `Authorization`: un grant senza `approval_id` scade sempre e porta i suoi tetti; uno con
  `approval_id` non ne ha.
- **ADR 0012 §3 e §5**: `consume` rifiuta un grant revocato nella stessa `UPDATE`, e l'errore nomina la revoca prima della
  scadenza.
- **ADR 0012 §7**: i grant di produzione nascono da due funzioni dello stesso package — `authorization_from_approval` e
  `authorization_from_policy` —, e la regola 15 aggiunge `bounds` ai suoi campi.
- **ADR 0013 §3**: `select_authorization` riceve la specifica e gli argomenti, e «copre» per una policy è il predicato.
- **ADR 0044 §4**: le rotte della console sono quindici, le undici di ADR 0044 e le quattro di §11; **§5**: le viste sono
  cinque.
- **ADR 0045 §3**: il predicato in un posto solo è `asks_at_every_use` per la riga e `shortfall` per una policy.
- **ADR 0060 §1**: «un sì copre una sessione» si legge «un sì, o una policy di Tommaso, copre una sessione». (La frase «una
  policy potrà coprirla», che la registrazione citava, in ADR 0060 non c'è mai stata.)
- La docstring di `ToolRegistryPort`, «the executor is the only caller»: la rotta delle policy chiama `prospect`.

### 15. La prova a mano

La **sezione 27** di `docs/GETTING_STARTED.md`, con `scripts/prova_m13_12.py`, sul Mac, dal codice del branch dopo `uv run
alembic upgrade head`, con i siti di oggi, su Haiku 5.5, con sessioni a 1,10 $: nove passi — la policy si crea con
l'anteprima e la domanda, una sessione dentro parte senza domanda e conta un uso, una sopra un tetto chiede con la riga
«perché te lo chiedo», la revoca, e dopo la revoca la domanda torna con la ragione. La scadenza la prova la suite, con
l'orologio finto; il margine del mese, passo per passo, con la funzione del cancello.

## Alternative considerate

- **Un grant permanente con il solo scope**: coprirebbe una sessione di qualunque costo, durata e modello, per sempre.
- **Abbassare `browser.guided` a `LOW`**: toglierebbe la domanda a tutti, senza confini né fine, e §59 vuole il contrario.
- **Il modello come fatto della chiamata** (la (b) della domanda 16): serve solo con un secondo fornitore sulla rotta; un
  test dice quando.
- **Un codice del filo per ogni controllo della nascita**: il nome del controllo sta già in testa al messaggio (§9).
- **La revoca che ferma una sessione in corso**: il «ferma» c'è già, ed è `ela task cancel`.
- **Un budget totale, un numero massimo di sessioni, una policy che si modifica, i promemoria di scadenza**: non in M13.12.

## Conseguenze

Con questo ADR le regole di architettura sono **sessantasei** (la 66), i contratti di import-linter restano **quindici**,
i port restano **trentatré** (`AuthorizationStore` guadagna `revoke`), le rotte dell'API sono **sessanta** e i comandi
della CLI **trentuno**; le capability restano **quattordici**, le identità del middleware **sei**. Una migrazione, la
`0015`: ELA va migrata (`uv run alembic upgrade head`) prima di ripartire.

Uno store delle autorizzazioni che non risponde ferma la corsa con il suo errore, prima del Guardian e di ogni tool: **mai
un'esecuzione**. Lo prova `tests/executive/test_policy_question.py`, con uno store che solleva e nessun tool chiamato.

Ciò che questo ADR dichiara e non risolve:

- **Gli usi contano le spese, non le sessioni**: una sessione rifiutata dopo la spesa, dal tetto del mese, conta un uso.
- **Una policy nomina un modello solo**: con un secondo fornitore sulla rotta di default il test di §1 fallisce, e la
  scelta fra i termini e la chiamata la fa un ADR.
- **Il tetto di costo è sulla prenotazione**: una sessione prenota il suo costo massimo, e la spesa vera la scrive il libro
  a fine sessione; l'anteprima lo dice.
- **La revoca non ferma una sessione già partita**: l'uscita lo dice, e il «ferma» è quello di sempre.
- **Le altre `MEDIUM` non ammettono una policy**: ognuna la riceve nella milestone che ne ha bisogno, con le sue ragioni.
- **Il terminale può creare una policy**: se `uv` o `ela` stanno fra `ELA_TERMINAL_PROGRAMS`, un `terminal.run` può lanciare
  `ela policy create … --confirm`. La regola 66 è statica su `ela.tools` e non lo vede; lo ferma il livello — `terminal.run`
  è `HIGH`, e la sua domanda mostra il programma e ogni argomento, a ogni uso (ADR 0047).
