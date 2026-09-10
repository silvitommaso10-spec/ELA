# 0036. L'ascolto: un trascrittore non sa dire «non ho sentito», e l'audio non si tiene

- **Stato:** Accettata. SPEC di M11.2 approvata dall'utente, dodici decisioni A–L, ciascuna in
  review separata fra il 2026-09-09 e il 2026-09-10.
- **Data:** 2026-09-10
- **Riferimenti spec:** §9, §10, §11, §20, §28, §29, §30, §33, §45, §57, §63
- **Continua:** ADR 0028 §1, §2, §4, §9, §10; ADR 0029 §1, §3, §6, §7; ADR 0030 §8, §15, §16;
  ADR 0033 §4, §7, §9; ADR 0034 §6, §7, §8; ADR 0035 §7.
- **Estende:** ADR 0002 (una regola nuova, la 45, e una rinominata, la 35), ADR 0005 (un port
  nuovo), ADR 0010 (una capability nuova), ADR 0027 (le righe di `CONSTANTS` si contano da sole).

## Contesto

§9 chiede che ELA ascolti. M11.1 ha consegnato la metà che non apre porte — ELA parla — con
l'argomento dell'utente: *si fa prima la metà che non apre porte*. Questa è l'altra metà, e apre
la porta più larga del progetto: **il microfono è il primo dato di ELA che contiene persone che
non sono l'utente.** Uno screenshot fotografa ciò che l'utente ha scelto di avere davanti; una
registrazione prende chiunque fosse nella stanza, compreso chi non ha acconsentito e non lo sa.

Prima delle decisioni sono state fatte tre ricognizioni misurate, e ognuna ha smontato
un'assunzione invece di confermarla. Sono in `docs/milestones/M11.2.md` per esteso; qui stanno
solo i fatti che decidono.

## 1. Il principio: un interprete converte un'assenza in una presenza

È la scoperta più importante della fase, e non riguarda il permesso negato — quello è solo il modo
in cui l'abbiamo trovata.

Misurato il 2026-09-09, col microfono negato a `Terminal.app` da Impostazioni di Sistema e con un
controllo che esegue **lo stesso identico script** sotto un'identità che il permesso ce l'ha:

| | negato | concesso |
|---|---|---|
| `AudioQueueNewInput` / `AudioQueueStart` | **0 / 0** | 0 / 0 |
| callback in 3 s, byte consegnati | 14, 96 244 | 14, 96 586 |
| **picco del segnale** | **0** | **3330** |

> **Il rifiuto è silenzioso, e non di poco: è indistinguibile.** macOS consegna una coda audio
> perfettamente funzionante che produce zeri. Non c'è nessun errore da intercettare, da nessuna
> parte.

E poi la parte che cambia il disegno. Trenta secondi di zeri assoluti, dati a un trascrittore:

| modello | che cosa ha scritto |
|---|---|
| `large-v3-turbo-q5_0` | «**Grazie a tutti.**» |
| `small`, `base` | «**[Musica]**» |

> **Un trascrittore non ha modo di dire «non ho sentito niente».** L'assenza di segnale gli arriva
> **come** segnale — una sequenza di campioni come tutte le altre — e lui restituisce parole,
> perché restituire parole è l'unica cosa che sa fare.
>
> **Ogni modo in cui la cattura può fallire in silenzio arriva all'interprete indistinguibile dal
> silenzio vero, e ne esce come linguaggio.** Il permesso negato è quello misurato; ci sono un
> dispositivo muto, un ingresso staccato, un formato negoziato male, e quelli che non conosciamo —
> che è il motivo per cui la difesa non può essere un elenco di casi.
>
> **Ciò che decide se c'è stato un segnale deve stare a monte di ciò che lo interpreta, e non può
> essere l'interprete.**

**È l'escalation di ADR 0030 §8, e i due gradini vanno distinti.** Là una lettura poteva
significare due cose — «non c'è testo» e «non ho potuto guardare» — e il rimedio era spezzarla
prima di consegnarla. Qui non c'è nessuna lettura ambigua da spezzare: Vision con una lingua
sbagliata rispondeva *zero osservazioni*; un trascrittore con zero audio risponde **una frase**. Il
primo caso perde un fatto, il secondo ne inventa uno.

Il principio ha due conseguenze operative, e sono §7 e §8.

## 2. α: whisper.cpp, e il figlio resta nostro

Non esiste un `screencapture` dell'audio — misurato: `/usr/bin` ha `say`, `afplay`, `afinfo`,
`afconvert` e nient'altro. La strada di ADR 0029 §3, dove il figlio è un binario firmato da Apple e
la regola 33 diventa vera per costruzione, **non è disponibile**. Il figlio torna nostro, e la
scelta è fra due architetture coerenti che non si mescolano.

| | **α — whisper** | **β — `Speech.framework`** |
|---|---|---|
| chi registra | figlio Python stdlib-only, `AudioQueue` via `ctypes` | un helper Swift, che registra e trascrive insieme |
| regola 33 | **intatta** | il soggetto si deriva dal `__main__` guard e non trova un file Swift |
| dipendenze di build | nessuna | Xcode CLT su ogni runner |
| catena di fornitura | **574 MB**, mitigati da uno sha256 | nessuna |
| latenza di un comando corto | ~1,7 s | **~0,23 s** |

`Speech.framework` è **5–7× più veloce**, non ha blob, e il suo on-device è un fatto misurato
(durante sei riconoscimenti i tre processi che fanno il lavoro hanno **zero** socket INET, con un
controllo che dimostra che il contatore conta). Anche il secondo permesso TCC costa niente:
bundle id nuovo, `notDetermined` → **`authorized` in 4,2 s senza dialogo**.

**Ed è stato scartato per una ragione sola, che è la prima dell'ADR per decisione dell'utente:**

> Su undici enunciati ha prodotto **una frase troncata** — «Leggimi l'ultima email **di**»,
> deterministica su tre giri, con e senza prefisso — perdendo il nome che era l'oggetto del
> comando. **Un errore che fallisce rumorosamente si scopre. Uno che consegna un comando
> quasi-plausibile senza destinatario arriva fino all'esecuzione.**

È ADR 0030 §16 nella sua forma più pericolosa: là il prodotto sbagliato era un testo da leggere,
qui è **un comando da eseguire**, e a valle c'è un Guardian che decide su argomenti e non su
intenzioni. «Manda una mail a» senza destinatario si ferma da solo; «leggimi l'ultima email di» è
una richiesta che qualcuno può soddisfare male.

**La seconda ragione è la struttura**, e da sola non avrebbe deciso: β vorrebbe il primo artefatto
compilato del repository, Xcode CLT su ogni runner e una regola 33 che smette di trovare il suo
soggetto — le tre cose che ADR 0034 §8 ha appena finito di togliere.

**Una cosa di β non si butta e si copia:** la confidenza. Non era un vantaggio di Apple, era un
vantaggio che non avevamo cercato in whisper — vedi §8.

**Il modello è `large-v3-turbo-q5_0`**, con i tre rimisurati nella stessa sessione perché
confrontare i numeri di oggi con quelli di ieri sarebbe stato lo stesso errore in un'altra forma.
`small` sbaglia il contenuto su due campioni su sette, e uno dei due è **una parola plausibile**
(«Consiglio di *Administrazione*»); `turbo` è a zero su sette. La rimisura non ha cambiato la
decisione e ha cambiato il prezzo: ~1 s in più di `small`, non ~0,4.

**E ciò che decide che cosa ELA crede di aver sentito non è una variabile d'ambiente**: binario e
modello sono percorsi assoluti con lo **sha256 dichiarato e controllato**, mai risolti via `PATH`.
È ADR 0029 §3 applicato a ciò che ascolta la stanza invece che a ciò che fotografa lo schermo.
Costo misurato: 413 ms per il modello, 1 ms per il binario, ricordati contro dimensione e mtime.

## 3. L'audio non si tiene, e il prezzo non è quello che sembrava

La domanda dell'utente: *la trascrizione è il dato utile e l'audio è la materia prima, quindi la
domanda è se la materia prima va tenuta quando il derivato basta.*

ADR 0029 §1 scelse l'artefatto perché **§20 vieta che un tool sia verificato sulla propria parola**
e il PNG *doveva* essere riletto. Qui il documento che il verifier rilegge è il **trascritto**:
l'audio esisterebbe solo perché un programma vuole un file, che è esattamente il caso in cui
ADR 0034 §7 scelse un file **senza nome**.

E la ragione che pesa di più non è di ingegneria: è che questo è l'unico dato di ELA che contiene
persone che non hanno acconsentito. Un TTL di cinque minuti è una buona politica per lo schermo
dell'utente; per la voce di un collega che passava di lì è una politica che nessuno gli ha
spiegato.

**Il prezzo, corretto dall'utente in review, perché la prima versione lo raccontava male.** Non è
vero che nessuno si accorge di un errore: *se ELA capisce male fa la cosa sbagliata davanti a chi
ha parlato*, e chi ha parlato se ne accorge subito — il ciclo di correzione più corto che esista.
Quello che si perde è **poter dimostrare a posteriori che cosa fu detto**, e quello non si compra
tenendo l'audio: si compra tenendo il **trascritto**.

**Che però non si ricalcola.** ADR 0032 §4: *se il fatto si ricalcola è contesto; se perderlo perde
informazione è memoria.* L'audio da cui verrebbe non esiste più, per costruzione. Quindi un
trascritto durevole è **memoria**, con i quattro campi di §21, e §21 è Fase 15.

> **Nessuna mezza memoria.** Il trascritto vive quanto il task che l'ha chiesto e non oltre. M11.2
> non gli dà nessuna strada per durare di più: non l'audit — dove il contenuto dell'utente non
> entra (regole 23 e 39) ed è append-only, quindi non durerebbe *più a lungo*, durerebbe **per
> sempre** — non il contesto di §44, nessuno store suo. Dove viva un trascritto durevole lo decide
> il Memory Core: è un vincolo **per la Fase 15**, non un vincolo riapribile qui.

## 4. `DENIED_BY_SYSTEM` non entra, e stavolta è misurato

ADR 0028 §4 la tenne fuori perché sotto §11 nessuno stato dipende da un permesso, e disse che
sarebbe nata «nella milestone in cui ELA proverà a rendere `ACTIVE` un dispositivo». Questa è
quella milestone. La previsione era giusta a metà: **la milestone è arrivata, il caso no.**

Col microfono negato la sonda risponde `microphone_count: 1`, `microphone_in_use: false`,
`microphone_permission: 2`. Il dispositivo c'è, il suo «in uso da qualcuno» si legge come sempre —
CoreAudio non chiede permessi — e il diniego è già visibile dove scatta davvero, come
`PermissionState.DENIED` sulla mappa separata. **Nessuno `SensorState` cambia sotto un diniego**,
quindi una causa per esso sarebbe un valore che non può scattare: ADR 0026 §7, e un ramo morto in
meno.

Il diniego resta dove è utile: `listen.denied_by_system`, un codice del tool.

## 5. Un port solo, il ventitreesimo

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ListeningPort` | §9, §10, §11 | async | `available`, `listen` |

`listen(seconds)` contiene l'apertura del dispositivo **e** la trascrizione, e **nessun byte di
audio attraversa il confine del Core**. Un port solo non è economia: è la decisione §3 resa
struttura, la stessa forma di ADR 0034 §6, dove la sintesi arrivò come un `Callable` tipizzato
invece che come un port suo. Due port renderebbero sostituibile lo STT da solo, e quella
sostituibilità non si perde: lo STT entra nell'adapter come callable, come `Spawn` in `darwin.py`.

Le clausole sono quelle degli altri tre di questa famiglia, più una: **una chiamata cancellata
chiude il microfono.** È la promessa di ADR 0033 §4 col segno invertito, ed è più grave — un `say`
orfano è ELA che continua a parlare, un registratore orfano è **ELA che continua ad ascoltare dopo
che le è stato detto di smettere**.

## 5-bis. La capability

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `perception.listen` | MEDIUM | — | — | sì | `purpose: string`, `seconds: integer` | — |

**Il nome è la superficie del consenso** (ADR 0034 §3): il prompt di un `Approval` mostra il
`capability_id` e mai la descrizione, quindi l'id è l'unico posto in cui la parola giusta arriva a
chi decide.

MEDIUM e sempre autorizzata, per la ragione che ADR 0028 §9 aveva registrato: è la prima lettura
di **contenuto** che non è né uno schermo né una parola di ELA. HIGH non è un'opzione — in
`RISK_POLICY` significa `DENY`, quindi non renderebbe l'ascolto più prudente, lo renderebbe
impossibile (ADR 0034 §4).

**Nessuno scope**, per la ragione di ADR 0029 §6: lo scope del Guardian è a forma di percorso, e
lo scope naturale dell'ascolto è *quando* e *chi altro c'è nella stanza*.

**`seconds` è obbligatorio, non ha un default, ed è nominato nella domanda** (dec. G2). Il
meccanismo di `prompt_arguments` accetta ora anche un `integer`: ciò che la regola stretta
proteggeva era il **contenuto** dell'utente dentro un `Approval` persistito, e un numero non è
contenuto. Una capability che aprisse un microfono per una durata scritta in un file di
configurazione nasconderebbe proprio la cosa che chi risponde vuole sapere.

## 6. Il figlio ha una scadenza sua, e non è ridondante

Un sottoprocesso **sopravvive al genitore**: `launchd` lo adotta. Se ELA muore a metà
registrazione, la scadenza del padre non chiude niente. Quindi il figlio ne ha una propria, e la
conseguenza si può scrivere come un numero invece che come una speranza:

> **La vita massima di un microfono orfano è `MAX_LISTEN_SECONDS` più il suo margine**, e non
> «finché qualcuno se ne accorge».

## 7. Due difese, e nessuna delle due è una soglia

**Il preflight** (ADR 0029 §7: *una credenza periodica non decide mai un'azione*) rilegge il
permesso nell'istante, e da uno stato negato **ELA non apre il dispositivo**. Dopo la misura di §1
non è più una cortesia ereditata: è l'unica difesa fra un interruttore spento e un fatto inventato.

**Il picco del segnale**, calcolato dal figlio mentre registra, dove i campioni sono. `picco == 0`
**non è una soglia, è un fatto**: nessun campione differiva dal silenzio. Prende il caso che il
preflight non può prendere — permesso concesso, dispositivo muto, ingresso morto — e l'audio non
raggiunge mai il trascrittore.

**Un undicesimo codice, trovato scrivendo il preflight e non previsto da questa decisione:**
`listen.permission_unreadable`. La sonda può non riuscire a leggere il permesso — scaduta, morta,
o che stampa spazzatura — e *«il sistema mi rifiuta»* e *«non sono riuscita a sapere se mi
rifiuta»* sono due fatti con due risposte. È il criterio di questa milestone un passo più
indietro, ed è il gemello di `screen.not_observable` (M10.2). Un dubbio non è un sì (§33).

**Il limite, dichiarato invece che risolto: una stanza silenziosa non ha picco zero.** Un ufficio
vuoto con un condizionatore dà un segnale piccolo e vero, e lì il trascrittore può ancora
inventare. La risposta strutturale esiste e non è una soglia — **l'approvazione nomina ciò che ELA
ha capito prima di agire**: «ho capito *manda una mail a Giulia*, procedo?». È la stessa forma
della dec. G2 (se la durata dell'apertura è metà di ciò che si approva, il contenuto capito è
l'altra metà) e il criterio che le regge entrambe è §30 nella forma di ADR 0029 §6.

Verificato sul codice, perché non basta proporlo: **niente lo impedisce, e una cosa manca.**
`_stated()` compone già il prompt dell'`Approval` con gli argomenti che la capability dichiara. Ma
un trascritto non può ancora *diventare* gli argomenti di uno step — è **ADR 0018 §6**, dove la
forma `{"$from": …}` è prevista e non costruita, assegnata *«alla milestone che porterà la prima
capability che ne ha bisogno»*. E la condizione non negoziabile di quel paragrafo — *la risoluzione
avviene prima del Guardian* — è questo stesso requisito scritto dall'altro lato, a un anno di
distanza. **Vincolo di progetto per la milestone che consumerà un trascritto.**

## 8. La confidenza non era persa

La dec. C aveva registrato come vantaggio di `Speech.framework` una cosa che si credeva mancasse a
whisper. È falso, e verificarlo è costato dieci minuti: `-oj -ojf` scrive una probabilità `p` per
**ogni token**, e la misura dice che è informativa e non decorativa.

| enunciato | mediana | token sotto 0,6 |
|---|---|---|
| «Ela, leggimi l'ultima mail di Marco» (esatto) | 0,998 | ` Ela` → **0,544** |
| «Ela dimmi che ore sono» (**sbagliato**: «E la») | 0,986 | ` E` → **0,555** |
| «Sposta la riunione di domani alle sei» (esatto) | 0,999 | **nessuno** |

La probabilità bassa cade sulla parola sbagliata o difficile, e un enunciato pulito non ne ha
nessuna. **Ed è per token, non per segmento**: dice *quale* parola, dove Apple dava una media.

Quindi ELA **può** dire «non sono sicura di aver capito», e il limite che si stava per dichiarare
non va dichiarato. Ne va dichiarato un altro, più piccolo e vero: **`p` è una probabilità del
decoder, non una confidenza calibrata.** Due campioni in cui «p bassa» coincide con «sbagliato»
sono evidenza, non calibrazione.

La forma copia quella dell'OCR (ADR 0030): l'artefatto tiene i token con la loro `p`, il risultato
porta minimo e mediana, e **nessuna soglia sta scritta da nessuna parte** — una soglia è una
decisione e appartiene a chi decide (§45).

## 9. Le regole

`Regole rinominate:`

| Regola | Da | A | Perché |
|---|---|---|---|
| 35 | `capture-stays-on-the-machine` | `content-stays-on-the-machine` | teneva già i pixel, il testo di una cattura e le parole di ELA; l'ascolto è il quarto genere, e «capture» è diventato sbagliato in modo evidente invece che per estensione |
| 34 | `perception-adapter-decides-nothing` | `machine-adapter-decides-nothing` | il package che quella regola sorveglia è stato rinominato dal primo commit di questa milestone: il disallineamento è **suo**, quindi si paga qui e non si lascia in eredità |

La 34 non era nel mandato — i rinomini decisi erano due — ed è entrata perché **l'ha creata questo
lavoro**. Il criterio che la fa entrare è lo stesso che tiene la tabella onesta: una riga che oggi
costa un rigo, e domani costa a qualcuno il tempo di capire perché una regola parla di un package
che non esiste più.

Il rinvio era stato preso due volte — ADR 0029 la prima, ADR 0033 §7 e la dec. G di M11.1 la
seconda — ogni volta con la stessa formula: *alla terza si rinomina*. Il rinomino è stato **il
primo commit della milestone, da solo**, perché un commit che rinomina *e* aggiunge è un commit in
cui la revisione guarda il codice nuovo.

Un ADR è immutabile e continua a nominare la regola com'era: `RENAMED_RULES` è dove la storia dei
nomi vive come **dato e non come commento**, e ha i suoi guardiani — ogni chiave assente da
`RULES`, ogni valore presente, ogni nome vecchio ancora stampato da un ADR (se nessuno lo nomina
la riga non è storia, è peso morto) e nessuna riga che dichiari un rinomino che nessun documento
ha deciso. Ha assorbito la tabella locale che `tests/docs/test_adr_perception.py` teneva per la
regola 33: due registri per uno scopo solo sono lo stesso difetto un piano più su.

`Regole aggiunte:`

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 45 `what-ela-hears-leaves-no-named-file` | nessuna scrittura di file, nessun file temporaneo | i due moduli attraverso cui passano i campioni | nessuna esenzione |

Non un'estensione della 41: quella si chiama `the-voice-leaves-no-named-file`, e allargarla a ciò
che ELA *sente* sarebbe stato il quarto nome più stretto della regola, tre commit dopo averne
pagati due. E il soggetto è **più stretto** di `LISTENING_MODULES` di proposito: `tools/listen.py`
tiene il trascritto, non l'audio, e lo consegna allo store che lo scrive con un nome e una
scadenza. Così la regola non ha **nessuna esenzione** — il file senza nome si fa in `darwin.py`,
dove la porta al sistema operativo già sta (regola 32, e ADR 0034 §8: una regola con un'esenzione
è una regola che qualcuno allarga).

`Regole estese:`

| Regola | Come cambia | Perché |
|---|---|---|
| 35 `content-stays-on-the-machine` | una **terza** tupla, `LISTENING_MODULES` | le metà devono restare riapribili una alla volta (ADR 0033 §7): con un elenco solo, riaprire la voce riaprirebbe lo schermo in silenzio |

Entrambe scritte, coi casi negativi, **nel commit precedente** a quello che introduce il codice
dell'ascolto. È ADR 0030 §15 applicato la quarta volta.

Due nomi di detector sono stati corretti nello stesso passaggio, perché sarebbero rinati stretti il
giorno dopo: `VOICE_FILE_WRITERS` → `NAMED_FILE_WRITERS`, `VOICE_WRITE_MODES` → `WRITE_MODES`. Un
detector letto da due regole non può chiamarsi come una delle due.

## 10. Il debito di ADR 0035 §7, saldato

ADR 0035 §7 datò il 2026-09-09 un debito — i conteggi in coda a `CONSTANTS`, scritti a mano e non
più veri — e lo assegnò *«alla milestone sulla disciplina della suite, e va insieme alla regola
45»*. La regola 45 è questa: **il congegno ha funzionato come doveva**, e chi aggiunge la regola
paga.

E si è rotto di nuovo durante il pagamento: aggiungere **una** riga `Constant` a una regola
esistente ha spostato i detector da 81 a 82, quindi anche i numeri «veri» che ADR 0035 aveva
scritto a mano *per denunciare i numeri scritti a mano* sono scaduti dentro la milestone che li
riparava.

La lettura scelta dall'utente: **righe, non nomi distinti** — *un docstring in cima a una tabella
dice quanto è grande la tabella, non la cardinalità di un insieme* — e **ogni numero porta la sua
unità**, perché è l'omissione dell'unità ad aver reso la frase ambigua e non il numero. E
**derivati**, non riscritti a mano coi valori giusti di oggi: *un numero corretto scritto a mano è
lo stesso difetto rimandato di sei mesi*. `constants_summary()` li conta; una volta che li conta il
codice, «quale lettura intendeva chi scrisse ADR 0027» smette di essere una domanda.

La difesa di ADR 0035 §7 era scritta per accorgersi del proprio pagamento, e si è rovesciata: ora
asserisce che la frase non c'è più, che `constants_summary` c'è, e che un documento di decisione
dica dove è finito il debito.

## 11. L'evento si scrive all'apertura, e la finestra che apre è nuova

Nasce qui il tipo che ADR 0028 §10 aveva promesso: *l'audit registra ciò che ELA decide*, e quando
ELA **causa** un cambio di stato quella è una scelta e si registra.

**`SENSOR_ACTIVATED`**, e non `DEVICE_*`: in questo repository `DEVICE_` è il vocabolario dei nodi
di §16, e un `DEVICE_ACTIVATED` accanto a `DEVICE_SELECTED` direbbe una cosa completamente diversa.

**Scritto all'apertura, non alla fine.** Un evento scritto alla fine descriverebbe meglio — saprebbe
la durata reale — e mancherebbe **esattamente nel caso peggiore**: ELA apre il microfono, qualcosa
muore, e nell'audit non c'è traccia che sia mai stato aperto. La durata reale non si perde: sta in
`seconds_recorded` nel risultato. L'audit dice *ELA ha deciso di aprire il tuo microfono, per tanti
secondi*; il risultato dice *ed è rimasto aperto per tanti*.

**Chi lo scrive, e non è il tool — ed è ADR 0026 §10, non un fatto nuovo.** *Chi sceglie scrive,
non chi tocca*: **l'executor sceglie di chiamare, il tool tocca il dispositivo.** Non nasce un
quarto genere di scrittore dell'audit, si applica il criterio che già governa chi scrive: la
capability dichiara che cosa accende (`CapabilitySpec.activates_sensor`) e l'executor scrive
l'evento prima di chiamare il tool. È anche la forma che `prompt_arguments` ha già — la capability
dice ciò che è vero di sé, un meccanismo generico agisce — e generalizza alla webcam, che §11
nomina accanto al microfono.

Ha anche una conseguenza sui test che ha confermato la scelta: **provare l'ordine non richiede un
microfono.** Una capability finta che dichiara il sensore e non apre niente basta a dimostrare che
l'evento precede il tool; se lo scrivesse il tool, ogni test di quell'ordine avrebbe avuto bisogno
di un tool che apre un dispositivo.

`SensorName` ha **un solo membro**: la webcam entra con la milestone che la apre, perché un valore
che nessuno può produrre è ciò che ADR 0026 §7 chiama peggio di una difesa assente.

E la distinzione decisa il 2026-09-08 resta: la sonda dice soltanto ciò che osserva. Mentre ELA
registra, `/perception` dirà `ACTIVE` con causa `OBSERVED` — vero, e non sa che è ELA. «Acceso **da
ELA**» è un fatto che ELA sa di sé, sta in chi ha aperto il dispositivo, e **quello** lo scrive
nell'audit (*chi sceglie scrive*, ADR 0026 §10).

**La finestra di crash che questo apre è nuova, per due ragioni distinte.**

La prima è formale: la derivazione delle finestre legge le **righe di una tabella**, e una
scrittura nuova in mezzo alla sequenza non produce una riga — quindi la difesa smetterebbe di
coprire **senza fallire**. `SENSOR_ACTIVATED` si infila fra la finestra 6 (`consume`) e la 7a (il
tool ha prodotto l'effetto, nessuna traccia) di ADR 0015 §8, e spacca quell'intervallo in due.

La seconda è di sostanza: in tutta quella tabella **ogni evento è scritto dopo la cosa che
registra**. Questo è il primo scritto **prima**, ed è ciò che la decisione vuole — ma crea una
forma di buco che non esisteva: non «ho fatto una cosa e non l'ho scritta», bensì **«ho scritto che
stavo per farla, e non si sa come è finita»**.

Non si chiude con un secondo evento — un `SENSOR_RELEASED` scritto dal processo che sta morendo è
precisamente l'evento che nel caso che conta non verrebbe scritto. Si chiude con **una riga**:
questa finestra è classificata **come la 7a, non riparabile per costruzione** (l'effetto e
l'`INSERT` sono due sistemi), la delimitano la scadenza propria del figlio (§6) e `recover()`
all'avvio, e **le tabelle si trovano per struttura invece di essere elencate** — un elenco scritto
a mano di quali ADR ne portano una avrebbe fatto passare inosservato il terzo.

| # | Il processo muore dopo… | …e prima di | Stato che resta | Retry |
|---|---|---|---|---|
| L1 | `SENSOR_ACTIVATED` | il ritorno del tool | un'apertura senza risoluzione nell'audit; il figlio può sopravvivere fino alla propria scadenza | `recover()` chiude lo step al prossimo avvio; il microfono lo chiude il figlio da solo. **Non riparabile per costruzione**, come la 7a. |

## 12. Un debito datato: `PROVIDER_CALLED` non lo scrive nessuno

Trovato lavorando qui, e non riparato qui. `AuditEventType.PROVIDER_CALLED` esiste nell'enum dal
M7.2 e **nessun modulo di `src/ela` lo scrive**. È esattamente ciò che ADR 0026 §7 chiama peggio di
una difesa assente: un valore che non può scattare, dentro l'enum che descrive tutto ciò che ELA
sa di aver deciso. Chi legge la catena di §32 vede un tipo che promette una traccia che non esiste.

C'è anche un candidato al posto suo, e va nominato perché la riparazione non è ovvia: la chiamata a
un provider **è già** nell'audit, dentro `TOOL_EXECUTED`, che porta `usage` — «provider usage
metadata» è una delle cose che §32 chiede al log di tenere, e il campo esiste e viene riempito
(ADR 0020 §6). Quindi la domanda non è «chi lo scrive», è **«serve, o va tolto?»**, e la risposta
dipende da che cosa vorrà distinguere chi avrà due fornitori accesi contemporaneamente.

Non si ripara qui: sarebbe scope di questa milestone speso su una domanda che riguarda il Model
Router e non l'ascolto, e sceglierne una delle due risposte in silenzio è precisamente la cosa che
questo repository non fa.

**Debito a carico di chi aggiungerà il prossimo `AuditEventType`**, dichiarato il **2026-09-10**.
È lo stesso congegno con cui ADR 0035 §7 si è fatto pagare da chi ha aggiunto la regola 45, e ha
funzionato: chi tocca l'enum si trova davanti l'unico membro che non scatta e decide, invece di
aggiungerne un altro accanto.

Fino ad allora il debito ha una sola difesa, ed è la più piccola possibile: un test verifica che
`PROVIDER_CALLED` **continui a non avere uno scrittore**. Il giorno in cui qualcuno gliene dà uno —
o lo toglie dall'enum — quel test fallisce e questa sezione esce con lui, perché un debito che non
sa di essere stato pagato è la stessa specie di bugia dei valori che descrive.

## Alternative considerate

- **`Speech.framework`** (§2). Scartata per il troncamento, non per la struttura — e con la sua
  velocità, la sua località misurata e la sua confidenza per segmento scritte per intero, perché
  chi la riaprirà trovi i numeri e non un'opinione.
- **Un helper Swift compilato** per registrare. Scartata: la regola 33 smetterebbe di trovare il
  suo soggetto, Xcode CLT diventerebbe una dipendenza di build, e TCC lega il grant all'identità
  del binario — ricompilare invalida il permesso, che è una proprietà del prodotto installato.
- **`faster-whisper` via pip.** Scartata per una ragione strutturale: sarebbe una dipendenza
  pesante e dipendente dalla piattaforma — ciò che ADR 0028 §2 si comprò evitando — e girerebbe
  dentro il processo di ELA, perché un figlio che importa terze parti è ciò che la regola 33 vieta.
- **STT cloud.** Scartata dalla soglia che questa milestone alza: dopo M11.2, «capire che cosa ha
  detto l'utente» non è più una ragione valida per mandare audio fuori da questa macchina.
- **Tenere l'audio con un TTL**, come una cattura (§3). Scartata: la materia prima non ha un
  secondo lettore, e il TTL di cinque minuti non è una politica che qualcuno abbia spiegato alle
  persone che sono nella registrazione senza saperlo.
- **Tenere l'audio solo quando il trascritto è vuoto o incerto.** Scartata senza tabella: una
  ritenzione condizionale si accenderebbe **proprio** nel caso in cui l'audio contiene qualcosa
  che ELA non ha capito, cioè quello in cui tenerlo è più invadente.
- **Fidarsi della confidenza al posto del picco** (§7). Scartata: separa in questo campione
  (mediana 0,677 sugli zeri contro 0,986–0,999 su un enunciato pulito), ma fidarsene vorrebbe dire
  scegliere una soglia, e una soglia è una decisione (§45).
- **Un secondo evento di audit alla chiusura.** Scartata: chiudere non è una decisione, e un
  `SENSOR_RELEASED` scritto dal processo che sta morendo è precisamente l'evento che nel caso che
  conta non verrebbe scritto (§11).

## Conseguenze

- ELA sente, e ciò che consegna sono parole: dell'audio non resta niente, nemmeno se ELA muore a
  metà registrazione, perché l'inode non ha un nome e il kernel lo libera.
- **Una lettura vuota non è più ambigua in tre modi.** «Non hai detto niente», «sono stata
  rifiutata» e «questo dispositivo non riceve segnale» sono tre risposte diverse con tre codici.
- Le regole di architettura passano da quarantaquattro a **quarantacinque**, e una ha cambiato
  nome per la prima volta nella storia del repository.
- I port passano da ventidue a **ventitré**.
- I conteggi in coda a `CONSTANTS` si contano da soli.

### Vincoli dichiarati, da riaprire quando serviranno

- **L'audio non si tiene**, e con lui la possibilità di dimostrare a posteriori che cosa fu detto.
- **Nessuna mezza memoria: il trascritto non sopravvive al task** — un trascritto durevole è
  memoria, e la memoria è Fase 15.
- **Una stanza silenziosa non ha picco zero**: il gate prende il microfono negato e il dispositivo
  muto, non il sussurro lontano.
- **`p` non è una confidenza calibrata.**
- **Un microfono orfano vive fino al tetto più il margine.**
- **Nessuna diarizzazione**: ELA non sa chi ha parlato e non ci prova.
- **Nessun ascolto continuo, nessuna parola di risveglio**: il microfono si apre quando uno step lo
  chiede e il Guardian acconsente.
- **`ELA_CAPTURE_DIR` resta il nome di una directory che tiene anche i trascritti**: un nome nel
  repository si cambia con un commit, una directory nella home dell'utente con una migrazione.
