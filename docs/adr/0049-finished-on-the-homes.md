# 0049. Un esito finale resta sulle superfici che elencano i task: l'ora dell'esito scritta con lo stato, gli ultimi N, e una domanda che prende un nome

- **Stato:** **Accettata il 2026-09-27**, quando la prova a mano di `docs/GETTING_STARTED.md` §18 è
  passata a `f85b228` — i passi 1–4 e 6, sul Mac e sull'iPhone; il 5 saltato per decisione
  dell'utente, e ciò che doveva mostrare lo affermano i test su un orologio che il test sposta.
  Proposta il 2026-09-26, con la SPEC di M17.2b decisa dall'utente — le decisioni 1–6, tutte (a), e
  le correzioni A e B della sua review.
- **Data:** 2026-09-26
- **Riferimenti spec:** §14, §15
- **Milestone:** M17.2b

## Contesto

La decisione 22 di M17.2 — presa dalla sua prova a mano — ha fatto della tessera dei task della home
un elenco dei task **vivi**, e ADR 0044 §5 l'ha ripetuto: «un task finito e senza domanda resta
raggiungibile solo dal suo id». **La decisione ha funzionato esattamente come era scritta.** Il suo
prezzo l'ha mostrato la prova a mano di M13.2: un comando finito `FAILED` per `terminal.timeout` è
sparito dalla pagina che l'utente stava guardando, l'unico esito che aspettava. La home del telefono
aveva lo stesso filtro, con un rimedio a metà — il task appena risposto, mostrato a parte con
`?task=` — che non copriva un task fermato dal telefono.

Riparare la vista chiedeva una cosa che il sistema non sapeva: **quando** un task è finito. `Task`
aveva `created_at` e basta; l'istante di un passaggio viveva solo nell'evento della trail, e lo stato
e il suo evento sono due scritture — ADR 0015 §8, riga 4: «task DENIED senza evento né audit. Non
riparato.» E `TaskRepository.tasks` dichiara l'ordine d'inserimento, e il suo `limit` tiene i primi,
cioè i più vecchi. Gli stati finali, poi, sono cinque e non i quattro della registrazione: `EXPIRED`
lo produce `recover()` all'avvio, per una domanda scaduta (ADR 0015 §6).

## Decisione

### 1. L'ora dell'esito si scrive con lo stato

`Task.finished_at: UtcDatetime | None`, `None` finché il task è vivo. Lo scrive **solo**
`transition()`, con lo stesso `now` dell'evento, quando `is_terminal(new_state)`, e la `save` che
salva lo stato salva anche lei: due campi, **una scrittura sola**. Da qui in poi un task finito senza
la sua ora non può nascere, e la finestra di ADR 0015 §8 — lo stato salvato, l'evento perso — non fa
più sparire un esito dall'elenco: l'elenco non legge l'evento.

**ADR 0004 §3 si legge con questa accanto**: il task che esce da `transition` non cambia più «solo
`state`» — cambia `state` e, quando lo stato è finale, `finished_at`.

### 2. La regola 5 guarda anche l'ora

`check_state_changes` (regola 5, ADR 0004 §6) segnala, oltre a ciò che segnalava, un
`model_copy(update={… "finished_at": …})` e un `Task(…, finished_at=<non None>)` fuori dalla macchina
degli stati e dal mapper: un'ora d'esito scritta altrove è una fine che nessuno ha raggiunto. I suoi
casi negativi stanno in `tests/architecture/violations.py`, accanto a quelli dello stato. Non è una
regola nuova: è la 5 che si allarga, e il conteggio delle regole non si muove.

### 3. La migrazione `0012`, e l'ora che non si inventa

Aggiunge la colonna, nullable, e la riempie per i task già finiti con il `created_at` dell'ultimo
evento che li ha portati nello stato in cui stanno. **Solo per i cinque stati finali**, scritti per
nome nella migrazione — che non importa codice che cambia dopo di lei, e perché anche un task vivo
ha un evento con il suo stato come `new_state`. Dove quell'evento manca, la colonna resta vuota:
un'ora inventata sarebbe un valore senza fonte. Il `downgrade` toglie la colonna.

Colonne aggiunte:

| Tabella | Colonne |
|---|---|
| `tasks` | `finished_at` |

### 4. Una domanda con un nome

«Gli ultimi N esiti» non è l'ordine di `tasks()`, e un ordine diverso è una domanda diversa — la
frase di `due` (M10.4). `TaskRepository.finished(states, limit)`: i task negli stati chiesti,
`finished_at` decrescente, a parità l'inserimento decrescente, e **un task senza ora in fondo, mai
fuori**. `states` lo passa il chiamante — il port non importa la macchina degli stati —, e `limit` è
obbligatorio: l'unico chiamante ne passa sempre uno. Quanti sono in tutto lo dice `count`, che c'è.
`TERMINAL_STATES` l'engine lo esporta accanto a `LIVE_STATES`, il suo complemento: il contratto 7 di
import-linter tiene `ela.api` lontano dalla macchina degli stati.

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `TaskRepository` | §14 | async | `finished` |

### 5. La rotta, e il suo comando

`GET /tasks/finished?limit=N` risponde gli ultimi N finiti e **quanti sono in tutto**: il totale è
ciò che permette a un elenco che taglia di dire «di 23» senza caricare i 23 (ADR 0025 §2), e a una
home di contare i suoi task senza caricarli. `limit` è obbligatorio. La rotta è **dichiarata prima**
di `GET /tasks/{task_id}`, perché il router prende la prima rotta che combacia e `{task_id}` combacia
con qualunque segmento. `TaskOut` guadagna `finished_at`, e con lui `TaskDetail`. **ADR 0023 §6 si
legge con questa accanto**: la sua tabella delle rotte guadagna la riga qui sotto.

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/tasks/finished` | gli ultimi task arrivati in uno stato finale, l'ultimo per primo, e quanti sono in tutto |

Ogni rotta si raggiunge da un comando (ADR 0024 §2), e questa ha il suo. Il default di `--limit` è
**della CLI**, dieci, scritto come suo: la CLI è un client e non legge le costanti di una pagina.

| Comando | Rotta | Uscite |
|---|---|---|
| `ela task finished` | `GET /tasks/finished` | `0` `1` `2` `3` |

### 6. Le due home: gli ultimi N, uno ciascuno

La tessera «Task» della console resta **una** — la tessera TASKS del §7 del design, che ha i vivi e i
falliti insieme — e ha **due gruppi**: «Vivi», le righe di prima con il loro taglio, e «Finiti · gli
ultimi 8», l'ultimo a finire per primo. La sezione «I task» del telefono ha gli stessi due gruppi, con
6. **N è il `SHOWN` della superficie**, lo stesso per le due liste di una pagina: non è misurato — è
l'unica risposta che la superficie ha dato a «quante righe» —, e un secondo numero sarebbe una
seconda opinione sulla stessa domanda. **Uno ciascuno**, perché con un N condiviso i finiti sarebbero
i primi a cadere quando i vivi sono tanti.

**Il limite si dichiara sempre** nel titolo dei finiti — un elenco degli ultimi N non è mai completo —
e, quando i finiti sono di più, dice di quanti: «gli ultimi 8 di 23». I vivi dicono il loro taglio
solo quando tagliano, come prima: un elenco dei vivi è completo finché non taglia. **Nessuna finestra
di tempo** decide che cosa si vede: il limite è un numero. Ogni gruppo vuoto lo dice. Le home non
caricano più ogni task: i vivi con il filtro degli stati, i finiti e il totale con la rotta nuova.

**Il confine è M17.5, il Task Center** del §9 del design: l'elenco di tutti i task, vivi e finiti,
filtrabile. Oltre gli ultimi N, un task si raggiunge dal suo id.

### 7. Il telefono: la riga senza collegamento, e il rimedio che se ne va

Sul telefono la riga di un finito **non è un collegamento**: il telefono non ha un riassunto, e non
c'è più niente da fermare. Il parametro `task` della home **se ne va**: dopo una risposta, sì o no,
la pagina torna a `/companion/`, e il task risposto è dove la regola generale lo mette — primo fra i
finiti se si è chiuso, fra i vivi se no. **ADR 0043 §5 si legge con questa accanto**: la riga della
sua tabella «`?task=<id>` mostra l'esito di ciò a cui si è appena risposto» non vale più. Il costo è
scritto: un task risposto e ancora vivo sta fra i vivi, con il collegamento per fermarlo come ogni
altro vivo, e oltre il taglio dei sei se i vivi più giovani sono di più.

### 8. L'avvio guarda anche le colonne

`missing_columns`, accanto a `missing_tables`: le colonne mappate delle tabelle che il database ha, e
che il database non ha. L'avvio si ferma nominandole, e nominando `alembic upgrade head` (ADR 0006:
ELA non migra all'avvio). La guida lo prometteva per una tabella e lo faceva; per una colonna la
promessa era falsa dal 2026-09-12 (`0010`), e `0012` sarebbe stata la terza.

### 9. La decisione precedente, riletta

La decisione 22 di M17.2 e la frase di ADR 0044 §5 si leggono con questa accanto: **la tessera dei
task elenca i vivi e gli ultimi finiti**, e un task finito si raggiunge dalla home finché è fra gli
ultimi N. Non era una svista: era una decisione che funzionava come scritta, e il suo prezzo si è
visto solo quando un comando lungo è finito mentre l'utente guardava.

## Alternative considerate

- **L'ordine dell'evento finale nella trail.** Nessuna migrazione, ma lo stato e il suo evento sono
  due scritture, e un task finito nella finestra di ADR 0015 §8 cadrebbe dall'elenco: il difetto in
  una finestra di crash.
- **L'ordine di creazione, dal più recente.** Nessuna migrazione, ma non risponde «gli ultimi esiti»:
  un comando lungo che finisce adesso starebbe sotto i task più giovani e brevi, o fuori — il caso di
  M13.2.
- **Un parametro di `GET /tasks`.** Nessuna rotta nuova, ma due ordini in una rotta che dichiara
  l'ordine d'inserimento, e nessun totale: «N task in tutto» avrebbe continuato a caricare ogni task.
- **Una pagina di riassunto sul telefono.** Una vista nuova, non la riparazione di una vista che
  mente: è di M17.5 o di una milestone sua.

## Conseguenze

- `Task` ha `finished_at`; `transition` lo scrive; la regola 5 lo guarda.
- `TaskRepository` ha `finished`; `ela.tasks.engine` esporta `TERMINAL_STATES`; la migrazione `0012`
  aggiunge `tasks.finished_at`; `ela.infrastructure.persistence` ha `missing_columns`, e l'avvio si
  ferma su una colonna che manca.
- `ela.api.schemas` ha `FinishedOut`, e `TaskOut` ha `finished_at`; `ela.api.tasks` ha
  `finished_tasks`; la CLI ha `ela task finished` e `FINISHED_LIMIT`.
- `ela.api.companion` ha `live_title`, `finished_title`, `NO_LIVE` e `NO_FINISHED`, condivisi con la
  console come `presence`; `ela.api.console` perde `NO_TASKS`. I modelli `group.html` delle due
  superfici danno il titolo di un gruppo.
- Le regole di architettura del registro restano **cinquantasette**, i port **ventotto**; le rotte
  sono **quarantanove** e i comandi **ventisette**. Questi conteggi di oggi vivono qui; gli ADR
  precedenti restano appuntati a ciò che videro, e i loro test tolgono la rotta e il comando di
  questo.
