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
