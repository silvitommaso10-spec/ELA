# 0055. La ragione di una fine è quella della transizione che ha chiuso il task: la stessa alla chiusura e alla porta, con il codice dell'errore; e un risultato che non è riuscito dice perché

- **Stato:** **Accettata il 2026-10-06**, quando la prova a mano di `docs/GETTING_STARTED.md` §22 è passata sul Mac
  a `b589b68`, con `scripts/prova_m13_1c_m13_1d_m9_6.py` (§8). Recepisce la SPEC di M13.1c
  (`docs/milestones/M13.1c.md`), decisa dal revisore il 2026-10-02 con le domande 1–5 e la 7 di M13.1d.
  **ADR 0059 §1 e §9** (M13.1e): «Una fonte sola, `TaskRunner._reason`» si legge con quella accanto — la lettura sola della ragione è `ela.tasks.ending`, composta da `TaskEngine.ending`, che il runner chiama come le rotte; e la domanda aperta del nome di chi ha detto no è chiusa da ADR 0059 §3 e §4.
- **Data:** 2026-10-02
- **Riferimenti spec:** §14, §32, §33, §62, §63, §64
- **Milestone:** M13.1c

## Contesto

ADR 0045 §12-bis ha scritto la regola: **ogni superficie umana che riporta un fallimento o un diniego mostra il suo
perché**, e per `run` il perché è il motivo della decisione o `codice: messaggio`. M13.1 l'ha portata fino a
`RunOut.reason` con `_why`, che leggeva la ragione dall'`Execution` restituita dall'executor. La registrazione di
M13.1c ha trovato quattro rami in cui la riga restava vuota; la misura della SPEC, a `ab87d9d` e a `827db61`, ne ha
trovati di più (`docs/milestones/M13.1c.md`, «Il difetto, rimisurato»): **la porta era vuota per ogni diniego e ogni
fallimento**, e la chiamata che chiude il task era vuota dove l'executor non aveva un errore da dare — **un
fallimento consegnato da un nodo**, che chiude lo step e lascia il task `EXECUTING`, uno step che un crash ha lasciato
interrotto o bloccato, un tool finto che diceva `FAILED` senza dire perché. Per `cancelled` M6.3c aveva già scelto
la forma (ADR 0054 §7): il sommario dell'evento d'audit della transizione che ha finito il task.

## Decisione

### 1. La ragione di una fine è il sommario della sua transizione, alla chiusura e alla porta

**Ogni fine che non è `completed` porta la sua ragione**: `denied`, `failed`, `cancelled` ed `expired`. È il sommario
dell'evento d'audit della transizione che ha messo il task nel suo stato — scelto per `payload.new_state`, non per
tipo, perché il no è un `APPROVAL_RESOLVED` —, e senza quella riga il messaggio dello `STATE_CHANGED` della trail con il
nome dell'operazione: la forma di ADR 0054 §7, ora per tutte le fini. **Una fonte sola**, `TaskRunner._reason`, per
ogni uscita di `run`: la porta, la porta con il lock preso (`answer`), la fine raggiunta dal ciclo, il piano bloccato,
la fine scritta sotto il ciclo (`_ended`). **La stessa per la chiamata che chiude il task e per ogni chiamata dopo**
(decisione D della sessione). `completed` resta senza: l'esito si spiega da sé.

**Il nome dell'operazione dice chi ha chiuso il task**: `deny_by_decision` il Guardian, `deny_by_approval` l'utente,
`fail` il runner o l'executor, `recover` l'avvio, `cancel` chi ha fermato, `expire` il tempo. **Il no riporta l'id
dell'identità che ha risposto** — dalla riga di comando quello di `local`, `6c38f1c5-6cda-5680-8a7a-4f061588deed` —,
perché è ciò che l'approvazione registra (`responded_by`); il nome del dispositivo è la domanda aperta di M13.1e.

`_why` non c'è più, e con lei `Execution.error`, che aveva un solo lettore: il runner non legge più la ragione da ciò
che l'executor restituisce. Continua a non scrivere niente di suo (ADR 0019 §2): passa ciò che l'engine ha scritto.

### 2. Il «codice: messaggio» si scrive nella transizione

**Ogni transizione verso `FAILED` scrive come ragione il `codice: messaggio` del suo errore**, il codice solo quando il
messaggio è vuoto: `fail` e l'orfano di `recover`, che scrive la sua ragione da sé. La compone l'engine
(`ela.tasks.engine._said`), che scrive le parole delle sue transizioni — come «rejected by» e «approved by» —; il
runner la passa. Cambiano di conseguenza, per le fini scritte da M13.1c, il messaggio della trail, il sommario e
`payload.reason` di `TASK_FAILED`: nessuna superficie li legge, tranne `run` e l'audit. **Le fini scritte prima**
restano come sono — l'audit è append-only —, e `run` le riporta con le parole con cui sono state scritte: un
fallimento vecchio ha il messaggio e non il codice. Il test chiuso sulle operazioni verso `FAILED` è
`tests/tasks/test_failed_reason.py`.

### 3. Un risultato che non è riuscito dice perché

**Il dominio non costruisce un `ExecutionResult` che non è `SUCCEEDED` né `STARTED` e non ha un `error`** (§64; la
decisione E della sessione). Misurato prima: nessuna costruzione di produzione da cambiare, nessuna riga così nel
database del Mac, un fake e qualche helper dei test. **Il varco di una copia** — `model_copy` non valida — **lo chiude
lo store**, che rifiuta in scrittura ciò che il dominio rifiuta, SQL e finto: è la porta da cui ogni risultato passa
prima che qualcuno lo legga. Una regola d'architettura su `model_copy` non serve: le regole 5, 12 e 15 sorvegliano
copie che nessuno store rilegge.

`_failure_of` non conia più `tool.<status>`: restituisce l'errore del risultato. **Una busta di un nodo che dice
`FAILED` senza errore** — nessun nodo di questo codice la manda — è accettata, e `_minted` le dà un errore del Core,
**`node.unexplained_failure`**, che dice ciò che sa: il nodo ha riportato un fallimento e non ha detto perché. Il
codice nomina il nodo come fonte; un `422` farebbe riconsegnare il nodo fino al `410` (decisione 4 della review).

### 4. La guida mostra la ragione, e il suo controllo la guarda

Il controllo dei blocchi di `run` di ADR 0051 §4 rifiuta **un blocco `denied` o `failed` la cui ragione è vuota o non
comincia con il nome di un'operazione che porta il task in quello stato**, letti da `OPERATIONS` dell'engine e non
scritti nel test; e trova un blocco di `run` **da qualunque sua riga**, non solo da `outcome`: un ritaglio è un blocco
fuori forma, e un blocco con più righe di `run` che non comincia con una di loro è riportato. I due ritagli di §16
passo 5, rimasti alla colonna di prima di M6.3b proprio perché il controllo non li vedeva, sono interi: i valori che
mancavano sono determinati dal piano. **Il ritaglio di `ela approvals` di §16 resta un ritaglio segnato** (M13.1d):
lì i valori che mancano non si conoscono — le due regole convivono, e il test lo dice.

### 5. La strada di `_closed_by_unfinished_verification`, attribuita di nuovo

La registrazione di M13.1c attribuiva a `run` il ramo di `_closed_by_unfinished_verification`. **È il contratto di
`execute` e di `finish` chiamati su uno step `FAILED`** la cui verifica è fallita e il cui task un crash ha lasciato
aperto (ADR 0015 §7), non un ramo di `run`: il runner guarda il piano bloccato prima di scegliere uno step, e da `run`
quella strada è il piano bloccato, con la sua ragione. La difesa resta, e il test che la raggiunge lo dice nel nome,
`test_execute_called_on_a_step_whose_verification_failed_fails_the_task_it_left_open` (decisione 3 della review).

### 6. Righe riviste

Gli ADR non si riscrivono: queste righe si leggono con questo accanto.

- **ADR 0045 §12-bis**: «`run` porta il motivo della decisione per un diniego e `codice: messaggio` per un
  fallimento» — da M13.1c dentro le parole della transizione, e sempre, non solo quando la chiamata le ha ricevute;
  l'ultimo capoverso, «`Execution` prende un campo `error`»: il campo non c'è più (§1). La regola resta mantenuta da
  `run` e da `results`; le altre superfici sono di M13.1e.
- **ADR 0013 §1**: il passo fallisce «con l'errore del risultato o uno coniato dallo stato» — da M13.1c un risultato di
  questa macchina non riuscito ha sempre il suo, e per la busta di un nodo che non dice perché il Core conia
  `node.unexplained_failure` (§3).
- **ADR 0019 §7**: il runner chiude un piano bloccato con l'errore dell'ultimo `STEP_FAILED`, com'era; è la strada di
  ogni fallimento consegnato da un nodo, non solo della ripresa, e la ragione che `run` dice è quella della transizione.
- **ADR 0051, le Conseguenze**: «`denied` e `failed` la portano **quando la chiamata l'ha ricevuta**» — superata (§1).
- **ADR 0054 §7**: «La porta dà la stessa ragione» vale da M13.1c per ogni fine che non è `completed`.
- **ADR 0054 §16**: «il debito è saldato da un file che dice «La prova è passata»» — rivisto da §7: il debito del
  passo 8 lo salda il passo 8 PASSATO sul PC.

### 7. Il debito di ADR 0054 §16, saldato: il passo 8 della prova a mano, passato sul PC il 2026-10-05

**Il giro è stato fatto il 2026-10-05, un giorno dopo la data di ADR 0054 §16** («entro domenica 2026-10-04»),
su `main` a `ab87d9d`, con il Mac e il PC e con lo script di `main`, `scripts/prova_m6_3c.py`. I file sono due:

- **`~/Downloads/prova-m6.3c-20261005-104506.txt`**, delle 10:45. I passi 2–6 come attesi; al passo 5 un no di
  Tommaso a una domanda dell'occhio, che dopo, rilette le tre frasi nella console, ha visto giuste. Al passo 8 il PC
  ha detto la frase di `docs/examples/speak-on-a-node.json`, **che chiede a chi ascolta di premere Ctrl-C**, perché
  era scritta per la prova di §12; Tommaso l'ha premuto sulla finestra di `ela serve`, ELA ha smesso di rispondere,
  e la chiamata seguente dello script all'API è finita in `Unreachable`: **lo script è crollato con un traceback**,
  che è andato sul terminale e non nel file. Il file si ferma a «[8] «ferma» mandato», senza l'ultima riga.
  **Nessun difetto di ELA**: ELA l'ha fermato chi faceva la prova, su istruzione di una frase scritta per un'altra
  prova. I difetti sono dell'esempio e dello script, e li riparano le decisioni Q e R della review (§21 prende un
  esempio suo; lo script che perde ELA a metà giro lo scrive nel file ed esce con 1).
- **`~/Downloads/prova-m6.3c-20261005-174637.txt`**, delle 17:46. **Il passo 8 PASSATO al primo giro**: «c'è ciò
  che il passo richiede: un nodo disponibile, il Mac a batteria», «il «ferma» è caduto dopo il punto», e l'uscita
  attesa di `task show` — fermato dopo il punto, il PC ha consegnato, e lo step si è chiuso come uno step normale.
  **L'unico FALLITO è al passo 5, ed è un passo umano fatto dalla superficie sbagliata**: Tommaso ha premuto «Ferma»
  dal telefono invece che dalla console, e la ragione dice il vero, «fermato dall'iPhone», dove il passo aspettava
  «fermato dal Command Center». ELA ha scritto chi ha fermato il task; non è un suo difetto, e da questo branch lo
  script lo riconosce e fa rifare il passo (decisione S). L'ultima riga dice «La prova non è passata: 1 FALLITI.».

**Il criterio di ADR 0054 §16 è rivisto qui, apertamente.** §16 voleva il debito saldato «da un file che dice «La
prova è passata»». **Era sbagliato**: chiedeva a un debito sul passo 8 di essere pagato anche dai passi che non
c'entrano — i passi 2–6, passati sul Mac il 2026-10-02, che sono la ragione per cui ADR 0054 è Accettata —, e così un
no detto per sbaglio, o un «Ferma» premuto dal telefono, avrebbero tenuto aperto un debito che il passo 8 aveva
pagato. **Il debito era il passo 8, e lo salda il passo 8 PASSATO sul PC: il file delle 17:46.** Il giorno di ritardo
resta scritto qui, accanto alla data che §16 dava.

### 8. La prova a mano, passata sul Mac il 2026-10-06

Tommaso, a `b589b68`, con lo script, in un giro: **`~/Downloads/prova-m13.1c-m13.1d-m9.6-20261006-122115.txt`**.
**19 PASSATI al primo giro**, nessun FALLITO, nessun SALTATO, nessun no a una domanda dell'occhio, e l'ultima riga «La
prova è passata.».

- **Passo 2 — un diniego, due volte**: `browser-read-outside.json`; le due corse dicono `denied` con la stessa ragione,
  `deny_by_decision: EXECUTING -> DENIED (targets ['example.org'] of browser.read are not within scope […])`, alla
  chiusura e alla porta (§1).
- **Passo 3 — un fallimento, due volte**: `browser-left-site.json`; le due corse dicono `failed` con
  `fail: EXECUTING -> FAILED (browser.left_site: …)`, il codice nelle parole della transizione (§2).
- **Passo 4 — il no**: `first-task.json`; il blocco di `ela approvals` del task ha la forma del blocco di §6 (M13.1d,
  §4), il no dato con `ela task deny`, e le due corse dicono `deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by
  6c38f1c5-6cda-5680-8a7a-4f061588deed)`, l'id di `local` (§1).
- **Passo 5 — l'help** di `ela task run` dice che `denied`, `failed`, `cancelled` ed `expired` portano sempre il loro
  perché.

**Nessun difetto del codice di ELA.** Le correzioni degli script di questi giorni — 2-bis, Q, R, S e U — sono nel
documento di M13.1c, «L'implementazione, e dove si scosta».

## Alternative considerate

- **La sola ragione della transizione** (`payload.reason`, il messaggio della trail) invece del sommario. Scartata
  (domanda 1, (b)): alla chiusura non avrebbe cambiato ciò che si legge, ma `cancelled` avrebbe dovuto seguire, e la
  ragione di un «ferma» dato senza parole sarebbe tornata vuota — il vuoto che ADR 0054 §7 aveva tolto.
- **Lasciare `expired` fuori**, come la registrazione. Scartata (domanda 2): le fonti sarebbero rimaste due, e un task
  scaduto avrebbe avuto una ragione sotto il ciclo e nessuna alla porta.
- **Rifiutare la busta di un nodo senza errore** con un `422`, o lasciar scattare il validatore. Scartata (domanda 4):
  il nodo riconsegnerebbe fino al `410`, la forma che ADR 0048 §3 ha chiuso per il surrogato.
- **Una regola d'architettura su `model_copy` dello stato di un risultato.** Scartata (§3): lo store chiude il varco
  dove ogni risultato passa.

## Conseguenze

- `RunOut.reason` e l'help di `ela task run` dicono che `denied`, `failed`, `cancelled` ed `expired` portano sempre il
  loro perché; lo tengono `tests/api/test_run_reasons.py` e `tests/cli/test_run_reasons.py`, un caso per ramo della
  tabella della SPEC, con le due chiamate.
- `Execution.error` e `_why` non ci sono più; `ExecutionResult` ha un validatore; gli store rifiutano in scrittura; il
  tool finto di `ela.testing` dice perché quando non riesce.
- Nessuna regola d'architettura nuova, nessun port, nessuna rotta, nessun comando, nessuna migrazione: i totali che il
  test di ADR 0054 appunta restano quelli.
