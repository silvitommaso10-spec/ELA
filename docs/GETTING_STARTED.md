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

**Questa sezione è scritta prima della prova a mano** (2026-09-17), e qui non vale ancora la regola
della guida: ciò che «devi vedere» è quello che il codice stampa e che le misure sul PC hanno
mostrato (`docs/milestones/M12.4.md`, «Gli esiti»), non l'output di una sessione vera. Dopo la
prova, ogni blocco si sostituisce con l'output vero, e ciò che non torna si scrive.

Sul PC servono Windows 10 o 11, Tailscale acceso sulla stessa tailnet del Mac, [uv](https://docs.astral.sh/uv/),
il repository in `$HOME\ELA` con `uv sync --locked`, e un Python **3.12.4 o successivo**: su
Windows il nodo rifiuta una 3.12 più vecchia, perché lì la cartella del segreto non sarebbe
protetta (M12.4, dec. B).

### 1. Sul Mac: il Core anche sulla tailnet

```
tailscale ip -4
```

Stampa l'indirizzo del Mac sulla tailnet, `100.x.y.z`. Aggiungilo al `.env` del Mac, poi avvia il
Core nel primo terminale:

```
ELA_API_TAILNET_HOST=<ip tailnet del Mac>
```

```
uv run ela serve
```

Devi vedere `Application startup complete.` Il Core ascolta sul loopback **e** sulla tailnet; ogni
rotta resta dietro il token.

### 2. Sul PC: il Mac risponde

```powershell
Test-NetConnection <ip tailnet del Mac> -Port 8351
curl.exe -s -o NUL -w "%{http_code}`n" "http://<ip tailnet del Mac>:8351/health"
```

Devi vedere `InterfaceAlias : Tailscale`, `TcpTestSucceeded : True`, e poi `401`: il Core risponde
e rifiuta una richiesta senza token, che è ciò che deve fare (P5, 2026-09-17).

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

Devi vedere almeno una voce `it-IT`: sul PC di M12.4, `Microsoft Elsa Desktop | it-IT` (P3,
2026-09-15). Quel nome è il `<nome della voce>`. Le voci «OneCore» delle impostazioni di Windows
non compaiono qui, e il nodo non le può usare.

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
```

Tre cose da sapere prima di andare avanti:

- **`ELA_MODEL_ROUTES` deve essere uguale a quella del Mac.** Se il `.env` del Mac la imposta,
  copia quella riga identica in questo file; se non la imposta, non scriverla. Con due tabelle
  diverse ogni chiamata a un modello che il PC esegue fallisce la verifica sul Mac — il passo 8 lo
  mostra apposta.
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

Il codice si stampa una volta e vale dieci minuti. Sul PC:

```powershell
Set-Location $HOME\ELA
uv run ela node run --join
```

Incolla il codice quando compare `Enrollment code:` — non si vede mentre lo scrivi, ed è voluto.
Da lì il nodo ha la sua identità in `$HOME\.ela\node.json`, in una cartella con i permessi ristretti
a te, SYSTEM e Administrators; le volte dopo basta `uv run ela node run`. **Lascia aperta questa
finestra**: il nodo vive quanto lei, e chiuderla con la X lo ferma senza chiudere niente.

In una **seconda** finestra di PowerShell, il firewall:

```powershell
Get-NetFirewallApplicationFilter | Where-Object Program -like '*python*' | Get-NetFirewallRule | Select-Object DisplayName, Direction, Action, Enabled
```

Devi vedere nessuna riga, e non deve essere comparso nessun dialogo: il nodo chiama il Core, non
ascolta niente.

Sul Mac:

```
uv run ela device list
```

Devi vedere il PC accanto a `local`: sistema `WINDOWS`, disponibile, e **tre** tool — `core-echo`,
`model-complete`, `voice-speak`. Non `voice-speak-online`: sul PC la voce online non ha un
riproduttore, e il nodo non promette ciò che la macchina non sa fare.

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

Il primo `run` si ferma sul consenso; il secondo risponde `assigned`, con l'id dell'assegnazione:
lo step è del PC. **Il PC parla** — una frase di tre quarti di minuto, lunga apposta per le prove
di questo passo e del passo 7. Mentre parla:

1. **L'albero dei processi, sul PC**, nella seconda finestra:

   ```powershell
   function Show-Tree($id, $depth = 0) {
     Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" | ForEach-Object {
       ('  ' * $depth) + "$($_.ProcessId) $($_.Name)"; Show-Tree $_.ProcessId ($depth + 1)
     }
   }
   Get-CimInstance Win32_Process -Filter "Name='uv.exe'" | ForEach-Object { "$($_.ProcessId) uv.exe"; Show-Tree $_.ProcessId 1 }
   ```

   Devi vedere `powershell.exe` in fondo alla catena che parte da `uv.exe`, passando per `ela.exe`
   e per i `python.exe`: è la voce, figlia del nodo. Annota la catena così come esce.
2. **Il Core spento a metà**: `Ctrl-C` sul primo terminale del Mac, poi `uv run ela serve` di
   nuovo. Il nodo, quando ha finito di parlare, trova il Core spento o appena riacceso: aspetta,
   riprova, e consegna la busta che teneva.

Quando la frase è finita e il nodo ha consegnato, sul Mac:

```
uv run ela task run <id>
uv run ela audit tail --task <id> -n 20
```

Il `run` risponde `completed`. Nel registro, un `DEVICE_SELECTED` nomina il PC «with 25 points».
Con `--json` sullo stesso comando di `audit tail`, il `TOOL_EXECUTED` porta il `device_id` del PC —
quello di `ela device list` —, e il `DEVICE_SELECTED` porta fra i candidati anche i 20 punti di
`local`.

### 7. `Ctrl-C` sul nodo, mentre parla

Un secondo task, con lo stesso piano, fino a `assigned`:

```
uv run ela task create "fai parlare il PC, e interrompilo" --privacy TRUSTED
uv run ela task plan <id> --file docs/examples/speak-on-a-node.json
uv run ela task run <id>
uv run ela approvals
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

Quando il PC comincia a parlare, `Ctrl-C` **nella finestra del nodo**, poi nella stessa finestra:

```powershell
"exit=$LASTEXITCODE"
```

Devi sentire la voce fermarsi subito, vedere `exit=0`, e **nessuna** riga `Exception ignored` prima
del prompt. Il lavoro interrotto non si perde in silenzio: per il Core è un nodo che tace, e
l'assegnazione scade. Poi riavvia il nodo con `uv run ela node run`, per il passo 8.

### 8. Le prove negative

**Una nota non va al nodo.** `docs/examples/first-task.json` ha due step: un `core.echo`, che
viaggia, e un `workspace.write_note`, che no.

```
uv run ela task create "una nota" --privacy TRUSTED
uv run ela task plan <id> --file docs/examples/first-task.json
uv run ela task run <id>
```

Il primo `run` risponde `assigned`: l'echo è del PC. Aspetta qualche secondo che il nodo consegni,
poi:

```
uv run ela task run <id>
uv run ela audit tail --task <id> -n 10 --json
```

Il secondo `run` chiude l'echo e si ferma sul consenso della nota. Nel registro, il
`DEVICE_SELECTED` della nota sceglie `local`, «1 of 2 node(s) eligible», e fra i suoi candidati il
PC porta `"refusals": ["UNVERIFIABLE"]`: il verifier della nota rileggerebbe la workspace del Mac,
dove il PC non ha scritto niente. Il consenso della nota puoi negarlo con `ela task deny`.

**Una tabella di rotte diversa fa fallire la verifica.** Ferma il nodo con `Ctrl-C`, aggiungi al
`.env` del PC una riga che il Mac non ha, e riavvialo:

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
```

L'ultimo `run` risponde `assigned`. Quando il nodo ha consegnato — la risposta del modello, qualche
secondo —:

```
uv run ela task run <id>
uv run ela audit tail --task <id> -n 10 --json
```

Il PC ha risposto con la sua chiave e con il profilo della sua tabella, `cheap`; il Mac ricalcola la
rotta con la sua, che per `reasoning` dice `quality`, e la verifica fallisce: nel registro,
l'`EXECUTION_VERIFIED` porta `model.misrouted`, «the call did not go where the policy routes it».
È il difetto di due `.env` diversi, visto con la sua ragione. **Poi togli quella riga**: riscrivi il
`.env` del PC con il blocco del passo 4, e riavvia il nodo.

### 9. Che cosa annotare, per la spec (M12.4, dec. J)

Quattro numeri, presi durante i passi qui sopra, e **nessuno con un cronometro a mano**: ciascuno ha
già un registro che lo scrive. Si annotano nella forma di `.env.example` — la data, le due macchine,
il numero —, e vanno in `docs/milestones/M12.4.md`.

1. **Dal piazzamento alla consegna**, per `voice.speak` (passo 6) e per `core.echo` (la nota del
   passo 8). Nel JSON di `uv run ela audit tail --task <id> -n 20 --json`, la differenza fra il
   `created_at` del `DEVICE_SELECTED` e quello del `TOOL_EXECUTED` dello stesso step: tutti e due
   sono ore del Core, e il secondo è l'istante in cui il Core ha ricevuto la consegna. **È il
   piazzamento, non la presa**: il Core non scrive un evento quando il nodo prende il lavoro, quindi
   il numero comprende anche l'attesa del nodo fino alla sua richiesta successiva.
2. **Il long-poll attraverso la rete.** Nel primo terminale del Mac ogni richiesta del nodo stampa
   una riga, `"GET /nodes/work HTTP/1.1" 204` quando non c'era lavoro: una richiesta tenuta aperta
   per la finestra e chiusa dal Core, non dalla rete. Tiene se, a nodo fermo per qualche minuto, le
   righe continuano ad arrivare con `204`, e il nodo sul PC **non** esce con `3`. Annota quante
   richieste in quanti minuti, e se ne è caduta qualcuna.
3. **Il giro del nodo contro il TTL del battito.** Il nodo manda un battito per giro, e il Core
   scrive l'ora dell'ultimo in `last_seen_at`. `uv run ela device list --json` due volte, a qualche
   minuto di distanza, contando le righe `GET /nodes/work` stampate in mezzo: la differenza fra i due
   `last_seen_at` divisa per quel numero è il giro. Contro i 60 s di
   `ELA_DEVICE_HEARTBEAT_TTL_SECONDS`: su una macchina sola, in M12.3, era ~33 s.
4. **I punti di §17.** Nel `DEVICE_SELECTED` del passo 6: il PC «with 25 points» nel riassunto, e
   nel JSON i `points` e i `components` di tutti e due i candidati — `local` e il PC.

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
