# Far partire ELA, e farle fare la prima cosa

Il giro completo, comando per comando, su una macchina vuota. Non serve `curl`: dopo M8.2 ELA si
guida dalla riga di comando (§54; ADR 0023 per il processo, ADR 0024 per la CLI).

Ogni output qui sotto è quello vero di una sessione reale — id e istanti a parte, che cambiano.
**Un blocco d'uscita è ciò che la CLI stampa**, e dove è lungo e se ne mostra un pezzo, le righe tolte
sono un `…`, sopra e sotto: un test confronta i blocchi di `ela task run` e di `ela approvals` con il comando
(M6.3b, M13.1c, M13.1d), e gli altri li prenderà M9.7.

### Come si leggono i comandi

Quello che sta fra parentesi angolari è un **segnaposto**: al suo posto va un valore vero, e le
parentesi **non si incollano**. `ela task run <id>` si scrive `ela task run 55ed2ab5-…`, mai
`ela task run <55ed2ab5-…>`. Sono tutti in questa tabella, con il posto da cui viene il valore:

| Segnaposto | Che cosa ci va | Da dove viene |
|---|---|---|
| `<questo repo>` | l'URL da cui cloni ELA | da dove hai preso il repository |
| `<id>` | l'id di un task | `ela task create`, oppure `ela task list` |
| `<approval-id>` | l'id di una richiesta di consenso | `ela approvals` |
| `<id del figlio>` | l'id del task di pianificazione di un task | `ela task plan <id>`, riga `planning` (§5, sezione 24) |
| `<nota>` | il nome della nota del passo 2 della sezione 24, unico per giro | lo scrive `scripts/prova_m14_2.py` al posto del segnaposto, con la data e l'ora |
| `<codice>` | il codice di arruolamento di un nodo | `ela node enroll`, stampato una volta sola |
| `<ip tailnet del Mac>` | l'indirizzo del Mac sulla tailnet | `tailscale ip -4`, sul Mac (§12) |
| `<nome della voce>` | una voce SAPI 5 installata sul PC | l'elenco del passo 3 di §12: sul PC di M12.4, `Microsoft Elsa Desktop` |
| `<chiave del modello del PC>` | la chiave Anthropic del nodo, mai quella del Core | la console Anthropic (§12, passo 4) |
| `<chiave del modello del Mac>` | la chiave Anthropic del Core, nella stessa workspace di quella del PC | la console Anthropic (§9, §23) |
| `<tetto in dollari>` | quanto il mese può spendere sulla chiave del modello, sotto il limite mensile dell'organizzazione | lo decidi tu (§9, §23) |
| `<id del companion>` | l'id della riga dell'iPhone nel registro | `ela device list`, colonna `ID` (§13) |
| `<id della console>` | l'id della riga del Command Center nel registro | `ela device list`, colonna `ID` (§14) |
| `<id del passo 2>` | l'id del task del passo 2 di §21, nel suo ultimo giro, o della sezione 25 | lo scrive `scripts/prova_m6_3c.py`, o `scripts/prova_m13_1e.py`, al posto del segnaposto |
| `<id del passo 3>` | l'id del task del passo 3 di §21, nel suo ultimo giro, o della sezione 25 | lo scrive `scripts/prova_m6_3c.py`, o `scripts/prova_m13_1e.py`, al posto del segnaposto |
| `<id del passo 4>` | l'id del task del passo 4 di §21, nel suo ultimo giro, o della sezione 25 | lo scrive `scripts/prova_m6_3c.py`, o `scripts/prova_m13_1e.py`, al posto del segnaposto |
| `<id del passo 5>` | l'id del task del passo 5 della sezione 25 | lo scrive `scripts/prova_m13_1e.py` al posto del segnaposto |
| `<id del passo 6>` | l'id del task del passo 6 della sezione 25 | lo scrive `scripts/prova_m13_1e.py` al posto del segnaposto |
| `<id di chi ha risposto>` | l'id dell'identità che ha detto no, nel passo della sezione 25 | lo scrive `scripts/prova_m13_1e.py`, da `GET /tasks/<id>`, al posto del segnaposto |
| `<nome di chi ha risposto>` | il nome che il registro dà a chi ha detto no | lo scrive `scripts/prova_m13_1e.py`, da `GET /devices`, al posto del segnaposto |
| `<porta>` | la porta su cui ELA ascolta | `ela diagnostics`, riga `addresses` (§14) |
| `<radice del PC>` | la cartella del PC dentro cui ELA può leggere e scrivere | la scegli tu, sul PC: una cartella che c'è, e che non contiene né sta dentro `$HOME\.ela` o `$HOME\ELA` (§17, passo 2) |
| `<id della voce configurata>` | l'id della voce online che usi | `uv run ela voice`, riga `online voice`: lo scrive `scripts/prova_m13_1c_m13_1d_m9_6.py` al posto del segnaposto (§22) |

## 0. Che cosa serve

Python 3.12+, [uv](https://docs.astral.sh/uv/), e il repository:

```
git clone <questo repo> && cd ELA
uv sync
```

E, da M13.4, il browser che ELA usa — lo shell di Chromium della versione che il lock nomina, circa
100 MB da scaricare, in `~/Library/Caches/ms-playwright` —, una volta per macchina e di nuovo quando
il lock porta un Playwright nuovo. `uv sync` non lo scarica, e senza di lui i test del browser
falliscono dicendo questo comando:

```
uv run playwright install --only-shell chromium
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
  write ELA_FS_ROOT, ELA_FS_SCOPE, ELA_TERMINAL_PROGRAMS and ELA_BROWSER_SITES in .env   # no default, and no start without
  uv run alembic upgrade head   # ELA does not migrate on start-up (ADR 0006)
  ela serve                     # ELA creates its database directory and workspace
```

Scrive **un solo file**, `.env`, con un token generato e permessi `0600`. Il token **non viene
stampato**: sta nel file, e da lì lo leggono sia ELA sia la CLI. Sotto al token trovi **le righe
obbligatorie** — `ELA_FS_ROOT`, `ELA_FS_SCOPE`, da M13.2 `ELA_TERMINAL_PROGRAMS` e da M13.4
`ELA_BROWSER_SITES` —, commentate
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
ela: .env does not set ELA_FS_ROOT, ELA_FS_SCOPE, ELA_TERMINAL_PROGRAMS and ELA_BROWSER_SITES, and ELA does not start without them: they have no default. Write them, for example:
    ELA_FS_ROOT=/Users/you/Documents
    ELA_FS_SCOPE=ELA
    ELA_TERMINAL_PROGRAMS=[]
    ELA_BROWSER_SITES=[]
The folder is yours: ELA does not create it and does not choose it.
The programs are one line of JSON, each relative to / — usr/bin/git is /usr/bin/git —, and [] is an answer: no program at all.
The sites are one line of JSON, each a host name alone — example.com, without https:// —, and [] is an answer: no site at all.
```

Fino a M13.1b `init` diceva che il token era «the only variable ELA requires» e, su questo stesso
file, «nothing required is missing»: se lo leggi ancora, stai girando su codice precedente.

**Nella verifica a mano di M13.1b, il 2026-09-22**: la seconda chiamata è uscita con `2` e ha
nominato `ELA_FS_ROOT` ed `ELA_FS_SCOPE`, le obbligatorie di allora; `ELA_TERMINAL_PROGRAMS` è
entrata con M13.2, `ELA_BROWSER_SITES` con M13.4.

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

### Una riga che **deve** essere scritta: i siti che il browser di ELA può aprire

Da M13.4 ELA apre pagine in un browser suo, vuoto, e **quali siti** lo dichiari tu, in una riga di
JSON senza default — un nome per sito, senza `https://`:

```
ELA_BROWSER_SITES=[]
```

`[]` è una risposta: nessun sito. Che cosa vuol dire dichiararne uno — ELA lo può **leggere senza
chiederti niente**, e per compilarvi un modulo ti chiede ogni volta — sta nella
[§20](#20-il-browser-la-prova-a-mano-di-m134). **Se il tuo `.env` è di prima di M13.4, `ela serve` non
parte finché non aggiungi questa riga.**

**Da M14.2 un piano lo può scrivere anche il modello** (§5), e una lettura di un sito dichiarato è un GET
che lui compone: può portare al sito parole del tuo obiettivo — nel percorso, nella query —, e se il sito
fa qualcosa su un GET, lo fa. Il piano lo leggi prima di avviarlo, con i suoi argomenti; ma dichiara solo
siti a cui una lettura non fa fare niente.

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

### Il piano lo scrive ELA, o lo scrivi tu

Da M14.2 ELA ha un **Planner** (§13): `ela task plan <id>`, **senza** `--file`, gli chiede il piano. Il Planner
non chiama il modello da sé: crea un **task di pianificazione**, figlio del tuo, il cui unico step è una domanda
al modello — e quella domanda, come ogni chiamata che spende, **chiede il tuo sì**, con il caso peggiore e ciò che
resta del mese (§23). Dopo il sì — `ela task approve <id del figlio> --approval <approval-id>` —, di nuovo
`ela task plan <id>`: il modello scrive il piano, ELA lo controlla con le stesse funzioni che decideranno quando
gira, e il task va in coda. **Non parte da solo**: lo leggi con `ela task show <id>` — chi l'ha scritto, e per
ogni step gli argomenti e le condizioni —, e lo avvii tu, con `ela task run <id>`. Di un task finito
`ela task show` dice anche **perché è finito**, nella riga `reason` sotto `state` — da M13.1e, la stessa ragione
di `ela task run` —, e per un no **chi ha risposto**, nella riga `answered by`. Serve una chiave e un tetto
(§9, §23); senza tetto la pianificazione è negata prima della domanda, e la ragione dice quale riga manca. La
prova a mano è la [sezione 24](#24-il-planner-la-prova-a-mano-di-m142).

Il piano lo puoi anche **scrivere tu**, ed è ciò che fa questo primo giro. Ne trovi uno pronto in
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

Il file viene mandato com'è. La sua forma è quella di un **piano scritto a mano**, non versionata: può
cambiare senza preavviso, e non conviene costruirci sopra niente di duraturo. ELA lo controlla prima di
metterlo in coda — ogni step con una capability sola del catalogo e almeno una condizione che il suo
verifier sa controllare —, e un piano che non lo è torna indietro subito, con lo step per numero.

## 6. `ela task run` — ELA si ferma e chiede

```
uv run ela task run <id>
```

```
outcome        waiting_approval
reason         —
state          WAITING_APPROVAL
steps handled  9c5b8f26-1a2b-4c3d-8e4f-000000000001, 9c5b8f26-1a2b-4c3d-8e4f-000000000002
stopped step   —
```

Il primo step — l'echo — è stato eseguito; sul secondo ELA si ferma e chiede. Sotto `steps handled`
ci sono gli step che questa corsa ha **trattato** — quelli su cui ELA ha dato la sua risposta:
eseguiti, falliti, negati, o fermi sul tuo consenso —, e dopo `waiting_approval` l'ultimo è quello su
cui si è fermata: un id lì sotto non vuol dire che lo step sia stato eseguito (M6.3b, ADR 0051). **Non è per il
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
approval              47fbce38-66ab-519c-b7dc-8cce4bd4a7f2
task                  55ed2ab5-94aa-581f-9468-c4d247d9fe04
capability            workspace.write_note
what                  Writes a note at a path inside the authorised notes folder.
risk                  LOW
may go                LOCAL_ONLY
question expires      2026-09-07T09:12:00+00:00
grant if you say yes  1 use, within 60 minutes
step goal             scrivere la nota del primo task
declared              —
targets               workspace/notes/first-task.md
target                —
does                  —
asks                  workspace.write_note on workspace/notes/first-task.md for step 9c5b8f26-… (scrivere la nota del primo task): workspace.write_note requires an authorization: none was given
```

**Un blocco per domanda, e mostra tutto ciò che la domanda nomina**: è la condizione per cui una
superficie può offrirti un sì (M13.1, ADR 0045 §11). Le due scadenze dicono ciascuna di chi è: la
domanda smette di poter essere risposta a un istante, e il permesso che un sì crea vive per un altro. I
trattini non sono buchi — `declared` è vuoto perché questa capability non dichiara argomenti da mostrare;
`target` e `does` perché lo strumento delle note non descrive prima che cosa tocca: quelli che lo fanno —
un file fuori dalla workspace in §15, un programma in §16 — chiamano la riga del bersaglio con la loro
parola, `file` e `program`.

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
outcome        completed
reason         —
state          COMPLETED
steps handled  9c5b8f26-1a2b-4c3d-8e4f-000000000002
stopped step   —
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
run`, il consenso, `task run` — e la risposta si legge con `ela task results`.

**Da M14.1 una chiamata che spende parte solo sotto un tetto mensile** ([ADR 0057](adr/0057-spending-cap.md)).
Senza la riga del tetto lo step è negato **prima della domanda**, e la ragione nomina la riga; con il tetto e senza
chiave è negato perché non si può limitare, `provider.unavailable`, **senza toccare la rete**. Per farlo girare, due
righe nel `.env` e `ela serve` riavviato:

```
ELA_ANTHROPIC_API_KEY=<chiave del modello del Mac>
ELA_SPENDING_CAP_USD=<tetto in dollari>
```

Il tetto sta **sotto** il limite mensile dell'organizzazione che imposti nella console di Anthropic, nella pagina
Billing: quello copre ogni chiave, anche ciò che spende fuori da ELA. La domanda di `ask-model.json` dice quanto può costare la chiamata — il caso peggiore,
4,065536 $ su Opus 5.5 — e quanto resta nel mese; `uv run ela spend` dice dove sei. Tutto il resto, con il PC, è §23.

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
10.0.26200, Python 3.12.10); ***dal 2026-09-28 (M6.3b)*** i blocchi di `ela task run` del passo 6
sono scritti come la CLI li stampa oggi — la riga degli step si chiama `steps handled`, non più
`steps executed`, e la colonna è di 15 —, con gli id e le ragioni di quella prova e le righe `reason`
e degli step che la guida aveva tolto. Dove un passo non è stato rieseguito perché una misura lo
aveva già coperto, è detto lì. Il trascritto integrale sta in `.git/m12-reference/ela-prova-a-mano.txt`.

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

Nella prova di M12.4 il file è stato scritto **senza** la terza riga, perché su nessuna delle due macchine
c'era ancora una chiave del modello (da M14.1 c'è, §23):

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
  sua. Da M14.1 sta nella **stessa workspace** della chiave del Mac — la workspace tiene insieme le due chiavi di ELA,
  e la sua spesa nella console è quella di ELA —, sotto il limite mensile dell'organizzazione, e il PC **non ha un
  tetto suo**: `ELA_SPENDING_CAP_USD` è una riga del Core, e il nodo spende solo ciò che il Core gli ha
  prenotato con l'ordine (§23). Il file sta in `$HOME\ELA` con i permessi della cartella del profilo — lo leggono i processi
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
outcome        waiting_approval
reason         —
state          WAITING_APPROVAL
steps handled  5a1e0c3d-7b2f-4e8a-9c41-000000000001
stopped step   —
```

```
outcome        assigned
reason         step 5a1e0c3d-7b2f-4e8a-9c41-000000000001 assigned to node DESKTOP-QQ0GSE2 (5ddae87a-6eb1-4fb0-947c-f912fce6c026) as assignment 0fa13927-593d-46f7-b5e2-744dde2c15aa, due by 2026-09-17T20:46:46.808533+00:00
state          EXECUTING
steps handled  —
stopped step   —
```

Sotto `assigned` nessuno step è trattato: lo step è del PC, la risposta la darà lui, e il `reason`
lo nomina.

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
outcome        completed
reason         —
state          COMPLETED
steps handled  —
stopped step   —
```

`steps handled` è vuoto anche qui: lo step l'ha chiuso la consegna del PC, e questa corsa ha solo
chiuso il task.

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
c'è l'output che lo mostra. ***Letto il 2026-10-07***, con la prova a mano di M14.1 (§23, passo 6):
`Ctrl-C` sul nodo del PC a metà chiamata, la presa scaduta in 125 secondi, e il task `FAILED` con
`execution.interrupted`, non rieseguito.

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
c'era ancora una chiave del modello né sul Mac né sul PC, e senza chiave `model.complete` fallisce
prima della verifica con `provider.unavailable`. **Da M14.1 è il passo 7 di §23**, con le chiavi e con lo
script, ***ed è passata il 2026-10-07*** sulle due macchine: il risultato del PC `SUCCEEDED` sul nodo, e il task
`FAILED` con `model.routed_as_asked (model.misrouted)`. Qui sotto i comandi a mano. Il Core prenota il caso peggiore di Opus 5.5, la sua rotta; il PC chiama Haiku, che
ci sta dentro. Ferma il nodo con `Ctrl-C`, aggiungi al `.env` del PC una riga che il Mac non ha, e riavvialo:

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
identità che *guarda e risponde* — le domande che aspettano, i task vivi e gli ultimi finiti, il sì,
il no, e fermare un task —, e lo fa da una pagina che ELA serve, nel browser del telefono (M12.5,
ADR 0043).

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
http://<ip tailnet del Mac>:<porta>/companion/
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
lavorando (`WORKING`) o se è ferma (`IDLE`). Sotto, le domande che aspettano, e i task in due gruppi:
i **vivi** e i **finiti** — gli ultimi sei, l'ultimo a finire per primo, con il loro stato; il titolo
dice il limite e, se sono di più, di quanti (M17.2b). Sotto lo stato di un task finito c'è **perché è finito**
(M13.1e): per un task che il telefono può vedere la ragione intera e, per un no, chi ha risposto con il suo nome;
per un task che resta sul Mac **solo parole di ELA** — l'operazione, il codice, e chi ha risposto detto come
«la riga di comando», «la console» o «il telefono» —, per esempio «`deny_by_approval` · ha risposto: la console». Toccare una domanda apre la pagina della
domanda: che cosa ELA vuole fare, con che rischio, fin dove può andare il contenuto, per quanto vale
il sì. **Il sì risponde e fa ripartire il task nella stessa richiesta** — le stesse due cose che al
Mac sono `ela task approve` e `ela task run` —, e la pagina torna alla home, dove il task è il primo
dei finiti se si è chiuso. Toccare un task vivo porta alla conferma per fermarlo, su una seconda
pagina: fermare non si annulla, e il task fermato resta fra i finiti. Un task finito non è un
collegamento: il suo riassunto si legge dal Mac.

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
e dove si legge. Di un task finito il riassunto dice **«Perché»** e, per un no, **«Ha risposto»** (M13.1e), e
la riga del task nella home porta la stessa ragione sotto lo stato: da questa macchina intera, con il nome di chi
ha risposto; da fuori, per un task che resta sul Mac, solo l'operazione, il codice e il ruolo di chi ha risposto. Il contenuto di un risultato non si legge lì: è su `GET /tasks/<id>/results`.

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
asks                  fs.write on ELA/prova.md for step …: fs.write requires an authorization: none was given
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

**Nella verifica a mano di M13.1b, il 2026-09-22**: la domanda ha detto «creates a new file», e dopo
il sì il task `2f03cb88…` ha scritto `ELA/prova.md` ed è finito `COMPLETED`. Le righe `STARTED` e
`SUCCEEDED` portano lo stesso `authorization_id`, `0b4537fc…`, che è quello di
`AUTHORIZATION_GRANTED` e di `TOOL_EXECUTED`, con `"uses": 1` (letto dal database il 2026-09-28;
l'esito intero è in `docs/milestones/M13.1b.md`).

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
outcome        failed
reason         fail: EXECUTING -> FAILED (fs.overwrite_mismatch: 'ELA/prova.md' was declared as a new file and something is there now)
state          FAILED
steps handled  d1b7c4a2-9e35-4f18-8c60-000000000001
stopped step   —
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

`steps handled` porta l'**id dello step**, non un conteggio: ELA ha dato la sua risposta su quello
step — un rifiuto, prima di toccare il disco —, ed è quello che il suo id lì dentro significa. Il tool
non è stato chiamato.

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
outcome        denied
reason         deny_by_decision: EXECUTING -> DENIED (targets ['altrove/non-deve-esistere.md'] of fs.write are not within scope ['ELA'])
state          DENIED
steps handled  d1b7c4a2-9e35-4f18-8c60-000000000003
stopped step   —
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
outcome        denied
reason         deny_by_decision: EXECUTING -> DENIED (targets ['usr/bin/whoami'] of terminal.run are not within scope ['bin/echo', 'usr/bin/seq', 'usr/bin/time', 'usr/bin/printf', 'usr/bin/env'])
state          DENIED
steps handled  e7a3c915-2b64-4d08-9f71-000000000002
stopped step   —
```

***Riscritto il 2026-10-02*** (M13.1c, ADR 0055): la riga `reason` è quella che la CLI stampa da M13.1c, le parole
della transizione che ha chiuso il task; nella sessione del 2026-09-24 era la sola ragione del Guardian, `targets
['usr/bin/whoami'] of terminal.run are not within scope […]`.

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
…
targets               bin/echo
program               /bin/echo
runs                  /bin/echo
arguments             ["la parola di prova è", "girasole-7431"]
folder                /Users/tu/Documenti/ELA
timeout               120 s
expects exit          0
does                  runs this program from this folder: it can read and change whatever you can, and ELA sees what it prints, not what it changes
…
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
outcome        failed
reason         fail: EXECUTING -> FAILED (terminal.timeout: /usr/bin/time was still running after 10 s: ELA stopped its process group)
state          FAILED
steps handled  e7a3c915-2b64-4d08-9f71-000000000004
stopped step   —
```

***Riscritto il 2026-10-02*** (M13.1c, ADR 0055): il blocco era un ritaglio di due righe, `reason` e `state`, ancora
alla colonna di prima di M6.3b — il controllo dei blocchi di `run` non lo vedeva, perché cercava la riga `outcome` —;
le righe che mancavano sono determinate dal piano, e la ragione è quella che la CLI stampa da M13.1c. Nella sessione
del 2026-09-24 la riga era `reason terminal.timeout: …`, senza la transizione.

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
outcome        failed
reason         fail: EXECUTING -> FAILED (terminal.stopped: ELA was stopping while /usr/bin/time ran, and stopped its process group)
state          FAILED
steps handled  e7a3c915-2b64-4d08-9f71-000000000004
stopped step   —
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
il risveglio e l'istante della misura** — tranne il cambio del risveglio stesso, «System time
synchronized with the hardware clock». Se ce n'è un altro, la lettura non misura il risveglio: si rifà
dopo un'altra sospensione.

**Il risveglio non è il caso peggiore.** La SPEC lo pensava, e la misura del 2026-09-26 l'ha smentito
(ADR 0048 §14): al risveglio Windows rimette l'ora da quella dell'orologio hardware, e l'errore è quello
accumulato dall'ultima sincronizzazione, come da acceso — 0,39 s dopo dieci ore di sonno, 6,94 s la sera
prima, dopo otto giorni senza sincronizzarsi. Il peggio è il PC rimasto più a lungo senza sincronizzarsi,
e lo dice la storia delle correzioni del servizio dell'ora: gli eventi `Kernel-General` 1 degli ultimi
trenta giorni, esclusi i risvegli. Nei trenta giorni prima della prova, il peggio è stato 38,3 s avanti.

La differenza fra lo scarto del PC e quello del Mac è la deriva del nodo rispetto al Core, e si
confronta con i 180 s che una decisione ha di vita nel caso peggiore. **Il segno non si deduce a
memoria**: lo si legge dalla documentazione dei due strumenti e lo si conferma con il numero di ELA —
`ran_at` meno l'istante in cui il Core ha ricevuto la busta, dalle consegne del blocco B —, che è un
limite inferiore: un valore positivo dice che il PC è avanti almeno di tanto, uno negativo non dice che
è indietro. `Out-File` di PowerShell 5.1 scrive un BOM: il file si legge lo stesso.

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

## 18. La pagina che mente e la pagina spoglia: la prova a mano di M17.2b e M17.2c

> **Eseguita dall'utente il 2026-09-27 a `f85b228`**, su questo Mac (la porta era 8351) e
> sull'iPhone. **Passati i passi 1–4 e 6; il 5 è saltato**, per decisione dell'utente, e ciò che
> doveva mostrare lo affermano i test sull'orologio finto (sotto). Nata come bozza con le SPEC del
> 2026-09-26 e allineata all'implementazione: gli ADR sono [0049](adr/0049-finished-on-the-homes.md) e
> [0050](adr/0050-sheets-inside-the-page.md), accettati dopo questa prova. Sotto ogni passo, **ciò
> che si deve vedere** è l'istruzione per chi la rifà, e **nella prova del 2026-09-27** ciò che è
> successo.

Due riparazioni. **M17.2b**: un task finito non sparisce più dalle home — la console e il telefono
elencano, accanto ai vivi, gli ultimi task arrivati in uno stato finale, l'ultimo per primo. **M17.2c**:
la pagina d'arruolamento, la prima che un browser nuovo vede, ha l'aspetto di ELA, senza che nessuna
rotta risponda a chi non è ancora nessuno.

Presuppone il Command Center arruolato su `127.0.0.1` (§14) e il telefono arruolato **in Chrome**, il
browser predefinito (§13). Tre passi **nessun test può farli al posto tuo**: il secondo e il terzo,
perché l'hash del foglio lo calcola il browser, e se ne calcola un altro la pagina arriva senza stile —
lo vede solo un browser vero, e i motori sono due, Blink e WebKit —; e il quarto, perché l'ordine in
cui un utente ritrova i suoi esiti si guarda sulle due pagine insieme.

### 1. Il Core dal codice giusto, e lo schema

M17.2b aggiunge una colonna — l'ora in cui un task è finito —, e ELA non migra all'avvio (§2):

```
uv run alembic upgrade head
```

`alembic upgrade head`, in questo repository, **non stampa niente**: non c'è una configurazione di
log che gli faccia dire quale migrazione ha applicato. A dirlo è la domanda successiva:

```
uv run alembic current
```

```
0012 (head)
```

```
uv run ela serve
```

**Che cosa si deve vedere**: `0012 (head)`, e ELA che parte. Sulla home del Command Center, nella
tessera «Task», il gruppo «Finiti» con i task delle prove precedenti.

**Nella prova del 2026-09-27**: l'upgrade non ha stampato niente — la bozza prometteva «la migrazione
`0012` applicata», che il comando non dice, ed è il rilievo che ha portato qui `alembic current` —;
`alembic current` ha risposto `0012 (head)`; sulla home della console, il gruppo «Finiti» con i task
delle prove precedenti.

### 2. La pagina d'arruolamento, sul Mac, in due browser

In **Chrome**, il browser predefinito del Mac, una finestra in incognito (⇧⌘N): non ha il cookie della
console. Apri lo stesso indirizzo di §14, `http://127.0.0.1:<porta>/console`.

**Che cosa si deve vedere**: la stanza scura e il carattere delle altre pagine di ELA, il titolo e le
frasi del design system, i campi e il bottone del design system — non la pagina bianca con il
carattere del browser. Poi un arruolamento vero da lì, perché la pagina è cambiata: conia il codice

```
uv run ela node enroll --privacy TRUSTED --role console
```

incollalo, dai un nome che la distingua, invia. **Che cosa si deve vedere**: la home. Se non vuoi
tenere quella console nel registro, revocala — la finestra normale resta arruolata —, con l'id della
riga che porta quel nome:

```
uv run ela device list
```

```
uv run ela node revoke <id della console>
```

Poi in **Safari**, una finestra privata (⇧⌘N), lo stesso indirizzo: **la stessa pagina, vestita**.
Chiudila senza arruolarla.

**Nella prova del 2026-09-27**: in Chrome in incognito la pagina d'arruolamento è arrivata vestita;
l'arruolamento vero, con il nome «prova incognito», è riuscito ed è arrivato alla home. **La revoca
non è stata fatta**, per scelta dell'utente: quell'identità resta nel registro. In Safari, finestra
privata, la pagina è arrivata vestita, ed è stata chiusa senza arruolarsi.

### 3. La pagina d'arruolamento, sull'iPhone in Chrome

In Chrome, una **scheda in incognito**, all'indirizzo di §13, `http://<ip tailnet del Mac>:<porta>/companion/`
— la porta è quella del passo 2, e di `ela diagnostics`.

**Che cosa si deve vedere**: la stessa pagina del passo 2, con la cornice del telefono. **Tocca il
campo del codice**: la tastiera sale e **la pagina non si ingrandisce**, come nella prova di M17.1 — un
campo che ingrandisce la pagina è un campo che il foglio non ha raggiunto. Poi un arruolamento vero da
lì — il modulo del telefono non è quello della console: il campo Sistema è fisso —:
conia il codice al Mac,

```
uv run ela node enroll --privacy TRUSTED --role companion
```

incollalo nella scheda in incognito, dai un nome che la distingua, invia. **Che cosa si deve
vedere**: la home del telefono. Se non vuoi tenere quell'identità, revocala — la scheda normale di
Chrome resta arruolata —, con l'id della riga che porta il nome che hai appena dato:

```
uv run ela device list
```

```
uv run ela node revoke <id del companion>
```

**Nella prova del 2026-09-27**: su `http://100.76.92.39:8351/companion/`, in Chrome in incognito, la
pagina è arrivata vestita, e toccando il campo del codice la pagina non si è ingrandita.
L'arruolamento vero, con il nome «prova incognito telefono», è riuscito; non revocato, per scelta
dell'utente.

### 4. Un task creato prima e finito dopo

Il comando di §16, passo 5, con il timeout abbassato: presuppone §15 e §16 fatte, e la cartella
dello scope che c'è. Nel `.env`, **aggiungi** `"usr/bin/time"` alla lista di `ELA_TERMINAL_PROGRAMS` —
la pulizia di §16 l'ha tolto; con la lista vuota diventa la prima riga qui sotto — e abbassa il
timeout a dieci secondi, poi riavvia `ela serve`:

```
ELA_TERMINAL_PROGRAMS=["usr/bin/time"]
```

```
ELA_TERMINAL_TIMEOUT_SECONDS=10
```

Il comando lungo **si crea per primo**, `TRUSTED`, così il telefono ne vede l'obiettivo:

```
uv run ela task create "dormire troppo" --privacy TRUSTED
```

```
uv run ela task plan <id> --file docs/examples/terminal-timeout.json
```

Poi un'eco, **senza `--privacy`**: resta sul Mac — un'eco `TRUSTED` può viaggiare al PC e tornare
`assigned` (§17) —, e dal telefono se ne vede l'id e non l'obiettivo, perché il tetto vale anche per
un task finito. Creala, pianificala e lanciala **subito**:

```
uv run ela task create "un'eco"
```

```
uv run ela task plan <id> --file docs/examples/echo.json
```

```
uv run ela task run <id>
```

L'eco è `COMPLETED`. **Adesso** il comando lungo, con l'id di «dormire troppo»:

```
uv run ela task run <id>
```

```
uv run ela task approve <id> --approval <approval-id>
```

```
uv run ela task run <id>
```

**Che cosa si deve vedere**: dopo una decina di secondi «dormire troppo» è `FAILED`, con
`terminal.timeout`. Sulla home del Command Center, nel gruppo «Finiti», **«dormire troppo» è il primo**,
con `FAILED`, anche se è stato creato prima dell'eco — l'ordine è quello della fine, non della nascita
—, e l'eco è seconda, `COMPLETED`; un clic su «dormire troppo» porta al suo riassunto. Sulla home del
telefono, nel gruppo «Finiti», lo stesso ordine: «dormire troppo» con `FAILED`, poi l'id dell'eco con
`COMPLETED`, senza collegamenti.

**Nella prova del 2026-09-27**: «dormire troppo» (`8c71d897…`) creato prima dell'eco (`f70a69aa…`).
L'eco è finita `COMPLETED`; poi «dormire troppo», dopo il sì, `FAILED` con `terminal.timeout`. Su tutte
e due le home «dormire troppo» è il primo dei finiti, con `FAILED`, e l'eco è seconda. Sulla console
un clic porta al riassunto; sul telefono l'eco compare con il suo id, e le righe dei finiti non sono
collegamenti. I titoli dichiarano il limite.

**Trovato qui, e non preso.** Il primo `ela task run` di «dormire troppo», con esito
`waiting_approval`, ha stampato sotto `steps executed` lo step che aspettava il sì, e quello step
non era stato eseguito: misurato, `steps` contiene gli step consegnati all'executor, qualunque cosa
abbia fatto. È registrato come riparazione, **M6.3b** (`docs/milestones/M6.3b.md`). ***Riparato da
M6.3b il 2026-09-28***: la riga si chiama `steps handled`, e porta gli step su cui la corsa ha dato
la sua risposta (ADR 0051); la prova è la §19.

### 5. Un terzo task che finisce dopo, e il primo che resta

```
uv run ela task create "un'altra eco"
```

```
uv run ela task plan <id> --file docs/examples/echo.json
```

```
uv run ela task run <id>
```

**Che cosa si deve vedere**: su tutte e due le home l'eco nuova è **prima**, e «dormire troppo» è
**ancora lì**, seconda, con `FAILED`. Il titolo del gruppo dichiara il limite — «Finiti · gli ultimi
8» sulla console, «Finiti · gli ultimi 6» sul telefono — e, se le prove precedenti hanno lasciato più
finiti di così, dice di quanti: «Finiti · gli ultimi 8 di 23». Lo stesso, dal terminale:

```
uv run ela task finished
```

**Nella prova del 2026-09-27: saltato**, per decisione dell'utente — non passato. Ciò che doveva
mostrare lo affermano i test su un orologio che il test sposta fra un'esecuzione e l'altra:
l'ultimo a finire è il primo sulla console, sul telefono, nella rotta e nella CLI
(`test_the_last_to_finish_comes_first_even_if_it_was_born_first`,
`test_on_the_phone_the_last_to_finish_comes_first`,
`test_the_finished_route_answers_the_last_to_finish_first_and_how_many`,
`test_finished_shows_the_last_to_finish_first`), il limite e il totale
(`test_the_finished_route_keeps_the_last_and_counts_them_all`,
`test_finished_says_its_limit_and_how_many_there_are`), e i titoli che dichiarano il limite sulle
due home.

### 6. Un task fermato dal telefono, che resta sul telefono

Un task vivo che non gira: creato e pianificato, e **non** lanciato, resta `QUEUED`. `TRUSTED`, così
il telefono ne vede l'obiettivo:

```
uv run ela task create "da fermare" --privacy TRUSTED
```

```
uv run ela task plan <id> --file docs/examples/echo.json
```

Sul telefono, nella home, il gruppo «Vivi» ha «da fermare» con `QUEUED`. Toccalo: la seconda pagina
chiede la conferma. Ferma.

**Che cosa si deve vedere**: la home del telefono, e «da fermare» **è primo nel gruppo «Finiti»**, con
`CANCELLED`. È l'unico caso rotto prima di M17.2b che solo il telefono mostra: un task fermato dal
telefono spariva dal telefono nello stesso istante.

**Nella prova del 2026-09-27**: «da fermare» (`a0d9bd07…`), in `QUEUED`, fermato dal telefono, è il
primo dei finiti, con `CANCELLED`.

**Se non si vede così**: se «dormire troppo» manca da una delle due home, o non è primo al passo 4, o
«da fermare» manca dal telefono al passo 6, è il difetto di M17.2b che non è riparato su quella
superficie. Se una pagina d'arruolamento è arrivata
senza stile, salva dal Mac la risposta intera, intestazioni comprese, e portala nella review:

```
curl -s -D ~/Downloads/m17.2c-401-intestazioni.txt -o ~/Downloads/m17.2c-401.html http://127.0.0.1:<porta>/console
```

**La pulizia**, che fa parte della prova: togli `usr/bin/time` da `ELA_TERMINAL_PROGRAMS` e la riga
di `ELA_TERMINAL_TIMEOUT_SECONDS`, e riavvia. **Nella prova del 2026-09-27**: fatta, ed ELA
riavviato.

## 19. La parola degli step: la prova a mano di M6.3b

> **Eseguita dall'utente il 2026-09-28 a `f1861b3`**, su questo Mac (la porta era 8351). **Passati i
> passi 1–3.** Nata come bozza con la SPEC dello stesso giorno e allineata all'implementazione: la
> parola è `steps handled` (decisione 1), l'ADR è [0051](adr/0051-steps-handled.md), accettato dopo
> questa prova. Sotto ogni passo, **ciò che si deve vedere** è l'istruzione per chi la rifà, e **nella
> prova del 2026-09-28** ciò che è successo.

Una riparazione. `ela task run` stampava sotto `steps executed` anche lo step su cui ELA si era fermato
a chiedere, e quello step non era stato eseguito (§18, passo 4). La riga adesso si chiama `steps
handled`: gli step su cui, in quella corsa, ELA ha dato la sua risposta — eseguiti, falliti, negati, o
fermi sul tuo consenso.

È breve: l'esempio di §5 e §6 sul tuo ELA, con il suo `.env` com'è e il Core acceso dal codice del
branch (`uv run ela serve`). Il sì non si dà mai, quindi niente si scrive sul disco.

### 1. Una corsa che si ferma a chiedere

```
uv run ela task create "la parola degli step"
```

```
uv run ela task plan <id> --file docs/examples/first-task.json
```

```
uv run ela task run <id>
```

**Che cosa si deve vedere**, identico al blocco di §6:

```
outcome        waiting_approval
reason         —
state          WAITING_APPROVAL
steps handled  9c5b8f26-1a2b-4c3d-8e4f-000000000001, 9c5b8f26-1a2b-4c3d-8e4f-000000000002
stopped step   —
```

Il primo id è l'eco, eseguita; il secondo è lo step su cui ELA si è fermato a chiedere, e non è stato
eseguito. Se il telefono è arruolato (§13), la domanda suona anche lì: è atteso.

**Nella prova del 2026-09-28**: il task `8e837b0d-99c8-519d-a06b-2b9b2c31cb96`, con il piano di
`docs/examples/first-task.json`. La corsa è tornata con `outcome waiting_approval`, `reason —`, `state
WAITING_APPROVAL` e `steps handled 9c5b8f26-1a2b-4c3d-8e4f-000000000001,
9c5b8f26-1a2b-4c3d-8e4f-000000000002`: **identica al blocco di §6**. Gli id coincidono con quelli della
guida perché li fissa il file del piano.

### 2. Il no, e la corsa che trova il task chiuso

```
uv run ela approvals
```

```
uv run ela task deny <id> --approval <approval-id>
```

```
uv run ela task run <id>
```

**Che cosa si deve vedere**:

```
outcome        denied
reason         deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by 6c38f1c5-6cda-5680-8a7a-4f061588deed)
state          DENIED
steps handled  —
stopped step   —
```

Nessuno step trattato: la corsa ha trovato il task già chiuso dal tuo no — lo step che chiedeva l'ha chiuso la
risposta —, e la riga `reason` dice chi l'ha chiuso: `deny_by_approval`, con l'id dell'identità che ha risposto, che
dalla riga di comando è quello di `local`, la persona a questa macchina.

***Riscritto il 2026-10-02*** (M13.1c, ADR 0055): fino a M13.1c la riga era `reason —`, come nella prova qui sotto.

***Annotato il 2026-10-08*** (M13.1e, ADR 0059): da M13.1e, sotto la riga `reason` di un no, la corsa stampa anche
`answered by  the command line on the Core` — chi ha risposto, con il nome fisso del token del Core. Il blocco resta il
verbale del 2026-10-02.

**Nella prova del 2026-09-28**: `ela approvals` ha mostrato la domanda
`601ecd9c-d168-5fb5-834e-17d8984ba95b` — `workspace.write_note` su `workspace/notes/first-task.md`,
`LOW`. Il no ha portato il task a `DENIED`, e la corsa dopo è tornata con `outcome denied`, `reason —`,
`state DENIED` e `steps handled —`. È stata lanciata due volte, per errore, con la stessa uscita tutte e
due le volte: il file delle uscite la contiene due volte.

**Trovato qui, e non preso.** Il blocco di `ela approvals` stampato in questo passo ha le righe
`question expires`, `grant if you say yes` e `target`; quello di §6 mostra ancora `grant`, `expires` e
`file`, nell'ordine di prima di M13.1, che le ha cambiate con la correzione della sua prova a mano
(`f08bbfd`), e la frase sotto spiega il trattino di `file`. Non è una frase su `steps`: che cosa farne
lo decide il revisore.

***Annotato il 2026-10-02***: il blocco di §6 l'ha riparato **M13.1d**, e da allora un test confronta ogni
blocco di `ela approvals` della guida con ciò che la CLI stampa.

### 3. Che cosa dice l'help

```
uv run ela task run --help
```

**Che cosa si deve vedere**: la frase che dice che cosa è uno step trattato — «A step is handled when
the executor gave its answer about it in this call» —, e che la ragione di `denied` e `failed` c'è
quando la corsa l'ha ricevuta.

**Nella prova del 2026-09-28**: l'help di `ela task run` contiene la definizione di uno step trattato,
«``—`` means the run handled no step», e la frase che dice che la ragione di `denied` e `failed` c'è
quando la corsa l'ha ricevuta.

***Annotato il 2026-10-02*** (M13.1c, ADR 0055): da M13.1c l'help dice che `denied`, `failed`, `cancelled` ed
`expired` portano **sempre** il loro perché, lo stesso alla corsa che chiude il task e a ogni corsa dopo; «quando la
corsa l'ha ricevuta» non c'è più. Lo prova §22, passo 5.

Le uscite dei tre passi, integrali, in un file: `~/Downloads/m6.3b-prova.txt`. **Nella prova del
2026-09-28** ci sono le uscite dal `plan` in poi, scritte con `tee`.

## 20. Il browser: la prova a mano di M13.4

> **Bozza, scritta con la SPEC di M13.4 il 2026-09-29**, prima di ogni riga di codice, e allineata lo
> stesso giorno alle decisioni 1–14 della review: i comandi e le uscite attese sono quelli che la SPEC
> decide, e **allineata all'implementazione**: i piani sono in [`examples/`](examples/), e la suite li
> manda a ELA byte per byte (`tests/api/test_examples_browser.py`); le frasi dei messaggi sono quelle
> che il codice scrive. L'ADR è [0052](adr/0052-browser.md), `Proposta` fino a questa prova.

Da M13.4 ELA apre pagine in un browser suo. `browser.read` è `LOW`: dentro i siti che dichiari **non
chiede**, e fuori nega. `browser.act` — riempire dei campi e cliccare — è `HIGH`, come `fs.write` e
`terminal.run`: chiede **ogni volta**, e nessuna policy potrà coprirlo in anticipo.

**Prima di cominciare, una frase da leggere per intero.** Il browser di ELA è **vuoto** a ogni step:
nessun cookie, nessun login, niente del tuo Chrome o del tuo Safari — il sito vede un visitatore, non
te. Un sito che dichiari è un sito che ELA può **visitare senza chiederti niente**. E ciò che un click
manda — un modulo, un messaggio, un ordine — **non si riprende**: ELA non sa se un click manda qualcosa
prima di averlo fatto, e per questo te lo chiede ogni volta.

***Annotato il 2026-10-07*** (M14.2, [ADR 0058](adr/0058-planner.md) §9): **da M14.2 il piano lo può scrivere il
modello**, e una lettura è un GET che compone lui: può portare al sito dichiarato parole del tuo obiettivo, e se il
sito fa qualcosa su un GET, lo fa. `browser.read` resta `LOW` perché un piano del modello lo avvii tu, dopo averlo
letto con i suoi argomenti (§5); dichiara solo siti a cui una lettura non fa fare niente.

Cinque dei passi qui sotto **nessun test può farli al posto tuo**: il primo, perché il messaggio è
scritto per un essere umano; il quarto, perché la domanda si legge — sul telefono e in console — prima
di dire sì; il sesto e il settimo, perché un «ferma» e una fermata a metà di una pagina lenta si vedono
solo con due terminali; e l'ottavo, perché una difesa che nega prima della domanda si prova
**dall'assenza del campanello**.

La prova usa due siti veri: `example.com`, per leggere, e `httpbin.org`, che ha un modulo di prova e
rimanda indietro ciò che riceve — se lo tenga non si sa; ciò che riceve è un marcatore innocuo. **Il
passo 4 invia davvero un modulo** a `httpbin.org`. Se `httpbin.org` risponde con un errore `5xx`, il
passo si ripete più tardi, **senza cambiare sito**.

**Mai una password o una carta in un piano.** ELA rifiuta di scrivere in un campo che si dichiara
password o carta, ma il rifiuto arriva **dopo** il sì: il valore sarebbe già nel piano, nella domanda
— anche sul telefono — e nella tabella delle approvazioni, che non si cancella. E il riconoscimento è
parziale: una password in un campo di testo qualunque passa.

### 0. Lo shell di Chromium

```
uv sync --locked
```

```
uv run playwright install --only-shell chromium
```

**Che cosa si deve vedere**: due scaricamenti, «Chrome Headless Shell 153.0.8010.12» e «FFmpeg», da
`cdn.playwright.dev`, in `~/Library/Caches/ms-playwright`. Una volta sola per macchina, e di nuovo
quando il lock porta una versione nuova di Playwright.

```
ls ~/Library/Caches/ms-playwright
```

```
chromium_headless_shell-1243
ffmpeg-1011
```

### 1. ELA che non parte — il messaggio che devi leggere

Senza `ELA_BROWSER_SITES` nel `.env`:

```
uv run ela serve
```

**Che cosa si deve vedere**: ELA non parte, e il messaggio nomina la variabile, dice la riga da
scrivere — un nome di sito per voce, senza `https://` — e dice che `[]` è una risposta ammessa,
«nessun sito», e non un errore. Leggilo per intero: se una frase ti costringe a rileggere, è un
difetto da riportare.

```
uv run ela init; echo "exit $?"
```

**Che cosa si deve vedere**: il file c'è già e non si tocca; `ELA_BROWSER_SITES` è nominata fra le
righe che mancano, e `exit 2`.

### 2. I siti, nel `.env`

```
ELA_BROWSER_SITES=["example.com", "httpbin.org"]
```

Un sito è **se stesso e basta**: `www.example.com` non è `example.com`, e si dichiara a parte. Poi:

```
uv run ela serve
```

### 3. Una lettura senza domanda, un sito che non hai dichiarato, e una pagina che porta altrove

```
uv run ela task create "leggere una pagina"
```

```
uv run ela task plan <id> --file docs/examples/browser-read.json
```

```
uv run ela task run <id>
```

**Che cosa si deve vedere**: nessuna domanda, nessun campanello:

```
outcome        completed
reason         —
state          COMPLETED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000001
stopped step   —
```

```
uv run ela task results <id>
```

**Che cosa si deve vedere**: l'indirizzo `https://example.com/`, lo stato `200`, il titolo «Example
Domain» e il testo del paragrafo, «This domain is for use in documentation examples…». Il verifier
l'ha riletto sulla pagina, non dal risultato. (Il piano legge `body > p:first-of-type`: il 2026-09-30
la pagina non ha un `<h1>`, e il suo JavaScript le aggiunge altri paragrafi, dove `p` sarebbe
`browser.element_ambiguous`. Se example.com cambia ancora, è il piano da correggere, non ELA.)

Poi, in un task nuovo, `browser-read-outside.json` — `example.org`, che non hai dichiarato:

```
outcome        denied
reason         deny_by_decision: EXECUTING -> DENIED (targets ['example.org'] of browser.read are not within scope ['example.com', 'httpbin.org'])
state          DENIED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000002
stopped step   —
```

E in un task nuovo `browser-left-site.json`: `httpbin.org` è dichiarato, ma la pagina manda il
browser su `example.org`.

```
outcome        failed
reason         fail: EXECUTING -> FAILED (browser.left_site: the page of httpbin.org went to https://example.org, which is not a declared site: the browser did not follow, and nothing was sent there)
state          FAILED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000003
stopped step   —
```

### 4. Un modulo, e la domanda da leggere prima del sì

Due giri, come in §15, passo 6: **uno `LOCAL_ONLY`**, il default, a cui si risponde dal Mac, e **uno
`TRUSTED`**, a cui si risponde dal telefono.

**Il giro `LOCAL_ONLY`, risposto dal Mac.**

```
uv run ela task create "inviare un modulo di prova"
```

```
uv run ela task plan <id> --file docs/examples/browser-act.json
```

```
uv run ela task run <id>
```

```
outcome        waiting_approval
reason         —
state          WAITING_APPROVAL
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000005
stopped step   —
```

```
uv run ela approvals
```

**Che cosa si deve vedere**, in `ela approvals` e nell'Approval Center (§14), **tutto**: il sito,
`httpbin.org`; l'indirizzo per intero, `https://httpbin.org/forms/post`; i gesti, **come una lista**
— `["fills input[name=custname] with “ELA prova 7431”", "clicks form button"]`: fra parentesi quadre,
ogni gesto fra virgolette, come le tre superfici scrivono gli argomenti di un comando (M13.2,
decisione 12), perché un valore non possa travestirsi da un gesto in più —; il testo atteso; i 30
secondi; e la frase che dice che il browser è vuoto, che il sito vede un visitatore e non te, e che
ciò che manda non si riprende. Una superficie che non mostra tutto non deve offrire il sì.

**Sul telefono** (§13) la domanda c'è, ma il sì no: il task è `LOCAL_ONLY`, e la pagina dice

```
Il contenuto resta sul Mac: rispondi da lì.
```

**Non è un difetto: è la regola che funziona** (§15, passo 6). Si risponde dal Mac:

```
uv run ela task approve <id> --approval <approval-id>
```

```
uv run ela task run <id>
```

```
outcome        completed
reason         —
state          COMPLETED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000005
stopped step   —
```

`uv run ela task results <id>`: lo stato della pagina del modulo, `200`, e due gesti fatti — il campo
e il click. La pagina dopo il click non la riporta il tool: l'ha guardata il verifier, che ha visto
comparire il testo atteso. E il marcatore **non** è nell'audit:

```
uv run ela audit tail --task <id> -n 30 --json | grep -c "ELA prova 7431"
```

```
0
```

**Il giro `TRUSTED`, risposto dal telefono.** In un task nuovo, creato più largo:

```
uv run ela task create "inviare un modulo dal telefono" --privacy TRUSTED
```

```
uv run ela task plan <id> --file docs/examples/browser-act.json
```

```
uv run ela task run <id>
```

**Che cosa si deve vedere**: con l'iPhone aperto sulla pagina del companion (§13), il campanello
suona, e la pagina mostra **tutti i campi** che mostra `ela approvals` — il sito, l'indirizzo, i gesti
come lista, il testo atteso, il tempo, la frase — **e offre il sì**. Rispondi dal telefono: il sì fa
ripartire il task nella stessa richiesta, fino a `COMPLETED`, e `uv run ela task show <id>` lo dice.

### 5. Un bottone che non c'è

In un task nuovo, `browser-act-missing.json`: il sì, poi di nuovo `run`.

```
outcome        failed
reason         fail: EXECUTING -> FAILED (browser.element_missing: gesture 2 of 2 names no element on the page of httpbin.org; no gesture was made)
state          FAILED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000006
stopped step   —
```

**Che cosa si deve vedere**: la frase dice che nessun gesto è stato fatto — il controllo di ogni
elemento viene prima del primo gesto, e sulla pagina non lo vedi, perché ELA l'ha chiusa —, e il sì è
speso: la domanda è nata prima che ELA aprisse la pagina, e questo è il suo prezzo.

### 6. Il «ferma» a metà corsa, com'è oggi

> **Superato da M6.3c** (§21, ADR 0054 §11): questo passo mostra il difetto com'era quando M13.4 è stata
> provata, e da M6.3c non si riproduce più. Il «ferma» arriva al browser prima della navigazione o prima del
> primo gesto; `run` risponde `cancelled`, **mai `409`**, con la ragione del «ferma» — anche alla porta, dove
> era vuota — e con la riga `stopped step`; e uno step che aveva già agito si chiude come uno step normale. Le
> uscite qui sotto restano quelle di allora.

Nel terminale A, in un task nuovo con `browser-read-slow.json` — una pagina che risponde dopo otto
secondi:

```
uv run ela task run <id>
```

E nel terminale B, **circa tre secondi dopo l'Invio di `run`** — non subito: lo step deve essere
cominciato —, e prima che passino gli otto secondi:

```
uv run ela task cancel <id>
```

Un «ferma» dato subito dopo l'Invio arriva **prima che lo step cominci**, e `run` risponde così:

```
outcome        cancelled
reason         —
state          CANCELLED
steps handled  —
stopped step   —
```

Nessuno step trattato, e il `reason` vuoto è quello di M13.1c: il caso di M6.3c **non si vede**.
Rifallo in un task nuovo, aspettando i tre secondi.

***Annotato il 2026-10-02*** (M13.1c, ADR 0055): quel vuoto **non era di M13.1c**, che esclude `cancelled` — lo
dice già ADR 0054 §14 —, e da M6.3c non c'è più: la ragione di un «ferma» sono le sue parole. Il blocco resta il
verbale del 2026-09-30.

**Che cosa si deve vedere**, con i tre secondi: il «ferma» risponde; **il browser no** — la visita finisce —, e nel
terminale A `run` torna con il rifiuto dell'API — un `409`, che la riga di comando chiama `conflict` — ed
esce con `1`:

```
ela: conflict: task <id>: complete_step needs an EXECUTING task, not CANCELLED
```

Poi:

```
uv run ela task show <id>
```

il task `CANCELLED` e lo step **ancora `RUNNING`**; e `uv run ela task results <id>` ha un risultato
`SUCCEEDED`. **Non è il comportamento giusto**: è il difetto di M6.3c, scritto com'è — e con
`browser.act` vorrebbe dire un modulo inviato dopo il «ferma». M13.4 non lo ripara; M6.3c, la milestone
dopo, sì, e porta anche la fermata del browser prima del primo gesto.

**I nomi dell'ambiente del driver** — i nomi soltanto, mai i valori — hanno **un giro loro, con un
task loro**: in otto secondi non stanno insieme un «ferma» e un `ps`. In un task nuovo con
`browser-read-slow.json`, `run` nel terminale A, e durante gli otto secondi, dal terminale B:

```
ps eww -o command= -p "$(pgrep -f 'driver/node.*run-driver')" | tr ' ' '\n' | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' | cut -d= -f1 | sort
```

**Che cosa si deve vedere**: le variabili della tua shell — `SSH_AUTH_SOCK` compresa, se la tua shell
l'ha: è dichiarato in ADR 0052 §14, e il browser non la riceve —, quelle che `uv` aggiunge e quelle di
Playwright (`PW_…`); **nessuna `ELA_`**, perché ELA legge il `.env` e non lo esporta, e **nessuna
`NODE_`**, perché il Core le toglie dal proprio ambiente quando parte. Se ne compare una, è un difetto
da riportare prima di andare avanti.

Se il comando risponde `ps: Invalid process id:`, seguito da qualche carattere senza senso, **nessun
driver stava girando**: gli otto secondi erano passati, o `run` non era ancora partito. Non c'è niente
da leggere; rifai il giro.

### 7. ELA si ferma con un browser aperto

Di nuovo `browser-read-slow.json` in un task nuovo, `run` nel terminale A, e durante gli otto secondi
**Ctrl-C nel terminale di `ela serve`**. Poi, dal terminale B:

```
pgrep -fl chrome-headless-shell
```

**Che cosa si deve vedere**: niente — nessun browser rimasto. Nel terminale A la corsa è tornata,
perché ELA, fermandosi, finisce le richieste che ha in corso:

```
outcome        failed
reason         fail: EXECUTING -> FAILED (browser.stopped: ELA stopped while the page of httpbin.org was open)
state          FAILED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000004
stopped step   —
```

`browser.stopped`, e non `browser.timeout` né `browser.failed`: il Ctrl-C arriva anche al driver di
Playwright, e ELA lo lancia in modo che non chiuda il browser da sé (la misura M5-bis della SPEC).

### 8. Lo shell che manca: il campanello che non suona

Ferma ELA, e riaccendila con i browser in una cartella vuota:

```
PLAYWRIGHT_BROWSERS_PATH=/tmp/nessun-browser uv run ela serve
```

In un task nuovo, `browser-act.json`, e `run`:

**Che cosa si deve vedere**: `failed` con `browser.not_installed`, e una frase che dice di lanciare
`uv run playwright install --only-shell chromium`; `uv run ela approvals` **non** ha una domanda nuova,
e il telefono **non** suona. Poi riaccendi ELA com'era.

### 9. Il PC sul branch: la ruota che niente lancia

Il browser non va sul PC, ma **la ruota di Playwright sì** — con un `node.exe` dentro — a ogni
`uv sync`, e il processo del nodo importa l'adapter del browser senza costruirlo. Che lo Smart App
Control lasci stare il nodo è un fatto del PC, e si prova qui, **prima del merge**. Il `.env` del PC
**resta com'è**: il nodo non legge né chiede `ELA_BROWSER_SITES`.

Sul PC:

```powershell
cd $HOME\ELA
git fetch
git checkout m13.4-browser
uv sync --locked
Test-Path .venv\Lib\site-packages\playwright\driver\node.exe
uv run python -m ela.cli node run
```

**Che cosa si deve vedere**: `True` — la ruota è arrivata —, e il nodo che parte come sempre, senza
nessun «Un criterio di controllo dell'applicazione ha bloccato il file». Sul Mac:

```
uv run ela device list
```

**Che cosa si deve vedere**: la riga del PC disponibile, come in §12. E sul PC, da un'altra finestra
di PowerShell, nessun `node` in esecuzione:

```powershell
Get-Process node -ErrorAction SilentlyContinue
```

Poi il PC torna a `main` quando il branch è mergiato.

Le uscite di tutti i passi, integrali, in un file: `~/Downloads/m13.4-prova.txt`, e quelle del PC in
`~/Downloads/m13.4-prova-pc.txt`.

## 21. Il «ferma» a metà corsa: la prova a mano di M6.3c

> **Scritta con l'implementazione di M6.3c il 2026-10-01**, dalla bozza della SPEC
> (`milestones/M6.3c.md`, proposta 10) e con le decisioni della sua review. **Fatta da Tommaso il
> 2026-10-02 sul branch**: i passi del Mac sono passati, e il passo 8 — il PC — è il debito datato di
> [ADR 0054](adr/0054-stopped-midway.md) §16, da pagare **domenica 2026-10-04**, dopo il merge, con il Mac e
> il PC su `main`: lo script intero, una volta, e un file che dice «La prova è passata».

Da M6.3c il «ferma» — `ela task cancel`, il bottone della console, quello del telefono — **arriva al tool
che sta girando**, prima del suo punto di non ritorno: un browser che non ha ancora fatto il primo gesto non
lo fa, un programma che non è ancora partito non parte. Se il tool l'ha già passato, lo step si chiude come uno
step normale, e **ogni superficie dice che cosa aveva fatto lo step in corso**: la riga `stopped step` della
riga di comando, la frase della console e quella del telefono.

**È la prima prova a mano con uno script.** I passi meccanici — creare i task, farli girare, guardare lo step,
mandare il «ferma» nell'istante giusto, confrontare ogni uscita con quella attesa — li fa
`scripts/prova_m6_3c.py`, che **legge da questa sezione i comandi, che cosa guardare e le uscite attese**: la
guida resta la fonte di verità, e `tests/docs/test_prova_m6_3c.py` tiene allineati i due. I blocchi che lo
script legge hanno sopra un marcatore, `<!-- prova: N.tipo -->`, che il Markdown non mostra:

| Tipo | Che cosa fa lo script |
|---|---|
| `comando` | fa girare le righe una per una; `<id>` è l'id del task che il passo ha creato. Prima del «ferma», l'ultima riga gira mentre lo script guarda |
| `guarda` | guarda finché vede il segno, o finché il task finisce da sé: `processo <modello>` è un processo nuovo la cui riga di comando contiene il modello, `risultato STARTED` è la `STARTED` dello step fra i risultati del task — `su un nodo` vuole che l'abbia scritta un nodo e non il Mac —, `stato CANCELLED` è il task fermato |
| `ferma` | manda il «ferma» — `POST /tasks/<id>/cancel`, con «la prova di M6.3c» — e dice il lato dove deve cadere: prima dello step, prima del tool, prima del punto o dopo il punto |
| `atteso` | le righe che l'uscita del comando sopra deve avere: ciascuna a parole intere, dentro una riga dell'uscita e a meno degli spazi — «0» non è dentro «10» —, e nell'ordine in cui sono scritte |
| `mano` | ciò che fai tu: lo script lo stampa e non aspetta un Invio — lo verifica il `guarda` che lo segue |
| `occhio` | ciò che guardi tu: lo script lo chiede finché rispondi `s` o `n` — o «si», «sì», «no» —, e scrive la tua risposta come GUARDATO |
| `richiede` | ciò che il passo vuole dal mondo, verificato dallo script e mai chiesto: `un nodo disponibile` lo legge da ELA, `il Mac a batteria` da `pmset -g batt`; se manca, il passo è SALTATO con ciò che manca |

Lo script manda il «ferma» **quando vede lo step in corso**, non dopo un'attesa fissa; poi aspetta che lo step
in corso si chiuda, e solo allora confronta. Legge dalla trail e dai risultati **dove** è caduto il «ferma»; se
non è caduto dal lato atteso — o se il task è finito da sé prima che lo step si vedesse — stampa **DA RIPETERE**
con il lato vero e **ripete il passo da sé**, con un task nuovo, fino a tre giri: è **FALLITO** solo se sbaglia
anche il terzo, e il file dice a che giro il passo è passato — «PASSATO al secondo giro» non è «PASSATO». Non è
un difetto di ELA: in una prova vera un browser parte più o meno in fretta, e i due lati di ogni tool li provano
i test. **L'ultima riga** conta i PASSATO con i loro giri, i FALLITO, i GUARDATO con un no e i SALTATO, e dice
«La prova è passata» solo senza FALLITO, senza SALTATO e con ogni GUARDATO un sì; altrimenti dice che cosa manca.
Dove una domanda nomina il task di un altro passo, `<id del passo 2>` e gli altri, lo script scrive l'id del suo
ultimo giro: fra i finiti, i giri ripetuti lasciano più righe che passi. **A te restano la console e il
telefono**: il sì ai passi `HIGH` e il «ferma» dei passi 5 e 6 li dai lì — lo script vede da sé quando sono
fatti, e aspetta finché non lo sono —, e lì guardi gli esiti. Ciò che guardi lo script non lo giudica: te lo
chiede, e lo scrive.

### 0. Prima di cominciare

Il Mac sul codice da provare — il branch prima del merge, `main` per il giro di domenica che paga il debito
del passo 8 —, e lo shell di Chromium com'era in §20, passo 0. Sul branch:

```
git fetch
git checkout m6.3c-ferma-a-meta-corsa
uv sync --locked
```

Dopo il merge, su `main`:

```
git checkout main
git pull
uv sync --locked
```

Nel `.env`, **due righe in più** rispetto a §20:

```
ELA_BROWSER_SITES=["example.com","httpbin.org"]
ELA_TERMINAL_PROGRAMS=["bin/sleep"]
```

Se `ELA_TERMINAL_PROGRAMS` dichiara già altri programmi, aggiungi `bin/sleep` a quelli; e se avevi abbassato
`ELA_TERMINAL_TIMEOUT_SECONDS` per §16, rimettilo sopra i 97 secondi. `bin/sleep` serve a un piano solo,
[`examples/terminal-stop.json`](examples/terminal-stop.json): **toglilo alla fine**, dopo il giro di domenica
(passo 9). Poi, nel
terminale A:

```
uv run ela serve
```

E apri la console nel browser del Mac (§14) e la home del telefono (§13).

### 1. Lo script

Nel terminale B:

```
uv run python scripts/prova_m6_3c.py
```

**Che cosa si deve vedere**: lo script controlla che ELA risponda, che lo shell di Chromium ci sia, che i due
siti e `bin/sleep` siano dichiarati nel `.env` e che il tempo massimo di un comando superi i 97 secondi, e
stampa **PASSATO** per ciascuno. Se una riga dice **FALLITO**, si ferma lì con l'uscita vera: si ripara il
`.env`, si riavvia `ela serve` e si rilancia. Tutto ciò che stampa finisce anche in un file in `~/Downloads`,
`prova-m6.3c-` con la data e l'ora nel nome (`--out` per un altro). I passi che seguono li fa lo script, in
quest'ordine; qui sotto c'è ciò che legge.

> ***Annotato il 2026-10-02*** (decisione 2-bis della review di M13.1c, M13.1d e M9.6): **dal merge del branch
> `m13.1c-m13.1d-m9.6`**, ciò che manca al passo 1 non dice più **FALLITO**: il passo 1 è **SALTATO** con ciò che
> manca — «la prova richiede «…», e non è così» —, lo script si ferma lì, e l'ultima riga dice «La prova non è
> passata: il passo 1 SALTATO.». Ciò che il passo 1 controlla è ciò che la prova richiede al mondo, non un
> comportamento di ELA, e un FALLITO sembrerebbe di ELA. Il rimedio è lo stesso: si ripara il `.env`, si riavvia
> `ela serve` e si rilancia. Il giro di domenica 2026-10-04 usa lo script di `main`, com'è scritto sopra.

> ***Annotato il 2026-10-05*** (decisioni Q, R e S della review del giro su `main` del 2026-10-05, ADR 0055 §7):
> **dal merge del branch `m13.1c-m13.1d-m9.6`**, tre cose cambiano, nello script e qui.
>
> - **Q. Il passo 8 ha un esempio suo**,
>   [`examples/speak-on-a-node-to-the-end.json`](examples/speak-on-a-node-to-the-end.json), con una frase che non
>   dà istruzioni a chi ascolta. Quella di
>   [`examples/speak-on-a-node.json`](examples/speak-on-a-node.json) è scritta per §12 e chiede di premere Ctrl-C:
>   il 2026-10-05 è stato premuto sulla finestra di `ela serve`, e ELA si è fermato a metà giro. Una frase scritta
>   per una prova non si riusa in un'altra che chiede il contrario. §12 resta com'è.
> - **R. Se ELA smette di rispondere a metà giro, lo script non crolla**: scrive nel file
>   «[N] INTERROTTO: ELA ha smesso di rispondere — …» al passo in cui è successo, non fa i passi che restano, e
>   l'ultima riga dice «La prova non è passata: ELA ha smesso di rispondere al passo N.»; l'uscita è 1. Fino a R,
>   il traceback andava sul terminale e il file restava senza l'ultima riga.
> - **S. Ai passi 5 e 6, un «Ferma» dato dalla superficie sbagliata si rifà**: la ragione nomina la superficie che
>   ha fermato il task, con le parole che la console e il telefono scrivono; se non è quella che il passo chiede,
>   lo script stampa **DA RIPETERE** — «il passo umano non è stato fatto come chiesto: la ragione dice «…», il
>   passo chiede «…»» — e rifà il passo con un task nuovo, come per un «ferma» caduto dal lato sbagliato,
>   fino a tre giri. Non è un difetto di ELA, che ha scritto il vero; ogni altra differenza della ragione resta
>   un **FALLITO**.

> ***Annotato il 2026-10-06*** (decisione U della review della prova di §22): **dal merge del branch
> `m13.1c-m13.1d-m9.6`**, a una domanda dell'occhio lo script prende anche «si» e «sì» per sì e «no» per no, oltre
> a `s` e `n`; ogni altra risposta, vuota compresa, la richiede ancora.

### 2. `browser.read`, fermato prima della navigazione

Lo script crea un task con [`examples/browser-read.json`](examples/browser-read.json), stampa il suo id, lo fa
girare con `ela task run`, e manda il «ferma» **appena vede un processo nuovo dello shell di Chromium**: il tool
sta avviando il browser, e `example.com` non ha ancora visto niente.

<!-- prova: 2.comando -->
```
uv run ela task create "la prova di M6.3c: browser.read" --json
uv run ela task plan <id> --file docs/examples/browser-read.json
uv run ela task run <id>
```

<!-- prova: 2.guarda -->
```
processo chrome-headless-shell
```

<!-- prova: 2.ferma -->
```
prima del punto
```

**Che cosa si deve vedere**, nell'uscita di `run`: `cancelled`; la ragione con le parole del «ferma», mai
vuota; lo step trattato; e `stopped step` che dice che lo step in corso non aveva agito.

<!-- prova: 2.atteso -->
```
outcome        cancelled
reason         cancel: EXECUTING -> CANCELLED (la prova di M6.3c)
state          CANCELLED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000001
stopped step   had not acted
```

E fra i risultati, uno solo: `CANCELLED`, con `execution.stopped`.

<!-- prova: 2.comando -->
```
uv run ela task results <id>
```

<!-- prova: 2.atteso -->
```
b4c2d7e1-5a3f-4b69-8d20-000000000001 browser.read CANCELLED browser-read
error execution.stopped
```

### 3. `browser.act`, fermato prima del primo gesto

Lo script crea un task con [`examples/browser-act.json`](examples/browser-act.json), stampa il suo id e lo fa
girare: è `HIGH`, e arriva la domanda.

<!-- prova: 3.comando -->
```
uv run ela task create "la prova di M6.3c: browser.act" --json
uv run ela task plan <id> --file docs/examples/browser-act.json
uv run ela task run <id>
```

<!-- prova: 3.mano -->
```
Dai il sì dalla console: apri la domanda come in §20, passo 4, e premi «Sì».
```

La console fa ripartire il task nella stessa richiesta; lo script guarda da quando la domanda è nata, e manda il
«ferma» **appena vede la `STARTED` dello step**: il tool sta aprendo la pagina, e nessun campo è stato toccato.

<!-- prova: 3.guarda -->
```
risultato STARTED
```

<!-- prova: 3.ferma -->
```
prima del punto
```

**Che cosa si deve vedere**: lo step `CANCELLED`, `stopped step` che dice che non aveva agito; i risultati
`STARTED` e poi `CANCELLED` con `execution.stopped`. `httpbin.org` non ha ricevuto nessun modulo, e la console,
dopo il sì, atterra sul riassunto del task.

<!-- prova: 3.comando -->
```
uv run ela task show <id>
```

<!-- prova: 3.atteso -->
```
state CANCELLED
stopped step had not acted
b4c2d7e1-5a3f-4b69-8d20-000000000005 CANCELLED
```

<!-- prova: 3.comando -->
```
uv run ela task results <id>
```

<!-- prova: 3.atteso -->
```
b4c2d7e1-5a3f-4b69-8d20-000000000005 browser.act STARTED browser-act
b4c2d7e1-5a3f-4b69-8d20-000000000005 browser.act CANCELLED browser-act
error execution.stopped
```

### 4. `terminal.run`, fermato dopo l'`exec`

Lo script crea un task `TRUSTED` con [`examples/terminal-stop.json`](examples/terminal-stop.json) — `/bin/sleep
97` —, perché il telefono offra il sì e ne mostri lo scopo, e lo fa girare fino alla domanda.

<!-- prova: 4.comando -->
```
uv run ela task create "la prova di M6.3c: terminal.run" --privacy TRUSTED --json
uv run ela task plan <id> --file docs/examples/terminal-stop.json
uv run ela task run <id>
```

<!-- prova: 4.mano -->
```
Dai il sì dal telefono: apri la domanda dalla home, e premi «Sì».
```

Lo script manda il «ferma» **quando vede `sleep 97` nella tabella dei processi**: il programma è partito, e il
punto di non ritorno è passato.

<!-- prova: 4.guarda -->
```
processo sleep 97
```

<!-- prova: 4.ferma -->
```
dopo il punto
```

**Che cosa si deve vedere**: lo step `FAILED`, e `stopped step` che dice che lo step in corso aveva già agito e
che nessuna verifica ne ha constatato l'effetto; il risultato `FAILED` con `terminal.stopped`, e `ended` che
nomina la fermata del task. Il telefono, dopo il sì, torna alla home.

<!-- prova: 4.comando -->
```
uv run ela task show <id>
```

<!-- prova: 4.atteso -->
```
state CANCELLED
stopped step had acted; its effect was not verified
c6d3e2f1-7a48-4c3b-9e05-000000000001 FAILED
```

<!-- prova: 4.comando -->
```
uv run ela task results <id>
```

<!-- prova: 4.atteso -->
```
c6d3e2f1-7a48-4c3b-9e05-000000000001 terminal.run FAILED terminal-run
ended stopped_with_the_task
error terminal.stopped
```

**Nessun `sleep 97` resta vivo**: lo script lo conta nella tabella dei processi.

<!-- prova: 4.comando -->
```
ps -axo command= | grep -c "[s]leep 97"
```

<!-- prova: 4.atteso -->
```
0
```

### 5. La console

Lo script crea un task con [`examples/echo.json`](examples/echo.json), stampa il suo id, e lo lascia `QUEUED`.

<!-- prova: 5.comando -->
```
uv run ela task create "la prova di M6.3c: la console" --json
uv run ela task plan <id> --file docs/examples/echo.json
```

<!-- prova: 5.mano -->
```
Nella console, apri il task con l'id che lo script ha stampato e premi «Ferma»; leggi la conferma, poi premi «Ferma il task». Lo script aspetta finché vede il task fermato.
```

<!-- prova: 5.guarda -->
```
stato CANCELLED
```

<!-- prova: 5.occhio -->
```
La conferma dice che nessuno step nuovo partirà, che uno step che ha già agito può finire ciò che ha cominciato, e che il riassunto del task dirà se aveva agito — e non più «il task non farà più niente»?
```

Lo script controlla da sé che il task sia `CANCELLED` con la ragione della console:

<!-- prova: 5.comando -->
```
uv run ela task run <id>
```

<!-- prova: 5.atteso -->
```
outcome        cancelled
reason         cancel: QUEUED -> CANCELLED (fermato dal Command Center)
state          CANCELLED
steps handled  —
stopped step   —
```

E ti chiede di guardare la home della console, dove fra i finiti ci sono i task dei passi 2–4, ciascuno con la
sua frase: lo script ti dà i loro id.

<!-- prova: 5.occhio -->
```
Fra i finiti della console: i task <id del passo 2> e <id del passo 3> dicono «Fermato prima che lo step in corso agisse.», e <id del passo 4> «Fermato, ma lo step in corso aveva già agito: nessuna verifica l'ha constatato.»?
```

<!-- prova: 5.occhio -->
```
Nel riassunto di <id del passo 2>, <id del passo 3> e <id del passo 4> la stessa frase sta accanto a «Lo step in corso», e nel piano nessuno step è disegnato come in corso?
```

### 6. Il telefono

Lo script crea un altro task come al passo 5.

<!-- prova: 6.comando -->
```
uv run ela task create "la prova di M6.3c: il telefono" --json
uv run ela task plan <id> --file docs/examples/echo.json
```

<!-- prova: 6.mano -->
```
Sul telefono, apri dalla home il task con l'id che lo script ha stampato e premi «Ferma»; leggi la conferma, poi premi «Ferma il task». Lo script aspetta finché vede il task fermato.
```

<!-- prova: 6.guarda -->
```
stato CANCELLED
```

<!-- prova: 6.occhio -->
```
La conferma dice che la riga del task, fra i finiti, dirà se aveva agito?
```

<!-- prova: 6.comando -->
```
uv run ela task run <id>
```

<!-- prova: 6.atteso -->
```
outcome        cancelled
reason         cancel: QUEUED -> CANCELLED (fermato dall'iPhone)
state          CANCELLED
steps handled  —
stopped step   —
```

I task dei passi 2 e 3 sono `LOCAL_ONLY`, e il telefono li mostra con l'id che lo script ha stampato; quello del
passo 4 con il suo scopo. La frase c'è per tutti e tre: dice che cosa aveva fatto lo step, niente del contenuto.

<!-- prova: 6.occhio -->
```
Fra i finiti della home del telefono, i task <id del passo 2>, <id del passo 3> e <id del passo 4> hanno le stesse frasi della console?
```

### 7. Il PC su `main`, per il giro di domenica

Il passo 8 manda uno step al PC, e si fa **dopo il merge, con il Mac e il PC su `main`**: è il giro che paga il
debito di ADR 0054 §16. Il protocollo fra il Core e il nodo non cambia, ma `src/ela/node/runner.py` sì — la
fermata che non si alza mai, che il nodo dà ai suoi tool —, ed è per questo che il PC gira dal codice mergiato,
non da quello di prima. Sul PC, con il nodo fermo (Ctrl-C nella sua finestra):

```powershell
cd $HOME\ELA
git checkout main
git pull
uv sync --locked
uv run python -m ela.cli node run
```

**Che cosa si deve vedere**: il nodo che parte come sempre, e sul Mac la riga del PC disponibile in `uv run ela
device list`. Poi lo script, intero, una volta (passo 1): i passi del Mac rifanno ciò che il 2026-10-02 è
passato, e il passo 8 è quello nuovo.

### 8. Lo step che un nodo ha preso

Con il PC acceso e disponibile, e il Mac a batteria perché il lavoro vada al PC (§12, passo 6), lo script crea
un task `TRUSTED` con [`examples/speak-on-a-node-to-the-end.json`](examples/speak-on-a-node-to-the-end.json), che
va al PC. Le due condizioni le verifica lo script, prima di cominciare: il PC lo legge da ELA, la batteria dal Mac.
**La frase non chiede niente a chi ascolta**: il PC va lasciato parlare fino in fondo. Non è quella di §12, che
chiede di premere Ctrl-C (decisione Q, nella nota del passo 1).

<!-- prova: 8.richiede -->
```
un nodo disponibile
il Mac a batteria
```

<!-- prova: 8.comando -->
```
uv run ela task create "la prova di M6.3c: il nodo" --privacy TRUSTED --json
uv run ela task plan <id> --file docs/examples/speak-on-a-node-to-the-end.json
uv run ela task run <id>
```

<!-- prova: 8.mano -->
```
Dai il sì dal telefono.
```

Dopo il sì il lavoro va al PC, e lo script manda il «ferma» **quando vede la `STARTED` che la presa del PC
scrive**: la busta è uscita, ed è il punto di non ritorno di uno step su un nodo. Se la `STARTED` l'ha scritta il
Mac, lo step è girato qui: il passo è **FALLITO** con «lo step è girato sul Mac, non sul PC», senza un altro giro,
che farebbe la stessa cosa.

<!-- prova: 8.guarda -->
```
risultato STARTED su un nodo
```

<!-- prova: 8.ferma -->
```
dopo il punto
```

**Che cosa si deve vedere**: il PC parla fino in fondo — il «ferma» non arriva al nodo —, consegna, e lo step si
chiude come uno step normale; lo script aspetta la consegna prima di confermare.

<!-- prova: 8.comando -->
```
uv run ela task show <id>
```

<!-- prova: 8.atteso -->
```
state CANCELLED
stopped step had acted; its verification passed
5a1e0c3d-7b2f-4e8a-9c41-000000000002 COMPLETED
```

**Che cosa si deve vedere**, alla fine dello script: i passi meccanici **PASSATO**, quelli a occhio **GUARDATO**
con le tue risposte, e l'ultima riga che dice «La prova è passata». Quel file salda il debito; se il passo 8
fallisce, si apre una riparazione con la sua lettera.

> ***Annotato il 2026-10-05***: **il debito è saldato** da ADR 0055 §7, con il giro su `main` del 2026-10-05 — un
> giorno dopo la data di ADR 0054 §16 —, dove il passo 8 è PASSATO sul PC. Il criterio di sopra, «un file che dice
> «La prova è passata»», è rivisto lì: il debito era il passo 8, e lo salda il passo 8.

### 9. Alla fine

**Dopo il giro di domenica**, non prima: togli `bin/sleep` da `ELA_TERMINAL_PROGRAMS`, e riavvia `ela serve`. I
file dello script restano in `~/Downloads`.

## 22. Le ragioni, il blocco delle domande e niente di Tommaso: la prova a mano di M13.1c, M13.1d e M9.6

> **Scritta con le SPEC del 2026-10-02** (`milestones/M13.1c.md`, `M13.1d.md`, `M9.6.md`) e **allineata con
> l'implementazione** il 2026-10-02: i passi 2–6 li fa girare la suite con lo script stesso, su un ELA nello stesso
> processo, con il browser finto (`tests/cli/test_section_22_on_the_cli.py`). La si fa sul Mac, sul branch
> `m13.1c-m13.1d-m9.6`, con lo script `scripts/prova_m13_1c_m13_1d_m9_6.py`. Il PC non serve. **Fatta da Tommaso il
> 2026-10-06 sul branch**, a `b589b68`: passata, ogni passo al primo giro
> (`~/Downloads/prova-m13.1c-m13.1d-m9.6-20261006-122115.txt`); [ADR 0055](adr/0055-the-reason-of-an-end.md) e
> [ADR 0056](adr/0056-the-author-is-not-in-the-product.md) sono Accettate.

Tre riparazioni, una prova. **M13.1c**: un diniego e un fallimento dicono il loro perché, e lo dicono uguale alla
corsa che chiude il task e a ogni corsa dopo — le parole della transizione che l'ha chiuso, come per un «ferma» da
M6.3c. **M13.1d**: il blocco di `ela approvals` di §6 è quello che la CLI stampa. **M9.6**: le voci che hai scelto
per l'audizione stanno nel tuo `.env`, non nel codice, e il saluto del design system non porta il tuo nome.

Lo script legge da questa sezione i blocchi con il marcatore sopra, come `scripts/prova_m6_3c.py` legge §21 — gli
stessi tipi, `comando`, `atteso`, `occhio` —, e in più fa tre confronti suoi: **ai passi 2, 3 e 4 la riga `reason`
delle due corse è la stessa, e non è `—`**; **al passo 4 il blocco di `ela approvals` del task ha le etichette, il
loro ordine e la loro larghezza del blocco di §6**; **al passo 6 il comando esce con `0`**. I segnaposto che riempie
sono `<id>`, `<approval-id>` — la domanda del task del passo — e `<id della voce configurata>`, letto da
`GET /voice`. Scrive tutto in `~/Downloads`, in `prova-m13.1c-m13.1d-m9.6-` con la
data e l'ora, e l'ultima riga dice «La prova è passata» o che cosa manca. **Se ELA smette di rispondere a metà
giro**, lo script scrive **INTERROTTO** al passo in cui è successo, non fa i passi che restano, e l'ultima riga lo
dice (decisione R, nella nota di §21 passo 1).

Sull'ELA di sempre, con il tuo `.env` com'è — i siti di §20 (`example.com` e `httpbin.org`), lo scope di §15, la voce
online di §12 — e **senza** la riga delle voci (passo 9: si aggiunge dopo il merge). Il Core acceso dal codice del
branch, `uv run ela serve`. Niente si scrive sul disco, e nessun sì si dà.

### 1. Prima

ELA risponde, lo shell di Chromium c'è, i due siti sono dichiarati e rispondono, e la voce online è configurata:
lo script lo controlla e stampa **PASSATO** per ciascuno. **Se qualcosa manca, il passo 1 è SALTATO** con ciò che
manca, e lo script si ferma lì: è il mondo che la prova richiede, non un comportamento di ELA, e un FALLITO
sembrerebbe di ELA. L'ultima riga dice «La prova non è passata: il passo 1 SALTATO.»; si ripara ciò che manca e si
rilancia.

### 2. Un diniego, due volte

<!-- prova: 2.comando -->
```
uv run ela task create "un sito che non hai dichiarato" --json
uv run ela task plan <id> --file docs/examples/browser-read-outside.json
uv run ela task run <id>
```

<!-- prova: 2.atteso -->
```
outcome        denied
reason         deny_by_decision: EXECUTING -> DENIED (targets ['example.org'] of browser.read are not within scope ['example.com', 'httpbin.org'])
state          DENIED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000002
stopped step   —
```

E di nuovo, sullo stesso task:

<!-- prova: 2.comando -->
```
uv run ela task run <id>
```

<!-- prova: 2.atteso -->
```
outcome        denied
reason         deny_by_decision: EXECUTING -> DENIED (targets ['example.org'] of browser.read are not within scope ['example.com', 'httpbin.org'])
state          DENIED
steps handled  —
stopped step   —
```

La seconda corsa trova il task chiuso e non tratta nessuno step; **la ragione è la stessa**. Prima di M13.1c la
seconda diceva `reason —`.

### 3. Un fallimento, due volte

<!-- prova: 3.comando -->
```
uv run ela task create "una pagina che porta altrove" --json
uv run ela task plan <id> --file docs/examples/browser-left-site.json
uv run ela task run <id>
```

<!-- prova: 3.atteso -->
```
outcome        failed
reason         fail: EXECUTING -> FAILED (browser.left_site: the page of httpbin.org went to https://example.org, which is not a declared site: the browser did not follow, and nothing was sent there)
state          FAILED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000003
stopped step   —
```

<!-- prova: 3.comando -->
```
uv run ela task run <id>
```

<!-- prova: 3.atteso -->
```
outcome        failed
reason         fail: EXECUTING -> FAILED (browser.left_site: the page of httpbin.org went to https://example.org, which is not a declared site: the browser did not follow, and nothing was sent there)
state          FAILED
steps handled  —
stopped step   —
```

Il codice dell'errore, `browser.left_site`, sta nelle parole della transizione: prima di M13.1c la transizione
scriveva solo il messaggio, e la seconda corsa diceva `reason —`.

### 4. Il no, e la domanda di §6

<!-- prova: 4.comando -->
```
uv run ela task create "il mio primo task" --json
uv run ela task plan <id> --file docs/examples/first-task.json
uv run ela task run <id>
uv run ela approvals
```

Il primo `run` si ferma a chiedere, come in §6. **Lo script prende il blocco di `ela approvals` la cui riga `task` è
il task di questo passo** — può aspettare anche un'altra domanda — **e lo confronta con il blocco di §6**: le stesse
etichette, nello stesso ordine, alla stessa larghezza, con lo stesso nome della riga del bersaglio (M13.1d). Poi dice no lui, con la CLI — la ragione di
un no si legge solo nella riga di comando e nell'audit — e fa girare due corse:

<!-- prova: 4.comando -->
```
uv run ela task deny <id> --approval <approval-id>
uv run ela task run <id>
```

<!-- prova: 4.atteso -->
```
outcome        denied
reason         deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by 6c38f1c5-6cda-5680-8a7a-4f061588deed)
state          DENIED
steps handled  —
stopped step   —
```

La corsa trova il task chiuso dal no — lo step che chiedeva l'ha chiuso la risposta —, e la seconda dice lo stesso:

<!-- prova: 4.comando -->
```
uv run ela task run <id>
```

<!-- prova: 4.atteso -->
```
outcome        denied
reason         deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by 6c38f1c5-6cda-5680-8a7a-4f061588deed)
state          DENIED
steps handled  —
stopped step   —
```

`6c38f1c5-6cda-5680-8a7a-4f061588deed` è l'id di `local`: la CLI parla con il token del Core, e chi risponde con quel
token è la persona a questa macchina. Dalla console o dal telefono sarebbe l'id della loro riga nel registro.

***Annotato il 2026-10-08*** (M13.1e, ADR 0059): da M13.1e la corsa stampa anche, sotto `reason`, `answered by  the
command line on the Core`; gli `atteso` cercano le loro righe in ordine, e quella in più non li cambia. Dalla console o
dal telefono, il nome della loro riga con il ruolo accanto: la sezione 25.

### 5. Che cosa dice l'help

<!-- prova: 5.comando -->
```
uv run ela task run --help
```

<!-- prova: 5.atteso -->
```
``denied``, ``failed``, ``cancelled`` and ``expired`` always carry their why: the words of the transition that ended the task
```

Lo script legge l'help con gli spazi riuniti, come la suite: l'help va a capo alla larghezza del terminale.

### 6. Il catalogo dell'audizione, vuoto

<!-- prova: 6.comando -->
```
uv run ela voice
```

<!-- prova: 6.atteso -->
```
(la voce configurata)  <id della voce configurata>  yes
the audition's catalogue is empty: ELA_ELEVENLABS_CANDIDATES in .env names the voices to try
```

Non è un errore: il comando esce con `0` — lo script lo controlla —, e la voce che usi resta nella tabella, con
`yes`.

### 7. L'audizione fa ancora parlare la voce che usi

<!-- prova: 7.comando -->
```
uv run ela voice audition <id della voce configurata>
```

<!-- prova: 7.occhio -->
```
Hai sentito la voce dire le due frasi di §9?
```

Costa i caratteri di due frasi. L'audizione è la parte che M9.6 ricostruisce; `voice.speak_online`, che M9.6 non
tocca e che chiederebbe un sì, la tengono i suoi test.

### 8. Il saluto del design system

<!-- prova: 8.comando -->
```
open apps/design-system/index.html
```

<!-- prova: 8.occhio -->
```
Nella composizione «home», nei due temi, il saluto è «Good evening.», senza un nome?
```

### 9. Dopo il merge: le tue voci nel `.env`

**Non fa parte della prova**: si fa dopo il merge, sul Mac, dalla cartella di ELA. La riga va **in cima** al `.env`
(`1i\`): il `sed` di macOS che aggiunge in fondo, su un `.env` che non finisce con un a-capo, la incollerebbe
all'ultima riga.

```
sed -i '' '1i\
ELA_ELEVENLABS_CANDIDATES={"VZOd9FMXDnXRZpGn0thg": "Daniela Narrator IT — Warm Elegant ITA", "kavPiGHUq62Aokyp5Tui": "Daniela — Giovane ed elegante", "UnOINkXZ3yK4vVg3Iayj": "Beatrice AI Agent", "3LTv5xMEHTJYUIMl1jBR": "Aurora — Clear and Supportive", "MuTiG4dbrEGYEy3XP4iP": "Rossana — Warm Italian Conversational", "mT0eqrjKfAPl6gQBlfBa": "Chiara — Professional and Versatile"}
' .env
```

```
grep -c '^ELA_ELEVENLABS_CANDIDATES=' .env
```

**Che cosa si deve vedere**: `1`. Un altro numero — `0`, o `2` dopo un secondo `sed` — si guarda con `grep -n` e si
corregge a mano. Poi riavvia `ela serve`, e `uv run ela voice` elenca le sei, con `yes` accanto a quella che usi, e
senza la riga del catalogo vuoto.

## 23. Il tetto di spesa sulla chiave del modello: la prova a mano di M14.1

> **Scritta con la SPEC del 2026-10-06** (`milestones/M14.1.md`, «La prova a mano») e **allineata con
> l'implementazione** il 2026-10-06: le domande dei quattro piani, con il caso peggiore che i passi 4–7 si aspettano,
> le fa la suite (`tests/api/test_examples.py`), e `tests/docs/test_prova_m14_1.py` tiene lo script allineato a questa
> sezione. **Riallineata con la console vera il 2026-10-07**, e corretta lo stesso giorno: il secondo tetto è il limite
> mensile dell'organizzazione, non quello della workspace, e il mese di ELA resta dichiarato (M14.1, «Le decisioni del
> 2026-10-07»). La si fa sul Mac e sul PC,
> sul branch di M14.1, con lo script `scripts/prova_m14_1.py`. **Fatta da Tommaso il 2026-10-07 sul branch**, a
> `845830c`, sul Mac e sul PC: passata, 45 PASSATI al primo giro, nessun FALLITO, nessun no, nessun SALTATO
> (`~/Downloads/prova-m14.1-20261007-213354.txt`); [ADR 0057](adr/0057-spending-cap.md) è Accettata.

**Che cosa ha misurato**, il 2026-10-07:

- **Il tetto che scatta** (passo 4): con il tetto piccolo, 1,48308 $, Opus 5.5 è negato prima della chiamata — speso
  0,017544 + prenotato 0,465536 + caso peggiore 4,065536 sopra il tetto —, e Haiku passa sotto lo stesso tetto. Ogni
  domanda nomina il caso peggiore e ciò che resta del mese.
- **I costi veri**, ciascuno con il modello che la risposta dichiara uguale a quello della tabella:
  `claude-opus-5-5` 0,003016 $, `claude-sonnet-5-5` 0,00097 $, `claude-haiku-4-5-20251001` 0,000315 $ e 0,00031 $
  sul Mac, 0,000325 $ sul PC al passo 5 e 0,000595 $ sul PC al passo 7.
- **Le due chiavi nella stessa workspace**: lo stesso id per le chiamate del Mac e del PC.
- **Il nodo che tace** (passo 6): `Ctrl-C` sul nodo del PC, la presa scaduta in 125 secondi, il task `FAILED` con
  `execution.interrupted` e non rieseguito; in `ela spend` lo speso invariato e una prenotazione aperta in più.
- **Le rotte diverse** (passo 7): il risultato del PC `SUCCEEDED` sul nodo, e il task `FAILED` con
  `model.routed_as_asked (model.misrouted)`.

Così si chiudono le due verifiche che M12.4 aveva lasciato a questa milestone (§12, passi 7 e 8; ADR 0040).

> ***Dal 2026-10-08 (M14.6, [ADR 0061](adr/0061-haiku-5-5.md))*** il profilo economico è **Haiku 5.5**, con due fasce
> di prezzo, e la lettura dalla cache di Sonnet 5.5 costa 0,10 $. I blocchi qui sotto restano quelli della prova del
> 2026-10-07, fatta su Haiku 4.5. Oggi gli stessi piani, `docs/examples/ask-model-routine.json` e
> `ask-model-long.json`, fanno nominare a ELA il caso peggiore della fascia alta di Haiku 5.5, che la finestra meno
> l'uscita raggiunge sempre:
>
> ```
> worst case            0.508192 USD, claude-haiku-5-5, up to 995904 tokens in and 4096 out
> worst case            0.516384 USD, claude-haiku-5-5, up to 991808 tokens in and 8192 out
> ```

**Da M14.1 nessuna chiamata che spende parte senza un tetto** ([ADR 0057](adr/0057-spending-cap.md)). Il tetto è una
riga del `.env` del Core, in dollari come il listino e la console:

```
ELA_SPENDING_CAP_USD=<tetto in dollari>
```

Prima di ogni chiamata ELA prenota il **caso peggiore** — la finestra di contesto del modello meno l'output, al prezzo
d'ingresso, più il `max_tokens` che la richiesta manda, al prezzo d'uscita — e la lascia partire solo se **speso +
prenotato + caso peggiore** sta dentro il tetto. Il mese è quello del calendario, in UTC, dichiarato. Senza la riga, ogni chiamata
che spende è negata prima, con la riga nominata nella ragione; un «sì» non alza il tetto, lo alza solo chi lo scrive.
`uv run ela spend` dice dove sei, con la stessa funzione con cui il cancello giudica.

**I tetti sono due.** Il secondo è il **limite mensile dell'organizzazione**, che imposti nella console di Anthropic
nella pagina Billing: copre ogni chiave dovunque stia, anche ciò che spende fuori da ELA. Il tetto di ELA sta **sotto**,
con un margine. **Il mese del fornitore può non essere quello di ELA**: la documentazione scrive l'azzeramento alle 00:00
UTC del primo del mese per il tetto del livello, e del limite che scegli dice solo che la risposta indica quando
l'accesso riprende. Le due chiavi —
quella del Mac e quella del PC — stanno nella **stessa workspace**: la workspace tiene insieme le chiavi di ELA, e la
sua spesa nella console resta quella di ELA. Sul PC non c'è un tetto: il nodo spende solo ciò che il Core ha prenotato
per il lavoro che gli manda, e non oltre. Per esempio: un tetto di 50 $ sotto un limite di 55 $.

**Il credito è un fermo anche lui.** Con il credito prepagato e la ricarica automatica spenta, finito il credito le
chiamate si fermano finché non lo ricarichi; se il credito è più piccolo del tetto — 5 $ sotto un tetto di 50 $, per
esempio — è il primo a scattare. ELA non lo conta: il libro è la spesa del mese, non il saldo.

Lo script legge da questa sezione i blocchi con il marcatore sopra, con il lettore di `scripts/prova_m6_3c.py`: i
tipi di §21 — `comando`, `atteso`, `occhio`, `richiede`, `guarda`, `mano` — e sei suoi:

- **`commit`**: il comando da dare **sul PC**; lo script chiede i primi sette caratteri che stampa e li confronta con il
  commit del Mac.
- **`limite`**: chiede il limite mensile dell'organizzazione che leggi nella console, in dollari, e lo confronta con il
  tetto che `GET /spend` dice: **PASSATO se il tetto di ELA sta sotto**.
- **`costo`**: legge i risultati del task del passo e vuole il modello scritto, **un costo** e un `finish_reason`; scrive
  l'id della workspace. Con «su un nodo», il risultato è del PC e la workspace è la stessa delle chiamate del Mac.
- **`spesa`**: confronta `GET /spend` con com'era all'ultimo `tetto`, all'ultima `spesa` o all'inizio del passo.
- **`tetto`**: «piccolo» calcola un tetto — speso + prenotato + 1 — e lo stampa come riga da mettere nel `.env` del
  Core; «il tuo» stampa quello che c'era. Aspetta che tu la scriva e riavvii il Core, e controlla che ELA la legga.
  **Se ELA legge un altro tetto, la prova si ferma lì** — **FERMATO** —: il resto sarebbe misurato con un tetto che
  non è quello voluto, e l'ultima riga lo dice.
- **`tace`** e **`aspetta`**: al passo 6, che il nodo non abbia consegnato prima del `Ctrl-C`, e che la presa scada —
  l'attesa la fa lo script, con il TTL della presa del `.env` del Core.

I segnaposto che riempie sono `<id>`, il task del passo, e `<approval-id>`, la sua domanda. Scrive tutto in
`~/Downloads`, in `prova-m14.1-` con la data e l'ora, e l'ultima riga dice «La prova è passata» o che cosa manca. **Se
ELA smette di rispondere a metà giro**, lo script scrive **INTERROTTO** al passo in cui è successo — al passo 4 lo
fermi tu, per riavviare il Core: lo script aspetta Invio prima di parlargli di nuovo.

Sul Mac, il `.env` con la chiave del Mac e il tuo tetto; sul PC, il `.env` di §12 passo 4, con la chiave del PC. Il
Core acceso dal codice del branch, dopo `uv run alembic upgrade head`; il nodo del PC acceso da §12 passo 5. Le chiamate
vere sono otto o nove, per pochi centesimi.

```
uv run python scripts/prova_m14_1.py
```

### 1. Prima

ELA risponde, dal codice del branch — `GET /spend` c'è, e c'è perché la migrazione `0013` è applicata: senza, il Core
non parte —, il tetto è dichiarato, e il provider del modello ha una chiave. Lo script lo controlla e stampa
**PASSATO** per ciascuno; **se qualcosa manca, il passo 1 è SALTATO** con ciò che manca, e lo script si ferma lì.

### 2. Il PC sullo stesso commit del Mac

Sul PC, nella cartella di ELA:

<!-- prova: 2.commit -->
```powershell
git log --oneline -1
```

Lo script chiede i primi sette caratteri che il PC ha stampato e li confronta con il commit del Mac: il nodo non
dichiara il suo commit, e nessun canale porta il `git` del PC al Mac. Se sono diversi, `git pull` sul PC, il nodo
riavviato, e si rilancia.

### 3. Il secondo tetto

Nella console di Anthropic, nella pagina Billing, alla voce dei limiti di spesa:

<!-- prova: 3.limite -->
```
il limite mensile dell'organizzazione, in dollari
```

<!-- prova: 3.occhio -->
```
La console dice che la ricarica automatica dei crediti è spenta?
```

Quando il limite riparte lo script non te lo chiede: la console non risponde a ciò che la documentazione non scrive. La
documentazione scrive la ripresa alle 00:00 UTC del primo del mese per il tetto del livello; del limite che scegli dice
solo che la risposta indica quando l'accesso riprende. Il mese di ELA è quello del calendario, in UTC, dichiarato
(ADR 0057 §4).

### 4. I tre modelli, e il tetto che scatta

Tre domande, una per profilo, **con il tuo tetto**. I task restano su questo Mac: senza `--privacy` non viaggiano.

Opus 5.5, il profilo `quality`:

<!-- prova: 4.comando -->
```
uv run ela task create "Opus 5.5, con il tetto" --json
uv run ela task plan <id> --file docs/examples/ask-model.json
uv run ela task run <id>
uv run ela approvals
```

<!-- prova: 4.atteso -->
```
worst case            4.065536 USD, claude-opus-5-5, up to 995904 tokens in and 4096 out
left this month
```

<!-- prova: 4.comando -->
```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

<!-- prova: 4.atteso -->
```
outcome        completed
reason         —
state          COMPLETED
steps handled  3f0d1a44-5b6c-4d7e-8f90-000000000001
stopped step   —
```

<!-- prova: 4.costo -->
```
claude-opus-5-5
```

Sonnet 5.5, il profilo `balanced` — lo step non nomina un `task_type`:

<!-- prova: 4.comando -->
```
uv run ela task create "Sonnet 5.5, con il tetto" --json
uv run ela task plan <id> --file docs/examples/ask-model-balanced.json
uv run ela task run <id>
uv run ela approvals
```

<!-- prova: 4.atteso -->
```
worst case            2.032768 USD, claude-sonnet-5-5, up to 995904 tokens in and 4096 out
left this month
```

<!-- prova: 4.comando -->
```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

<!-- prova: 4.atteso -->
```
outcome        completed
reason         —
state          COMPLETED
steps handled  3f0d1a44-5b6c-4d7e-8f90-000000000002
stopped step   —
```

<!-- prova: 4.costo -->
```
claude-sonnet-5-5
```

Haiku 4.5, il profilo `cheap`, con l'id fissato:

<!-- prova: 4.comando -->
```
uv run ela task create "Haiku 4.5, con il tetto" --json
uv run ela task plan <id> --file docs/examples/ask-model-routine.json
uv run ela task run <id>
uv run ela approvals
```

<!-- prova: 4.atteso -->
```
worst case            0.216384 USD, claude-haiku-4-5-20251001, up to 195904 tokens in and 4096 out
left this month
```

<!-- prova: 4.comando -->
```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

<!-- prova: 4.atteso -->
```
outcome        completed
reason         —
state          COMPLETED
steps handled  3f0d1a44-5b6c-4d7e-8f90-000000000003
stopped step   —
```

<!-- prova: 4.costo -->
```
claude-haiku-4-5-20251001
```

Un costo che manca è un FALLITO: un nome di modello che la tabella di ELA non conosce terrebbe ogni chiamata al caso
peggiore per un mese. Ora **un tetto piccolo**: speso + prenotato + 1 dollaro. Lo script lo stampa; scrivilo nel `.env`
del Core al posto del tuo, ferma il Core con `Ctrl-C` e riaccendilo con `uv run ela serve`, poi Invio.

<!-- prova: 4.tetto -->
```
piccolo
```

Opus 5.5 non ci sta più: **negato prima della domanda**, nessun risultato, e il prenotato non si muove.

<!-- prova: 4.comando -->
```
uv run ela task create "Opus 5.5, sotto il tetto piccolo" --json
uv run ela task plan <id> --file docs/examples/ask-model.json
uv run ela task run <id>
```

<!-- prova: 4.atteso -->
```
outcome        denied
reason         deny_by_cap: EXECUTING -> DENIED (the monthly cap would be crossed: spent
state          DENIED
steps handled  3f0d1a44-5b6c-4d7e-8f90-000000000001
stopped step   —
```

<!-- prova: 4.spesa -->
```
speso invariato
prenotato invariato
```

Haiku ci sta: chiede, passa, e lo speso cresce del suo costo vero.

<!-- prova: 4.comando -->
```
uv run ela task create "Haiku 4.5, sotto il tetto piccolo" --json
uv run ela task plan <id> --file docs/examples/ask-model-routine.json
uv run ela task run <id>
uv run ela approvals
```

<!-- prova: 4.atteso -->
```
worst case            0.216384 USD, claude-haiku-4-5-20251001, up to 195904 tokens in and 4096 out
left this month
```

<!-- prova: 4.comando -->
```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

<!-- prova: 4.atteso -->
```
outcome        completed
reason         —
state          COMPLETED
steps handled  3f0d1a44-5b6c-4d7e-8f90-000000000003
stopped step   —
```

<!-- prova: 4.costo -->
```
claude-haiku-4-5-20251001
```

<!-- prova: 4.spesa -->
```
speso cresciuto del costo
prenotato invariato
```

Rimetti il tuo tetto nel `.env`, riavvia il Core, Invio:

<!-- prova: 4.tetto -->
```
il tuo
```

Una difesa che non si è vista scattare non conta: questo passo è il tetto che scatta, con la chiave vera.

### 5. Una chiamata sul PC

Il nodo del PC acceso. Il task può viaggiare, e lo prende il PC, che chiama con **la sua** chiave:

<!-- prova: 5.richiede -->
```
un nodo disponibile
```

<!-- prova: 5.comando -->
```
uv run ela task create "Haiku 4.5, sul PC" --privacy TRUSTED --json
uv run ela task plan <id> --file docs/examples/ask-model-routine.json
uv run ela task run <id>
uv run ela approvals
```

<!-- prova: 5.atteso -->
```
worst case            0.216384 USD, claude-haiku-4-5-20251001, up to 195904 tokens in and 4096 out
left this month
```

<!-- prova: 5.comando -->
```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

<!-- prova: 5.atteso -->
```
outcome        assigned
reason         step 3f0d1a44-5b6c-4d7e-8f90-000000000003 assigned to node
state          EXECUTING
steps handled  —
stopped step   —
```

<!-- prova: 5.guarda -->
```
risultato SUCCEEDED su un nodo
```

<!-- prova: 5.comando -->
```
uv run ela task run <id>
```

<!-- prova: 5.atteso -->
```
outcome        completed
reason         —
state          COMPLETED
steps handled  —
stopped step   —
```

<!-- prova: 5.costo -->
```
claude-haiku-4-5-20251001 su un nodo
```

<!-- prova: 5.spesa -->
```
speso cresciuto del costo
prenotato invariato
```

La chiamata del PC la conta il libro del Mac, e la sua workspace è quella delle chiamate del Mac: la stessa workspace
tiene insieme le due chiavi di ELA, e la sua spesa nella console resta quella di ELA. Il limite dell'organizzazione
copre ogni chiave, dovunque stia.

### 6. Il nodo che tace a metà lavoro

Una risposta lunga — `max_output_tokens` 8192, caso peggiore 0,232768 $ — perché il PC sia ancora dentro la chiamata
quando premi `Ctrl-C`. Il testo che il modello scrive è una descrizione, e non contiene istruzioni per nessuno.

<!-- prova: 6.richiede -->
```
un nodo disponibile
```

<!-- prova: 6.comando -->
```
uv run ela task create "una risposta lunga, sul PC" --privacy TRUSTED --json
uv run ela task plan <id> --file docs/examples/ask-model-long.json
uv run ela task run <id>
uv run ela approvals
```

<!-- prova: 6.atteso -->
```
worst case            0.232768 USD, claude-haiku-4-5-20251001, up to 191808 tokens in and 8192 out
left this month
```

<!-- prova: 6.comando -->
```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

<!-- prova: 6.atteso -->
```
outcome        assigned
reason         step 3f0d1a44-5b6c-4d7e-8f90-000000000004 assigned to node
state          EXECUTING
steps handled  —
stopped step   —
```

Lo script guarda finché il PC prende il lavoro — la presa scrive il `STARTED`, con la prenotazione:

<!-- prova: 6.guarda -->
```
risultato STARTED su un nodo
```

<!-- prova: 6.mano -->
```
Adesso: Ctrl-C nella finestra del nodo sul PC, poi Invio qui.
```

<!-- prova: 6.tace -->
```
nessun esito prima del Ctrl-C
```

**Se la risposta è arrivata prima del `Ctrl-C`**, il passo non ha provato niente: lo script lo scrive **SALTATO**, ti
chiede di riaccendere il nodo e lo rifà, fino a tre volte. Non è un fallimento di ELA.

<!-- prova: 6.aspetta -->
```
la presa scade
```

<!-- prova: 6.comando -->
```
uv run ela task run <id>
```

<!-- prova: 6.atteso -->
```
outcome        failed
reason         fail: EXECUTING -> FAILED (execution.interrupted: model-complete was started for step 3f0d1a44-5b6c-4d7e-8f90-000000000004 and never reported; it is not run again, here or on another machine, so whether it acted is unknown)
state          FAILED
steps handled  3f0d1a44-5b6c-4d7e-8f90-000000000004
stopped step   —
```

<!-- prova: 6.spesa -->
```
speso invariato
una prenotazione aperta in più
```

Nessuno sa se la chiamata è partita, e il mese la tiene **al caso peggiore** fino al primo del mese dopo: è il vincolo
dichiarato di ADR 0040, con il suo prezzo scritto in ADR 0057. Riaccendi il nodo sul PC, poi Invio.

<!-- prova: 6.mano -->
```
Riaccendi il nodo sul PC (uv run python -m ela.cli node run), poi Invio qui.
```

### 7. La tabella di rotte diversa: `model.misrouted`

La negativa di §12 passo 8, ora con le chiavi. Sul PC: `Ctrl-C` sul nodo, una riga di rotte che il Mac non ha, e il
nodo di nuovo acceso:

```powershell
[IO.File]::AppendAllText("$HOME\ELA\.env", "`nELA_MODEL_ROUTES={""reasoning"": {""providers"": [""anthropic""], ""profile"": ""cheap""}}`n")
uv run python -m ela.cli node run
```

<!-- prova: 7.mano -->
```
Sul PC: la riga di ELA_MODEL_ROUTES nel .env e il nodo riacceso, poi Invio qui.
```

<!-- prova: 7.richiede -->
```
un nodo disponibile
```

<!-- prova: 7.comando -->
```
uv run ela task create "una domanda, con le rotte del PC" --privacy TRUSTED --json
uv run ela task plan <id> --file docs/examples/ask-model.json
uv run ela task run <id>
uv run ela approvals
```

<!-- prova: 7.atteso -->
```
worst case            4.065536 USD, claude-opus-5-5, up to 995904 tokens in and 4096 out
left this month
```

<!-- prova: 7.comando -->
```
uv run ela task approve <id> --approval <approval-id>
uv run ela task run <id>
```

<!-- prova: 7.atteso -->
```
outcome        assigned
reason         step 3f0d1a44-5b6c-4d7e-8f90-000000000001 assigned to node
state          EXECUTING
steps handled  —
stopped step   —
```

<!-- prova: 7.guarda -->
```
risultato SUCCEEDED su un nodo
```

<!-- prova: 7.comando -->
```
uv run ela task run <id>
```

<!-- prova: 7.atteso -->
```
outcome        failed
reason         fail: EXECUTING -> FAILED (verification.failed: 1 of 2 success conditions failed for model.complete: model.routed_as_asked (model.misrouted))
state          FAILED
steps handled  —
stopped step   —
```

<!-- prova: 7.costo -->
```
claude-haiku-4-5-20251001 su un nodo
```

Il Core ha prenotato il caso peggiore di Opus 5.5, la sua rotta; il PC, con la sua tabella, ha chiamato Haiku — che ci
sta dentro, e quindi è partito —, e la verifica sul Mac ha visto la rotta sbagliata. Le negative per ultime, perché
questa cambia il `.env` del PC.

### 8. Il ripristino

Sul PC, il `.env` riscritto con il blocco di §12 passo 4 — senza la riga delle rotte — e il nodo riacceso.

<!-- prova: 8.mano -->
```
Sul PC: il .env riscritto con il blocco di §12 passo 4 e il nodo riacceso, poi Invio qui.
```

<!-- prova: 8.richiede -->
```
un nodo disponibile
```

**Quando il fornitore ferma una chiamata**, il codice dice che cosa guardare, perché il rimedio è diverso:

- **`provider.spend_limit`**: un limite di spesa del fornitore è raggiunto. La ragione dice quale — quello
  dell'organizzazione, quello di una workspace, se un giorno ce n'è uno, o il tetto del livello — e quanto ELA ha contato
  del suo tetto nel suo mese. Non dice perché, e le cause possibili sono tre:
  1. **il conto di ELA è indietro rispetto alla fattura**: lo speso della console è più di quello di `ela spend`;
  2. **un'altra chiave dell'organizzazione ha speso**: il limite dell'organizzazione copre ogni chiave, non solo le due
     di ELA, e la spesa della workspace di ELA nella console è la sola parte di ELA;
  3. **il mese del fornitore non è quello di ELA**: per esempio 50 $ a fine mese e 50 all'inizio del mese dopo, nella
     stessa finestra del fornitore — ELA è in regola con il suo tetto, e il limite scatta lo stesso.

  Guarda il limite e la spesa nella console, la spesa della workspace di ELA, e `uv run ela spend`. Non si ritenta: tiene
  finché il fornitore non riapre, come dice la console, o finché qualcuno alza il limite.
- **Un fallimento con il tipo `billing_error`**, o **un `provider.bad_request` mentre `ela spend` mostra margine**: i
  piani della prova sono quelli che la suite fa girare, quindi la prima cosa da guardare è **il credito e il
  pagamento**, nella pagina Billing della console. Se il credito è finito, ricaricalo. La documentazione non scrive con
  che risposta arriva il credito finito, ed ELA non la indovina: un `400` resta `provider.bad_request`, un `402` resta
  `provider.rejected` con il tipo `billing_error` nella ragione (ADR 0057 §10).

**Nessuno dei due la prova lo raggiunge**: servirebbe spendere fino al limite, o fino all'ultimo centesimo del credito.
Il primo lo prova la suite, con le risposte costruite sulle parole e sul campo della documentazione. **Il confronto fra la somma di ELA e il costo della console non è nella prova**:
le chiamate di prova costano meno di un centesimo e la console arrotonda ai centesimi; è una misura da fare dopo un
mese d'uso (ADR 0057).

## 24. Il Planner: la prova a mano di M14.2

> **Scritta con l'implementazione il 2026-10-07** (`milestones/M14.2.md`, «La prova a mano», con le decisioni della
> review dello stesso giorno), e `tests/docs/test_prova_m14_2.py` tiene lo script allineato a questa sezione. La si fa
> **sul Mac**, sul branch di M14.2, con lo script `scripts/prova_m14_2.py`: M14.2 non cambia niente sul nodo. Il
> cancello sulla chiamata del Planner — senza tetto, o con un tetto che non ci sta — lo prova la suite
> (`tests/executive/test_planner_spending.py`); qui lo vedi nella domanda. **Fatta da Tommaso il 2026-10-08 sul
> branch**, a `f2b67c0`, sul Mac: passata, 29 PASSATI al primo giro, nessun FALLITO, nessun no, nessun SALTATO
> (`~/Downloads/prova-m14.2-20261008-091143.txt`); [ADR 0058](adr/0058-planner.md) è Accettata, e le misure sono in `milestones/M14.2.md`,
> «Passata il 2026-10-08». Il primo giro, a `28c4c88`, non era passato per due difetti dello script, non di ELA —
> l'atteso del passo 2 leggeva solo l'ultimo comando, il rifiuto cercava la ragione dove l'API non la scrive —, corretti
> lo stesso giorno (`milestones/M14.2.md`, «Il primo giro»).

Da M14.2 `uv run ela task plan <id>`, senza `--file`, chiede il piano a ELA (§5). Il Planner crea il **task di
pianificazione**, figlio del tuo, con un solo step `model.complete`: ciò che esce è il tuo obiettivo, le istruzioni del
Planner e il catalogo delle capability — mai le cartelle, i siti e i programmi che hai dichiarato, mai i dispositivi,
mai il contesto. La chiamata va a Opus 5.5 con `max_output_tokens` 16384, e **il suo caso peggiore è 4,262144 $**:
la domanda lo dice, con ciò che resta del mese. Dopo il tuo sì il modello scrive il piano, ELA lo controlla con le
funzioni che decideranno quando gira, e il tuo task va in coda — **senza partire**: lo leggi, e lo avvii tu.

**Il modello non è deterministico**: lo stesso obiettivo dà piani diversi. Lo script confronta **proprietà, non
piani**, e il giudizio «fa ciò che l'obiettivo chiede?» resta al tuo occhio. A te restano due cose: **i sì** — lo
script ti mostra la domanda e chiede «rispondi sì?»; con un «s» dà il sì con la CLI, con un «n» la prova si ferma, perché
il resto del passo non avrebbe niente da misurare — e **l'occhio** su ogni piano.

Lo script legge da questa sezione i blocchi con il marcatore sopra, con il lettore di `scripts/prova_m6_3c.py`: i tipi
`comando`, `atteso` e `occhio` di §21 — qui l'`atteso` cerca le sue righe in ciò che hanno stampato **tutti** i comandi
del blocco sopra, in ordine —, e cinque suoi:

- **`sì`**: legge il task di pianificazione e la sua domanda, te la mostra, e chiede «rispondi sì?». Con un «s» esegue il
  comando del blocco, il sì con la CLI; con un «n» la prova si ferma — **FERMATO** —.
- **`piano`**: legge `GET /tasks/<id>` e vuole il task `QUEUED`, **l'autore `MODEL`** con un risultato e
  `claude-opus-5-5`, e per ogni step una capability **del catalogo del codice** — letto al commit che il passo 1 ha
  verificato, dal catalogo e dai verifier, mai dalle funzioni del Planner —, almeno una condizione nel suo vocabolario,
  il rischio e la domanda del catalogo, nessun tratto preferito, nessuno step `HIGH`. Ogni riga del blocco è una
  capability che il piano deve avere; per `model.complete`, un `task_type` della tabella delle rotte. **Il catalogo che
  il Planner ha mandato** lo confronta con lo stesso: ogni sua capability c'è nel codice, con lo stesso rischio, la
  stessa domanda e lo stesso vocabolario. Un Planner che sbagliasse la derivazione scriverebbe piano e catalogo
  d'accordo fra loro, e solo il codice lo vede. Scrive il piano nel file, step per step, con gli argomenti.
- **`chiamata`**: il risultato del task di pianificazione — `claude-opus-5-5`, un costo, un `finish_reason` —, e scrive
  due misure: **se la risposta era un oggetto JSON**, e **quanti token d'uscita** ha usato.
- **`rifiuto`**: il task `FAILED`, nessun piano, le parole del modello stampate, e **`planner.no_plan` nella riga
  `reason` dell'`uv run ela task plan <id>` sopra** — ciò che leggi tu; `GET /tasks/<id>` una ragione non ce l'ha
  (***annotato il 2026-10-08***: da M13.1e ce l'ha, in `end`, e `rifiuto` legge ancora la riga di `ela task plan`). **Se
  il modello scrive comunque un piano valido, il passo è SALTATO e non FALLITO**: ciò che il modello non ha dato non è
  un errore di ELA. Lo script scrive il piano nel file e ti chiede di guardarlo.
- **`spesa`**: `GET /spend`, confrontato con com'era al passo 1.

I segnaposto che riempie sono `<id>`, il task del passo; `<nota>`, il nome della nota del passo 2, **unico per giro**,
con la data e l'ora; `<id del figlio>`, il task di pianificazione; e `<approval-id>`, la sua domanda. Scrive tutto in
`~/Downloads`, in `prova-m14.2-` con la data e l'ora, e l'ultima riga dice «La prova è passata» o che cosa manca.
**Nessuna modifica al `.env`, nessun `Ctrl-C`, nessun riavvio** dopo l'avvio.

Sul Mac, il `.env` con la chiave del Mac e il tuo tetto (§23); il Core acceso dal codice del branch, dopo
`uv run alembic upgrade head`. Le chiamate vere sono **quattro**, tutte a Opus 5.5; il loro costo vero lo legge il
passo 6.

```
uv run python scripts/prova_m14_2.py
```

### 1. Prima

Lo script controlla, e stampa **PASSATO** per ciascuno: il Mac è sull'ultimo commit del branch su `origin`, con l'albero
pulito; il Core gira da quel codice — lo schema dell'API ha `POST /tasks/{task_id}/planning` —; `uv run alembic current`
dice `0014 (head)`; il provider del modello ha una chiave e c'è un tetto; ciò che resta del mese basta per **quattro
pianificazioni al caso peggiore**, 4 × 4,262144 = 17,048576 $, calcolate dalla funzione del cancello; `example.com` è
fra i siti dichiarati (§20, passo 2). **Se qualcosa manca, la prova si ferma lì** — **FERMATO** —, con ciò che manca:
il resto misurerebbe un'altra cosa.

### 2. Una nota

Un obiettivo che il catalogo sa fare, e che si fa girare: la nota la scrive `workspace.write_note`, che dentro lo scope
non chiede.

<!-- prova: 2.comando -->
```
uv run ela task create "Scrivi in workspace/notes/<nota> una nota con il testo: Questa nota l'ha pianificata ELA." --json
uv run ela task plan <id>
```

<!-- prova: 2.atteso -->
```
outcome waiting_approval
worst case 4.262144 USD, claude-opus-5-5, up to 983616 tokens in and 16384 out
```

<!-- prova: 2.sì -->
```
uv run ela task approve <id del figlio> --approval <approval-id>
```

<!-- prova: 2.comando -->
```
uv run ela task plan <id>
```

<!-- prova: 2.atteso -->
```
outcome planned
author MODEL claude-opus-5-5
```

<!-- prova: 2.piano -->
```
workspace.write_note
```

<!-- prova: 2.chiamata -->
```
claude-opus-5-5
```

<!-- prova: 2.occhio -->
```
Il piano scrive la nota che l'obiettivo chiede, nel posto che l'obiettivo nomina?
```

Poi lo avvii: niente domanda, e la nota c'è.

<!-- prova: 2.comando -->
```
uv run ela task run <id>
cat ~/.ela/workspace/workspace/notes/<nota>
```

<!-- prova: 2.atteso -->
```
outcome completed
Questa nota l'ha pianificata ELA.
```

### 3. Una pagina

Un obiettivo del browser. Il piano **non si fa girare**: un selettore scelto dal modello può trovare più di un paragrafo,
e non è ciò che questa prova misura.

<!-- prova: 3.comando -->
```
uv run ela task create "Leggi il primo paragrafo della pagina principale di example.com." --json
uv run ela task plan <id>
```

<!-- prova: 3.atteso -->
```
outcome waiting_approval
worst case 4.262144 USD, claude-opus-5-5, up to 983616 tokens in and 16384 out
```

<!-- prova: 3.sì -->
```
uv run ela task approve <id del figlio> --approval <approval-id>
```

<!-- prova: 3.comando -->
```
uv run ela task plan <id>
```

<!-- prova: 3.atteso -->
```
outcome planned
```

<!-- prova: 3.piano -->
```
browser.read
```

<!-- prova: 3.chiamata -->
```
claude-opus-5-5
```

<!-- prova: 3.occhio -->
```
Il piano legge la pagina principale di example.com, e il suo primo paragrafo?
```

### 4. Una domanda al modello

Un piano con uno step `model.complete`: `MEDIUM`, che chiede, con un `task_type` della tabella. **Non si fa girare**:
sarebbe una quinta chiamata, e un altro sì.

<!-- prova: 4.comando -->
```
uv run ela task create "Fatti spiegare dal modello, in due frasi, che cos'è un grafo aciclico diretto." --json
uv run ela task plan <id>
```

<!-- prova: 4.atteso -->
```
outcome waiting_approval
worst case 4.262144 USD, claude-opus-5-5, up to 983616 tokens in and 16384 out
```

<!-- prova: 4.sì -->
```
uv run ela task approve <id del figlio> --approval <approval-id>
```

<!-- prova: 4.comando -->
```
uv run ela task plan <id>
```

<!-- prova: 4.atteso -->
```
outcome planned
```

<!-- prova: 4.piano -->
```
model.complete
```

<!-- prova: 4.chiamata -->
```
claude-opus-5-5
```

<!-- prova: 4.occhio -->
```
Il piano chiede al modello di spiegare, in due frasi, che cos'è un grafo aciclico diretto?
```

### 5. La negativa, con la chiave vera: un obiettivo fuori catalogo

Nessuna capability spegne una luce. Il modello deve rispondere che non c'è un piano, e dire perché; un piano che parla
della luce invece di spegnerla non è un piano (le istruzioni glielo dicono).

<!-- prova: 5.comando -->
```
uv run ela task create "Spegni la luce della cucina." --json
uv run ela task plan <id>
```

<!-- prova: 5.atteso -->
```
outcome waiting_approval
worst case 4.262144 USD, claude-opus-5-5, up to 983616 tokens in and 16384 out
```

<!-- prova: 5.sì -->
```
uv run ela task approve <id del figlio> --approval <approval-id>
```

<!-- prova: 5.comando -->
```
uv run ela task plan <id>
```

<!-- prova: 5.chiamata -->
```
claude-opus-5-5
```

<!-- prova: 5.rifiuto -->
```
planner.no_plan
```

<!-- prova: 5.occhio -->
```
La ragione del modello dice perché il catalogo non sa spegnere una luce?
```

### 6. La spesa

Le quattro chiamate sono nello speso, e nessuna prenotazione è rimasta aperta.

<!-- prova: 6.spesa -->
```
speso cresciuto dei costi delle chiamate
prenotato com'era al passo 1
```

## 25. La ragione di una fine sulle tre superfici: la prova a mano di M13.1e

> **Scritta con l'implementazione il 2026-10-08** (`milestones/M13.1e.md`, «La prova a mano», con le decisioni della
> review dello stesso giorno), e `tests/docs/test_prova_m13_1e.py` tiene lo script allineato a questa sezione. La si fa
> **sul Mac e sul telefono, senza il PC**, sul branch di M13.1e, con lo script `scripts/prova_m13_1e.py`. `EXPIRED` lo
> prova la suite: a mano vorrebbe un riavvio. **Fatta da Tommaso il 2026-10-08 sul branch**, a `b5a8d7a`, sul Mac e sul
> telefono: passata, 29 PASSATI al primo giro, nessun FALLITO, nessun no, nessun SALTATO
> (`~/Downloads/prova-m13.1e-20261008-124455.txt`); [ADR 0059](adr/0059-the-reason-on-every-route.md) è Accettata, e le misure
> sono in `milestones/M13.1e.md`, «Passata il 2026-10-08».

Da M13.1e ogni superficie che mostra un task finito dice **perché è finito** — la stessa ragione di `ela task run`, il
sommario della transizione che l'ha chiuso — e, per un no, **chi ha risposto**: `ela task show`, le risposte di
`ela task deny` e `ela task cancel`, la tabella `why` sotto `ela task finished` e `ela task list`, il riassunto e la home
della console, la home del telefono. Chi ha risposto lo dice il registro dei dispositivi: il nome che hai scritto
quando hai arruolato la console o il telefono, con il ruolo accanto; per la riga di comando sul Core un nome fisso,
`the command line on the Core`. **Sotto il tetto** — il telefono per un task `LOCAL_ONLY`, la console da fuori — una
pagina mostra **solo parole di ELA**: l'operazione, il codice, e chi ha risposto detto come «la riga di comando», «la
console» o «il telefono»; mai il messaggio, che nomina percorsi e siti, mai il nome di un dispositivo.

A te restano tre cose con le mani — il «Rifiuta» della console, il «No» del telefono, il sì del passo 5 — e l'**occhio**
sulla console e sul telefono, una domanda per task. Tutto il resto lo script lo legge da solo, dalla riga di comando e
dall'API. **Nessuna chiamata parte**: i piani sono esempi senza `model.complete`, un no nega prima di ogni chiamata, e il
fallimento lo dà `browser.act` su un bottone che `example.com` non ha. Nessuna voce.

Lo script legge da questa sezione i blocchi con il marcatore sopra, con il lettore di `scripts/prova_m6_3c.py`: i tipi
`comando`, `atteso`, `occhio` e `mano` di §21 — l'`atteso` cerca le sue righe in ciò che hanno stampato **tutti** i
comandi del blocco sopra, in ordine; `mano` ti dice che cosa fare, e non aspetta Invio —, `sì` della sezione 24 — qui
legge la domanda del task stesso —, e quattro suoi:

- **`guarda`**: `stato DENIED`, e aspetta che il task finisca, al più un quarto d'ora. Finito in un altro stato, il passo
  è FALLITO con lo stato vero: lì può esserci un difetto di ELA. Se in un quarto d'ora nessuno ha agito, il passo è
  **SALTATO** — «nessuno ha risposto in un quarto d'ora: il passo si rifà» —: è il passo umano non fatto.
- **`fine`**: legge `GET /tasks/<id>`, `GET /audit` e `GET /devices`, e vuole la ragione del task uguale al sommario
  dell'evento della transizione che l'ha chiuso, l'operazione e il codice della riga, e chi ha risposto con il ruolo
  della riga — `LOCAL` con il nome fisso, `CONSOLE` o `COMPANION` con il nome della sua riga del registro, `nessuno` —;
  e la stessa ragione nella riga del task di `GET /tasks/finished`. Se il task non è fra gli ultimi 20 finiti, quella
  riga non si confronta — **SALTATO**, «un altro task finito l'ha spinto fuori» —, e il resto sì.
- **`ultimi`**: prima dei passi all'occhio, legge `GET /tasks/finished` con il numero di righe della superficie — 8 la
  console, 6 il telefono — e vuole fra quelle i task dei passi 2–6. Se un altro task finito li ha spinti fuori, il passo
  è **SALTATO**, con il task e la superficie: è la precondizione del passo, non un errore di ELA.
- **`misura`**: le rotte della riga, cinque volte ciascuna, con quanti task hanno una ragione; scrive i millisecondi,
  ed è una misura, non un verdetto.

I segnaposto che riempie sono `<id>`, il task del passo; `<approval-id>`, la sua domanda; `<id di chi ha risposto>` e
`<nome di chi ha risposto>`, che scrive `fine`; e `<id del passo N>`, il task del passo N. Scrive tutto in
`~/Downloads`, in `prova-m13.1e-` con la data e l'ora, e l'ultima riga dice «La prova è passata» o che cosa manca.
**Nessuna modifica al `.env`, nessun `Ctrl-C`, nessun riavvio** dopo l'avvio: M13.1e non ha migrazioni.

Sul Mac, il Core acceso dal codice del branch; la console aperta nel browser del Mac, su `127.0.0.1` (§14); il telefono
arruolato con `--privacy TRUSTED` (§13).

```
uv run python scripts/prova_m13_1e.py
```

### 1. Prima

Lo script controlla, e stampa **PASSATO** per ciascuno: il Mac è sull'ultimo commit del branch su `origin`, con l'albero
pulito; ELA risponde, dal codice del branch — lo schema dell'API ha `EndOut` —; `uv run alembic current` dice
`0014 (head)`; `example.com` è fra i siti dichiarati, e lo shell di Chromium c'è; nel registro c'è una console e c'è un
telefono `TRUSTED`, non revocati. **Se qualcosa manca, la prova si ferma lì** — **FERMATO** —, con ciò che manca.

### 2. Il no dalla riga di comando

Il piano del primo task: il saluto, poi la nota, che chiede. Al no lo dici tu dalla riga di comando, cioè lo script.

<!-- prova: 2.comando -->
```
uv run ela task create "il no dalla riga di comando" --json
uv run ela task plan <id> --file docs/examples/first-task.json
uv run ela task run <id>
```

<!-- prova: 2.atteso -->
```
outcome waiting_approval
```

<!-- prova: 2.comando -->
```
uv run ela task deny <id> --approval <approval-id>
```

<!-- prova: 2.atteso -->
```
state DENIED
reason deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by 6c38f1c5-6cda-5680-8a7a-4f061588deed)
answered by the command line on the Core
```

<!-- prova: 2.fine -->
```
operazione deny_by_approval
codice —
ha risposto LOCAL
```

<!-- prova: 2.comando -->
```
uv run ela task show <id>
```

<!-- prova: 2.atteso -->
```
state DENIED
reason deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by 6c38f1c5-6cda-5680-8a7a-4f061588deed)
answered by the command line on the Core
```

### 3. Il no dalla console

Lo stesso piano; il no lo dai tu, dalla console.

<!-- prova: 3.comando -->
```
uv run ela task create "il no dalla console" --json
uv run ela task plan <id> --file docs/examples/first-task.json
uv run ela task run <id>
```

<!-- prova: 3.atteso -->
```
outcome waiting_approval
```

<!-- prova: 3.mano -->
```
Dalla console sul Mac apri l'Approval Center, apri la domanda del task <id> e premi «Rifiuta».
```

<!-- prova: 3.guarda -->
```
stato DENIED
```

<!-- prova: 3.fine -->
```
operazione deny_by_approval
codice —
ha risposto CONSOLE
```

<!-- prova: 3.comando -->
```
uv run ela task show <id>
```

<!-- prova: 3.atteso -->
```
state DENIED
reason deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by <id di chi ha risposto>)
answered by <nome di chi ha risposto> (console)
```

### 4. Il no dal telefono

Il task è `TRUSTED`, perché il telefono possa vederlo e rispondere: un task `LOCAL_ONLY` resta sul Mac.

<!-- prova: 4.comando -->
```
uv run ela task create "il no dal telefono" --privacy TRUSTED --json
uv run ela task plan <id> --file docs/examples/first-task.json
uv run ela task run <id>
```

<!-- prova: 4.atteso -->
```
outcome waiting_approval
```

<!-- prova: 4.mano -->
```
Dal telefono apri la domanda del task <id> e premi «No».
```

<!-- prova: 4.guarda -->
```
stato DENIED
```

<!-- prova: 4.fine -->
```
operazione deny_by_approval
codice —
ha risposto COMPANION
```

<!-- prova: 4.comando -->
```
uv run ela task show <id>
```

<!-- prova: 4.atteso -->
```
state DENIED
reason deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by <id di chi ha risposto>)
answered by <nome di chi ha risposto> (phone)
```

### 5. Un fallimento dopo un sì

`docs/examples/browser-act-missing-here.json`: un clic su `#non-esiste`, che sulla pagina di `example.com` non c'è. La
domanda è `HIGH`; dopo il sì la pagina si apre, e prima del primo gesto ELA vede che il bottone non c'è.

<!-- prova: 5.comando -->
```
uv run ela task create "un bottone che non c'è" --json
uv run ela task plan <id> --file docs/examples/browser-act-missing-here.json
uv run ela task run <id>
```

<!-- prova: 5.atteso -->
```
outcome waiting_approval
```

<!-- prova: 5.sì -->
```
uv run ela task approve <id> --approval <approval-id>
```

<!-- prova: 5.comando -->
```
uv run ela task run <id>
```

<!-- prova: 5.atteso -->
```
outcome failed
reason fail: EXECUTING -> FAILED (browser.element_missing: gesture 1 of 1 names no element on the page of example.com; no gesture was made)
```

<!-- prova: 5.fine -->
```
operazione fail
codice browser.element_missing
ha risposto nessuno
```

### 6. Un fermo dalla riga di comando

Un task in coda, mai avviato, fermato con parole tue.

<!-- prova: 6.comando -->
```
uv run ela task create "da fermare" --json
uv run ela task plan <id> --file docs/examples/echo.json
uv run ela task cancel <id> --reason "la prova di M13.1e"
```

<!-- prova: 6.atteso -->
```
state CANCELLED
reason cancel: QUEUED -> CANCELLED (la prova di M13.1e)
```

<!-- prova: 6.fine -->
```
operazione cancel
codice —
ha risposto nessuno
```

### 7. La riga di comando, tutti insieme

La tabella `why` sotto le due liste: gli ultimi cinque, l'ultimo a finire per primo, e i task fermati, negati e falliti
nell'ordine in cui sono nati.

<!-- prova: 7.comando -->
```
uv run ela task finished --limit 5
uv run ela task list --state DENIED --state FAILED --state CANCELLED
```

<!-- prova: 7.atteso -->
```
why
<id del passo 6> cancel: QUEUED -> CANCELLED (la prova di M13.1e) —
<id del passo 5> fail: EXECUTING -> FAILED (browser.element_missing:
<id del passo 4> deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by
<id del passo 3> deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by
<id del passo 2> deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by 6c38f1c5-6cda-5680-8a7a-4f061588deed) the command line on the Core
why
<id del passo 2> deny_by_approval:
<id del passo 3> deny_by_approval:
<id del passo 4> deny_by_approval:
<id del passo 5> fail:
<id del passo 6> cancel:
```

### 8. La console

Nella console sul Mac — la nota in fondo dice «Stai leggendo da questa macchina» —: la home, fra i Finiti, e il
riassunto di ogni task, che si apre toccando la sua riga.

<!-- prova: 8.ultimi -->
```
console 8
<id del passo 2>
<id del passo 3>
<id del passo 4>
<id del passo 5>
<id del passo 6>
```

<!-- prova: 8.occhio -->
```
Il task «il no dalla riga di comando» dice «deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by 6c38f1c5-…)» e, nel riassunto, «Ha risposto the command line on the Core (la riga di comando)»?
```

<!-- prova: 8.occhio -->
```
Il task «il no dalla console» dice «deny_by_approval: … (rejected by …)» e «Ha risposto» con il nome della tua console e «(la console)» accanto?
```

<!-- prova: 8.occhio -->
```
Il task «il no dal telefono» dice «deny_by_approval: … (rejected by …)» e «Ha risposto» con il nome del tuo telefono e «(il telefono)» accanto?
```

<!-- prova: 8.occhio -->
```
Il task «un bottone che non c'è» dice «fail: EXECUTING -> FAILED (browser.element_missing: …)», e nessun «Ha risposto»?
```

<!-- prova: 8.occhio -->
```
Il task «da fermare» dice «cancel: QUEUED -> CANCELLED (la prova di M13.1e)»?
```

### 9. Il telefono

La home del telefono, fra i Finiti. Dei quattro task `LOCAL_ONLY` il telefono mostra l'id, non l'obiettivo, e della
ragione **solo parole di ELA**; del task `TRUSTED` del passo 4 l'obiettivo e la ragione intera.

<!-- prova: 9.ultimi -->
```
telefono 6
<id del passo 2>
<id del passo 3>
<id del passo 4>
<id del passo 5>
<id del passo 6>
```

<!-- prova: 9.occhio -->
```
La riga del task <id del passo 2> dice «deny_by_approval · ha risposto: la riga di comando», e niente altro della ragione?
```

<!-- prova: 9.occhio -->
```
La riga del task <id del passo 3> dice «deny_by_approval · ha risposto: la console», senza il nome della console?
```

<!-- prova: 9.occhio -->
```
La riga del task «il no dal telefono» dice la ragione intera, «deny_by_approval: … (rejected by …)», e «ha risposto:» con il nome del tuo telefono e «(il telefono)» accanto?
```

<!-- prova: 9.occhio -->
```
La riga del task <id del passo 5> dice «fail · browser.element_missing», senza il resto del messaggio?
```

<!-- prova: 9.occhio -->
```
La riga del task <id del passo 6> dice «cancel», senza le parole del fermo?
```

### 10. La misura

Sul database vero del Mac: quanto costa leggere la ragione di ogni task finito di una lista. Lo script scrive i numeri
nel file; non c'è un verdetto.

<!-- prova: 10.misura -->
```
/tasks
/tasks/finished?limit=10
```

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
