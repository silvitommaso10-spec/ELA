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
| `<radice del PC>` | la cartella del PC dentro cui ELA può leggere e scrivere | la scegli tu, sul PC: una cartella che c'è, e che non contiene né sta dentro `$HOME\.ela` o `$HOME\ELA` (§17, passo 2) |

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
  write ELA_FS_ROOT, ELA_FS_SCOPE and ELA_TERMINAL_PROGRAMS in .env   # no default, and no start without
  uv run alembic upgrade head   # ELA does not migrate on start-up (ADR 0006)
  ela serve                     # ELA creates its database directory and workspace
```

Scrive **un solo file**, `.env`, con un token generato e permessi `0600`. Il token **non viene
stampato**: sta nel file, e da lì lo leggono sia ELA sia la CLI. Sotto al token trovi **le righe
obbligatorie** — `ELA_FS_ROOT`, `ELA_FS_SCOPE` e, da M13.2, `ELA_TERMINAL_PROGRAMS` —, commentate
con un esempio: ELA non ha un default per loro e non parte finché non le scrivi (qui sotto). Poi ogni
altra variabile commentata accanto al suo default: di quelle si tocca solo ciò che si vuole cambiare.

Se `.env` esiste già, `init` **non lo tocca**: dice quali variabili facoltative quel file non
imposta, e se manca `ELA_API_TOKEN`, o una delle righe obbligatorie, esce con `2` e dice che cosa
scrivere. Per vederlo, in una cartella vuota (`~/ELA` è la cartella in cui hai clonato ELA):

```
cd "$(mktemp -d)" && uv run --project ~/ELA ela init
uv run --project ~/ELA ela init; echo "exit $?"
```

La seconda volta il file c'è già e resta com'è, le righe obbligatorie non stanno fra quelle «con il
default di ELA», e l'uscita è `exit 2` con:

```
ela: .env does not set ELA_FS_ROOT, ELA_FS_SCOPE and ELA_TERMINAL_PROGRAMS, and ELA does not start without them: they have no default. Write them, for example:
    ELA_FS_ROOT=/Users/you/Documents
    ELA_FS_SCOPE=ELA
    ELA_TERMINAL_PROGRAMS=[]
The folder is yours: ELA does not create it and does not choose it.
The programs are one line of JSON, each relative to / — usr/bin/git is /usr/bin/git —, and [] is an answer: no program at all.
```

Fino a M13.1b `init` diceva che il token era «the only variable ELA requires» e, su questo stesso
file, «nothing required is missing»: se lo leggi ancora, stai girando su codice precedente.

Il database e il workspace stanno di default in `~/.ela/`. Per tenerli altrove, togli il commento
a `ELA_DB_URL` e `ELA_WORKSPACE_DIR` nel `.env` appena scritto.

### Due righe che **devono** essere scritte: la cartella dei tuoi file

Da M13.1 ELA legge e scrive file **fuori dalla sua workspace**, e il confine glielo dichiari tu.
Sono due righe, e **non hanno un default**: finché mancano, `ela serve` non parte e lo dice.

```
ELA_FS_ROOT=/Users/tu/Documenti
ELA_FS_SCOPE=ELA
```

`ELA_FS_ROOT` è una cartella **tua**, e ELA non la crea mai: se non c'è, ELA non parte e lo dice —
e se sparisce dopo l'avvio, ogni chiamata rifiuta con `fs.no_root` —, invece di inventarsi un posto
che non hai scelto. `ELA_FS_SCOPE` è la sola cartella dentro quella
radice che `fs.read` e `fs.write` possono toccare — con l'esempio qui sopra,
`/Users/tu/Documenti/ELA` — e **quella la crea la prima scrittura**, come la cartella delle note
dentro la workspace: la radice è tua, ciò che sta dentro lo scope è lavoro di ELA.

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

### Una riga che **deve** essere scritta: i programmi che ELA può lanciare

Da M13.2 ELA esegue anche programmi, e **quali** lo dichiari tu, in una riga di JSON senza default:

```
ELA_TERMINAL_PROGRAMS=[]
```

`[]` è una risposta, non un errore: nessun programma, e ogni richiesta di lanciarne uno è negata prima
di chiederti niente. Come dichiararne, e che cosa vuol dire, sta nella [§16](#16-il-terminale-la-prova-a-mano-di-m132).

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
approval    47fbce38-66ab-519c-b7dc-8cce4bd4a7f2
task        55ed2ab5-94aa-581f-9468-c4d247d9fe04
capability  workspace.write_note
what        Writes a note at a path inside the authorised notes folder.
risk        LOW
may go      LOCAL_ONLY
grant       1 use, within 60 minutes
expires     2026-09-07T09:12:00+00:00
step goal   scrivere la nota del primo task
declared    —
targets     workspace/notes/first-task.md
file        —
does        —
asks        workspace.write_note on workspace/notes/first-task.md for step 9c5b8f26-… (scrivere la nota del primo task): workspace.write_note requires an authorization: none was given
```

**Un blocco per domanda, e mostra tutto ciò che la domanda nomina**: è la condizione per cui una
superficie può offrirti un sì (M13.1, ADR 0045 §11). I trattini non sono buchi — `declared` è vuoto
perché questa capability non dichiara argomenti da mostrare, `file` e `does` perché la domanda non
parla di un file: quelli li vedrai in §15.

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

**Sul PC ELA si lancia con `uv run python -m ela.cli`, mai con `uv run ela`.** `uv sync` ricostruisce
`ela.exe`, il lanciatore dell'ambiente virtuale: è un file nuovo e senza firma, e con lo Smart App
Control acceso Windows lo blocca — «Un criterio di controllo dell'applicazione ha bloccato il file»,
os error 4551 (prova a mano di M13.3, 2026-09-26). `python -m ela.cli` fa girare lo stesso codice
attraverso l'interprete, che è firmato. **Non spegnere lo Smart App Control** per aggirarlo: una volta
spento, non si riaccende.

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

Da sapere prima di andare avanti:

- **`ELA_MODEL_ROUTES` deve essere uguale a quella del Mac.** Se il `.env` del Mac la imposta,
  copia quella riga identica in questo file; se non la imposta, non scriverla — nella prova il Mac
  non la impostava. Con due tabelle diverse ogni chiamata a un modello che il PC esegue fallisce la
  verifica sul Mac: è la seconda prova negativa del passo 8.
- **Nessun `ELA_NODE_PERFORMANCE`** e nessun tratto: chi parla lo decide ciò che le macchine
  leggono di sé, non una dichiarazione (passo 6).
- **La chiave è del PC** e non viaggia mai con il lavoro: il Core manda la chiamata, il nodo usa la
  sua. Il file sta in `$HOME\ELA` con i permessi della cartella del profilo — lo leggono i processi
  del tuo utente, lo stesso confine del segreto del nodo.
- **Da M13.3, una riga facoltativa: `ELA_FS_ROOT`**, la cartella in cui il nodo può leggere e scrivere
  per `fs.read` e `fs.write` (ADR 0048 §7). Sul nodo è **sola** — niente `ELA_FS_SCOPE`: lo scope resta
  uno, sul Core — e segue le regole della radice del Core: esiste, non è un link, non contiene e non
  sta dentro `$HOME\.ela` né `$HOME\ELA`. Senza la riga il nodo non dichiara i due tool, e lo dice
  all'avvio. La prova di M13.3 l'aggiunge al file in §17, passo 2.

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
uv run python -m ela.cli node run --join
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
ristretti a te, SYSTEM e Administrators; le volte dopo basta `uv run python -m ela.cli node run`.
**Lascia aperta questa finestra**: il nodo vive quanto lei, e chiuderla con la X lo ferma senza
chiudere niente. Mentre gira non stampa niente.

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
***Superato da M13.3*** (ADR 0048 §2): il Core batte per `local` prima di ogni piazzamento e a un
periodo di un terzo del TTL, quindi `local` resta disponibile fra un `run` e l'altro; resta `UNKNOWN`
soltanto il suo **stato**, che `local` non riporta.

### 6. Il Mac a batteria, e il PC che parla

**Stacca l'alimentatore del Mac**, e lascialo staccato fino alla fine della sezione. È ciò che
manda il lavoro al PC, ed è letto, non dichiarato: il Mac a batteria vale 20 punti (la rete),
il PC a corrente 25 (la rete 5, la corrente 10, libero 10). Con il Mac attaccato vincerebbe lui,
30 a 25, e parlerebbe il Mac. ***Superato da M13.3*** (ADR 0048 §13): il Core osserva lo stato di
`local` e la corrente vale 20 — il Mac a batteria e libero 30, il PC 35; attaccato, il Mac 50. Vince
chi vinceva, per la ragione giusta.

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
nodo si riavvia con `uv run python -m ela.cli node run`.

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
uv run python -m ela.cli node run
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

## 15. Il filesystem fuori dalla workspace: la prova a mano di M13.1

Da M13.1 ELA legge e scrive file **fuori dalla sua workspace**, e `fs.write` è la prima capability
`HIGH` che abbia mai avuto: chiede il permesso **ogni volta**, e nessuna policy potrà coprirla in
anticipo. Questa è la prova che quel confine tiene, e che la domanda dice la verità.

Due dei passi qui sotto **nessun test può farli al posto tuo**: il primo, perché il messaggio è
scritto per un essere umano e l'unico modo di sapere che si legge è leggerlo; e il quinto, perché
una difesa che nega *prima* della domanda si prova **dall'assenza del campanello**, non dalla
presenza del diniego.

I piani sono in [`examples/`](examples/) e la suite li manda a ELA byte per byte
(`tests/api/test_examples.py`): quello che lanci qui è quello che la suite ha visto.

### 1. ELA che non parte — il messaggio che devi leggere

Togli `ELA_FS_ROOT` dal `.env` (commentala) e prova ad avviare:

```
uv run ela serve
```

**Che cosa si deve vedere**, e leggilo per intero invece di guardare solo che è rosso:

```
ELA is not configured:
  ELA cannot start without the folder it may read and write outside its workspace: ELA_FS_ROOT
  and ELA_FS_SCOPE are missing. Write both lines in .env, for example:
      ELA_FS_ROOT=/Users/you/Documents
      ELA_FS_SCOPE=ELA
  They are one boundary and they are declared together: a scope without a root names nothing on
  disk, and ELA does not choose the folder for you (M13.1).
```

**Se non si vede così**: se ELA parte lo stesso, il `.env` non è quello che sta leggendo — ELA
legge quello della cartella da cui la lanci. Se il messaggio parla di una variabile sola, l'altra
era rimasta nell'ambiente della shell: `env | grep ELA_FS`.

Rimetti le due righe, con una cartella tua, e riavvia.

### 2. Un file nuovo, e la domanda che dice che lo **crea**

```
uv run ela task create "scrivi un file fuori dalla workspace"
uv run ela task plan <id> --file docs/examples/fs-write.json
uv run ela task run <id>
uv run ela approvals
```

**Che cosa si deve vedere**: il task si ferma in `WAITING_APPROVAL`, e `ela approvals` stampa **un
blocco** con tutto ciò che la domanda nomina — perché una superficie può offrirti un sì solo se ti
mostra a che cosa lo stai dicendo:

```
approval              9f2c1e30-0000-4000-8000-000000000001
task                  55ed2ab5-94aa-581f-9468-c4d247d9fe04
capability            fs.write
what                  Writes one file inside the authorised folder, outside the workspace.
risk                  HIGH
may go                LOCAL_ONLY
question expires      2026-09-22T10:14:00+00:00
grant if you say yes  1 use, within 60 minutes
step goal             lasciare un file nella cartella che ho dichiarato
declared              purpose: la prova a mano del filesystem
targets               ELA/prova.md
file                  /Users/tu/Documenti/ELA/prova.md
does                  creates a new file
asks                  fs.write on ELA/prova.md for step …: requires an authorization: none was given
```

Due scadenze, e ciascuna dice di chi è: `question expires` è fin quando la domanda si può ancora
rispondere, `grant if you say yes` è quanto vive il permesso che il sì farà nascere — un uso, per
un'ora col default di `ELA_AUTHORIZATION_TTL_SECONDS`.

Le due righe da guardare sono `file` e `does`: il **percorso risolto per esteso** —
`/Users/tu/Documenti/ELA/prova.md`, non `ELA/prova.md` — e che cosa il sì farà. Quei due fatti li
legge il disco, non il piano.

```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
cat /Users/tu/Documenti/ELA/prova.md
```

**E l'audit dice con quale sì** (da M13.1b). Il sì ha fatto nascere un grant di un uso solo, e la
scrittura lo **spende**: il risultato e l'audit lo nominano.

```
uv run ela task results <id> --json | grep authorization_id
uv run ela audit tail --task <id> -n 20 --json | grep -E '"(event_type|authorization_id|uses)"'
```

**Che cosa si deve vedere**: le due righe del risultato — `STARTED`, scritta prima di scrivere, e
`SUCCEEDED` — portano **lo stesso** `authorization_id`; in `TOOL_EXECUTED` c'è **quello**, lo stesso di
`AUTHORIZATION_GRANTED`, e `"uses": 1`. Se vedi `null`, stai girando su codice precedente a M13.1b:
quella versione lasciava il grant intatto per un'ora, e l'audit non sapeva dire con quale
autorizzazione il file era stato scritto.

**Se non si vede così**: se il task finisce `DENIED` senza chiedere niente, il percorso del piano
non è dentro `ELA_FS_SCOPE` — è il passo 5, ma su un piano che doveva passare. Se il risultato è
`fs.no_root`, la radice non esiste: creala tu, ELA non lo fa.

### 3. Lo stesso piano una seconda volta — ELA non chiede, rifiuta

Rilancia **lo stesso file**, senza toccarlo:

```
uv run ela task create "riscrivi lo stesso file"
uv run ela task plan <id> --file docs/examples/fs-write.json
uv run ela task run <id>
```

**Che cosa si deve vedere**: il task va in `FAILED` **senza chiedere niente**, e la riga `reason`
dice perché:

```
outcome         failed
reason          fs.overwrite_mismatch: 'ELA/prova.md' was declared as a new file and something is there now
state           FAILED
steps executed  d1b7c4a2-9e35-4f18-8c60-000000000001
```

```
uv run ela approvals                   # «nothing to show»
uv run ela audit tail -n 5             # nessun APPROVAL_REQUESTED, nessun BELL_RUNG
cat /Users/tu/Documenti/ELA/prova.md   # il file di prima, intatto
```

**Perché è questo e non una domanda.** Il piano dichiara `"overwrite": false`, cioè «lì non c'è
niente», e adesso qualcosa c'è: la chiamata verrebbe rifiutata nell'istante in cui girasse. **Una
domanda si compone solo per ciò che, approvato adesso, riuscirebbe sul disco di adesso** — non si
chiede a nessuno di approvare ciò che ELA sa già che rifiuterà, e non si sveglia nessuno per
questo. Il confronto lo fa la stessa funzione che rifiuterebbe davvero: un fatto, una definizione,
un posto.

`steps executed` porta l'**id dello step**, non un conteggio: lo step è stato tentato e si è
fermato prima di toccare il disco, ed è quello che il suo id lì dentro significa.

**Il messaggio dice «declared» e non «approved»**, ed è deliberato: qui nessuno ha approvato
niente, quindi «approved» sarebbe una diagnosi falsa. La stessa frase nasce anche in un secondo
posto — quando il mondo si muove **fra il sì e la scrittura** — e lì ciò che è stato approvato *è*
ciò che il piano aveva dichiarato, perché la domanda nasce solo quando dichiarazione e disco
concordano. Una frase sola, vera in tutti e due i posti.

**Per sovrascrivere davvero** basta che il piano dichiari il vero. Copia il file e cambia una riga:

```
sed 's/"overwrite": false/"overwrite": true/' docs/examples/fs-write.json > /tmp/fs-overwrite.json
uv run ela task create "sovrascrivi davvero"
uv run ela task plan <id> --file /tmp/fs-overwrite.json
uv run ela task run <id>
uv run ela approvals
```

**Che cosa si deve vedere**: adesso la domanda c'è, e la riga `does` dice **`overwrites a file that
is already there`** invece di `creates a new file`. È l'unico modo di vedere con gli occhi che la
domanda racconta il mondo e non il piano — e che la frase è della capability: una lettura, al passo
4, dirà `reads a file that is there` e non parlerà mai di sovrascrivere.

```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

**Se non si vede così**: se al primo rilancio compare una domanda invece del `FAILED`, stai girando
su codice precedente alla riparazione di M13.1 — quella versione chiedeva e poi rifiutava, che è il
difetto che la prova a mano ha trovato.

### 4. Rileggere il file, e dove finiscono i byte

```
uv run ela task create "rileggi il file"
uv run ela task plan <id> --file docs/examples/fs-read.json
uv run ela task run <id>
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
uv run ela task results <id>
```

**Che cosa si deve vedere**: il contenuto del file **nel risultato**. E nell'audit no:

```
uv run ela audit tail -n 10
```

Il percorso c'è, **il contenuto no** — un log append-only non si redige più — e nemmeno la
dimensione: quella sta nel risultato, accanto al contenuto (`bytes` nel blocco di `ela task
results`). Fino a M13.1b questa riga diceva «la dimensione c'è»: non c'è mai stata. Una lettura che
**fallisce**, invece, porta le dimensioni nel suo errore, per scelta (ADR 0045 §8).

### 5. Fuori dallo scope: il campanello che **non** suona

Questo è il passo che si prova da un'assenza.

```
uv run ela task create "prova a scrivere fuori dallo scope"
uv run ela task plan <id> --file docs/examples/fs-outside-the-scope.json
uv run ela task run <id>
```

**Prima di lanciare, il campanello deve poter suonare.** Un'assenza vale come prova solo se
l'assenza è di qualcosa che altrimenti ci sarebbe: senza `ELA_NTFY_TOPIC` nel `.env` ELA non suona
**mai**, e questo passo non proverebbe niente. Configuralo come dice il §13, poi conta i rintocchi
prima e dopo:

```
uv run ela audit tail -n 200 --json | grep -c BELL_RUNG
```

Tieni da parte il numero. Poi lancia, e ricontalo.

**Che cosa si deve vedere**: il task va in `DENIED` **subito**, la riga `reason` dice perché, e poi
tre assenze:

```
outcome  denied
reason   targets ['altrove/non-deve-esistere.md'] of fs.write are not within scope ['ELA']
```

```
uv run ela approvals                            # «nothing to show»: nessuno è stato interpellato
uv run ela audit tail -n 200 --json | grep -c BELL_RUNG   # **lo stesso numero di prima**
ls /Users/tu/Documenti/altrove                  # non esiste
```

E se hai l'iPhone arruolato (§13), **il telefono non deve aver ricevuto niente**. Il conteggio dei
`BELL_RUNG` è ciò che rende la prova una prova: se è salito, il rifiuto è arrivato *dopo* la
domanda invece che prima, e non si chiede a qualcuno di approvare ciò che sarebbe negato comunque.

Nell'audit la decisione porta `rule: SCOPE`:

```
uv run ela audit tail -n 5 --json | grep -o '"rule": "[A-Z_]*"'
```

**Se non si vede così**: se compare una domanda, controlla che il percorso del piano sia davvero
fuori da `ELA_FS_SCOPE` — con lo scope `ELA` il piano d'esempio scrive in `altrove/`. Se la regola
dice `ALLOW_WITHIN_SCOPE`, stai girando su codice precedente a M13.1.

### 6. La stessa domanda dal telefono e dal browser — e quando il telefono non risponde

Qui si vedono **le due metà** della regola: una superficie può rispondere a una domanda solo se
mostra tutto ciò che quella domanda nomina.

**La metà che risponde.** I piani d'esempio nascono `LOCAL_ONLY`, che è il default, e a quel
livello il companion **non vede** percorso né sovrascrittura: per il tetto di M12.5 la pagina porta
solo id, stato, capability e rischio, e dice di rispondere dal Mac. Per dare la domanda al telefono
il task va creato più largo:

```
uv run ela task create "scrivi dal telefono" --privacy TRUSTED
uv run ela task plan <id> --file docs/examples/fs-write.json
uv run ela task run <id>
```

(Se `ELA/prova.md` esiste già dal passo 2, cancellalo o cambia il `path` nel piano: altrimenti il
passo 3 ti ha già insegnato che cosa succede.)

**Che cosa si deve vedere**: con l'iPhone aperto sulla pagina del companion (§13) e il Command
Center aperto sul Mac (§14), **tutt'e due mostrano il percorso risolto e che cosa fa il sì**, e
tutt'e due offrono i pulsanti. Rispondi dal telefono: il task riparte nella stessa richiesta.

**La metà che non risponde.** Rifai lo stesso giro **senza** `--privacy TRUSTED`: la pagina del
telefono mostra la domanda ma non il percorso, non i pulsanti, e dice che il contenuto resta sul
Mac. **Non è un difetto: è la regola che funziona.** Una superficie che non mostra ciò a cui
direbbe sì non risponde, e non c'è nessun elenco di dispositivi da tenere aggiornato — il giorno in
cui una domanda imparerà un fatto nuovo, ogni superficie o lo mostra o smette di offrire il sì.

## 16. Il terminale: la prova a mano di M13.2

> **Scritta con la SPEC di M13.2**, allineata alle sue decisioni 1–16, a M13.1b (ADR 0046) e alle
> tre domande decise alla ripresa. **I blocchi della riga di comando vengono dall'uscita vera** di
> una sessione con due processi del 2026-09-24 — un `ela serve` isolato e la CLI —: ciò che dipende
> dalla macchina — la cartella, il timeout, gli id — è scritto come lo vedrai tu, e dove l'uscita è
> lunga le righe tolte sono un `…`. Quelli del telefono e del Command Center li scrive la tua prova.
> L'ADR è [0047](adr/0047-terminal.md).

Da M13.2 ELA esegue un programma su questo Mac e ne riporta l'uscita. `terminal.run` è `HIGH`, come
`fs.write`: chiede **ogni volta**, e nessuna policy potrà coprirlo in anticipo.

**Prima di cominciare, una frase da leggere per intero.** Il confine del terminale è **quali
programmi**, e soltanto quello. Un programma ammesso gira con i tuoi diritti: scrive dove tu scrivi,
legge ciò che tu leggi, e può lanciarne altri. La cartella di lavoro è il posto da cui parte, non
quello in cui resta — il confine di §15 vale per `fs.read` e `fs.write`, che ELA esegue da sé, e un
programma non lo eredita. Il giudizio sugli argomenti di ogni chiamata è tuo, a ogni domanda.

Quattro dei passi qui sotto **nessun test può farli al posto tuo**: il primo, perché il messaggio è
scritto per un essere umano; il terzo, perché una difesa che nega *prima* della domanda si prova
**dall'assenza del campanello**; il quinto, perché due processi che muoiono davvero si vedono solo
con due terminali; e l'ottavo, perché che cosa fa Safari mentre una richiesta resta aperta lo sa solo
Safari.

I piani sono in [`examples/`](examples/) e la suite li manda a ELA byte per byte
(`tests/api/test_examples_terminal.py`). Presuppongono §15 fatta: la cartella dello scope — `ELA/` dentro la
tua radice — **deve esistere**, perché è la cartella da cui i programmi partono, e ELA non la crea.

### 1. ELA che non parte — il messaggio che devi leggere

Senza `ELA_TERMINAL_PROGRAMS` nel `.env`:

```
uv run ela serve
```

**Che cosa si deve vedere**: ELA non parte, e il messaggio nomina la variabile, dice la riga da
scrivere e dice che `[]` è una risposta ammessa — «nessun programma» — e non un errore:

```
ela: ELA is not configured:
  ELA cannot start without the programs terminal.run may launch: ELA_TERMINAL_PROGRAMS is missing. Write it in .env as one line of JSON, each program relative to /, for example:
      ELA_TERMINAL_PROGRAMS=["usr/bin/git"]
  or, for no program at all — an answer, not an error:
      ELA_TERMINAL_PROGRAMS=[]
```

Leggilo per intero: se una frase ti costringe a rileggere, è un difetto da riportare.

E `ela init`, sullo stesso `.env`, lo dice nello stesso modo in cui dice le due righe di §15:

```
uv run ela init; echo "exit $?"
```

**Che cosa si deve vedere**: il file c'è già e non si tocca; `ELA_TERMINAL_PROGRAMS` è nominata fra
le righe che mancano — **non** fra quelle «con il default di ELA» —, e `exit 2`:

```
ela: .env does not set ELA_TERMINAL_PROGRAMS, and ELA does not start without it: it has no default. Write it, for example:
    ELA_TERMINAL_PROGRAMS=[]
The programs are one line of JSON, each relative to / — usr/bin/git is /usr/bin/git —, and [] is an answer: no program at all.
```

**Se non si vede così**: se ELA parte lo stesso, la variabile è rimasta nell'ambiente della shell —
`env | grep ELA_TERMINAL`.

### 2. Dichiarare i programmi della prova

Nel `.env`, **una riga sola**, in JSON:

```
ELA_TERMINAL_PROGRAMS=["bin/echo","usr/bin/seq","usr/bin/time","usr/bin/printf","usr/bin/env"]
```

**I programmi si scrivono senza la barra iniziale**: sono percorsi **relativi alla radice `/`**, come
`ELA_FS_SCOPE` è relativo a `ELA_FS_ROOT` — `bin/echo` è `/bin/echo`. È la stessa grammatica dello
scope di §15, e per questo il Guardian li confronta come confronta i tuoi percorsi. Nei piani si
scrivono uguali. **ELA non usa mai il `PATH`.**

ELA li controlla all'avvio e si ferma con una frase se uno non va: uno scritto con la barra o con un
`..`, una cartella — che ammetterebbe tutto ciò che contiene —, o un file che non si esegue. E
nient'altro. **Non rifiuta gli interpreti**, nemmeno il Python con cui ELA stessa gira, e non è una
dimenticanza: ammettere `sh`, `python`, `env`, `xargs` o `find` significa ammettere qualunque cosa, e
la difesa è la domanda che ELA ti fa a ogni uso. Una lista di interpreti vietati sarebbe incompleta
dal primo giorno. **Una voce che non c'è non ferma l'avvio**: ogni domanda per lei è rifiutata prima
di nascere, con `terminal.no_program`.

**Un link dichiarato è una scelta tua.** `ELA_TERMINAL_PROGRAMS=["opt/homebrew/bin/rg"]` dichiara il
link, e la domanda ti mostra il file a cui porta oggi; se dopo l'avvio qualcuno lo ripunta — `brew
upgrade`, per esempio — ELA rifiuta con `terminal.program_changed` prima di chiederti niente.

**`/usr/bin/git` non è git.** È lo shim di `xcode-select`: un file vero, che esegue il git degli
strumenti di Xcode — lo stesso file, con 77 altri nomi, è `/usr/bin/make`, `/usr/bin/clang`,
`/usr/bin/python3`. Dichiararlo si può, e la domanda nominerà `/usr/bin/git`; ciò che quel file
sceglie di eseguire è comportamento suo. Se vuoi che la domanda nomini ciò che gira davvero,
dichiara il percorso che stampa `xcrun --find git`, senza la barra iniziale — su un Mac con i soli
Command Line Tools, `Library/Developer/CommandLineTools/usr/bin/git`.

**Due di questi programmi lanciano altri programmi**: `/usr/bin/time` esegue ciò che gli passi come
argomento, e `/usr/bin/env` pure. Dichiararli allarga il confine a tutto ciò che possono lanciare.
Sono qui perché la prova ha bisogno di un nipote (passo 5) e di un ambiente da stampare (passo 7):
**toglili quando hai finito** (passo 9).

Riavvia ELA.

### 3. Un programma non dichiarato — il campanello che **non** suona

Si comincia dall'assenza, finché il conteggio è pulito. **Il campanello deve poter suonare**: senza
`ELA_NTFY_TOPIC` ELA non suona mai, e questo passo non proverebbe niente (§13). Conta i rintocchi:

```
uv run ela audit tail -n 200 --json | grep -c BELL_RUNG
```

Tieni da parte il numero, poi:

```
uv run ela task create "un programma che non ho dichiarato"
uv run ela task plan <id> --file docs/examples/terminal-not-declared.json
uv run ela task run <id>
```

**Che cosa si deve vedere**: `DENIED` **subito**, con la riga `reason` che nomina `usr/bin/whoami` e
lo scope — scritto senza la barra iniziale —:

```
outcome         denied
reason          targets ['usr/bin/whoami'] of terminal.run are not within scope ['bin/echo', 'usr/bin/seq', 'usr/bin/time', 'usr/bin/printf', 'usr/bin/env']
state           DENIED
```

poi due assenze, e il nome del confine che ha rifiutato:

```
uv run ela approvals                                        # «nothing to show»
uv run ela audit tail -n 200 --json | grep -c BELL_RUNG     # lo stesso numero di prima
uv run ela audit tail -n 5 --json | grep -o '"rule": "[A-Z_]*"'   # "rule": "SCOPE"
```

E l'iPhone, se è arruolato, non ha ricevuto niente.

**Se non si vede così**: se compare una domanda, `usr/bin/whoami` è finito nella riga del passo 2.

### 4. Un programma che gira, e dove finiscono le sue parole

```
uv run ela task create "far girare echo"
uv run ela task plan <id> --file docs/examples/terminal-echo.json
uv run ela task run <id>
uv run ela approvals
```

**Che cosa si deve vedere**: il task si ferma in `WAITING_APPROVAL`, e il blocco di `ela approvals`
porta, oltre a ciò che porta per `fs.write`, **il programma per esteso** e il file a cui porta, **gli
argomenti uno per uno** con i loro confini visibili, **la cartella di lavoro risolta**, **il
timeout** e **il codice atteso**:

```
targets               bin/echo
program               /bin/echo
runs                  /bin/echo
arguments             ["la parola di prova è", "girasole-7431"]
folder                /Users/tu/Documenti/ELA
timeout               120 s
expects exit          0
does                  runs this program from this folder: it can read and change whatever you can, and ELA sees what it prints, not what it changes
```

Guarda gli argomenti: sono **due**, e il primo contiene degli spazi — una lista, non una riga di
shell. La riga del bersaglio si chiama `program` perché così lo chiama il tool: per `fs.write` si
chiama `file`.

E leggi la frase della domanda: dice che il programma parte da quella cartella e **può leggere e
cambiare tutto ciò che puoi tu**. La cartella di lavoro non è un confine: è il posto da cui il
programma parte, non quello in cui resta.

```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
uv run ela task results <id>
```

**Che cosa si deve vedere**: `la parola di prova è girasole-7431` nell'uscita, il codice `0`, e per
ogni flusso quanto è stato tenuto e quanto c'era:

```
  args            ["la parola di prova è", "girasole-7431"]
  argument_count  2
  ended           exited
  exit_code       0
  signal          —
  stdout  shown 36 of 36 bytes
  la parola di prova è girasole-7431
  stderr  shown 0 of 0 bytes
```

**E nell'audit no**:

```
uv run ela audit tail -n 200 --json | grep -c girasole-7431     # 0
uv run ela audit tail -n 200 --json | grep -c bin/echo          # più di 0: il programma c'è
```

Il programma è nell'audit — è ciò che la decisione ha giudicato —; gli argomenti e l'uscita no: sono
contenuto tuo, e un log append-only non si redige più. **I numeri sì**: il numero degli argomenti, il
codice d'uscita e i byte di ogni flusso, e sono soltanto numeri:

```
uv run ela audit tail --task <id> -n 20 --json | grep -A 12 '"numbers"'
```

**E l'audit dice con quale sì**, come per `fs.write` da M13.1b:

```
uv run ela task results <id> --json | grep authorization_id
uv run ela audit tail --task <id> -n 20 --json | grep -E '"(event_type|authorization_id|uses)"'
```

**Che cosa si deve vedere**: le due righe del risultato (`STARTED` e `SUCCEEDED`) portano **lo stesso**
`authorization_id`, in `TOOL_EXECUTED` c'è **quello** — lo stesso di `AUTHORIZATION_GRANTED` — e
`"uses": 1`.

**Se non si vede così**: se il task fallisce prima della domanda con un codice di percorso, la
cartella `ELA/` non c'è — §15, o creala tu.

### 5. Il tempo che scade, e il nipote che deve morire — due volte

**La prima volta lo ferma il timeout.** Abbassalo, perché il default è di due minuti, e riavvia:

```
ELA_TERMINAL_TIMEOUT_SECONDS=10
```

```
uv run ela task create "dormire troppo"
uv run ela task plan <id> --file docs/examples/terminal-timeout.json
uv run ela task run <id>
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

In **un terzo terminale** — il primo è quello di `ela serve`, il secondo quello dei comandi —,
mentre aspetti, guarda i due processi — `time` è il figlio, `sleep` il
nipote:

```
pgrep -fl "sleep 600"
```

**Che cosa si deve vedere**: dopo una decina di secondi il task va in `FAILED` con
`terminal.timeout`:

```
reason          terminal.timeout: /usr/bin/time was still running after 10 s: ELA stopped its process group
state           FAILED
```

e **subito dopo**:

```
pgrep -fl "sleep 600"          # niente: il nipote è morto con il figlio
uv run ela task results <id>   # l'uscita raccolta fino a lì, con shown e total, e ended: stopped_by_ela
```

**La seconda volta lo ferma ELA che si ferma.** Togli la riga del timeout, riavvia, rilancia lo
stesso giro in un task nuovo, e **mentre il comando gira** premi Ctrl-C nel terminale di
`ela serve`. Il comando sta in un gruppo di processi suo, quindi il Ctrl-C non lo raggiunge da solo:
è ELA, fermandosi, a doverlo uccidere — al segnale, non allo scadere dei due minuti.

```
pgrep -fl "sleep 600"          # niente, anche questa volta, e subito
```

Il `task run` dell'altro terminale torna **subito**, senza aspettare i due minuti:

```
reason          terminal.stopped: ELA was stopping while /usr/bin/time ran, and stopped its process group
state           FAILED
```

`terminal.stopped` e non `terminal.timeout`: il tempo non era scaduto, era ELA che si fermava. Nella
sessione del 2026-09-24 il gruppo era vuoto 0,03 s dopo il segnale. Poi riavvia ELA e guarda il
risultato del task: `ended: stopped_by_ela`, e l'uscita raccolta fino a lì.

```
uv run ela task results <id>
```

**Se non si vede così**: se `sleep 600` è ancora vivo, ELA ha ucciso il figlio e non il suo gruppo —
è un difetto, e va riportato con che cosa `pgrep` mostra. Uccidilo a mano (`pkill -f "sleep 600"`).

### 6. Un'uscita più lunga del tetto

```
uv run ela task create "contare fino a centomila"
uv run ela task plan <id> --file docs/examples/terminal-long-output.json
uv run ela task run <id>
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
uv run ela task results <id>
```

**Che cosa si deve vedere**: sopra, quanto è stato tenuto e quanto c'era; poi le prime righe (`1`,
`2`, `3`…), **una riga della CLI** che dice **dove** sta il taglio — dopo quanti byte, e quanti ne
mancano —, e le ultime (`…99999`, `100000`):

```
  stdout  shown 65536 of 588895 bytes
  1
  2
  …
  6775
  — cut after 32768 bytes: 523359 bytes not shown —

  94540
  …
  99999
  100000
```

Quella riga è della superficie, non del comando: nei dati non c'è nessun testo inventato, il taglio lo
dicono i numeri. L'ultima riga della testa e la prima della coda possono essere pezzi di un numero:
il taglio cade sul byte, e lo dice.

### 7. Che cosa riceve un programma: l'ambiente, e i caratteri che non si stampano

Prima **esporta una variabile finta** nella shell da cui lanci ELA, e riavvia da lì:

```
export ELA_API_TOKEN_DI_PROVA=non-deve-arrivare
uv run ela serve
```

Poi, dall'altro terminale:

```
uv run ela task create "l'ambiente del figlio"
uv run ela task plan <id> --file docs/examples/terminal-env.json
uv run ela task run <id>
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
uv run ela task results <id>
```

**Che cosa si deve vedere**: `PATH`, `HOME`, `TMPDIR`, `LANG`, e **nient'altro**: né
`ELA_API_TOKEN_DI_PROVA`, né `SSH_AUTH_SOCK`, né `VIRTUAL_ENV`:

```
  args            []
  stdout  shown 129 of 129 bytes
  PATH=/usr/bin:/bin:/usr/sbin:/sbin
  HOME=/Users/tu
  TMPDIR=/var/folders/…/T
  LANG=C.UTF-8
```

**Che `SSH_AUTH_SOCK` manchi è voluto, e ha un prezzo**: un `git push` o un `git pull` via ssh da
`terminal.run` non funzionano. L'agente ssh è un'autorità che non hai dato a quel comando.

E i caratteri di controllo:

```
uv run ela task create "una parola rossa"
uv run ela task plan <id> --file docs/examples/terminal-escape.json
uv run ela task run <id>
uv run ela approvals
```

**Che cosa si deve vedere, già qui**: l'argomento di `printf` nella domanda con le sue barre
rovesciate **scritte**, e il tuo terminale che non cambia. Poi:

```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
uv run ela task results <id>
```

**Che cosa si deve vedere**: il carattere ESC **reso visibile** — la parola `ROSSO` fra due sequenze
che si leggono come testo —, e il tuo terminale che **non** diventa rosso:

```
  args            ["prima \\033[31mROSSO\\033[0m dopo\\n"]
  stdout  shown 26 of 26 bytes
  prima \x1b[31mROSSO\x1b[0m dopo
```

Nella domanda e fra gli argomenti la barra rovesciata che hai scritto nel piano è raddoppiata, perché
una barra scritta e un carattere di controllo non si leggano uguali; nell'uscita `\x1b` è il
carattere ESC che `printf` ha stampato. Una superficie che mostra ciò a cui dici sì non può essere
riscritta da ciò che mostra.

**Se non si vede così**: se la parola è rossa, la CLI ha stampato il carattere crudo — è un difetto.

### 8. La stessa domanda dal telefono, e il telefono che aspetta

Con l'iPhone sulla pagina del companion (§13) e il Command Center aperto (§14):

```
uv run ela task create "echo dal telefono" --privacy TRUSTED
uv run ela task plan <id> --file docs/examples/terminal-echo.json
uv run ela task run <id>
```

**Che cosa si deve vedere**: **tutt'e due** mostrano il programma per esteso, la cartella risolta e gli
argomenti come lista, e offrono i pulsanti. Rispondi dal telefono.

Poi il telefono che aspetta. Scrivi `ELA_TERMINAL_TIMEOUT_SECONDS=30` nel `.env`, riavvia, e rifai
il giro con il piano del passo 5, sempre `--privacy TRUSTED`. Il sì dal telefono fa ripartire il task
**nella stessa richiesta**, quindi il telefono **aspetta** mentre il comando gira. **Guarda che cosa
mostra Safari** per quei trenta secondi, e che cosa mostra alla fine. È il passo che nessuno ha mai
provato: fino a oggi nessuna capability durava più di una frase letta ad alta voce. Poi togli la
riga del timeout e riavvia.

**Se non si vede così**: se il telefono mostra un errore mentre il comando sta ancora girando, o
dopo, annota che cosa dice e dopo quanti secondi: è un difetto da riparare con il suo test prima.

### 9. Un programma cambiato, o sparito, mentre ELA gira — e la pulizia

ELA fissa l'identità di ogni programma dichiarato **all'avvio**, e la riconfronta prima di chiedere e
prima di eseguire. Per vederlo serve un programma che puoi cambiare tu:

```
mkdir -p ~/ela-prova/bin && cp /bin/echo ~/ela-prova/bin/eco
```

Aggiungi `"Users/tu/ela-prova/bin/eco"` a `ELA_TERMINAL_PROGRAMS` — senza la barra iniziale —,
riavvia, e fai un piano che lo usa:

```
sed 's#"bin/echo"#"Users/tu/ela-prova/bin/eco"#' docs/examples/terminal-echo.json > /tmp/eco.json
uv run ela task create "l'eco che cambierà"
uv run ela task plan <id> --file /tmp/eco.json
uv run ela task run <id>                 # la domanda nasce: non rispondere ancora
```

Adesso, **senza riavviare ELA**, sostituisci il programma, e rilancia lo stesso piano in un task
nuovo:

```
cp /bin/ls ~/ela-prova/bin/eco
uv run ela task create "l'eco cambiato"
uv run ela task plan <id> --file /tmp/eco.json
uv run ela task run <id>
```

**Che cosa si deve vedere**: `FAILED` **senza domanda**, con `terminal.program_changed` e una frase
che dice di riavviare ELA per accettare il programma nuovo. E se adesso approvi la domanda del primo
task e lo rilanci, il rifiuto arriva **prima dell'esecuzione**, con lo stesso codice: il file a cui
avevi detto sì non è più quello.

**Poi sparito.** Riavvia ELA, che fissa il programma com'è adesso, apri una domanda con lo stesso
piano senza rispondere, e **cancella il file**:

```
uv run ela task create "l'eco che sparirà"
uv run ela task plan <id> --file /tmp/eco.json
uv run ela task run <id>                 # la domanda nasce: non rispondere ancora
rm ~/ela-prova/bin/eco
uv run ela task create "l'eco sparito"
uv run ela task plan <id> --file /tmp/eco.json
uv run ela task run <id>
```

**Che cosa si deve vedere**: `FAILED` **senza domanda**, con **`terminal.program_gone`** — non
`terminal.program_changed`: il file non è un altro, non c'è — e una frase che dice il fatto:

```
'/Users/tu/ela-prova/bin/eco' was there when ELA started and is not there now: nothing is left to run
```

E se approvi la domanda aperta e rilanci quel task, il rifiuto arriva **prima dell'esecuzione**, con
lo stesso codice. Il terzo momento — un programma che sparisce *mentre* gira, come un
disinstallatore che si cancella da sé — non si prova a mano: lo afferma un test dell'executor, e il
passo finisce `FAILED` per verifica, con `terminal.program_gone` e l'uscita del programma nel
risultato, perché ELA non può più confermare che ciò che ha girato fosse il programma dichiarato.

**La pulizia**, che fa parte della prova: togli `usr/bin/time`, `usr/bin/env` e
`Users/tu/ela-prova/bin/eco` da `ELA_TERMINAL_PROGRAMS` (o scrivi `[]`), cancella `~/ela-prova`, e
riavvia.

## 17. L'azione che viaggia: la prova a mano di M13.3

> **Nata come bozza con la SPEC di M13.3, e resa definitiva con l'implementazione (ADR 0048).** Le
> righe della domanda sono quelle che `ela approvals` stampa: `machine`, il percorso, `does`, `disk`.
> **L'ordine è parte della prova**: il battito prima di tutto, perché una misura presa mentre il Mac
> risulta non disponibile misura una gara in cui un nodo non compete. **Un comando per blocco**, tranne
> i cicli della misura del passo 4, che sono una riga per blocco e non un comando (decisione 11).

Il Core resta su questo Mac, il nodo sul PC, la tailnet in mezzo: la preparazione è quella di §12,
passi 1–5. **Ogni uscita che è una misura va in un file**, in `~/Downloads` sul Mac; quelle del PC si
prendono in `$HOME\Downloads` e si copiano sul Mac. Il nome del file è nel comando. I comandi non
portano commenti: con la configurazione di default di zsh un `#` incollato non è un commento, e
diventa un argomento.

### 1. Il Mac che resta disponibile

Nel primo terminale, il Core con il codice di M13.3:

```
uv run ela serve
```

Nel secondo, **senza lanciare nessun task**:

```
uv run ela device list --json > ~/Downloads/m13.3-battito-1.json
```

```
sleep 90
```

```
uv run ela device list --json > ~/Downloads/m13.3-battito-2.json
```

**Che cosa si deve vedere**: nella riga di `local`, `"available": true` in tutti e due i file. La
disponibilità la deriva il Core nell'istante della lettura dall'ultimo battito, quindi `true` nel
secondo file vuol dire che nei novanta secondi qualcuno ha battuto per il Mac, e nessun `run` l'ha
fatto. Prima di M13.3 il secondo diceva `false`: novanta secondi sono più dei sessanta del TTL.
**Finché questo passo non passa, il passo 4 non si comincia.**

### 2. Il PC con una radice

Sul PC, il nodo fermo con `Ctrl-C`; poi una riga in più nel suo `.env` — la cartella deve esistere, e
non deve contenere né stare dentro `$HOME\.ela`, dove il nodo tiene il segreto, o `$HOME\ELA`, dove
stanno il codice e il `.env` del nodo:

```powershell
[IO.File]::AppendAllText("$HOME\ELA\.env", "`nELA_FS_ROOT=<radice del PC>`n")
```

```powershell
uv run python -m ela.cli node run
```

Con il modulo e non con il lanciatore: dopo un `uv sync` lo Smart App Control blocca `ela.exe` (§12).

Sul Mac:

```
uv run ela device list --json > ~/Downloads/m13.3-pc-con-radice.json
```

**Che cosa si deve vedere**: nella riga del PC, fra i tool, `fs-read` e `fs-write`, e `power_source`
`AC` — non `UNKNOWN`: la lettura dell'alimentazione del PC è quella che il blocco B del passo 4 pesa.
Senza la riga nel `.env` i due tool non ci sono, e il nodo lo dice all'avvio
con una riga («No ELA_FS_ROOT here…»).

### 3. Un file scritto sul PC, e riletto

**Stacca l'alimentatore del Mac**: con il Mac a batteria vince il PC (§12, passo 6).

```
uv run ela task create "un file sul PC" --privacy TRUSTED
```

```
uv run ela task plan <id> --file docs/examples/fs-write.json
```

```
uv run ela task run <id>
```

```
uv run ela approvals
```

**Che cosa si deve vedere**: la domanda nomina **il PC** nella riga `machine` — il suo nome e l'inizio
del suo id —, il percorso `ELA/prova.md` come il piano lo scrive nella riga `file`, in `does` «creates a
new file: the plan says nothing is there», e nella riga `disk` che ELA non ha guardato quel disco e che
il nodo rifiuta prima di agire se il disco dice altro. Poi:

```
uv run ela task approve <id> --approval <approval-id>
```

```
uv run ela task run <id>
```

La risposta è `assigned`. Dopo qualche secondo:

```
uv run ela task run <id>
```

```
uv run ela audit tail --task <id> -n 10 --json > ~/Downloads/m13.3-file-sul-pc.json
```

Sul PC:

```powershell
Get-Content "<radice del PC>\ELA\prova.md"
```

**Che cosa si deve vedere**: il task `completed`; il file sul disco del PC, con il testo del piano; e
nel registro un `EXECUTION_VERIFIED` il cui payload ha `verified_on` uguale all'id del PC — il campo
`id` della sua riga in `ela device list --json` —: **la verifica è avvenuta sul PC**, e il file che il Mac può avere allo
stesso percorso dalla prova di §15 non conta niente. Poi la lettura, con lo stesso giro e `docs/examples/fs-read.json`, e il
contenuto in `uv run ela task results <id>`.

**La perdita dichiarata, vista.** Lo stesso `fs-write.json`, in un task nuovo `TRUSTED`, sempre con il
Mac a batteria: **la domanda nasce** — ELA non vede il disco del PC, e sul Mac, dove lo vede, non
l'avrebbe fatta nascere (§15, passo 3) —; approvala, e il nodo **rifiuta prima di scrivere**. Il
rifiuto dice quale fatto il disco ha smentito, con il suo codice, fra le righe del risultato:

```
uv run ela task results <id>
```

```
error      fs.overwrite_mismatch
message    'ELA/prova.md' was declared as a new file and something is there now
```

(qui solo le due righe dell'errore; il resto del blocco è quello di sempre).

Il file sul PC resta quello di prima: il costo della domanda già condannata è un sì speso, mai un
effetto diverso da quello approvato.

### 4. La misura dei pesi

Il PC attaccato alla corrente e fermo, il passo 1 passato. **Che cosa si misura** sta nella SPEC
(«Le prove a mano»), scritto prima dei numeri: l'eco e la lettura, dieci prove per macchina — la voce
no, perché misurerebbe il motore e non la località —; sul PC dall'offerta alla consegna ricevuta, su
`local` dalla decisione `ALLOWED` al risultato registrato — mai dal piazzamento, perché lo step
comincia prima della domanda, e per una lettura misurerebbe il consenso.

**I blocchi sono cicli**, una riga ciascuno: ogni prova scrive la sua riga nel file, con l'esito e con
**Low Power Mode letto da `pmset` all'inizio e alla fine della prova**, e il ciclo **si ferma alla prima
prova che non vale** — un esito che non è `completed`, o Low Power Mode acceso — e stampa quale. Low
Power Mode su questo Mac a batteria può accendersi da solo, e raddoppia i tempi. Nel blocco B un `run`
che trova il task occupato da una consegna del PC risponde `409` e non stampa niente: il ciclo lo
riprova, e non lo conta come una prova.

**Perché nel blocco B vince il PC** (ADR 0048 §13): il Core osserva lo stato di `local` come il nodo
riporta il suo, e la corrente vale 20. Il Mac a batteria e libero vale 20 (la rete) + 0 (la corrente)
+ 10 (libero) = **30**; il PC sotto corrente e libero 5 + 20 + 10 = **35**. Attaccato, il Mac varrebbe
50 e il lavoro resterebbe sul Mac. **Una domanda lasciata aperta non occupa il Mac**: `local` è `BUSY`
(−10) solo mentre un suo tool gira, dall'avvio al risultato registrato, e i cicli qui sotto fanno un
task alla volta — a ogni piazzamento il Mac è libero.

**Blocco A, `local`**: il Mac attaccato, i task senza `--privacy`, quindi `LOCAL_ONLY`. Prima del
blocco, lo stato dei nodi:

```
uv run ela device list --json > ~/Downloads/m13.3-pesi-A-nodi.json
```

Dieci eco:

```
for i in {1..10}; do prima=$(pmset -g | awk '/lowpowermode/ {print $2}'); id=$(uv run ela task create "eco locale $i" --json | jq -r .id); uv run ela task plan "$id" --file docs/examples/echo.json > /dev/null; out=$(uv run ela task run "$id" --json); dopo=$(pmset -g | awk '/lowpowermode/ {print $2}'); line=$(echo "$out" | jq -c --argjson prova "$i" --arg prima "$prima" --arg dopo "$dopo" '. + {prova: $prova, lowpowermode_prima: $prima, lowpowermode_dopo: $dopo}'); echo "$line" >> ~/Downloads/m13.3-pesi-A-eco.jsonl; echo "$line" | jq -e '.outcome == "completed" and .lowpowermode_prima == "0" and .lowpowermode_dopo == "0"' > /dev/null || { echo "prova $i non valida: $line"; break; }; done
```

Dieci letture — ognuna chiede il consenso, e il ciclo lo dà per te. Rileggono `ELA/prova.md` sotto la
radice del **Mac**: se la prova di §15 non l'ha lasciato, scrivilo prima con `fs-write.json` in un task
senza `--privacy`.

```
for i in {1..10}; do prima=$(pmset -g | awk '/lowpowermode/ {print $2}'); id=$(uv run ela task create "lettura locale $i" --json | jq -r .id); uv run ela task plan "$id" --file docs/examples/fs-read.json > /dev/null; uv run ela task run "$id" > /dev/null; a=$(uv run ela approvals --json | jq -r --arg t "$id" '.[] | select(.task_id == $t) | .id'); uv run ela task approve "$id" --approval "$a" > /dev/null; out=$(uv run ela task run "$id" --json); dopo=$(pmset -g | awk '/lowpowermode/ {print $2}'); line=$(echo "$out" | jq -c --argjson prova "$i" --arg prima "$prima" --arg dopo "$dopo" '. + {prova: $prova, lowpowermode_prima: $prima, lowpowermode_dopo: $dopo}'); echo "$line" >> ~/Downloads/m13.3-pesi-A-lettura.jsonl; echo "$line" | jq -e '.outcome == "completed" and .lowpowermode_prima == "0" and .lowpowermode_dopo == "0"' > /dev/null || { echo "prova $i non valida: $line"; break; }; done
```

**Blocco B, il PC**: **stacca l'alimentatore del Mac**, aspetta un battito — venti secondi —, e i task
`TRUSTED`. Lo stato dei nodi deve dire `local` disponibile **e** a batteria:

```
uv run ela device list --json > ~/Downloads/m13.3-pesi-B-nodi.json
```

Ogni ciclo aspetta che il PC abbia consegnato — rilancia `run` finché la risposta non è più
`assigned` — prima di passare al task dopo: un nodo tiene un lavoro alla volta, e un'offerta che
aspetta in coda gonfierebbe la misura di quella dopo.

```
for i in {1..10}; do prima=$(pmset -g | awk '/lowpowermode/ {print $2}'); id=$(uv run ela task create "eco sul PC $i" --privacy TRUSTED --json | jq -r .id); uv run ela task plan "$id" --file docs/examples/echo.json > /dev/null; until out=$(uv run ela task run "$id" --json) && [ -n "$out" ] && ! echo "$out" | jq -e '.outcome == "assigned"' > /dev/null; do sleep 2; done; dopo=$(pmset -g | awk '/lowpowermode/ {print $2}'); line=$(echo "$out" | jq -c --argjson prova "$i" --arg prima "$prima" --arg dopo "$dopo" '. + {prova: $prova, lowpowermode_prima: $prima, lowpowermode_dopo: $dopo}'); echo "$line" >> ~/Downloads/m13.3-pesi-B-eco.jsonl; echo "$line" | jq -e '.outcome == "completed" and .lowpowermode_prima == "0" and .lowpowermode_dopo == "0"' > /dev/null || { echo "prova $i non valida: $line"; break; }; done
```

```
for i in {1..10}; do prima=$(pmset -g | awk '/lowpowermode/ {print $2}'); id=$(uv run ela task create "lettura sul PC $i" --privacy TRUSTED --json | jq -r .id); uv run ela task plan "$id" --file docs/examples/fs-read.json > /dev/null; uv run ela task run "$id" > /dev/null; a=$(uv run ela approvals --json | jq -r --arg t "$id" '.[] | select(.task_id == $t) | .id'); uv run ela task approve "$id" --approval "$a" > /dev/null; until out=$(uv run ela task run "$id" --json) && [ -n "$out" ] && ! echo "$out" | jq -e '.outcome == "assigned"' > /dev/null; do sleep 2; done; dopo=$(pmset -g | awk '/lowpowermode/ {print $2}'); line=$(echo "$out" | jq -c --argjson prova "$i" --arg prima "$prima" --arg dopo "$dopo" '. + {prova: $prova, lowpowermode_prima: $prima, lowpowermode_dopo: $dopo}'); echo "$line" >> ~/Downloads/m13.3-pesi-B-lettura.jsonl; echo "$line" | jq -e '.outcome == "completed" and .lowpowermode_prima == "0" and .lowpowermode_dopo == "0"' > /dev/null || { echo "prova $i non valida: $line"; break; }; done
```

**Che cosa si deve vedere alla fine di ogni ciclo**: nessuna riga «prova … non valida», e nel suo file
dieci righe, ciascuna con `"outcome":"completed"`, `"lowpowermode_prima":"0"` e
`"lowpowermode_dopo":"0"`. Se il ciclo si è fermato, sposta il suo file — per esempio aggiungendo `.1`
al nome — e rifai il blocco da capo: i nomi dei file sono nei comandi, e un secondo giro nello stesso
file mescolerebbe le prove.

I `sleep` non misurano niente: danno al nodo il tempo di consegnare fra un `run` e l'altro. **I tempi
si leggono dal database**, sull'orologio del Core — le assegnazioni, i risultati, e gli eventi con le
decisioni e i punteggi. Il database è `~/.ela/ela.db` se `ELA_DB_URL` non è impostata; le righe sono
di tutti i task del database, e la sessione tiene solo quelle dei task che i file `.jsonl` nominano —
nel database un id è di 32 cifre esadecimali senza trattini, nei `.jsonl` è con i trattini, e la
sessione li confronta togliendoli:

```
sqlite3 -json ~/.ela/ela.db "select a.task_id, a.device_id, a.created_at, a.claimed_at, a.delivered_at, r.capability_id, r.duration_ms, r.created_at as received_at, json_extract(r.metadata, '\$.node.ran_at') as ran_at from assignments a join execution_results r on r.task_id = a.task_id and r.step_id = a.step_id and r.status <> 'STARTED' order by a.seq" > ~/Downloads/m13.3-pesi-assegnazioni.json
```

```
sqlite3 -json ~/.ela/ela.db "select task_id, capability_id, device_id, created_at, duration_ms from execution_results where status <> 'STARTED' order by seq" > ~/Downloads/m13.3-pesi-risultati.json
```

```
sqlite3 -json ~/.ela/ela.db "select task_id, event_type, created_at, device_id, payload from audit_events where event_type in ('DEVICE_SELECTED', 'PERMISSION_DECIDED', 'STEP_STARTED', 'TOOL_EXECUTED', 'EXECUTION_VERIFIED', 'STEP_COMPLETED') order by seq" > ~/Downloads/m13.3-pesi-eventi.json
```

**Che cosa si deve vedere, prima di guardare un numero** — è la regola 5 della SPEC, e una prova che
non la rispetta non vale:

- in `m13.3-pesi-A-nodi.json` la riga di `local` disponibile e `AC`; in `m13.3-pesi-B-nodi.json`
  disponibile e `BATTERY`; in tutti e due la riga di `local` `IDLE` e la riga del PC `AC` e `IDLE`,
  non `UNKNOWN`;
- ogni riga finale di un task nei `.jsonl` dice `completed`;
- nel blocco A ogni `DEVICE_SELECTED` sceglie `local`; nel blocco B sceglie il PC, e fra i candidati
  `local` c'è, con i suoi punti e **senza** `UNAVAILABLE` fra i rifiuti: un PC che vince perché il Mac
  risultava assente misura la gara che il vincolo della review esclude;
- l'eco e la lettura valide **tutte e due**, sulle due macchine.

I numeri li legge la sessione dai file, con la regola scritta nella SPEC prima di vederli.

### 5. L'orologio

Sul Mac e sul PC, uno subito dopo l'altro, contro lo stesso server; nessuno dei due comandi imposta
l'ora — `sntp` la imposta solo con `-s` o `-S`, e `/stripchart` la legge soltanto:

```
sntp time.apple.com > ~/Downloads/m13.3-orologio-mac.txt 2>&1
```

```powershell
w32tm /stripchart /computer:time.apple.com /samples:5 /dataonly | Out-File -Encoding utf8 "$HOME\Downloads\m13.3-orologio-pc.txt"
```

**Il PC appena sveglio.** Sospendi il PC per almeno un'ora. Al risveglio, **la misura prima di
qualunque altra cosa** — e mai `w32tm /resync`, né avviare il servizio dell'ora per leggerne lo stato,
perché avviarlo è già una risincronizzazione:

```powershell
w32tm /stripchart /computer:time.apple.com /samples:5 /dataonly | Out-File -Encoding utf8 "$HOME\Downloads\m13.3-orologio-pc-sveglio.txt"
```

E sul Mac, nello stesso minuto:

```
sntp time.apple.com > ~/Downloads/m13.3-orologio-mac-2.txt 2>&1
```

**Solo dopo**, sul PC, la prova che fra il risveglio e la misura nessuno ha toccato l'ora — gli eventi
di sistema delle ultime due ore: il risveglio (`Power-Troubleshooter`, con l'istante in cui la
macchina si è svegliata), ogni cambio dell'ora (`Kernel-General`, con l'ora vecchia e la nuova), ogni
sincronizzazione del servizio dell'ora (`Time-Service`):

```powershell
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddHours(-2)} | Where-Object { $_.ProviderName -in 'Microsoft-Windows-Power-Troubleshooter','Microsoft-Windows-Kernel-General','Microsoft-Windows-Time-Service' } | Format-List TimeCreated, ProviderName, Id, Message | Out-File -Encoding utf8 "$HOME\Downloads\m13.3-orologio-pc-sveglio-eventi.txt"
```

**Che cosa si deve vedere**: un risveglio, e **nessun cambio dell'ora e nessuna sincronizzazione fra
il risveglio e l'istante della misura**. Se ce n'è uno, la lettura non è il caso peggiore: si rifà
dopo un'altra sospensione. La differenza fra lo scarto del PC e quello del Mac è la deriva del nodo
rispetto al Core, e si confronta con i 180 s che una decisione ha di vita nel caso peggiore. **Il segno
non si deduce a memoria**: lo si legge dalla documentazione dei due strumenti e lo si conferma con il
numero di ELA — `ran_at` meno l'istante in cui il Core ha ricevuto la busta, dalle consegne del
blocco B —, che è un limite inferiore: un valore positivo dice che il PC è avanti almeno di tanto, uno
negativo non dice che è indietro. `Out-File` di PowerShell 5.1 scrive un BOM: il file
si legge lo stesso.

### 6. La seconda metà del passo 9 di M13.2

La prova di §16, passo 9, dal paragrafo «Poi sparito», **nella sostanza com'è scritta**; qui i
comandi sono uno per blocco e senza i commenti in coda, e c'è la preparazione, che la pulizia di
M13.2 ha tolto e un riavvio del Mac cancella da `/tmp`. Un programma da cancellare:

```
mkdir -p ~/ela-prova/bin
```

```
cp /bin/echo ~/ela-prova/bin/eco
```

Aggiungi `"Users/tu/ela-prova/bin/eco"` a `ELA_TERMINAL_PROGRAMS` nel `.env` — senza la barra
iniziale —, riavvia `ela serve` nel primo terminale, e prepara il piano:

```
sed 's#"bin/echo"#"Users/tu/ela-prova/bin/eco"#' docs/examples/terminal-echo.json > /tmp/eco.json
```

Una domanda aperta, a cui **non** rispondere:

```
uv run ela task create "l'eco che sparirà"
```

```
uv run ela task plan <id> --file /tmp/eco.json
```

```
uv run ela task run <id>
```

Poi il file sparisce, mentre ELA gira:

```
rm ~/ela-prova/bin/eco
```

```
uv run ela task create "l'eco sparito"
```

```
uv run ela task plan <id> --file /tmp/eco.json
```

```
uv run ela task run <id>
```

**Che cosa si deve vedere**: questo secondo task `FAILED` **senza domanda**, con
**`terminal.program_gone`**, e la frase di §16. Poi approva la domanda del primo task e rilancialo:

```
uv run ela approvals
```

```
uv run ela task approve <id> --approval <approval-id>
```

```
uv run ela task run <id>
```

**Che cosa si deve vedere**: il rifiuto **prima dell'esecuzione**, con lo stesso codice. La pulizia è
quella di §16: togli la voce da `ELA_TERMINAL_PROGRAMS`, cancella `~/ela-prova`, e riavvia.

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
- [`adr/0045-filesystem-and-high.md`](adr/0045-filesystem-and-high.md) — il primo livello `HIGH`,
  perché lo scope si lega al fatto e non alla riga, e dove vanno i byte di un file letto.
- [`adr/0040-node-windows.md`](adr/0040-node-windows.md) — il nodo su un PC: dove tiene il segreto,
  con che cosa parla, e perché dichiara solo ciò che la sua macchina sa fare.
- [`adr/0043-companion.md`](adr/0043-companion.md) — l'iPhone che guarda e risponde: il ruolo, il
  cookie, le pagine e il campanello.
- [`adr/0044-command-center.md`](adr/0044-command-center.md) — il Command Center: la terza
  identità, il tetto derivato dal socket, e l'impronta che suona quando una capability arriva
  senza la sua vista.
