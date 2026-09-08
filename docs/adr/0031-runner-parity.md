# 0031. La copertura non dipende dal runner: una scelta di piattaforma è un'istruzione, non un'espressione

- **Stato:** Accettata. Correzione della CI di `main` dopo il merge di M10.3, quattro decisioni.
  Le due che cambiano il modo in cui ELA si verifica sono §3 (il criterio del gate acquista la sua
  seconda metà) e §4 (la regola 37, che la rende vera invece che promessa).
- **Data:** 2026-09-08
- **Contesto:** la build di `main` verde su macOS e rossa su ubuntu per **una riga**, senza che
  nessun test fallisse.
- **Riferimenti spec:** §49, §51, §52
- **Estende:** ADR 0002 (una regola nuova, la 37), ADR 0028 §1 (il criterio che decide chi entra
  nel gate: qui acquista la clausola che gli mancava).

## Contesto

Dopo il merge di M10.3 la CI di `main` diceva due cose diverse sulla stessa riga di storia:
**4526 passed, 14 skipped** su entrambi i runner, nessun test fallito da nessuna parte, e
`cov-critical` verde su macOS e rosso su ubuntu. Mancava una riga sola:

```
src/ela/tools/settings.py   47   1   0   0   98%   171
```

La 171 è il corpo di `CaptureSettings.ocr_timeout`: `return timedelta(seconds=self.ocr_timeout_seconds)`.
Una riga **pura** — nessun I/O, nessun `platform`, nessuna dipendenza dal sistema — in un package
che il gate copre per intero. Non è una riga che su Linux *non può* girare: è una riga che su
Linux **nessuno chiama**.

Il suo unico chiamante in tutto il repo era il composition root:

```python
recognition = (
    VisionTextRecognition(timeout=settings.captures.ocr_timeout)
    if darwin
    else UnsupportedTextRecognition()
)
```

I due fratelli della property — `capture_timeout` e `probe_timeout` — hanno da sempre un test
proprio, e per questo non erano mai emersi. `ocr_timeout` no: su un Mac era coperta **per
rimbalzo**, dal ramo Darwin del composition root, e la milestone che l'ha scritta è stata scritta
su un Mac.

Questo ADR esiste perché la riga è l'ultima cosa interessante della vicenda. Quello che conta è
che il gate al 100% branch — lo strumento con cui ELA dimostra che nessuna decisione resta non
provata — **non vede** una scelta scritta in quella forma, e la Fase 12, con i nodi Windows e
macOS, moltiplicherà proprio quel tipo di scelta.

## 1. La misura: un'espressione condizionale non è un ramo

Non è un'opinione sullo stile. È una proprietà dello strumento, e si misura in dodici righe:

```python
def darwin_side(): ...  # riga 2:  return "mac"
def other_side(): ...


def pick(darwin):  # righe 10-14: la forma a ESPRESSIONE
    chosen = darwin_side() if darwin else other_side()
    return chosen


def pick_statement(darwin):  # righe 19-23: la forma a ISTRUZIONE
    if darwin:
        chosen = darwin_side()  # riga 20
    else:
        chosen = other_side()
    return chosen
```

Chiamando **solo** `pick(False)` e `pick_statement(False)` — cioè esercitando entrambe le forme
in una sola direzione, che è ciò che fa un runner Linux — `pytest --cov --cov-branch` risponde:

```
Name      Stmts   Miss   Branch   BrPart   Cover   Missing
tern.py      12      2        2        1     79%   2, 20
```

Si legge così:

| | righe mancanti | archi parziali | cosa vede il gate |
|---|---|---|---|
| `pick`, a espressione (righe 10-14) | **nessuna** | **nessuno** | niente |
| `pick_statement`, a istruzione (righe 19-23) | la 20 | l'`if` della 19 | il ramo non preso |

`Branch` vale **2**: gli unici due archi misurabili del file sono quelli dell'`if`. Un'espressione
condizionale è una singola istruzione, il lato che non viene valutato non produce né riga scoperta
né arco scoperto, e il gate al 100% branch le passa sopra senza aprire bocca.

La riga 2 — il corpo di `darwin_side`, che nessuna delle due forme ha chiamato — è **l'unica
traccia** che la scelta lascia: una funzione pura, in un altro punto del file, che non ha niente a
che vedere con la piattaforma. In ELA quella riga si chiamava `src/ela/tools/settings.py:171`.

> **Una scelta invisibile al gate affiora un frame più in basso, in un package diverso, su una
> riga che con la piattaforma non c'entra niente — e solo sul runner che non la prende.**

## 2. Perché il criterio di ADR 0028 §1 non l'ha intercettata

ADR 0028 §1 dice:

> Un package entra in `cov-critical` quando ogni suo ramo può essere eseguito in CI. Dove questo è
> falso, il package non deve contenere nessun ramo che decida qualcosa.

Applicato a questo caso non scatta, e **correttamente**, tre volte:

1. `ela.tools` è a norma: la 171 non è un ramo e gira ovunque.
2. `ela.infrastructure.perception` è a norma: sta fuori dal gate proprio perché i suoi rami
   dipendono dall'hardware, ed è la regola 34 a impedirgli di decidere.
3. `ela.composition` è a norma: contiene il ramo di piattaforma, ma scritto in una forma che il
   gate non vede — quindi la domanda «questo ramo può essere eseguito in CI?» non viene mai posta
   a nessuno.

Il buco non è un package classificato male. È che **§1 è un criterio su quali package entrano nel
gate, e non dice niente su cosa il gate debba dimostrare allo stesso modo ovunque.** Finché lo si
gira su una macchina sola, quella clausola mancante è invisibile: la 171 risulta coperta, e non da
un test che la riguarda.

## 3. Il criterio, con la seconda metà

> Un package entra in `cov-critical` quando ogni suo ramo può essere eseguito in CI. Dove questo è
> falso, il package non deve contenere nessun ramo che decida qualcosa. **E il risultato del gate
> non dipende dal runner: una scelta di piattaforma è un'istruzione e non un'espressione, e si
> prova in entrambe le direzioni nominando il sistema, mai essendolo.**

Due corollari, che valgono oltre questo caso:

- **Una riga coperta da chi passa di lì non è coperta.** La copertura incidentale — quella che
  arriva perché qualcun altro, per la strada, ti ha chiamato — dice che la riga è raggiungibile,
  non che è giusta. `ocr_timeout` non si esenta e non si sposta: è pura, resta nel gate, e ciò che
  mancava era la sua prova.
- **Un test che chiede alla macchina cosa aspettarsi verifica metà su ognuna** e non fallisce su
  nessuna. Vale per `platform.system()` come per `os.name`, e §6 elenca i tre che ELA aveva.

## 4. La regola 37, perché il criterio non resti una promessa

`Regole aggiunte:`

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 37 `platform-choice-is-a-statement` | nessuna espressione condizionale ha per condizione una domanda su *che macchina è questa* | tutto `src/ela` | nessuna esenzione |

Tre scelte dentro la regola, e ognuna ha una ragione:

- **Su tutto `src/ela`, non solo su `ela.composition`.** Oggi la scelta sta nel composition root
  perché la regola 27 la vuole lì; la prossima la scriverà chi cabla un nodo Windows, e la
  scriverà altrove. Una regola che nomina il punto in cui il problema è già stato trovato è una
  regola che non trova mai il secondo.
- **Legge la condizione, non i rami.** `platform.system() if given is None else given` — che è
  quello che `ela.devices.local` scrive davvero — non è una scelta di piattaforma: è un default, e
  ogni runner lo prende in entrambe le direzioni. Una regola che lo vietasse sarebbe una regola
  contro i ternari, che è un'altra cosa e non ne vale la pena.
- **Riconosce le parole intere.** `nt` è una parola in `os.name != "nt"` e una coincidenza dentro
  `count`: la condizione viene letta come AST — identificatori, attributi, costanti di stringa — e
  mai come testo.

Il caso negativo è quello che CLAUDE.md chiede a ogni controllo di `make check`: due moduli
sintetici in `violations.py` la fanno parlare (uno nel composition root, uno in un tool, perché il
prossimo sarà altrove) e due la obbligano a stare zitta — la stessa scelta scritta come `if`, e il
default che *contiene* una parola di piattaforma senza *chiedere* niente sulla piattaforma.

Verificata anche all'indietro, sull'albero da cui questo ADR nasce: sul `root.py` del commit di
M10.3 la regola riporta tre violazioni, una per ternario.

## 5. Il ramo, nel composition root

I tre ternari diventano un `if`, e uno solo — la domanda è una: *questa macchina è un Mac?*

```python
darwin = platform.system() == "Darwin"
probe: PerceptionProbe
screen: ScreenCapturePort
recognition: TextRecognitionPort
if darwin:
    probe = DarwinProbe(timeout=settings.perception.probe_timeout)
    screen = ScreenCaptureCommand(timeout=settings.captures.capture_timeout)
    recognition = VisionTextRecognition(timeout=settings.captures.ocr_timeout)
else:
    probe = UnsupportedProbe()
    screen = UnsupportedScreenCapture()
    recognition = UnsupportedTextRecognition()
```

Da qui in poi il gate misura due archi e **pretende** che qualcuno provi entrambi, su ogni runner.
Il test che li prova nomina il sistema invece di essere quel sistema, e può farlo perché i tre
adapter Darwin, alla costruzione, memorizzano un timeout e uno spawn e nient'altro: nessun figlio
parte finché nessuno li chiama. È la stessa forma di `overdue(granted, measured)` di M10.2 — la
parte che decide separata da ciò che il mondo risponde — applicata un livello più in alto, dove in
M10.3 non era stata applicata.

## 6. I test che si adattano al runner: la famiglia

Cercati in tutta la suite (`platform.system()`, `sys.platform`, `os.name`), ne sono emersi tre.
Sono la stessa forma dei test a tempo di M9.1: verificano metà su ogni macchina e non falliscono
su nessuna.

| Test | Come si adattava | Cosa fa adesso |
|---|---|---|
| `tests/composition/test_perception.py` | `expected = DarwinProbe if platform.system() == "Darwin" else UnsupportedProbe` | due casi con un nome, `Darwin` e `Linux`, e ogni runner li esegue entrambi — sui tre adapter, non solo sulla sonda |
| `tests/devices/test_local.py` | `assert local_device(...).os is SYSTEMS[platform.system()]` | una voce per ogni sistema di `SYSTEMS`, nominata |
| `tests/infrastructure/persistence/test_engine.py` | `if os.name != "nt": assert ...` dentro il test | due test, e su Windows il secondo è uno **skip dichiarato** |

La differenza fra un `if` dentro il test e uno `skipif` sopra il test è tutta qui: il primo passa
in silenzio senza asserire niente, il secondo compare nel riepilogo come «skipped» e dice quale
metà è stata eseguita. I tre smoke test di `tests/infrastructure/perception/` restano
`skipif(platform.system() != "Darwin")` e va bene così: chiedono una macchina vera, lo dicono, e
sono fuori dal gate perché ADR 0028 §1 li tiene fuori.

## Alternative considerate

- **`# pragma: no cover` sulla 171.** Scartata per la ragione di ADR 0028 §1: produce una
  copertura che non dimostra niente, e per giunta su una riga che si può eseguire ovunque.
- **Togliere `ela.tools` dal gate**, o esentarne il modulo delle settings. Scartata: il criterio è
  che una riga che non può essere eseguita ovunque non sta in un package sotto gate — questa può,
  quindi ci sta, e ciò che manca è il test.
- **Girare `cov-critical` su un runner solo.** Renderebbe la CI d'accordo con se stessa e cieca:
  è esattamente la condizione in cui il buco è stato scritto.
- **Estrarre la scelta in una funzione pura `select_backends(darwin: bool)`** e provarla con
  entrambi i valori — la forma di `overdue()` alla lettera. Scartata perché l'`if` più i due casi
  danno la stessa prova, imposta dallo stesso gate, senza un livello di indirezione in più; e
  perché la regola 37 vale ovunque, mentre una funzione vale dove qualcuno si ricorda di usarla.
- **Lasciarlo alla review.** È ciò che è successo: la review ha letto tre ternari corretti, perché
  singolarmente lo sono. Ciò che non si vede leggendo è che il gate non li stava misurando.

## Conseguenze

- Le regole di architettura passano da trentasei a **trentasette**, e i contratti di import-linter
  restano **tredici**: la 37 guarda un'espressione, non un import.
- I port restano **ventuno**, le capability di produzione **cinque**, quelle di v0.1 **tre**, le
  famiglie di percezione **quattro**. Nessuna superficie cambia: cambia ciò che il gate dimostra.
- `cov-critical` dà lo stesso risultato su macOS e su Linux, e la prossima volta che non lo darà
  sarà per un ramo che qualcuno può vedere.
- `ela.tools.settings` è coperto al 100% **dai test di `ela.tools`**, senza il composition root.
- Fase 12 parte con la regola già in piedi: ogni nodo nuovo moltiplica le scelte di piattaforma, e
  la prima scritta come espressione non compila la CI invece di passare per anni.

### Vincoli dichiarati, da riaprire quando serviranno

- **Il risultato del gate non dipende dal runner** (§3). Criterio generale.
- **Una riga coperta da chi passa di lì non è coperta** (§3). Criterio generale.
- **Un test che chiede alla macchina cosa aspettarsi verifica metà su ognuna** (§3, §6). Criterio
  generale, gemello del criterio sui test a tempo di M9.1.
- **Uno skip dichiarato è visibile, un `if` dentro un test no** (§6).
