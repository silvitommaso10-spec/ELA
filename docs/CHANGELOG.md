# Changelog

Che cosa ELA ha guadagnato, milestone per milestone, e l'ADR che l'ha deciso. Una voce per ogni
milestone di `docs/milestones/` che non sia ancora una `Proposta`, e nessuna voce senza la sua
milestone: `tests/docs/test_changelog.py` chiude il mondo nelle due direzioni, e verifica che l'ADR
nominato esista **e** sia nominato dal documento della milestone. Le tre milestone di avvio non
nominano nessun ADR — non ce n'erano ancora — e portano `—`, che è un'assenza dichiarata e non una
riga dimenticata.

Il formato non è [Keep a Changelog](https://keepachangelog.com): ELA non ha ancora utenti a cui
raccontare «Added/Fixed/Changed», e ciò che serve oggi è la storia delle decisioni.

## v0.1 — 2026-09-07

La prima versione che gira: un task nasce da un intento, riceve un piano, viene autorizzato,
eseguito su un nodo, verificato e chiuso, e ogni passaggio lascia una riga in un log che si accorge
se qualcuno lo riscrive. Due tool reali (`core.echo`, `workspace.write_note`), uno che parla con un
modello (`model.complete`), un'API su loopback e una CLI che la usa.

Ciò che v0.1 **non** fa, e i limiti che dichiara, stanno in
[`docs/milestones/M9.4.md`](milestones/M9.4.md), sezione «L'elenco di ciò che in v0.1 è
semplificato» — sessantasei voci, ognuna con il suo rimando. Il disegno di com'è fatta è in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

### Fase 0 — Il cantiere

- **M0.1** — Bootstrap del repository: `uv`, `ruff`, `mypy --strict`, `pytest`, e un `make check` che è il cancello di tutto ciò che segue. (—)
- **M0.2** — CI su GitHub Actions e il template di milestone: ogni milestone dichiara i suoi criteri di accettazione, e uno script rifiuta quelle che non lo fanno. (—)
- **M0.3** — Il framework degli architecture test: le regole di dipendenza come funzioni pure sull'albero dei sorgenti, ognuna con il suo caso negativo. (—)

### Fase 1 — Il dominio

- **M1.1** — Il domain model: entità pydantic immutabili, identità esplicite, istanti sempre in UTC. (ADR 0003)
- **M1.2** — La state machine del Task: transizioni legali dichiarate una volta, e una transizione illegale che solleva invece di correggere. (ADR 0004)
- **M1.3** — I ports: `async` dove c'è I/O, errori nominati, e il Core che non conosce nessuna implementazione. (ADR 0005)

### Fase 2 — La memoria

- **M2.1** — Persistenza su SQLite con SQLAlchemy async, ORM tenuto separato dal dominio da una regola e da un mapper. (ADR 0006)
- **M2.2** — L'audit log persistente con hash chain: append-only a quattro livelli, e una catena che rende visibile chi riscrive il database. (ADR 0007)

### Fase 3 — Il motore

- **M3.1** — Il Task Engine: la tabella delle operazioni, l'idempotenza per chiave, e l'ordine delle scritture dichiarato. (ADR 0008)
- **M3.2** — Il Task Graph: gli step come DAG, lo stato derivato dalla trail e mai scritto due volte. (ADR 0009)

### Fase 4 — Il permesso

- **M4.1** — Il catalogo delle capability: registro immutabile, schema degli argomenti, scope come confine. (ADR 0010)
- **M4.2** — Il Permission Guardian: decide su capability e contesto, non possiede tool, e nel dubbio nega. (ADR 0011)
- **M4.3** — Autorizzazioni e Approval: un grant nasce da un "sì" dell'utente, si consuma una volta sola, e scade. (ADR 0012)

### Fase 5 — L'azione

- **M5.1** — L'executor e i due tool: uno step per chiamata, il grant scelto e consumato prima dell'azione, e l'unico posto del Core che chiama un tool. (ADR 0013)
- **M5.2** — La verifica: le condizioni di successo sono un vocabolario chiuso, e la parola del tool non basta. (ADR 0014)
- **M5.3** — La persistenza di `Approval` ed `ExecutionResult`: la richiesta vive in uno store, il risultato pure, e un retry riprende dalla prima scrittura che manca. (ADR 0015)

### Fase 6 — I nodi

- **M6.1** — Il Device Registry: la disponibilità di un nodo è derivata dal suo ultimo heartbeat, mai letta da una colonna. (ADR 0016)
- **M6.1b** — Il nodo che non impara, riparato il 2026-09-09: `ensure_local` restituiva la riga che trovava e non guardava mai se ciò che il chiamante dichiara è ancora ciò che la riga dice, quindi una capability aggiunta dopo il primo avvio non diventava mai eseguibile — trovato verificando M11.3, e valeva identico per le due capability di percezione. La riga ha due metà: quella dichiarata la rifà una ri-registrazione, quella osservata la scrive solo l'heartbeat e la regola 44 tiene separate le due. Una capability aggiunta è eseguibile al riavvio successivo, una rimossa smette di esserlo allo stesso riavvio, e i due eventi nuovi dicono *quale* tool è comparso o sparito — il debito che ADR 0016 §6 aveva dichiarato nel 2026-09-07. E `waiting_device` smette di essere un valore nudo: la ragione arriva fino a `ela task run`, per ogni motivo e non per uno. La voce sta qui, sotto la Fase 6, perché è qui che il difetto vive. (ADR 0035)
- **M6.2** — Il Device Orchestrator: filtri di idoneità, punteggio esplicito, e l'attesa invece di un ripiego. (ADR 0017)
- **M6.3** — Il Task Runner: la camminata del grafo, ri-entrante, che non scrive nulla di suo. (ADR 0019)

### Fase 7 — Il modello

- **M7.1** — `ModelProvider` e il provider Anthropic: la chiave la conosce solo ELA, lo stato è dichiarato, un fallimento pulito è un fallimento. (ADR 0020)
- **M7.2** — Il protocollo STARTED e `model.complete`: il primo tool che non può promettere che due volte è una. (ADR 0021)
- **M7.3** — Il Model Router: una tabella di rotte su profili, e il rifiuto di mandare il contenuto dell'utente a un provider che nessuno ha scelto. (ADR 0022)

### Fase 8 — La porta

- **M8.1** — La composition root e l'API locale: `ela.composition` monta tutto una volta, quindici rotte su loopback dietro un token. (ADR 0023)
- **M8.2** — La CLI: un client dell'API locale, mai una seconda implementazione. (ADR 0024)
- **M8.3** — I debiti raccolti di Fase 8: i port che non riportano righe inutili, e i limiti dichiarati di quelli che restano. (ADR 0025)

### Fase 9 — Le liste che si accorgono di essere false

- **M9.1** — Le difese: il confronto del token a tempo costante reso strutturale, il piazzamento come dato che l'executor verifica, e due regole nuove. (ADR 0026)
- **M9.3** — Le esenzioni senza codice dietro, ritirate: una tabella di 116 coppie che fallisce quando una porta non ha più nessuno dietro. (ADR 0027)
- **M9.4** — Le finestre di crash derivate dall'ADR e i negativi dell'API osservati invece che dichiarati, con i documenti della release. (ADR 0015)

## Non ancora rilasciato

### Fase 10 — La percezione

- **M10.1** — Il Perception Core, primo anello di §10: ELA guarda la macchina su cui gira, dice quali permessi le mancano senza poter morire nel farlo, e ogni stato di §11 viaggia con la causa che dice se è un'osservazione o un default. (ADR 0028)
- **M10.2** — Il secondo anello: ELA può fotografare lo schermo, dietro una capability MEDIUM che passa dal Guardian come ogni altra e una domanda che dice *per cosa*. L'immagine resta su questa macchina, vive cinque minuti in una cartella privata che non è il workspace, e quando il permesso manca ELA lo dice senza tentare — perché tentare è come si registra un diniego permanente. Verificata contro `screencapture` vero nei due versi dell'interruttore. (ADR 0029)
- **M10.3** — Il terzo anello, e non costa un permesso: ELA sa quali applicazioni l'utente sta usando — misurato, il proprietario di una finestra è gratis e il suo **titolo** costa lo stesso grant di uno screenshot, quindi il titolo è contenuto e non entra — e sa che cosa c'è scritto in una cattura che ha già fatto, leggendola con Vision sulla macchina, senza rete e senza che un carattere esca. Il testo eredita la scadenza della sua immagine per costruzione: un derivato senza origine è già scaduto. (ADR 0030)
- **M10.4** — Il Context Core: ELA compone in un solo istante la risposta alla domanda di §44 — cosa sta facendo l'utente, cosa stava facendo prima, quali task sono in corso, quali scadenze esistono, su quale nodo gira — e, per le tre righe di §44 a cui non può rispondere, **nomina la fonte che le manca** invece di tacere: calendario, email, documenti, progetti, rilevanza. L'elenco delle assenze non è scritto da nessuna parte: è la differenza fra le fonti che §44 chiede e i campi che lo snapshot ha, quindi il giorno in cui il calendario arriverà l'assenza sparirà da sola. Il confine con la memoria di §21 è deciso qui — ciò che si ricalcola è contesto, ciò che perderlo perde informazione è memoria — e la strada che porterebbe il contesto dentro un prompt è chiusa da una regola, non da una nota. (ADR 0032)

### Fase 11 — La voce

- **M11.1** — La prima uscita di ELA verso il mondo fisico: ELA dice una frase ad alta voce, dietro una capability MEDIUM che passa dal Guardian e una domanda che dice *per cosa*, e non lascia traccia — nessun file, nessuno store, nessun byte fuori dalla macchina, e una regola che lo rende controllabile invece che promesso (`say -o` è a un carattere di distanza). Il verifier **dichiara ciò che non prova**: che ELA ha chiesto a macOS di dire quelle parole e che macOS ci ha messo il tempo di dirle, non che qualcuno abbia sentito. E la domanda che decideva la fase ha una risposta: la meccanica di una conversazione non si compra separata dal cervello, quindi il loop è nostro e si comprano le estremità. (ADR 0033)
- **M11.2** — L'ascolto, e la prima volta che qualcosa entra in ELA **dalla stanza**: ELA apre il microfono di questo Mac per un numero dichiarato di secondi, dietro una capability MEDIUM che passa dal Guardian come ogni altra, e consegna **un trascritto, non l'audio**. È il primo dato di ELA che contiene persone che non sono l'utente — uno screenshot fotografa ciò che l'utente ha scelto di avere davanti, un microfono aperto prende chiunque fosse nella stanza — e la domanda di §57 qui non è dove mandiamo il dato, che non esce, ma quanta materia prima ELA ha diritto di tenere quando il derivato basta: la risposta è nessuna, e la regola 45 la rende controllabile invece che promessa, perché i campioni non prendono mai il nome di un file. Trascrive whisper.cpp sulla macchina, senza rete e senza che un carattere esca; il picco del segnale decide che una voce c'è stata **prima** di chi la interpreta, così «stanza silenziosa» è una proprietà del suono e non una soglia sul testo; e il trascritto non sopravvive al task, perché un trascritto non si ricalcola — è memoria (§21), e la memoria è Fase 15. Porta anche due debiti pagati: il package `perception` prende il nome della regola che lo protegge, `ela.infrastructure.machine`, in un commit da solo, e i conteggi scritti a mano in coda a `CONSTANTS` li conta ora `constants_summary()` — il debito che ADR 0035 §7 aveva messo a carico di chi avrebbe aggiunto la regola 45. (ADR 0036)
- **M11.3** — La voce di §9, e il primo dato che esce da questa macchina per qualcosa che non è un modello: ELA parla con una voce femminile e professionale scelta a orecchio, dietro una capability **sua** — `voice.speak_online`, il cui nome dice cosa succede e non dove sta il server — perché un grant su «puoi parlare» non è un grant su «puoi mandare le mie parole a un fornitore». Le quattro domande di §57 hanno una risposta misurata e non citata: il testo **è conservato** da ElevenLabs e rileggibile nella dashboard dell'utente — verificato rileggendo le frasi della ricognizione — e la modalità che lo impedirebbe è enterprise, accettata dal server e ignorata. Quindi il risultato porta la **ricevuta**: l'id della copia che loro hanno tenuto, e i crediti che loro dichiarano, mai una parola del testo. L'audio torna come byte e non ha un nome — un inode scollegato passato al riproduttore come `/dev/fd/N`, perché `afplay` rifiuta una pipe — e non è lo store delle catture: quello serviva a un verifier che rilegge, e qui non c'è niente da rileggere. (ADR 0034)

### Fase 12 — I nodi sulla rete

- **M12.1** — L'identità dei nodi: ELA smette di stare soltanto su questa macchina, e una macchina entra nel suo mondo perché l'utente l'ha ammessa. L'utente conia un codice monouso con la `privacy` che il nodo avrà — mai `LOCAL_ONLY`, che resta di `local` — e il nodo che lo presenta riceve un id che non ha scelto e un segreto suo, che ELA custodisce come SHA-256 e confronta in tempo costante in un modulo solo; parla solo per sé, dalle sue due rotte, e ne esce quando l'utente lo revoca: la riga resta, il segreto non apre più niente, e l'orchestratore lo scarta dicendo «revocato» (`REVOKED`, F6). La riga di un nodo ha tre metà — dichiarata dal nodo, osservata dal registro, imposta dall'utente — e ogni metà ha la sua scrittura: l'annuncio è condizionale sulla revisione, `If-Match` sul filo, così due processi che dicono di essere lo stesso nodo non si sovrascrivono e un annuncio non si perde sotto un heartbeat. Il middleware riconosce tre identità, i rifiuti che nominano un nodo esistente vanno nell'audit e quelli anonimi si contano; `ELA_USER_NAME` è ritirato, con una lapide sola per ogni variabile ritirata, e chi approva è l'identità risolta. ELA ascolta su loopback e, se dichiarata e presente, sulla tailnet. In M12.1 un nodo remoto non riceve ancora lavoro — lo porta M12.2 —, e la milestone paga il debito di ADR 0036 §12: `PROVIDER_CALLED` ed `ERROR_RECORDED` escono dall'enum, e ogni tipo di evento ha ora uno scrittore. (ADR 0037)
- **M12.2** — Il lavoro che esce da questa macchina: ELA affida la chiamata a un tool a un nodo che ha vinto il piazzamento, e il nodo la esegue davvero. La linea passa dove D1 l'ha messa — `tool.execute` —, e tutto ciò che mette una corsa nella catena di §32 resta del Core: il nodo consegna una **busta** con ciò che il suo tool ha detto, e l'esito lo conia ELA, con un id derivato dall'assegnazione e l'istante del proprio orologio, perché con l'orologio del nodo `TOOL_EXECUTED` nascerebbe prima del `PERMISSION_DECIDED` che l'ha permesso. **Il tempo decide per chi tace**: un'assegnazione ha una scadenza sola, derivata in lettura e mai spazzata, e alla scadenza un'offerta che nessuno ha preso torna in gioco per qualunque tool — mentre un lavoro preso e taciuto si chiude `interrupted` se il suo tool non si può ripetere, perché «se ha agito non si sa» è un dubbio e un dubbio non si inventa. Ogni scrittura che fissa una scadenza scrive prima un heartbeat del task, e questo rende `recover()` sicuro per costruzione invece che per coordinamento. Un nodo parla da **cinque** rotte: le due di M12.1 più chiedere lavoro, riportarlo e chiedere più tempo, con l'id dell'assegnazione **nel corpo** perché l'elenco delle rotte di un nodo resta letterale e nessun id entra nei suoi percorsi; la richiesta di lavoro si tiene aperta e allo spegnimento **chi aspetta viene svegliato** — misurato: il gestore del segnale è il solo posto abbastanza presto, e interrompere un handler che può essere avvisato è lo strumento sbagliato. La sensibilità di un task smette di essere un argomento che nessuno poteva passare e diventa un campo dichiarato alla nascita e immutabile, `Task.max_privacy`: è il difetto che D18 nominava — non che un nodo non potesse lavorare, ma che **nessuno potesse dichiarare** che un task glielo permetteva — e ADR 0017 §8 è rivisto apertamente per il task. Ciò che si verifica solo qui non viaggia (`UNVERIFIABLE`, F7): quattro capability su otto hanno un verifier che legge il disco di questa macchina, e una nota con lo stesso percorso nella workspace del Core sarebbe un falso positivo — scritto come test, non come nota. Un rifiuto che diceva troppo è stato trovato scrivendo i test: i tre modi in cui un lavoro non è tuo ora condividono **una sola frase**, perché dalla differenza un nodo potrebbe mappare le assegnazioni degli altri. E la milestone consegna il contratto che M12.3–M12.5 implementano: tredici storie scritte **una volta** contro un `NodeDriver`, con un nodo finto che esegue tool veri, e una mappa di ciò che un'implementazione non sa recitare che diventa uno skip visibile invece di un `if`. (ADR 0038)
- **M12.3** — Il nodo macOS: questa macchina diventa **anche** un nodo. Un processo separato dal Core si arruola con un codice che una persona gli ha portato, legge la propria riga, si annuncia, dice di essere lì, chiede lavoro in long-poll, lo esegue con i **suoi** tool, consegna la busta e chiede più tempo quando serve — e non decide niente, il tempo compreso: una regola nuova, la 53, vieta a `ela.node` di coniare una scadenza, perché senza di essa «il Core decide il tempo» sarebbe rimasta una frase in un documento. Le tredici storie del contratto di M12.2 passano ora con **due** kit e la mappa `UNSUPPORTED` del secondo è **vuota**: una piattaforma vera recita il protocollo per intero, e il kit costruisce il codice che `ela node run` avvia, non un'imitazione. Implementare un contratto significa anche scoprire dove non chiude, e il nodo vero ha trovato subito un buco che il nodo finto non poteva vedere — la sua «riavviata» è lo stesso oggetto Python: **un processo che riparte non ha nessuna revisione da cui annunciarsi**, e le tre strade senza una rotta nuova erano tutte e tre già scartate altrove (una cache che nessuno risincronizza, il numero letto dalla prosa di un errore, una seconda identità per la stessa macchina). Quindi `GET /nodes/me`, la sola rotta nuova, con la revisione nell'`ETag` dove l'annuncio già la cerca; il `412` si rilegge **una volta** e il secondo di fila resta il gemello di ADR 0035 §5, perché la rilettura sta sopra l'atto e non dentro. Il segreto vive in un file `0o600` scritto con `O_EXCL` e **non nel portachiavi**, e questa volta per misura e non per opinione: sei sonde su questa macchina mostrano che l'ACL riconosce il `cdhash`, quindi ogni aggiornamento dell'interprete renderebbe il segreto illeggibile dietro un dialogo che un processo di sfondo non ha a chi mostrare — lo stesso muro che ADR 0029 §16 aveva già trovato per TCC, e si abbatte una volta sola, con `launchd`, quando ELA avrà un eseguibile firmato suo. `ela node run` diventa una **terza specie** di comando — uno la cui vita non è una richiesta — invece di allargare un `==` a un caso che la sua ragione non copriva, e costa una parola e non una regex. E la prova che conta non è stata un test: con Core e nodo in due terminali, `say` è nato sotto il pid del nodo, l'audit l'ha nominato, un Core ucciso a metà non ha perso la busta, `workspace.write_note` non è arrivato — e la prima esecuzione a mano ha trovato il difetto che nessun test aveva, un nodo che riportava una volta sola e dopo un minuto era vivo, sveglio e invisibile. (ADR 0039)
