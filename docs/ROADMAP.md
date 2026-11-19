# ELA — la roadmap

**Dal 2026-11-13 questo è il solo posto dove vive l'ordine delle milestone** (decisione di Tommaso, sul
branch `docs-roadmap`). Prima l'ordine stava in [`STATO.md`](STATO.md), nelle file delle voci 5.10, 5.11 e
5.12, e nella riga «Ordine» di ogni documento in [`milestones/`](milestones/): quelle restano come storia, con
una riga datata che rimanda qui. Una frase d'ordine nuova si scrive qui, con la sua data, e in nessun altro posto.

## Come si legge

- **Le tappe sono numerate, e i numeri non scalano.** Quando una tappa finisce resta qui con il suo numero, e
  le sue milestone restano al loro posto con lo stato del loro documento. Un numero di tappa nomina sempre la
  stessa tappa.
- **Una tappa non è una fase.** La fase di una milestone è il numero prima del punto, e il suo nome glielo dà
  il [changelog](CHANGELOG.md): la regola della 4.1 di `STATO.md` sui nomi delle fasi resta com'è. Una tappa
  mette insieme milestone di fasi diverse perché servono alla stessa cosa.
- **Accanto a ogni milestone c'è lo stato del suo documento**: la prima parola della sua riga «Stato:», letta
  come la leggono `STATO.md` e il changelog. Una milestone **riservata** ha un numero e nessun documento, e
  accanto porta `riservata`.
- **La prossima è la prima voce, nell'ordine, che non è fatta.** Qui non c'è una frase «la prossima è…»: è
  una frase da rincorrere a ogni merge, e la 4.1 di `STATO.md` dice com'è invecchiata.
- **Fuori dalla fila** ci sono le milestone senza un posto: si fanno insieme ad altro, quando capita.

## Le tappe

### Tappa 1 — Le policy

*A che cosa serve:* chi usa ELA decide una volta, lui, che cosa ELA fa da sola, e le sue policy arrivano alle
azioni `HIGH`.

- `M13.14` — Implementata — Le policy di Tommaso arrivano alle azioni HIGH

### Tappa 2 — La pulizia, su un branch solo

*A che cosa serve:* la suite torna a dire il vero — i due test che a volte diventano rossi senza una causa vista, e
la disciplina della suite con i debiti che porta e la misura di dove va il suo tempo.

- `M13.13b` — Implementata — Uno scaricamento interrotto che a volte lascia il suo file a metà
- `M9.5` — Implementata — La disciplina della suite: gli skip che si accorgono di essere saltati, e i test che aspettano un evento

### Tappa 3 — Più permessi, e il PC

*A che cosa serve:* le policy arrivano al login e ai file dal browser, i file arrivano a tutto il computer, e il
browser arriva sul PC.

- `M13.15` — Implementata — Le policy di Tommaso arrivano al login e ai file dal browser
- `M13.17` — Implementata — I file di tutto il computer
- `M13.17b` — Proposta — Un test di uno script non lancia un processo vero e non chiama un fornitore vero
- `M13.11` — Proposta — Il browser sul PC: le capacità di M13.9 e M13.10 sul nodo Windows, e il verdetto che torna in busta

### Tappa 4 — ELA lavora sul codice

*A che cosa serve:* ELA lavora su un progetto con una sessione di Claude Code, e poi sul proprio codice, quando
glielo si chiede; il diff si approva, e il merge non lo fa mai ELA.

- `M14.7` — Proposta — Il lavoro su un progetto: una sessione di Claude Code in un worktree, e il diff che si approva prima del branch
- `M16.1` — riservata — ELA ripara il proprio codice su richiesta

### Tappa 5 — ELA usa il computer

*A che cosa serve:* mouse, tastiera e schermo sotto il Guardian, il modello che li guida, il terminale su un
nodo, il file che vive su una macchina, e il terminale sotto le policy.

- `M13.20` — riservata — I programmi che ELA lancia, fra i suoi posti
- `M13.18` — riservata — L'eseguibile firmato
- `M13.5` — Proposta — Computer control: il muro dichiarato prima di cominciare
- `M14.4` — Proposta — Il computer guidato dal modello: lo schermo, con il meccanismo di M14.3
- `M13.19` — riservata — Mouse e tastiera sul PC
- `M13.7` — Proposta — Il terminale su un nodo: il Job Object, e `argv` che su Windows diventa una stringa
- `M13.8` — Proposta — Un file che vive su una macchina: quale disco, e chi lo dice
- `M13.16` — Proposta — Il terminale sotto le policy di Tommaso, con un confine dimostrato

`M13.18` si apre in questa tappa **solo se il grant TCC di `M13.5` non tiene**: è la condizione d'ingresso di
`M13.5`, e la regola della 5.11 di `STATO.md`, «Chi apre la milestone dell'eseguibile firmato». Se il grant
tiene, il numero resta riservato, e la regola resta la stessa: la apre la prima milestone che ci sbatte contro.
`M17.3`, nella tappa 8, la vuole prima di sé (il suo documento, «Ordine»).

***Annotato il 2026-11-19*** (risposta 57 della review di M13.17): **`M13.20` è la prima voce della tappa**, riservata.
La tappa 5 è quella in cui ELA comincia a lanciare e guidare i programmi del computer, e la dichiarazione a mondo chiuso
di ciò che ELA lancia costa meno prima che i lanciatori aumentino.

### Tappa 6 — ELA con iniziativa

*A che cosa serve:* ELA riparte da ciò che le è già riuscito, sa che cosa succede nella giornata, ricorda, e parla
per prima: la sua domanda trova chi la usa dove sta, e quando serve lo chiama.

- `M15.2` — Proposta — Le skill: un lavoro già riuscito, salvato con il suo verifier, da cui il Planner riparte
- `M14.5` — Proposta — Il contesto nel Planner: che cosa ELA sa della giornata, nel prompt che scrive un piano
- `M15.4` — riservata — La memoria
- `M15.5` — riservata — La proattività
- `M15.6` — riservata — La domanda trova chi la usa dove sta
- `M15.7` — riservata — Le chiamate
- `M15.1` — riservata — La wake word
- `M15.3` — Proposta — ELA conosce il nome di chi la usa

### Tappa 7 — ELA si migliora

*A che cosa serve:* ELA si accorge dei propri errori e propone come ripararli; una modifica si prova su una copia,
si confronta con la versione di prima, e si torna indietro. Il sì e il merge restano di chi la usa.

- `M16.2` — riservata — ELA si accorge dei propri errori, e propone
- `M16.3` — riservata — La copia di prova, il confronto e il ritorno alla versione prima

### Tappa 8 — Design e uso reale

*A che cosa serve:* ELA sullo schermo senza la dashboard aperta e una vista per ogni task; poi un periodo in cui
ELA si usa davvero, e il redesign con ciò che, usandola, non piace.

- `M17.3` — Proposta — La presenza desktop: ELA sullo schermo senza la dashboard aperta
- `M17.5` — Proposta — Il Task Center: ogni task, vivo o finito, in una vista sua
- Un periodo di uso reale di ELA. Non è una milestone: è l'ingresso di `M17.4`, insieme all'elenco di ciò che
  a Tommaso non piace (il suo documento, «Ordine»).
- `M17.4` — Proposta — Il passaggio di design del Command Center: le viste tutte insieme, quando guardarle non basta più

### Tappa 9 — Oltre il core

*A che cosa serve:* ciò che viene dopo il core, **senza un numero e senza un ordine fra loro**. Nessuna di queste
è una milestone, e il giorno in cui una lo diventa prende un numero e la sua riga fra le riservate.

- **Ricerca, studio e creatività** (§40, §42, §43). Dopo le skill di `M15.2` si decide se sono skill o milestone.
- **I pagamenti.**
- **Commerce.**
- **ELA Finanza.**
- **Un'ELA per persona.**

Ciò che Tommaso ne ha detto finora — Commerce, ELA Finanza, un'ELA per ognuno installata e impostata da lui — è
nella 4.3 di [`STATO.md`](STATO.md), «Oltre le fasi in fila».

## Fuori dalla fila

Da fare insieme ad altro, quando capita. Una condizione d'ingresso, dove c'è, sta nel documento.

***Dal 2026-11-17*** (decisioni 56 e 57 della review delle tre SPEC di `m9.5-la-pulizia-della-suite`): **`M13.4g`
esce dalla tappa 2** — nelle due serie della sua misura la causa non si è vista —, e **si riapre quando il suo test torna
rosso in un giro**: quel giro, con il log della suite (`tests/suite_log.py`, il passo della CI che lo porta via), è la
misura. **`M9.8`**, nata dal taglio di M9.5, **passa davanti se uno dei suoi test torna rosso in un giro**, con la
regola di `M13.13b`.

***Annotato il 2026-11-17*** (decisione 69 della review di M13.15, una scelta d'ordine di Tommaso): uno dei test di
`M9.8`, `test_a_page_that_is_still_arriving_is_waited_for_before_it_is_asked_about`, è stato rosso in un giro di `make
check` a `4e4adc5`, alla riga 293 — il lancio del browser del profilo —, **prima** dell'attesa che M9.8 eredita (riga
298). **M9.8 non passa davanti per questo rosso**, che è di **`M13.9d`**; passa davanti quando uno dei suoi test è rosso
per l'attesa che eredita. **`M13.9d`** passa davanti al prossimo rosso di un test che lancia il browser del profilo per
un lancio non arrivato: quel giro, con il log della suite, è la misura.

***Annotato il 2026-11-18*** (decisione 75 della review di M13.15, una scelta d'ordine di Tommaso): **`M13.9d` passa
davanti, su `m13.15-le-policy-al-login-e-ai-file`**, prima che la prova a mano di M13.15 si rifaccia. È venuto prima del
rosso di un test un caso del prodotto, sull'ELA vera: la prova del 2026-11-17 a `3256e4b` si è appesa al passo 3. Il
browser del profilo è caduto 1,28 s dopo il lancio, e lo step non è più finito. La SPEC è in
[`M13.9d.md`](milestones/M13.9d.md).

***Annotato il 2026-11-18*** (risposta 90 della review della SPEC di M13.9d): **M13.9d si chiude con la parte del
prodotto**, una chiusura del browser ha un limite. **Il rosso di `make check` a `4e4adc5`** — un lancio del browser del
profilo non arrivato in 180 s, in un test — **è ridichiarato in `M13.9e`**, Proposta, fuori dalla fila: si riapre al
prossimo rosso di un test che lancia il browser del profilo per un lancio non arrivato, e quel giro, con il log della
suite, è la misura.

***Annotato il 2026-11-18*** (decisione 103 della review della fermata di M13.9d a `5082459`): **il crash della prova
del 2026-11-17 è un difetto di `browser.download_as_you`**, che c'è da M13.13 — dal terzo scaricamento con il browser del
profilo sullo stesso profilo, Chrome for Testing cade al gesto —, ed è registrato in **`M13.13c`**, su
`m13.15-le-policy-al-login-e-ai-file`. **La prova a mano di M13.15 non può passare prima di M13.13c**; la sua SPEC si
scrive su quel branch dopo la misura che ne isola l'innesco (decisioni 104 e 105). M13.9d si chiude con ciò che ha
fatto, e ADR 0071 e ADR 0072 restano Proposta fino alla prova.

***Annotato il 2026-11-18*** (ultimo blocco di `m13.15-le-policy-al-login-e-ai-file`, decisioni 128 e 130): **M13.15,
M13.9d e M13.13c sono fatte**, con la prova a mano della sezione 34 passata a `fe776f4`, e ADR 0071, 0072 e 0073
Accettate. **`M13.9e` resta Proposta, fuori dalla fila.** **`M13.17` è la prossima**: il suo documento nasce ora, ed esce
dalle riservate. **`M13.14b`** è una riparazione di M13.14 trovata dopo la prova, fuori dalla fila.

- `M9.2` — Proposta — Le liste che restano scritte a mano
- `M9.7` — Proposta — Ogni blocco della guida che mostra un'uscita della CLI è confrontato con la CLI
- `M9.8` — Proposta — Le attese che nessun elenco conosceva
- `M10.3b` — Proposta — Una riga che `ela init` scrive, tolto il `#`, ferma l'avvio
- `M13.4d` — Proposta — Lo shell del browser vuoto gira senza il sandbox di Chromium
- `M13.4g` — Proposta — Il click che apre un'altra pagina, con il browser del profilo: un'azione che a volte non dice la sua pagina
- `M13.6` — Proposta — Spostare un lavoro già in corso: il ripiazzamento, quando due capability sanno dichiararsi ripetibili
- `M13.9d` — Implementata — Un lancio del browser del profilo che a volte non arriva
- `M13.9e` — Proposta — Un lancio del browser del profilo che in un test, una volta, non è arrivato
- `M13.13c` — Implementata — Il browser del profilo che cade allo scaricamento, dal terzo sullo stesso profilo
- `M13.14b` — Proposta — Il modello sente dire che il gesto chiede sempre, e da M13.14 non è vero
- `M14.1c` — Proposta — Il caso peggiore senza prezzo: un ramo e un rifiuto che nessun produttore raggiunge
- **WhatsApp Web con il profilo di ELA**, senza un numero: nessuna milestone finché la causa della barra di
  caricamento ferma non è nota ([ADR 0065](adr/0065-browser-steps.md) §5, punto 9).

## Riservate

Un numero riservato non ha un documento. **Il documento nasce quando la milestone è la prossima o quella dopo**:
quel giorno la sua riga esce da questa tabella, e accanto al suo numero, nella tappa, compare lo stato del
documento. Un numero non sta mai nei due posti.

| Numero | Titolo | Che cosa porta | Spec |
|---|---|---|---|
| `M13.20` | I programmi che ELA lancia, fra i suoi posti | Ogni programma che ELA lancia — i browser, il trascrittore con il suo modello, e gli altri che il suo censimento trova — derivato a mondo chiuso da chi lo lancia, ed entrato fra i posti che nessuna lettura e nessuna scrittura raggiunge; ADR 0068 e ADR 0074 lo dichiarano e non lo risolvono. | §58, §65 |
| `M13.18` | L'eseguibile firmato | Solo se il grant TCC di `M13.5` non tiene (la tappa 5). | §11, §20 |
| `M13.19` | Mouse e tastiera sul PC | Le capacità di `M13.5` e di `M14.4` sul nodo Windows: chi usa ELA vuole le stesse capacità sul Mac e sul PC, come `M13.11` fa per il browser. | §17, §18, §20, §56 |
| `M15.1` | La wake word | Il quarto stato del microfono, e la riga della 5.6 di `STATO.md` sulla voce: una voce riconosciuta non vale mai come un sì. | §9, §11, §34 |
| `M15.4` | La memoria | Il Memory Core. | §21, §22 |
| `M15.5` | La proattività | ELA parte da sola. | §34, §61 |
| `M15.6` | La domanda trova chi la usa dove sta | Anche sul computer. | §6, §7, §62 |
| `M15.7` | Le chiamate | Con Twilio. | §7, §8 |
| `M16.1` | ELA ripara il proprio codice su richiesta | Il meccanismo di `M14.7` puntato sul suo repository; il diff si approva, e il merge non lo fa mai ELA. | §35, §36 |
| `M16.2` | ELA si accorge dei propri errori, e propone | Con l'Evolution Dashboard. | §38 |
| `M16.3` | La copia di prova, il confronto e il ritorno alla versione prima | Ogni evoluzione si prova su una copia, si confronta, e si può disfare. | §36, §37 |

## Che cosa tiene vero questo file

`tests/docs/test_roadmap.py`, a mondo chiuso, con i suoi casi negativi:

- ogni milestone `Proposta` con un documento compare qui **una volta sola**, in una tappa o fuori dalla fila, e
  nessuna voce compare due volte;
- **lo stato accanto a ogni voce è quello del suo documento**, e il titolo è quello del documento o della riga
  fra le riservate;
- **ogni id che questo file nomina ha un documento oppure è riservato, mai tutti e due**, e ogni numero
  riservato sta in una tappa;
- le tappe sono numerate da 1 senza buchi, e le sezioni della spec delle riservate esistono.
- ***dal 2026-11-14*** (decisione 6 di `m9.5-la-pulizia-della-suite`): **ogni documento ancora `Proposta` ha una
  riga «Ordine», e quella riga rimanda qui** — letta intera, con le sue righe di continuazione —, così che una
  frase d'ordine rimasta in un documento dica sempre dove l'ordine vive davvero.

**Che cosa il test non tiene.** L'ordine: è una decisione di Tommaso, e nessuna riga del repository la contiene.
E una voce già fatta tolta da una tappa: il mondo chiuso parte dalle `Proposta`, perché le milestone fatte prima
del 2026-11-13 non stanno in nessuna tappa; che una voce fatta resti al suo posto lo tiene chi rilegge.
