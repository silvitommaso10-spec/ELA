# 0029. La prima lettura di contenuto: l'artefatto che si può verificare, il figlio che non è nostro, e la credenza che non decide

- **Stato:** Accettata. SPEC di M10.2 approvata dall'utente, sedici decisioni. Le quattro che
  cambiano la forma di ciò che ELA fa sono §1 (dove vive il contenuto, e dove non vivrà mai), §3
  (il figlio è di Apple, e la regola 33 diventa vera per costruzione), §7 (una credenza periodica
  non decide mai un'azione) e §16 (di chi è il permesso, e a quali condizioni si passa a launchd).
- **Contesto:** M10.2, la prima milestone in cui ELA produce contenuto dell'utente.
- **Riferimenti spec:** §10, §11, §20, §23, §28, §29, §30, §33, §57, §58, §63
- **Estende:** ADR 0002 (una regola nuova, la 35), ADR 0005 (un port nuovo), ADR 0010 (una
  capability aggiunta), ADR 0013 (un tool), ADR 0014 (un verifier), ADR 0023 (un campo di
  `/diagnostics`), ADR 0028 §9 (il vincolo che questa milestone salda).

## Contesto

ADR 0028 §9 registrò un vincolo invece di consegnare una capability nessuno consumava:

> **La prima lettura di contenuto** — uno screenshot, un OCR, un campione audio — nasce con la
> propria capability `MEDIUM` e con l'autorizzazione che le compete, nella milestone che la
> introduce e non prima. Il confine non è «percezione sì / percezione no»: è **stato contro
> contenuto**, ed è lì che passa la linea di §57.

Questa è quella milestone, e la riga che decide la sua forma non è la cattura. È che **per la
prima volta ELA produce contenuto dell'utente che nessuno le ha dettato.** Tutto ciò che ELA
aveva scritto fino a qui era o una sua decisione (l'audit), o qualcosa che l'utente le aveva
dettato (una nota), o la risposta di un provider a una domanda che l'utente aveva approvato. Un
PNG dello schermo è di un'altra specie: contiene tutto ciò che c'era davanti agli occhi
dell'utente in quell'istante, password manager compreso se era aperto.

Il secondo fatto è che **il permesso è negato, misurato, e lo concede un umano a mano.** Non
esiste nessuna strada di codice che lo ottenga (ADR 0028 §2: un processo che non è un'app non
può ottenere il permesso chiedendolo). La ricognizione, su macOS 26.6 (25G72), da un processo
senza grant:

| Lettura | Permesso | Esito |
|---|---|---|
| `CGPreflightScreenCaptureAccess()` | nessuno, e **non chiede** | **`False`**, 7,0 ms |
| `CGDisplayCreateImage`, `CGWindowListCreateImage` | — | simboli presenti, **deprecate da macOS 14/15** |
| ScreenCaptureKit | — | presente; Objective-C asincrono con **block** |
| `/usr/sbin/screencapture` | — | presente, firmato Apple |
| Display | — | 2560 × 1664 Retina → ~4,26 Mpixel; PNG realistico 1–5 MB |
| Interprete del venv | — | uv CPython 3.12.14, **adhoc / linker-signed**, nessun TeamIdentifier |

**Nessuna cattura è stata tentata durante la ricognizione, ed è una decisione e non una
dimenticanza:** un tentativo da uno stato negato può far comparire il prompt di sistema, e un
prompt che nessuno vede registra un **diniego permanente** che poi va disfatto a mano. È lo stesso
fatto che decide §7.

## 1. Dove vive un'immagine catturata, e dove non vivrà mai

Tre posti sono esclusi da fatti verificati, non da preferenze:

- **Non in `ExecutionResult.output`.** È una colonna `JSON` in una tabella *insert-only*, senza
  API di update né di delete, e il commento del suo ORM la descrive già come «the user's content
  (§57): it lives here, in the private database». Un PNG in base64 lì sarebbe contenuto **senza
  nessuna scadenza**, rileggibile da ogni lettura dei risultati, per sempre.
- **Non nell'audit** — regola 23, già esistente.
- **Non nella percezione** — ADR 0028 §10: «la percezione non è memoria».

Fra «solo memoria, e muore con la chiamata» e «un artefatto su disco» decide **§20**:

> *Perception → Planning → Permission → Action → Verification.* «Non deve assumere che un click
> sia riuscito solo perché è stato inviato.»

Nel repo questo non è una massima ma la `VerifierRegistry`, e ogni capability ne ha uno. **Un tool
che non lascia niente può essere verificato solo sulla propria parola**, che è precisamente ciò che
§20 vieta. Quindi: artefatto.

**Dove — e questo è un vincolo permanente, non una scelta di questa milestone:**

> **Il contenuto catturato non vive mai in una directory che qualcosa può sincronizzare.** Il
> workspace è la cartella che §23 descrive come sincronizzata; contenuto che vi atterra esce dalla
> macchina **senza che nessuno l'abbia deciso**, e «nessuno l'ha deciso» è l'esatto contrario di
> §57. Lo store è un fratello del database: `~/.ela/captures`, `ELA_CAPTURE_DIR`.

Permessi `0o700` sulla directory e `0o600` sui file, e sono **letteralmente le stesse due
costanti** del workspace e della directory del database, importate invece che ripetute: «i file
privati di ELA sono `0o600`» è un fatto in un posto solo e non tre che oggi coincidono.

| Manopola | Default | Tetto |
|---|---|---|
| `ELA_CAPTURE_TTL_SECONDS` | **300** | 3600, imposto come `MAX_DECISION_TTL` |
| `ELA_CAPTURE_MAX_COUNT` | **20** | — |
| `ELA_CAPTURE_MAX_BYTES` | **209 715 200** (200 MB) | — |

**Si purga all'avvio e prima di ogni cattura, mai su una cadenza.** Il ciclo continuo di percezione
è spento di default (ADR 0028 §7), e una ritenzione che dipendesse da un ciclo che nessuno ha
acceso non sarebbe una ritenzione. L'avvio è l'unico momento che ELA raggiunge con certezza: una
purga che girasse solo quando qualcuno fotografa terrebbe l'ultima cattura finché ELA è lasciata in
pace, e una foto dello schermo che sopravvive ai suoi cinque minuti perché non è successo niente è
esattamente l'accumulo che §57 vieta.

**La scadenza si legge dall'`mtime` dell'artefatto**, non da un indice: ciò che ELA riporta è ciò
che la purga applicherà, e non esiste un secondo registro di ciò che c'era sullo schermo da tenere
allineato.

## 2. L'`output` porta metadati, e il tipo lo rende impossibile

`output` porta `capture_id`, `path`, `bytes`, `sha256`, `width`, `height`, `display`,
`expires_at`. La stessa forma di `workspace.write_note`, che restituisce `{"path", "bytes"}` e non
il corpo della nota. `path` è il **nome dentro lo store**, non un percorso assoluto: lo store sta
sotto la home dell'utente, e una home directory non appartiene a un risultato persistito.

E non è disciplina: `Outcome.output` è una `JsonMapping`, e `JsonValue` **non ammette `bytes`**. Un
tool che provasse a metterci l'immagine non passerebbe `mypy --strict` e non validerebbe a runtime.
Vale la pena scriverlo perché è il motivo per cui **non c'è una regola di architettura per questo**:
una difesa che il sistema dei tipi dà già gratis, aggiunta come regola, è rumore.

## 3. Il figlio è `screencapture(1)`, e la regola 33 diventa vera per costruzione

| | stato su 26.6 | costo del rischio |
|---|---|---|
| `CGDisplayCreateImage` + ImageIO via `ctypes` | simboli presenti, deprecate | macOS 15+ ha introdotto un **ri-consenso periodico** per la cattura per via legacy: un permesso che torna a chiedere ogni mese non è una base |
| ScreenCaptureKit | presente | Objective-C **asincrono con block**: costruire un block literal da `ctypes` sarebbe la cosa più fragile del repo, e il sottoprocesso copre il crash ma non fa funzionare la cattura |
| **`/usr/sbin/screencapture`** | presente, firmato Apple | `-x` silenzioso, `-t png`, `-D <n>`, esce non-zero se rifiutato |

L'argomento che decide non è la robustezza. È che **la regola 33 diventa vacua invece che
rispettata**: «il figlio importa solo la standard library, mai `ela`» difende una proprietà — *ciò
che deve poter morire da solo non porta con sé il grafo di import del Core* — e quando il figlio
**non è codice nostro**, la proprietà è vera per costruzione invece che per verifica. Ed elimina
`ctypes` dalla lettura più rischiosa del progetto.

L'obiezione di ADR 0028 (`system_profiler` scartato come «un secondo meccanismo») non si applica:
non è un secondo modo di ottenere una risposta che la sonda già dà — è l'unico modo, e sostituisce
uno *più* fragile.

**Il costo dichiarato:**

- `screencapture` non stampa metadati. Larghezza e altezza si leggono dal chunk **IHDR** del PNG:
  ventiquattro byte e quattro rami — firma sbagliata, file troppo corto, primo chunk non IHDR,
  dimensione zero — dentro il gate e coperti al 100%.
- Nessun controllo su color space e cursore oltre ai suoi flag.
- **La regola 33 non viene estesa**: non nasce un secondo figlio Python, e `PERCEPTION_PROBE`
  resta un `Path` singolo.
- La regola 32 copre già lo spawn, perché il suo contenuto è «ELA tocca il sistema operativo in un
  posto solo» — **la porta, non la parola “percezione”**. L'adapter vive quindi in
  `ela.infrastructure.perception` anche se la cattura è un'azione (§5).

Il binario è a **percorso assoluto** e mai risolto tramite `PATH`: che cosa fotografa lo schermo
dell'utente non si decide con una variabile d'ambiente.

## 4. Il padre possiede la destinazione; il payload non passa da stdout

Il contratto di M10.1 è: il figlio stampa JSON su stdout, il padre lo parsa. Con un PNG diventerebbe
base64 su una pipe — +33%, l'intera immagine in memoria nel padre — e il modo di fallire
peggiorerebbe invece di restare uguale: **un figlio ucciso al timeout lascerebbe una stringa
troncata che decodifica in un'immagine parziale**, cioè una mezza risposta che assomiglia a una
risposta.

Direzione invertita: il padre crea la directory, sceglie il nome, lancia il figlio su quel percorso,
poi `lstat` (file regolare, nessun link), `chmod 0o600`, legge l'IHDR, misura e calcola lo sha256.
Tre proprietà che questa forma ottiene:

1. **Il percorso non è mai un argomento della capability.** Il chiamante non può scegliere dove
   atterra lo schermo dell'utente; il nome è un UUID più `.png`, e un nome che non ha quella forma
   non è un nome che lo store ha emesso — così un separatore di percorso smette di essere
   esprimibile invece di essere filtrato.
2. **Il successo lo decide il padre**, dal codice di uscita *e* dai metadati, mai da «il file non
   è vuoto».
3. **Il residuo è una classe di guasto nuova.** Il caso peggiore di M10.1 era «nessuna risposta» e
   non lasciava tracce; qui è **un file parziale a `0o600` sul disco**. Un `finally` lo cancella
   ogni volta che il figlio non ha riportato successo, e un test lo dimostra.

**Limite dichiarato:** `screencapture` crea il file da sé, quindi fra la sua scrittura e il `chmod`
del padre il file può portare per un istante l'umask del processo. La barriera vera è la directory
`0o700`, che nessun altro utente può attraversare; il `chmod` è la seconda cintura. Un link piazzato
dentro `captures/` fra i controlli e la scrittura è lo stesso limite dichiarato di `notes.py`: un
workspace locale a utente singolo.

## 5. La cattura è un'**azione**, non un'osservazione

§10 elenca «screen awareness» sotto la percezione; §20 dice dove sta davvero:
*Perception → Planning → Permission → **Action** → Verification*. La cattura è l'Action, e da qui
segue tutta la collocazione senza discussioni caso per caso:

- **`ela.perception` non cambia.** Niente famiglia nuova, niente `FAMILY_FIELDS`, niente `merge`,
  niente `_due_at`, nessun `RawObservation` allargato. Il Perception Core non sa che la cattura
  esiste. **Il primo anello osserva; il secondo agisce**, e agire passa dall'Executor.
- Il tool vive in `ela.tools`, dentro il gate al 100%.
- La classificazione — che cos'è un nome, che cos'è un file di cattura, quando è scaduto — vive in
  `ela.tools.captures`, **condivisa dal tool e dal suo verifier** e **read-only per costruzione**
  (regola 18, come `ela.tools.paths`). Se ciascuno avesse i propri controlli potrebbero non essere
  d'accordo, e una cattura che il tool dichiara sarebbe una cattura che il verifier non trova.
  Tutto ciò che **scrive** — la directory, il `chmod`, la purga, la rimozione di una cattura
  fallita — sta con il tool.
- L'adapter vive in `ela.infrastructure.perception` perché è lì che la regola 32 mette la porta.

## 6. La capability, e la domanda che l'utente legge

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `perception.capture_screen` | MEDIUM | — | — | sì | `purpose: string` | `display: integer` |

- **MEDIUM**, per la ragione che §29 dà a `model.complete` — «perché il contenuto dell'utente può
  essere inviato a un provider AI esterno» — letta un passo prima: qui il contenuto non parte, ma
  **nasce**, e nessuno l'ha dettato.
- **`requires_authorization`**: ogni cattura vuole un'approvazione o un grant che la copre.
  Nessuna scorciatoia perché la capability è «interna»: passa da `authorize` come `model.complete`,
  con `Rule.APPROVAL_UNLESS_AUTHORIZED`.
- **Nessuno scope, e non è una dimenticanza.** Lo scope del Guardian è *a forma di percorso*
  (`is_valid_scope_entry`, `scope_covers`, `targets_of`); lo scope naturale di una cattura è *quale
  display*, che non è un percorso. Infilarcelo produrrebbe uno scope che finge di essere un path. La
  protezione è l'autorizzazione, esattamente come per `model.complete`.
- **`display` è l'indice 1-based di `screencapture -D`**, e **non è correlato con `display_count`
  di M10.1** oltre al conteggio: due enumerazioni diverse dello stesso hardware, e promettere che
  coincidano è una promessa che ELA non può tenere.

### `purpose` finisce nella domanda che l'utente legge — §30

Un `purpose` obbligatorio che nessuno legge sarebbe un campo, non una difesa. §30 parla di
pagamenti, ma la sua frase è più generale — «un semplice “Sì” fuori contesto non deve
automaticamente autorizzare un pagamento critico». Generalizzata:

> **Un “sì” vale solo se la domanda era completa.** Un'approvazione a una domanda che non dice
> *per cosa* è un consenso fuori contesto, ed è precisamente ciò che §30 vieta.

Prima di M10.2 `Approval.prompt` era costruito da `spec.id`, dai target, dallo step e dalla
`reason`: **gli argomenti non ci arrivavano mai**. Il meccanismo che serve è piccolo e generale, e
ha la forma che §28 già descrive — una Capability *dichiara* ciò che la riguarda:

`CapabilitySpec.prompt_arguments`, default **vuoto**. `check_capability` impone che ciascuno sia
una proprietà **`string`** e **obbligatoria** dello schema: una domanda a cui può mancare metà
delle parole non è una domanda.

Il default vuoto è il verso fail-safe e non una comodità: `model.complete` ha `input`, che è
**contenuto dell'utente**, e un prompt che lo mostrasse lo scriverebbe in un `Approval` persistito.
**Un argomento non si mostra a meno che la capability non lo dichiari.** Nessuna delle tre di v0.1
lo fa, e per loro il prompt è identico byte per byte.

**Perché il campo è generale, e non un'eccezione per la cattura.** Prima di M10.2 la domanda posta
all'utente diceva *quale capability* stava per essere eseguita e non *che cosa* stava approvando —
sono due informazioni diverse, e §30 chiede la seconda. Il campo esiste perché:

> **La domanda posta all'utente deve poter dire che cosa sta approvando, non soltanto quale
> capability sta per essere eseguita.**

Non è un requisito dello schermo: è il requisito di ogni consenso informato che ELA chiederà.
Telefonare a qualcuno (§7) non è «`comms.call` ha chiesto il permesso», è *a chi* e *per dire
cosa*; mandare una email (§39) è *a chi* e *su cosa*; un ordine (§30) è *che cosa* e *per quanto*.
Ognuna di quelle capability avrà il suo `prompt_arguments`, e il meccanismo che oggi porta un
`purpose` è lo stesso che porterà quei campi — dichiarati uno a uno, mai tutti, perché il default
vuoto è ciò che tiene il contenuto dell'utente fuori da un `Approval` persistito.

## 7. Una credenza periodica non decide mai un'azione

La sonda **legge già** `screen_recording_permission`, nella famiglia `PERMISSIONS`, a 30 s di
cadenza. Il tool **non si fida** di quella credenza: 30 s di ritardo significano rifiutare una
cattura che l'utente ha appena abilitato, o tentarne una che ELA sa negata. Il permesso si rilegge
**nell'istante della cattura**.

E se la risposta è «negato», **ELA non lancia il figlio.** Non è un'ottimizzazione: è la cosa che
protegge l'utente. Tentare una cattura da uno stato negato è **come si registra un diniego
permanente**; un `Outcome` con un codice e una ragione — con scritto cosa fare e dove — è ciò che
ELA deve fare invece. Ed è una proprietà con un test che guarda le *chiamate* all'adapter, non
l'assenza di un file: non tentare è il comportamento, e un comportamento si prova osservandolo.

> **Il criterio, scritto perché valga oltre questa milestone: una credenza periodica non decide mai
> un'azione.** Una credenza a cadenza serve a **raccontare** — `/perception`, `/diagnostics`, una
> riga della CLI. Nel momento in cui qualcosa deve **accadere**, il fatto si rilegge. È la
> generalizzazione di ADR 0028 §5 («misurare e confrontare sono cose diverse») al confine fra
> osservare e agire.

Il figlio del preflight e il figlio della cattura sono due processi diversi ma **ereditano lo stesso
processo responsabile** (§16), quindi TCC dà a entrambi la stessa risposta. Se un giorno non fosse
più vero, ciò che resta è una corsa di millisecondi che atterra su `screen.capture_failed` e non su
un prompt.

## 8. Nessun trigger automatico

«Quando il primo anello segnala un cambiamento, ELA **può** guardare» è una possibilità, non un
automatismo. In M10.2 nessuno crea un task di cattura: lo crea l'utente, con la pipeline che
esiste già. Chi lo creerà da solo è il **Proactive Core (§34)**, la milestone in cui esiste
qualcuno con una ragione per prendere quella decisione. È la stessa forma di ADR 0028 §7 («un
osservatore che nessuno legge non deve stare a guardare»): il collegamento fra i due anelli è **una
capability che esiste**, non un filo che scatta.

## 9. Il verifier, perché §20 lo pretende

| Condizione | Cosa controlla |
|---|---|
| `capture.exists` | al nome dichiarato c'è un file **regolare**, non un link, dentro lo store, ed è un PNG con un IHDR leggibile |
| `capture.matches` | byte, sha256, larghezza e altezza letti dal disco sono quelli che il risultato dichiara |

Il confronto è contro l'**output** e non contro gli argomenti, e non è l'errore di «fidarsi della
parola del tool» che `WriteNoteVerifier` evita: `purpose` e `display` non determinano un solo pixel,
quindi non c'è un'intenzione con cui confrontare. Ciò che è sotto esame **è** la dichiarazione — «ho
scritto un PNG di questa dimensione con questo digest» — e la fonte di verità è il disco. È
letteralmente §20.

Il verifier rilegge **con lo stesso codice** che ha scritto (§5) e non ricattura nulla: verificare
non è rifare.

**Il limite, dichiarato perché nessuno lo legga per più di quello che è.** Il verifier **non può
dire che l'immagine ritrae lo schermo**. Può dire che esiste, che è un PNG, e che è esattamente
quella che il tool ha dichiarato — byte, digest, larghezza, altezza. Che quei pixel siano il
desktop dell'utente e non una schermata nera, o la finestra sbagliata, o un display addormentato,
è fuori dalla sua portata: servirebbe capire l'immagine, che è visione e non verifica.

Quello che copre è precisamente §63: *«non deve assumere che un click sia riuscito solo perché è
stato inviato»* — l'esecuzione non è la prova del successo, e ciò che il verifier confronta è la
**dichiarazione del tool contro il disco**. Un tool che riportasse successo senza aver scritto
niente, o che avesse scritto qualcos'altro, viene preso. Un tool che ha fotografato uno schermo
spento no, e ammetterlo è più utile che un verifier che sembra dire di più.

E il secondo limite: **deve girare entro la TTL.** Nella pipeline gira nello stesso step, a
millisecondi di distanza; è scritto per chi un giorno verificherà in differita.

## 10. Nessun evento di audit nuovo

L'esecuzione è già tracciata: `PERMISSION_DECIDED` dal Guardian, `TOOL_EXECUTED` e `STEP_*`
dall'Executor. La cattura non cambia nessuno stato di §11 — lo schermo non si «accende» perché ELA
lo legge — quindi **l'eccezione registrata in ADR 0028 §10 non scatta qui**: nasce quando ELA
*causerà* un cambio di stato, e leggere non è causare.

Nel payload finiscono il nome e l'id, che non sono contenuto: la regola 23 resta soddisfatta senza
doverla toccare. `purpose` è la ragione dichiarata da chi ha chiesto, ed **è desiderabile** che
finisca nella traccia: è l'unico posto dove «perché è stata letta» sopravvive alla scadenza
dell'immagine.

## 11. Un port nuovo, il ventesimo

`PerceptionProbe` promette tre cose, e la cattura ne rompe due: risponde con primitive *e non
prende ingressi*; non fallisce, riporta; e legge **stato, mai contenuto** — la frase che sta nel suo
docstring.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ScreenCapturePort` | §10, §20, §57 | async | `available`, `capture` |

`available` è un membro suo e non un fallimento di `capture`, per la ragione che ADR 0028 diede a
`UnsupportedProbe`: «ELA su Linux non fotografa niente» merita di essere una risposta con un nome e
un test invece di un buco che qualcuno scopre. E permette di risolvere la domanda **prima** del
permesso, così una macchina che non potrebbe mai catturare non legge un permesso che non le serve.

`capture(destination, display)` risponde con `RawCapture` — codice di uscita e se è stato ucciso —
e mai con un pixel: l'immagine va nel file e da nessun'altra parte. La regola 34 continua a valere:
l'adapter non nomina `PermissionState`, e che cosa significhi «uscito con 1» non è suo da dire.

Implementazioni: `ScreenCaptureCommand` (Darwin) e `UnsupportedScreenCapture`, scelte dal
composition root con lo stesso `platform.system()` di M10.1.

## 12. Una regola nuova, la 35, e le due che non servono

`Regole aggiunte:`

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 35 `capture-stays-on-the-machine` | i moduli che tengono una cattura non nominano un router, un provider registry né un client HTTP | `ela.tools.screen`, `ela.tools.captures` | nessuna esenzione |

È la regola che rende vera la frase centrale della milestone, e **può scattare**: `ela.tools.model`
importa davvero il router, quindi «un tool importa il router» è codice legale in questo repo, e
scriverlo in `screen.py` è esattamente ciò che M10.3 sarà tentata di fare. Una difesa che non
potesse scattare sarebbe peggio di nessuna (ADR 0026 §7). Non è una regola sui tool in generale:
`ela.tools.model` deve nominare il router. È una regola sui due moduli che hanno lo schermo
dell'utente fra le mani.

Le due che **non** entrano, e perché:

- *«L'immagine non entra in un `output`»* — il sistema dei tipi lo impedisce già (§2).
- *«Solo lo store legge la directory delle catture»* — una regola sui percorsi costruiti a runtime
  sarebbe sintattica e aggirabile con una `Path` composta altrove: sembrerebbe attiva e non lo
  sarebbe. La garanzia vera è che la directory ha **un solo modulo** che la conosce (§5), e quello
  si vede leggendo gli import.

## 13. Il catalogo cresce, e `catalogue_v01()` resta congelato

§29 elenca *tre* capability di produzione per v0.1, e v0.1 è rilasciata (M9.4). Un
`catalogue_v01()` che ne restituisse quattro sarebbe una funzione che mente.

Il precedente esiste ed è di M10.1: `tests/docs/test_v01_surface.py` conta quindici rotte da una
tupla `ROUTERS` che **non contiene** `perception.router`. La rotta post-v0.1 non è stata ripiegata
nella superficie di v0.1: è stata lasciata fuori. Stessa forma qui.

- `catalogue_v01()`, `tools_v01()`, `verifiers_v01()` **restano come sono**.
- Nascono `production_catalogue()`, `production_tools()`, `production_verifiers()`, che compongono
  la baseline con ciò che le fasi successive aggiungono. Il composition root usa queste.
- **I due nomi dicono cose diverse, e i docstring lo dicono.** `production_` dice **quando** si
  usa; `catalogue_v01` dice **cosa contiene**. Ciascun docstring rimanda all'altro: una coppia di
  funzioni in cui una sembra la versione vecchia dell'altra è come nascono le chiamate al posto
  sbagliato. Il criterio, in una riga: **v0.1 non si ripiega, si affianca.**

## 14. Un timeout suo, e il numero si misura

I 2 s di `ELA_PERCEPTION_PROBE_TIMEOUT_SECONDS` sono generosi di due ordini di grandezza su una
lettura da 35 ms, e la loro ragione è *un `tccd` che non risponde*. Una cattura ha un altro
orologio: risveglio del display, compositor sotto carico, codifica PNG di 4,26 Mpixel. Condividere
la manopola sarebbe condividere un budget che descrive un'altra cosa.

`ELA_CAPTURE_TIMEOUT_SECONDS` è la manopola. **10 s è un segnaposto dichiarato, non un default**:
al momento della scrittura il permesso era negato, nessuna cattura era mai girata e nessun numero
onesto esisteva. Il numero misurato entra nella spec di M10.2 e qui **prima** del codice che lo
usa, cioè nel commit in cui il permesso c'è.

Un default provvisorio che nessuno rimisura è una soglia messa «per ora», e questo progetto sa come
finisce — quindi il promemoria non è un commento. È `CAPTURE_TIMEOUT_IS_MEASURED`, e il test che lo
legge:

> **La condizione è un fatto osservabile, non una data.** Su una macchina dove ELA legge che
> Screen Recording è **concesso**, un segnaposto ancora segnaposto è un test rosso. Dove il
> permesso manca — un runner Linux, un Mac che nessuno ha autorizzato — non c'è niente da misurare
> e il test dice «non applicabile» invece di passare in silenzio.

È la stessa forma di un budget: un promemoria che scatta su un calendario scatta quando nessuno può
farci niente; questo scatta esattamente quando qualcuno può. La decisione è una funzione pura con
il suo caso negativo (`overdue`), perché la combinazione che conta — *concesso, e ancora
segnaposto* — deve poter essere provata su qualunque runner e non solo sulla macchina dove capita
di essere vera. Il flag si gira **nella stessa modifica** che sostituisce il numero, mai da solo.

## 15. Il tetto rifiuta, non sfratta

Se dopo la purga ci sono ancora 20 catture non scadute, o 200 MB non scaduti, la cattura nuova
**viene rifiutata** con `screen.store_full`. Non si cancella una cattura ancora viva per fare posto:
qualcuno potrebbe starla leggendo, e il fail-safe di §33 è non agire, non «agire su qualcos'altro».

`/diagnostics` guadagna, dentro `perception`, cosa ELA sta trattenendo adesso:

| Campo | Cosa dice |
|---|---|
| `captures.retained`, `captures.bytes` | quante catture e quanti byte ELA tiene in questo momento |
| `captures.ttl_seconds`, `captures.max_count`, `captures.max_bytes` | sotto quali limiti |

Sta lì e non su `/perception` per la linea di ADR 0028 §8: `/perception` è **il mondo**, e uno store
di catture non è il mondo, è ELA. E ci sta di diritto: §57 rende «quale contenuto stai trattenendo
in questo momento» una domanda che l'utente deve poter fare, e uno store di screenshot che conosce
solo il filesystem è esattamente ciò che non deve esistere. Il conteggio è una lettura di directory
su al più `max_count` voci: `/diagnostics` continua a **non osservare il mondo**, legge il proprio
stato come già conta i provider e i task.

**Nessuna rotta nuova e nessun comando nuovo:** la cattura si raggiunge con `POST /tasks`,
`/approvals` e `/tasks/{id}/results`, che esistono.

## 16. Come gira ELA, e di chi è il permesso

**v0.1 gira da terminale, e il permesso di registrazione dello schermo è di Terminal.app.** La
catena misurata è `Terminal.app → login → zsh → python`, e TCC attribuisce la registrazione dello
schermo al **processo responsabile**, non all'interprete.

`launchd` porterebbe TCC ad attribuire il grant all'interprete —
`~/.local/share/uv/python/cpython-3.12.14-macos-aarch64-none/bin/python3.12`, **adhoc /
linker-signed, senza TeamIdentifier**. Due conseguenze, entrambe inaccettabili: **ogni progetto
Python di questo Mac** che usa quell'interprete erediterebbe la registrazione dello schermo (§57
al contrario), e il grant, legato al **cdhash**, sarebbe **revocato in silenzio** da un
aggiornamento di `uv` — un permesso che sparisce senza dirlo è peggio di un permesso che non c'è.

> **Vincolo di Fase 12:** il passaggio a `launchd` richiede **un eseguibile firmato proprio di
> ELA** — bundle, Developer ID, identità TCC sua. Finché non esiste, ELA gira da terminale e il
> permesso è del terminale.

## Alternative considerate

- **Solo memoria, e l'immagine muore con la chiamata.** Scartata per §20: un tool che non lascia
  niente è verificabile solo sulla propria parola, e M10.3 dovrebbe comunque costruire lo store.
- **L'immagine in base64 su stdout**, come i tre numeri di M10.1. Scartata: un figlio ucciso al
  timeout lascia una stringa troncata che decodifica in una mezza immagine — una risposta
  sbagliata invece di nessuna risposta (§4).
- **`ctypes` su `CGDisplayCreateImage`.** Scartata: deprecata, e macOS 15+ ri-chiede il consenso
  periodicamente per quella strada.
- **ScreenCaptureKit da `ctypes`.** Scartata: block literal costruiti a mano sarebbero la cosa più
  fragile del repo, e l'isolamento copre il crash ma non fa funzionare la cattura.
- **La cattura come quarta famiglia del Perception Core.** Scartata: §20 la mette sotto *Action*.
  Una famiglia le darebbe una cadenza, un `merge` e una freschezza che una fotografia non ha.
- **Un `io.error` generico nel tool.** Scartata: ogni fallimento di filesystem che questo tool può
  incontrare è già classificato con un codice suo, quindi sarebbe **un codice che non può
  scattare** — peggio di nessun codice (ADR 0026 §7).
- **Uno `screen.empty` accanto a `capture.missing` e `capture.malformed`.** Scartata per la stessa
  ragione: due vocabolari per lo stesso fatto, e quello condiviso col verifier è l'unico che
  garantisce che i due siano d'accordo.
- **Sfrattare la cattura più vecchia quando il tetto è raggiunto.** Scartata: §15.
- **Un tetto sulla TTL più alto, o nessuno.** Scartata: oltre un'ora una cattura smette di essere
  un file di lavoro e diventa un archivio di ciò che l'utente aveva sullo schermo.
- **Rinominare `catalogue_v01()`.** Scartata: dice cosa contiene, e continuerà a contenerlo (§13).
- **Concedere il permesso a un LaunchAgent adesso.** Scartata: §16.

## Conseguenze

- ELA sa fotografare lo schermo, e non può farlo senza che qualcuno abbia detto di sì a una domanda
  che dice **per cosa**.
- Il contenuto dell'utente ha per la prima volta una **scadenza applicata**, non dichiarata: una
  directory sola, due tetti, una purga che gira all'avvio e prima di ogni scrittura.
- Quando il permesso manca, ELA lo dice e **non tenta** — che è anche ciò che impedisce a ELA di
  far registrare al sistema operativo un diniego permanente per conto dell'utente.
- `ctypes` non compare più nella lettura più rischiosa del progetto: il figlio che fotografa è di
  Apple.
- Il vincolo di ADR 0028 §9 è **saldato**: la prima lettura di contenuto esiste, è MEDIUM, e chiede
  autorizzazione.
- Le regole di architettura passano da trentaquattro a **trentacinque**, e i contratti di
  import-linter restano **tredici**: la 35 guarda nomi e attributi, non è esprimibile come divieto
  di import.
- I port passano da diciannove a **venti**.
- Le capability di produzione passano da tre a **quattro**; quelle di v0.1 restano **tre**.
- Rotte e comandi non cambiano.

### Vincoli dichiarati, da riaprire quando serviranno

- **Il contenuto catturato non vive mai in una directory sincronizzabile** (§1). Permanente.
- **Una credenza periodica non decide mai un'azione** (§7). Criterio generale.
- **v0.1 gira da terminale; il permesso è di Terminal.app**, e `launchd` richiede un eseguibile
  firmato proprio di ELA — **vincolo di Fase 12** (§16).
- **L'immagine non lascia la macchina** (§12). Si riapre in M10.3, con la propria decisione di
  privacy e le quattro risposte di §57 su un dato che esce.
- **Nessun trigger automatico** (§8): si riapre col Proactive Core, §34.
- **Il tetto rifiuta, non sfratta** (§15).
- **Il verifier deve girare entro la TTL** (§9).
- **`display` non è correlato con `display_count`** oltre al conteggio (§6).
- **Nessuna cifratura a riposo, e nessuna redazione** — la cattura prende lo schermo intero: se c'è
  un password manager aperto, è nel PNG. §57 è mitigato dalla TTL corta, dai permessi e dal
  `purpose` obbligatorio — **non da un filtro**, perché un filtro che sbaglia una volta è peggio di
  nessun filtro, e riconoscere «una regione sensibile» è un problema di visione che questa
  milestone non ha.
- **Un display per cattura**, e nessuna cattura di finestra o di regione.
- **Nessun backoff** sul figlio della cattura: un permesso revocato fa fallire ogni cattura allo
  stesso costo, e il costo è pagato da chi chiede.
