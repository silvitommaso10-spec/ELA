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
- **Dopo il tag, e fuori da qualunque release**, ELA ha guadagnato quattro cose: la **percezione**
  (Fase 10 — fotografa lo schermo, ne legge il testo sulla macchina, sa quali applicazioni l'utente
  sta usando, e compone il contesto di §44 dicendo quali fonti le mancano), la **voce** (Fase 11 —
  parla con `say` di macOS e con ElevenLabs, e ascolta il microfono restituendo un trascritto e non
  l'audio), i **nodi sulla rete** (Fase 12) e un **aspetto** (Fase 17). Quali milestone e in che
  stato è la tabella della §2; che cosa ciascuna ha portato è il [changelog](CHANGELOG.md). Non si
  riscrive qui: sarebbe una terza copia da tenere allineata.
- **ELA non gira più su una macchina sola** — la Fase 12 si è chiusa il 2026-09-20. Il Mac resta il
  **Core**, e ci resta per scelta (5.5); è anche un nodo, `local`, la cui riga la scrive il processo
  stesso all'avvio con un id deterministico *perché è questa macchina*. Accanto a lui un nodo
  remoto **può** esistere e **si autentica** con un segreto suo (M12.1), prende le chiamate del
  Core e le riporta (M12.2), e ne esistono due implementazioni vere — questo Mac come nodo (M12.3)
  e un **PC Windows** sulla tailnet (M12.4) —, più il **companion iPhone**, che nodo non è: guarda,
  risponde e non prende lavoro (M12.5). Il Device Orchestrator non sceglie più fra un candidato
  solo per costruzione: sceglie fra quelli che il registro ha, con i filtri e i punteggi di
  ADR 0017.
- **Il ciclo di lavoro** è quello di `CLAUDE.md`: una milestone alla volta, SPEC → IMPLEMENTATION →
  TEST → REVIEW → COMMIT, su un branch di lavoro; il merge su `main` lo fa l'utente dopo revisione
  esterna. `make check` in primo piano, una volta, alla fine della milestone, letto intero. Il
  controllo Linux è la CI sul branch, verde su entrambi i runner di `make check` prima del merge —
  e da M12.4 la CI ha anche un **terzo** job, la suite del nodo su `windows-latest`.

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
| 9 — Le liste che si accorgono di essere false | `M9.5` | Proposta | La disciplina della suite: gli skip che si accorgono di essere saltati, e i test che aspettano un evento |
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
| 12 — I nodi sulla rete | `M12.5` | Implementata | Il companion iPhone: vedere e rispondere da lontano, e un campanello che non porta lettere |
| 13 — Il permesso prima dell'azione | `M13.1` | Implementata | Il filesystem fuori dalla workspace, e il primo HIGH |
| 13 — Il permesso prima dell'azione | `M13.1b` | Implementata | Il grant di un sì si consuma: la riga `HIGH` e le promesse di M13.1 che l'albero non manteneva |
| 13 — Il permesso prima dell'azione | `M13.2` | Implementata | Il terminale: un comando è `argv`, e i programmi ammessi stanno nello scope |
| 13 — Il permesso prima dell'azione | `M13.3` | Proposta | L'azione che viaggia: il verifier dove avviene l'effetto, e i tre debiti che la fase paga qui |
| 13 — Il permesso prima dell'azione | `M13.4` | Proposta | Il browser: Playwright, e il costo che la SPEC misura prima di decidere |
| 13 — Il permesso prima dell'azione | `M13.5` | Proposta | Computer control: il muro dichiarato prima di cominciare |
| 13 — Il permesso prima dell'azione | `M13.6` | Proposta | Spostare un lavoro già in corso: il ripiazzamento, quando due capability sanno dichiararsi ripetibili |
| 17 — Design | `M17.1` | Implementata | Il Design System: l'identità minima, e le regole che ogni superficie di ELA eredita |
| 17 — Design | `M17.2` | Implementata | Il Command Center v1: un client dell'API, quattro viste, e la terza identità del registro |
| 17 — Design | `M17.2b` | Proposta | Un esito finale sparisce dalle superfici che elencano i task |
| 17 — Design | `M17.3` | Proposta | La presenza desktop: ELA sullo schermo senza la dashboard aperta |
| 17 — Design | `M17.4` | Proposta | Il passaggio di design del Command Center: le viste tutte insieme, quando guardarle non basta più |
| 17 — Design | `M17.5` | Proposta | Il Task Center: ogni task, vivo o finito, in una vista sua |

<!-- fine del blocco generato: le milestone -->

## 3. I numeri

Nessuno di questi è scritto a mano, ed è il motivo per cui vale la pena leggerli: sono la
dimensione del sistema oggi, non la dimensione che aveva quando qualcuno l'ha annotata.

<!-- generato da scripts/generate_stato.py: i numeri -->

| Che cosa | Quanti | Contati leggendo |
|---|---|---|
| ADR scritti | **47** | `docs/adr/NNNN-*.md` |
| Milestone | **59, di cui 49 non più `Proposta`** | la riga `- **Stato:**` di ogni documento |
| Regole di architettura | **57** | `RULES` in `tests/architecture/` |
| Contratti import-linter | **14** | `pyproject.toml` |
| Port | **27** | i `Protocol` di `src/ela/ports.py` |
| Capability di produzione | **11** | `production_catalogue()` |
| Rotte dell'API | **48** | i `router` di `ela.api` |
| Comandi della CLI | **25** | l'albero Typer di `ela.cli` |
| Vincoli dichiarati negli ADR | **200** | le sezioni «Vincoli dichiarati» |

<!-- fine del blocco generato: i numeri -->

## 4. Cosa manca

### 4.1 Le fasi

Qui c'è che cosa è **fatto** e che cosa è **aperto**. **Qual è la prossima milestone non sta qui**:
è una decisione d'ordine, e sta nella §5, nella voce della fase che la contiene, in un posto solo.
Una frase che va rincorsa a ogni merge è una lista scritta a mano, e questa è invecchiata due volte
in tre giorni.

**Una registrazione non è un inizio**, ed è lo stesso criterio che vale per il blocco generato in
fondo alla sezione e per il nome che il changelog dà a una fase: **una fase comincia quando una sua
milestone esce da `Proposta`**, non quando qualcuno ne scrive i documenti. Una fase registrata e
non ancora cominciata ha la sua voce qui **e** resta nel blocco delle fasi future: sono due letture
dello stesso fatto, e nessuna delle due va aggirata.

**La regola della prima voce**: quando una fase si chiude, la sua voce resta qui — la prima —
finché la prossima non **comincia**; è il posto dove si legge da dove si riparte, e una fase che
sparisce il giorno in cui finisce lascia il lettore senza il filo.

**Che cosa qui nessun test tiene.** I due criteri qui sopra li tiene `tests/docs/test_stato.py`
**nella forma dei fatti, non delle parole**: che una fase abbia un nome esattamente quando una sua
milestone è uscita da `Proposta` è un mondo chiuso con il suo caso negativo. **Ha suonato il
2026-09-21**, il giorno in cui M13.1 è uscita da `Proposta`, e ha detto che cosa riscrivere qui —
che è tutto ciò che un appunto del genere deve fare. Ciò che nessun test tiene è **il verbo di
questa prosa**: se qui si scrive «è cominciata» dove i blocchi derivati
dicono «registrata», nessuna misura se ne accorge — l'unico controllo possibile sarebbe un
confronto di stringhe, che la riscrittura successiva aggira, e una prova che non può fallire non è
una prova. È successo il 2026-09-21, ed è il motivo per cui questa riga esiste.

- **Fase 13 — il permesso prima dell'azione. È cominciata il 2026-09-21**, con M13.1, ed è la
  prima voce perché è la fase in corso. ELA ha smesso di agire solo dentro la sua workspace: legge
  e scrive file in una cartella che l'utente dichiara — `ELA_FS_ROOT` e `ELA_FS_SCOPE`, due righe
  senza default, perché un confine che ELA sceglie per te è un confine che non ha deciso nessuno —
  e il livello **`HIGH` esiste davvero**: non è più un diniego, è un'approvazione per ogni uso che
  nessuna policy permanente di §59 raggiunge. Con **M13.2** esegue anche i programmi che l'utente
  dichiara — `ELA_TERMINAL_PROGRAMS`, relativi a `/`, `[]` ammessa —: un comando è `argv`, il figlio
  riceve un ambiente chiuso e nasce in un gruppo suo, e la domanda nomina ciò che girerà. Restano
  aperte **M13.3** (l'azione che viaggia, e tre debiti), **M13.4** (il browser), **M13.5** (il
  computer control) e **M13.6** (il ripiazzamento, fuori dalla fila): l'ordine e le condizioni
  stanno nella voce 5.11.
- **Fase 12 — i nodi. È chiusa** (2026-09-20, con M12.5). ELA ha smesso di essere un processo su
  una macchina e di essere usabile solo davanti a quella macchina: un'identità provabile per un
  nodo, il protocollo del lavoro con la sua suite di conformità, **due implementazioni vere** —
  questo Mac e un PC Windows — e il companion iPhone, che nodo non è. Che cosa ha portato,
  milestone per milestone, è il [changelog](CHANGELOG.md); il censimento di ciò che ha onorato, di
  ciò che non le si applicava e di ciò che si è spostato con una casa nuova è in ADR 0043 §9.
  ***Ha smesso di essere la prima voce il 2026-09-21***, quando la 13 è cominciata: la regola della
  prima voce ha fatto esattamente ciò per cui esiste, tenere il filo fino al giorno dopo.
- **Fase 17 — il design.** Registrata il 2026-09-18: la fonte di verità è
  [`spec/ELA_design.md`](spec/ELA_design.md), e le decisioni sono nella 5.10. **M17.1, il Design
  System, è fatta** (2026-09-19, ADR 0042): ELA ha un aspetto — una sfera di luce nel vetro, azzurra
  e bianca, «stile Apple, futuristico stile JARVIS» — e `apps/design-system/` è ciò che ogni
  superficie eredita — e M12.5 è la prima che l'ha ereditata davvero, sull'iPhone (§20 del design).
  **Anche M17.2, il Command Center v1, è fatta** (2026-09-20, ADR 0044): l'utente apre un browser
  sul Mac e vede ELA — quattro viste che mostrano solo ciò che sta già in una rotta, una terza
  identità del registro, un tetto derivato dalla coppia degli indirizzi del socket —, e da lì vale
  la regola che ogni milestone che aggiunge una capacità aggiunge la sua vista. **Restano aperte**
  M17.4, il passaggio di design del Command Center, M17.3, la presenza desktop, e — registrate il
  2026-09-24 — M17.2b, la riparazione di un esito che sparisce, e M17.5, il Task Center: quando si
  fanno lo dice la 5.10.
- **Fase 15 — la memoria e la proattività.** §21 (Memory Core) e §34 (Proactive Core), rimandate
  da ADR 0023, ADR 0025, ADR 0036 e da tre milestone: il richiamo periodico di `recover()`, il
  momento in cui ELA decide di parlare da sola, e il trascritto che oggi non sopravvive al task
  perché un trascritto è memoria e la memoria è lì.
- **Le fasi che restano non hanno ancora consegnato niente.** Il blocco qui sotto elenca le fasi
  che un documento del repository nomina e che **nessuna milestone ha ancora cominciato** — nessuna
  delle loro è uscita da `Proposta` —, e ciò che non compare non è dimenticato: è **non ancora
  deciso**, e il posto dove deciderlo è una SPEC di milestone, non questo file. La Fase 12 è uscita
  da quell'elenco quando la sua prima milestone è uscita da `Proposta` — che è il modo in cui una
  lista derivata dice che una fase ha smesso di essere futura, ed è lo stesso fatto con cui il
  changelog le dà un nome. **Avere una registrazione non è avere cominciato**: la 13 ci sta dentro
  pur avendo sei documenti, e il numero non conta — la 17 c'è rimasta finché M17.1 non è uscita da
  `Proposta`, anche se è cominciata prima della 13.

<!-- generato da scripts/generate_stato.py: le fasi che un documento nomina -->

| Fase | Documenti che la nominano |
|---|---|
| 15 | 14 |
| 16 | 1 |

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
| §38 | Evolution Dashboard |
| §40 | Creatività |
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

*Come è finita, il 2026-09-20 (M12.5, ADR 0043):* la decisione regge, e il vincolo è stato onorato
in un modo che il 2026-09-07 non era ovvio. La frase resta vera **delle rotte dei nodi**, che la
suite di M12.2 prova proprio in quella forma. Il companion però **non le usa**: parla dal browser
del telefono, con un **cookie** invece di un header, e le pagine gliele serve `ela.api`. Nessuno dei
tre trasporti esclusi qui gli serve — niente connessione tenuta aperta, niente certificato client,
nessun processo suo sull'iPhone —, e la notifica push è quella di §6 (ntfy, con il tocco che apre la
pagina). Uno Shortcut c'è, e non tiene segreti: apre un indirizzo. Se un giorno uno Shortcut
**parlerà** a ELA presentando una credenziale, sarà la milestone che darà voce all'iPhone a dire
dove la tiene, con la sua misura.

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
  uno stub: è il riferimento che M12.5 ha usato e che M17.2 userà. La voce 17, il companion iPhone,
  **l'ha fatta M12.5** il 2026-09-20, con l'identità di M17.1: le pagine del telefono usano i
  `tokens.css` e i `components.css` della cartella, e la sfera la **includono** invece di
  ricopiarla.
- **M17.2 — Command Center v1.** Un **client dell'API come la CLI** (ADR 0024 §2), in
  `apps/command-center/`. Gli stati di §6 del design sono **derivati da ciò che l'API espone, mai
  memorizzati**. Da quel momento vale una regola fissa: **ogni milestone che aggiunge una capacità
  aggiunge la sua vista.**
- **La forma del client web l'ha decisa M12.5, con ADR 0043, e M17.2 la eredita** (deciso il
  2026-09-19, fatto il 2026-09-20). Le pagine le **compone `ela.api`**, dietro lo stesso middleware
  e leggendo le sue stesse rotte, e **il browser è il client**: non c'è un secondo processo che
  tenga e inoltri la credenziale del telefono, che sarebbe il reverse proxy che la 5.2 esclude con
  un altro nome. L'identità di un browser viaggia in un **cookie**, perché un browser non può
  mandare un header. **Niente JavaScript nostro**, e una `Content-Security-Policy` che lo vieta
  comunque, composta nell'unico posto dove nasce una pagina. I modelli stanno in
  `apps/<superficie>/`, con le loro regole nei test della cartella.

  *Ciò che tiene vera la frase «client dell'API come la CLI» è una regola, non una promessa*: la
  **regola 55** — *le pagine leggono le rotte* — dice che `api/companion.py` chiama le funzioni
  delle rotte e non raggiunge mai un port, uno store, il catalogo o l'executor attraverso `Ela`, e
  ha il suo caso negativo. Ne discende la disciplina che M17.2 eredita: **ciò che una vista mostra
  deve già stare in una rotta**, e se non ci sta è la rotta che cresce — è così che `ApprovalOut`
  ha guadagnato i pezzi della domanda invece di lasciare alla pagina una seconda copia.

  **M17.2 le ha decise, il 2026-09-20** (ADR 0044). Le **viste** sono quattro — la home con la
  presenza, l'Approval Center, il Device Center e un task come execution summary — e ognuna mostra
  solo ciò che sta già in una rotta: nessuna rotta è cresciuta per servirle. L'**identità del
  browser del Mac** è un terzo ruolo, `CONSOLE`, coniato dall'utente come il companion, con il suo
  cookie `ela_console` e il suo prefisso `/console`: non si riusa il cookie del telefono, perché
  `COMPANION` è una restrizione e una console che cresce a ogni milestone la renderebbe finta. Il
  **tema** resta scuro sempre, e il perché è scritto: i token del tema chiaro sono emessi solo
  sotto `[data-theme="light"]`, quindi la media query va derivata dal generatore di M17.1 e non
  scritta in una superficie. Gli **stati** restano i tre del companion — l'estensione è vuota, e i
  dieci perché no sono scritti uno per uno con la loro fonte.

  Due cose che M17.2 ha aggiunto e che la registrazione non prevedeva. Il **tetto di ciò che la
  console vede si deriva dalla coppia degli indirizzi del socket**: `LOCAL_ONLY` quando peer e
  sockname sono di loopback, altrimenti il livello imposto all'arruolamento — perché un livello
  inciso nel registro non sa dove sia il browser, e il socket sì; e la pagina dice quale tetto è in
  vigore **nei due versi**. E la regola «ogni milestone aggiunge la sua vista» è diventata
  **un'impronta generata** delle capability di `production_catalogue()`, riconfrontata a ogni
  `make check`: una capability nuova ferma la suite, e la risposta si scrive nel documento della
  milestone che l'ha fatta fermare.

- **M17.4 — Il passaggio di design del Command Center** (registrata il 2026-09-21, alla fine di
  M17.2). M17.2 ha costruito il Command Center perché ELA si potesse **guardare**; il passaggio di
  §23 del design e §24 del design — ritmo, gerarchia, movimento, l'interfaccia che cambia con ciò
  che sta succedendo (§27 del design) — si fa su **tutte** le viste insieme, e le viste non ci sono
  ancora tutte. **Condizione d'ingresso**, la prima che arriva: dopo la Fase 16, oppure quando il
  Command Center smette di bastare a guardarlo — quando per capire che cosa succede si apre il
  terminale invece della pagina. **Costo dichiarato:** le viste che le milestone aggiungeranno da
  qui in poi nascono con l'aspetto di M17.2, e M17.4 le ritroverà tutte insieme; è il prezzo di
  aver messo il Command Center prima della Fase 13 invece che dopo la Fase 16, ed è voluto.
  **Nessuna riparazione estetica nel frattempo**: una vista si ripara quando *mente* — un'assenza
  che non si nomina, una vista che non si raggiunge —, non quando è spoglia, e le due riparazioni
  che la prova a mano di M17.2 ha chiesto sono di quella specie.
- **M17.2b — Un esito finale sparisce dalle superfici che elencano i task** (registrata il
  2026-09-24, dalla prova a mano di M13.2). Un task finito sparisce dalla home del Command Center e
  da quella del telefono: l'esito che l'utente aspettava è quello che la vista smette di mostrare. È
  la decisione 22 di M17.2 che funziona come scritta, e il suo prezzo; ed è una vista che **mente**,
  quindi si ripara prima di M17.4, per la regola della voce qui sopra. Il suo confine è M17.5.
- **M17.5 — Il Task Center** (§9 del design; registrata il 2026-09-24, con M17.2b). M17.2 l'aveva
  messo fuori scope come «una vista sua», e nessuna milestone lo prendeva.
- **M17.3 — Presenza desktop** (§19 del design), alla fine, dopo le altre fasi.
- **Com'è ELA sullo schermo** — deciso dall'utente il 2026-09-18, guardando la pagina-campionario
  di M17.1, con le sue parole: «ELA deve sembrare una sfera, azzurra e bianca; una dashboard
  futuristica stile JARVIS ma senza informazioni inutili; ELA deve apparire sul mio schermo come un
  widget».

**L'ordine, e qual è la prossima: qui l'ordine delle milestone della Fase 17 e ciò che le viene
dopo; l'ordine dentro un'altra fase sta nella voce di quella fase.** Ciò che non sta in nessuna
delle due è §4.1, che dice che cosa è fatto e che cosa è aperto e non che cosa viene dopo: una
frase sulla «prossima milestone» scritta lì va rincorsa a ogni merge, ed è invecchiata due volte in
tre giorni.

L'ordine è **M17.1 → M12.5 → M17.2 → Fase 13**, con M17.4 dopo la Fase 16 (o prima, se la sua
condizione scatta) e M17.3 dopo tutte. Il numero di una fase non dice
quando si fa: M17.1 è venuta prima dell'ultima milestone della Fase 12. **Le tre sono fatte** —
M17.1 il 2026-09-19, M12.5 e M17.2 il 2026-09-20 —, e **ciò che viene dopo è la Fase 13**: la sua
prima milestone è M13.1, e l'ordine dentro la fase sta nella 5.11. **M17.2b viene dopo M13.3**, in
una sessione di design insieme alle altre riparazioni della stessa pagina, ciascuna con il suo
documento e la sua lettera, su un branch solo. **L'ordine di M17.5 non è deciso.**

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
nodo che non esiste ancora è uno stub, non un debito. **La condizione è soddisfatta dal
2026-09-20**: i nodi ci sono tutti — il Mac, il PC, e il telefono che nodo non è — e il Device
Center ha righe vere da mostrare, companion compreso, con la disponibilità derivata e l'ultimo
contatto come due fatti separati. E le prime capability HIGH della Fase 13
vogliono l'Approval Center di §14 del design e §29 del design già in piedi, perché un'approvazione
HIGH data da un terminale non nomina ciò che conta.

*Perché il Command Center è un client:* per la ragione della CLI. `ela.api` è l'unica porta da cui
un «sì» dell'utente entra nel sistema e l'unica che controlla l'identità di chi chiama;
un'approvazione data dal Command Center passa da lì, come una data con `ela task approve`, e un
Command Center che leggesse il database sarebbe un secondo ELA. Dal 2026-09-20 non è più soltanto
una ragione: è **la regola 55**, con il suo caso negativo — e «l'unica che controlla il token» si
legge oggi come «l'unica che risolve un'identità», perché un browser porta un cookie e non un
token.

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

### 5.11 Il permesso prima dell'azione: l'ordine della Fase 13

La **Fase 13 è cominciata il 2026-09-21**, con M13.1: registrata lo stesso giorno, è cominciata
quando la sua prima milestone è uscita da `Proposta`, che è il criterio di §4.1. La sua fonte di
verità è [`spec/ELA_spec.md`](spec/ELA_spec.md): §18 (l'Action Core), §19 (il browser), §20 (il
computer control). Porta il momento in cui ELA smette di agire solo dentro la sua workspace — il
filesystem vero, il terminale, il browser, lo schermo — e, perché quel momento sia sorvegliato,
**il livello `HIGH`**: da M13.1 `RISK_POLICY` non lo nega più, lo chiede **a ogni uso**, e nessuna
`Authorization` permanente di §59 lo raggiunge. `fs.write` è la prima capability che lo fa
scattare, e da M13.1b un sì ne copre un uso solo — il grant nato dal sì si spende prima che il tool
agisca, e l'audit lo nomina (ADR 0046).

**Il nome della fase l'ha dato il changelog**, con M13.1: «Il permesso prima dell'azione». La tabella
della §2 e il blocco della §4.1 lo leggono dallo stesso fatto — la prima milestone uscita da
`Proposta` —, e nessuna delle due liste si aggira scrivendo un nome a mano.

**L'ordine è M13.1 → M13.2 → M13.3 → M13.4 → M13.5**, con **M13.6 dopo M13.3, quando la sua
condizione d'ingresso scatta** — nella forma condizionale di M17.4: non una posizione nella fila,
ma un fatto che la apre. E ognuna ha la sua ragione.

- **M13.1 — il filesystem fuori dalla workspace, e il primo `HIGH`. Prima, perché è lei che apre il
  livello.** La riga `HIGH` di `RISK_POLICY` e la prima capability `HIGH` entrano **insieme**, per
  il motivo di ADR 0026 §7: una riga che nessuna capability può far scattare è una difesa che non
  scatta, e una capability `HIGH` senza la riga la nega il Guardian prima di chiedere qualunque
  cosa. `HIGH` smette di essere `DENY` e diventa **un'approvazione per ogni uso, che nessuna
  `Authorization` di §59 può coprire**: §59 è il posto dove le policy dell'utente allargano, e
  `HIGH` è il livello che non raggiungono. Entrano `fs.read` e `fs.write` sotto uno scope dichiarato
  fuori dalla workspace, con **tool e verifier che condividono la classificazione del percorso**,
  come `paths.classify` fa già per le note (ADR 0014 §2), e **la vista dell'approvazione `HIGH` nel
  Command Center**, per la regola della 5.10. **Non entra il viaggio verso un nodo**, e si dichiara
  con un test invece di sottintenderlo (ADR 0038 §14). Ci vuole **un ADR che rivede apertamente**
  la tabella di ADR 0011 §3 e la frase di §29 sulle capability `HIGH` in v0.1. **Il livello di
  `fs.read` lo decide la SPEC**, con lo scope in mano, con il vincolo che il rischio sta nella
  capability e **mai negli argomenti**.
- **M13.2 — il terminale. Seconda, perché vuole la riga che M13.1 apre.** Un comando è **`argv`**,
  non una stringa per la shell: non c'è un interprete in mezzo, quindi non c'è niente da citare e
  nessuna espansione che l'utente non ha scritto. **I programmi ammessi stanno nello scope della
  capability, non nel piano**, per la ragione di ADR 0026 §7: tutto ciò che la policy legge viene
  dal catalogo, e un piano arriva dal client. **L'output troncato dice di essere
  troncato** (ADR 0032 §9-bis). **Implementata il 2026-09-24** (ADR 0047): i programmi sono lo scope,
  relativi a `/`; l'identità di ognuno si fissa all'avvio; il figlio riceve quattro variabili e
  nient'altro e nasce in un gruppo suo, che ELA svuota allo scadere e quando si ferma; l'uscita tiene
  testa e coda con il taglio dichiarato, e nell'audit entrano solo numeri.
- **M13.3 — l'azione che viaggia. Terza, e prima del browser.** Il verifier gira **dove avviene
  l'effetto**, e qui la fase paga **tre** debiti: **ADR 0044 §8**, il battito di `local` — il Mac
  risulta non disponibile mentre ELA gira —; **i pesi di §17**, che ADR 0017 dichiarò «da ritarare
  con dati reali» e che la Fase 12 ha misurato senza ritarare (ADR 0043 §9), e che si ritarano qui,
  quando due nodi competono davvero; e **la deriva dell'orologio di un nodo contro i cinque minuti**
  (M12.2, la stessa casa di ADR 0043 §9), che è la stessa materia — chi misura il tempo, e con quale
  orologio — e che M12.2 ha lasciato non misurata perché la sua suite gira sul `FakeClock` del Core.
  M13.3 guadagna anche **un obbligo esplicito**: **ogni capability che viaggia dichiara se si può
  ripiazzare**, senza default, come `reads_the_machine`. Oggi §15 è onorato da **un tool solo**,
  quello di `core.echo` (ADR 0038 §8), e la cosa è vera implicitamente: questa è la milestone che smette di lasciarla
  implicita, ed è quella dichiarazione a rendere M13.6 possibile o impossibile. Prima del browser
  perché **un'azione che non si può verificare su un nodo non si esegue su quel nodo** (ADR 0014
  §3): la domanda «dove gira il verifier» si risponde prima di aggiungere l'azione che la farà
  pesare.
- **M13.4 — il browser** (§19), con **Playwright**. **Condizione d'ingresso: M13.3 chiusa.** La
  SPEC **misura e scrive prima di decidere**: una dipendenza nuova, i binari dei browser, il tempo
  che aggiunge a `make check` e il tempo che aggiunge alla CI **sui tre runner** della matrice vera
  — `ubuntu-latest`, `macos-latest`, `windows-latest`. Se il conto non regge, la decisione si
  riapre con i numeri in mano, come è stato per il modello della voce (5.3) e per il portachiavi
  (ADR 0039 §6).
- **M13.5 — il computer control** (§20). **Il muro è dichiarato**, e misurato due volte su questa
  macchina: il grant TCC è legato al **binario** — ADR 0029 §16 per la registrazione dello schermo,
  ADR 0039 §6 per il portachiavi. La condizione d'ingresso **non aspetta una milestone: è una misura
  su questo Mac** — il permesso di controllo è chiesto a un eseguibile di ELA, concesso a quello, e
  sopravvive a un riavvio. Se a fine fase non si ottiene, **resta `Proposta` e la fase si chiude
  senza di lei**.
- **M13.6 — spostare un lavoro già in corso da un nodo a un altro** (§15, §12 del design), il terzo
  rinvio che ADR 0043 §9 aveva dato alla fase. **Fuori dalla fila**: entra **dopo M13.3**, e solo
  quando **almeno due capability che viaggiano dichiarano la propria idempotenza** — oggi ne
  dichiara una sola, `core.echo` (ADR 0038 §8), e uno spostamento con un ripetibile solo non ha
  niente da spostare che non sia un'eco. Se a fine fase nessun'altra lo fa, **resta `Proposta`**,
  come M13.5. **Perché non sta dentro M13.3**: è un cambio del runner, e dipende da una cosa che
  M13.3 crea (la dichiarazione) ma non completa (quante la daranno).

**Che cosa la Fase 13 non porta.**

- **Non il Planner.** §13 è una sezione della spec, non questa fase: **un piano continua ad
  attaccarsi a mano**, come dal primo giorno. Che uno step dichiari sempre le capability che userà
  resta il vincolo che ADR 0011 lascia a chi costruirà il Planner, e resta lì.
- **Non §30.** Il tetto di spesa **prende la sua milestone prima della Fase 14**, come dice la 5.9,
  e quella milestone non è una di queste sei.

*Che cosa la fase eredita, e non può contraddire:*

- **La regola della vista** (5.10): ogni milestone che aggiunge una capacità aggiunge la sua vista,
  e l'impronta di ADR 0044 §6 lo fa suonare — `apps/command-center/capabilities.txt` cambia,
  `make check` fallisce, e **la risposta si scrive nel documento della milestone che l'ha fatto
  suonare**, non rigenerando il file.
- **Il verifier non si fida della parola del tool** (§20, §63, ADR 0014): vale per un comando che
  ritorna `0` come per un `click` inviato.
- **L'Audit Log non è un canale neutro** (ADR 0011, Conseguenze): i bersagli di una decisione sono
  percorsi, e un percorso fuori dalla workspace è più personale di uno dentro (§57).

*Chi apre la milestone dell'eseguibile firmato.* ADR 0043 §9 le ha dato una casa — «una milestone
sua, prima di M17.3» — e non un numero, e adesso la aspettano **quattro** cose: `launchd`
(ADR 0029 §16), il portachiavi (ADR 0039 §6), M17.3 (una presenza che resta sullo schermo vuole un
processo residente) e M13.5. La regola è questa: **la prima milestone che ci sbatte contro la
apre**, e in questa fase è M13.5. Se la misura della sua condizione d'ingresso dice che il grant non
tiene, **la SPEC di M13.5 si ferma lì** e quella milestone si apre prima, con il suo numero. Un
debito che quattro cose aspettano e che nessuna apre è un debito che resta aperto per educazione.

*Perché nessun ADR:* è una scelta d'ordine e di perimetro — quale milestone, quando, che cosa
eredita, che cosa resta fuori — e nessuna riga di codice la contiene. Le parti tecniche prendono il
loro ADR con la milestone che le costruisce, come per la Fase 17 (5.10): il livello `HIGH` e la
revisione di ADR 0011 con M13.1, il posto del verifier e i pesi con M13.3.

## 6. I debiti datati

Un debito datato è un difetto **trovato lavorando e non riparato lì**, scritto in un ADR con la
data, con chi lo paga, e con la difesa più piccola possibile: un test che si accorge del pagamento.
Il criterio è di ADR 0025 §1; la forma è di ADR 0035 §7, che è anche il primo ad essere stato
pagato da chi doveva.

<!-- generato da scripts/generate_stato.py: i debiti datati -->

| Debito | Dichiarato | A carico | Stato |
|---|---|---|---|
| ADR 0041 §5 — i test che aspettano, e le difese che costano un terzo della suite | 2026-09-18 | della milestone sulla disciplina della suite | **aperto** |
| ADR 0044 §8 — il battito di `local`, e la prima vista che l'ha reso visibile | 2026-09-20 | della Fase 13 | **aperto** |
| ADR 0047 §16 — il surrogato isolato fuori dal piano | 2026-09-24 | di M13.3 | **aperto** |
| ADR 0047 §17 — i test di Windows che nessun job raccoglie | 2026-09-24 | di M13.3 | **aperto** |
| ADR 0047 §18 — gli skip sul sistema che il test copre, che nessuno vede | 2026-09-24 | di M9.5, la milestone sulla disciplina della suite | **aperto** |
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
   piano, una volta sola, alla fine della milestone, **letto intero** — sorvegliarlo costa più del
   lavoro che sorveglia, e tagliargli la coda costa il giro. Il controllo Linux è la CI sul branch,
   che il merge vuole verde su entrambi i runner di `make check`, e da M12.4 c'è anche la suite del
   nodo su `windows-latest`; `make check-linux` serve a riprodurre qui una CI rossa su ubuntu,
   fingendo l'altra metà della matrice (i suoi limiti sono scritti in `tests/foreign_machine.py`).
5. **Fai partire ELA**: [`GETTING_STARTED.md`](GETTING_STARTED.md), comando per comando — e da
   M12.3 anche questa macchina come nodo, in un terzo terminale (§11 di quel documento): un nodo è
   un comando in primo piano, e vive quanto la finestra (ADR 0039 §6).
6. **Quando aggiungi una milestone, un ADR, una regola o una capability, rigenera questo file.**
   `make check` te lo ricorda fallendo.
