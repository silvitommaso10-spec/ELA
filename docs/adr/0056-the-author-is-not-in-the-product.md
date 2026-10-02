# 0056. Niente di chi ha scritto ELA in ciò che installa e serve: un test per ciò che una macchina riconosce, il catalogo dell'audizione nella configurazione, la provenienza di una misura in `docs/`

- **Stato:** **Proposta** fino alla prova a mano di `docs/GETTING_STARTED.md` §22, passi 6–8, con
  `scripts/prova_m13_1c_m13_1d_m9_6.py`. Recepisce la SPEC di M9.6 (`docs/milestones/M9.6.md`), decisa dal revisore
  il 2026-10-02 con le domande 8–11 e con le decisioni I–M della sessione.
- **Data:** 2026-10-02
- **Riferimenti spec:** §9, §48, §54
- **Milestone:** M9.6

## Contesto

Il 2026-09-30 `CLAUDE.md` ha preso una regola: **niente di Tommaso in ciò che ELA installa e serve, `src/` e `apps/`**
— nomi, macchine, percorsi, siti, preferenze e identità stanno nella configurazione; `scripts/` e `docs/` sono
l'officina. Il censimento che l'ha accompagnata, rifatto il 2026-10-02 su tutto `apps/` e `src/`, ha trovato quattro
specie di cose sue: **l'indirizzo Tailscale del Mac** in un docstring di `src/ela/api/security.py`; **le voci del suo
account ElevenLabs**, `CANDIDATES` in `src/ela/infrastructure/machine/audition.py`, che arrivavano a chiunque da
`GET /voice` e da `ela voice`; **l'impronta delle sue macchine** nei docstring, come provenienza delle misure — i core,
lo schermo, macOS 26.6, Chrome 152, «the user's PC», «this plan» —; e **il suo nome** nel saluto di una composizione del
design system. Nessun test camminava `src/` e `apps/` come testo: le regole di `tests/architecture/` sono sull'AST dei
moduli Python.

## Decisione

### 1. Il test della regola prova ciò che una macchina sa riconoscere, e lo dice nel nome

**`tests/architecture/test_the_author_is_not_in_the_product.py`**, con
**`test_no_tailnet_host_and_no_path_inside_a_home_in_src_and_apps`**: nessun host di una rete Tailscale e nessun
percorso assoluto dentro la home di un utente, nei file di testo che git traccia sotto `src/` e `apps/`. Il resto della
regola — un nome, una macchina descritta in un docstring, una preferenza — **resta alla review**, e il nome del test non
promette di più.

- **I file** sono quelli che `git ls-files` elenca e che git non dice binari, letti come testo; non i `.DS_Store` che un
  `rglob` troverebbe. Il test afferma di averne letti; dove non c'è un repository lo dice uno `skipif`, quello di
  `tests/docs/test_line_endings.py` (ADR 0031 §6).
- **Le reti sono `TAILNET_RANGES`**, IPv4 e IPv6, lette da `ela.composition.settings` e non riscritte nel test (ADR 0037
  §2; decisione 10 della review). **Una rete è un prefisso più corto dell'indirizzo, senza bit d'host** — ciò che
  `ipaddress.ip_network(strict=True)` accetta —, ed è ammessa; un host scritto come `/32` o `/128`, o seguito da un
  percorso numerico in un URL, resta un host.
- **Una home è `/Users/<nome>`, `/home/<nome>` o `<disco>:\Users\<nome>`**, in qualunque maiuscola e con l'una o
  l'altra barra, dove comincia un percorso — all'inizio di una riga, dopo uno spazio, una virgoletta, un backtick, un
  `=`, una parentesi o `file://` —, mai dopo un host. **L'unico nome ammesso è il segnaposto `you`**, l'esempio di
  `ELA_FS_ROOT`.
- **Nella stessa passata, le sei voci**: i loro id, letti dalla tabella di `docs/milestones/M9.6.md` e non riscritti
  nel test, non sono in nessun file di `src/` né di `apps/`.
- **I casi negativi** sono sulle funzioni che cercano, con stringhe costruite: un host trovato e la sua rete no, in
  IPv4 e in IPv6; una home di un altro nome trovata, il segnaposto e una home dentro un URL no; un id dentro un testo
  trovato. Il test è stato rosso sull'albero di `ab87d9d` su `src/ela/api/security.py:500`, e su niente altro.

Non entra in `RULES` di `tests/architecture/rules.py`, che sono regole sull'AST dei moduli Python, e non ne cambia il
conto: legge testo, come `tests/architecture/test_travel_rules.py`. **È un'eccezione scritta** alla riga di `CLAUDE.md`
per cui le regole di `apps/` vivono nei test della loro cartella: questa attraversa `apps/` e `src/`, e vive in un
posto solo. Il precedente è il README di `apps/command-center/`, che nomina già una difesa fuori cartella
(`tests/api/test_console.py`). La riga di `CLAUDE.md` nomina il test e `TAILNET_RANGES`, ed è cambiata nello stesso
commit del test.

### 2. Ogni README di `apps/` nomina la regola con il suo test

**Ogni `README.md` tracciato sotto `apps/`, i segnaposto di `apps/desktop/` compresi** (decisione 11 della review),
nomina il percorso e il nome del test, in una riga «Regola | Test» dove il README ha quella tabella.
`test_every_readme_of_apps_names_the_rule_with_its_test`, nello stesso modulo, lo verifica su ogni README e afferma di
averne letto almeno uno: un README nuovo che non la nomina ferma la suite. È l'unica difesa che `apps/ios/` e
`apps/desktop/` hanno; quelle di `design-system` e `command-center` contano solo i test della loro cartella, e un test
fuori cartella non le disturba.

### 3. Il catalogo dell'audizione è nella configurazione: chi sceglie scrive

**`ELA_ELEVENLABS_CANDIDATES`**, un oggetto JSON su una riga, `{"<voice_id>": "<nome>", …}`, nell'ordine in cui le voci
si ascoltano; **il default è vuoto** (decisione K). Lo legge **`AuditionSettings`**, una sezione di `Settings` che
**solo il Core legge**: non `ElevenLabsSettings`, che legge anche il nodo, perché una riga del catalogo scritta male
non deve fermare `ela node run` su una macchina che non fa audizioni. **Il valore vuoto è un catalogo vuoto**, letto
prima del parser JSON (`env_ignore_empty`): la riga che `ela init` scrive, tolto il `#`, non ferma l'avvio. Un JSON
malformato, o un valore che non è un oggetto di nomi, è la `ConfigurationError` che nomina la variabile.

`CANDIDATES` esce da `src/`: **`Audition` riceve il catalogo alla costruzione**, dal composition root. Con il catalogo
vuoto **`GET /voice` lo dice**, con il campo **`empty_catalogue_setting`** — il nome dell'impostazione che lo riempie,
`null` con un catalogo pieno —, e **`ela voice`** stampa sotto la tabella «the audition's catalogue is empty:
ELA_ELEVENLABS_CANDIDATES in .env names the voices to try». **Non è un errore**: la risposta è `200`, il comando esce
`0`, la voce configurata resta in `candidates` come «(la voce configurata)» e continua a parlare. Un campo e non la
lunghezza di `candidates`, perché `candidates` porta la voce configurata anche quando il catalogo è vuoto. La riga che
Tommaso aggiunge al suo `.env` dopo il merge, con `sed`, e la sua verifica con `grep`, sono in `docs/GETTING_STARTED.md`
§22, passo 9.

### 4. La provenienza di una misura sta in `docs/`

Un docstring o un commento di `src/` o di `apps/` porta l'impronta di una macchina di Tommaso quando **nomina come luogo
di una misura una sua macchina, il suo account, il suo piano o il suo workspace, o ne porta l'hardware, il sistema o le
versioni**; il nome della topologia — «the PC», «the iPhone» — conta quando è il luogo di una misura o di un fatto
osservato, non quando è il ruolo della spec, e «this machine» per la macchina su cui ELA gira non è un'impronta. **La
macchina, il suo sistema e la data escono dal docstring; il numero che serve al ragionamento del codice resta; il
docstring rimanda al documento** — l'ADR o la milestone, con la sezione e non con la riga — che ha la macchina, la data
e il numero (decisione L). L'elenco delle righe è la tabella della proposta 3 di `docs/milestones/M9.6.md`.
L'indirizzo di `from_this_machine` diventa una descrizione: l'indirizzo tailnet del Core, `ELA_API_TAILNET_HOST`.

**Restano** le misure che non dicono dove sono state prese, le date delle review come provenienza di una decisione, gli
episodi datati che non nominano una macchina, e la direzione del design nelle parole dell'utente, che ADR 0042 registra
come il brief del prodotto.

### 5. La misura che non ha un documento

«Out of the twenty-five this workspace can reach», nel docstring di `CANDIDATES`, se ne va con lui e **non si porta in
`docs/` come una misura**: `docs/milestones/M11.3.md` dice 21 voci premade più le voci di libreria, e nessuna uscita
conservata dice venticinque. Misurarlo vorrebbe dire interrogare l'account di Tommaso; resta registrato così, con il
dubbio, nel documento di M9.6.

### 6. Righe riviste

Gli ADR non si riscrivono: queste righe si leggono con questo accanto.

- **ADR 0034 §9**: «la rosa dice le due frasi di §9» — da M9.6 la rosa è dell'utente, `ELA_ELEVENLABS_CANDIDATES`, e
  può essere vuota; le due frasi restano letterali del repository, e la regola 43 resta com'è. La ragione che il
  docstring di `CANDIDATES` dava per tenere la lista nel repository — «the list changes here, in a diff» — è superata
  (§3): la lista cambia quando la cambia chi ascolta.
- **ADR 0037 §2**: `TAILNET_RANGES` è letta anche dal test della regola (§1), che trova un host di quelle reti in
  `src/` e `apps/`.
- **`docs/milestones/M11.3.md`**, la tabella delle candidate e la riga di `ela voice` che «dice le sei candidate»:
  da M9.6 `ela voice` dice il catalogo del `.env`, o che è vuoto.

## Alternative considerate

- **Il catalogo in `ElevenLabsSettings`**, accanto alla voce. Scartata (§3): la sezione la legge anche il nodo, e una
  riga malformata fermerebbe `ela node run` — il contrario di ciò che `NodeConfig` scrive di sé.
- **Un catalogo vuoto come errore**, o `GET /voice` che risponde `409` senza catalogo. Scartata (decisione K): la voce
  configurata parla senza catalogo, e l'audizione è uno strumento per scegliere, non una condizione per parlare.
- **Il test che cammina l'albero con `rglob`.** Scartata (§1): troverebbe i `.DS_Store` ignorati, che ELA non installa.
- **Il test che legge solo la rete IPv4 e ogni prefisso**, com'era scritta la registrazione. Scartata (decisione 10):
  un indirizzo della stessa rete IPv6, o lo stesso indirizzo con `/32` accanto, l'avrebbe aggirata.
- **I README segnaposto saltati finché la cartella è vuota.** Scartata (decisione 11): è il modo in cui la prima
  cartella piena arriva senza la riga.

## Conseguenze

- Una regola nuova, fuori da `RULES`: `tests/architecture/test_the_author_is_not_in_the_product.py`, con il test della
  regola, quello delle sei voci, quello dei README e i loro casi negativi. Nessun port, nessuna rotta, nessun comando,
  nessuna migrazione.
- Un'impostazione nuova, `ELA_ELEVENLABS_CANDIDATES`, in `VARIABLES` e in `.env.example`, con il default vuoto; un
  campo nuovo di `VoiceStatusOut`, `empty_catalogue_setting`; una riga nuova di `ela voice`. Li tengono
  `tests/composition/test_audition_settings.py`, `tests/api/test_voice.py` e `tests/cli/test_voice.py`, con il catalogo
  che passa dal composition root com'è in produzione.
- Chi aggiorna un ELA già configurato vede il catalogo vuoto finché non scrive la riga: è il passo 9 di §22, per
  Tommaso, e la frase di `ela voice` per chiunque altro.
- La regola tiene ciò che una macchina riconosce; il resto lo tiene la review, e ogni milestone che tocca `src/` o
  `apps/` lo rilegge con il criterio di §4.
