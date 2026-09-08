# 0033. La prima uscita verso il mondo fisico: la meccanica non si compra separata dal cervello, la porta chiusa prima della stanza, e un verifier che dichiara cosa non prova

- **Stato:** Accettata. SPEC di M11.1 approvata dall'utente, dieci decisioni (A–J), tutte prese
  **dopo** una ricognizione misurata e **prima** dello scope. Le tre che cambiano la forma di ciò
  che ELA può fare sono §1 (il criterio per ogni prodotto che sembrerà risolvere un pezzo di
  ELA), §5 (un verifier che dichiara ciò che non prova) e §7 (la difesa scritta nel commit
  precedente al codice che difende, per la seconda volta).
- **Contesto:** M11.1, la prima milestone in cui ELA produce un effetto **fuori dallo schermo**.
- **Riferimenti spec:** §8, §9, §26, §28, §29, §30, §33, §57, §59, §63
- **Estende:** ADR 0002 (una regola nuova, la 40; e la regola 35 estesa), ADR 0005 (un port
  nuovo, il ventiduesimo), ADR 0010 (una capability aggiunta), ADR 0013 (un tool), ADR 0014 (un
  verifier), ADR 0023 (un campo di `/diagnostics`), ADR 0024 (tre variabili), ADR 0028 §2 (il
  criterio del sottoprocesso, e un difetto latente in `spawn` che qui smette di essere latente),
  ADR 0029 §3 (il binario di Apple a percorso assoluto), ADR 0029 §6 (`prompt_arguments`, e il
  rischio MEDIUM letto in una direzione nuova), ADR 0030 §8 (una lettura che significa due cose
  va spezzata, applicato a una **scrittura**), ADR 0030 §15 (la difesa si scrive prima).

## Contesto

Fino a M10.4 tutto ciò che ELA faceva finiva in un posto che si legge andandolo a guardare: una
riga di database, un file che scade, una risposta HTTP. **Una frase detta ad alta voce non si
legge: si sente**, e la sente chiunque sia nella stanza, compreso chi non è l'utente.

La ricognizione è stata fatta prima della spec, e l'ordine delle due metà di §9 è stato deciso
dall'utente con la sua ragione, che vale la pena riportare perché è il criterio e non la
preferenza:

> ELA che dice qualcosa è utile da sola — le notifiche di §7, gli esiti dei task. ELA che ascolta
> senza saper rispondere non è metà di una conversazione, è un dettatore. **Si fa prima la metà
> che non apre porte.**

Parlare non chiede nessun permesso a macOS, non tocca nessuno stato di §11, non fa nascere
`DENIED_BY_SYSTEM` e non aggiunge nessun evento di audit. Tutti e quattro quei debiti sono
dell'ascolto e restano lì (M11.2).

### La ricognizione, in numeri

Misurata il **2026-09-08** su questa macchina — macOS 26.6 (25G72), arm64, MacBook Air.

| Misura | Valore |
|---|---|
| `/usr/bin/say`, permesso richiesto | **nessuno** |
| Dipendenza nuova | **nessuna** |
| Sintesi, «Fatto.» → 0,54 s di audio | 513 ms |
| Sintesi, 33 caratteri → 1,65 s di audio | 360 ms |
| Sintesi, 168 caratteri → 9,30 s di audio | **382 ms** |
| **600 caratteri**, velocità normale | **31,5 s** parlati — 19,1 car/s |
| 600 caratteri, `-r 100` (la più lenta) | 37,8 s — 15,9 car/s |
| Voci italiane / di cui femminili | 9 su 184 / **una** |

> **Il costo della sintesi è piatto rispetto alla lunghezza.** Una risposta di nove secondi si
> prepara in 382 ms come una di mezzo secondo: l'attesa prima della prima sillaba non cresce col
> testo. È il fatto che rende `say` utilizzabile davvero e non solo disponibile.

E il pavimento di rete verso un fornitore cloud, misurato per il confronto: **210–224 ms** a
richiesta completa (DNS 2,4 / TCP 18 / TLS 57), prima di qualunque sintesi.

## 1. La meccanica non si compra separata dal cervello

Il criterio generale che questa milestone lascia, e la ragione per cui è qui invece che nella
milestone: **varrà per ogni prodotto che sembrerà risolvere un pezzo di ELA.**

§9 chiede cinque cose — ascoltare, interpretare, rispondere vocalmente, interrompersi, continuare
una conversazione col contesto precedente — e un prodotto che le fa tutte esiste: gli Agents di
ElevenLabs, di cui l'utente ha già l'abbonamento. Letti sullo schema di creazione e non sulla
descrizione, fanno STT, turn-taking, barge-in configurabile per tool, LLM, TTS, tool calling e
knowledge base.

**La cucitura quasi funziona, e va detto perché è l'argomento che convincerebbe.** Un tool di tipo
`client` manda un evento al nostro client: il loro modello decide *che* un tool vada chiamato e
*con quali argomenti*, ed è **ELA a eseguirlo**. Non è vero, quindi, che adottare un Agent
scavalchi il Guardian sull'esecuzione.

Si strappa in tre punti, in ordine di gravità crescente:

1. **Il Guardian deciderebbe senza il contesto su cui decide.** `CLAUDE.md`: *il Guardian non
   possiede tool, decide su Capability + contesto*. Quel contesto è il `Task`, il `TaskPlan`, lo
   step, la ragione. Con un Agent non c'è nessun piano: arriverebbero un nome di capability e
   degli argomenti senza step e senza provenienza. Il Guardian non sarebbe indebolito — **gli
   verrebbe posta una domanda diversa da quella che sa rispondere.**
2. **§26 si inverte.** *Il Core deve parlare con una Model Provider abstraction*: qui il Core non
   parlerebbe con nessun modello, sarebbe un modello a parlare col Core. Il `ModelRouter`
   aggirato proprio nell'interazione che conta di più, e «aggiungere successivamente altri
   modelli» diventerebbe riscrivere un prompt nella console di qualcun altro.
3. **L'audit resterebbe vero e vuoto nel punto che conta.** `PERMISSION_DECIDED` e
   `TOOL_EXECUTED` verrebbero scritti onestamente, e la catena di §32 conterrebbe **tutte le
   conseguenze e nessuna causa** — peggio di una lacuna, perché ha l'aspetto di una traccia
   completa (ADR 0028 §10: *l'audit registra ciò che ELA decide*).

E sopra i tre, §57: prompt, knowledge base e trascritto non sarebbero un invio per richiesta ma
una **residenza stabile** dei dati dell'utente su un server altrui.

Ma nessuno di questi tre chiude la domanda, perché a tutti e tre si potrebbe rispondere «allora
usiamone solo un pezzo». Quello che la chiude è un fatto sul prodotto:

> **La meccanica non si compra separata dal cervello.** ElevenLabs vende il TTS da solo e lo STT
> da solo. Il turn-taking e il barge-in esistono **soltanto dentro un Agent**, e un Agent non è
> istanziabile senza un `prompt`. Non si può comprare la metà che §26 non rivendica senza
> comprare anche quella che rivendica.

Svuotare l'Agent — prompt vuoto, tutto come tool `client` — non salva: si pagherebbe un LLM per
fare da ponte, tutto l'audio passerebbe comunque da loro, e **sarebbe ancora il loro modello a
decidere quando un turno finisce e quando parlare**, che è esattamente la decisione che §8 chiama
fondamentale.

**Come si applica il criterio la prossima volta**, perché è questo il motivo per cui è scritto:
davanti a un prodotto che risolve un pezzo di ELA, la domanda non è *«questo pezzo è una
decisione o una meccanica?»* — è *«questo pezzo si può comprare senza comprare anche una
decisione?»*. Un prodotto che impacchetta le due insieme va valutato come se fosse tutto
decisione, perché è quello che si adotta.

**Ne segue la forma della Fase 11**, e le due estremità si comprano davvero: M11.1 parlare
(locale) → M11.2 ascoltare (locale) → M11.3 la voce di §9 → M11.4 il turno, che è nostro.

## 2. Il contesto precedente esce dalla Fase 11, e non è una rinuncia

Applicando il test operativo di ADR 0032 §4 — *se il fatto si ricalcola è contesto, se perderlo
perde informazione è memoria* — a un trascritto di conversazione: **perderlo perde informazione.**
Quindi è memoria, con i quattro campi di §21 (importanza, confidenza, scadenza, privacy), e non un
anello di buffer dentro il loop.

> **La conversazione avrà memoria quando §21 esisterà, non prima.** Un buffer dentro il loop
> sarebbe memoria improvvisata senza le regole di §21, che è ciò che ADR 0028 §10 e ADR 0032 §4
> hanno già rifiutato due volte — per la percezione e per il compositore. Rifiutarlo una terza
> volta per la voce non è prudenza, è la stessa regola.

Vincolo dichiarato: la riga di §9 *«comprendere il contesto precedente»* **non è consegnata in
Fase 11**, e chi la riaprirà lo farà con §21 in mano.

## 3. `voice.speak` è MEDIUM, e §59 è la strada già prevista

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `voice.speak` | MEDIUM | — | — | sì | `text: string`, `purpose: string` | — |

- **MEDIUM**, per l'argomento di ADR 0029 §6 letto in una direzione nuova. Lì il ragionamento era
  che §29 chiama `model.complete` MEDIUM *«perché il contenuto dell'utente può essere inviato a un
  provider AI esterno»*, letto un passo prima: il contenuto non parte, **nasce**. Qui parte, solo
  non attraverso una rete: **parte nella stanza**, e il pubblico non è qualcosa che ELA sceglie o
  possa anche solo osservare. Un collega alla scrivania accanto è un destinatario che ELA non ha
  deciso.
- **Nessuno scope, e non è una dimenticanza**: lo scope del Guardian è a forma di percorso, e lo
  scope naturale del parlare è *a chi* e *quando*, che non è un percorso. È la stessa riga di ADR
  0029 §6 per la cattura.
- **`prompt_arguments` è `purpose` e non `text`.** Il testo sono le parole di ELA, e una domanda
  che le mostrasse le scriverebbe dentro un `Approval` persistito — la cosa da cui ADR 0029 §6
  mette in guardia. E l'apparente stranezza di approvare senza leggere è più piccola qui che
  altrove: **le parole le senti un secondo dopo.** La domanda è se ELA possa fare rumore, non
  quali parole.

**Il costo, e la risposta che non è abbassare il rischio.** `requires_authorization` significa
oggi un'approvazione per ogni frase, ed è precisamente ciò che può rendere la voce insopportabile.
La risposta non è LOW:

> Una policy di §59 — *«puoi parlare liberamente quando sono al Mac»* — è un'**`Authorization`
> riusabile** con TTL e condizione, sotto `Rule.APPROVAL_UNLESS_AUTHORIZED`, che è già come
> funzionano `model.complete` e `perception.capture_screen`. **Strada registrata e non
> percorsa qui**: un grant scritto prima che qualcuno abbia avuto ragione di chiederlo è ciò che
> ADR 0028 §4 rifiutò.

## 4. Il port, e la promessa che nessun altro port ha

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `SpeechPort` | §8, §9 | async | `available`, `speak` |

`available` è un membro suo per la ragione che ADR 0028 diede a `UnsupportedProbe` e ADR 0029 ad
`available`: *«ELA su Linux non dice niente»* merita di essere una risposta con un nome e un test.

La promessa che gli altri port non hanno: **una chiamata cancellata ferma il suono.** Attendere
`speak` fino in fondo è ciò che il chiamante fa; cancellare quell'attesa è ciò che fa un chiamante
che ha cambiato idea, e la frase deve fermarsi. Non è il barge-in di §9 — quello vuole un ascolto
che non c'è — ma è la primitiva su cui il barge-in poggerà, e un port che qui lasciasse un figlio
orfano non potrebbe farla crescere.

## 5. Il verifier dichiara ciò che non prova

§63 chiede che ELA verifichi il proprio lavoro, e ADR 0014 che ogni capability abbia un verifier.
**Nessun verifier di una voce può fare ciò che fanno i suoi fratelli**: il suono non lascia
artefatto, non c'è file da rileggere come per la nota e per la cattura, e nessun runner ha
orecchie.

Le due condizioni:

| Condizione | Che cosa confronta |
|---|---|
| `speech.text_matches` | il digest che il risultato dichiara contro il digest dell'argomento |
| `speech.took_real_time` | la durata contro `len(text) × 0,005 s` |

E la frase che il verifier porta nel proprio docstring, perché la dichiarazione **è** la
consegna:

> Prova che ELA ha chiesto a macOS di dire quelle parole e che macOS ci ha messo il tempo di
> dirle. **Non prova che qualcuno abbia sentito.**

È ADR 0030 §8 applicato a una **scrittura** invece che a una lettura: *una lettura che significa
due cose va spezzata prima di essere consegnata*. «L'helper è uscito con zero» può significare che
la frase è stata detta o che non è uscito alcun suono, e le due si separano con l'unico testimone
disponibile — l'orologio. Un `say` che ha risposto in un decimo del tempo che quelle parole
richiedono non le ha riprodotte.

**La soglia è misurata**: 600 caratteri hanno richiesto 31,5 s (52 ms/carattere) e 37,8 s alla
velocità più lenta (63 ms/carattere). Il pavimento è **5 ms**, circa dieci volte sotto la lettura
più veloce, perché non è un budget di prestazioni: è la linea sotto la quale l'unica spiegazione è
che non sia uscito nulla. Funziona perché il parlato è riprodotto in tempo reale — non esiste una
macchina più veloce che parli più in fretta.

**Ciò che il verifier deliberatamente non controlla: che esistesse un dispositivo di uscita
audio.** Leggerlo vorrebbe una famiglia di percezione nuova e un campo nuovo su `RawObservation`,
che M11.1 ha dichiarato fuori scope; e la soglia temporale prende **lo stesso caso** per cui quella
lettura serviva — un helper che riesce senza produrre suono — dall'esterno e senza port nuovi.
Registrato perché chi volesse il dispositivo sappia che è stato considerato.

## 6. Il tetto è un interruttore che non c'è

`MAX_SPOKEN_CHARACTERS = 600`, rifiutato dallo schema della capability, prima del Guardian e prima
del figlio: una frase troppo lunga è un argomento sbagliato, non un'azione che fallisce.

Il numero non è di cortesia. **Finché non esiste il barge-in non c'è modo di fermare ELA a metà**
(dec. F): il tetto è ciò che sta al posto di un'interruzione che non è stata costruita, quindi è
scelto contro la cosa peggiore che possa succedere senza interruzione — mezzo minuto — e non
contro quanto un modello vorrebbe dire.

**E il timeout non eredita nessun rapporto.** ADR 0030 §14 scrisse che *un rapporto fra un timeout
e una mediana non è una costante di questo progetto: dipende da chi fa il lavoro.* Qui il lavoro
non è calcolo affatto: **la chiamata dura quanto dura il parlato**, quindi l'attesa è la consegna e
non un costo accessorio, e un multiplo di una mediana sarebbe un numero su un'altra cosa. Si
deriva invece: 600 caratteri misurati a 31,5 s (37,8 s alla velocità più lenta), e sessanta secondi
sono 1,9× il primo.

**Non c'è una manopola della velocità**, ed è ciò che rende il numero derivabile invece che una
supposizione: una velocità configurabile renderebbe la frase più lunga una funzione di
un'impostazione, e il timeout starebbe sorvegliando una durata che nessuno ha misurato.

## 7. Le due difese, scritte nel commit precedente al codice

`Regole aggiunte:`

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 40 `the-voice-writes-no-file` | i moduli della voce non nominano `-o`, `--output-file`, `--file-format`, `--data-format` | `VOICE_MODULES` | nessuna esenzione |

`Regole estese:`

| Regola | Come cambia | Perché |
|---|---|---|
| 35 `capture-stays-on-the-machine` | il soggetto diventa `CAPTURE_MODULES` **più** `VOICE_MODULES` | il testo che ELA dice è composto dal contesto di §44 e dal `goal` dell'utente |

**L'ordine è parte della decisione.** Entrambe sono state scritte, coi loro casi negativi, **nel
commit precedente** a quello che introduce il codice che parla. È ADR 0030 §15 applicato una
seconda volta: una difesa scritta dopo la cosa che difende ha una finestra in cui la cosa esiste e
la difesa no, e in quella finestra la revisione guarda il codice nuovo e non la regola che manca.

**Due tuple e non una, e questa è la decisione.** M11.3 manderà le parole di ELA a un fornitore di
sintesi, e quella milestone deve poter riaprire **quella metà** — con le quattro risposte di §57
nella forma di ADR 0030 §17 — senza che la modifica tocchi per sbaglio la metà della cattura. Con
un solo elenco, rilassare la voce avrebbe rilassato lo schermo in silenzio.

**Il nome della regola 35 è ora più stretto della regola**: dice «capture» e tiene anche la voce.
Rinominarla toccherebbe tre ADR immutabili, quindi il nome resta e la discrepanza si scrive —
stessa disciplina della dec. G, e stessa terza volta che la risolverà.

E la regola 40 può scattare, che è l'unica ragione per cui vale averla (ADR 0026 §7): `say -o` è un
flag documentato e funzionante, e fra «ELA ha parlato» e «ELA ha tenuto una registrazione di tutto
quello che ti ha detto» c'è **un carattere**. Legge i literal e non gli import, come la regola 36:
un flag è una stringa in un `argv`, e una regola che leggesse gli import sarebbe muta proprio sulla
riga che può romperla.

## 8. Un difetto latente in `spawn` che qui smette di essere latente

`spawn` avvolgeva `process.communicate()` in `asyncio.wait_for`. Quella funzione cancella la
coroutine che legge le pipe del figlio e **non tocca il figlio**: una chiamata cancellata lasciava
un processo vivo.

Per la sonda e per la cattura il residuo è un lettore vagante — sgradevole, non grave. Per la voce
non è latente: **un `say` orfano è ELA che continua a parlare dopo che le è stato detto di
smettere**, cioè la metà peggiore del problema che la dec. F ha rimandato al barge-in.

Trovato scrivendo il criterio 9 della spec, e riparato nell'ordine che `CLAUDE.md` impone: prima
il test che fallisce — un figlio che scrive un file dopo l'istante in cui dovrebbe essere morto,
e il file c'era — poi il fix. Riparato **una volta per tutti e tre** i chiamanti: un helper
condiviso con un buco non è tre problemi.

## 9. Due rifiuti, due codici

`ELA_VOICE_ENABLED` è l'interruttore dell'utente; `available()` è se questa macchina abbia una
voce. Rispondere a entrambi con `voice.unsupported` sarebbe l'ambiguità che ADR 0030 §8 dice di
spezzare, ed è la stessa forma di ADR 0028 §3, dove `OFF` da solo non poteva esistere.

| Codice | Che cosa significa | Riprovabile |
|---|---|---|
| `voice.disabled` | l'utente ha spento la voce | no — finché un umano non la riaccende |
| `voice.unsupported` | questo sistema operativo non ha una voce che ELA conosca | no |
| `voice.timeout` | il figlio non ha finito in tempo | sì — **e la frase è stata detta a metà** |
| `voice.failed` | il figlio è finito male | sì |

`voice.timeout` merita la sua riga: non significa «non è successo niente», significa **«ELA si è
fermata a metà parola»**, e per chi ha sentito sono due cose diverse.

## 10. Niente audit nuovo, niente rotte nuove, niente su disco

Parlare non cambia nessuno stato di §11 — §11 sono microfono e webcam, cioè **ingressi** — quindi
non nasce nessun tipo di evento. La catena `PERMISSION_DECIDED` → `TOOL_EXECUTED` → `STEP_*` copre
già tutto. Il tipo di evento per un cambio di stato **causato** da ELA nasce con M11.2, dove ELA
accenderà qualcosa (ADR 0028 §10).

`/diagnostics` guadagna un campo `voice` — abilitata, disponibile, quale voce, il tetto e il
timeout — e sta lì per la linea di ADR 0028 §8: dice *a cosa ELA è collegata*, non *cosa ELA sta
facendo*. **Non c'è nessuna rotta che dica se ELA sta parlando adesso**, e non deve essercene una
in M11.1: una frase dura quanto una frase, e uno stato vero per trenta secondi non è uno stato su
cui qualcuno possa agire.

E niente su disco, che è la decisione 7 dell'utente: nessuno store, nessun TTL, nessun soffitto —
perché non c'è niente da tenere. `RawSpeech` non ha un campo per il testo, e il risultato porta una
lunghezza e un digest e mai le parole: un modello che riportasse la frase la metterebbe in un
`ExecutionResult` persistito, che è l'accumulo di §57 raggiunto per un'altra strada.

## Alternative considerate

- **Un Agent conversazionale di ElevenLabs**, intero. Scartata per §1 — e non per i tre strappi,
  che da soli si potrebbero aggirare, ma perché la meccanica non è in vendita separata.
- **Ascoltare per primo.** Scartata dall'utente con l'argomento che è diventato il criterio: *si
  fa prima la metà che non apre porte.*
- **TTS cloud in questa milestone.** Scartata: sarebbe il primo dato in uscita del progetto,
  dentro una milestone che doveva essere quella economica, e vuole prima le quattro risposte di
  §57 nella forma di ADR 0030 §17. È M11.3.
- **Rischio LOW.** Scartata: `workspace.write_note` è LOW ed è protetta da uno **scope**, che qui
  non esiste e non può esistere a forma di percorso. Senza scope la protezione è il grant, e un
  grant è ciò che MEDIUM richiede.
- **`text` fra i `prompt_arguments`.** Scartata: scriverebbe le parole di ELA in un `Approval`
  persistito (ADR 0029 §6), per un beneficio che il tempo azzera — la frase la si sente un secondo
  dopo.
- **Una manopola della velocità.** Scartata: renderebbe la durata della frase più lunga una
  funzione di un'impostazione, e il timeout starebbe sorvegliando un numero mai misurato.
- **Un verifier che legga il dispositivo di uscita audio.** Scartata per ora (§5): vorrebbe una
  famiglia di percezione nuova, e la soglia temporale prende lo stesso caso dall'esterno.
- **Uno `stop` in questa milestone.** Scartata (dec. F): lo stop appartiene al barge-in, che vuole
  un ascolto. Ciò che entra qui è la primitiva — un figlio che muore quando la coroutine è
  cancellata — senza la quale il barge-in non sarebbe costruibile.
- **Rinominare `ela.infrastructure.perception`.** Scartata (dec. G): è la seconda volta che il
  nome è più stretto del contenuto, e ADR 0029 fu la prima. Alla terza si rinomina, ed è una
  milestone sua.

## Conseguenze

- ELA può dire una frase ad alta voce, dietro una decisione del Guardian, senza scrivere niente e
  senza che un byte lasci la macchina.
- **La voce di §9 non è consegnata.** Alice è l'unica femminile italiana che `say` offre ed è
  sintesi concatenativa datata: M11.1 consegna *che ELA parla*, non *che ELA suoni come §9 la
  descrive*. Riaperto da M11.3.
- Le regole di architettura passano da trentanove a **quaranta**, e i contratti di import-linter
  restano **quattordici**: la regola 40 guarda literal e non è esprimibile come divieto di import.
- I port passano da ventuno a **ventidue**.
- Le capability di produzione passano da cinque a **sei**; quelle di v0.1 restano **tre**.
- `spawn` uccide il figlio anche quando è la chiamata a essere cancellata, per tutti e tre i suoi
  chiamanti.

### Vincoli dichiarati, da riaprire quando serviranno

- **La voce non è quella di §9** (§Conseguenze). M11.3.
- **Niente esce** — regola 35 estesa alla voce, con la condizione di riapertura scritta dentro:
  M11.3 apre quella metà, e solo quella, con le quattro risposte di §57.
- **Niente su disco**, e non c'è uno store da progettare perché non c'è niente da tenere.
- **Non si può far tacere ELA a metà frase**: il solo limite è il tetto di 600 caratteri e il
  timeout. Lo `stop` arriva col barge-in (M11.4).
- **ELA non parla mai di propria iniziativa**: una frase esce solo se uno step la chiede. Quando
  parlare sia una decisione è §34, che non esiste.
- **§8 non è implementato** — *decidere di non parlare* è la caratteristica che §8 chiama
  fondamentale, e in M11.1 quella decisione la prende chi scrive lo step: ELA non sa se lo schermo
  è bloccato, se ci sono le cuffie, se c'è una riunione in corso.
- **Il contesto precedente esce dalla Fase 11** (§2): la conversazione avrà memoria quando §21
  esisterà.
- **Un'approvazione per frase**, finché §59 non porta un grant riusabile (§3).
- **Il verifier non prova che qualcuno abbia sentito** (§5), e lo dice.
