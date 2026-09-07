# 0027. Le esenzioni senza codice dietro, ritirate; e la tabella che se ne accorge

- **Stato:** Accettata. SPEC di M9.3 approvata dall'utente il 2026-09-07: decisioni **1a** (la
  restrizione generica per tipo), **2b** (il mondo chiuso anche sulle costanti che ogni regola
  legge) e **9a** (questo ADR, che ripete sotto etichetta le righe che cambia). Il prezzo della
  voce `connection` è stato approvato esplicitamente, con la frase che lo motiva: *la porta si
  riapre con un motivo scritto, ed è il punto*.
- **Contesto:** M9.3, il primo quarto della milestone di hardening.
- **Riferimenti spec:** §49, §50, §51, §52
- **Estende:** ADR 0002 (le regole di architettura e come si verificano), ADR 0012 §7 (regola 15),
  ADR 0013 §9 (regola 16), ADR 0017 §9 (regola 21).

## Contesto

La review di M6.2 aveva scritto il principio, e ADR 0017 §9 lo ripete: **«un'esenzione senza
codice che la giustifichi è una porta aperta prima che qualcuno bussi»**. Era un principio, e
nient'altro: nessun test ha mai chiesto, di nessuna esenzione, se qualcuno stesse davvero dietro
di essa.

L'esperimento che ha prodotto M9.1 e M9.3 lo ha chiesto per la prima volta. Il metodo è
banale — si restringe l'esenzione e si rieseguono tutte le regole sull'albero vero — e il
risultato non lo era: **cinque esenzioni su quarantasei non facevano parlare nessuno.**

Il motivo per cui nessuno se n'era accorto è strutturale, non distratto. I casi `ALLOWED` di
`tests/architecture/violations.py` *sintetizzano*, dentro una copia temporanea, il codice che
l'esenzione esiste per permettere, e poi verificano che la regola taccia. Sono ottimi test **della
regola** e sono, per costruzione, incapaci di dire qualcosa **della porta**: una porta con nessuno
dietro supera quei test esattamente come una porta usata ogni giorno.

## Decisione

### 1. Le cinque esenzioni ritirate

Sono le cinque per cui la misura dice che nessuna riga di `src/ela` sta dietro la porta, **e** che
il modulo esentato non è l'attore legittimo della regola (§3).

**Esenzioni ritirate:**

| Regola | Costante | Voce ritirata | Perché nessuno è dietro |
|---|---|---|---|
| 6 `testing-imports` | `TESTING_ALLOWED_INTERNAL` | `ela.testing` | `fakes.py` è un modulo solo: non c'è un secondo modulo dei fake da importare |
| 15 `authorization-builders` | `AUTHORIZATION_BUILDERS_EXEMPT` | `testing` | i fake nominano `Authorization` come tipo e non ne coniano nessuna |
| 16 `tool-execute-callers` | `SQL_EXECUTORS` | `connection` | la persistenza esegue su `session` e su `cursor`, mai su una `connection` |
| 21 `device-port-readers` | `DEVICE_PORT_ALLOWED` | `ela.ports` | la regola guarda gli **import**: `ports.py` *dichiara* `DeviceRegistryPort` e non può importare ciò che definisce |
| 21 `device-port-readers` | `DEVICE_PORT_ALLOWED` | `ela.infrastructure.persistence.device_registry` | l'adapter soddisfa il port **strutturalmente** — è un `Protocol` — e lo nomina solo nei docstring |

Le righe che questa tabella sostituisce, ripetute per intero perché un ADR non si modifica:

**Regole estese:**

| # | Regola | Esenzioni prima (ADR) | Esenzioni ora |
|---|---|---|---|
| 15 | fuori da `ela.permissions` nessuno costruisce o allarga un'`Authorization` | `ela.permissions`, `ela.testing`, e il mapper per percorso esatto (ADR 0012 §7) | `ela.permissions`, e il mapper per percorso esatto |
| 16 | fuori da `executive/executor.py` nessuno chiama `<x>.execute(...)` | il runner per percorso, e i ricevitori `session`, `connection`, `cursor` (ADR 0013 §9) | il runner per percorso, e i ricevitori `session`, `cursor` |
| 21 | fuori da tre moduli nessuno nomina `DeviceRegistryPort` | `ela.ports`, `ela.devices`, l'adapter SQL (ADR 0017 §9) | `ela.devices` |

Una delle cinque non cambia una decisione: `ela.testing` in `TESTING_ALLOWED_INTERNAL` **non è
scritta in nessun ADR**. ADR 0002 documenta la regola 6 come «`ela.testing` importa solo stdlib,
domain e ports», e il codice ci aveva aggiunto sé stesso senza che nessun documento lo dicesse.
Toglierla non ritira una decisione: chiude una divergenza fra doc e codice, ed è il motivo per cui
`test_lint_imports_cannot_forbid_a_package_from_itself` esiste — un contratto `forbidden` non può
dire che un package non importa sé stesso, quindi solo la regola pytest può.

### 2. Il prezzo di `connection`, dichiarato

Chiudere `SQL_EXECUTORS['connection']` ha un costo reale e non nullo: **il giorno in cui la
persistenza eseguirà su una `connection`, la regola 16 parlerà.** Segnalerà `connection.execute(…)`
come «qualcuno che non è l'executor esegue un tool», che è un falso positivo.

È voluto. Quel giorno la riapertura è **una riga più una motivazione** — la voce torna nella
costante, il caso `sql-executed-on-a-connection` torna da `VIOLATIONS` ad `ALLOWED`, e questo ADR
ne prende uno successivo — **non un incidente**. La differenza fra le due cose è tutto il valore
della decisione: una porta ereditata non ha un motivo, e nessuno sa più se ce l'aveva.

### 3. Il criterio: l'attore legittimo

Non tutte le esenzioni silenziose vanno tolte, e questa è la riga che divide.

> **Un'esenzione si toglie quando il modulo esentato non è l'attore legittimo della regola; resta
> quando lo è.**

`ela.testing` non conia grant, `ela.ports` non importa il port che dichiara, la persistenza non ha
una `connection`: nessuno di quei moduli è *l'attore* della sua regola, sono moduli a cui era stato
concesso il permesso per comodità o per anticipo. Togliere il permesso non cambia ciò che la regola
dice.

L'attore legittimo è un'altra cosa. Il passaggio sulle 116 coppie (§4) ha trovato una **sesta**
porta silenziosa che l'esperimento di M9.1 non aveva vista, perché quell'esperimento restringeva
solo le costanti che qualcuno aveva già riconosciuto come esenzioni: **`TASKS_DIR` per la
regola 11** (`step-event-writers`, ADR 0009). Ristretta, la regola riporta zero violazioni.

**Non va chiusa.** Il silenzio non dice che nessuno usa la porta: dice che l'euristica non lo vede.
L'engine costruisce i suoi eventi con `event_type=op.event_type`, un attributo che arriva da
`STEP_OPERATIONS`, e `_is_step_event` riconosce solo un attributo il cui nome inizia per `STEP_` o
una stringa letterale — limite già dichiarato nel docstring della regola («a heuristic on names,
like rule 5: it catches the obvious bypass, the review catches the rest»). E `ela.tasks` **è**
l'attore della regola 11: il Task Engine è *il* scrittore degli eventi di step. Togliere
`TASKS_DIR` non chiuderebbe una porta di servizio: cambierebbe ciò che la regola dice, da «solo
`ela.tasks` può» a «nessuno può», e trasformerebbe lo scrittore legittimo in un imputato il giorno
in cui scriverà l'evento nel modo ovvio.

Quella riga resta quindi un'esenzione, e la sua prova non è l'albero vero ma il caso sintetico che
`violations.py` già contiene, `step-event-built-by-engine`, che la riga **nomina**. La regola
generale che ne esce: **un'esenzione è provata dall'albero vero oppure da un caso `ALLOWED` che la
riga nomina, mai da niente.** È l'unica delle trentasei che ha bisogno del ripiego.

### 4. La tabella delle costanti, e le due asserzioni opposte

`CONSTANTS` in `tests/architecture/rules.py` ha **una riga per ogni coppia (regola, costante) che
le regole leggono davvero**: 116 coppie, 76 costanti distinte. Le coppie non sono elencate a mano —
`tests/architecture/test_exemptions.py` le ricava dall'**AST** di `rules.py`, seguendo anche gli
helper che una regola chiama, e pretende che l'insieme derivato sia **esattamente** l'insieme delle
righe. Aggiungere una costante a una regola esistente fa fallire la suite finché qualcuno non la
classifica.

Tre classi, e le prime due hanno asserzioni **opposte**:

| Classe | Che cos'è | Che cosa il test pretende |
|---|---|---|
| `EXEMPTION` | una porta: chi è esentato dalla regola | ristretta, la sua regola riporta **almeno una** violazione |
| `DETECTOR` | ciò che la regola cerca o guarda: una libreria, un nome di metodo, un campo, un file | ristretto per intero, la sua regola riporta **zero** violazioni: un rivelatore può solo far tacere |
| `SUBJECT` | ciò senza cui la regola non ha soggetto | nessuna asserzione, **e la riga porta il motivo scritto** |

L'opposizione è ciò che rende la tabella verificabile invece che dichiarativa: **classificare una
porta viva come rivelatore fallisce**, perché restringerla fa parlare la regola. `COMPOSED_NAMES`
(regola 28) è il caso che ha reso necessarie tre classi invece di due: ristretta non fa parlare
nessuno e **non** è un'esenzione morta — è l'elenco di ciò che la regola cerca.

La restrizione è generica per tipo (decisione 1a): da un contenitore di alternative si toglie un
elemento alla volta, uno scalare `Path` diventa un percorso che non esiste, una stringa un nome che
nessuno ha, un insieme grande l'insieme vuoto, un `re.Pattern` un pattern che non matcha. **Gli
elementi non sono scritti nella tabella: si leggono dalla costante**, così una voce aggiunta a una
allowlist esistente è coperta senza che nessuno debba ricordarsi di aggiungerla due volte.

Ogni riga `EXEMPTION` porta l'ADR che ha aperto la porta, o `—` se nessun ADR la documenta. **Non
se ne inventa uno**: una porta senza ADR è un fatto da registrare, e il posto dove registrarla è
l'elenco di ciò che v0.1 semplifica (M9.4).

### 5. Che cosa questo non copre

Tre cose, tutte scritte perché una lacuna dichiarata è una lacuna che qualcuno può chiudere:

1. **Le righe `SUBJECT`** — `ROOT_PACKAGE` (letta da tutte e 31 le regole), `SECURITY_MODULE` e
   `CLI_DIR`. Sono le costanti che restringere non significa niente: `ROOT_PACKAGE` toglie il
   soggetto invece di aprire o chiudere una porta, `SECURITY_MODULE` è l'unico file che la
   regola 31 legge e ristretto la fa sollevare invece che parlare, `CLI_DIR` è il package di cui
   la regola 28 parla su entrambi i lati. Non sono asserite, portano il motivo, e sono il solo
   posto dove una porta potrebbe ancora nascondersi.
2. **La riga `TASKS_DIR` della regola 11**, provata da un caso sintetico e non dall'albero vero
   (§3).
3. **Il mondo chiuso è sulle costanti che una regola *legge*.** Una regola che aprisse una porta
   con un valore scritto in linea, senza costante, non comparirebbe nella tabella. È una perdita
   più piccola di quella che questo ADR chiude, e ha un presidio debole ma reale: nessuna delle 31
   regole di oggi scrive un'esenzione in linea, e la review lo vedrebbe.

## Alternative considerate

- **Mondo chiuso solo sulle regole** — ogni regola nella tabella con le sue esenzioni o con un
  marcatore `NO_EXEMPTIONS`, ~31 righe invece di 116. Costa molto meno e lascia in piedi
  esattamente la forma che questo ADR esiste per togliere, un livello più in basso: una costante di
  allowlist nuova dentro una regola *esistente* sfuggirebbe in silenzio. Scartata (decisione 2b).
- **Normalizzare tutte le esenzioni in contenitori** (`EXECUTE_CALLERS = (EXECUTOR_MODULE,
  RUNNER_MODULE)`, …) per avere una restrizione uniforme — uniforme e più leggibile, ma è la
  riscrittura di una dozzina di costanti dentro una milestone che non doveva toccare le regole, e
  la restrizione generica per tipo funziona su tutte e quarantasei le voci. Scartata (decisione 1a).
- **Ogni riga dichiara il proprio valore ristretto** invece di ricavarlo dal tipo — più esplicito,
  molto più verboso, e una riga può mentire in un modo che la restrizione generica non permette.
  Scartata (decisione 1a).
- **Togliere anche `TASKS_DIR` dalla regola 11**, per coerenza con le cinque — cambierebbe ciò che
  la regola dice e metterebbe sotto accusa lo scrittore legittimo. Scartata (§3).
- **Modificare ADR 0012, 0013 e 0017 invece di scriverne uno nuovo** — rompe l'immutabilità degli
  ADR, che è una convenzione dichiarata e verificata dai doc-test. Scartata (decisione 9a).
- **Lasciare le cinque esenzioni e limitarsi alla tabella** — la tabella fallirebbe su tutte e
  cinque il giorno stesso in cui esiste: o si tolgono, o il gate nasce rosso. Scartata.
- **Una quarta classe `VACUOUS`**, per una porta silenziosa che non si vuole chiudere — sarebbe la
  scappatoia scritta a mano che tutto questo esiste per togliere. La riga della regola 11 nomina
  invece un caso `ALLOWED` esistente, che è una prova, non una dichiarazione. Scartata.

## Conseguenze

- **`tests/architecture/rules.py`**: cinque voci in meno in quattro costanti; `EXEMPTION`,
  `DETECTOR`, `SUBJECT`, `WHOLE`, `EACH`, la dataclass `Constant` e la tabella `CONSTANTS`, una
  riga per coppia — alla stesura 116 righe: 36 porte, 47 rivelatori, 33 soggetti, di cui 31
  `ROOT_PACKAGE`. I numeri crescono con le regole; a essere fisso è che la tabella e l'AST
  coincidano.
- **`tests/architecture/test_exemptions.py`**: il mondo chiuso derivato dall'AST, le due
  asserzioni opposte, il caso negativo di una costante nuova non classificata, e i cinque casi
  negativi che rimettono ognuna delle porte ritirate e mostrano che il gate le vedrebbe.
- **`tests/architecture/violations.py`**: tre casi passano da `ALLOWED` a `VIOLATIONS` — il fake
  che conia un grant, `ela.testing` che importa sé stesso (in due forme, assoluta e relativa),
  `connection.execute`.
- **`tests/architecture/test_import_linter.py`**: il contratto della regola 6 non può nominare
  `ela.testing` fra i moduli vietati a `ela.testing`, e il test che lo documenta è il secondo caso
  di ciò che import-linter non sa esprimere.
- **Nessuna riga di `src/ela` cambia.** Questo ADR non tocca il codice di produzione: cambia ciò
  che i test sono disposti a lasciar passare.
- **Il principio della review di M6.2 diventa un fatto verificato.** Da qui in avanti un'esenzione
  nuova nasce con qualcuno dietro, o la suite è rossa; e una che perde il suo ultimo utente lo dice
  il giorno in cui lo perde, non dopo tre milestone.

### Vincoli dichiarati, da riaprire quando serviranno

- **Le tre costanti `SUBJECT` non sono asserite** (§5, punto 1). Portano il motivo scritto, e sono
  l'unico posto della tabella dove una porta potrebbe nascondersi.
- **La regola 11 è provata da un caso sintetico** (§5, punto 2). Il giorno in cui l'euristica di
  `_is_step_event` seguirà anche un `event_type` che arriva da una variabile, quella riga si
  proverà sull'albero vero come tutte le altre.
- **Una porta scritta in linea, senza costante, sfuggirebbe** (§5, punto 3).
- **La riapertura di `connection`** (§2): prevista, con la sua forma — una riga più una
  motivazione, e un ADR che ripete la riga.
