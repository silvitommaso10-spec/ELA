# 0045. Il filesystem fuori dalla workspace, e il primo livello HIGH: la riga che chiede a ogni uso, lo scope legato al fatto, e un codice che smette di mentire

- **Stato:** Accettata
- **Data:** 2026-09-21
- **Riferimenti spec:** §18, §23, §27, §28, §29, §33, §37, §57, §59, §63
- **Milestone:** M13.1

## Contesto

§29 elenca cinque livelli di rischio e chiude dicendo che «le capability HIGH e CRITICAL non
vengono introdotte in produzione nella prima versione». ADR 0010 §5 ha tradotto quella frase in un
tetto del catalogo (`MAX_RISK = MEDIUM`) e ADR 0011 §3 in una riga della policy (`HIGH → DENY`), e
ADR 0026 §8 ha scritto perché le due difese restano **indipendenti**: «il giorno in cui il tetto si
muoverà — e si muoverà, §29 ha livelli sopra MEDIUM per una ragione — la seconda linea si
scoprirebbe non essere mai esistita».

Quel giorno è questo. §18 vuole che ELA agisca sul computer vero, e la prima voce dell'Action Core
è il filesystem: leggere e scrivere **fuori dalla workspace**, cioè fuori dall'unica cartella che
ELA si è fatta da sola. Un'azione così non può entrare sotto una riga che la nega né sotto una che
non chiede.

Le domande erano: dove può stare il confine, se lo scope dello scope-per-rischio regga a un
livello che non è `LOW`, che cosa può coprire un'approvazione a ogni uso, che cosa la domanda deve
nominare perché un sì significhi qualcosa, e dove vanno i byte di un file letto.

## Decisione

### 1. `HIGH` smette di essere `DENY`, e §29 si rivede apertamente

`MAX_RISK` passa da `MEDIUM` a `HIGH`, e la riga `HIGH` di `RISK_POLICY` passa da `DENY` a
`APPROVAL_EVERY_USE`. **Le due cose nella stessa milestone**, per ADR 0026 §7: una riga che
nessuna capability può far scattare è una difesa che non scatta, e una capability `HIGH` senza la
riga la nega il Guardian prima di chiedere qualunque cosa.

**La frase di §29 non si aggira in silenzio.** «Le capability HIGH e CRITICAL non vengono
introdotte in produzione nella prima versione» era vera e resta vera di ciò che descriveva: v0.1 è
taggata dal 2026-09-07 e questo lavoro le sta fuori. Si legge accanto a questa riga, come ADR 0038
§16 ha fatto con ADR 0017 §8.

`CRITICAL` resta sopra il tetto e resta `DENY`. Il giorno in cui avrà un uso, quella riga si muoverà
come si è mossa questa: in chiaro, con la capability che la rende non vacua.

Policy rivista:

| Rischio | Regola | Esito |
|---|---|---|
| SAFE | `ALLOW` | `ALLOWED` |
| LOW | `ALLOW_WITHIN_SCOPE` | `ALLOWED`; fuori scope `DENIED` con `SCOPE` (§2) |
| MEDIUM | `APPROVAL_UNLESS_AUTHORIZED` | come ADR 0011 §3 |
| HIGH | `APPROVAL_EVERY_USE` | `REQUIRES_APPROVAL` sempre, salvo un grant **nato da un'approvazione** (§3) |
| CRITICAL | `DENY` | `DENIED` sempre |

**`POLICY_VERSION` passa da `v0.1` a `v0.2`**, e non è una formalità: la versione è stampata in
ogni decisione e in ogni evento dell'audit, e una decisione che permette un `HIGH` dicendo di
essere stata presa sotto `v0.1` manderebbe chi la legge a cercare in ADR 0011 §3 una riga che lì
non c'è. Le righe vecchie dell'audit continuano a dire `v0.1`, ed è esattamente a questo che serve
stamparla.

**Perché `APPROVAL_EVERY_USE` e non `APPROVAL_UNLESS_AUTHORIZED`.** «A meno che autorizzata» sarebbe
falso proprio per la riga che nessuna autorizzazione permanente raggiunge (§3), e il nome di una
regola è ciò che qualcuno legge in un audit un mese dopo — lo stesso motivo per cui M17.2 dec. K.3
ha rinominato `core_on_a_companion_route`.

### 2. Lo scope si lega al fatto, non alla riga: `Rule.SCOPE`

Fino a M13.1 il confine dichiarato da una capability era controllato **solo** quando la riga era
`ALLOW_WITHIN_SCOPE`, cioè solo per `LOW`. Non si vedeva, perché l'unica capability con uno scope
era `workspace.write_note`, che è `LOW`. Una `HIGH` con uno scope avrebbe avuto **un confine che
nessuno faceva rispettare**: la difesa che non scatta di ADR 0026 §7, nel cuore del Guardian.

La regola diventa: **una capability che dichiara uno scope ha quello scope fatto rispettare
qualunque sia il suo rischio, e un bersaglio fuori è `DENIED` prima di qualunque domanda.** Il
controllo sta dopo il diniego della riga — un `CRITICAL` resta negato *per essere `CRITICAL`* — e
prima dell'autorizzazione, che è l'ordine che ADR 0011 §3 tiene di proposito.

Il `Rule` registrato nella decisione **nomina lo scope**: `Rule.SCOPE`, undicesimo membro, accanto a
`CATALOGUE`, `ARGUMENTS` e `STEP_MISMATCH`, che sono i controlli e non le righe. Prima un diniego di
scope si firmava `ALLOW_WITHIN_SCOPE`, che nomina la riga che *permette*: una `HIGH` negata così
sarebbe la diagnosi falsa di §5 in casa propria. `ALLOW_WITHIN_SCOPE` resta la regola di una `LOW`
**permessa**.

**La mezza riga di ADR 0011 §3 che questo rende falsa**, nominata invece che riscritta: «`ALLOWED`
se ogni bersaglio è nello scope della capability, altrimenti `DENIED`». La metà prima della virgola
resta vera; **la metà dopo la virgola si è spostata su `Rule.SCOPE`** — il diniego c'è ancora, ma non
lo firma più quella regola. Un ADR immutabile resta vero di ciò che fu; ciò che oggi è falso si
legge accanto a chi lo rivede.

### 3. Che cosa copre una riga che chiede a ogni uso

Una `HIGH` è coperta **solo** da un'`Authorization` nata da un'approvazione. La distinzione non è
nuova: sta già nel tipo (ADR 0012 §1), dove `approval_id` valorizzato significa «nata da un sì,
monouso, legata a questo task e a questo step» — e il dominio lo impone con un validatore — mentre
`approval_id` nullo è la forma che avranno le policy permanenti di §59.

§59 è il posto dove le policy dell'utente **allargano**; `HIGH` è il livello che non raggiungono.
Un grant permanente presentato per una `HIGH` è negato con un motivo che lo **nomina**, e non con
un «non copre» generico.

**È una difesa esercitata, non dichiarata.** Le due forme sono costruibili oggi, quindi il test le
fabbrica nei due versi: il grant nato da un sì copre, quello permanente no. Non è il caso di ADR
0026 §7 — lì si trattava di un filtro che nessun percorso poteva far scattare.

**Il predicato vive in un posto solo** (`asks_at_every_use`): lo legge il Guardian quando giudica un
grant che gli è stato consegnato, e lo legge l'executor quando sceglie quale grant consegnargli. Due
copie sarebbero due risposte alla domanda «questo grant copre», e la più economica delle due
conseguenze sarebbe un task negato dove l'utente andava interpellato.

Righe di consumo aggiunte:

| Regola | Consuma |
|---|---|
| `APPROVAL_EVERY_USE` | sì |

### 4. Le due capability, e perché una è MEDIUM e l'altra HIGH

Capability aggiunte:

| Capability | Rischio | Scope | Argomenti scoped | Autorizzazione | Argomenti obbligatori | Argomenti opzionali |
|---|---|---|---|---|---|---|
| `fs.read` | MEDIUM | `undeclared` | `path` | sì | `path: string`, `purpose: string` | — |
| `fs.write` | HIGH | `undeclared` | `path` | sì | `path: string`, `body: string`, `overwrite: boolean`, `purpose: string` | — |

La colonna «Scope» porta il **valore di comodo** delle fabbriche, `UNDECLARED_FS_SCOPE`, che è ciò
che il catalogo costruisce quando nessuno gli passa niente — come la riga di `workspace.write_note`
porta `workspace/notes`, il default di `ELA_NOTES_SCOPE`. La differenza è che lì un default esiste
anche nelle impostazioni, e qui no: il confine vero è `ELA_FS_ROOT` + `ELA_FS_SCOPE`, e senza quei
due ELA non parte (§5). Il segnaposto non è mai il confine di nessuno.

**`fs.write` è HIGH** perché fuori dalla workspace **una scrittura è irreversibile finché §37 non
esiste**: non c'è rollback a cui appellarsi. L'esempio di §59 — «puoi modificare liberamente i file
dentro questa cartella» — è già onorato, oggi, da `workspace.write_note`: `LOW`, dentro il suo
scope, senza domanda. `fs.write` è la stessa azione su una casa invece che su una cartella.

**`fs.read` è MEDIUM** perché leggere non è scrivere. Oggi le due righe chiedono entrambe a ogni uso,
perché ogni grant è monouso; ciò che le separa è la promessa sul domani — una policy di §59 potrà
coprire una `MEDIUM` e non raggiungerà mai una `HIGH`. Non è `LOW`, che non chiederebbe niente dentro
lo scope: un file fuori dalla workspace è contenuto dell'utente (§57), e `LOW` trasformerebbe un
permesso in una riga di configurazione su cui nessuno viene più interpellato.

Il rischio sta nella capability e **mai negli argomenti** (ADR 0038 §16): `fs.read` non è `HIGH` per
certi percorsi e `MEDIUM` per altri.

### 5. Il confine: una coppia, senza default, e un codice che smette di mentire

Il confine è `ELA_FS_ROOT` + `ELA_FS_SCOPE`, la forma di `ELA_WORKSPACE_DIR` + `ELA_NOTES_SCOPE`
(ADR 0025 §5): la grammatica dello scope non si tocca, e i bersagli assoluti restano rifiutati per
costruzione, che è una difesa in più arrivata gratis.

**Nessuna delle due ha un default, e si dichiarano insieme, con un messaggio solo.** Uno scope
relativo da solo non nomina niente sul disco; una radice da sola è una casa senza porta. Un default
avrebbe fatto sì che l'utente dichiarasse la radice e ELA continuasse a non poter scrivere lì, per un
valore mai visto e una cartella che nessuno ha creato: **un restringimento silenzioso è peggio di un
rifiuto all'avvio, perché il rifiuto si legge.** Le fabbriche del catalogo tengono un valore di
comodo (`UNDECLARED_FS_SCOPE`) perché `production_catalogue()` resti costruibile senza ambiente, e un
test dimostra che il percorso di produzione non lo usa mai.

**ELA non crea mai la radice**, né all'avvio né al primo uso: il tool rifiuta con `fs.no_root` invece
di fare `mkdir(parents=True)`, perché una cartella che ELA si fabbrica è un posto che nessuno ha
scelto — e perché una cartella può sparire mentre ELA gira.

**La radice non può contenere né essere contenuta da ciò che ELA usa per esistere**: la workspace, il
database, le catture, l'audio che ELA spazza all'avvio, la cartella dove un nodo tiene il segreto
(ADR 0039 §6), il `.env` letto da questo processo e il proprio albero sorgente quando è
raggiungibile. **L'elenco si deriva dalle impostazioni**, non si scrive: così `~` è rifiutata perché
contiene `~/.ela`, senza un caso speciale per `~`, e una variabile aggiunta domani non lascia un buco.

**La radice si risolve all'avvio e la risposta si dice.** Se non esiste, o se è un link — la forma
che `~/Documents` prende con «Scrivania e Documenti» di iCloud attivo —, ELA si ferma con una frase:
altrimenti `classify` rifiuterebbe di attraversare il link e ogni chiamata morirebbe una per una con
`path.symlink`, senza che il messaggio spieghi perché.

**Il codice `path.outside_workspace` diventa `path.outside_root`.** Con una radice che non è la
workspace quel nome era **una diagnosi falsa, e una diagnosi falsa è falsa anche quando l'esito è
giusto**. Il nome vecchio è **superato**; il precedente è M17.2 dec. K.3, dove
`core_on_a_companion_route` è diventato `core_on_a_page`, e ADR 0013 §11 — che lo nomina in una riga
— si legge con questa riga accanto.

Tool sostituiti:

| Capability | Tool | Nome | Output | Codici di errore |
|---|---|---|---|---|
| `workspace.write_note` | `WriteNoteTool` | `workspace-notes` | `path`, `bytes` | `arguments.invalid`, `path.invalid`, `path.symlink`, `path.outside_root`, `path.is_directory`, `io.error` |

Il rinominare costa **una** riga, quella qui sopra, e non tocca la tabella dei verifier di ADR 0014
§2, che scrive «percorso» e lascia che il test espanda `PATH_CODES`. La differenza fra i due
documenti è la differenza fra elencare e derivare.

### 6. La domanda nomina il bersaglio risolto e la sovrascrittura

Una domanda su un file porta due fatti **della macchina**, non del chiamante: il **bersaglio
risolto** e **se sovrascrive qualcosa che c'è già**. `purpose` c'è in più, non al posto: è testo che
arriva dal client, e un criterio che si fidasse di ciò che il chiamante dichiara sarebbe falso il
giorno in cui il chiamante sbaglia. Il corpo di una scrittura non si mostra mai (§57).

I due fatti li legge **la classificazione condivisa** (`ela.tools.paths`), e li risponde il tool, che
è il componente che tiene la radice: `describe_target` è di sola lettura e **non è
un'esecuzione** — il tool si esegue dopo, e solo sotto una decisione `ALLOWED`. È `async` perché
legge il filesystem (ADR 0005 §1) e perché un port ha **un modo solo**: un membro sincrono su un
port async sarebbe il primo posto in cui qualcuno smette di poter dire qual è.

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ToolPort` | §18, §30 | async | `describe_target` |

### 7. La sovrascrittura vale nei due versi

`overwrite` è **un'asserzione sul mondo, non una richiesta**. Il tool la rilegge prima di scrivere e
rifiuta con `fs.overwrite_mismatch` se è cambiata **in un verso o nell'altro**: un file apparso dove
era stata approvata una creazione, o sparito dove era stato approvato un sovrascrivere. **Un criterio
che nomina un verso solo è mezza difesa, e il caso mancante è proprio quello che una corsa perde.**

*Che cosa risponde chi.* Il verifier risponde dei **byte a quel percorso adesso**, confrontati con
l'intento e mai con il rapporto del tool; **non risponde dell'identità del percorso**, perché
risolve la stessa coppia radice/percorso e seguirebbe lo stesso scambio. Un componente sostituito
fra `classify` e `open` resta un **limite dichiarato** — `ela.tools.notes` lo dichiara già per la
workspace, e qui è più largo, perché la radice è la casa dell'utente. E se l'asserzione era già falsa
quando la domanda è nata, il rifiuto arriva dopo il sì e non prima: la domanda mostra comunque la
verità della macchina, quindi nessuno approva una cosa credendone un'altra.

### 8. Dove vanno i byte di una lettura

`fs.read` è la capability che prende i file dell'utente e li mette in un risultato, quindi va detto
dove finiscono:

- **il risultato porta il contenuto** — è ciò per cui esiste, e resta sulla sua rotta con la regola 29;
- **l'audit porta il percorso e la dimensione, e mai i byte** (§57; ADR 0011: ciò che entra in un log
  append-only non si redige più);
- **un fallimento porta le dimensioni e non gli hash**, la forma di `WriteNoteVerifier`, perché
  l'hash di un file breve si inverte per dizionario.

Un file che non è UTF-8 è un rifiuto e non un'ipotesi: un decoder che sostituisse ciò che non sa
leggere metterebbe nel risultato qualcosa che nel file non c'è.

### 9. Nessuna delle due viaggia, e lo dice un test

I verifier di `fs.read` e `fs.write` dichiarano `reads_the_machine = True`: leggono il disco del
Core, dove un file con lo stesso percorso può esistere — il falso positivo di ADR 0038 §14, una
radice più larga. L'orchestratore le rifiuta su un nodo che non è `local` con `UNVERIFIABLE`.
**Non si sottintende**: un non-viaggio sottinteso è un permesso che nessuno ha scritto.

Verifier di produzione aggiunti:

**Non** sotto l'etichetta `Verifier aggiunti:` di ADR 0014 §2: quella tabella descrive i verifier di
`verifiers_v01`, cioè di v0.1, e `fs.read` e `fs.write` non sono di v0.1 — la stessa ragione per cui
`fs.*` non entra nella tabella dei tool di ADR 0013 §11, che `coded_tools()` confronta con
`tools_v01`. Ciò che questa tabella dichiara lo verifica `tests/docs/test_adr_filesystem.py` contro
`production_verifiers`.

| Capability | Verifier | Nome | Condizioni | Codici di fallimento |
|---|---|---|---|---|
| `fs.read` | `FsReadVerifier` | `fs-read-verifier` | `fs.file_exists`, `fs.content_matches` | comuni, percorso, `fs.content_mismatch`, `fs.unreadable` |
| `fs.write` | `FsWriteVerifier` | `fs-write-verifier` | `fs.file_exists`, `fs.content_matches` | comuni, percorso, `fs.content_mismatch`, `fs.unreadable` |

### 10. `step.risk` riesaminato, come ADR 0026 §7 chiedeva

ADR 0026 §7 dichiarò vacuo il filtro `DEGRADED` e disse che «il filtro tornerà vivo il giorno in cui
il catalogo ammetterà capability HIGH — e quel giorno la provenienza di `step.risk` andrà
riesaminata». È oggi.

`Requirements.risk` diventa `max(step.risk, il rischio che il catalogo porta)`. Il client conserva
l'unico potere che deve avere — **può solo stringere** — e perde quello che non avrebbe dovuto avere:
dichiarare `SAFE` per una capability `HIGH` non nasconde più uno step al filtro. Una capability che
il catalogo non conosce non contribuisce: è già raccolta in `unresolved`, e il task aspetta.

L'orchestratore riceve per questo un `CapabilityRegistryPort`, che è un port e non un concreto.

### 11. Una superficie risponde solo se mostra tutto ciò che la domanda nomina

La regola, derivabile e valida anche per `CRITICAL` quando arriverà: **una superficie può rispondere
a una domanda solo se mostra tutto ciò che quella domanda nomina.** **Non c'è un elenco di
dispositivi da tenere aggiornato**: è un mondo chiuso nei due versi fra i campi che la domanda
dichiara e quelli che ogni superficie mostra, e il giorno in cui una domanda impara un fatto nuovo,
ogni superficie che offre un sì o lo mostra o smette di offrirlo.

**Le superfici che rispondono sono tre, non due**: il Command Center, il companion, e **la riga di
comando** — `ela task approve` è il primo sì che chiunque dia. Tutte e tre mostrano ora tutto ciò
che la domanda nomina: le due pagine ne mostrano le **parti**, perché una pagina non può far
leggere una frase (M12.5 dec. F), e `ela approvals` mostra la frase **e** le parti, un blocco per
domanda — nove colonne sarebbero un riversamento, non qualcosa che si legge prima di dire sì.

**Il divario della riga di comando precedeva M13.1**, e va detto perché è il genere di cosa che si
scopre due volte: M12.5 diede il sacchetto della domanda alle pagine e lasciò alla CLI la frase e i
bersagli, quindi `ela task approve` poteva rispondere a una domanda senza dirne il rischio.
Nessuno se n'era accorto finché questa milestone non ha aggiunto due campi al sacchetto e ha dovuto
chiedersi dove dovessero comparire. **L'ha reso visibile M13.1 e l'ha chiuso M13.1**: le tre strade
scartate erano ritagliare un'eccezione alla regola per la prima superficie che non la rispettava,
lasciarlo come debito datato, oppure darlo a una milestone sua — e `ApprovalOut` porta già quei
campi sul filo, quindi mostrarli era formato e non lavoro nuovo.

`fs.read` e `fs.write` **non hanno una vista propria** nel Command Center: hanno il trattamento del
rischio e i due fatti nuovi nell'Approval Center. La regola della Fase 17 è «ogni milestone che
aggiunge una capacità aggiunge **la sua** vista», non «una vista nuova»: una seconda vista della
stessa cosa sarebbe la seconda copia che la voce 5.10 vieta.

### 12. Una promessa mantenuta a metà, e la regola che ne esce

M12.5 dec. F.3 promise «un test che appunta che `RISK_POLICY` nega `HIGH` e `CRITICAL`, e fallisce il
giorno in cui la Fase 13 lo cambia, **con un messaggio che nomina questa domanda**». I test che
falliscono esistono; **il messaggio che nomina la domanda del companion no**. La domanda — se
l'iPhone possa rispondere a una `HIGH` — è arrivata a M13.1 da un censimento, cioè per fortuna.

La regola che ne esce, per chi promette: **una promessa che un test futuro «porterà una domanda» è
mantenuta solo se il messaggio nomina la domanda, e si verifica leggendo il messaggio il giorno in cui
la si fa.** Non si scrive ora un test «che si accorge del primo `HIGH`»: il primo `HIGH` è questo, e
un test che aspetta un evento già accaduto non è una difesa.

### 13. Un appunto deve fallire quando il mondo si muove, non adattarsi

`test_the_policy_denies_every_level_above_the_catalogue_cap` derivava la sua domanda da `MAX_RISK`:
«ogni livello **sopra il tetto** è negato?». Alzando il tetto a `HIGH` non falliva — si restringeva a
`CRITICAL` e **smetteva in silenzio di provare per `HIGH`** ciò che il suo nome prometteva.

**Un'asserzione che si adatta al cambiamento che esiste per intercettare non è un'asserzione.** Il
tetto e le righe si affermano ora **insieme**, per esteso, e il messaggio dice che cosa riscrivere.
Vale per ogni appunto della stessa famiglia: i conteggi si spostano all'ADR che li cambia
(`_rules_up_to`), e nessuno deriva la propria soglia dal valore che sta difendendo.

## Alternative considerate

- **Una seconda riga `APPROVAL_WITHIN_SCOPE` per `HIGH`** — riparava `HIGH` e riapriva la stessa
  trappola per la terza riga che nascerà. Il controllo si lega al fatto. Scartata in review.
- **Lasciare il diniego di scope firmato `ALLOW_WITHIN_SCOPE`** — il nome della riga che permette su
  una decisione che nega: la diagnosi falsa di §5. Scartata.
- **Scope assoluti** — cambiavano `is_valid_scope_entry` e `within_scope`, cioè il confronto più
  delicato del Guardian, e toglievano la difesa gratuita contro i bersagli assoluti. Scartata.
- **Un default per `ELA_FS_SCOPE`** (`ELA`) — un restringimento silenzioso, e un confine che ELA
  sceglie per l'utente. Scartata in review.
- **Un secondo modulo di classificazione dei percorsi** — due definizioni di «dove porta un percorso»
  (ADR 0014 §2), e la regola 18 cammina una tupla chiusa di due moduli: il terzo tacerebbe. Scartata.
- **Solo la frase del codice cambiata, non il codice** — il codice è ciò che finisce nell'audit e nei
  messaggi; il nome sarebbe rimasto falso dove conta. Scartata in review.
- **`fs.read` HIGH** — renderebbe ELA inutilizzabile per qualunque lavoro che legga più di un file, e
  confonderebbe due promesse diverse su §59. Scartata.
- **`fs.read` LOW** — nessuna domanda dentro lo scope, cioè un permesso dato una volta in
  configurazione su contenuto personale (§57). Scartata.
- **`overwrite` dedotto e non dichiarato** — il tool avrebbe scritto comunque, e il fatto approvato
  non avrebbe avuto niente contro cui essere riconfrontato al momento della scrittura. Scartata.
- **L'iPhone escluso dalle domande `HIGH`** — un elenco di dispositivi da tenere aggiornato al posto
  di una regola, e toglierebbe al telefono proprio il caso in cui essere lontani dal Mac conta.
  Scartata: la regola è §11.
- **Lasciare `POLICY_VERSION` a `v0.1`** — una versione che non si muove quando si muove la tabella
  che nomina. Scartata.

## Conseguenze

- `ela.permissions` esporta in più `ASKING_RULES`, `asks_at_every_use`, `FS_READ`, `FS_WRITE`,
  `fs_read`, `fs_write`, `UNDECLARED_FS_SCOPE`, `PHASE_13_INTRODUCED_AT`. `Rule` ha due membri nuovi,
  `RISK_POLICY` una riga cambiata, `MAX_RISK` un valore nuovo, `POLICY_VERSION` la versione `v0.2`.
- `ela.ports` esporta `Target`, e `ToolPort` ha un membro in più.
- `ela.tools` ha `fs.py` (`FsReadTool`, `FsWriteTool`) e due verifier; `paths.py` ha `describe` e il
  codice rinominato.
- `ela.composition` ha `FilesystemSettings`, e `Settings` non si costruisce senza la coppia.
- `DeviceOrchestrator` riceve un `CapabilityRegistryPort`.
- **Le capability di produzione restano dieci** e **quattro viaggiano, sei no**: i due conteggi di
  oggi vivono qui, e gli ADR precedenti restano appuntati a ciò che videro.
- **Un difetto trovato scrivendo il test, non dalla suite**: con la radice assente il tool la
  **creava**, perché `mkdir(parents=True)` non distingue una cartella intermedia dalla radice. Prima
  il test che falliva, poi `fs.no_root`.
- **Che cosa questa milestone non fa**: non costruisce le policy permanenti di §59, non porta il
  terminale (M13.2), non porta il Planner, e non cancella, sposta o elenca file.
