# ELA — stato del progetto

**Questo file è il punto di ripartenza.** Chi lo apre deve poter riprendere il lavoro senza
nessuna conversazione precedente: dove siamo, che cosa manca, e le decisioni che non stanno in
nessun ADR perché non sono decisioni tecniche.

Non è un posto dove si decide. La fonte di verità resta [`spec/ELA_spec.md`](spec/ELA_spec.md);
le decisioni stanno in [`adr/`](adr/README.md); che cosa entra in una milestone sta in
[`milestones/`](milestones/); che cosa ELA ha guadagnato, milestone per milestone, sta in
[`CHANGELOG.md`](CHANGELOG.md); com'è fatta sta in [`ARCHITECTURE.md`](ARCHITECTURE.md). Qui ci
sono i puntatori, i conteggi, e **ciò che non ha nessun altro posto**.

**Cinque blocchi sono generati** leggendo il repository, con `scripts/generate_stato.py`, e
`tests/docs/test_stato.py` li riconfronta byte a byte a ogni `make check`: una milestone aggiunta,
una regola nuova, un debito saldato, una capability in più, e questo file fallisce finché non viene
rigenerato. **La §5 è scritta a mano** e lo dichiara: sono scelte dell'utente, e non esiste codice
da cui possano essere derivate. Il criterio è quello di `ARCHITECTURE.md`: *un documento che non
può accorgersi di essere diventato falso è decorazione* — e un punto di ripartenza falso è peggio
di nessun punto di ripartenza, perché chi lo legge non ha motivo di dubitarne.

Per rigenerare:

```
uv run python scripts/generate_stato.py
```

## 1. Dove siamo

- **v0.1.0**, taggata il 2026-09-07: un task nasce da un intento, riceve un piano, viene
  autorizzato, eseguito su un nodo, verificato e chiuso, e ogni passaggio lascia una riga in un log
  che si accorge se qualcuno lo riscrive. API su loopback dietro un token, CLI che la usa.
- **Dopo il tag, e fuori da qualunque release**: la **percezione** (Fase 10 — ELA fotografa lo
  schermo, ne legge il testo sulla macchina, sa quali applicazioni l'utente sta usando, e compone
  il contesto di §44 dicendo quali fonti le mancano) e la **voce** (Fase 11 — ELA parla, con
  `say` di macOS e con ElevenLabs, e ascolta il microfono restituendo un trascritto e non l'audio).
- **ELA gira su una macchina sola.** Il Mac è insieme Core e unico nodo: `local`, la cui riga la
  scrive il processo stesso all'avvio, con un id deterministico *perché è questa macchina*. Nessun
  nodo remoto esiste, nessun nodo si autentica, e il Device Orchestrator sceglie fra un candidato
  solo. **È esattamente ciò che la Fase 12 cambia.**
- **Il ciclo di lavoro** è quello di `CLAUDE.md`: una milestone alla volta, SPEC → IMPLEMENTATION →
  TEST → REVIEW → COMMIT, su un branch di lavoro; il merge su `main` lo fa l'utente dopo revisione
  esterna. `make check` in primo piano, una volta, alla fine della milestone; il controllo Linux è
  la CI sul branch, verde su entrambi i runner prima del merge.

## 2. Le milestone

Lo stato è la riga `- **Stato:**` di ogni documento; il nome della fase è quello che il changelog
le dà, e una fase senza nome è una fase che non ha ancora consegnato una milestone fuori da
`Proposta`.

<!-- generato da scripts/generate_stato.py: le milestone -->

| Fase | Milestone | Stato | Che cosa porta |
|---|---|---|---|
| 0 — Il cantiere | `M0.1` | Implementata | Bootstrap del repository |
| 0 — Il cantiere | `M0.2` | Implementata | CI e template di milestone |
| 0 — Il cantiere | `M0.3` | Implementata | Framework di architecture test |
| 1 — Il dominio | `M1.1` | Implementata | Domain model |
| 1 — Il dominio | `M1.2` | Implementata | Task state machine |
| 1 — Il dominio | `M1.3` | Implementata | Ports |
| 2 — La memoria | `M2.1` | Implementata | Persistence SQLite |
| 2 — La memoria | `M2.2` | Implementata | Audit Log persistente con hash chain |
| 3 — Il motore | `M3.1` | Implementata | Task Engine |
| 3 — Il motore | `M3.2` | Implementata | Task Graph |
| 4 — Il permesso | `M4.1` | Implementata | Capability registry |
| 4 — Il permesso | `M4.2` | Implementata | Permission Guardian |
| 4 — Il permesso | `M4.3` | Implementata | Authorization e Approval |
| 5 — L'azione | `M5.1` | Implementata | Tool e pipeline dell'executor |
| 5 — L'azione | `M5.2` | Implementata | Verification |
| 5 — L'azione | `M5.3` | Implementata | Persistenza di Approval ed ExecutionResult |
| 6 — I nodi | `M6.1` | Implementata | Device Registry |
| 6 — I nodi | `M6.1b` | Implementata | Il nodo che non impara: una capability aggiunta dopo il primo avvio |
| 6 — I nodi | `M6.2` | Implementata | Device Orchestrator |
| 6 — I nodi | `M6.3` | Implementata | Task Runner: la camminata del grafo |
| 7 — Il modello | `M7.1` | Implementata | `ModelProvider` e provider Anthropic |
| 7 — Il modello | `M7.2` | Implementata | Protocollo STARTED e `model.complete` |
| 7 — Il modello | `M7.3` | Implementata | Model Router |
| 8 — La porta | `M8.1` | Implementata | Composition root, configurazione e API |
| 8 — La porta | `M8.2` | Implementata | CLI |
| 8 — La porta | `M8.3` | Implementata | Debiti raccolti di Fase 8 |
| 9 — Le liste che si accorgono di essere false | `M9.1` | Completata | Hardening: le difese |
| 9 — Le liste che si accorgono di essere false | `M9.2` | Proposta | Le liste che restano scritte a mano |
| 9 — Le liste che si accorgono di essere false | `M9.3` | Completata | Le esenzioni che si accorgono di essere false |
| 9 — Le liste che si accorgono di essere false | `M9.4` | Completata | Le finestre, i negativi, e la release v0.1 |
| 10 — La percezione | `M10.1` | Completata | Perception Core: fondamenta |
| 10 — La percezione | `M10.2` | Completata | Screen awareness: la prima lettura di contenuto |
| 10 — La percezione | `M10.3` | Implementata | Comprendere ciò che si vede: il contesto che non costa niente, e il testo che non esce |
| 10 — La percezione | `M10.4` | Implementata | Il Context Core: comporre senza decidere, e dire ciò che non si sa |
| 11 — La voce | `M11.1` | Implementata | La voce che esce: ELA dice qualcosa, e non lascia traccia |
| 11 — La voce | `M11.2` | Implementata | L'ascolto: ELA apre il microfono, e tiene solo le parole |
| 11 — La voce | `M11.3` | Implementata | La voce di §9: la prima frase che esce da questa macchina |
| 12 — I nodi sulla rete | `M12.1` | Implementata | L'identità: provare chi si è, e poter smettere di esserlo |
| 12 — I nodi sulla rete | `M12.2` | Implementata | L'assegnazione e il protocollo del lavoro: la chiamata al tool fatta da lontano, e il tempo che decide per chi tace |
| 12 — I nodi sulla rete | `M12.2b` | Implementata | Il rinnovo passa per la porta della consegna: una frase, un codice e un audit per ogni «non è tuo» |
| 12 — I nodi sulla rete | `M12.3` | Implementata | Il nodo macOS: questa macchina diventa un nodo, e il contratto si implementa invece di descriversi |
| 12 — I nodi sulla rete | `M12.3b` | Implementata | La cartella del segreto del nodo: `0o700` anche dove il Core non l'ha creata prima |
| 12 — I nodi sulla rete | `M12.3c` | Implementata | Chi legge l'alimentazione: un campo che l'orchestratore pesa e che nessuna macchina produceva |
| 12 — I nodi sulla rete | `M12.4` | Implementata | Il nodo Windows: il contratto su un secondo sistema operativo, e ciò che il primo nascondeva |
| 12 — I nodi sulla rete | `M12.5` | Proposta | Il companion iPhone: vedere e rispondere da lontano, e un campanello che non porta lettere |
| 17 — Design | `M17.1` | Implementata | Il Design System: l'identità minima, e le regole che ogni superficie di ELA eredita |
| 17 — Design | `M17.2` | Proposta | Il Command Center v1: un client dell'API, e gli stati di ELA come proiezione |
| 17 — Design | `M17.3` | Proposta | La presenza desktop: ELA sullo schermo senza la dashboard aperta |

<!-- fine del blocco generato: le milestone -->

## 3. I numeri

Nessuno di questi è scritto a mano, ed è il motivo per cui vale la pena leggerli: sono la
dimensione del sistema oggi, non la dimensione che aveva quando qualcuno l'ha annotata.

<!-- generato da scripts/generate_stato.py: i numeri -->

| Che cosa | Quanti | Contati leggendo |
|---|---|---|
| ADR scritti | **43** | `docs/adr/NNNN-*.md` |
| Milestone | **48, di cui 44 non più `Proposta`** | la riga `- **Stato:**` di ogni documento |
| Regole di architettura | **56** | `RULES` in `tests/architecture/` |
| Contratti import-linter | **14** | `pyproject.toml` |
| Port | **25** | i `Protocol` di `src/ela/ports.py` |
| Capability di produzione | **8** | `production_catalogue()` |
| Rotte dell'API | **35** | i `router` di `ela.api` |
| Comandi della CLI | **25** | l'albero Typer di `ela.cli` |
| Vincoli dichiarati negli ADR | **200** | le sezioni «Vincoli dichiarati» |

<!-- fine del blocco generato: i numeri -->

## 4. Cosa manca

### 4.1 Le fasi

- **Fase 12 — i nodi.** È la fase in corso, e tre quarti sono fatti: ELA ha smesso di essere un
  processo su una macchina. M12.1 ha dato a un nodo un'identità provabile, M12.2 il protocollo del
  lavoro con la sua suite di conformità, M12.3 il **primo nodo vero** — questo Mac, che è anche un
  nodo: un processo separato che esegue le chiamate del Core e le riporta, e che recita le tredici
  storie del contratto senza dichiararne nessuna irrecitabile, e M12.4 il **secondo sistema**: un PC
  Windows che prende le chiamate del Core attraverso la tailnet, protegge il suo segreto con l'ACL
  della cartella e parla con la voce di Windows. Resta il companion iPhone (M12.5), sullo stesso
  contratto e con l'identità di M17.1 — e la prova che regge
  il peso di una seconda implementazione l'ha già data M12.3, trovandogli un buco: un processo che
  riparte non aveva modo di sapere la propria revisione. È la fase a cui una dozzina di documenti
  hanno rimandato qualcosa: `grep -rn "Fase 12" docs/` è l'elenco di ciò che va onorato, e
  `launchd` con il portachiavi è ciò che resta murato finché ELA non avrà un eseguibile firmato
  suo (ADR 0029 §16, ADR 0039 §6).
- **Fase 17 — il design.** Registrata il 2026-09-18: la fonte di verità è
  [`spec/ELA_design.md`](spec/ELA_design.md), e le decisioni sono nella 5.10. **M17.1, il Design
  System, è fatta** (2026-09-19, ADR 0042): ELA ha un aspetto — una sfera di luce nel vetro, azzurra
  e bianca, «stile Apple, futuristico stile JARVIS» — e `apps/design-system/` è ciò che ogni
  superficie eredita. **La prossima milestone è M12.5**, il companion iPhone, che nasce con
  quell'identità (§20 del design). Poi M17.2, il Command Center v1, prima della Fase 13; M17.3, la
  presenza desktop, alla fine.
- **Fase 15 — la memoria e la proattività.** §21 (Memory Core) e §34 (Proactive Core), rimandate
  da ADR 0023, ADR 0025, ADR 0036 e da tre milestone: il richiamo periodico di `recover()`, il
  momento in cui ELA decide di parlare da sola, e il trascritto che oggi non sopravvive al task
  perché un trascritto è memoria e la memoria è lì.
- **Le altre fasi non hanno né una milestone né una SPEC.** Il blocco qui sotto elenca le fasi che
  un documento del repository nomina e che **nessuna milestone ha ancora cominciato** — nessuna
  delle loro è uscita da `Proposta` —, e ciò che non compare non è dimenticato: è **non ancora
  deciso**, e il posto dove deciderlo è una SPEC di milestone, non questo file. La Fase 12 è uscita
  da quell'elenco quando la sua prima milestone è uscita da `Proposta` — che è il modo in cui una
  lista derivata dice che una fase ha smesso di essere futura, ed è lo stesso fatto con cui il
  changelog le dà un nome. Il numero non conta: la 17 resta nell'elenco finché M17.1 non esce da
  `Proposta`, anche se comincia prima della 13.

<!-- generato da scripts/generate_stato.py: le fasi che un documento nomina -->

| Fase | Documenti che la nominano |
|---|---|
| 13 | 3 |
| 15 | 12 |

<!-- fine del blocco generato: le fasi che un documento nomina -->

### 4.2 La spec che nessuna milestone ha ancora nominato

Non è «cosa manca» in senso stretto — §22 e §56 sono citate da milestone che non le hanno
costruite — ma la cosa più debole e verificabile: le sezioni della fonte di verità che nessuna
milestone ha **mai nominato**. È la lista da rileggere prima di decidere che cosa viene dopo. Le
cinque sezioni conclusive (§66–§70) non entrano: sono la visione, non funzionalità, e che restino
non citate è verificato invece che assunto.

<!-- generato da scripts/generate_stato.py: le sezioni della spec che nessuna milestone ha nominato -->

| Sezione | Titolo |
|---|---|
| §24 | Agent System |
| §37 | Rollback |
| §38 | Evolution Dashboard |
| §40 | Creatività |
| §41 | Programmazione |
| §42 | Ricerca |
| §43 | Studio |
| §60 | ELA e l'utente |
| §61 | ELA deve anticipare |

<!-- fine del blocco generato: le sezioni della spec che nessuna milestone ha nominato -->

## 5. Le decisioni che non stanno in nessun ADR

**Questa sezione è scritta a mano, e non può essere altrimenti**: sono scelte dell'utente — di
prodotto, di costo, di come si lavora — e nessuna riga di codice le contiene. Stanno qui perché
altrimenti starebbero solo in una conversazione, e una conversazione non è un posto.

### 5.1 Niente app iPhone nativa

Il Companion Node di §6 si fa con **Shortcuts, notifiche push (ntfy o Pushover) e Safari sulla
rete privata**. Non ci sarà un'app nativa.

*Perché:* un'app nativa vuole un account sviluppatore, una firma, una distribuzione e un ciclo di
release, e il ruolo che §6 dà all'iPhone è notifiche, approvazioni, voce, stato dei task,
informazioni rapide — cose che un Shortcut sa fare oggi.

*Che cosa ne discende, e vincola la Fase 12:* la metà iPhone del protocollo dei nodi **deve essere
esprimibile in uno Shortcut** — una richiesta HTTP con un header e una risposta JSON — e in una
notifica push. Qualunque trasporto che chieda al nodo di tenere aperta una connessione, di
presentare un certificato client o di far girare un processo suo taglia fuori l'iPhone.

### 5.2 La rete è Tailscale

I nodi si vedono sulla **tailnet**, non su Internet e non su LAN: nessuna porta aperta, nessun
reverse proxy, indirizzi stabili, e l'identità di macchina che Tailscale già dà.

*Che cosa ne discende:* la frase di ADR 0023 §7 — il token statico «va bene per un sistema a utente
singolo su loopback» — **scade il giorno in cui l'API smette di essere solo loopback**, e quel
giorno è la Fase 12. Non è un motivo per fidarsi della rete: è un motivo per non doverne aprire una
seconda.

### 5.3 La voce è ElevenLabs, con `eleven_flash_v2_5`

*Perché quel modello:* misurato il 2026-09-08 (ADR 0034, `providers/elevenlabs/settings.py`), al
tetto dei 600 caratteri `eleven_multilingual_v2` lascia **5,6 secondi di silenzio** prima della
prima sillaba e costa **1 credito per carattere**; `eleven_flash_v2_5` ne lascia **1,24** e costa
**0,5**. La scelta è il costo dei crediti, e la qualità che si perde è stata ascoltata.

### 5.4 La ritenzione di ElevenLabs è accettata

ADR 0034 §1.2 l'ha **verificata invece che citata**: il testo che ELA dice è conservato e
rileggibile nella dashboard dell'utente, `enable_logging=false` risponde `200` e non cambia niente,
e lo Zero Retention Mode è riservato agli enterprise. **L'utente lo accetta**, sapendolo.

*Che cosa ne discende:* niente da riparare, e una cosa da non dimenticare — il risultato porta la
**ricevuta** (l'id della copia che loro hanno tenuto e i crediti dichiarati, mai una parola del
testo), e quella ricevuta esiste perché questa decisione è consapevole e non ignorata.

### 5.5 Lo sviluppo è in locale, sul Mac

Nessun deploy, nessun server remoto, nessun container: ELA gira dal repository, `ela serve` su
loopback, il database è un file SQLite su questa macchina. Anche quando i nodi saranno tre, **il
Core resta qui**.

### 5.6 La wake word è rimandata a M15.1

ELA non si sveglia a una parola: oggi il microfono si apre per un numero dichiarato di secondi,
dietro una decisione del Guardian, e si chiude.

*Perché è un rinvio e non una dimenticanza:* una wake word vuole un microfono **aperto in
permanenza in attesa di una parola**, e quello non è nessuno dei tre stati che §11 dichiara —
`OFF`, `AVAILABLE`, `ACTIVE`. Sarebbe **il quarto stato del microfono**, e §11 è la spec: allargare
quell'enum è una decisione che si prende con la milestone che la usa, non prima. Va con la Fase 15
perché «ELA decide da sola di ascoltare» è §34, non §11.

### 5.7 Chi paga il lavoro agentico

Dalla **Fase 14** il lavoro agentico — coding, ricerca — **non lo fa ELA chiamando il modello**: lo fa
una sessione di Claude Code che ELA lancia come programma.

*Perché è accettabile:* per tre cose, e valgono solo insieme.

- **La sessione si lancia come processo, mai guidandola a mouse e tastiera.** Da programma il
  risultato è un dato leggibile — l'esito, il costo dichiarato, il diff —; a tastiera sarebbe pixel
  da interpretare. E a tastiera ELA risponderebbe da sé alle richieste di permesso della sessione:
  prenderebbe l'approvazione dell'utente senza che nessuno la registri.
- **Il Guardian è l'host dei permessi della sessione.** Ogni azione che la sessione vuole compiere
  passa dallo stesso punto di decisione di ogni altro effetto di ELA, e lascia la sua riga
  nell'audit.
- **Ciò che si approva è il diff, non la sessione.** La sessione gira in un worktree suo, e il suo
  effetto è ispezionabile.

### 5.8 Come si paga una sessione

Il modo di pagamento **non è una variabile di configurazione: deriva dalla cartella su cui la
sessione lavora.** La cartella dell'utente, con la sua configurazione invariata, va in modalità con
abbonamento. Una cartella arrivata da fuori, o una configurazione cambiata rispetto a quella
approvata, va in modalità pulita, con la chiave API.

*Perché:* nella modalità con abbonamento la sessione carica gli hook, i server MCP e il `CLAUDE.md`
della cartella in cui lavora **anche se nessuno l'ha dichiarata fidata**, quindi la protezione è
sapere di chi è la cartella. Una riga di `.env` che dicesse «usa l'abbonamento» sarebbe una difesa
che si spegne cambiando una riga.

*Che cosa ne discende:* prima di lanciare, ELA rileva la configurazione della cartella e la
confronta con quella approvata; **se è cambiata, chiede di nuovo**. E la ricevuta vale in tutti e
due i modi: la sessione dichiara comunque il costo, quindi l'audit registra la spesa anche quando
non è a consumo.

### 5.9 Il tetto di spesa

Il budget dell'utente sulla chiave API è **non più di ~50 EUR al mese**, più gli abbonamenti già in
essere.

Oggi **nessuno lo fa rispettare**. Fra i vincoli dichiarati di ADR 0021 c'è «**Nessun budget** (§3):
l'usage si registra, non si somma e non si confronta con un tetto», e ADR 0022 lo ripete invariato.
Quei due ADR hanno messo il tetto sotto §30 — che nella spec è «Pagamenti» —, e §30 non ha ancora né
un ADR né una milestone.

*Che cosa ne discende:* finché §30 non esiste, **il tetto lo mette il fornitore**: una workspace
dedicata sulla console, con la sua chiave, un limite mensile e l'auto-reload spento. E **§30 prende
la sua milestone prima della Fase 14, non dopo**.

*Perché nessun ADR, per nessuna di queste tre voci:* ADR 0021 e ADR 0022 sono immutabili e dicono il
vero, e non si toccano. Li rivedranno apertamente §30 e la capability della Fase 14, quando
esisteranno, ciascuno con il proprio ADR.

### 5.10 Il design è una fase, non una rifinitura

La **Fase 17 si chiama Design**, e la sua fonte di verità è
[`spec/ELA_design.md`](spec/ELA_design.md), «ELA — Design System & Command Center», accanto a
`ELA_spec.md`, che una sezione di design visivo non ce l'ha. Le due numerazioni si sovrappongono —
§6 della spec è l'iPhone, §6 del design sono gli stati di ELA —, quindi qui una sezione del design
si scrive sempre «§N del design», e un «§N» da solo resta la spec.

- **M17.1 — Design System.** Le voci 3, 4, 5, 6, 7, 8, 18 e 19 di §34 del design — typography,
  colori, token, componenti, motion, stati d'interazione, comportamento responsive, regole di
  accessibilità — e **l'identità visiva minima che servono** (§22 del design). E la voce 20, il
  prototipo, in una forma sola: **una pagina-campionario** che rende token, componenti e stati
  d'interazione, servita sulla tailnet e aperta in Safari. È ciò che l'utente prova a mano, e non è
  uno stub: è il riferimento che M12.5 e M17.2 usano. La voce 17, il companion iPhone, la fa
  **M12.5**, con l'identità di M17.1.
- **M17.2 — Command Center v1.** Un **client dell'API come la CLI** (ADR 0024 §2), in
  `apps/command-center/`. Gli stati di §6 del design sono **derivati da ciò che l'API espone, mai
  memorizzati**. Da quel momento vale una regola fissa: **ogni milestone che aggiunge una capacità
  aggiunge la sua vista.**
- **M17.3 — Presenza desktop** (§19 del design), alla fine, dopo le altre fasi.
- **Com'è ELA sullo schermo** — deciso dall'utente il 2026-09-18, guardando la pagina-campionario
  di M17.1, con le sue parole: «ELA deve sembrare una sfera, azzurra e bianca; una dashboard
  futuristica stile JARVIS ma senza informazioni inutili; ELA deve apparire sul mio schermo come un
  widget».

L'ordine è **M17.1 → M12.5 → M17.2 → Fase 13**, e M17.3 dopo tutte. Il numero di una fase non dice
quando si fa: M17.1 viene prima dell'ultima milestone della Fase 12.

*Perché è una fase:* è il design stesso a chiederlo. §33 del design vieta di saltare da «ELA deve
essere futuristica» a «scrivi il codice della dashboard», §22 del design vuole l'identità progettata
prima della UI definitiva, e §34 del design fa cominciare l'implementazione completa della UI solo
dopo i suoi deliverable. Una rifinitura arriva dopo il codice e si adatta a ciò che trova; una fase
ha le sue milestone, e ciò che viene dopo le eredita.

*Perché M17.1 prima di M12.5:* §20 del design dice che l'iPhone usa la stessa identità visiva, e il
companion è la prima superficie di ELA che non è un terminale. Fatto prima del design system,
nascerebbe senza identità e andrebbe rifatto.

*Perché M17.2 dopo la Fase 12 e prima della Fase 13:* ciò che il Command Center mostra per primo
sono i nodi (§11 del design e §12 del design), e prima che la Fase 12 li abbia tutti una vista di un
nodo che non esiste ancora è uno stub, non un debito. E le prime capability HIGH della Fase 13
vogliono l'Approval Center di §14 del design e §29 del design già in piedi, perché un'approvazione
HIGH data da un terminale non nomina ciò che conta.

*Perché il Command Center è un client:* per la ragione della CLI. `ela.api` è l'unica porta da cui
un «sì» dell'utente entra nel sistema e l'unica che controlla il token; un'approvazione data dal
Command Center passa da lì, come una data con `ela task approve`, e un Command Center che leggesse
il database sarebbe un secondo ELA.

*Perché gli stati sono derivati:* uno stato memorizzato è una seconda copia di ciò che il task,
l'approvazione e il nodo già dicono, e si disallinea alla prima scrittura mancata — la ragione per
cui lo stato di uno step è la piega della sua trail (ADR 0009 §2) e la disponibilità di un nodo è
derivata dall'heartbeat (ADR 0016 §3). E un enum del dominio con gli stati di §6 del design
porterebbe `EVOLVING` e `UPDATING` prima che qualcosa in ELA sappia evolvere o aggiornarsi: valori
che nessun percorso di produzione può produrre, cioè gli stub «per dopo» che `CLAUDE.md` vieta.

*Perché la regola della vista:* perché il Command Center non diventi un debito che cresce a ogni
milestone. È la forma del gate della copertura: un package entra nel gate nella milestone che gli dà
codice, non dopo; una vista entra nella milestone che dà la capacità.

*Perché M17.3 per ultima:* il livello «Expanded» di §19 del design **è** il Command Center, quindi
la presenza desktop viene dopo M17.2. E dopo le altre fasi per due ragioni: il livello Ambient non ha
niente da mostrare finché ELA non decide da sola di dire qualcosa — §18 del design, che è la
Fase 15 —, e una presenza che resta sullo schermo vuole il processo residente che è murato finché
ELA non ha un eseguibile firmato suo (ADR 0029 §16, ADR 0039 §6).

*Che cosa il design eredita, e non può contraddire:*

- **Niente app iPhone nativa** (la 5.1, qui sopra). Il companion di §20 del design, e la voce 17
  di §34 del design, si disegnano per ciò che la 5.1 lascia all'iPhone: Shortcuts, notifiche push,
  Safari sulla rete privata.
- **Gli stati di §6 del design non sono un enum del dominio: sono una proiezione.** `domain.py` non
  riceve un valore per ciascuno; si calcolano da ciò che l'API espone.
- **§10 del design non mostra mai il chain-of-thought.** L'execution summary si compone di ciò che
  il sistema registra — l'obiettivo, il piano, lo step corrente, il nodo, il modello scelto —, mai
  del ragionamento di un modello.

*Perché nessun ADR:* sono scelte di prodotto e d'ordine — quale fase, quando, che cosa eredita — e
nessuna riga di codice le contiene ancora. Le parti tecniche prendono il loro ADR con la milestone
che le costruisce: la cartella, lo stack e il calcolo della proiezione con M17.2, come la cartella
della CLI l'ha preso con M8.2 (ADR 0024 §1).

## 6. I debiti datati

Un debito datato è un difetto **trovato lavorando e non riparato lì**, scritto in un ADR con la
data, con chi lo paga, e con la difesa più piccola possibile: un test che si accorge del pagamento.
Il criterio è di ADR 0025 §1; la forma è di ADR 0035 §7, che è anche il primo ad essere stato
pagato da chi doveva.

<!-- generato da scripts/generate_stato.py: i debiti datati -->

| Debito | Dichiarato | A carico | Stato |
|---|---|---|---|
| ADR 0041 §5 — i test che aspettano, e le difese che costano un terzo della suite | 2026-09-18 | della milestone sulla disciplina della suite | **aperto** |
| ADR 0035 §7 — i numeri in coda a `CONSTANTS` non contano più niente | 2026-09-09 | della milestone sulla disciplina della suite | saldato da ADR 0036 §10 |
| ADR 0036 §12 — `PROVIDER_CALLED` non lo scrive nessuno | 2026-09-10 | di chi aggiungerà il prossimo `AuditEventType` | saldato da ADR 0037 §14 |

<!-- fine del blocco generato: i debiti datati -->

## 7. Come si riparte

1. **Leggi `CLAUDE.md`** alla radice: è il contratto di lavoro (una milestone alla volta,
   architettura non negoziabile, gate di qualità).
2. **Leggi le sezioni della spec** che riguardano la milestone, e gli ADR che la continuano —
   [`adr/README.md`](adr/README.md) è l'indice, e non può diventare stantio.
3. **Scrivi la SPEC** della milestone in `docs/milestones/<id>.md`, con che cosa entra, che cosa
   **non** entra, i criteri di accettazione e i test previsti. **Fermati e mostrala** prima di
   implementare.
4. **Fai girare la suite**: durante il lavoro, i test del pezzo che tocchi; `make check` in primo
   piano, una volta sola, alla fine della milestone — sorvegliarlo costa più del lavoro che
   sorveglia. Il controllo Linux è la CI sul branch, che il merge vuole verde su entrambi i runner;
   `make check-linux` serve a riprodurre qui una CI rossa su ubuntu, fingendo l'altra metà della
   matrice (i suoi limiti sono scritti in `tests/foreign_machine.py`).
5. **Fai partire ELA**: [`GETTING_STARTED.md`](GETTING_STARTED.md), comando per comando.
6. **Quando aggiungi una milestone, un ADR, una regola o una capability, rigenera questo file.**
   `make check` te lo ricorda fallendo.
