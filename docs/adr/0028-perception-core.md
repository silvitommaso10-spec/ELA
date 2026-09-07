# 0028. Il primo contatto con l'hardware: la sonda isolata, lo stato con la sua causa, e il criterio dell'audit

- **Stato:** Accettata. SPEC di M10.1 approvata dall'utente, undici decisioni. Le quattro che
  cambiano la forma di ciò che ELA dice di sapere sono §3 (lo stato non viaggia mai da solo), §4
  (una causa che non può scattare non entra), §9 (nessuna capability finché non si legge
  contenuto) e §10 (l'audit registra ciò che ELA decide, non ciò che il mondo fa).
- **Contesto:** M10.1, la prima milestone che tocca l'hardware del Mac.
- **Riferimenti spec:** §10, §11, §33, §45, §51, §52, §57
- **Estende:** ADR 0002 (le regole di architettura: tre nuove, 32, 33, 34), ADR 0005 (un port
  nuovo), ADR 0023 (una rotta e una riga di `/diagnostics`), ADR 0024 (un comando), ADR 0026 §10
  (il criterio «chi sceglie scrive» esteso dall'osservare).

## Contesto

§10 descrive un anello: *local detection → rilevazione di cambiamenti → analisi solo quando
necessario*. M10.1 costruisce il primo terzo e niente del resto: ELA guarda la macchina su cui
gira, nomina ciò che vede col vocabolario di §11, e si accorge di cosa è cambiato. Non analizza,
non legge contenuto, non manda niente a nessuno.

La difficoltà non è nessuna di queste. È che **su un runner di CI non c'è niente da osservare, e
su Linux non esiste nemmeno la domanda.** Una milestone che tocca l'hardware o è progettata perché
l'assenza di hardware sia un caso di prima classe — testabile, dichiarato, distinguibile da un
guasto — oppure ha un buco che nessun test può vedere.

Prima di decidere è stata fatta una ricognizione, misurata su un Mac (Darwin 25.6.0) da un
processo **senza alcun grant TCC**, che è lo scenario «permesso mancante» e non un caso limite.
Tre risultati hanno deciso più delle opinioni:

| Lettura | Permesso | Costo |
|---|---|---|
| Elenco fotocamere e microfoni (AVFoundation) | nessuno | 75 ms a freddo, poi in cache |
| **Microfono in uso da chiunque** (`kAudioDevicePropertyDeviceIsRunningSomewhere`) | nessuno | **0,03 ms** |
| Stato TCC di camera e microfono (`authorizationStatusForMediaType:`) | nessuno, e **non chiede** | 3,2 ms |
| Screen Recording (`CGPreflightScreenCaptureAccess`), schermi, blocco, inattività | nessuno | ~1 ms |
| **Webcam in uso da chiunque** | — | **non esiste** |

1. **Interrogare un permesso non è mai chiedere un permesso.** Ogni query di stato risponde senza
   mostrare niente all'utente. «Permesso mancante» è quindi una domanda con risposta, non un
   fallimento da intercettare — ed è ciò che rende il requisito realizzabile invece che simulato.
2. **Un processo che non è un'app non può ottenere il permesso chiedendolo.** Il Core gira sotto
   l'identità TCC del processo responsabile; da un daemon senza sessione GUI nessun prompt può
   comparire. Il permesso lo concede l'utente in Impostazioni di Sistema, o non arriva. L'unica
   cosa corretta che ELA può fare è dirlo con precisione.
3. **Un errore in `objc_msgSend` via `ctypes` uccide il processo.** Verificato: argomento
   sbagliato → `NSInvalidArgumentException` → `libc++abi: terminating`. Non un traceback: la fine
   di ELA.

## 1. La superficie iniettabile, e quali righe sono esenti dal gate

Il gate `cov-critical` chiede il 100% branch e nessun runner può eseguire un ramo che dipende da
una webcam. Le due uscite facili — un `# pragma: no cover`, o un mock di `ctypes` che asserisce di
aver chiamato `ctypes` — producono una copertura che non dimostra niente. Nessuna delle due entra.

La forma scelta sposta il problema invece di aggirarlo: **fuori dal processo di ELA escono
primitive, non decisioni.**

```
        ela.perception  (puro, nel gate, 100% branch)
        ▲   interpret(): primitive → stati di §11; fingerprint(); detect(); merge()
        │
        │   RawObservation:  int | None, bool | None, float | None
        │   (None = non letto — l'unico modo in cui l'assenza si esprime)
        ▲
        ela.infrastructure.perception  (adapter, fuori dal gate)
        │
        ├── darwin.py    spawn iniettato → parse, timeout, JSON rotto: tutti testabili
        └── probe.py     IL FIGLIO: solo stdlib, solo ctypes, stampa JSON
```

Il criterio, scritto perché valga anche per il prossimo che lo legge:

> **Un package entra in `cov-critical` quando ogni suo ramo può essere eseguito in CI. Dove questo
> è falso, il package non deve contenere nessun ramo che decida qualcosa.**

`ela.perception` entra nel gate in questa milestone. `ela.infrastructure.perception` no — e non
perché sia infrastruttura: `ela.infrastructure.persistence` è nel gate, e ci sta perché SQLite gira
ovunque. Ci sta fuori perché i suoi rami dipendono da hardware che il runner non ha.

E la promessa «l'adapter non decide niente» non resta una promessa: la fa rispettare la **regola
34**, che vieta a `ela.infrastructure.perception` di nominare `SensorState`, `SensorCause` o
`PermissionState`, sia importandoli sia raggiungendoli per attributo. *Un adapter che non conosce
le parole non può usarle male*, ed è questo che rende l'esenzione onesta invece che dichiarata.

**Cosa resta non eseguibile su un runner: un file, `probe.py`.** E anche quello non è non
verificato:

- `darwin.py` riceve lo spawn come dipendenza. Timeout, figlio morto, JSON malformato, chiave
  sconosciuta: tutti si producono con uno spawn finto, senza hardware, al 100%.
- `spawn` è `asyncio` e basta — non sa niente di macOS — quindi gira su **ogni** runner, Ubuntu
  compreso, lanciando un comando Python banale.
- `probe.py` **viene eseguito in CI su macOS**, e il test asserisce il contratto e non i valori:
  esce 0, stampa JSON, ogni chiave è nota. Non può dire che la webcam c'è; dice che la sonda è
  viva, che le firme `ctypes` sono giuste, e che non è morta di eccezione.

## 2. Il sottoprocesso isolato, e perché non pyobjc

Tre strade, misurate invece che immaginate. Il criterio: nessuna lettura di percezione può
uccidere il processo di ELA.

| | il criterio | costo | dipendenze |
|---|---|---|---|
| Solo API C (`ctypes`) | rispettato — le funzioni C tornano codici d'errore | ~1 ms | nessuna |
| pyobjc | **rispettato, verificato**: `NSInvalidArgumentException` → `ValueError` | 3,4 ms | pyobjc, solo macOS |
| Sottoprocesso isolato | **rispettato, verificato**: figlio `SIGABRT` (rc −6), padre vivo | 35 ms | nessuna |

**Solo API C non basta**, e questo decide più di ogni altra cosa: lo stato TCC di microfono e
webcam — il cuore del requisito «permesso mancante di prima classe» — non ha API C pubblica.
Esiste solo come messaggio Objective-C.

Fra le due che restano, **il sottoprocesso**, per tre ragioni in ordine di peso:

1. **pyobjc garantisce la cosa sbagliata delle tre.** Converte le eccezioni Objective-C — provato,
   funziona — ma non copre un blocco e non copre un crash dentro un framework. E la lettura più
   preziosa, lo stato TCC, è una chiamata XPC a `tccd`: un demone che può non rispondere è
   esattamente la cosa che si pianta, e un'eccezione convertita non serve a niente quando il
   problema è che la risposta non arriva. Un sottoprocesso con timeout copre tutti e tre i modi di
   fallire con un meccanismo solo.
2. **Il fallimento atterra su un valore che il dominio ha già.** Sonda scaduta, sonda morta, sonda
   che stampa spazzatura: tutte e tre diventano `NOT_OBSERVABLE` (§3), che è già il valore giusto
   e già coperto. Non serve inventare un modo di fallire — ce n'è uno e ha un nome.
3. **`ela` resta senza dipendenze nuove.** Nessun marker di piattaforma in `pyproject.toml`,
   nessun `uv.lock` che diverge fra i due runner di CI.

**Il costo architetturale, dichiarato:** un secondo eseguibile dentro `src/ela`, un formato di
serializzazione, un timeout, e 35 ms per osservazione invece di 3. Il fail-safe di §33 viene prima
della velocità, e 35 ms su una cadenza di secondi è rumore.

La **regola 33** tiene il figlio con le sole importazioni della standard library: ciò che deve
poter morire da solo non deve portarsi dietro il grafo di import del Core, e il Core non deve avere
una strada dentro l'unico modulo che nessun runner copre. Le due parti si accordano su un oggetto
JSON e su nient'altro.

E la **regola 32** tiene `ctypes` e l'avvio di processi dentro quel package soltanto: prima di
M10.1 `ela` non usava né l'uno né l'altro in nessun punto, e «ELA tocca la macchina in un posto
solo» è un fatto che si controlla invece di una promessa. La regola legge **due grafie**, e la
seconda è la lezione: `import subprocess` si vede come import, ma
`asyncio.create_subprocess_exec(...)` — la grafia che questa milestone usa davvero — si vede solo
come chiamata. Una regola che leggesse i soli import sarebbe stata muta proprio sul codice che
esiste, cioè una difesa che sembra attiva e non può scattare.

## 3. Tre stati, e la causa accanto

`SensorState` è quello di §11 — `OFF`, `AVAILABLE`, `ACTIVE` — e `ACTIVE` significa **«il
dispositivo è in uso da qualcuno»**, non «ELA sta catturando»: §11 esiste perché l'utente sappia se
la sua webcam è accesa, non per descrivere ELA. Accanto viaggia `SensorCause`, e i due non si
separano mai:

```python
class SensorStatus(_DomainModel):
    state: SensorState
    cause: SensorCause
```

La regola che governa il tipo:

> **`cause != OBSERVED` significa che lo stato è il default fail-safe, non un'affermazione sul
> mondo.** `OFF` da solo non esiste: esiste `OFF perché non c'è hardware` e `OFF perché nessuno ha
> guardato`, che sono fatti diversi e nessuno dei due dice «è spento».

È lo stesso mestiere di `Device.privacy` che parte `LOCAL_ONLY` (ADR 0016): un valore non
dichiarato non deve mai essere letto come un permesso; qui, un valore non osservato non deve mai
essere letto come un'osservazione. Nessun campo, nessuno schema di API e nessuna riga della CLI
porta uno `SensorState` nudo.

**Il microfono e la webcam non sono simmetrici, e il modello lo dice.**

| | esiste hardware | in uso da qualcuno | stato |
|---|---|---|---|
| Microfono | osservabile | **osservabile** (CoreAudio) | `ACTIVE`/`AVAILABLE` + `OBSERVED` |
| Webcam | osservabile | **non osservabile** | `AVAILABLE` + `NOT_OBSERVABLE` |

`isInUseByAnotherApplication` non si usa: deprecato da 10.14. Una simmetria costruita su un'API
deprecata è una simmetria che si rompe da sola. E il codice non ha un secondo ramo per la webcam:
`_sensor(count, in_use)` è una funzione sola, e la webcam le passa `in_use=None`. L'asimmetria è un
fatto **sull'argomento**, non un ramo che finge che i due si somiglino.

Una nota di lettura, perché il nome inganna: qui `AVAILABLE` vuol dire «c'è e non è in uso», non
«ELA può usarlo». Se ELA possa usarlo lo dice la mappa dei permessi, separata di proposito. Unire
le due risposte è il lavoro della milestone che accenderà qualcosa.

## 4. Le cause che scattano, e la sola che non entra

Le quattro cause proposte erano *spento per scelta / negato dal sistema / hardware assente / non
osservabile*. Contro la semantica di §3, due di loro cambiano: una prende un nome più preciso,
l'altra non ha più un caso.

| Causa | Quando scatta | In M10.1 |
|---|---|---|
| `OBSERVED` | ho guardato, ed è così | **sì** |
| `NO_HARDWARE` | il dispositivo non esiste | **sì** — è il caso della CI |
| `NOT_OBSERVABLE` | non si può guardare | **sì** — webcam in uso, non-Darwin, sonda morta |
| `NOT_LOOKING` | ELA non ha guardato | **sì** — `ELA_PERCEPTION_ENABLED=false`, e prima del primo tick |
| ~~`DENIED_BY_SYSTEM`~~ | macOS rifiuta la lettura | **no** |

`NOT_LOOKING` è «spento per scelta» col nome che dice **qual è** la scelta: non usare il
dispositivo — ELA non lo usa comunque — ma *non guardare*.

`DENIED_BY_SYSTEM` non entra perché sotto §3 nessuno stato di §11 dipende da un permesso: il
microfono si osserva con CoreAudio, che non chiede niente, e le fotocamere si elencano senza TCC.
Consegnarla sarebbe consegnare un valore che non può scattare, ed è precisamente ciò che ADR 0026
§7 chiama peggio di una difesa assente. Il rifiuto resta un fatto reale e osservato, ma come
`PermissionState` sulla mappa separata, dove `DENIED` scatta oggi.

**Dove nasce:** la milestone in cui ELA proverà a **rendere `ACTIVE`** un dispositivo — accendere
il microfono, aprire la webcam. Lì «macOS mi rifiuta» spiegherà uno stato invece di essere un fatto
a parte, e sarà una domanda diversa da quella di adesso.

## 5. Il confronto è discreto, la misura no

`CGEventSourceSecondsSinceLastEventType` restituisce un float che cambia a ogni tick. Un rilevatore
di cambiamenti alimentato da un valore continuo dice «è cambiato qualcosa» sempre, e quindi non
dice niente.

L'altra metà è altrettanto vera: i secondi di inattività entrano **come numero**, senza nessuna
inferenza «presente/assente». Una soglia è una decisione e appartiene a chi decide (§45), non a chi
osserva; un Perception Core che pubblicasse `ASSENTE` avrebbe già deciso al posto del Decision
Engine, con una costante che nessuno ha discusso.

Le due cose si tengono separando **misurare** da **confrontare**:

> L'osservazione porta ciò che è stato misurato. Il *fingerprint* — ciò che il rilevatore confronta
> — porta solo valori discreti. `idle_seconds` viaggia nell'osservazione e **non entra nel
> fingerprint**.

Non c'è nessun `UserPresence`, e chi vorrà sapere se l'utente è davanti al Mac (§7) legge il numero
e sceglie la propria soglia. La partizione non è scritta a mano: `fingerprint()` deriva le chiavi
dai campi di `Observation` meno `UNCOMPARED`, così un campo aggiunto domani è **confrontato per
default** e va escluso di proposito — il verso fail-safe.

## 6. Tre cadenze, e sono configurazione

I costi misurati stanno su tre ordini di grandezza e le tre letture cambiano con frequenze
altrettanto diverse: il microfono si accende mentre guardi, un permesso cambia quando un umano
clicca in Impostazioni di Sistema.

| Famiglia | Cosa | Default |
|---|---|---|
| `SENSORS` | microfono in uso, presenza dei dispositivi | 2 s |
| `SESSION` | schermi, sleep, blocco, console, inattività | 5 s |
| `PERMISSIONS` | TCC di camera, microfono, Screen Recording | 30 s |

Un tick lancia **una** sonda con l'elenco delle famiglie scadute; se nessuna è scaduta non lancia
niente. Tutti i valori sono `ELA_PERCEPTION_*_INTERVAL_SECONDS`.

E il pezzo che rende onesto tutto il resto: `merge(previous, fresh, families)`. Un tick che
rinfresca solo i sensori **non deve** far risultare i permessi diventati illeggibili, perché
nessuno li ha chiesti. Senza quella funzione le cadenze differenziate produrrebbero un cambiamento
fantasma a ogni giro — il modo più facile di sbagliarle. `FAMILY_FIELDS` è una tabella sola, letta
dalle due parti, e un test verifica che partizioni `RawObservation` **esattamente**: due tabelle
divergerebbero, e la divergenza si vedrebbe come un permesso che «cambia».

## 7. Quando ELA guarda, e i due default

Tre momenti, e nessun refresh implicito nascosto altrove:

- **all'avvio, una volta**, nel `lifespan` — precedente esatto: `recover()`, «once, here, and not
  periodically» (ADR 0023 §11). Così `/diagnostics` ha da subito qualcosa di vero da dire.
- **a ogni lettura** di `GET /perception`: chi chiede vuole la risposta di adesso.
- **sulla cadenza**, se il ciclo continuo è acceso.

Due manopole, e scattano entrambe:

- `ELA_PERCEPTION_ENABLED`, default **`true`**.
- `ELA_PERCEPTION_LOOP_INTERVAL_SECONDS`, default **`0`, spento**.

**Percezione abilitata, ciclo spento.** ELA sa rispondere se le chiedi lo stato, e non osserva da
sola finché non l'accendi: è §11 applicato al livello sopra — niente è attivo senza motivo — e chi
accende il ciclo lo fa con un gesto. In v0.1 il gesto è configurazione; sarà una decisione del
Proactive Core (§34) quando ci sarà qualcuno che ha motivo di prenderla.

## 8. Dove si legge

`GET /perception` è il quadro intero e **osserva**; `/diagnostics` guadagna una riga e **non
osserva**. La linea fra le due è il docstring di `/diagnostics`: dice *a cosa ELA è collegata*, non
*cosa ELA sta facendo*. Un permesso mancante è composizione — è ciò che ELA **può** fare su questa
macchina, e sta accanto a `providers` e `tools`. Lo stato del microfono è il mondo.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `PerceptionProbe` | §10, §11 | async | `read` |

Il port più stretto di ELA, e stretto di proposito: risponde con primitive e mai col vocabolario
del dominio (§1). Il suo contratto ha una clausola che gli altri port non hanno — **non fallisce,
riporta**: un timeout, un figlio morto, un sistema operativo che non ha questa nozione tornano come
`RawObservation` con i campi a `None`, mai come eccezione.

## 9. Nessuna capability, e dove nasce la prima

Il Guardian decide su una Capability quando l'Executor sta per eseguire un Tool. In M10.1 non c'è
nessuno step, nessun tool, nessuna decisione: **non c'è niente da decidere**. Introdurre una
capability adesso significherebbe metterne a catalogo una che nessuno consuma, e il catalogo è
immutabile alla costruzione (ADR 0010) proprio perché non sia un posto dove si aggiungono cose «per
dopo».

C'è anche un argomento di merito: quello che M10.1 legge non è contenuto dell'utente. «Il microfono
è in uso» è un fatto sulla macchina, della stessa specie di «lo schermo dorme» — non un secondo di
audio, non un pixel.

**Vincolo registrato:** la **prima lettura di contenuto** — uno screenshot, un OCR, un campione
audio — nasce con la propria capability `MEDIUM` e con l'autorizzazione che le compete, nella
milestone che la introduce e non prima. Il confine non è «percezione sì / percezione no»: è **stato
contro contenuto**, ed è lì che passa la linea di §57.

## 10. L'audit registra ciò che ELA decide, non ciò che il mondo fa

Un cambio di stato osservato non entra nell'audit. Il criterio, che generalizza:

> **L'audit registra ciò che ELA decide, non ciò che il mondo fa.**

È la stessa forma di ADR 0026 §10 («chi sceglie scrive, non chi tocca»), estesa dal confermare
all'osservare. La catena di §32 è la traccia della responsabilità di ELA; riempirla di eventi che
ELA non ha causato la rende più lunga e meno leggibile, e ogni evento in più è rumore fra le
decisioni che qualcuno un giorno dovrà rileggere.

**L'eccezione, già decisa:** quando ELA **causerà** un cambio di stato — accendere il microfono —
quella è una scelta e si registra, con il tipo di evento che quella milestone introdurrà. In M10.1
ELA non causa niente, quindi un tick completo scrive **zero** eventi di audit, ed è una proprietà
con un test e non un'omissione.

Ne segue anche dove la percezione **non** va: non nell'audit, e non nella memoria. `PerceptionCore`
tiene l'osservazione corrente e la precedente — la seconda solo per poter confrontare — e niente
altro. Un anello di cambiamenti recenti sarebbe uno storico non dichiarato, e la memoria
strutturata è §21, con regole che questo modulo non ha e non deve improvvisare: importanza,
confidenza, scadenza, privacy. **La percezione non è memoria.**

## 11. Cosa la sonda non legge

`CGSessionCopyCurrentDictionary` restituisce anche `kCGSessionLongUserNameKey` — nome e cognome
dell'utente. La sonda legge **per chiave nominata** e non copia mai il dizionario: le chiavi lette
sono `kCGSSessionOnConsoleKey` e `CGSSessionScreenIsLocked`, e nient'altro. È una riga di codice ed
è il primo posto in cui §57 tocca l'hardware: uno snapshot che si porta dietro PII perché nessuno ha
guardato cosa c'era dentro il dizionario è esattamente il modo in cui questi errori entrano.

Nessuno dei modelli di percezione ha un `JsonMapping`, e per loro è una proprietà di §57 e non una
preferenza: un sacco libero su un'osservazione è precisamente dove un titolo di finestra, un nome
di file o una trascrizione finirebbero «giusto per contesto». Ciò che ELA percepisce sono i campi
dichiarati e nient'altro.

## 12. Le tabelle

`Regole aggiunte:`

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 32 `machine-access-in-one-place` | `ctypes` e l'avvio di processi solo in `ela.infrastructure.perception` | tutto `ela` | l'adapter è esente |
| 33 `perception-probe-imports-only-stdlib` | il figlio importa solo la standard library, mai `ela` | `probe.py` | nessuna esenzione |
| 34 `perception-adapter-decides-nothing` | l'adapter non nomina `SensorState`, `SensorCause`, `PermissionState` | `ela.infrastructure.perception` | nessuna esenzione |

`Soggetti aggiunti:` — la riga di ADR 0027 §5, ripetuta qui perché la tabella cresce (ADR
immutabile).

| Costante | Parola | Perché |
|---|---|---|
| `PERCEPTION_PROBE` | `ARTEFACT` | l'unico file che la regola 33 apre: ristretto, non ha niente da aprire e solleva invece di parlare |

**Rotta aggiunta** alla tabella di ADR 0023 §6:

| Metodo | Rotta | Cosa risponde |
|---|---|---|
| `GET` | `/perception` | sensori, permessi, sessione, inattività e i cambiamenti dell'ultimo tick |

`/diagnostics` non è una rotta nuova: guadagna un campo, `perception`, con abilitata, in ascolto,
i permessi e l'età dell'ultima osservazione. E non osserva — vedi §8.

**Comandi aggiunti** alla tabella di ADR 0024 §3:

| Comando | Rotta | Uscite |
|---------|-------|--------|
| `ela perception` | `GET /perception` | `0` `1` `2` `3` |

## Alternative considerate

- **pyobjc in-process.** Scartata, con la prova a favore in mano: converte davvero le eccezioni
  Objective-C in eccezioni Python. Non copre un blocco di `tccd` né un crash dentro un framework, e
  la lettura più importante è proprio una chiamata a un demone (§2).
- **Solo API C.** Scartata perché non risponde alla domanda centrale: lo stato TCC di camera e
  microfono non ha API C pubblica.
- **Un figlio persistente** invece di uno per tick. Scartata per v0.1: costerebbe meno e vorrebbe
  respawn, watchdog e uno stato in più che può bloccarsi. Si riapre sotto i ~200 ms di cadenza, che
  v0.1 non ha.
- **Un quarto valore `UNKNOWN` in `SensorState`.** Scartata: §11 dichiara tre stati e sono della
  spec. La domanda «lo hai osservato?» è di un'altra specie dalla domanda «è acceso?», e un enum
  che le assorbe entrambe è lo stesso errore di una difesa che non può scattare.
- **Quantizzare l'inattività in presente/assente.** Scartata: è una soglia, e una soglia è una
  decisione (§45). Il problema che risolveva — il rumore nel rilevatore — si risolve escludendo la
  misura dal fingerprint, che non decide niente al posto di nessuno.
- **`system_profiler` per l'elenco dei dispositivi.** Scartata: 390 ms contro 75, e sarebbe un
  secondo meccanismo (un sottoprocesso dentro il sottoprocesso) per una risposta che AVFoundation
  dà già nel figlio.
- **Mettere `ela.infrastructure.perception` nel gate con un `omit` per `probe.py`.** Scartata: un
  `omit` è una lista scritta a mano che descrive un'eccezione, cioè la forma che M9.1 ha passato
  una milestone intera a togliere. La regola 34 ottiene la stessa garanzia in modo derivabile.
- **Un anello di cambiamenti recenti in memoria.** Scartata: sarebbe uno storico non dichiarato, e
  la memoria ha una milestone e regole sue (§21).

## Conseguenze

- ELA sa dire cosa può e cosa non può fare su questa macchina, e lo dice senza mai chiedere un
  permesso e senza poter morire nel farlo.
- `OFF` ha smesso di essere esprimibile da solo: ogni stato di §11 viaggia con la causa che dice se
  è un'osservazione o il default fail-safe.
- ELA tocca il sistema operativo in **un** package, e la cosa è una regola invece che un'abitudine.
- Le regole di architettura passano da trentuno a **trentaquattro**, e i contratti di import-linter
  restano **tredici**: nessuna delle tre nuove è esprimibile come un divieto di import — due
  guardano chiamate, e la terza guarda nomi.
- I port passano da diciotto a **diciannove**.
- Nessun consumatore. Nessun task legge la percezione, nessuna decisione ne dipende: è la forma
  della milestone, ed è anche perché il ciclo continuo è spento di default — un osservatore che
  nessuno legge non deve stare a guardare.

### Vincoli dichiarati, da riaprire quando serviranno

- **La webcam in uso non è osservabile**, e lo resta finché Apple non pubblica un'API. Non si
  ripiega su `isInUseByAnotherApplication`, deprecato dal 2018.
- **`DENIED_BY_SYSTEM` non è una `SensorCause`** (§4): nasce quando ELA proverà ad accendere
  qualcosa.
- **Un processo per tick, non un figlio persistente** (§2). Si riapre sotto i ~200 ms.
- **La percezione non è memoria** (§10): l'osservazione corrente e la precedente, e nient'altro. Un
  riavvio azzera ciò che ELA ha visto.
- **Niente contenuto** (§9): la prima lettura di contenuto nasce con la propria capability MEDIUM.
- **`/diagnostics` mostra permessi vecchi** quanto l'ultima osservazione, e ne dichiara l'età.
- **Su Linux e su Windows ELA non percepisce niente**, e lo dice: `UnsupportedProbe` esiste come
  oggetto con un nome e un test, invece che come un buco che qualcuno scopre.
- **Il ciclo non ha backoff** — una sonda che fallisce viene richiamata alla cadenza di sempre; la
  credenza diventa `NOT_OBSERVABLE` e resta visibile, ma niente rallenta. Con una sonda che fallisce
  a lungo è un processo lanciato ogni N secondi per niente.
