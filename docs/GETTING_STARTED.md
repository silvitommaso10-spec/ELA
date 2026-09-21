# Far partire ELA, e farle fare la prima cosa

Il giro completo, comando per comando, su una macchina vuota. Non serve `curl`: dopo M8.2 ELA si
guida dalla riga di comando (§54; ADR 0023 per il processo, ADR 0024 per la CLI).

Ogni output qui sotto è quello vero di una sessione reale — id e istanti a parte, che cambiano.

### Come si leggono i comandi

Quello che sta fra parentesi angolari è un **segnaposto**: al suo posto va un valore vero, e le
parentesi **non si incollano**. `ela task run <id>` si scrive `ela task run 55ed2ab5-…`, mai
`ela task run <55ed2ab5-…>`. Sono tutti in questa tabella, con il posto da cui viene il valore:

| Segnaposto | Che cosa ci va | Da dove viene |
|---|---|---|
| `<questo repo>` | l'URL da cui cloni ELA | da dove hai preso il repository |
| `<id>` | l'id di un task | `ela task create`, oppure `ela task list` |
| `<approval-id>` | l'id di una richiesta di consenso | `ela approvals` |
| `<codice>` | il codice di arruolamento di un nodo | `ela node enroll`, stampato una volta sola |
| `<ip tailnet del Mac>` | l'indirizzo del Mac sulla tailnet | `tailscale ip -4`, sul Mac (§12) |
| `<nome della voce>` | una voce SAPI 5 installata sul PC | l'elenco del passo 3 di §12: sul PC di M12.4, `Microsoft Elsa Desktop` |
| `<chiave del modello del PC>` | la chiave Anthropic del nodo, mai quella del Core | la console Anthropic (§12, passo 4) |
| `<id del companion>` | l'id della riga dell'iPhone nel registro | `ela device list`, colonna `ID` (§13) |
| `<id della console>` | l'id della riga del Command Center nel registro | `ela device list`, colonna `ID` (§14) |

## 0. Che cosa serve

Python 3.12+, [uv](https://docs.astral.sh/uv/), e il repository:

```
git clone <questo repo> && cd ELA
uv sync
```

Da qui in poi i comandi si scrivono `uv run ela …`. Se preferisci scrivere solo `ela`, attiva il
virtualenv (`source .venv/bin/activate`).

## 1. `ela init` — la configurazione

```
uv run ela init
```

```
wrote .env (mode 600) with a fresh ELA_API_TOKEN. It is not printed here: read it from the file.
next:
  uv run alembic upgrade head   # ELA does not migrate on start-up (ADR 0006)
  ela serve                     # ELA creates its database directory and workspace
```

Scrive **un solo file**, `.env`, con un token generato e permessi `0600`. Il token **non viene
stampato**: sta nel file, e da lì lo leggono sia ELA sia la CLI. Sotto al token trovi ogni altra
variabile commentata accanto al suo default — si tocca solo ciò che si vuole cambiare.

Se `.env` esiste già, `init` **non lo tocca**: dice quali variabili quel file non imposta, e se
manca `ELA_API_TOKEN` esce con `2` e dice come generarne uno.

Il database e il workspace stanno di default in `~/.ela/`. Per tenerli altrove, togli il commento
a `ELA_DB_URL` e `ELA_WORKSPACE_DIR` nel `.env` appena scritto.

### Due righe che **devono** essere scritte: la cartella dei tuoi file

Da M13.1 ELA legge e scrive file **fuori dalla sua workspace**, e il confine glielo dichiari tu.
Sono due righe, e **non hanno un default**: finché mancano, `ela serve` non parte e lo dice.

```
ELA_FS_ROOT=/Users/tu/Documenti
ELA_FS_SCOPE=ELA
```

`ELA_FS_ROOT` è una cartella **tua**, che ELA non crea mai; `ELA_FS_SCOPE` è la sola cartella
dentro quella radice che `fs.read` e `fs.write` possono toccare — con l'esempio qui sopra,
`/Users/tu/Documenti/ELA`. Creala tu: ELA rifiuta di inventarsi un posto che non hai scelto.

Che cosa ELA rifiuta all'avvio, e perché il messaggio te lo dice invece di lasciartelo scoprire:

- una radice che **contiene o sta dentro** ciò che ELA usa per esistere — la workspace, il
  database, le catture, il segreto di un nodo, il `.env`, il suo stesso codice. Per questo `~` non
  va bene: contiene `~/.ela`;
- una radice che è un **link simbolico**. Su macOS è la forma che `~/Documents` prende quando
  «Scrivania e Documenti» di iCloud Drive è attivo: punta la variabile alla cartella vera,
  altrimenti ogni chiamata fallirebbe una per una senza spiegare perché;
- una radice che non esiste.

**Scrivere qui dentro è irreversibile**: `fs.write` è la prima capability `HIGH` di ELA, ti chiede
il permesso **ogni volta**, e nessuna policy potrà mai coprirla in anticipo — il rollback (§37) non
esiste ancora.

## 2. `alembic upgrade head` — lo schema

```
uv run alembic upgrade head
```

ELA **non migra all'avvio** (ADR 0006): una migrazione è un'operazione da eseguire
consapevolmente. Se te ne dimentichi, l'avvio si ferma dicendo esattamente questo comando.

## 3. `ela serve` — il processo

In un terminale:

```
uv run ela serve
```

```
INFO:     Uvicorn running on http://127.0.0.1:8351 (Press CTRL+C to quit)
```

Solo loopback: `ELA_API_HOST` accetta unicamente un indirizzo di questa macchina (ELA sulla rete
è la storia dei nodi, §56). Ogni rotta è dietro il token, `/health` compresa.

Gli altri comandi vanno in un **secondo terminale**, nella stessa directory (è lì che c'è il
`.env` con il token).

## 4. `ela health` e `ela diagnostics` — ELA è viva, e com'è fatta

```
uv run ela health
```

```
status    ok
database  ok
now       2026-09-07T14:24:54.378792Z
```

`ok` sul database vuol dire che ELA ha fatto un giro vero fino a SQLite: un health che risponde
senza toccare niente direbbe solo che il processo è acceso.

```
uv run ela diagnostics
```

```
version                0.1.0
database               sqlite:////tmp/elareal/ela.db
workspace              /tmp/elareal/workspace
user                   user
providers              anthropic: UNAVAILABLE
task types             analysis, classification, coding, extraction, planning, reasoning, routine
default profile        balanced
capabilities           core.echo, workspace.write_note, model.complete
tools                  core-echo, workspace-notes, model-complete
devices                local: available
tasks                  —
approvals waiting      0
recovered at start-up  0 failed, 0 skipped, 0 expired
```

`anthropic: UNAVAILABLE` è normale su una macchina senza chiave: il provider è registrato e lo
dice, ELA parte lo stesso e uno step `model.complete` fallirebbe senza toccare la rete. Per dargli
una chiave, `ELA_ANTHROPIC_API_KEY` nel `.env`.

`diagnostics` non stampa mai un segreto e mai contenuto tuo: dice **a che cosa** ELA è collegata,
non che cosa sta facendo.

## 5. Il primo task

Un task nasce da ciò che hai chiesto, e non ha ancora un piano:

```
uv run ela task create "il mio primo task"
```

```
id        55ed2ab5-94aa-581f-9468-c4d247d9fe04
state     CREATED
goal      il mio primo task
created   2026-09-07T14:25:27.988196Z
deadline  —
plan      —
```

Tieni da parte l'`id`: lo vogliono i comandi che seguono.

### Il piano, per ora, si scrive a mano

ELA non ha ancora un Planner (§13), quindi il piano entra da fuori. Ne trovi uno pronto in
[`examples/first-task.json`](examples/first-task.json): due step, il secondo dipendente dal primo —
un `core.echo` che non chiede niente a nessuno, e un `workspace.write_note` che chiede il tuo
consenso. Il file spiega da sé, nella chiave `_nota`, perché lo chiede.

```
uv run ela task plan <id> --file docs/examples/first-task.json
```

Cioè, con l'id stampato qui sopra e senza le parentesi:

```
uv run ela task plan 55ed2ab5-94aa-581f-9468-c4d247d9fe04 --file docs/examples/first-task.json
```

```
id        55ed2ab5-94aa-581f-9468-c4d247d9fe04
state     QUEUED
goal      il mio primo task
plan      be397065-1fc4-4ff2-8ead-c7e76657e7be
```

Il file viene mandato com'è. La sua forma è quella dell'API, ed è **temporanea**: il giorno in cui
il Planner esisterà, quell'endpoint cambierà o sparirà — non costruirci sopra niente di duraturo.

## 6. `ela task run` — ELA si ferma e chiede

```
uv run ela task run <id>
```

```
outcome         waiting_approval
state           WAITING_APPROVAL
steps executed  9c5b8f26-1a2b-4c3d-8e4f-000000000001, 9c5b8f26-1a2b-4c3d-8e4f-000000000002
```

Il primo step — l'echo — è stato eseguito; sul secondo ELA si ferma e chiede. **Non è per il
rischio:** `workspace.write_note` è LOW (§29), perché è lo *scope* a proteggerla — può scrivere
solo dentro la cartella autorizzata — e per questo la capability non richiede da sé
un'autorizzazione. A chiederla è lo **step**, che nel file dichiara `requires_authorization`. Il
Guardian ne domanda una quando la capability *oppure* lo step ne vogliono una: un piano può
alzare l'asticella su sé stesso, non abbassarla. Nessun tool viene eseguito senza una decisione
del Guardian, e nel dubbio la decisione è «no» (§33).

```
uv run ela approvals
```

```
APPROVAL                              TASK                                  CAPABILITY            TARGETS                        ASKS
47fbce38-66ab-519c-b7dc-8cce4bd4a7f2  55ed2ab5-94aa-581f-9468-c4d247d9fe04  workspace.write_note  workspace/notes/first-task.md  workspace.write_note on workspace/notes/first-task.md for step 9c5b8f26-… (scrivere la nota del primo task): workspace.write_note requires an authorization: none was given
```

Leggi la richiesta, poi rispondi. Il «sì» e il «no» hanno due comandi, perché sono due risposte
(§62):

```
uv run ela task approve <id> --approval <approval-id>
uv run ela task deny    <id> --approval <approval-id>
```

L'`--approval` è obbligatorio apposta: un «sì» si dà a una domanda che si è letta.

## 7. Di nuovo `run`, e il lavoro è fatto

```
uv run ela task run <id>
```

```
outcome         completed
state           COMPLETED
steps executed  9c5b8f26-1a2b-4c3d-8e4f-000000000002
```

Il secondo `run` esegue solo ciò che restava: il primo step era già fatto, e rifarlo sarebbe
rifare un lavoro che nessuno ha chiesto due volte (il ciclo è ri-entrante, ADR 0019).

La nota è sul disco, dove `diagnostics` diceva che sta il workspace:

```
cat ~/.ela/workspace/workspace/notes/first-task.md
```

```
Primo task di ELA: eseguito dal Task Runner, autorizzato dall'utente.
```

(`workspace/` due volte non è un refuso: la prima è la directory del workspace, la seconda è il
percorso che lo step ha chiesto — ogni percorso che un tool scrive è relativo alla radice.)

E il task lo racconta step per step:

```
uv run ela task show <id>
```

```
id        55ed2ab5-94aa-581f-9468-c4d247d9fe04
state     COMPLETED
goal      il mio primo task
created   2026-09-07T14:25:27.988196Z
deadline  —
plan      be397065-1fc4-4ff2-8ead-c7e76657e7be

STEP                                  STATE      RISK  CAPABILITIES          GOAL
9c5b8f26-1a2b-4c3d-8e4f-000000000001  COMPLETED  SAFE  core.echo             dire ciao, per vedere che la catena gira
9c5b8f26-1a2b-4c3d-8e4f-000000000002  COMPLETED  LOW   workspace.write_note  scrivere la nota del primo task
```

La colonna `RISK` è quella che il **piano** dichiara, e dice LOW perché LOW è quello del catalogo
(§29). Non è il campo che ha fatto fermare ELA: quello era `requires_authorization` dello step.

E ciò che i tool hanno **prodotto** si legge da qui:

```
uv run ela task results <id>
```

```
STEP                                  CAPABILITY            STATUS     TOOL             WHEN
9c5b8f26-1a2b-4c3d-8e4f-000000000001  core.echo             SUCCEEDED  core-echo        2026-09-07T14:25:29.104882Z
9c5b8f26-1a2b-4c3d-8e4f-000000000002  workspace.write_note  SUCCEEDED  workspace-notes  2026-09-07T14:25:31.733601Z

core.echo — step 9c5b8f26-1a2b-4c3d-8e4f-000000000001
  message  ciao, sono ELA

workspace.write_note — step 9c5b8f26-1a2b-4c3d-8e4f-000000000002
  path   workspace/notes/first-task.md
  bytes  70
```

È l'unico comando che ti restituisce il **contenuto**: il registro dice che cosa è successo
(§32), questo dice che cosa è stato prodotto (§63). Con una chiave del provider, è qui che
trovi la risposta del modello.

## 8. Il registro, e la sua catena

Tutto ciò che ELA ha fatto è nel registro append-only (§32):

```
uv run ela audit tail -n 6
```

```
WHEN                         EVENT                  ACTOR                       TASK        SUMMARY
2026-09-07T14:25:31.728943Z  AUTHORIZATION_GRANTED  USER:user                   55ed2ab5-…  grant: authorization … for workspace.write_note from approval …
2026-09-07T14:25:31.731288Z  PERMISSION_DECIDED     SYSTEM:permission-guardian  55ed2ab5-…  decide: ALLOWED workspace.write_note (LOW): workspace.write_note is covered by authorization …
2026-09-07T14:25:31.733601Z  TOOL_EXECUTED          ELA:ela                     55ed2ab5-…  execute: SUCCEEDED workspace.write_note by workspace-notes
2026-09-07T14:25:31.735295Z  EXECUTION_VERIFIED     ELA:ela                     55ed2ab5-…  verify: passed workspace.write_note by workspace-notes-verifier
2026-09-07T14:25:31.737529Z  STEP_COMPLETED         ELA:ela                     55ed2ab5-…  complete_step: step … RUNNING -> COMPLETED
2026-09-07T14:25:31.741590Z  TASK_COMPLETED         ELA:ela                     55ed2ab5-…  complete: EXECUTING -> COMPLETED
```

(gli id sono accorciati qui per stare nella pagina; la CLI li stampa interi, perché servono al
comando dopo.)

Il registro non porta **mai** gli argomenti di una chiamata né l'output di un tool: registra i
bersagli, non il contenuto (§57). E si può verificare:

```
uv run ela audit verify
```

```
entries    24
head hash  005f3d15618aa7ba04b426d18521fc20f3d944f689f22ec19b7ec77cc9c265a6
```

Ogni riga porta l'hash della precedente: cambiarne una, toglierne una o riordinarle rompe la
catena, e `verify` dice **dove**. Se tieni da parte quei due numeri fuori dal registro, diventa
visibile anche una coda tagliata.

## 9. Gli altri comandi

```
uv run ela task list --state QUEUED     # i task, filtrabili e limitabili
uv run ela task cancel <id> --reason …  # fermare un task è tuo, sempre (§65)
uv run ela task results <id>            # ciò che i tool hanno prodotto
uv run ela device list                  # i nodi, e se ELA li userebbe adesso
uv run ela provider list                # i provider, con lo stato che dichiarano
```

Ogni comando di lettura ha `--json`, che stampa la risposta dell'API così com'è: la tabella è per
te, il JSON è per uno script.

### Quando avrai una chiave

C'è un secondo esempio, [`examples/ask-model.json`](examples/ask-model.json): un piano con un solo
step `model.complete`, cioè una domanda a un modello. Si usa come il primo — `task plan`, `task
run`, il consenso, `task run` — e la risposta si legge con `ela task results`. Senza chiave lo
step fallisce con `provider.unavailable` **senza toccare la rete**, che è il comportamento
dichiarato del provider: per dargliene una, `ELA_ANTHROPIC_API_KEY` nel `.env`.

Un secondo step che salvasse la risposta in una nota non è ancora esprimibile: gli argomenti di
uno step stanno nel piano, e nessun dato passa da uno step al successivo (ADR 0018 §6). È il primo
limite che incontrerai davvero.

## 10. Quando qualcosa non va

I codici di uscita sono un contratto (ADR 0024 §6):

| Uscita | Vuol dire | Che cosa fare |
|---|---|---|
| `0` | fatto | — |
| `1` | ELA ha risposto, e la risposta è un errore | leggi il messaggio: è quello dell'API |
| `2` | configurazione o invocazione sbagliata: a ELA non è arrivato niente | `ela init`, o rileggi il comando |
| `3` | nessuno risponde: ELA non è avviata | `ela serve` nell'altro terminale |

Un «no» di ELA e un'ELA spenta non escono mai con lo stesso codice: uno script che riprova al
`3` non deve riprovare all'`1`.

## 11. Questa macchina come nodo, e la prova che il lavoro è avvenuto altrove

Da M12.3 questo Mac può essere **anche un nodo**: un secondo processo che prende le chiamate del
Core, le esegue con i suoi tool e riporta l'esito. Serve un **terzo terminale** — il nodo è un
comando in primo piano, come `ela serve`, e non c'è un servizio di sistema: finché ELA non ha un
eseguibile firmato suo, il permesso resta del terminale (ADR 0029 §16). Il prezzo è dichiarato: il
nodo vive quanto la finestra.

Questa sezione non si può verificare da `pytest` — la suite non apre prese di rete, per scelta —
ed è per questo che è scritta qui, comando per comando.

Nel **secondo** terminale, quello dei comandi, si conia un codice:

```
uv run ela node enroll --privacy TRUSTED
```

```
code                                            privacy   expires at
<codice>                                        TRUSTED   ...
```

Il codice si stampa **una volta**. Nel **terzo** terminale si avvia il nodo e lo si incolla quando
lo chiede — non si vede mentre lo si scrive, ed è voluto: un segreto sulla riga di comando finirebbe
in `ps` e nella cronologia della shell.

```
uv run ela node run --join
```

```
Enrollment code:
```

Da quel momento il nodo ha la sua identità in `~/.ela/node.json` — due campi, `0o600` — e non serve
più `--join`: le volte successive basta `uv run ela node run`. Nel secondo terminale il nodo si
vede:

```
uv run ela device list
```

Compare accanto a `local`, `available`, con i suoi **quattro** tool: `core-echo`, `model-complete`,
`voice-speak`, `voice-speak-online`.

**La prova, come è stata fatta in M12.3** (il 2026-09-12). Un task dichiarato `TRUSTED` con uno step
`voice.speak`, e le tre cose da guardare:

```
uv run ela task create "dì una frase" --privacy TRUSTED
uv run ela task plan <id> --file docs/examples/speak-on-a-node.json
uv run ela task run <id>
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

L'ultimo `run` **non** è di troppo: la consegna del nodo chiude lo step, e il piano lo fa avanzare
la chiamata successiva (ADR 0038 §11). La prima volta la risposta è `assigned` con l'id
dell'assegnazione e la sua scadenza; la seconda, `completed`.

1. **Si sente parlare** — e l'albero dei processi mostra `say` sotto il **nodo**, non sotto il
   Core. È l'unica prova che l'esecuzione è avvenuta nell'altro processo. `uv run` lascia un
   processo intermedio, quindi `say` è un **nipote** e non un figlio: si guarda con
   `pstree -p <pid del nodo>`, oppure, senza installare niente,

   ```
   for k in $(pgrep -P <pid del nodo>); do pgrep -P $k -l; done
   ```

   Misurato il 2026-09-12 su questa macchina: `say` discendeva dal pid del nodo, e dal Core mai.
2. `uv run ela audit tail` porta un `TOOL_EXECUTED` che **nomina il device_id del nodo**, e un
   `DEVICE_SELECTED` che l'ha scelto.
3. **Il Core spento a metà**: `Ctrl-C` sul primo terminale fra l'esecuzione e la consegna, poi
   `uv run ela serve` di nuovo. Il nodo ritenta, consegna la busta che teneva, e `ela task show
   <id>` dice `completed`. È la storia 11 del contratto, con due processi veri.

**E la prova negativa**, che è quella che dice dove finisce tutto questo: uno step
`workspace.write_note` sullo stesso task **non** va al nodo. Il `DEVICE_SELECTED` della nota sceglie
`local`, «1 of 2 node(s) eligible», e con `uv run ela audit tail --task <id> --json` fra i suoi
candidati il nodo porta `"refusals": ["UNVERIFIABLE"]`: il verifier di quella capability
rileggerebbe la workspace del **Core**, e potrebbe rispondere «sì» per una nota che il nodo non ha
mai scritto. Quattro capability su otto viaggiano; queste no.

**Riletta sul codice il 2026-09-17, e non rieseguita.** Due cose di questa sezione non sono più come
la prova le ha viste. La prima è il testo del rifiuto: la frase
`UNVERIFIABLE (workspace.write_note: its verifier reads this machine)` il codice la scrive soltanto
quando **nessun** nodo è idoneo, e qui `local` lo è. La seconda pesa di più: **su una macchina sola
lo step non va più al nodo.** Da M12.3c l'alimentazione si legge, e il nodo e `local` leggono la
stessa: `local` vale 20 (la rete) più la corrente, il nodo 5 (la rete) più 10 (libero) più la stessa
corrente — 30 a 25 con il Mac attaccato, 20 a 15 staccato. Il 2026-09-12 il nodo vinceva perché
dichiarava una corrente che non aveva letto. **La prova con due macchine, che si riproduce, è la
§12.**

## 12. Un PC Windows come nodo, con il Core su questo Mac

Da M12.4 un PC Windows è un nodo come il Mac della §11, con lo stesso ciclo: il **Core** resta su
questo Mac, il **nodo** gira sul PC, e i due si parlano attraverso la tailnet. Sul PC i comandi sono
di **PowerShell**, in una finestra da utente normale; sul Mac, del terminale.

Gli output qui sotto sono quelli della prova a mano del **2026-09-17**, con il Core su questo Mac
(tailnet `100.76.92.39`) e il nodo sul PC `DESKTOP-QQ0GSE2` (tailnet `100.92.165.124`, Windows 11
10.0.26200, Python 3.12.10). Dove un passo non è stato rieseguito perché una misura lo aveva già
coperto, è detto lì. Il trascritto integrale sta in `.git/m12-reference/ela-prova-a-mano.txt`.

Sul PC servono Windows 10 o 11, Tailscale acceso sulla stessa tailnet del Mac, [uv](https://docs.astral.sh/uv/),
il repository in `$HOME\ELA` con `uv sync --locked`, e un Python **3.12.4 o successivo**: su
Windows il nodo rifiuta una 3.12 più vecchia, perché lì la cartella del segreto non sarebbe
protetta (M12.4, dec. B).

### 1. Sul Mac: il Core dal codice giusto, e anche sulla tailnet

**Il Core deve girare dal codice del branch del nodo Windows**, o il piano d'esempio e la lettura
dell'alimentazione non ci sono: nella prova il primo avvio è stato fatto da `main`, e `task plan` è
morto con `No such file or directory` sul file del piano. Se il branch è già aperto in un worktree,
`git checkout` lo rifiuta, e si va sul commit staccando la testa:

```
git fetch && git checkout --detach origin/m12.4-node-windows
uv sync --locked && uv run alembic upgrade head
```

```
HEAD is now at 2fd2def docs(m12.4): la review di ADR 0040 …
```

Poi l'indirizzo sulla tailnet:

```
tailscale ip -4
```

```
100.76.92.39
```

(l'indirizzo è quello misurato il 2026-09-17; nella prova il `.env` del Mac lo aveva già, e il
comando non è stato rieseguito.) Quell'indirizzo va nel `.env` del Mac, e il Core si avvia nel primo
terminale:

```
ELA_API_TAILNET_HOST=<ip tailnet del Mac>
```

```
uv run ela serve
```

```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

(queste tre righe sono del primo avvio della prova, quello da `main`; dopo il checkout il trascritto
riporta la sola `Application startup complete.`) Il Core ascolta sul loopback **e** sulla tailnet;
ogni rotta resta dietro il token.

### 2. Sul PC: il Mac risponde

```powershell
Test-NetConnection <ip tailnet del Mac> -Port 8351
curl.exe -s -o NUL -w "%{http_code}`n" "http://<ip tailnet del Mac>:8351/health"
```

```
InterfaceAlias   : Tailscale
SourceAddress    : 100.92.165.124
TcpTestSucceeded : True
401
```

Il Core risponde e rifiuta una richiesta senza token, che è ciò che deve fare. (Misurato il
2026-09-17 con lo stesso Core sulla stessa tailnet, e per questo non ripetuto durante la prova.)

### 3. Sul PC: quale voce

```powershell
$list = @'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name + ' | ' + $_.VoiceInfo.Culture.Name }
$s.Dispose()
'@
& "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -EncodedCommand ([Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($list)))
```

```
Microsoft Elsa Desktop | it-IT
Microsoft Zira Desktop | en-US
```

(l'elenco è quello di P3, riscritto nella forma che stampa lo script di questa sezione: lì i campi
erano quattro, con il genere e `enabled`.) Su questo PC l'unica voce `it-IT` che SAPI 5 elenca è `Microsoft Elsa Desktop`, ed è il
`<nome della voce>`. Le voci «OneCore» delle impostazioni di Windows non compaiono qui, e il nodo non
le può usare. (Misurato il 2026-09-15, non ripetuto durante la prova.)

### 4. Sul PC: il `.env` del nodo — senza `ela init`

`ela init` **non** si usa sul PC: scrive il `.env` con una funzione che Windows su Python 3.12 non
ha, e un nodo non ha bisogno del token del Core. Il file si scrive così, e il modo conta:
`[IO.File]::WriteAllText` scrive UTF-8 **senza BOM**, mentre `Set-Content` e `Out-File` di
PowerShell 5.1 ne mettono uno, e con il BOM la prima variabile del file verrebbe ignorata **in
silenzio**.

```powershell
$lines = @'
ELA_NODE_CORE_URL=http://<ip tailnet del Mac>:8351
ELA_VOICE_NAME="<nome della voce>"
ELA_ANTHROPIC_API_KEY=<chiave del modello del PC>
'@
[IO.File]::WriteAllText("$HOME\ELA\.env", $lines)
Get-Content "$HOME\ELA\.env"
```

Nella prova il file è stato scritto **senza** la terza riga, perché su nessuna delle due macchine c'è
ancora una chiave del modello:

```
ELA_NODE_CORE_URL=http://100.76.92.39:8351
ELA_VOICE_NAME="Microsoft Elsa Desktop"
```

Tre cose da sapere prima di andare avanti:

- **`ELA_MODEL_ROUTES` deve essere uguale a quella del Mac.** Se il `.env` del Mac la imposta,
  copia quella riga identica in questo file; se non la imposta, non scriverla — nella prova il Mac
  non la impostava. Con due tabelle diverse ogni chiamata a un modello che il PC esegue fallisce la
  verifica sul Mac: è la seconda prova negativa del passo 8.
- **Nessun `ELA_NODE_PERFORMANCE`** e nessun tratto: chi parla lo decide ciò che le macchine
  leggono di sé, non una dichiarazione (passo 6).
- **La chiave è del PC** e non viaggia mai con il lavoro: il Core manda la chiamata, il nodo usa la
  sua. Il file sta in `$HOME\ELA` con i permessi della cartella del profilo — lo leggono i processi
  del tuo utente, lo stesso confine del segreto del nodo.

### 5. Il nodo: arruolato dal Mac, avviato sul PC

Sul Mac, nel secondo terminale, un codice:

```
uv run ela node enroll --privacy TRUSTED
```

```
kz5OC1S7mRM…
```

(il comando stampa una tabella — il codice, la privacy, la scadenza — come nella §11; il trascritto
della prova ne ha tenuto il solo codice, e qui è troncato: vale una volta sola ed è scaduto.) Il
codice si stampa una volta e vale dieci minuti. Sul PC:

```powershell
Set-Location $HOME\ELA
uv run ela node run --join
```

```
Enrollment code:
```

Incolla il codice quando compare — non si vede mentre lo scrivi, ed è voluto. Se lo incolli monco, il
nodo lo dice e non parte:

```
ela: this code did not enrol the node (unauthorized). A code is good once and for ten minutes: ask the Core for another one.
```

Arruolato, il nodo ha la sua identità in `$HOME\.ela\node.json`, in una cartella con i permessi
ristretti a te, SYSTEM e Administrators; le volte dopo basta `uv run ela node run`. **Lascia aperta
questa finestra**: il nodo vive quanto lei, e chiuderla con la X lo ferma senza chiudere niente.
Mentre gira non stampa niente.

In una **seconda** finestra di PowerShell, il firewall:

```powershell
Get-NetFirewallApplicationFilter | Where-Object Program -like '*python*' | Get-NetFirewallRule | Select-Object DisplayName, Direction, Action, Enabled
```

Nella prova non ha stampato **nessuna riga**, e non è comparso nessun dialogo: il nodo chiama il
Core, non ascolta niente.

Sul Mac:

```
uv run ela device list
```

```
NAME             ID                                    OS       AVAILABLE  STATUS   LAST SEEN                    REVOKED  TOOLS
local            6c38f1c5-6cda-5680-8a7a-4f061588deed  MACOS    yes        UNKNOWN  2026-09-17T20:42:51.528882Z  —        core-echo, workspace-notes, model-complete, perception-screen, listen, perception-screen-text, voice-speak, voice-speak-online
DESKTOP-QQ0GSE2  5ddae87a-6eb1-4fb0-947c-f912fce6c026  WINDOWS  yes        IDLE     2026-09-17T20:42:56.806628Z  —        core-echo, model-complete, voice-speak
```

Il PC compare accanto a `local`, sistema `WINDOWS`, disponibile, e con **tre** tool. Non
`voice-speak-online`: sul PC la voce online non ha un riproduttore, e il nodo non promette ciò che la
macchina non sa fare.

**`local` può comparire `no` / `UNKNOWN`**, ed è così che va oggi — nella prova è successo in altre
due letture, alle 20:26 e alle 20:51: il Core manda il proprio battito solo all'avvio e a ogni
`task run` (ADR 0023 §5-bis e §9; M12.3c ha lasciato fuori scope un battito periodico), quindi fra
un run e l'altro la sua riga scade rispetto al TTL. Non tocca il piazzamento — che avviene subito dopo il battito di un `run` — ma la lista lo
mostra come assente (osservato nella prova, ed è fra le cose da riesaminare di M12.4).

### 6. Il Mac a batteria, e il PC che parla

**Stacca l'alimentatore del Mac**, e lascialo staccato fino alla fine della sezione. È ciò che
manda il lavoro al PC, ed è letto, non dichiarato: il Mac a batteria vale 20 punti (la rete),
il PC a corrente 25 (la rete 5, la corrente 10, libero 10). Con il Mac attaccato vincerebbe lui,
30 a 25, e parlerebbe il Mac.

```
uv run ela task create "fai parlare il PC" --privacy TRUSTED
uv run ela task plan <id> --file docs/examples/speak-on-a-node.json
uv run ela task run <id>
uv run ela approvals
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

Il primo `run` si ferma sul consenso; dopo l'approvazione il secondo risponde `assigned`, e lo step
è del PC:

```
outcome         waiting_approval
state           WAITING_APPROVAL
steps executed  5a1e0c3d-7b2f-4e8a-9c41-000000000001
```

```
outcome         assigned
reason          step 5a1e0c3d-7b2f-4e8a-9c41-000000000001 assigned to node DESKTOP-QQ0GSE2 (5ddae87a-6eb1-4fb0-947c-f912fce6c026) as assignment 0fa13927-593d-46f7-b5e2-744dde2c15aa, due by 2026-09-17T20:46:46.808533+00:00
state           EXECUTING
```

**Il PC parla**, con la voce di Elsa — una frase di tre quarti di minuto, lunga apposta per le prove
di questo passo e del passo 7. Nella prova l'albero dei processi e il Core spento a metà sono stati
fatti su un **secondo** task con lo stesso piano: gli output dei due punti qui sotto sono di quello,
il resto del passo è del primo task.

1. **L'albero dei processi, sul PC**, nella seconda finestra, mentre parla:

   ```powershell
   function Show-Tree($id, $depth = 0) {
     Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" | ForEach-Object {
       ('  ' * $depth) + "$($_.ProcessId) $($_.Name)"; Show-Tree $_.ProcessId ($depth + 1)
     }
   }
   Get-CimInstance Win32_Process -Filter "Name='uv.exe'" | ForEach-Object { "$($_.ProcessId) uv.exe"; Show-Tree $_.ProcessId 1 }
   ```

   ```
   4428 uv.exe
     32904 ela.exe
       27772 python.exe
         8748 python.exe
           32832 powershell.exe
   ```

   `powershell.exe` è in fondo alla catena che parte da `uv.exe`: la voce è figlia del nodo, e i due
   `python.exe` sono il lanciatore del venv e l'interprete vero (P4).
2. **Il Core spento a metà**: `Ctrl-C` sul primo terminale del Mac mentre il PC parla, poi
   `uv run ela serve` di nuovo. Il nodo, finita la frase, ha trovato il Core appena riacceso, e ha
   consegnato la busta che teneva: nessun intervento sul PC. (Nella prova è successo due volte — al
   cambio di commit del passo 1 e qui — e il nodo ha riagganciato da solo tutte e due.)

Quando la frase è finita e il nodo ha consegnato, sul Mac:

```
uv run ela task run <id>
uv run ela audit tail --task <id> -n 20
```

```
outcome         completed
state           COMPLETED
```

```
2026-09-17T20:43:53.955644Z  DEVICE_SELECTED     SYSTEM:device-orchestrator  place step 5a1e0c3d-…: DESKTOP-QQ0GSE2 (5ddae87a-6eb1-4fb0-947c-f912fce6c026) with 25 points, 2 of 2 node(s) eligible
2026-09-17T20:44:46.800192Z  TASK_STARTED        ELA:ela                     start: QUEUED -> EXECUTING (on device 5ddae87a-6eb1-4fb0-947c-f912fce6c026)
2026-09-17T20:44:46.806755Z  PERMISSION_DECIDED  SYSTEM:permission-guardian  decide: ALLOWED voice.speak (MEDIUM): voice.speak is covered by authorization ed2d7872-…
2026-09-17T20:45:27.463987Z  TOOL_EXECUTED       ELA:ela                     execute: SUCCEEDED voice.speak by voice-speak
2026-09-17T20:45:27.479103Z  EXECUTION_VERIFIED  ELA:ela                     verify: passed voice.speak by voice-speak-verifier
2026-09-17T20:45:54.306784Z  TASK_COMPLETED      ELA:ela                     complete: EXECUTING -> COMPLETED
```

Il `DEVICE_SELECTED` nomina il PC «with 25 points», e il `TOOL_EXECUTED` porta il `device_id` del PC
— quello di `ela device list` — quando si legge con `--json`. I punti di **tutti e due** i candidati,
con i loro componenti, si vedono nel JSON del passo 8: qui l'`audit tail` è stato letto senza.

### 7. `Ctrl-C` sul nodo, mentre parla

Un terzo task, con lo stesso piano, fino a `assigned`; poi, quando il PC comincia a parlare, `Ctrl-C`
**nella finestra del nodo**, e nella stessa finestra:

```powershell
"exit=$LASTEXITCODE"
```

```
exit=0
```

Nella prova la voce si è fermata subito, l'uscita è stata `0`, e **non** è comparsa nessuna riga
`Exception ignored`: è la traccia che la sonda di P4 lasciava e che il nodo non deve lasciare. Poi il
nodo si riavvia con `uv run ela node run`.

**Che cosa ne è stato del task interrotto non è stato letto** (2026-09-17): la lettura è stata
saltata durante la prova. Per il Core è un nodo che ha taciuto, e l'assegnazione scade — ma qui non
c'è l'output che lo mostra.

### 8. Le prove negative

**Una nota non va al nodo.** `docs/examples/first-task.json` ha due step: un `core.echo`, che
viaggia, e un `workspace.write_note`, che no.

```
uv run ela task create "una nota" --privacy TRUSTED
uv run ela task plan <id> --file docs/examples/first-task.json
uv run ela task run <id>
```

Il primo `run` risponde `assigned`: l'echo è del PC. Dopo qualche secondo, il tempo che il nodo
consegni:

```
uv run ela task run <id>
uv run ela audit tail --task <id> -n 10 --json
```

Il secondo `run` chiude l'echo e si ferma sul consenso della nota, e nel registro il
`DEVICE_SELECTED` della nota sceglie `local`:

```
20:56:11.722534Z DEVICE_SELECTED  place step 9c5b8f26-…-000000000002: local (6c38f1c5-…) with 20 points, 1 of 2 node(s) eligible
    candidates:
      6c38f1c5-…  points 20  components {traits 0, network 20, performance 0, power 0, workload 0, status 0}  refusals []
      5ddae87a-…  points 25  components {traits 0, network 5, performance 0, power 10, workload 0, status 10}  refusals ["MISSING_TOOL", "UNVERIFIABLE"]
```

Il PC porta **due** rifiuti: `MISSING_TOOL`, perché non ha `workspace-notes`, e `UNVERIFIABLE`,
perché il verifier della nota rileggerebbe la workspace del Mac, dove il PC non ha scritto niente.
Aveva più punti del Mac e non è stato scelto. Il consenso della nota si nega con `ela task deny`.

**Una tabella di rotte diversa fa fallire la verifica** — **non eseguita il 2026-09-17**, perché non
c'è ancora una chiave del modello né sul Mac né sul PC, e senza chiave `model.complete` fallisce
prima della verifica con `provider.unavailable`. Quando la chiave ci sarà: ferma il nodo con
`Ctrl-C`, aggiungi al `.env` del PC una riga che il Mac non ha, e riavvialo:

```powershell
[IO.File]::AppendAllText("$HOME\ELA\.env", "`nELA_MODEL_ROUTES={""reasoning"": {""providers"": [""anthropic""], ""profile"": ""cheap""}}`n")
uv run ela node run
```

Sul Mac, il piano con uno step `model.complete`:

```
uv run ela task create "una domanda" --privacy TRUSTED
uv run ela task plan <id> --file docs/examples/ask-model.json
uv run ela task run <id>
uv run ela approvals
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
uv run ela task run <id>
uv run ela audit tail --task <id> -n 10 --json
```

Atteso: il PC risponde con la sua chiave e con il profilo della sua tabella, `cheap`; il Mac
ricalcola la rotta con la sua, che per `reasoning` dice `quality`, e la verifica fallisce —
nell'`EXECUTION_VERIFIED`, `model.misrouted`, «the call did not go where the policy routes it». Poi
si toglie quella riga, riscrivendo il `.env` con il blocco del passo 4, e si riavvia il nodo.

### 9. I numeri della prova (M12.4, dec. J)

Quattro numeri, **nessuno preso con un cronometro a mano**: ciascuno ha già un registro che lo
scrive. Misurati il 2026-09-17, Core su questo MacBook Air, nodo sul PC `DESKTOP-QQ0GSE2`,
attraverso la tailnet. **Il Mac era a batteria** per i numeri 1 e 4 e per la prima delle due letture
del 2 e del 3: l'alimentatore è stato riattaccato alla fine del passo 8, e le due letture stanno a
cavallo di quel momento.

1. **Dal piazzamento alla consegna**, dalla differenza fra i `created_at` dell'audit — tutte e due
   ore del Core, e il secondo è l'istante in cui il Core ha ricevuto la consegna:
   - `voice.speak`, la frase di 571 caratteri: `TASK_STARTED` 20:44:46,800 → `TOOL_EXECUTED`
     20:45:27,464 = **40,7 s**; sul task con il Core riavviato a metà, **40,4 s**. Quasi tutto è
     parlato: al ritmo di P3-bis, 75 ms per carattere, 571 caratteri varrebbero 43,1 s — **più**
     dell'intervallo intero —, quindi su questa frase Elsa ha parlato a non più di 71 ms per
     carattere, e ciò che la rete e la presa aggiungono resta sotto quello che la misura distingue.
   - `core.echo`: `STEP_STARTED` 20:55:32,270 → `TOOL_EXECUTED` 20:55:32,627 = **0,36 s**.
   - **È il piazzamento, non la presa**: il Core non scrive un evento quando il nodo prende il
     lavoro, e il numero comprende l'attesa del nodo fino alla sua richiesta successiva.
2. **Il long-poll attraverso la rete.** Fra due letture di `ela device list --json` a 280 s di
   distanza, il terminale del Core ha stampato **10 coppie**
   `"POST /nodes/work HTTP/1.1" 204 No Content` e `"POST /nodes/heartbeat HTTP/1.1" 200 OK`: dieci
   richieste tenute aperte per la finestra e chiuse dal Core, **nessuna caduta**, e il nodo non è mai
   uscito. (Sono `POST`, non `GET`.) Al riavvio del nodo la porta sorgente cambia e compaiono
   `GET /nodes/me` e `PUT /nodes/me`: il nodo rilegge la sua riga e si riannuncia.
3. **Il giro del nodo contro il TTL del battito.** Il `last_seen_at` del PC è passato da
   20:57:40,150 a 21:02:20,151 — 280,0 s — con 10 battiti in mezzo: **28,0 s per giro**, contro i
   **60 s** di `ELA_DEVICE_HEARTBEAT_TTL_SECONDS`, un margine di 2,1×. Su una macchina sola, in
   M12.3, erano ~33 s.
4. **I punti di §17.** Il PC «with 25 points», `2 of 2 node(s) eligible`; nel JSON, `local` 20
   (rete 20) e il PC 25 (rete 5, corrente 10, libero 10), con il Mac a batteria.

Nessuno di questi numeri ha fatto ritarare niente: i pesi di §17, la finestra di long-poll e il TTL
del battito restano quelli (M12.4, dec. J).

## 13. L'iPhone come companion: vedere e rispondere da lontano

L'iPhone **non è un nodo**: non prende lavoro, non esegue tool, non manda battiti. È l'unica
identità che *guarda e risponde* — le domande che aspettano, i task vivi, il sì, il no, e fermare un
task —, e lo fa da una pagina che ELA serve, nel browser del telefono (M12.5, ADR 0043).

Serve la tailnet del §12: l'iPhone con Tailscale, sulla stessa rete del Mac.

**1. Conia il codice del companion, al Mac.** È lo stesso comando dei nodi, con il ruolo:

```
uv run ela node enroll --privacy TRUSTED --role companion
```

Il codice dura dieci minuti e si usa una volta sola. Si copia con un **doppio clic** sulla cella
`CODE` (misurato: il doppio clic prende il codice intero) e arriva sull'iPhone con gli **Appunti
universali** — copiato sul Mac, incollato sul telefono, senza passare da nessun'altra parte.

`--privacy TRUSTED` non è un dettaglio: è **il tetto di ciò che il telefono può vedere**. Un task
`LOCAL_ONLY` — il default di ogni task — resta sul Mac: la pagina ne mostra l'id, lo stato, la
capability e il rischio, e dice di rispondere dal Mac.

**2. Arruola il browser, sull'iPhone.** Apri

```
http://<ip tailnet del Mac>:8130/companion/
```

**nel browser predefinito del telefono** — quello che si apre quando tocchi un collegamento. La
pagina chiede un codice: incollalo, lascia `IOS` nel campo Sistema, dai un nome, invia. Da lì in poi
il browser porta la sua credenziale in un cookie, e la pagina si apre da sola.

Perché proprio il predefinito: lo Shortcut e il tocco di una notifica aprono **quello**, e un cookie
messo in un altro browser lì non si vede. Cambiare browser predefinito vuol dire riarruolarsi.

**3. Il campanello (facoltativo).** Senza, il telefono vede ogni domanda quando apri la pagina; con,
te lo dice. Conia l'argomento di ntfy **senza stamparlo** — è una credenziale durevole: chi lo
conosce legge i campanelli e può suonarne di falsi —, scrivendolo in coda al `.env` e mettendolo
negli appunti:

```
uv run python -c "import secrets,pathlib,subprocess; t=secrets.token_urlsafe(16); pathlib.Path('.env').open('a').write(f'\nELA_NTFY_TOPIC={t}\n'); subprocess.run('pbcopy', input=t, text=True)"
```

Poi installa **ntfy** dall'App Store, tocca «Subscribe to topic» e **incolla** l'argomento: è negli
appunti del telefono, con gli Appunti universali. Riavvia `ela serve`.

Che cosa esce da ELA, per intero: il titolo `ELA` e una riga come `WAITING APPROVAL · MEDIUM`.
Niente dello scopo, niente degli argomenti, niente del contenuto — il campanello è un campanello, non
una lettera. Il tocco apre la pagina della domanda, con un tocco solo.

**4. Lo Shortcut, per aprire la pagina senza digitare.** In Comandi: un'azione sola, **«Apri URL»**,
con l'indirizzo del passo 2. Chiamalo **«Cruscotto»**: è il nome che Siri riconosce anche a telefono
bloccato (chiede il codice di sblocco e poi apre). «ELA» da solo Siri non lo capisce. Lo Shortcut non
contiene nessun segreto: apre un indirizzo, e la credenziale è quella del browser.

**5. Che cosa fa la pagina.** La sfera dice se una domanda aspetta (`WAITING APPROVAL`), se ELA sta
lavorando (`WORKING`) o se è ferma (`IDLE`). Sotto, le domande che aspettano e i task vivi. Toccare
una domanda apre la pagina della domanda: che cosa ELA vuole fare, con che rischio, fin dove può
andare il contenuto, per quanto vale il sì. **Il sì risponde e fa ripartire il task nella stessa
richiesta** — le stesse due cose che al Mac sono `ela task approve` e `ela task run` —, e la pagina
torna con l'esito vero. Toccare un task vivo porta alla conferma per fermarlo, su una seconda pagina:
fermare non si annulla.

**6. Revocare il telefono.** Come per un nodo, e vale subito:

```
uv run ela device list
uv run ela node revoke <id del companion>
```

Alla richiesta successiva la pagina torna a chiedere un codice, il cookie sparisce dal browser, e
nell'audit c'è `DEVICE_REJECTED` con `revoked`. Un codice nuovo riarruola lo stesso browser.

## 14. Il Command Center: ELA nel browser del Mac

Il Command Center è la dashboard di ELA — la presenza, che cosa sta facendo, le domande che
aspettano, i dispositivi, il riassunto di un task — e vive nel **browser del Mac**, servito da ELA
stessa (M17.2, ADR 0044). Non è un'applicazione e non c'è niente da installare: è un'identità in
più nel registro, con il suo codice e il suo cookie.

**1. Conia il codice della console, al Mac.** Lo stesso comando dei nodi e del telefono, con il
terzo ruolo:

```
uv run ela node enroll --privacy TRUSTED --role console
```

Dura dieci minuti, si usa una volta sola, e presentato su un'altra rotta di arruolamento è
rifiutato **senza consumarsi**: se lo incolli nel posto sbagliato non hai perso niente.

**2. Apri la pagina, e da quale indirizzo.** Sul Mac, `http://127.0.0.1:<porta>/console`.

**La porta la decide il tuo `.env`** (`ELA_API_PORT`), e il modo di sapere quale sia davvero è
chiederlo al processo:

```
uv run ela diagnostics
```

La riga `addresses` porta gli indirizzi su cui ELA **ha legato**, non quelli che l'impostazione
chiede: se la tailnet non c'era all'avvio, lì c'è solo il loopback.

Incolla il codice, dai un nome, invia. Da lì in poi il browser porta la sua credenziale in un
cookie e la pagina si apre da sola.

**L'indirizzo conta**, ed è misurato: un cookie è di **un browser e di un indirizzo**. Arruolata su
`127.0.0.1`, la console non manda niente all'indirizzo della tailnet, e viceversa. Se vuoi aprire
il Command Center anche da fuori, arruoli quell'indirizzo: sono due console, e `ela device list` le
mostra tutte e due.

**3. Che cosa vedi, e perché dipende da dove leggi.** Su `127.0.0.1` vedi anche il contenuto dei
task `LOCAL_ONLY`, che sono quasi tutti: non sta lasciando la macchina su cui vive. Dall'indirizzo
della tailnet vedi ciò che vede il telefono — l'id di quei task, non il contenuto. **La pagina lo
dice**, in fondo a ogni vista, nei due versi: «stai leggendo da questa macchina» oppure «stai
leggendo da fuori». Quella frase non è un dettaglio grafico: è il modo di accorgersi, a occhio, se
un giorno qualcosa cominciasse a inoltrare le connessioni attraverso il loopback.

Il tetto **non si dichiara all'arruolamento** e non si scrive da nessuna parte: si deriva dai due
capi del socket, a ogni richiesta, e la riga del registro resta quella che hai imposto.

**4. Le quattro viste.** La **home** con la sfera, che cosa ELA sta facendo adesso e le tre
tessere; l'**Approval Center**, dove una domanda si legge per intero e si risponde — il sì risponde
e fa ripartire il task, come dal telefono —; il **Device Center**, con la disponibilità e l'ultimo
contatto come due colonne distinte; e il **dettaglio di un task**, che è un riassunto di esecuzione:
l'obiettivo, il piano con lo step corrente, il dispositivo, e la riga che dice che il risultato c'è
e dove si legge. Il contenuto di un risultato non si legge lì: è su `GET /tasks/<id>/results`.

**5. Revocare la console.** Come per un nodo, e vale subito:

```
uv run ela device list
uv run ela node revoke <id della console>
```

Alla richiesta successiva la pagina torna a chiedere un codice. Un codice nuovo riarruola lo stesso
browser.

## Dove guardare dopo

- [`spec/ELA_spec.md`](spec/ELA_spec.md) — che cos'è ELA, per intero. È la fonte di verità.
- [`adr/`](adr/) — perché è fatta così, una decisione per file.
- [`adr/0023-composition-root-and-api.md`](adr/0023-composition-root-and-api.md) — le rotte, il
  token, i limiti dichiarati dell'API.
- [`adr/0024-cli.md`](adr/0024-cli.md) — perché la CLI è un client e non un secondo ELA.
- [`adr/0025-phase-8-debts.md`](adr/0025-phase-8-debts.md) — i debiti di Fase 8 pagati, e quelli
  che restano scritti.
- [`adr/0039-node-macos.md`](adr/0039-node-macos.md) — perché il nodo è un comando in primo piano,
  dove tiene il segreto e perché non nel portachiavi.
- [`adr/0040-node-windows.md`](adr/0040-node-windows.md) — il nodo su un PC: dove tiene il segreto,
  con che cosa parla, e perché dichiara solo ciò che la sua macchina sa fare.
- [`adr/0043-companion.md`](adr/0043-companion.md) — l'iPhone che guarda e risponde: il ruolo, il
  cookie, le pagine e il campanello.
- [`adr/0044-command-center.md`](adr/0044-command-center.md) — il Command Center: la terza
  identità, il tetto derivato dal socket, e l'impronta che suona quando una capability arriva
  senza la sua vista.
