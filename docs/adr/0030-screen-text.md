# 0030. Comprendere ciò che si vede: il contesto che non costa un permesso, il figlio che torna nostro, e l'artefatto che eredita

- **Stato:** Accettata. SPEC di M10.3 approvata dall'utente, diciotto decisioni. Le quattro che
  cambiano la forma di ciò che ELA fa sono §2 (i titoli non entrano, ed è una regola), §7 (il
  testo passa da stdout, dove i pixel non potevano), §8 (una lettura che significa due cose va
  spezzata) e §10 (un artefatto derivato eredita per costruzione).
- **Contesto:** M10.3, la milestone in cui ELA capisce ciò che ha visto senza far uscire niente.
- **Riferimenti spec:** §10, §11, §20, §28, §29, §33, §44, §45, §57, §58, §63
- **Estende:** ADR 0002 (una regola nuova, la 36; e le regole 33 e 35 estese), ADR 0005 (un port
  nuovo), ADR 0010 (una capability aggiunta), ADR 0013 (un tool), ADR 0014 (un verifier),
  ADR 0028 (una famiglia di percezione), ADR 0029 §12 (il vincolo che questa milestone riapre,
  esamina e **conferma**).

## Contesto

ADR 0029 §12 scrisse, nel docstring della regola 35, che il divieto valeva «finché M10.3 non
decide, con la sua decisione di privacy, cosa può uscire e sotto quale policy».

**La decisione di M10.3 è: non esce niente**, e la regola si estende invece di rilassarsi. Questo
ADR esiste per dire *perché quella era la scelta migliore e non solo la più prudente*, e per
lasciare a chi la riaprirà le domande già formulate invece che da inventare.

La ricognizione, su macOS 26.6 (25G72), con un controllo negativo che le due precedenti non
avevano potuto costruire: un `.app` usa-e-getta lanciato via LaunchServices, che TCC tratta come
**responsabile di sé stesso** (`ppid 1`, preflight `False`). Senza di esso ogni lettura fatta dal
terminale risponde col permesso già concesso, e «gratis» e «già pagato» sono indistinguibili.

| Lettura | con Screen Recording | **senza alcun grant** | costo |
|---|---|---|---|
| `kCGWindowOwnerName`, `OwnerPID`, `Bounds`, `Layer` | presenti | **presenti** | 0,26 ms a caldo |
| **`kCGWindowName`** (il titolo) | **6/6** | **0/5** | — |
| `NSWorkspace.frontmostApplication` | — | **presente** (nome, bundle id, pid) | **0,001 ms** |
| `runningApplications` | — | **123 processi, 15 con interfaccia** | incluso |
| `AXIsProcessTrusted` | — | **`False`** — e non si chiede | ~0 |

| OCR (Vision, livello `accurate`, `it-IT,en-US`) | Valore |
|---|---|
| 1200 × 1200 con testo noto | 108 ms a caldo — **tutte** le righe corrette, anche a 9 punti, confidenza **1,00** |
| **2940 × 1912, schermo reale** | **232 ms** — 44 righe, 497 caratteri |
| 2940 × 2940, testo denso | **1003 ms** — 65 righe, 5738 caratteri |
| **lo stesso, con 20 processi che bruciano CPU su 10 core** | **2727 ms**, massimo 2959 — **2,7×** |
| con rete negata (`sandbox-exec`) | **106 ms, identico** |
| **da un processo senza alcun grant TCC** | **funziona**, 287 ms |
| `regionOfInterest`, un quarto dell'immagine | 639 ms e **2732** caratteri contro 1336 ms e 6956 |
| livello `fast` | 20 ms, e `Nota pl¢¢ols'.18 s¢*denz¥ slitta 812026-04-03`, confidenza 0,50 |

E i modi di fallire, misurati uno per uno:

| Ingresso | Esito |
|---|---|
| file inesistente, file non-immagine, immagine 1 × 1 | `ok=False`, code 13, con un messaggio |
| **PNG troncato** | **`ok=True`, zero osservazioni** |
| **lingua inesistente (`xx-YY`)** | **`ok=True`, zero osservazioni** |

Quattro fatti hanno deciso più delle opinioni, e sono tutti misure:

1. **Il titolo di una finestra costa lo stesso permesso di uno screenshot.** L'ipotesi di partenza
   — «è testo, non pixel, e potrebbe non richiedere di far uscire nulla» — è vera sull'uscita e
   falsa sul permesso.
2. **Vision non chiede permessi e non chiede la rete.** È l'unica delle tre strade che è locale
   per costruzione e non per promessa.
3. **Il primo tentativo via `ctypes` verso Vision è morto con SIGSEGV**, prima di stampare una
   riga. Il pericolo di ADR 0028 §2, su un framework diverso.
4. **L'OCR degrada sotto carico e la cattura no.** 2,7×, dove ADR 0029 §14 aveva misurato che il
   lavoro di `WindowServer` non risente del carico dello userland.

## 1. Due consegne, e la linea era già tracciata

ADR 0028 §9: *non è «percezione sì / percezione no», è **stato contro contenuto**, ed è lì che
passa la linea di §57.* Questa milestone lo applica due volte, in due direzioni opposte, il che è
la prova migliore che il criterio funziona.

| | cosa è | dove va | capability |
|---|---|---|---|
| quali app girano, quale è in primo piano, quante finestre | **stato** | `ela.perception`, quarta famiglia | **nessuna** |
| che cosa c'è scritto in una cattura | **contenuto** | `ela.tools`, dietro il Guardian | **`perception.read_screen_text`** |

Ne segue tutto il resto senza discussioni caso per caso: la famiglia non scrive niente, non ha
TTL e non passa dall'Executor perché **osservare non è agire** (ADR 0029 §5); la capability non ha
cadenza né `merge` perché una lettura di contenuto non è un'osservazione periodica.

## 2. La famiglia `APPLICATIONS`, e i titoli che non ci sono

Tre campi in `RawObservation` e in `Observation`, e non uno di più: `running_bundle_ids`,
`frontmost_bundle_id`, `window_count`. Cadenza 2 s, la classe di `SENSORS`, perché è quello che
cambia mentre guardi; e l'ordine di dichiarazione dell'enum **è la misura**, con un test che
asserisce che i default salgano lungo di esso.

**Il bundle identifier e non il nome.** `localizedName` risponde `Terminale`, `Impostazioni di
Sistema`, `Contatti`: confrontare due osservazioni su valori che cambiano con la lingua del
sistema significa un rilevatore che scatta a un aggiornamento di macOS.

Cosa non entra, e perché ciascuna cosa non entra:

- **I titoli.** Contenuto — un titolo di Chrome porta un URL o il soggetto di una mail — e
  costano lo stesso permesso di uno screenshot. Vorrebbero una capability loro per
  un'informazione che l'OCR legge comunque dalla barra del titolo, dentro la stessa immagine.
- **La geometria per finestra.** Nessun consumatore: la `region` di §12 è normalizzata
  sull'immagine e non sulle finestre. Un campo che nessuno legge è uno stub «per dopo».

**Una nota che non è una scusa:** l'elenco delle app che una persona usa *è* informazione
personale, anche se non è contenuto. Non esce (§15), non entra nell'audit e non entra nella
memoria — la percezione tiene l'osservazione corrente e la precedente e nient'altro (ADR 0028
§10), quindi un riavvio azzera anche questo.

## 3. Il titolo non si legge, ed è la regola 36

Il precedente è ADR 0028 §11: la sonda legge `CGSessionCopyCurrentDictionary` **per chiave
nominata** perché il nome e cognome dell'utente non vengano copiati per errore. Quella disciplina
restò un commento, e l'ADR stessa la descrive come «una riga di codice».

Qui diventa una regola, per la ragione che ADR 0029 §12 dà alla 35: **può scattare.** Il codice
per leggere il dizionario delle finestre adesso esiste nel file, leggere un titolo è una
`CFStringCreateWithCString(b"kCGWindowName")` di distanza, ed è esattamente ciò che la milestone
successiva sarà tentata di fare. Una difesa che non potesse scattare sarebbe peggio di nessuna
(ADR 0026 §7).

Guarda un **letterale**, non un import: una chiave CoreFoundation è una stringa passata a una
funzione C, e una regola sugli import sarebbe stata muta sull'unico codice capace di romperla. Per
questo i contratti di import-linter restano tredici.

## 4. Il fingerprint impara a confrontare un elenco

`fingerprint()` guadagna un ramo per le sequenze: `",".join(sorted(value))`. **Ordinato**, perché
l'ordine in cui macOS elenca le app non è un fatto sul mondo e il rilevatore riporterebbe sé
stesso; **unito**, perché un `PerceptionChange` che portasse due `repr` da quindici elementi non
direbbe a nessuno che cosa è cambiato.

I tre campi entrano tutti nel confronto, e `frontmost_bundle_id` cambia a ogni passaggio di
finestra. Il criterio di ADR 0028 §5 non si applica: quello riguardava una misura **continua**
(`idle_seconds`), non una grandezza discreta che cambia spesso. «L'utente è passato a Mail» ha un
prima e un dopo, ed è precisamente il cambiamento che §44 vuole sapere.

## 5. L'OCR non fotografa: consuma un `capture_id`

Prende una cattura che esiste già, e tre cose diventano gratuite invece che costruite:

1. **Il permesso non è affare suo.** Vision non ne chiede — misurato da un processo senza alcun
   grant — quindi niente preflight, niente diniego che possa essere registrato.
2. **La TTL si applica da sé.** Il tool purga prima di scrivere, quindi una cattura scaduta viene
   rimossa e la lettura torna `capture.missing` **senza un ramo «scaduta»**: la purga *è* il
   meccanismo della scadenza, e un secondo controllo sarebbe un secondo posto da tenere allineato.
3. **L'integrità si controlla col codice del verifier** (`captures.inspect`). Ed è necessario, non
   elegante: un PNG troncato fa rispondere a Vision `ok=True` con zero righe, quindi «non c'è
   testo» è vero solo se il file era intero.

I codici d'errore della cattura sono quelli che esistono già, per la ragione con cui ADR 0029
scartò uno `screen.empty`: due vocabolari per lo stesso fatto, e quello condiviso col verifier è
l'unico che garantisce che i due siano d'accordo.

## 6. Il figlio torna nostro, e la regola 33 deriva il suo soggetto

Non esiste nessun binario Apple che faccia OCR: cercati `shortcuts`, `textutil`, `sips`,
`qlmanage`, `mdimport`, e niente in `/usr/bin`, `/usr/sbin`, `/usr/libexec`. Quindi la proprietà
che ADR 0029 §3 aveva ottenuto **per costruzione** — un figlio che non è codice nostro non può
importare il nostro — torna a essere una **verifica**.

La strada facile era una tupla di due file. Non entra:

> **Una lista è una cosa che qualcuno dimentica di aggiornare**, e la regola sarebbe andata muta
> proprio sul file che ne aveva bisogno. Il soggetto si **deriva**: un figlio è un modulo
> dell'adapter eseguibile come script.

E la derivazione si difende da sola, che è ciò che la rende affidabile: **la proprietà che fa
scattare la regola è la stessa che fa funzionare il figlio.** `python -m <modulo>` esegue il corpo
con `__name__ == "__main__"`, quindi un figlio che perdesse il guard non stamperebbe niente e il
suo adapter leggerebbe uno stdout vuoto. Non si può uscire in silenzio da questa regola e avere
ancora un helper che funziona.

Ne segue che **`PERCEPTION_PROBE` esce dai `SUBJECT`**: i soggetti dichiarati tornano tre. Un
soggetto derivabile vale più di uno dichiarato, perché solo il dichiarato può restare indietro
rispetto all'albero.

Il figlio Vision ha la disciplina del figlio di M10.1: primitive fuori, nessuna decisione dentro,
regola 34 — riverificata su di lui con un test che fallisce se il file nuovo non è nella lista che
la regola legge.

## 7. Il testo passa da stdout, e qui si può

ADR 0029 §4 invertì la direzione per i pixel, e la ragione era precisa:

> un figlio ucciso al timeout lascerebbe una stringa troncata che **decodifica in un'immagine
> parziale**, cioè una mezza risposta che assomiglia a una risposta.

**Quella ragione qui non esiste, ed è una proprietà del formato: JSON si autodelimita, base64 no.**
Un oggetto JSON troncato non è un oggetto JSON: è un errore di parsing, cioè esattamente il
fallimento pulito che la forma di M10.2 doveva costruire a mano.

E la direzione invertita **guadagna** una cosa che ADR 0029 §4 aveva dovuto dichiarare come
limite: lì `screencapture` crea il file da sé, quindi fra la sua scrittura e il `chmod` del padre
il file può portare per un istante l'umask del processo. Qui il padre scrive, con `O_EXCL` su un
nome temporaneo e poi `rename`, e il file nasce a `0o600`: **quella finestra si chiude.**

Il costo, senza giri: **il testo dello schermo passa dalla memoria del processo di ELA**, che i
pixel non facevano. È limitato — il caso peggiore misurato è 5738 caratteri — e vale per lui la
disciplina che `measure()` già ha: un fallimento porta una dimensione, mai un byte. Il testo non
entra in un messaggio d'errore, non entra in `output`, non entra nell'audit.

## 8. Una lettura che significa due cose va spezzata — il gemello di ADR 0026 §7

`xx-YY` come lingua fa rispondere a Vision **`ok=True` con zero osservazioni**. Una
`ELA_OCR_LANGUAGES` con un refuso produrrebbe quindi, per sempre e in silenzio, «questo schermo
non contiene testo».

Il criterio non è sulle lingue:

> **Una lettura del mondo che può rispondere «non c'è» e «non ho potuto guardare» con lo stesso
> valore va spezzata prima di essere consegnata.** Le due risposte hanno conseguenze opposte — una
> chiude una domanda, l'altra dice di riprovare o di sistemare qualcosa — e un chiamante che le
> riceve unite ha ricevuto un fatto in meno, non uno in più.

È il **gemello di ADR 0026 §7**, e i due si tengono per lo stesso motivo. Là: *un valore che non
può scattare non entra*, perché una difesa che sembra attiva e non lo è è peggio di una difesa
assente. Qui: *un valore che può scattare per due ragioni opposte non esce*, perché una risposta
che sembra un fatto e ne copre due è peggio di nessuna risposta. Nell'un caso il difetto è un ramo
morto, nell'altro un ramo sovraccarico; in entrambi la forma sbagliata è quella che si legge come
se fosse giusta.

**E ELA lo aveva già applicato senza dargli un nome.** È la ragione di `SensorCause` (ADR 0028
§3): `OFF` da solo non esiste, esistono `OFF perché non c'è hardware` e `OFF perché nessuno ha
guardato`. Quel ragionamento era stato fatto su §11 e trattato come una scelta di modellazione;
qui si scopre che vale per **ogni** lettura del mondo. Vale da qui in avanti per ogni percezione e
ogni lettura di contenuto che ELA aggiungerà: `NOT_OBSERVABLE` non è un valore di comodo, è la
metà di questo criterio.

Il figlio interroga `supportedRecognitionLanguagesAndReturnError:` — 30 lingue, 10,6 ms — **prima**
di riconoscere. Restano due significati distinti e nominati: `text.language_unsupported` («ero
configurata male») e un risultato con zero righe («questo schermo non ha testo»), che a quel punto
è una risposta vera.

## 9. Solo `accurate`, e non è una manopola

`fast` costa 20 ms invece di 108 e produce `Nota pl¢¢ols'.18 s¢*denz¥ slitta 812026-04-03`,
confidenza 0,50 contro 1,00. Un livello che sbaglia le cifre di una data e di un importo non è un
compromesso fra velocità e qualità: è un generatore di fatti falsi, che ELA scriverebbe in un
artefatto che poi qualcuno legge. **Una manopola senza un secondo valore buono non è una
manopola.**

## 10. Un artefatto derivato eredita per costruzione, non per memoria

> **Quando nasce un artefatto derivato da una cattura, eredita i vincoli della cattura senza che
> nessuno debba ricordarsene.** Non «gli si applicano le stesse regole»: **sono** le stesse
> regole, perché è lo stesso meccanismo a leggerlo.

| Vincolo | Come si eredita |
|---|---|
| **Stesso posto** | `ELA_CAPTURE_DIR`. Una seconda directory sarebbe un secondo posto da purgare. |
| **Stesso nome** | `<capture_id>.png` e `<capture_id>.jsonl`, lo **stesso stem**. L'id *è* il legame, e non esiste un indice che dica quale testo appartiene a quale immagine. |
| **Stessi permessi** | `0o600`, la costante che `screen.py` importa già. |
| **Stessa scadenza** | letta dall'`mtime` **del PNG**. Se il `.jsonl` usasse il proprio sopravvivrebbe alla sua immagine, che è il bug che questa decisione rende impossibile. |
| **Stessa purga** | `_entries` enumera tutti gli artefatti e li raggruppa per id: quando un id scade, spariscono tutti i suoi file. |
| **Stessi tetti** | `retained()` conta i byte di tutti; `room()` conta gli **id**, non i file, perché il tetto sul numero dice quante schermate ELA sta trattenendo e un OCR non ne aggiunge una. |
| **Stessa regola 35** | §15. |

**E il caso peggiore, che è quello che rende il meccanismo verificabile invece che dichiarato: il
PNG purgato e il `.jsonl` ancora lì.**

> La scadenza di un artefatto **non si legge dal suo `mtime`**: si legge dall'`mtime` della sua
> origine. Un derivato senza origine non ha una scadenza da ereditare, quindi vale
> `ALREADY_EXPIRED` — un istante che è nel passato per qualunque `now`.

La differenza fra «per costruzione» e «per ordine delle operazioni» si vede nel test. Provarlo
facendo girare la purga e osservando che cancella entrambi i file proverebbe che *quella* purga, in
*quell'ordine*, si comporta bene: un riordino la romperebbe in silenzio. Ciò che si prova invece è
la **classificazione**, che è una funzione pura della directory: `retained()` risponde
`ALREADY_EXPIRED` per l'orfano senza che nessuna purga sia stata chiamata, e la purga — che
confronta `expires_at <= now` e nient'altro — non può che prenderlo, qualunque sia il suo `now` e
qualunque sia l'ordine in cui visita i file.

**Perché non un tetto suo:** due tetti separati vorrebbero dire che il testo può sopravvivere
all'immagine o viceversa, e in entrambi i casi ELA starebbe trattenendo metà di una schermata
senza che nessuno l'abbia deciso. Il testo pesa lo 0,2% del PNG (≈ 6 KB contro 0,8–4 MB): non
merita un tetto, merita di viaggiare con quello che c'è.

## 11. Il formato è JSON Lines, e un port nuovo, il ventunesimo

Una riga per riga riconosciuta: `{"text": ..., "confidence": ...}`. La confidenza non è un
ornamento — è la differenza fra «ELA ha letto il tuo schermo» e «ELA ha prodotto `pl¢¢ols'.18`».
Le alternative, e perché perdono:

- **Testo semplice con la confidenza aggregata**: più comodo, e perde la sola informazione che
  dice a un consumatore di quale riga non fidarsi.
- **Testo semplice filtrando sotto una soglia**: scartata per ADR 0028 §5. **Una soglia è una
  decisione**, appartiene a chi decide (§45) e non a chi legge.

Il costo dichiarato: **non è un file che si legge come prosa.**

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `TextRecognitionPort` | §10, §44, §57 | async | `available`, `recognise` |

`available` è un membro suo per la ragione che ADR 0028 diede a `UnsupportedProbe` e ADR 0029 ad
`available`: «ELA su Linux non legge niente» merita di essere una risposta con un nome e un test.
Implementazioni: `VisionTextRecognition` (Darwin) e `UnsupportedTextRecognition`, scelte dal
composition root con lo stesso `platform.system()` di M10.1.

## 12. La `region` è top-left, e la conversione sta nel codice coperto

`regionOfInterest` di Vision è normalizzata con l'origine **in basso a sinistra**. È la convenzione
di un framework; uno schema di capability è vocabolario di ELA, e chi scrive «la metà superiore
dello schermo» pensa in coordinate schermo.

Quindi lo schema è **top-left** e la conversione (`y_vision = 1 − y − height`) sta **nel tool**,
dentro il gate al 100% e con un test. Non nell'adapter: il posto dove si sbaglia un ribaltamento
di coordinate non deve essere il posto che nessun runner copre — un rettangolo capovolto non
solleva, restituisce il testo della metà sbagliata.

Il beneficio è misurato: un quarto dell'immagine sono 2732 caratteri invece di 6956. **La region
non è un'ottimizzazione, è quanto dello schermo diventa testo.**

## 13. La capability, e il secondo `purpose`

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `perception.read_screen_text` | MEDIUM | — | — | sì | `capture_id: string`, `purpose: string` | `region: object` |

- **MEDIUM**, per la ragione di ADR 0029 §6 letta un passo avanti: là il contenuto **nasceva**;
  qui viene **reso leggibile**. Un PNG con cinque minuti di vita e un file di testo cercabile
  nella stessa directory non sono lo stesso rischio, e il secondo non è il minore: il testo è ciò
  che sta in un prompt, in un incolla, in un `grep`.
- **Nessuno scope**, per la ragione di ADR 0029 §6: un id di cattura è un UUID e lo scope del
  Guardian è a forma di percorso.
- **`prompt_arguments = ("purpose",)`** e non `capture_id`: la domanda deve dire *per cosa*, e un
  UUID non lo dice.

**Un secondo `purpose` non è una domanda doppia.** La tentazione è dire che chi ha approvato la
foto ha approvato la lettura. È §30 generalizzata a dire il contrario — *un «sì» vale solo se la
domanda era completa* — e «fotografo lo schermo per allegarlo al ticket» e «leggo il testo di
quello schermo per cercarci un codice» sono due atti con due conseguenze. §57 vuole sapere il
*perché* di entrambi.

`catalogue_v01()`, `tools_v01()` e `verifiers_v01()` restano come sono (ADR 0029 §13): **v0.1 non
si ripiega, si affianca.**

## 14. Il verifier, e un timeout che non eredita un rapporto

| Condizione | Cosa controlla |
|---|---|
| `text.exists` | al nome dichiarato c'è un file regolare, non un link, dentro lo store, ed è JSON Lines leggibile |
| `text.matches` | byte, sha256, righe e caratteri riletti dal disco sono quelli che il risultato dichiara |

Rilegge con lo stesso codice che ha scritto e **non riconosce niente**: verificare non è rifare. E
non può: il suo costruttore prende una directory e una ritenzione, quindi non ha un riconoscitore
da chiamare — la proprietà è strutturale e non disciplinare.

**Il limite, con la franchezza di ADR 0029 §9:** non può dire che il testo è quello che c'era
sullo schermo. Servirebbe un secondo OCR con cui confrontarlo, che è rifare. §20 chiede che
l'esecuzione non sia presa per prova del successo; non chiede un oracolo.

**Il timeout è `ELA_OCR_TIMEOUT_SECONDS` e vale 10 s, misurato il 2026-09-08 su questa macchina**
— 10 core, macOS 26.6 (25G72), display 2940 × 1912 — e dove è stato misurato è parte del numero.

**Il rapporto ≈ 57× di ADR 0028 §6 e ADR 0029 §14 non viene ereditato, e questa milestone ha
dimostrato perché non è una legge.** Quel rapporto era stato scelto due volte su letture che non
degradano sotto carico — una sonda da 35 ms, una cattura il cui lavoro è di `WindowServer` — e
applicarlo alla mediana a riposo qui darebbe 13 s partendo dalla base sbagliata.

> **Un rapporto fra timeout e mediana non è una costante del progetto: dipende da chi fa il
> lavoro.** Quando il lavoro è di un demone di sistema, la mediana a riposo descrive anche il caso
> carico. Quando è nel processo di ELA, non lo descrive, e un timeout derivato per analogia
> sarebbe un numero preso in prestito da una misura di qualcos'altro. Ogni timeout nuovo si misura
> sul proprio lavoro, sotto il carico che quel lavoro incontrerà.

La base è quindi il caso peggiore **sotto carico**, 2,96 s, e 10 s lascia 3,4× per un display più
grande di questo. Non serve un `..._IS_MEASURED`: il segnaposto di ADR 0029 §14 esisteva perché
mancava un permesso, e qui l'OCR non ne chiede.

## 15. La regola 35 si estende **prima** del codice che produce il testo

`Regole aggiunte:`

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 36 `perception-reads-no-window-titles` | nessun modulo dell'adapter nomina mai `kCGWindowName` | `ela.infrastructure.perception` | nessuna esenzione |

`Regole estese:`

| Regola | Come cambia | Perché |
|---|---|---|
| 33 `perception-children-import-only-stdlib` | rinominata al plurale, e il soggetto si **deriva** invece di essere un file nominato | un secondo figlio nostro, e una lista è una cosa che si dimentica (§6) |
| 35 `capture-stays-on-the-machine` | da due moduli a cinque: `screen_text`, `textrecognition`, `vision` | il testo è più facile da mandare via del PNG |

**L'ordine è parte della decisione, non una preferenza di processo.** La regola 35 è stata estesa,
col suo caso negativo, **nel commit precedente** a quello che introduce il codice che produce il
testo. Una difesa scritta dopo la cosa che difende ha una finestra in cui la cosa esiste e la
difesa no, e in quella finestra la revisione guarda il codice nuovo e non l'assenza della regola.

Il vincolo di ADR 0029 §12 è stato **riaperto, esaminato e confermato**: non esce niente — né i
pixel, né il testo, né l'elenco delle app.

`Soggetti rimossi:` — la riga di ADR 0027 §5, tolta qui perché la tabella cambia (ADR immutabile).

| Costante | Parola | Perché esce |
|---|---|---|
| `PERCEPTION_PROBE` | `ARTEFACT` | la regola 33 smette di nominare un file e deriva il suo soggetto dal `__main__` guard: la costante non esiste più (§6) |

## 16. Due milestone che non sono questa

**«OCR della sola finestra in primo piano» è una milestone sua.** Servirebbe mappare i `Bounds` di
`CGWindowList` sui pixel del PNG attraverso il fattore di scala Retina (2940 pixel per 2560 punti
su questa macchina) e l'origine del display in un arrangiamento multi-monitor, dove le origini
possono essere negative e i fattori di scala diversi fra loro.

> Un calcolo di coordinate che sbaglia **non fallisce**: restituisce un rettangolo, e ELA
> consegnerebbe **l'OCR della finestra sbagliata** con la stessa faccia con cui consegna quello
> giusto. Un testo che dice di venire dalla finestra di Mail e viene da quella accanto è peggio di
> nessun OCR: nessun OCR si vede, questo no.

E il PNG non porta con sé né il fattore di scala né l'origine del display — è un file con un IHDR
— quindi quella milestone dovrà decidere che cosa una cattura debba **ricordare** di come è stata
presa. È una decisione, non un calcolo.

## 17. Il vincolo multimodale, con le quattro domande già formulate

Registrato perché chi lo riaprirà trovi le domande e non debba inventarle.

| Domanda di §57 | Come si pone su una cattura dello schermo |
|---|---|
| **Quale provider** | Quale provider concreto riceve i pixel, con quale modello, in quale regione, sotto quale contratto di ritenzione. Non «il router»: il router sceglie, e una scelta che varia non è una risposta. Se la rotta può cambiare a runtime, la risposta è «quale provider **può** riceverli», che è un insieme e va dichiarato. |
| **Quale tipo di dati** | Lo schermo **intero**, non una regione: se c'è un password manager aperto, è nel PNG. Va detto che il dato è indiscriminato per costruzione. |
| **Perché viene inviato** | Quale domanda ELA sta ponendo che l'OCR locale **non** può rispondere. Questa milestone alza la soglia di proposito: dopo M10.3, «capire cosa c'è scritto» non è più una ragione valida. Restano le domande sul *significato* di un'interfaccia, e vanno nominate una per una. |
| **Quale policy lo consente** | Quale `Authorization` o approvazione copre l'invio, con quale TTL e quale scope — e se un `purpose` di cattura possa mai coprire un invio. La risposta di questa milestone alla domanda analoga (§13) è: **serve un consenso suo**. |

I costi, misurati: **~4675 token visivi ≈ $0,023 a cattura** (2940 × 1912 ridimensionata dal tier
ad alta risoluzione a ≈ 2368 × 1540), contro **~130 token** per il testo dello stesso schermo —
**circa 36 volte**. E `ProviderRequest.input` è oggi `str`: il multimodale non è una capability in
più, è un cambio di forma del port, del dominio, del payload del provider e del pricing.

**Il vincolo:** l'invio di una cattura o del suo testo a un provider esterno **rompe la regola 35**
e non si fa finché non esistono le quattro risposte sopra **e** un consumatore che abbia una
ragione per pagarne il prezzo. Oggi non esiste nessuno dei due.

## 18. Niente audit nuovo, niente rotte nuove

L'esecuzione è già tracciata da `PERMISSION_DECIDED`, `TOOL_EXECUTED` e `STEP_*`. La famiglia
`APPLICATIONS` scrive **zero** eventi, per il criterio di ADR 0028 §10 — *l'audit registra ciò che
ELA decide, non ciò che il mondo fa* — e un utente che apre Mail non è una decisione di ELA.

`GET /perception` e `ela perception` guadagnano i tre campi; l'OCR si raggiunge con `POST /tasks`,
`/approvals` e `/tasks/{id}/results`, che esistono. `/diagnostics` non cambia forma:
`captures.bytes` ora include gli artefatti derivati, che è la risposta più vera alla domanda che
già poneva.

## Alternative considerate

- **Includere i titoli delle finestre.** Scartata: contenuto, stesso permesso di uno screenshot, e
  una seconda capability per un valore che l'OCR copre dalla stessa immagine.
- **Una tupla di due figli per la regola 33.** Scartata: una lista è una cosa che si dimentica di
  aggiornare, e la regola sarebbe andata muta sul file che ne aveva bisogno (§6).
- **Il livello `fast`, come opzione con un default.** Scartata: misurato illeggibile (§9).
- **Testo semplice invece di JSON Lines**, con o senza soglia di confidenza. Scartate: la prima
  perde l'unica informazione che dice di quale riga non fidarsi, la seconda decide una soglia al
  posto di chi decide (§11).
- **Un `region` in coordinate bottom-left**, come il framework. Scartata: uno schema di capability
  è vocabolario di ELA, non di Vision (§12).
- **Un tetto suo per gli artefatti derivati.** Scartata: permetterebbe al testo di sopravvivere
  all'immagine (§10).
- **Leggere l'`mtime` del `.jsonl` per la sua scadenza.** Scartata: è precisamente il bug che
  questa milestone esiste per rendere impossibile (§10).
- **Un `text.store_full`.** Scartata: i tetti contano le schermate, e leggerne una non ne aggiunge
  una — sarebbe un codice che non può scattare (ADR 0026 §7).
- **La geometria per finestra nella famiglia.** Scartata: nessun consumatore, quindi uno stub.
- **`localizedName` invece del bundle identifier.** Scartata: è localizzato, e il rilevatore
  scatterebbe al cambio di lingua del sistema (§2).
- **Chiedere l'Accessibilità.** Scartata: un permesso nuovo e molto più potente, che appartiene a
  §20 e non a §10.
- **Ereditare il rapporto ≈ 57× per il timeout.** Scartata, e la ragione è una misura: l'OCR
  degrada sotto carico e la cattura no (§14).

## Conseguenze

- ELA sa quali applicazioni l'utente sta usando **senza chiedere niente a nessuno**, e sa che cosa
  c'è scritto in una cattura che ha già fatto **senza che un pixel o un carattere lascino la
  macchina**.
- Il vincolo di ADR 0029 §12 è stato riaperto, esaminato e **confermato**, e le quattro domande di
  §57 sono scritte per chi lo riaprirà davvero.
- Il contenuto derivato ha una scadenza che **non può** superare quella della sua origine, e la
  proprietà è una classificazione invece che un ordine di operazioni.
- La regola 33 smette di nominare un file: i soggetti dichiarati passano da quattro a **tre**, e
  il quarto è diventato derivabile.
- Le regole di architettura passano da trentacinque a **trentasei**, e i contratti di
  import-linter restano **tredici**: la 36 guarda un letterale, non un import.
- I port passano da venti a **ventuno**.
- Le capability di produzione passano da quattro a **cinque**; quelle di v0.1 restano **tre**.
- Le famiglie di percezione passano da tre a **quattro**; i figli dell'adapter da uno a **due**.
- Rotte e comandi non cambiano.

### Vincoli dichiarati, da riaprire quando serviranno

- **Non esce niente** (§15, §17): né i pixel, né il testo, né l'elenco delle app.
- **Un artefatto derivato eredita i vincoli della sua origine per costruzione** (§10). Criterio
  generale.
- **Una lettura che può rispondere «non c'è» e «non ho potuto guardare» con lo stesso valore va
  spezzata prima di essere consegnata** (§8). Criterio generale, gemello di ADR 0026 §7.
- **Un rapporto fra timeout e mediana dipende da chi fa il lavoro** (§14). Criterio generale.
- **I titoli delle finestre non si leggono** (§2, §3), ed è una regola.
- **L'Accessibilità non si chiede** finché non sarà §20.
- **«OCR della sola finestra in primo piano» è una milestone sua** (§16), e dovrà decidere che
  cosa una cattura ricorda di come è stata presa.
- **Nessun trigger automatico** (ADR 0029 §8): si riapre col Proactive Core, §34.
- **Solo `accurate`** (§9), finché `fast` non smetterà di sbagliare le cifre.
- **Un OCR per cattura, e nessuna cache**: due letture rifanno il lavoro. A 232 ms un secondo
  indice costerebbe più di quanto risparmia.
- **Nessuna cifratura a riposo e nessuna redazione**, invariato rispetto ad ADR 0029: il testo di
  un password manager aperto finisce nel `.jsonl` come i suoi pixel finivano nel PNG.
- **Nessun backoff** su un Vision che fallisce, come per la cattura.
