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
  esterna. `make check` in primo piano, una volta; `make check-linux` prima di ogni push.

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
| 12 — *senza nome* | `M12.1` | Proposta | L'identità: provare chi si è, e poter smettere di esserlo |
| 12 — *senza nome* | `M12.2` | Proposta | L'assegnazione e il protocollo del lavoro: la chiamata al tool fatta da lontano, e il tempo che decide per chi tace |

<!-- fine del blocco generato: le milestone -->

## 3. I numeri

Nessuno di questi è scritto a mano, ed è il motivo per cui vale la pena leggerli: sono la
dimensione del sistema oggi, non la dimensione che aveva quando qualcuno l'ha annotata.

<!-- generato da scripts/generate_stato.py: i numeri -->

| Che cosa | Quanti | Contati leggendo |
|---|---|---|
| ADR scritti | **37** | `docs/adr/NNNN-*.md` |
| Milestone | **39, di cui 36 non più `Proposta`** | la riga `- **Stato:**` di ogni documento |
| Regole di architettura | **47** | `RULES` in `tests/architecture/` |
| Contratti import-linter | **14** | `pyproject.toml` |
| Port | **24** | i `Protocol` di `src/ela/ports.py` |
| Capability di produzione | **8** | `production_catalogue()` |
| Rotte dell'API | **20** | i `router` di `ela.api` |
| Comandi della CLI | **22** | l'albero Typer di `ela.cli` |
| Vincoli dichiarati negli ADR | **134** | le sezioni «Vincoli dichiarati» |

<!-- fine del blocco generato: i numeri -->

## 4. Cosa manca

### 4.1 Le fasi

- **Fase 12 — i nodi.** È la fase che comincia adesso: ELA smette di essere un processo su una
  macchina e diventa il sistema distribuito di §56, con un Core e nodi che si annunciano, si
  autenticano, ricevono lavoro e riportano. La prima milestone è il **protocollo**, e tutto il
  resto della fase — il nodo macOS, il Power Node Windows, il companion iPhone — sta su quel
  contratto. È la fase a cui una dozzina di documenti hanno già rimandato qualcosa: `grep -rn
  "Fase 12" docs/` è l'elenco di ciò che va onorato.
- **Fase 15 — la memoria e la proattività.** §21 (Memory Core) e §34 (Proactive Core), rimandate
  da ADR 0023, ADR 0025, ADR 0036 e da tre milestone: il richiamo periodico di `recover()`, il
  momento in cui ELA decide di parlare da sola, e il trascritto che oggi non sopravvive al task
  perché un trascritto è memoria e la memoria è lì.
- **Le altre fasi non hanno un contenuto scritto.** Il blocco qui sotto elenca le fasi **oltre
  l'ultima che ha una milestone** che un documento del repository nomina, e ciò che non compare non
  è dimenticato: è **non ancora deciso**, e il posto dove deciderlo è una SPEC di milestone, non
  questo file. La Fase 12 è uscita da quell'elenco nel momento in cui ha avuto la sua prima
  milestone — che è il modo in cui una lista derivata dice che una fase ha smesso di essere futura.

<!-- generato da scripts/generate_stato.py: le fasi che un documento nomina -->

| Fase | Documenti che la nominano |
|---|---|
| 15 | 8 |

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

## 6. I debiti datati

Un debito datato è un difetto **trovato lavorando e non riparato lì**, scritto in un ADR con la
data, con chi lo paga, e con la difesa più piccola possibile: un test che si accorge del pagamento.
Il criterio è di ADR 0025 §1; la forma è di ADR 0035 §7, che è anche il primo ad essere stato
pagato da chi doveva.

<!-- generato da scripts/generate_stato.py: i debiti datati -->

| Debito | Dichiarato | A carico | Stato |
|---|---|---|---|
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
4. **Fai girare la suite**: `make check` in primo piano, una volta sola — dura qualche minuto e
   sorvegliarlo costa più del lavoro che sorveglia. Prima di ogni push, `make check-linux`, che
   rifà suite e gate della copertura fingendo l'altra metà della matrice (i suoi limiti sono
   scritti in `tests/foreign_machine.py`).
5. **Fai partire ELA**: [`GETTING_STARTED.md`](GETTING_STARTED.md), comando per comando.
6. **Quando aggiungi una milestone, un ADR, una regola o una capability, rigenera questo file.**
   `make check` te lo ricorda fallendo.
