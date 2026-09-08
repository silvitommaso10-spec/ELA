# 0034. La voce di §9: il primo dato che esce per qualcosa che non è un modello, un consenso che non si eredita, e un audio che non ha un nome

- **Stato:** Accettata. SPEC di M11.3 approvata dall'utente, undici decisioni (A–K), tutte prese
  **dopo** una ricognizione fatta con la chiave vera e **prima** dello scope. Le tre che cambiano
  la forma di ciò che ELA può fare sono §3 (due capability, perché un consenso non si eredita),
  §7 (un audio che non ha un nome, e perché **non** è la forma di ADR 0029 §1) e §10 (la ricevuta
  di ciò che il fornitore conserva).
- **Contesto:** M11.3, la prima milestone in cui un dato dell'utente esce da questa macchina per
  una capability che non è `model.complete`.
- **Riferimenti spec:** §8, §9, §25, §26, §29, §30, §33, §44, **§57**, §59, §63
- **Estende:** ADR 0002 (tre regole nuove, la 41, la 42 e la 43), ADR 0010 (una capability
  aggiunta, la settima), ADR 0013 (un tool), ADR 0014 (un verifier, la stessa classe su due
  capability), ADR 0020 (§2 lo stato dichiarato, §3 la chiave, §7 il vocabolario chiuso nel port,
  §8 il retry, §10 ciò che non esce — tutti riusati, uno **corretto**), ADR 0023 (tre rotte e un
  campo di `/diagnostics`), ADR 0024 (un gruppo di comandi), ADR 0028 §2 (il criterio del
  sottoprocesso), ADR 0029 §1 (lo store delle catture — qui **non** si applica, §7), ADR 0030 §8
  (una lettura che significa due cose va spezzata, applicata a un **errore**), ADR 0030 §15 (la
  difesa si scrive prima, terza volta), ADR 0030 §17 (le quattro domande di §57, nella forma),
  ADR 0033 (ne chiude **due** vincoli su nove, e ne lascia sette dove sono).

## Contesto

ADR 0033 consegnò *che ELA parla* e dichiarò, nelle Conseguenze, ciò che non consegnava:

> **La voce di §9 non è consegnata.** Alice è l'unica femminile italiana che `say` offre ed è
> sintesi concatenativa datata: M11.1 consegna *che ELA parla*, non *che ELA suoni come §9 la
> descrive*. Riaperto da M11.3.

E lasciò la condizione di riapertura scritta dentro la regola 35: M11.3 apre la metà della voce,
**e solo quella**, con le quattro risposte di §57 nella forma di ADR 0030 §17.

L'utente ha sentito Alice e l'ha respinta. Ciò che chiede — *una voce femminile, elegante e
moderna* — è §9 alla lettera, e non esiste su questa macchina.

## 1. La ricognizione, e le tre cose che ha corretto

Misurata il **2026-09-08** con la chiave dell'utente, piano **creator**, voce di misura
*Daniela Narrator IT*, formato `mp3_44100_128`, servita da `europe-west4`.

### 1.1 Il costo della sintesi **non** è piatto

| Caratteri | `eleven_multilingual_v2` | `eleven_flash_v2_5` |
|---|---|---|
| 40 | 1,09 s | 0,32 s |
| 170 | 1,68 s | 0,58 s |
| **600 (il tetto)** | **5,62 s** | **1,24 s** |

> ADR 0033 misurò che *«il costo della sintesi è piatto rispetto alla lunghezza»* — 0,54 s, 1,65 s
> e 9,30 s di parlato preparati tutti in ~380 ms — e chiamò quella piattezza *«il fatto che rende
> `say` utilizzabile davvero e non solo disponibile»*. **Col cloud la piattezza non c'è.** Al
> tetto l'attesa è 5,6 secondi con il modello migliore, e non è la consegna: è silenzio prima
> della consegna.

Il primo byte in streaming è invece quasi piatto — 206–210 ms con flash a qualunque lunghezza —
e questo dice dove starà il guadagno il giorno in cui esisterà un riproduttore che comincia prima
della fine (§Vincoli).

### 1.2 La ritenzione, verificata invece che citata

| | |
|---|---|
| Zero Retention Mode | documentato, e **riservato agli enterprise** |
| Piano dell'utente | **creator** |
| `enable_logging=false` su questo piano | **HTTP 200, e torna comunque un `history-item-id`** |
| `GET /v1/history` | **restituisce il testo delle richieste, testualmente** |

> **Non l'ho letto in una policy: ho riletto le mie stesse parole.** Le frasi della ricognizione
> sono nella history dell'account, in chiaro, con il loro id. Il testo che ELA dice **è
> conservato e rileggibile nella dashboard dell'utente**, e chiedere di non conservarlo non serve:
> il flag esiste, risponde 200, e non cambia niente.

### 1.3 Il codice HTTP mente

| Situazione | HTTP | Corpo |
|---|---|---|
| chiave invalida | **400** | `type: authentication_error`, `code: invalid_api_key` |
| voce inesistente (sintesi) | 404 | `status: voice_not_found` |
| voce inesistente (metadati) | **400** | `status: voice_not_found` — *lo stesso fatto, due codici* |
| modello inesistente | 400 | `status: model_not_found` |
| 10 500 caratteri su un modello documentato a 10 000 | **200** | *audio prodotto e addebitato* |

ADR 0020 §7 poté mappare le **classi di eccezione** dell'SDK Anthropic. Qui non c'è SDK, e una
credenziale rifiutata arriva come 400, che ovunque significa «richiesta sbagliata». Quindi il
vocabolario chiuso si mappa su `detail.type` e `detail.status` **del corpo**, con il codice HTTP
come ripiego — non il contrario. È l'unica riga di ADR 0020 che questo ADR corregge invece di
riusare.

E l'ultima riga: **il limite documentato non è un rifiuto.** Il tetto vero è il nostro.

### 1.4 Gli altri numeri

| Misura | Valore |
|---|---|
| Audio a 600 caratteri | 594 799 B / **37,15 s** (multilingual), 621 549 B / **38,82 s** (flash) |
| Caratteri al secondo parlato | 16,2 e 15,5 — contro i **19,1** di `say`: la voce del cloud parla più piano |
| `byte ÷ 16 000` contro `afinfo` | 37,17 vs 37,146 e 38,85 vs 38,818 — **errore < 0,1%** |
| Costo dichiarato dal provider | header `character-cost`: 52 contro 26 sullo stesso testo |
| Concorrenza del piano | `maximum-concurrent-requests: 10` |
| Riproduzione da pipe / FIFO | **impossibile**: `AudioFileOpen failed (-40)` |
| Riproduzione da fd scollegato via `/dev/fd/N` | **2,11 s**, contro i 2,13 di un file con un nome |
| `kill` a metà riproduzione | rc −9, **il suono si ferma** |
| Costo della ricognizione | **8419 crediti su 131 000** (6,4% del mese) |

## 2. Le quattro domande di §57

| Domanda | Risposta |
|---|---|
| **Quale provider** | **ElevenLabs**, `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`, modello fisso dichiarato in configurazione, abbonamento **creator** dell'utente, servito da `europe-west4` il 2026-09-08 **senza impegno di regione**. Non «il router»: c'è un provider, nominato; se non c'è quello non c'è niente. **Ritenzione: nessuna protezione** (§1.2). |
| **Quale tipo di dati** | **Il testo che ELA dice**, al massimo 600 caratteri, più `voice_id`, `model_id`, `output_format`. Nient'altro: né `purpose`, né `task_id`, né il nome dell'utente, né un byte di audio dell'utente. Ma va detto per ciò che è: quel testo è composto dal contesto di §44 e dal `goal`, quindi è **contenuto dell'utente nella sua forma più concentrata** — non indiscriminato come un PNG (ADR 0030 §17), ma più denso: una frase *sulla sua situazione*. |
| **Perché viene inviato** | Perché §9 chiede una presenza femminile e professionale e `say` ha **una** voce femminile italiana, datata. La soglia si alza come ADR 0030 §17 alzò la propria dopo l'OCR locale: **dopo M11.1, «ELA deve parlare» non è più una ragione valida.** L'unica ragione ammessa è la **qualità della voce**. |
| **Quale policy lo consente** | Un'`Authorization` **sua**, su `voice.speak_online`. Un grant su `voice.speak` non la copre e non può coprirla: sono due `capability_id`, e il Guardian consuma i grant per `capability_id`. È la risposta di ADR 0029 §13 alla domanda analoga — **serve un consenso suo** — applicata al confine fra la stanza e la rete. |

## 3. Due capability, non una — e il nome dice cosa succede, non dove

`voice.speak` (locale, invariata) e **`voice.speak_online`**. Il nome è dell'utente, con la sua
ragione, che è il criterio e non la preferenza:

> «cloud» dice dove sta il server, «online» dice cosa succede: **questa frase esce da questa
> macchina.** È quella la cosa che l'utente deve leggere nell'approvazione.

E la legge letteralmente. Il prompt di un `Approval` è
`{capability_id} … for step {id} ({goal}) (purpose: …)` (ADR 0013 §5): la **descrizione** della
capability non compare. Il nome della capability *è* la superficie del consenso — l'unico posto in
cui la parola giusta arriva a chi decide.

Perché due e non una con un provider intercambiabile: la protezione di questa capability non è
uno scope — non esiste a forma di percorso, ADR 0033 §3 — ma **il grant**. Con una capability
sola, un grant «puoi parlare» diventerebbe «puoi mandare le mie parole a ElevenLabs» il giorno in
cui qualcuno cambia una variabile d'ambiente: il consenso resterebbe scritto, ma su un atto
diverso da quello eseguito.

## 4. Entrambe MEDIUM, e il livello non è ciò che le separa

In `RISK_POLICY` (ADR 0011) **HIGH → `Rule.DENY`**: una capability HIGH non è più sorvegliata, è
**ineseguibile**. Alzare il livello non renderebbe la voce online più prudente, la spegnerebbe, e
riaccenderla vorrebbe cambiare la policy di §29 — un ADR suo. E MEDIUM è già la definizione
letterale che §29 dà: *«perché il contenuto dell'utente può essere inviato a un provider AI
esterno»*.

> Due capability, stesso livello, **due grant**. Ciò che le separa non è un'etichetta di pericolo:
> è che nessuno può dire di sì a una dicendo di sì all'altra.

## 5. Chi sceglie fra le due, e cosa succede quando la rete non c'è

**Nessun ripiego automatico**, in nessuna delle due direzioni:

- **online → locale** sarebbe eseguire un atto che il Guardian non ha deciso, e farlo verificare
  da un verifier registrato per un'altra capability: l'ambiguità di ADR 0030 §8, su un risultato;
- **locale → online** sarebbe far uscire un dato **senza decisione**, cioè l'opposto di §33.

Il precedente che sembrerebbe autorizzarlo — il `ModelRouter` che prova i provider in ordine
(ADR 0022) — dice la stessa cosa al contrario: là i provider sono **equivalenti rispetto al
consenso**, quindi sceglierne uno non cambia ciò che l'utente ha approvato. Qui la differenza *è*
il consenso.

Sceglie **lo step**, decide il Guardian, e il fallimento ha un nome. `SPEECH_ERROR_CODES` sta in
`ela.ports` e non nell'adapter, per la ragione di ADR 0020 §7: chi riceve un fallimento distingue
«rete assente» da «chiave rifiutata» senza sapere chi è il fornitore, e una seconda
implementazione riporta gli stessi codici o non è intercambiabile.

**Due assenze, due codici** — e questa è la correzione dell'utente alla spec, con il suo
argomento: *«non hai messo la chiave» e «la chiave non è valida» sono due fatti diversi con due
azioni diverse*. La spec ne aveva uno solo, `speech.unconfigured`, con due messaggi. Separarli è
ADR 0030 §8 applicato a un **errore** invece che a una lettura, e il vocabolario del port cresce
di un codice, che è ciò che deve fare quando serve un nome che non c'è.

## 6. Un port solo — i port restano ventidue

`SpeechPort` è *testo → suono*, e regge entrambe: l'implementazione online sintetizza **e**
riproduce dietro la stessa interfaccia. Il port che M11.1 ha disegnato era giusto, e questa
milestone non lo tocca.

La composizione **non introduce un port di sintesi**: la sintesi arriva come un `Callable`
tipizzato, come `Spawn` in `darwin.py`, che è un alias e non un port. Il Core dipende da
`SpeechPort` e da nient'altro.

E la promessa più difficile di ADR 0033 §4 — *una chiamata cancellata ferma il suono* — vale sul
percorso nuovo, misurata: `kill` a metà riproduzione, rc −9, silenzio.

## 7. I byte non hanno un nome — e non è la forma di ADR 0029 §1

`afplay` vuole un file *seekable*: pipe e FIFO falliscono entrambe (`AudioFileOpen -40`), e non
esiste un altro riproduttore su questa macchina. Quindi un file c'è. Ciò che lo rende accettabile
è che **non ha un nome**: `mkstemp` → `unlink` immediato → scrittura sul descrittore →
`/dev/fd/N` al figlio → `close` nel `finally`. Un inode anonimo, che nessuno può aprire per
percorso e che il kernel libera quando il descrittore si chiude — **anche se ELA muore nel mezzo**.

**Perché non lo store delle catture**, che è la domanda che l'utente ha posto:

> La cattura ha bisogno di un artefatto perché **il verifier lo rilegge** — §20 vieta che un tool
> sia verificato sulla propria parola. Il verifier della voce ha già dichiarato in ADR 0033 §5
> che quella strada gli è preclusa: verifica sull'orologio e su un digest. Quindi **l'audio non ha
> un secondo lettore**: esiste solo perché `afplay` non sa leggere una pipe. Uno store con TTL,
> tetto e purga sarebbe una politica di ritenzione per qualcosa che nessuno rileggerà mai — il
> criterio di ADR 0029 §1 applicato al contrario.

**La finestra di una syscall, dichiarata invece che nascosta.** Fra `mkstemp` e `unlink` un nome
esiste. Il file nasce quindi col prefisso `ela-speech-` in una directory di ELA a `0700` — mai il
workspace, che è sincronizzabile (ADR 0029 §1) — e **l'avvio spazza quel prefisso**: la riga di
ADR 0029 §1 sulla purga, usata per la sola cosa che qui può sopravvivere, cioè un crash a metà
syscall. Non è uno store: è un pavimento spazzato.

**E il file anonimo si fa in `darwin.py`, non nei moduli della voce.** È dove la porta verso il
sistema operativo già sta (regola 32), è un modulo che non tiene parole di ELA, ed è ciò che
permette alla regola 41 di non avere **nessuna eccezione**: i moduli che tengono le parole non
toccano un filesystem, punto. Una regola con un'eccezione è una regola che qualcuno allarga.

## 8. Le tre regole, scritte nel commit precedente al codice

`Regole aggiunte:`

| Regola | Cosa dice | Su |
|---|---|---|
| 41 `the-voice-leaves-no-named-file` | nessuna scrittura di file, nessun file temporaneo | `VOICE_MODULES` + l'adapter |
| 42 `the-voice-goes-only-where-it-is-declared` | un solo host, scritto come costante; nessun campo `base_url`; nessuna lettura dell'ambiente; nessun router né registry | l'adapter |
| 43 `the-audition-speaks-only-the-repositorys-words` | nessuna funzione dell'audizione accetta testo | il modulo dell'audizione |

`Regole estese:`

| Regola | Come cambia |
|---|---|
| 35 `capture-stays-on-the-machine` | `VOICE_MODULES` accoglie il tool online e il modulo dell'audizione |

È ADR 0030 §15 applicato la **terza volta**, e questa volta ha avuto un prezzo che vale la pena
scrivere: due delle tre regole, come erano state disegnate nella spec, avevano un'**esenzione** —
e un'esenzione senza nessuno dietro è una porta aperta (ADR 0026 §7, la tabella di ADR 0027 se ne
accorge). Le regole sono state ridisegnate per non averne: il file anonimo è andato in
`darwin.py` (§7), e il divieto dell'adapter è una costante positiva invece di una sottrazione
dentro la funzione. L'unica esenzione rimasta è l'endpoint stesso, e dietro c'è
`providers/elevenlabs/settings.py`, che è arrivato **nello stesso commit delle regole**: la
costante e la regola che la protegge insieme, e la rete un commit dopo.

## 9. L'audizione: un comando, non un task

L'utente vuole sentire alcune voci prima di scegliere, e una capability per prova sarebbe
un'approvazione per prova. Quindi due gradini:

1. **`ela voice preview`** — le voci hanno un campione **già generato**: ELA lo scarica e lo
   riproduce. Zero caratteri inviati, zero crediti. **Best effort, e misurato perché**: i metadati
   di una voce di libreria rispondono `400 voice_not_found` per alcune voci e `200` per altre —
   *la stessa voce ha risposto 400 e poi 200 nel giro di un minuto*. Un campione che manca è un
   esito con un nome, non un errore.
2. **`ela voice audition`** — la rosa dice **le due frasi di §9**: *«No, questa non è una buona
   idea.»* e *«Stai cercando di risolvere il problema sbagliato.»* Perché la domanda non è come
   suona una voce: è **come suona ELA quando ti contraddice.** Almeno una voce le dice su
   **entrambi i modelli**, perché la scelta del modello è dell'utente e non un default nostro:
   5,6 secondi di attesa sono tanti, ma se la differenza di qualità si sente, è una scelta sua.

Ciò che esce durante un'audizione è **un letterale del repository**, e la forma che lo rende vero
non è un commento ma un'assenza: **nessuna funzione dell'audizione accetta testo** (regola 43).

**E l'audizione non sta nella CLI, per la regola 27**: solo `ela.composition` può nominare
`ela.providers` e `ela.infrastructure`, quindi il lavoro sta dietro l'API locale e la CLI resta
un client (regola 28). È una deviazione dalla spec, imposta dall'architettura e non scelta, ed è
migliore: la rotta non ha **nessun campo per il testo**, quindi la proprietà «solo le parole del
repository» è nello schema prima ancora che nella regola.

## 10. La ricevuta, e la cancellazione che resta non percorsa

Il risultato porta `history_item_id` e `credits`, e **mai una parola del testo**.

> Un costo accettato che nessuno può poi ritrovare è **un costo raccontato.** `history-item-id` è
> l'indirizzo esatto della copia che ElevenLabs ha tenuto: con quello, «il testo è conservato»
> smette di essere una frase in un ADR e diventa una riga che si va a guardare. Non è il testo,
> non è contenuto: è la ricevuta.

E `credits` chiude una cosa che ADR 0020 §6 non poté chiudere: là il costo era una **stima** su
una tabella datata, con un test che scade dopo 180 giorni perché nessun test si accorge che un
listino è cambiato. Qui il provider **dichiara** il costo a ogni richiesta (`character-cost`).
Quindi si riportano **crediti**, che il provider afferma, e mai una valuta, che dipenderebbe da un
piano che ELA dovrebbe inseguire. Nessuna tabella, niente da far scadere.

**La cancellazione post-hoc resta non percorsa, e ora per scelta e non per limite** — la
differenza conta ed è la ragione per cui è scritta. La ricognizione ha stabilito che sarebbe
facile: l'id torna in un header e `DELETE /v1/history/{id}` esiste. Non si fa perché **cancellare
dopo non è non aver mandato**: il testo è stato sul loro disco, il momento in cui c'era è passato,
e una cancellazione che riesce quasi sempre produrrebbe la sensazione di una garanzia che nessuno
ha dato. La ricevuta è onesta; la cancellazione sarebbe consolatoria.

## 11. La ritenzione sta scritta dove si guarda quale voce ELA usa

Aggiunta dallo scope dall'utente, con la sua ragione: *l'ha scelta consapevolmente e la scelta
deve restare visibile.*

`/diagnostics` porta `text_retained_by_provider` accanto alla voce online, e `ela voice` **scrive
la frase** dove si guarda quale voce ELA sta usando. Il booleano sta nell'API, la frase la compone
la CLI, e un test lega le due cose: se il booleano è vero e la frase manca, il test fallisce.

**Non un avviso a ogni frase**: un avviso ripetuto si impara a ignorare, e questo non è un evento
— è un fatto della configurazione, e sta dove si guarda la configurazione.

## Alternative considerate

- **Una capability sola con un provider intercambiabile.** Scartata (§3): renderebbe un grant già
  dato una risposta a una domanda diversa.
- **`voice.speak_online` HIGH.** Scartata (§4): in `RISK_POLICY` HIGH è `DENY`. Il livello non è
  ciò che protegge qui; il grant sì.
- **Un ripiego automatico sul locale quando la rete manca.** Scartata (§5): eseguirebbe un atto
  che il Guardian non ha deciso, e lo farebbe certificare dal verifier sbagliato.
- **Due capability decomposte per atto** — `voice.synthesize` (esce) e `voice.speak` (suona).
  Scartata: costringerebbe i byte dell'audio a passare fra due step, cioè dentro un
  `ExecutionResult` persistito o uno store — esattamente ciò che §7 evita.
- **Lo store di ADR 0029 §1 per l'audio.** Scartata (§7): una ritenzione per qualcosa che nessuno
  rileggerà.
- **Uno streaming che comincia prima della fine.** Scartata qui, con la sua misura: 210 ms contro
  1236 di primo byte. `afplay` vuole un file completo, e un audio che comincia mentre arriva è un
  riproduttore nostro.
- **`enable_logging=false`.** Scartata perché **misurata inutile** (§1.2): scriverla nel codice
  sarebbe una finta protezione.
- **Cancellare la history dopo ogni frase.** Scartata per scelta (§10).
- **Una tabella dei prezzi come ADR 0020 §6.** Scartata: il provider dichiara il costo, e una
  tabella che nessun test può verificare contro il mondo è un promemoria che invecchia (§10).
- **`voice_settings` — stabilità, stile, velocità.** Scartate: ADR 0033 §6 ha già rifiutato una
  manopola che renda la durata di una frase funzione di un'impostazione.
- **Rinominare la regola 35 e il package `perception`.** Scartata **di proposito**: M11.2 ha già
  fissato la forma di quel pagamento — *il rinomino è il primo commit di M11.2, da solo, prima di
  qualunque codice dell'ascolto* — e un commit che rinomina *e* aggiunge è quello in cui la
  revisione guarda l'aggiunta. M11.3 aggiunge un terzo elenco a quella regola e **peggiora il
  debito senza pagarlo**, che è la cosa onesta da fare quando la scadenza è di qualcun altro.

## Conseguenze

- ELA può dire una frase con la voce che §9 descrive, dietro una decisione del Guardian che è
  **sua** e non ereditata da quella della voce locale.
- **Un dato dell'utente esce da questa macchina per la seconda volta**, e la prima fuori da
  `model.complete`. Ciò che il fornitore ne fa è scritto in §1.2 e visibile in `/diagnostics`.
- Le regole di architettura passano da quaranta a **quarantatré**; i contratti di import-linter
  restano **quattordici** (il decimo si allarga al package nuovo).
- I port restano **ventidue**: `SpeechPort` regge due implementazioni.
- Le capability di produzione passano da sei a **sette**; quelle di v0.1 restano **tre**.
- `spawn` guadagna un secondo modo di essere chiamato — con dei byte da consegnare al figlio —
  e resta l'unica porta verso il sistema operativo.

### Vincoli dichiarati, da riaprire quando serviranno

- **Il testo è conservato dal fornitore**, non c'è modo di impedirlo su questo piano, e la
  ricevuta è ciò che lo rende verificabile invece che dichiarato (§10).
- **Nessuno streaming dell'audio**: la prima sillaba arriva quando l'audio è completo. La misura di quanto
  varrebbe è in §1.1.
- **Nessun ripiego automatico** fra le due voci (§5): il ripiego è un secondo step, e chi scrive
  il piano lo decide.
- **Lo `stop` a metà frase** resta del barge-in (M11.4), come in ADR 0033.
- **La memoria della conversazione** resta di §21, **§8** resta non implementato, e **il grant
  riusabile di §59** resta una strada registrata: tutti e tre dove ADR 0033 li ha lasciati.
- **Il debito di nome cresce a tre teste** e resta di M11.2 (§Alternative).
- **Il preview è best effort**: i metadati di una voce di libreria non sono affidabili, misurato.
