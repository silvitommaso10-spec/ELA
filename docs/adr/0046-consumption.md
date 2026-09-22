# 0046. Il grant di un sì si consuma: la regola del consumo derivata dalla domanda, un sì che non copre due effetti, e le righe che il merge di M13.1 ha reso false

- **Stato:** Accettata
- **Data:** 2026-09-21
- **Riferimenti spec:** §27, §29, §32, §33, §57, §59, §62
- **Milestone:** M13.1b

## Contesto

ADR 0045 §3 ha aperto la riga `HIGH` come **un'approvazione a ogni uso**, e sotto l'etichetta «Righe
di consumo aggiunte:» ha scritto `APPROVAL_EVERY_USE | sì`: una `HIGH` permessa si regge sul grant
nato dal sì, e lo spende. Il codice non l'ha mai fatto. `CONSUMING_RULES` era una lista scritta a mano
nell'executor — `APPROVAL_UNLESS_AUTHORIZED` e `AUTHORIZATION_REQUIRED` — e la riga nuova non c'era:
un'azione `HIGH` approvata girava senza spendere il suo sì, il grant restava a zero usi per la sua
ora, e il risultato e `TOOL_EXECUTED` non dicevano **con quale autorizzazione** l'azione era avvenuta
(§32), proprio per il livello che chiede a ogni uso.

Nessun test se n'era accorto, per due ragioni che sono una: il test del documento leggeva la tabella
«Regola | Consuma» **solo da ADR 0013**, e la proprietà dell'executor **derivava l'atteso da
`CONSUMING_RULES`** — il vizio di ADR 0045 §13, un appunto che si adatta al valore che dovrebbe
difendere. E la proprietà non raggiungeva mai una `HIGH` permessa, perché generava solo grant
permanenti, che una `HIGH` non accetta.

Le domande erano: da dove si legge la risposta a «questa decisione si regge su un grant?»; se il grant
non speso poteva coprire davvero una seconda esecuzione; e in quale punto del ciclo lo si spende
perché un sì non copra mai due effetti.

## Decisione

### 1. La regola del consumo si deriva dalla domanda

```python
CONSUMING_RULES = ASKING_RULES | {Rule.AUTHORIZATION_REQUIRED}
```

`RISK_POLICY` dice quale regola ha ogni livello, non quale regola chiede: quella frase è scritta una
volta, `ASKING_RULES`, accanto alla tabella, e il Guardian si comporta secondo lei — una riga fuori da
lì, senza un grant richiesto, è permessa senza domanda. Le regole sotto cui un `ALLOWED` si regge su un
grant sono esattamente i valori che il `settled_by` del Guardian può prendere: le righe che chiedono,
più `AUTHORIZATION_REQUIRED` quando è la capability o lo step a volere un grant (ADR 0011 §7). **Il
consumo non può più divergere dalla domanda**: una riga che chiede consuma perché chiede.

È la forma che ADR 0045 §3 aveva già deciso per la copertura — «il predicato vive in un posto solo»,
`asks_at_every_use`, letto dal Guardian e dall'executor — **estesa al consumo**. La docstring di
`ASKING_RULES` lo prometteva («the executor reads the same set to know when a decision rests on its
grant»), e adesso è vera.

### 2. Il test che la tiene vera, per ogni valore di `Rule`

`tests/executive/test_consuming_rules.py` ha **uno scenario per ogni membro di `Rule`** — capability,
argomenti, step, task, grant — e il Guardian decide la stessa chiamata con quel grant e senza. Se
l'esito è `ALLOWED` con il grant e non lo è senza, l'`ALLOWED` si regge sul grant e la regola deve stare
in `CONSUMING_RULES`; altrimenti no. Ogni scenario deve produrre davvero la regola sotto cui è
archiviato, così la tabella non può mentire su quale regola esercita. **Il mondo è chiuso su `Rule`**:
un membro nuovo senza scenario fa fallire il test, e uno il cui `ALLOWED` si regge su un grant lo fa
fallire finché non consuma.

Gli scenari sono **precondizioni, non attese**: ciò che il test afferma lo legge dal comportamento del
Guardian, non da `CONSUMING_RULES`. La stessa idea sostituisce la proprietà cieca dell'executor, che
ora ha un oracolo suo — *un grant si consuma se e solo se la decisione è `ALLOWED`, un grant è stato
consegnato, e la stessa chiamata senza grant sarebbe stata una domanda* — e genera anche il grant nato
da un sì, usabile, esaurito e scaduto. E `tests/security/test_high_risk_capability.py` afferma sul
comportamento ciò che §32 chiede: un'azione `HIGH` approvata spende il suo grant, e il risultato, il
record `STARTED` e `TOOL_EXECUTED` lo nominano.

### 3. Il punto in cui il grant si consuma, e un sì che non copre due effetti

Il ciclo di una chiamata locale è `authorize` → **`consume`** → il record `STARTED` (se il tool non si
può rifare) → il tool → il salvataggio dell'esito → `TOOL_EXECUTED`. **Il grant si consuma dopo il sì
del Guardian e prima che qualunque cosa agisca** — l'ordine di ADR 0012 §6, con l'istante unico di ADR
0013 §6. Questo ADR non lo sposta: fa passare la riga `HIGH` da quel punto, da cui finora passava
diritta. Quel punto chiude il caso per tre fatti già veri:

- **`consume` è una sola `UPDATE` condizionale**: incrementa gli usi solo se sono sotto il massimo e il
  grant non è scaduto. Un grant nato da un sì ha un uso solo, per invariante del dominio (ADR 0012
  §1): **una sola chiamata, al massimo, spende quel sì.**
- **La spesa è scritta prima dell'effetto.** Un processo che muore dopo il consumo — prima del tool
  (finestra 6 di ADR 0015 §8) o dopo il tool e prima del salvataggio (finestra 7a) — lascia il grant
  esaurito: la ripresa lo trova non usabile, il Guardian risponde `REQUIRES_APPROVAL`, e l'utente
  riceve **una domanda nuova**. È la clausola «grant monouso speso → domanda all'utente» della riga 7a.
- **Un processo che muore prima del consumo** non ha né effetto né spesa: la ripresa decide di nuovo e
  agisce una volta.

Due esecuzioni insieme possono ricevere entrambe `ALLOWED`, ma una sola `UPDATE` riesce; l'altra va
nella domanda **senza raggiungere il tool**. Quindi **un sì copre al massimo un effetto**, con
qualunque tool — e non dipende più dall'idempotenza né dal record `STARTED`, che restano difese in
più. Il limite dichiarato della riga 7a resta: l'effetto di un tool morto prima del salvataggio è
avvenuto e nessun esito lo registra. Il prezzo resta quello di ADR 0012 §6: un secondo sì anche quando
nessun effetto è avvenuto.

**La riga 7a ha adesso un test che raggiunge la sua clausola sul grant**:
`test_window_7a_a_spent_single_use_grant_asks_again_and_never_acts_twice`, in
`tests/executive/test_executor_recovery.py`, su un tool `HIGH` **idempotente** — la forma in cui nessun
`STARTED` sta fra un sì e un secondo effetto — e su `core.echo_guarded`. Accanto, i due lati del
consumo: morto prima, la ripresa agisce una volta; morto dopo, chiede. Prima di questo ADR l'unico
test della finestra 7a usava `core.echo`, che non chiede un grant, e la clausola non la raggiungeva
nessuno, per nessuna regola.

### 4. La gravità, misurata

Misurata sull'albero a `1c24ec1`, prima della correzione, con due sonde — la composizione di
produzione con gli store SQL e il `fs.write` vero, e l'executor del mondo di prova — i cui output
integrali stanno nel documento di M13.1b e fuori dall'albero tracciato.

- **Su ciò che girava, nessuna seconda scrittura sotto lo stesso sì** — ma **non per merito del
  conteggio d'uso**. L'unica capability `HIGH` di produzione, `fs.write`, non è idempotente, e la
  seconda esecuzione l'hanno fermata altre difese: il grant nato da un sì è legato al suo task e al
  suo step, un task chiuso non si cammina di nuovo, il record `STARTED` con il suo indice unico ferma
  la ripetizione dopo un crash e la seconda di due esecuzioni insieme, e l'API rifiuta un secondo `run`
  dello stesso task (ADR 0023 §9).
- **Dove il conteggio era l'ultima difesa, il sì è stato speso due volte.** Su un tool `HIGH`
  idempotente, nella finestra 7a di ADR 0015 §8, la ripresa ha rieseguito il tool sotto lo stesso sì
  **senza nessuna domanda**: la riga dichiarata «grant monouso speso → domanda all'utente» era violata.
  Con due runner insieme sugli store SQL, il Guardian ha detto `ALLOWED` due volte sotto un grant
  monouso, e solo l'indice dei `STARTED` ha fermato la seconda scrittura.
- **Per ogni `fs.write` riuscita**: `authorization_id` nullo sul risultato e in `TOOL_EXECUTED`, e il
  grant a zero usi fino alla scadenza.
- **Come si è chiuso**: con il §3. Misurato dopo la correzione, la finestra 7a sul tool `HIGH`
  idempotente chiede una seconda volta, e il tool è chiamato una volta; con due runner insieme la
  seconda decisione è `REQUIRES_APPROVAL`, e il tool è chiamato una volta. Quella corsa resta fuori da
  ogni configurazione dichiarata, e la correzione ne cambia l'esito: il runner che perde va nella
  domanda, la domanda vede il file ormai scritto e fallisce lo step, e in una corsa su quattro il task
  finisce `FAILED` con il file scritto — scritto nei rischi di M13.1b, non riparato qui.

### 5. I test del documento leggono ogni tabella «Regola | Consuma»

Un ADR è immutabile, quindi un ADR successivo aggiunge le sue righe sotto la stessa intestazione, come
ADR 0045 §3 ha fatto. Il test le legge **tutte**, in ordine di numero, e confronta l'unione con
`CONSUMING_RULES`. **Se due tabelle si contraddicono, vince la più recente**, e il messaggio del test
mostra ogni riga con l'ADR da cui viene e quelle che una più recente ha superato. Il caso negativo si
misura sull'unione e non su ADR 0013 da sola: ammorbidire la sola tabella di ADR 0013, dopo la
derivazione, non avrebbe più potuto fallire.

### 6. Righe riviste

Un ADR accettato non si riscrive: le righe qui sotto si leggono con questa accanto, e la riga «Stato:»
di ciascun ADR lo dice.

- **ADR 0045 §8** — «l'audit porta il percorso e la dimensione, e mai i byte». **La dimensione di una
  lettura riuscita non è mai stata nell'audit**: sta nel risultato, accanto al contenuto (`bytes`);
  l'audit porta il percorso. Il terzo punto dello stesso paragrafo resta vero: una lettura *fallita*
  porta le dimensioni nel suo errore, per scelta. Nessun canale nuovo si apre nell'audit.
- **ADR 0024 §8** — «Sotto al token, ogni variabile facoltativa» e «`ELA_API_TOKEN`, che è l'unica
  obbligatoria, esce con `2`». Da M13.1 `ELA_FS_ROOT` ed `ELA_FS_SCOPE` non hanno un default e fermano
  l'avvio. `ela init` le tiene ora in `REQUIRED`, in un blocco loro sopra le facoltative, le nomina
  prima di `ela serve`, ed **esce con `2` su un `.env` che non le imposta**, nominandole. Il test non
  confronta due liste: scrive ciò che `init` scrive più quelle righe, con l'ambiente svuotato di ogni
  `ELA_`, e chiede a `Settings.load()` se ELA partirebbe — e senza ciascuna di esse, se non partirebbe.
- **ADR 0011 §7** — «`HIGH` resta `DENIED`». Da M13.1 `HIGH` chiede a ogni uso (ADR 0045 §3);
  `requires_authorization` continua a stringere soltanto.
- **ADR 0045, Conseguenze** — «`paths.py` ha `describe`». `describe` è stata tolta prima del merge di
  M13.1: il bersaglio risolto che una domanda mostra lo dà il `prospect` del tool, con la stessa
  funzione che decide l'esecuzione (ADR 0045 §6-bis).

ADR 0024 §8 e ADR 0045 §8 sono le due righe che la review di M13.1b ha assegnato a questo ADR; ADR 0011
§7 e le Conseguenze di ADR 0045 ci entrano per la regola della stessa review — **entra ciò che il merge
di M13.1 ha reso falso** —, perché una riga di un ADR si corregge solo con un ADR.

## Alternative considerate

- **Aggiungere `APPROVAL_EVERY_USE` alla lista a mano** — riparava la riga e lasciava la ragione del
  difetto: la prossima riga che chiede sarebbe stata dimenticata allo stesso modo. Scartata dalla
  review.
- **Nessuna lista: la decisione dice se si è retta sul grant** — più robusta, ma cambiava che cosa
  `PERMISSION_DECIDED` porta, che oggi è il grant ricevuto, usato o no (ADR 0011 §6). Il significato di
  un campo dell'audit non cambia in una riparazione. Scartata.
- **Togliere il test del documento invece di riscriverlo** — la tabella di ADR 0013 §6 sarebbe rimasta
  senza lettore, la forma esatta in cui la riga di ADR 0045 è andata alla deriva. Scartata.
- **Spostare il consumo dopo il tool** — avrebbe tolto il secondo sì della finestra 6, e riaperto la
  finestra 7a: un effetto avvenuto sotto un grant ancora intatto. Scartata: è ADR 0012 §6.
- **Annotare le righe rese false senza un ADR, nominando il documento della milestone** — una forma
  nuova, dove finora una riga «Stato:» ha sempre nominato un ADR. Scartata dalla review.

## Conseguenze

- `CONSUMING_RULES` è derivata; `ela.executive` lo esporta come prima. **Il Guardian non cambia
  comportamento**, e nessun test di `tests/permissions/` è cambiato: è la prova che la riparazione
  tocca solo l'executor.
- Ogni `fs.write` approvata spende il suo grant, e l'audit lo nomina. Dopo un crash nella finestra 6
  una `HIGH` costa un secondo sì, come una `MEDIUM` già costava.
- `ela.cli.setup` esporta `REQUIRED`; `ela init` esce con `2` su un `.env` senza le righe
  obbligatorie.
- `tests/foreign_machine.py` nasconde `/usr/sbin/screencapture`, che è il binario che ELA usa, e un test
  lega la sua lista ai percorsi che `ela.infrastructure.machine` esporta, leggendo il plugin come testo:
  importarlo renderebbe finta la macchina di tutto il processo.
- **Il numero 0046 era promesso a M13.2**, che passa ad ADR **0047** e aggiorna i suoi riferimenti
  quando riprende, dal suo branch.
- **Che cosa questo ADR non fa**: non apre un canale di numeri nell'audit, non lega le chiavi della
  domanda ai campi delle superfici (M13.2), e non corregge la citazione di ADR 0038 §16 in ADR 0045 §4,
  che è di M13.2.
