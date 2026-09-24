# 0040. Il nodo Windows: la piattaforma la sceglie la composizione, il segreto sta sotto l'ACL della cartella, e un nodo dichiara solo ciò che la sua macchina sa fare

- **Stato:** Accettata il **2026-09-18**, quando la prova a mano sul PC è passata — il criterio di
  fine di M12.4 — e con lei `GETTING_STARTED.md` §12, che porta ora gli output veri. SPEC di M12.4
  approvata dall'utente il 2026-09-15, fatte M12.3c e le misure sul PC (P0–P6, P1-bis, P3-bis,
  P6-bis); implementata il 2026-09-17 a blocchi, ciascuno approvato da una review — dec. B, D, F, G,
  la regola 54, dec. H, dec. I —, e il contenuto approvato dalla review dello stesso giorno. Le
  decisioni ereditate sono D1–D20 di M12.1, A–P di M12.2 e A–M di M12.3. La prova non ha smentito
  niente; due sue parti non sono state fatte, e sono qui fra i vincoli dichiarati. I numeri di dec. J
  stanno in `docs/milestones/M12.4.md`. §5, il meccanismo dell'attesa: il caso del nipote che tiene
  la pipe è riparato da ADR 0047 §13, per ogni chiamante del lanciatore.
- **Data:** 2026-09-17 (accettata il 2026-09-18)
- **Riferimenti spec:** §4, §9, §16, §17, §48, §56, §57
- **Continua:** ADR 0023 §10; ADR 0028 §1; ADR 0029 §3, §16; ADR 0031 §3, §5, §6; ADR 0033 §9;
  ADR 0034 §5, §7; ADR 0037 §2, §7; ADR 0038 §11, §12, §14; ADR 0039 §1, §6, §7.
- **Estende:** ADR 0002 (una regola nuova, la 54; una stretta, la 40), ADR 0037 §7 (dove un nodo
  Windows tiene il segreto, che lì restava in bianco), ADR 0039 §1 («un modulo e non un ramo», letto
  per tre scelte e non per una), ADR 0023 §10 (i codici d'errore sul filo diventano un vocabolario
  chiuso, §7).

## Contesto

ADR 0039 ha messo il codice di un nodo in `src/ela/node/` e ha promesso che il secondo sistema
avrebbe aggiunto **un modulo e non un ramo**. Il nodo di M12.3 girava sulla stessa macchina del Core,
e ha dichiarato fra i suoi vincoli che così nascondeva tre accoppiamenti: lo stesso `.env`, la stessa
tabella di rotte, la stessa chiave. M12.4 porta il nodo su un PC Windows, con il Core sul Mac e la
tailnet in mezzo.

Il ciclo non cambia: arruolarsi, leggere la propria riga, annunciarsi, chiedere, eseguire, consegnare,
rinnovare. Cambia ciò che la macchina sa fare, e la ricognizione ha trovato che su macOS quattro righe
erano vere per caso: lo scrittore del segreto chiamava `os.fchmod`, che Windows su Python 3.12 non ha;
il nodo dichiarava `"os": "MACOS"` come letterale; un nodo dichiarava tool che la sua macchina non
sapeva eseguire; e l'audio senza nome della voce online è POSIX da cima a fondo. Nessuna delle quattro
si vedeva da un runner, perché nessun runner era Windows.

E una decisione presa prima del codice Windows, perché il secondo lato del filo la rendeva urgente: il
vocabolario dei codici che l'API manda e il nodo legge (§7).

## 1. La piattaforma la sceglie la composizione, nominando il sistema

La piattaforma decide **tre** cose di un nodo, non una: la dichiarazione (`os`), il modo di proteggere
il segreto, e la voce — con il riproduttore della voce online. Tutte e tre le sceglie `build_node`, per
il sistema che gli si **nomina** (ADR 0031 §3: una scelta di piattaforma si prova nominando il
sistema, mai essendolo), con `platform.system()` come default di `system=`; e sempre per il sistema
nominato sceglie, da M12.3c, il lettore dell'alimentazione. Il nodo riceve tutto già scelto in
`NodeWorld`. Il valore di dominio di `os` viene dalla stessa mappa con cui
il Core dichiara `local` (`ela.devices.local.operating_system`), non da una seconda lista.

**Chi sceglie scrive, e scrive una volta.** Il riproduttore della voce online è `online_player(system)`
— `afplay` su Darwin, nessuno altrove — e lo chiedono sia `build_node` sia il kit di conformità che
deve sapere se fingerne uno: una prima stesura faceva ridire al kit «Windows: nessuno», ed era una
seconda lista che poteva diventare falsa senza che nessuno se ne accorgesse.

**Un nodo non chiede alla macchina che macchina è** — la regola 54. Sotto `ela.node` nessun import di
`platform`, nessun `sys.platform`, `os.name` o `sys.version_info`, e nessun `getattr` o `hasattr` sul
modulo `os`: la forma sbagliata più probabile non è `platform.system()` ma «`os` ha `fchmod`?», e ce
n'era una, nello scrittore del segreto, fino a §2. La regola è nata senza esenzioni.

## 2. Il segreto su Windows: un file, sotto l'ACL della cartella

La decisione di ADR 0039 §6 resta: `~/.ela/node.json`, due campi, `O_EXCL`, mai stampato, fuori
dall'albero. Cambiano **come** si protegge, **in che ordine** nasce la cartella, e **perché** non il
portachiavi.

**Un modo, scelto dalla composizione, e uno scrittore solo.** `PermissionMode.BITS` su Darwin e Linux:
il file nasce con `O_NOFOLLOW` e `fchmod(0o600)` prima del primo byte. `PermissionMode.ACL` su Windows:
il file nasce con `O_EXCL` e nient'altro, e l'accesso lo porta l'ACL **ereditata** da una cartella che
esiste prima di lui. Lo scrittore non ha un modo di default: chiamato senza, era la riga che cadeva sul
PC — P1 (2026-09-15) ha visto l'`AttributeError` di `os.fchmod` a quella riga ventitré volte, dopo
che `O_EXCL` aveva creato il file e prima del suo primo byte. Che cosa ne segue in produzione — l'identità
coniata dal Core non scritta da nessuna parte, e ogni avvio successivo davanti a un file vuoto — è
dedotto dal codice, non visto.

**La cartella di stato nasce per prima**, con `mkdir(0o700)`, prima di qualunque cosa dentro di lei
(M12.3b). Su Windows è la condizione perché l'ACL protetta esista: Python dalla 3.12.4 applica a
`mkdir(path, 0o700)` un DACL protetto — SYSTEM, Administrators, OWNER RIGHTS, niente ereditato
(CVE-2024-4030) — **soltanto** alla cartella creata con quel modo, non ai genitori di un
`parents=True`. Misurato sul PC: P2 con `icacls` il 2026-09-15, e lo smoke test del criterio 9 il
2026-09-17 sull'SDDL vero — sul percorso di `build_node` e `join_or_read`, la cartella con il flag `P`
e le tre voci e il file con le stesse tre ereditate; e, a parte, una cartella nata come genitore di un
`mkdir(parents=True)` che quell'ACL non ce l'ha.

**Un rifiuto all'avvio, ed è la sola garanzia.** Su Windows la composizione rifiuta un Python anteriore
alla **3.12.4** con un `ConfigurationError`, **prima** che la cartella di stato esista: prima di quella
versione il modo è ignorato in silenzio, e una cartella fatta così resterebbe con l'ACL ereditata dal
profilo. Il progetto non sceglie il Python del PC — `uv` usa la 3.12 che trova, e sul PC di M12.4 ha
trovato una 3.12.10 che non aveva installato (P0) —, quindi il rifiuto è la garanzia e non una
cautela. La parte che decide è una funzione pura della versione, `mkdir_applies_the_acl`, e la
composizione la riceve per parametro (`python_version=`): la versione si nomina, l'interprete non si
patcha (ADR 0031 §5).

**Non DPAPI, non Credential Manager — e la ragione non è quella del Mac.** Su macOS il portachiavi
riconosceva il binario. Su Windows no: sul PC una copia dell'interprete e `powershell.exe` hanno riletto
il blob DPAPI con la stessa impronta, `a84a49c9df78073f` (P2, 2026-09-15). Nessuno dei due restringe
quindi il segreto ai processi di un binario: ogni processo dell'utente lo legge, come legge un file
sotto l'ACL della cartella — misurato per DPAPI, e per Credential Manager lo dice la documentazione
(`CredReadW` non ha un parametro sul chiamante). Ciò che aggiungono — la protezione da una copia offline
del disco — non è la minaccia di M12.1 D5, che è `git add -A`; costerebbero `ctypes` nel processo del nodo
o un figlio a ogni avvio; e un reset della password da amministratore lascerebbe un segreto
illeggibile dietro un file che `O_EXCL` non lascia riscrivere.

## 3. La voce di un PC: System.Speech attraverso `powershell.exe`, con la frase su stdin

`say` non esiste su Windows. La voce locale è `SapiSpeechCommand`, in
`ela/infrastructure/machine/windows.py` accanto al lettore dell'alimentazione di M12.3c: un binario del
sistema a un percorso **letterale** — `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`,
non `%SystemRoot%`, perché una variabile d'ambiente è una porta —, figlio del nodo, ucciso se sfora.
La composizione lo sceglie per il sistema `Windows`. Su un Windows installato altrove il binario non
c'è: `available()` risponde no, il nodo non dichiara la voce, e l'alimentazione vale `UNKNOWN` — il
guasto si vede in ciò che il nodo promette, non in un errore.

**La frase non passa mai per la riga di comando**, che su Windows ogni processo dell'utente legge come
`ps` su macOS. Lo script è una costante in chiaro, codificata per `-EncodedCommand` al momento
dell'avvio e uguale per ogni frase; il nome della voce e la frase arrivano su stdin in UTF-8, e lo
script li legge come dati. La primitiva è `spawn_with_input`, sorella di `spawn`, con gli stessi
`_wait` e `_kill`: `asyncio` ordinario, provato con un figlio Python sui runner di `make check`, Ubuntu
e macOS. Sul job Windows non gira — `tests/infrastructure/machine/test_spawn.py` non è nell'elenco —,
e con il Proactor l'ha esercitato la prova a mano (§5).

**Ciò che si cronometra è il suono.** `spoken_seconds` è il cronometro che lo script mette intorno a
`Speak` e scrive su stdout nella cultura invariante, non la vita del figlio: sul PC, sulla frase di 40
caratteri, il figlio è vissuto 0,55 s e 1,43 s più del cronometro dello script (P3, P3-bis) —
sovraccarico sopra il pavimento del verifier per ogni frase sotto i cento caratteri —, e un figlio che
uscisse `0` senza parlare passerebbe. Un `exit 0` senza un
numero — o con `nan`, un negativo, una virgola che il nostro script non scrive — non ha durata, e lo
rifiuta la verifica. Uno sforamento lo decide l'orologio del tool, non l'`exit 1` che
`TerminateProcess` lascia, e non ha durata nemmeno lui, diversamente da `say`, per cui la vita del
figlio **è** la misura.

**stderr è una diagnosi, mai una decisione, e resta sulla macchina.** Il figlio eredita lo stderr del
nodo: la riga di `SelectVoice` per una voce che non c'è compare nella finestra del PC, e il chiamante
non la riceve — non decide, non si salva, non viaggia verso il Core. Decide l'exit code.

**La regola 40 si stringe e cambia forma.** System.Speech ha tre modi di mandare una frase altrove che
all'altoparlante — `SetOutputToWaveFile`, `SetOutputToWaveStream`, `SetOutputToAudioStream` —, e sono
righe **dentro** uno script, mai costanti intere: la regola li cerca per sottostringa nelle costanti di
stringa dei moduli della voce, fra cui ora `windows.py`. Con il confronto per costante intera un caso
negativo scritto come letterale isolato sarebbe passato, e lo script vero sarebbe rimasto invisibile.

**La voce del PC di M12.4 è «Microsoft Elsa Desktop»**, l'unica `it-IT` che SAPI 5 elenca lì; le voci
OneCore ci sono e SAPI 5 non le vede. Il timeout resta **60 s** fissi: 600 caratteri con Elsa valgono
45,703 s del figlio (P3-bis, 2026-09-15).

## 4. Un nodo dichiara solo ciò che la sua macchina sa fare

All'avvio il nodo chiede `available()` alla metà di macchina di ogni voce e dichiara solo i tool che
rispondono sì. I tool restano **costruiti** tutti e quattro — un ordine che arriva risponde come ha
sempre risposto —, cambia ciò che si **promette**: l'orchestratore filtra per nome, e senza questo un
nodo avrebbe promesso una voce che la sua macchina rifiuta.

| Sistema nominato | Voce locale | Riproduttore della voce online | Il nodo dichiara |
|---|---|---|---|
| Darwin | `say` | `afplay` | i quattro tool, se `say` e `afplay` ci sono |
| Windows | System.Speech | nessuno | `core-echo`, `model-complete`, e `voice-speak` se `powershell.exe` c'è |
| Linux | nessuna | nessuno | `core-echo`, `model-complete` |

**La voce online non viaggia sul nodo Windows.** Su Windows non esiste un riproduttore che legga un
MP3 da memoria senza file o senza WinRT; `SoundPlayer` legge un WAV da uno `Stream`, ma chiederne uno è un secondo
formato accanto all'unico di ADR 0034, e una seconda derivazione della durata. Il tool resta costruito,
e senza chiave dice ancora che manca la chiave **prima** di dire che manca il riproduttore (la
correzione del 2026-09-09). «Nessun riproduttore» è `binary=None` in `OnlineSpeechCommand`: un valore,
non un'omissione, che risponde no su ogni runner senza chiedere al filesystem.

**L'interruttore dell'utente non entra.** Con `ELA_VOICE_ENABLED=false` il tool resta dichiarato e
rifiuta con `voice.disabled`: un interruttore è una scelta e non un fatto della macchina, e `voice.disabled`
nomina l'interruttore, dove «nessun nodo idoneo» lo nasconderebbe (ADR 0033 §9).

## 5. Come resta vivo, e dove si prova

**Il terminale, per la ragione che su Windows resta.** Delle due ragioni di M12.3 per il comando in
primo piano, su Windows non vale il muro della firma — Windows non chiede permessi per la voce e,
misurato, non lega il segreto al binario —, e vale l'altra: il nodo vive quanto il Core che lo usa, e un nodo che ripartisse da solo con
il Core spento sarebbe un processo che chiede lavoro a nessuno. Misurato sul PC (P4, 2026-09-17):
`Ctrl-C` su un `await` fermo in I/O con il Proactor esce con `0`; la finestra chiusa con la X lascia nel
log la sola riga d'avvio, né `finally` né `atexit`; e sotto `uv.exe` ci sono due `python.exe`, perché
quello del venv è un lanciatore — e un `TerminateProcess` sul processo che si vede, per documentazione,
non uccide l'interprete sotto di lui.

**Le tracce della sonda.** La sonda di P4 uccideva il figlio senza aspettarlo, e in chiusura Python
stampava due `Exception ignored` del transport. `_kill` aspetta il figlio dopo averlo ucciso, e in
CPython 3.12.10 quell'attesa si sveglia dopo la chiusura del transport: il nodo **non le lascia**.
Sul Mac la forma della sonda lascia la traccia Unix analoga e quella di ELA nessuna; sul Proactor
l'ha misurato la prova a mano del 2026-09-17, con un `Ctrl-C` sul nodo mentre parlava (§5). L'attesa non copre due casi: un figlio che esce da
solo nell'istante della cancellazione, che ha già il codice d'uscita prima che la sua pipe sia chiusa,
e un secondo `Ctrl-C` durante la chiusura, che interrompe l'attesa stessa.

**Tre livelli di prova, e il nome di ciascuno dice fin dove arriva.**

1. **Sui runner di `make check`**, Ubuntu e macOS. Le tredici storie del contratto passano con **tre**
   kit: il finto, il reale che nomina Darwin, il reale che nomina Windows — lo stesso driver, un sistema
   diverso —, e la mappa `UNSUPPORTED` del terzo è vuota. Sul job Windows il kit Darwin è saltato, con
   la sua ragione: scrive il segreto con `BITS`. **Il kit Windows non prova Windows**: prova il ciclo sotto la
   composizione di un PC; su un Mac lo scrittore `ACL` gira su un filesystem POSIX e `powershell.exe`
   non esiste.
2. **Sul PC, dichiarato.** Smoke test con `skipif(platform.system() != "Windows")`: l'SDDL della
   cartella e del segreto, lo speaker che dice una sillaba, il lettore dell'alimentazione. Passati sul
   PC il 2026-09-16 e il 2026-09-17.
3. **In CI.** Un job `windows-latest` accanto alla matrice di `make check`, con un elenco nominato —
   `tests/node`, `tests/conformance`, `tests/composition/test_build_node.py` —, senza `make` e senza
   gate di copertura, con il `core.autocrlf` del runner — che è sicuro perché `.gitattributes` fissa
   `eol=lf` per ogni file di testo, e `tests/docs/test_line_endings.py` lo chiede a `git ls-files
   --eol` —, e con gli skipped nominati nel riepilogo. Il
   primo run (`35237077806`) è stato **rosso per una ragione nominata**: un test che nominava Darwin
   faceva girare il writer `BITS` su Windows; il secondo (`35239701097`) verde, 137 passati e 23 saltati
   ciascuno con la sua ragione.

**Una parte della prova non la fa nessuna suite**, ed è `docs/GETTING_STARTED.md` §12: il Core sul Mac,
il nodo sul PC, la tailnet in mezzo, il PC che parla con il Mac staccato dalla corrente. **Passata il
2026-09-17**: il PC ha parlato con la voce di Elsa e `powershell.exe` è nato sotto il nodo, attraverso
`uv.exe`, `ela.exe` e i due `python.exe`; il Core spento a metà frase non ha perso la busta; `Ctrl-C`
sul nodo mentre parlava ha fermato la voce ed è uscito con `0`, senza tracce; e la nota è rimasta al
Mac, con il PC che portava più punti e due rifiuti, `MISSING_TOOL` e `UNVERIFIABLE`.

## 6. Le regole

| N | Regola | Soggetto | Vincolo |
|---|---|---|---|
| 40 | La voce non scrive su file | i moduli della voce, fra cui ora `infrastructure/machine/windows.py` | nessun flag di `say` che scriva, e nessuno dei tre metodi di System.Speech che mandano altrove, cercati per sottostringa |
| 54 | Un nodo non chiede alla macchina che macchina è | tutto `node/` | nessun `platform`, `sys.platform`, `os.name`, `sys.version_info`; nessun `getattr` o `hasattr` sul modulo `os` |

La 37 non si tocca: la scelta in `build_node` resta un'istruzione, ora a tre rami. La 32 non si tocca,
ed è il punto: lo speaker avvia un figlio da `ela.infrastructure.machine`, e lo scrittore del segreto
non avvia niente e non carica `ctypes`.

**I limiti delle due regole, scritti nei loro docstring.** La 54 legge nomi: un `try: os.fchmod(...)
except AttributeError` fa la stessa domanda e non si vede, e un rivelatore che lo vedesse leggerebbe
ogni `except AttributeError` del package; e `os` o `sys` importati con un altro nome passano. La 40
legge costanti: uno script composto a pezzi, `"SetOutputTo" + "WaveFile"`, passa.

## 7. Il vocabolario dei codici sul filo

Un client ramifica su `error.code` (ADR 0023 §10), e un nodo lo fa esattamente dove lo stato non
distingue due risposte: i due `409` di una consegna (ADR 0038 §12). Fino a M12.4 il codice era una
stringa scritta dove serviva — nella tabella dell'API, nelle costanti del nodo, nei test del nodo — e
niente le confrontava: i test del nodo scriptavano tre codici che nessun Core ha mai mandato,
`renewal.capped`, `too_late` e `code_reused`, e passavano. Tre codici falsi nello stesso file sono una
lista che non sa di essere falsa, non tre sviste.

**Una lista sola: `ela.ports.WireCode`**, uno `StrEnum` di diciassette membri. Sta in `ela.ports`
perché è l'unico posto che i contratti fanno importare a entrambi i lati — `ela.api` ed `ela.node`
raggiungono `ela.ports`, ed `ela.ports` non raggiunge altro che il dominio (contratto 2) —; le port
restano venticinque, perché si contano i `Protocol` e non i codici.

**Onesta nei due versi**, per test (`tests/api/test_wire_codes.py`) e non per regola: **ogni codice che
l'API emette è un membro** — `problem()` accetta solo un `WireCode`, ed è chiamato in due posti soli,
il gestore della tabella e il `401` del middleware —, e **ogni membro è emesso da qualcuno**, perché un
membro che nessuno manda è un ramo che un client può scrivere e nessuna risposta può prendere. Il nodo
confronta `WireCode.DELIVERY_CONFLICT`; i suoi test scriptano un rifiuto con un membro, e lo status lo
ricavano dalla tabella stessa dell'API, così non esistono né un codice inventato né uno status che il
Core non gli associa. I codici dei **tool** — `provider.*`, `speech.*`, `verification.*` — restano fuori:
viaggiano dentro un risultato, come sua parola, e non come risposta a una richiesta.

## Alternative considerate

- **DPAPI o Credential Manager.** Scartati (§2): non restringono il segreto ai processi di un binario —
  misurato per DPAPI, documentato per Credential Manager —, e costano una porta.
- **Un oggetto-macchina per sistema**, `MacosMachine` e `WindowsMachine`. È la scelta in composizione
  con un tipo in più, e un tipo per due valori precede il terzo caso — che per M12.5 non è un sistema
  operativo ma uno Shortcut.
- **La voce con WinRT, o con una libreria che carica COM nel processo del nodo.** WinRT produce uno
  stream e non suona, e da PowerShell 5.1 chiede interop asincrona scritta a mano; una libreria nel
  processo è `ctypes` fuori da `ela.infrastructure.machine` (regola 32, ADR 0029 §3).
- **La vita del figlio come `spoken_seconds`**, come per `say`. Scartata (§3): il sovraccarico del
  figlio sul cronometro dello script supera il pavimento del verifier, e un figlio muto passerebbe.
- **stderr nel risultato**, con un campo in `RawSpeech`. Scartata il 2026-09-17: porterebbe al Core testo
  scritto da un figlio, e cambierebbe dominio e tool per una diagnosi che serve a chi sta alla macchina.
- **La voce online con `SoundPlayer` e un WAV.** Scartata in M12.4 (§4): è una decisione di ADR 0034 —
  un secondo formato e una seconda durata —, non un adapter.
- **Un'attività pianificata o un servizio**, invece del terminale. Scartati (§5): un nodo che riparte
  da solo con il Core spento, e un servizio gira in Sessione 0, dove — dedotto, non misurato — non ha
  l'audio.
- **`make check-windows`** sulla forma di `make check-linux`. Scartato: fingere Windows su macOS farebbe
  girare gli adapter su un filesystem POSIX, e proverebbe meno di quanto il suo nome dica.
- **Il kit che dice da sé se il sistema ha un riproduttore.** Scartato dalla review del 2026-09-17
  (§1): una seconda lista scritta a mano.
- **Il vocabolario del filo come regola di architettura**, o in `ela.api`. Una regola leggerebbe nomi
  e non saprebbe che cosa l'API emette davvero; in `ela.api` il nodo non potrebbe importarlo (§7).

## Conseguenze

- Un PC Windows può essere un nodo con lo stesso ciclo del Mac: si arruola, dichiara `WINDOWS`,
  protegge il segreto con l'ACL della cartella, e parla con System.Speech — e non decide niente. Le
  suite e gli smoke test sul PC ne provano le parti; il ciclo intero con due macchine lo prova
  `GETTING_STARTED.md` §12, passata il 2026-09-17 (§5).
- Le tredici storie del contratto passano con **tre** kit, e le mappe `UNSUPPORTED` sono tutte vuote.
- Le regole di architettura passano da cinquantatré a **cinquantaquattro**; una si stringe (40).
- Le rotte dell'API **restano ventinove**, quelle che un nodo può chiamare **sei**; i comandi della CLI
  **ventisei**, le specie di comando **tre**.
- I contratti import-linter restano **quattordici**, nessuno modificato: nessun package nuovo.
- Le capability di produzione **restano otto**, e le port **venticinque**.
- `build_node` ha **sei** parametri dichiarati: l'orologio, le due voci, il sistema, l'alimentazione e
  la versione di Python.
- La CI ha un terzo job, `windows-latest`, per la suite del nodo e soltanto per lei.
- Il repository fissa i fine riga, `.gitattributes` con `eol=lf`: su un clone Windows con il default
  di Git ne sarebbero stati convertiti 598 su 629 (P0, 2026-09-15).
- `nodes/windows/README.md` punta a `src/ela/node/`, come i due di ADR 0039 §1.
- I codici d'errore sul filo sono un vocabolario chiuso, `ela.ports.WireCode`, che l'API e il nodo
  importano tutti e due (§7).

### Vincoli dichiarati, da riaprire quando serviranno

- **Il segreto di un nodo Windows ha il confine dell'utente**: l'ACL della cartella lo lascia leggere a
  SYSTEM, Administrators e al proprietario, come `root` legge un `0o600` su macOS (§2; smoke SDDL,
  2026-09-17). DPAPI e Credential Manager non restringerebbero ai processi di un binario (§2).
- **Una cartella di stato che esiste già non si restringe**, su nessuno dei due sistemi: il modo e l'ACL
  li decide chi la crea per primo (§2).
- **Su Windows il Python del nodo è quello che `uv` trova**, e il rifiuto di una versione anteriore alla
  3.12.4 è la sola garanzia della cartella (§2; P0, 2026-09-15: una 3.12.10 trovata, non installata).
- **La voce online non viaggia sul nodo Windows**, finché ADR 0034 ha un formato solo: costruita e non
  dichiarata, ed entrarci costa una revisione di quel formato (§4).
- **Le voci OneCore non si raggiungono da SAPI 5**: sul PC di M12.4 l'unica voce `it-IT` che SAPI 5
  elenca è «Microsoft Elsa Desktop»; Cosimo ed Elsa OneCore ci sono e non si vedono (§3; P3,
  2026-09-15).
- **Il timeout della voce resta 60 s anche su Windows, con un margine più stretto**: 600 caratteri con
  Elsa valgono 45,703 s del figlio, 1,31× contro 1,6–1,9× di `say`; da riaprire se entrerà una
  regolazione della velocità della voce (§3; P3-bis, 2026-09-15).
- **La diagnosi della voce di un PC resta sul PC**: lo stderr del figlio va nella finestra del nodo, e
  dal Mac una voce che non c'è si legge soltanto come un'uscita `1` (§3).
- **La disponibilità di una voce si legge all'avvio**: una voce che sparisce mentre il nodo gira resta
  dichiarata fino al prossimo annuncio, e rifiuta quando le si chiede (§4).
- **La voce non segue l'utente**: l'alimentazione decide dove va il lavoro, non dove sta l'utente, e con
  il Mac a batteria ELA parla dal PC (M12.3c).
- **Il piazzamento di una voce fra due macchine è una domanda di §17 ancora aperta**: i pesi sono
  quelli di ADR 0017 §5, nessuno li ha ritarati per una voce, e nessuna milestone ha posto la domanda
  (M12.4, domanda aperta 1).
- **A parità di punti vince `local`**, perché `choose` prende il primo massimo nell'ordine di
  registrazione e `local` si registra all'avvio del Core: è l'ordine di una lista, non una regola che
  qualcuno ha scelto.
- **Su una macchina sola un nodo non vince più contro `local`**: da M12.3c il nodo e `local` leggono la
  stessa corrente, e `local` ha 5 punti in più — 30 a 25 attaccato, 20 a 15 staccato. La prova a mano
  di M12.3, `GETTING_STARTED.md` §11, non si riproduce su un Mac solo — la §11 è stata riletta sul
  codice il 2026-09-17 e lo dice —, e quella con due macchine è la §12.
- **Un PC senza batteria vale corrente, e leggerlo costa un `powershell.exe` a ogni battito**: 0,265–0,406
  s a lettura nella forma del codice (P6-bis, 2026-09-17), contro i 9–15 ms di `pmset` sul Mac (P6,
  2026-09-15).
- **Il kit Windows non prova Windows**: prova il ciclo sotto la composizione di un PC; Windows lo provano
  il job e la prova a mano (§5).
- **Su Windows gira in CI la suite del nodo, e solo lei**: un elenco nominato, senza gate di copertura e
  senza `make`, e lo skip del kit Darwin su Windows è verificato soltanto dal riepilogo di quel job (§5).
- **Un nodo Windows vive quanto la sua finestra, e la ragione non è la firma**: chiusa con la X, né
  `finally` né `atexit` girano (§5; P4, 2026-09-17).
- **Il `python.exe` del venv è un lanciatore**: sotto `uv.exe` ci sono due `python.exe` (P4,
  2026-09-17), e un `TerminateProcess` sul processo che si vede, per documentazione, non uccide
  l'interprete sotto di lui (§5).
- **L'attesa di `_kill` non copre due casi**: un figlio che esce da solo nell'istante della
  cancellazione, e un secondo `Ctrl-C` durante la chiusura (§5).
- **Il Core e `ela init` non sono supportati su Windows**: `ela init` chiama `os.fchmod` e cadrebbe
  (dedotto dal codice), il Core non è mai stato provato lì; e il `.env` del nodo porta la chiave del
  modello con l'ACL del profilo, senza un `ela init` che lo scriva ristretto.
- **La regola 54 non vede tutte le domande**: un `try: os.fchmod(...) except AttributeError`, e `os` o
  `sys` importati con un altro nome, passano (§6).
- **La regola 40 non vede uno script composto a pezzi**: `"SetOutputTo" + "WaveFile"` passa (§6).
- **Che due tabelle di rotte diverse facciano fallire la verifica non è stato provato a mano**: la
  prova negativa di `GETTING_STARTED.md` §12 chiede una chiave del modello, e il 2026-09-17 non ce
  n'era una né sul Mac né sul PC. Il percorso è provato dalla suite, non dalle due macchine.
- **Che cosa diventa un task il cui nodo tace a metà lavoro non è stato letto**: nella prova del
  2026-09-17 il `Ctrl-C` sul nodo è stato dato e lo stato finale di quel task non è stato guardato.
  Il protocollo lo tratta come un'assegnazione che scade (M12.1 D6), e nessuna riga della prova lo
  mostra.
- **Il vocabolario del filo copre le risposte dell'API e non i codici dei tool**: un `provider.*` o uno
  `speech.*` inventato in un test del nodo non lo ferma nessuna lista chiusa, perché viaggia dentro un
  risultato (§7).
