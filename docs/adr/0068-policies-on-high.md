# 0068. Le policy di chi usa ELA arrivano alle azioni HIGH

- **Stato:** Proposta il **2026-11-12**, con il codice di M13.14 (`docs/milestones/M13.14.md`, la SPEC e la review
  della SPEC, risposte 18–36). Si accetta con un commit suo dopo la prova a mano della sezione 32 di
  `docs/GETTING_STARTED.md`, con `scripts/prova_m13_14.py`.

## Contesto

Fino a M13.14 una policy di §59 copriva solo una `MEDIUM` che dichiarasse i suoi termini — le due sessioni guidate
(ADR 0062) —, e **tre difese** la tenevano lontana da una `HIGH`: il catalogo rifiutava la dichiarazione su una riga che
non fosse `APPROVAL_UNLESS_AUTHORIZED` («no policy reaches a HIGH (ADR 0045 §3)»), la nascita rifiutava con `ADMITS`, e
il Guardian negava un grant permanente presentato per una `HIGH`. La decisione del 2026-11-02 e la sua revisione del
2026-11-12 (STATO, 5.14) dicono altro: «se imposto una policy qualsiasi cosa chieda di fare la policy la può fare ELA
senza autorizzazioni; solo io posso impostare policy e lei non può modificare le sue policy», e «il limite irrevocabile
è che ELA non può creare policy da sola». §59 stesso lo prevede: «Puoi modificare liberamente i file dentro questa
cartella» è una policy su `fs.write`, che in ELA è `HIGH`.

Questo ADR rivede apertamente le tre difese per le `HIGH` che dichiarano termini, e solo per quelle. **Il livello non si
abbassa**: `fs.write`, `browser.act` e `browser.act_as_you` restano `HIGH`; `CRITICAL` resta `DENY` e nessuna capability
lo è; `terminal.run`, il login e le quattro capability dei file dal browser chiedono a ogni uso, come prima.

## Decisione

### 1. La riga di una `HIGH` che dichiara termini è una riga sua

`RISK_POLICY` non cambia, e nessun livello si muove. **La riga di una capability è `row_of(capability)`**, in
`ela/permissions/rows.py`, il posto solo che la dice: la riga del suo livello, e per una `HIGH` che dichiara
`policy_terms` e non lancia un programma **`Rule.APPROVAL_UNLESS_POLICY`** — «una domanda a ogni uso, salvo una policy
tua **di questa capability** che copra la chiamata: mai la copertura di una sessione, e un sì copre un uso». La leggono
il Guardian dove leggeva il livello, `asks_at_every_use` — che prende la capability e non più il livello —,
`no_policy_for`, e attraverso di loro il catalogo, la nascita e l'executor. Una `CRITICAL` con termini resta `DENY`:
gira solo la riga di `HIGH`.

**Perché una riga nuova.** `APPROVAL_UNLESS_AUTHORIZED` è la riga che la copertura di una sessione raggiunge (ADR 0063
§1): una `HIGH` che la leggesse sarebbe coperta da una sessione guidata. `APPROVAL_EVERY_USE` direbbe «a ogni uso» di
una chiamata che non ha chiesto niente — il nome di una regola è ciò che qualcuno legge in un audit un mese dopo (ADR
0045 §1).

`ASKING_RULES` guadagna la riga, e `CONSUMING_RULES` la deriva (ADR 0046 §1):

| Regola | Consuma |
|---|---|
| `APPROVAL_UNLESS_POLICY` | sì |

**`POLICY_VERSION` passa da `v0.3` a `v0.4`**: un Guardian che permette ciò che prima non poteva non è quello della
versione prima. Le righe vecchie dell'audit continuano a dire la loro.

### 2. Le ragioni per cui una policy non copre, in un posto solo

`no_policy_for(capability)` dà la ragione, letta dal catalogo, dalla nascita (`ADMITS`) e dal Guardian, che nega una
policy presentata per una riga che chiede a ogni uso con «authorization … is a standing policy (§59): » e quella frase:

| Caso | La frase |
|---|---|
| una capability di `LAUNCHES_A_PROGRAM` | «terminal.run launches a program the plan chooses: a program can read the Core's token and create a policy, and only you create one» |
| una `HIGH` senza termini | «browser.login is HIGH and declares no terms: only a grant born from an approval covers it» |
| una `MEDIUM` che nessuna milestone ha dichiarato | «no milestone has said what a policy must bound for …» |
| una riga che non chiede | «… does not ask: it needs no policy» |
| una riga che nega | «… is CRITICAL: its row denies, and no policy covers it» |

**`LAUNCHES_A_PROGRAM`** — in `rows.py`, non nel catalogo, che `rows.py` non importa — è l'insieme delle capability che
lanciano un programma che il piano sceglie, con argomenti che il piano sceglie: oggi `terminal.run`. Un programma lanciato
così gira come chi usa ELA, può leggere il gettone del Core e creare una policy: nessuna policy lo copre. **La regola di
architettura 74**, `a-program-is-launched-by-the-terminal`, tiene vero l'insieme: in `ela.tools` solo il modulo del
terminale, e il registro che glielo consegna, nominano `CommandLauncher`. Il terminale sotto policy è
[M13.16](../milestones/M13.16.md), fuori dalla fila.

### 3. La dichiarazione

Le righe di ADR 0062 §1 che il catalogo applica, con la revisione:

| Riga di ADR 0062 §1 | Da M13.14 |
|---|---|
| sta su una riga che non è `APPROVAL_UNLESS_AUTHORIZED` | si rifiuta dove `no_policy_for` dà una ragione: un programma, una riga che non chiede, una che nega, una `HIGH` senza termini |
| non ha tetti | **tolta**: ciò che limita una policy è il suo scope, la sua fine, e gli usi se li metti |
| sta su una capability senza argomenti con lo scope, o con uno che non è una lista | resta la prima metà; **la seconda è tolta**: un argomento con lo scope che è un valore solo dà un bersaglio per chiamata, e la sua «partirebbe» si chiede al tool per luogo (§5). Gli argomenti con lo scope sono tutti liste o tutti valori soli |
| ha un argomento libero, obbligatorio, che non è una `string` | vale solo per una capability il cui scope è una lista, l'unica la cui «partirebbe» è una chiamata costruita |
| *(nuova)* una `HIGH` che dichiara termini senza `policy_words` | rifiutata: un'anteprima che non dice ciò che ELA farà senza chiedere non si mostra |
| *(nuova)* `policy_words` senza termini | rifiutata: parole di una policy che nessuno può creare |

`PolicyTerms` guadagna **`on_the_core: bool = False`** — un termine, perché cambia ciò che una policy copre (§4) —, e
`CapabilitySpec` guadagna **`policy_words: PolicyWords | None`**, con `does` e `goes`: parole, fuori dai termini, perché
una parola corretta non deve revocare le policy di nessuno. Una riga salvata prima, senza `on_the_core`, si legge
`False`, che è ciò che le due sessioni guidate dichiarano: **le policy di prima continuano a coprire**.

Le dichiarazioni aggiunte:

| Capability | Tetti | Mai coperti | Liberi | Rotta |
|---|---|---|---|---|
| `fs.write` | — | — | `body`, `overwrite`, `purpose` | — |
| `browser.act` | — | — | `path`, `fill`, `click`, `expect_text`, `purpose`, `continues` | — |
| `browser.act_as_you` | — | — | `path`, `fill`, `click`, `expect_text`, `purpose`, `continues` | — |

| Capability | Solo sul Core |
|---|---|
| `fs.write` | sì |
| `browser.act` | no |
| `browser.act_as_you` | no |

| Capability | `does` | `goes` |
|---|---|---|
| `fs.write` | «writes and overwrites any file in these folders, on the Core» | «what it writes goes into these folders, and wherever your system copies them; a file written there may be one your system runs» |
| `browser.act` | «makes any submission on these sites, in ELA's own empty browser» | «what it sends goes to these sites, and is not taken back» |
| `browser.act_as_you` | «makes any submission on these sites as you, in the browser that keeps your accounts» | «what it sends goes to these sites in your name, and is not taken back» |

**Nessun argomento mai coperto**: i confini li sceglie chi crea la policy. `continues` libero vuol dire che una policy
copre anche un gesto che continua la pagina del suo task (ADR 0065 §3). Nessuna stringa che si legge o che va
nell'audit ha il nome di chi usa ELA scritto nel codice: «you», «yours».

### 4. Il Core soltanto: il Guardian legge il nodo, solo per togliere

Una policy di una capability che dichiara `on_the_core` **copre solo uno step piazzato sul Core**: lo scope di
`fs.write` è una cartella del Core, e lo stesso percorso su un nodo è un altro file (ADR 0048 §11). Uno step su un nodo
non è coperto — il gap `ELSEWHERE` — e chiede come prima, con la domanda di ADR 0048 §8.

**Lo controllano l'executor e il Guardian.** L'executor non consegna una policy che non copre; il Guardian nega
`AUTHORIZATION_MISMATCH` una policy consegnata per uno step che non copre. Per questo **`decide` riceve `device_id`**, e
**una regola sola lo legge, solo per togliere**. Quale sia il Core il Guardian lo riceve alla costruzione (`core`), dalla
composizione: `ela.permissions` non importa `ela.devices`. **`device_id=None` vuol dire «non detto», e una policy
`on_the_core` non copre** (§33). È la revisione aperta di ADR 0019 §4: la sua ragione — un nodo che *concedesse*
sarebbe un secondo asse di permessi, più debole — vale ancora; questo può solo negare una copertura, e un test lo
afferma su ogni capability del catalogo: con un nodo la risposta non è mai più permissiva che con il Core.

Firma rivista:

```python
def decide(
    self,
    capability: CapabilitySpec,
    arguments: JsonMapping,
    *,
    task: Task | None = None,
    step: TaskStep | None = None,
    authorization: Authorization | None = None,
    authorization_uses: int = 0,
    author: PlanAuthor | None = None,
    session: SessionCover | None = None,
    device_id: DeviceId | None = None,
) -> PermissionDecision: ...
```

### 5. Gli usi, gli stati e il predicato

`PolicyRequest` guadagna **`uses: int | None`**, e la nascita un controllo, **`USES`**, fra `LIMITS` e `DAYS`: nessuno,
per «senza limite», o un intero da 1 in su, senza un massimo — un `bool` no. Il grant nasce con `max_uses = uses`. Vale
per ogni policy, `MEDIUM` compresa: il campo è uno. Sul filo `uses` è un intero stretto; nella CLI `--uses N`; nella
console il campo «Usi», vuoto per «senza limite».

I controlli della nascita, nel loro ordine:

| # | Controllo | Che cosa deve essere vero |
|---|---|---|
| 1 | `CATALOGUE` | la capability è nel catalogo |
| 2 | `ADMITS` | la capability ammette una policy: nessuna ragione di `no_policy_for` (§2) |
| 3 | `SCOPE` | lo scope non è vuoto, ogni voce è valida e sta nello scope registrato della capability |
| 4 | `LIMITS` | i tetti sono esattamente quelli dichiarati, ognuno valido per il suo schema |
| 5 | `USES` | nessuno, o un intero da 1 in su |
| 6 | `DAYS` | i giorni sono un intero, dal minimo al massimo |

Il predicato, `shortfall(policy, capability, arguments, *, now, uses, on_the_core, gaps)`, ha due gap in più:

| # | Gap | Che cosa manca | La frase, per una policy `3f2a1b2c` |
|---|---|---|---|
| 1 | `REVOKED` | `revoked_at` c'è | «policy 3f2a1b2c was revoked on 2026-11-12» |
| 2 | `EXPIRED` | `expires_at <= now` | «policy 3f2a1b2c expired on 2026-11-13» |
| 3 | `EXHAUSTED` | `max_uses` c'è e gli usi lo hanno raggiunto | «policy 3f2a1b2c was used 5 of its 5 times» |
| 4 | `TERMS` | la capability non dichiara termini, o non quelli con cui la policy è nata — `on_the_core` compreso | «fs.write declares other terms than those policy 3f2a1b2c was created under» |
| 5 | `ELSEWHERE` | i termini dicono `on_the_core` e lo step non è piazzato sul Core, o nessuno ha detto dove | «policy 3f2a1b2c covers only a step that runs on the Core, and this step is not one» |
| 6 | `SITE` | lo scope della policy non copre il bersaglio della chiamata | «a value of path is not among those of policy 3f2a1b2c» |
| 7 | `LIMIT` | un tetto alla volta: il valore della chiamata è sopra, o non è un numero | «max_cost_usd 2.00 is above the 1.10 of policy 3f2a1b2c» |
| 8 | `ARGUMENT` | la chiamata porta un argomento che i termini non classificano | «task_type is never covered by a policy: policy 3f2a1b2c does not cover this call» |

`UNUSABLE` sono i primi tre, `UNCOVERED` gli altri cinque. **Esaurita è come revocata o scaduta: usabile no, coperta
sì**, e lo step **chiede**, con la riga «perché te lo chiedo» che lo dice. `why_lines` resta pura: riceve ogni policy con
i suoi usi, e lo step con il suo luogo.

**`PolicyState` guadagna `EXHAUSTED`**, derivato: una policy che non può più coprire niente non è `LIVE`. Sta fra le
finite, con le scadute e le revocate; **revocarla è il `409` di una policy non viva**, «policy … was used 5 of its 5
times: there is nothing to revoke»; e la console la mostra fra le finite di recente, con «ha finito gli usi».

### 6. «Partirebbe» per luogo, e la spesa di ciò che riuscirebbe

**Alla nascita.** Per una capability il cui argomento con lo scope è un valore solo la chiamata della «partirebbe» di
ADR 0062 §7 non c'è. **`ToolPort` guadagna `prospect_place(place) -> Prospect`**: «potrebbe partire, adesso, una
chiamata il cui bersaglio sta in questo luogo?», risposto dal tool che tiene il confine. La rotta della nascita lo chiede
per ogni voce dello scope, in ordine, e il primo rifiuto è quello della creazione (`PolicyWouldNotStartError`, con il
codice del tool davanti). **Il default di `Tool.prospect_place` rifiuta**, `tool.place_unseen`: un default che dicesse
«partirebbe» sarebbe una difesa che sembra attiva.

| Tool | `prospect_place` |
|---|---|
| `fs.write` | la radice; la cartella classificata — deve esserci, ed essere una cartella: un file è `fs.not_a_folder`, un link `path.symlink` o `path.outside_root` —; poi i posti protetti, `path.ela_s_own` (§7). La risposta porta la cartella come la nomina il disco del Core |
| `browser.act` | il browser c'è, su un sistema dove gira |
| `browser.act_as_you` | lo stesso, con il profilo: dichiarato, sicuro, libero |

**L'anteprima di una policy che tocca un file mostra, per ogni voce dello scope, la cartella risolta sul disco del Core,
intera, accanto alla voce scritta**: ciò che si approva nomina ciò che conta. È contenuto `LOCAL_ONLY`, come i siti.

**All'uso.** Una policy si spende solo per ciò che riuscirebbe adesso: **quando il Guardian permette su una policy di una
riga `APPROVAL_UNLESS_POLICY`, l'executor chiede al tool la prospettiva della chiamata prima del `consume`**, e un
rifiuto chiude lo step con il codice del tool: **nessun uso speso, nessun tool, niente scritto**. È ADR 0045 §6-bis per
una spesa senza domanda. Un link dentro la cartella — anche uno che resta lì —, un posto protetto, un `overwrite` che il
disco smentisce: lo step fallisce, non diventa una domanda. **Solo per le `HIGH`**: una sessione guidata coperta da una
policy resta com'è da ADR 0062.

### 7. I posti protetti

La lista è una, `Settings.ela_s_own()`, e oltre ai posti di ADR 0045 §5 guadagna **il programma del vault**
(`ELA_VAULT_PROGRAM`), **la casa di ELA** (`~/.ela`, una funzione sola, che è anche il default dei posti che la
scrivevano da sé), e **`sys.prefix` e `sys.base_prefix`** — l'interprete che il processo carica, derivato come l'albero
sorgente —, ciascuno con la sua frase all'avvio. Il confronto è `_within` nei due versi — è, contiene, sta dentro —,
per grafia e per ciò che il volume dice: una radice scritta con maiuscole diverse da `~/.ela` non passa più sul volume
del Mac. La lista del nodo guadagna la sua casa e il suo interprete; un nodo non ha un vault.

La stessa lista va ai tool che scrivono un file: alla nascita (`prospect_place`) e a ogni scrittura, sì o policy, un
bersaglio risolto che è, contiene o sta dentro uno dei posti è **`path.ela_s_own`**. **Un file con più di un nome** è
**`path.hard_link`**, a ogni scrittura che lo sovrascriverebbe: il confronto dei posti guarda i percorsi, e un secondo
nome li scavalca. Vale anche sul nodo.

I codici che i tool aggiungono a quelli che gli ADR di prima scrivono — uno scaricamento dal browser scrive un file come
`fs.write`, con la stessa funzione, e ne riceve i rifiuti —:

| Tool | Codici aggiunti |
|---|---|
| `fs.write` | `path.ela_s_own`, `path.hard_link` |
| `browser.download` | `path.ela_s_own`, `path.hard_link` |
| `browser.download_as_you` | `path.ela_s_own`, `path.hard_link` |

E due che solo `prospect_place` dà, alla nascita: `fs.not_a_folder` e, per un tool che non sa guardare un luogo,
`tool.place_unseen`.

`ELA_BROWSER_SITES` rifiuta all'avvio un nome che finisce in `.localhost`, che l'RFC 6761 riserva al loopback.

### 8. Una sessione non è un gesto

Il gesto `act` di una sessione guidata è uno step figlio, con la capability del gesto. **Una policy di
`browser.guided_as_you` non copre mai un `browser.act_as_you`**: il gesto chiede, e la riga «perché» dice «no policy of
yours for browser.act_as_you»; **lo copre solo una policy di `browser.act_as_you`** sul sito, e il `within` della
sessione restringe ancora (ADR 0060). Una policy della sessione consegnata per il gesto è negata, «authorization … is
for browser.guided_as_you»; la parola della stanza consegnata per il gesto è `SESSION_MISMATCH`. Lo stesso per
`browser.guided` e `browser.act`.

### 9. Ogni azione si vede

L'audit nomina la policy a ogni uso — `PERMISSION_DECIDED` con «covered by policy …», `TOOL_EXECUTED` ed
`EXECUTION_VERIFIED` con `authorization_id`. **`AuditLog.read` guadagna due filtri**, `authorization_id` ed
`event_type`, applicati prima di `limit`; il port resta di due membri, e l'audit in sola aggiunta. **`PolicyOut`**
guadagna `risk`, `does`, `max_uses`, `remaining` e `recent` — le ultime azioni fatte sotto la policy, al più cinque
`TOOL_EXECUTED` con il suo id, la più recente prima —: **derivati, mai memorizzati**.

```python
RECENT_MAX = 5
```

`ela policy list` dice il livello, gli usi come «3 of 10» o «3, no limit», e sotto la tabella le ultime azioni; la
console le coppie «Livello», «Che cosa fa senza chiederti», «Usi», «Ultime azioni», e le policy finite di recente. I
bersagli sono `LOCAL_ONLY`: sotto un tetto più stretto la console li tace e lo dice. Si crea e si revoca dalla console e
dalla CLI; nessuna notifica, che è della Fase 15.

**L'anteprima** dice, nell'ordine in cui si legge, il livello, `does`, `goes`, lo scope con la cartella risolta, i tetti,
gli usi — «at most N uses», «no limit of uses» —, la scadenza, «only a step that runs on the Core: a step on a node
asks» per una policy del Core, e ciò che non copre mai, derivato: le capability che chiedono a ogni uso, una chiamata
fuori dallo scope, uno step su un nodo, i gesti di una sessione, e «what has left is not taken back: a revocation stops
only what comes after». La console sotto il tetto `LOCAL_ONLY` e la CLI ne mostrano ogni campo. La conferma di una
policy senza modello porta il `None` dell'anteprima — dalla CLI era un `422` —, e la console il suo testo vuoto.

| Caso | Eccezione | Stato |
|---|---|---|
| la revoca di una policy scaduta, o che ha finito gli usi | `PolicyNotLiveError` | `409` |
| il tool rifiuta un luogo dello scope | `PolicyWouldNotStartError` | `422` |

### 10. Chi crea, cambia e revoca una policy

Solo chi usa ELA crea e revoca una policy, dalla console o dalla CLI; cambiarla vuol dire revocarla e crearne un'altra.
Oltre ai test di ADR 0062: **un test afferma per nome che una policy non si cambia** — i membri dello store che
scrivono, le rotte, le pagine, i comandi —; **le rotte delle policy sono provate per ogni identità e ogni metodo**, con
un gettone di sessione vero; **il contratto di import-linter 16** vieta a `ela.tools` e a `ela.executive` di importare
`ela.api`; e **la regola 66** riporta ogni `.grant(` fuori dalla rotta e dall'executor, qualunque sia il ricevente. Una
revoca fuori dalla rotta su uno store sotto un altro nome resta dichiarata: toglie, non allarga. Nessuna proposta di
policy da parte di ELA.

### Ciò che questo ADR dichiara e non risolve

Il limite di chi usa ELA, «ELA non crea policy da sola», ha tre strade aperte: **il limite è vero quanto le cartelle e i
siti scelti**. Per l'API, chi crea una policy è
chi ha il gettone del Core o una console arruolata, e il gettone sta nel `.env`, che un programma lanciato come l'utente
può leggere. Nessuna capability sotto policy *lancia* un programma (§2); restano tre strade:

1. **`fs.write` sotto una policy può scrivere un programma dove il sistema lo lancia** — `~/Library/LaunchAgents`, un
   file d'avvio della shell, gli hook di un repository —, e quel programma gira come l'utente, legge il gettone e crea
   una policy. L'anteprima lo dice: «a file written there may be one your system runs». **Nessuna lista dei posti che il
   sistema lancia**: sarebbe la lista degli interpreti che ADR 0047 §1 ha rifiutato. Il programma che lancia ELA e gli
   altri del `PATH` stanno qui: solo ciò che il processo carica è fra i posti protetti (§7).
2. **`browser.act_as_you` sotto una policy, su un sito dove vive il codice di ELA**, può cambiarlo come l'utente, e il
   cambio arriva al Mac al prossimo `git pull`. ELA non sa quali siti tengono il suo codice.
3. **Un file scritto sotto una policy, poi lanciato da `terminal.run` con un sì**: la domanda del terminale mostra il
   programma e gli argomenti, non il contenuto del file che un argomento nomina.

E il resto:

- **Su quei siti il modello può fare qualunque gesto come l'utente**, anche uno che una pagina gli suggerisce; **una
  revoca non richiama ciò che è già partito**; il cancello limita i documenti del frame principale, non le richieste che
  il codice di una pagina fa da sé, salvo quando la pagina tiene un file: una pagina può chiamare l'indirizzo di ELA,
  dove l'API vuole il gettone e la console il suo cookie e la stessa origine, che il browser di ELA non ha; ELA non
  risolve i nomi, e un nome dichiarato che porta a una macchina della rete non è riconosciuto.
- **Gli usi contano le spese, non gli effetti** (ADR 0062 §2).
- **La finestra fra il controllo del percorso e l'`open`** resta quella di `ela/tools/fs.py`.
- **Un'altra copia del repository o un altro `.env` sotto la radice** non sono esclusi: il controllo all'avvio legge il
  `.env` e l'albero sorgente di questo processo.
- **Il login e le quattro capability dei file** chiedono a ogni uso fino a [M13.15](../milestones/M13.15.md).

## Alternative

- **Togliere al gettone del Core la creazione di una policy**, lasciandola alla sola console. **Non chiude**: un
  programma che gira come l'utente scrive il database o l'albero sorgente senza passare da nessuna rotta. Rivedrebbe la
  decisione 14 di M13.14 e la CLI di ADR 0062 §10 senza togliere la strada.
- **Una conferma della creazione che un programma non sa dare**: un tasto in un terminale vero non basta, perché un
  programma apre una pseudo-console; serve un secondo fattore fuori da ELA, che oggi non c'è.
- **Una lista dei posti che il sistema lancia**: incompleta dal primo giorno, insegnerebbe che ciò che non c'è è sicuro.
- **La riga `APPROVAL_UNLESS_AUTHORIZED` per le `HIGH` con termini**: una sessione guidata le coprirebbe.
- **Il solo executor per il Core soltanto**: una difesa invece di due.
- **Una policy esaurita che resta `LIVE`**, con «finiti» nella console: una policy che non può coprire niente non è
  viva.

## Conseguenze

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0019** §4 — «il nodo non entra in nessuna regola del Guardian» diventa «in una sola, per togliere»: una policy di una capability che dichiara `on_the_core` non copre uno step su un nodo, né uno di cui nessuno ha detto dove (§4).
- **ADR 0045** §1, §3, §4, §5 — la riga `HIGH` resta `APPROVAL_EVERY_USE` per una `HIGH` senza termini, e una `HIGH` che li dichiara legge `APPROVAL_UNLESS_POLICY`; il predicato in un posto solo è `row_of`; una policy di §59 raggiunge una `HIGH` che dichiara termini; i posti protetti crescono e si confrontano con `_within` (§1, §3, §7).
- **ADR 0047** Contesto — «un'approvazione a ogni uso, che nessuna policy di §59 raggiungerà» resta vero per `terminal.run`, non più per la riga (§2).
- **ADR 0048** §11 — «ogni grant di `fs.*` nasce da un sì ed è monouso» resta vero per uno step su un nodo, che una policy non copre mai (§4).
- **ADR 0060** §4 — un `browser.act` porta il figlio a `WAITING_APPROVAL`, salvo una policy di `browser.act` sul sito (§8).
- **ADR 0062** §1, §2, §3, §4, §5, §7, §12 — le righe della dichiarazione; `max_uses` di una policy non è più nullo, e `USES`; le ragioni di `ADMITS`; i gap; il diniego di una `HIGH` e `POLICY_VERSION`; la «partirebbe» per luogo; una policy di `browser.guided` non copre mai un gesto, che solo una policy di `browser.act` copre (§3, §5, §6, §8).
- **ADR 0063** §1, §6 — «un `act` della sessione è `HIGH` e chiede come sempre», «un `act` chiede sempre»: salvo una policy della capability del gesto (§8).
- **ADR 0066** §4 — «nessuna policy le copre fino a M13.14»: fino a M13.15.

Le altre conseguenze:

- **Il dominio**: `PolicyTerms.on_the_core`, `PolicyWords`, `CapabilitySpec.policy_words`.
- **I port**: `ToolPort` guadagna `prospect_place`; `PermissionGuardianPort.decide` riceve `device_id`; `AuditLog.read`
  guadagna `authorization_id` ed `event_type`.

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `ToolPort` | §59 | async | `prospect_place` |

- **Regola di architettura 74**, `a-program-is-launched-by-the-terminal` (§2).
- **Contratto di import-linter 16**, «ela.tools ed ela.executive non importano ela.api» (§10).
- **Nessuna migrazione**: `on_the_core` ha il suo default, e `max_uses` c'era.

Con questo ADR le regole di architettura sono **settantaquattro** (la 74); i contratti di import-linter **sedici**; i
port restano **trentasei**, le rotte dell'API **settantadue**, i comandi della CLI **trentanove**, le capability
**ventidue**, le identità del middleware **sei**.
