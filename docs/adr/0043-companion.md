# 0043. Il companion iPhone: un ruolo imposto nel registro, un cookie come portatore, pagine servite dal Core, e un campanello che suona un metodo

- **Stato:** Proposta il **2026-09-20**, con la spec di M12.5 approvata dall'utente dopo le misure
  P0–P4 sull'iPhone. Si accetta quando la prova a mano di M12.5 passa — il percorso di ADR 0040 e di
  ADR 0042 —, e cresce in «Proposta» a ogni commit della milestone: qui c'è ciò che è deciso e
  scritto, e ogni sezione entra col codice che difende.
- **Data:** 2026-09-20
- **Riferimenti spec:** §6, §16, §57, §58, §65
- **Milestone:** M12.5, l'ultima della Fase 12 (`docs/STATO.md`, voce 4.1).
- **Continua:** ADR 0037 (l'identità di un nodo: il codice, il segreto, le rotte, i rifiuti);
  ADR 0016 §3 (la disponibilità è derivata, non letta da una colonna); ADR 0023 §7 e §10 (lo stesso
  401 per ogni fallimento; la tabella degli errori); ADR 0038 §18 (che cosa un contratto non può
  provare).

## Contesto

La spec di M12.5 (`docs/milestones/M12.5.md`) decide che l'iPhone **vede e risponde**, e non comanda:
guarda le domande che aspettano, dice sì o no, e può fermare un task. Non prende lavoro, non esegue
tool, non manda heartbeat. Le misure sull'iPhone del 2026-09-19 e del 2026-09-20 — in appendice alla
spec, con gli orari e la macchina — hanno chiuso ciò che da questo Mac non si poteva sapere: quale
browser apre uno Shortcut, quali cookie arrivano dopo un riavvio, quanto ci mette una notifica.

ADR 0037 §4 aveva già preparato la forma: «questo nodo può rispondere alle approvazioni» è un
permesso che l'utente dà a un dispositivo preciso, della specie di `privacy`. Questo ADR la usa.

## 1. Un ruolo imposto, e il portatore fa parte del ruolo

`DeviceRole` ha due membri, ciascuno con un produttore in produzione:

| Ruolo | Chi | Portatore della credenziale | Rotte |
|---|---|---|---|
| `WORKER` | ogni nodo, e `local` — il default della migrazione | l'header `Authorization` | `NODE_ROUTES` |
| `COMPANION` | il browser predefinito dell'iPhone | il cookie, e solo il cookie | le pagine del companion |

Il ruolo sta nella **metà imposta** di ADR 0037 §10, accanto a `privacy`: lo sceglie l'utente quando
conia il codice (`ela node enroll --role companion`), il codice lo porta, e l'identità non lo scrive
mai — `PUT /nodes/me` scrive la metà dichiarata, e il ruolo non ci sta. La regola 44 lo impara per
nome, col suo caso negativo.

**Un iPhone non è mai idoneo al lavoro.** La disponibilità resta il fatto dell'heartbeat (ADR 0016
§3), e un companion non ne manda: `is_available` risponde `UNAVAILABLE` per costruzione, qualunque
sia l'ultimo contatto. La condizione sta nella derivazione e non solo in `available()`, perché uno
step senza capability ha l'insieme dei tool vuoto — `MISSING_TOOL` non scatta — e un companion
«disponibile» per un minuto dopo ogni pagina aperta sarebbe un candidato su cui il runner aprirebbe
task e step a suo nome prima che l'executor rifiuti. Due fatti, due nomi: l'**ultimo contatto** dice
quando quell'identità ha parlato con ELA, la **disponibilità** dice se manda segni di vita.

**Perché un ruolo solo.** La stesura ne proponeva un secondo, `GLANCE`, per uno Shortcut che leggesse
un riassunto senza contenuto. L'utente l'ha tolto il 2026-09-19: il suo valore è un conteggio che il
campanello già dà, il suo prezzo è una seconda identità per telefono, un segreto in un file la cui
custodia nei backup non è stabilita, un secondo portatore nel middleware e un secondo driver nel
contratto.

## 2. Lo schema: una colonna per tabella, e il default è il mondo com'era

La migrazione `0011` aggiunge `role` a `devices` e a `enrollments`, non nulla, con
`server_default='WORKER'`: ogni nodo arruolato prima che i ruoli esistessero resta ciò che era, e
così `local`. Il default è il significato del mondo di ieri, non il più sicuro dei due — qui non ce
n'è uno più sicuro, perché i due ruoli sono rifiutati sul terreno dell'altro (§3), e un companion
nato per difetto sarebbe un companion per cui nessuno ha coniato un codice.

Il `server_default` resta sulla colonna, per la ragione di `0010`: una riga inserita da qualcosa che
non è il mapper di ELA avrebbe altrimenti un ruolo assente, e ogni lettore del registro legge questa
colonna.

Colonne aggiunte:

| Tabella | Colonne |
|---|---|
| `devices` | `role` |
| `enrollments` | `role` |

## 3. Un codice vale su una rotta sola, e un codice rifiutato non si consuma

Ogni rotta di arruolamento accetta soltanto i codici del suo portatore:

| Codice | Rotta | Esito |
|---|---|---|
| `WORKER` | `POST /nodes/enroll` | `201`, un nodo, come oggi |
| `COMPANION` | `POST /nodes/enroll` | `422` `invalid`: la credenziale di un companion non torna mai in un corpo, nasce in un `Set-Cookie` |
| `COMPANION` | `POST /companion/enroll` | `303` e il `Set-Cookie` |
| `WORKER` | `POST /companion/enroll` | `422` sulla pagina, con il comando che conia il codice giusto |

**Il controllo del ruolo è una condizione della `UPDATE` che spende il codice**, non un controllo
prima di essa: la quarta applicazione della forma di ADR 0012 §5, dopo `consume`, `respond` e
l'annuncio condizionale. Un codice presentato sulla rotta dell'altro ruolo non tocca nessuna riga,
quindi **non si consuma**, e chi l'ha incollato nel posto sbagliato non ha perso niente. Il motivo
lo nomina un errore suo, `EnrollmentRoleError`, che non porta né il codice né il suo hash.

**È l'unico rifiuto di un codice che non è lo stesso 401 di una credenziale sconosciuta** (ADR 0023
§7, ADR 0037 §13). Chi presenta un codice che esiste, sulla rotta dell'altro ruolo, ce l'ha già: non
c'è niente da nascondergli, e ciò che gli serve è l'unica cosa su cui può agire. Sconosciuto, scaduto
e già speso tengono le risposte di ADR 0037 §13.

Errori aggiunti, nella forma della tabella di ADR 0023 §10:

| Caso | Eccezione | Stato |
|---|---|---|
| un codice coniato per l'altro ruolo, sulla rotta di questo | `EnrollmentRoleError` | `422` |

## 4. Le pagine leggono le rotte

`ela.api` serve le pagine da sé (dec. D1): lo stesso processo, lo stesso middleware, le stesse
funzioni delle rotte JSON, e il browser è il client. «Client dell'API come la CLI» regge solo se una
pagina è **un'altra rappresentazione delle stesse rotte**, e una regola lo rende vero invece che
promesso — la **regola 55**, *le pagine leggono le rotte*: `api/companion.py` chiama le funzioni
delle rotte e non nomina mai un port, uno store, il catalogo o l'executor **attraverso** `Ela`. È la
forma della regola 28 della CLI, all'altro capo dello stesso confine, e **senza porte**: ciò che una
pagina mostra deve già stare in una rotta, e se non ci sta è la rotta che cresce (dec. F).

## 5. Le pagine: chi le compone, e che cosa risponde ELA sotto il prefisso

Sei rotte, e nessuna porta un id nel percorso — nella query o nel corpo, per la ragione di ADR 0038
§11: insegnare un template al middleware sarebbe «una difesa che sembra attiva».

| Metodo | Percorso | Che cosa |
|---|---|---|
| `GET` | `/companion/` | la presenza, le domande che aspettano, i task vivi; `?task=<id>` mostra l'esito di ciò a cui si è appena risposto |
| `GET` | `/companion/approval` | una domanda, con le parti che dec. F elenca; `?id=<id>` |
| `POST` | `/companion/answer` | il sì o il no, e dopo un sì il `run` (§6) |
| `GET` | `/companion/cancel` | la conferma di fermare un task: che cosa si ferma, e che è irreversibile; `?id=<id>` |
| `POST` | `/companion/cancel` | il modulo della conferma: il task si ferma, firmato dall'iPhone (§7) |
| `POST` | `/companion/enroll` | il modulo con il codice: `303` e il `Set-Cookie`, o la stessa pagina con la frase che dice che fare |
| `GET` | `/companion/tokens.css` | i token del design system, da `apps/` |
| `GET` | `/companion/components.css` | i componenti del design system, da `apps/` |

**Un compositore solo.** Ogni risposta HTML di `ela.api` — le pagine, il `401` che è il modulo di
arruolamento, il `404` «non esiste», gli errori sotto il prefisso — si compone in `api/pages.py`, ed
è lì che nasce la `Content-Security-Policy`: `default-src 'none'; style-src 'self'; form-action
'self'; frame-ancestors 'none'; base-uri 'none'`. La **regola 57** lo tiene: nessun altro modulo di
`ela.api` costruisce una risposta HTML. «Niente JavaScript» è difeso due volte e le due difese non
sono la stessa — i modelli non contengono script (un test in `tests/ios/`), e la politica lo vieta
comunque, così un valore che un giorno sfuggisse all'escape verrebbe rifiutato dal browser invece
che eseguito.

**L'escape è per costruzione.** Un valore che entra in una pagina passa da `html.escape`; non esiste
un argomento che lo disattivi. Ciò che entra crudo è di tipo `Markup`, e `Markup` lo produce solo il
compositore: un modello di `apps/ios/` o un frammento del design system, cioè file di questo
repository. Solo la libreria standard: niente Jinja2, `uv.lock` non si muove.

**Gli errori sotto il prefisso sono pagine.** La stessa tabella di ADR 0023 §10, lo stesso stato e la
stessa frase, composti dal compositore: in un browser il JSON crudo è un vicolo cieco. Un posto solo,
così nessuna rotta deve ricordarsene.

**Il tema è quello scuro, sempre**, e la pagina di arruolamento è **senza stile**: i fogli stanno
dietro il middleware come tutto il resto, e chi non è ancora nessuno non li carica. Servirli a
chiunque sarebbe la prima rotta anonima di ELA.

## 6. Il «sì» risponde e fa ripartire il task

Dal Mac l'utente fa due cose, `ela task approve` e `ela task run`. La pagina fa le stesse due, ognuna
dalla sua funzione, nella stessa richiesta (dec. H1): un «sì» che resta lì fino al ritorno a casa non
rende ELA usabile lontano dal Mac. Un «no» non esegue niente — il task è `DENIED`.

Non apre una rotta nuova a chi ruba il telefono: esegue solo ciò che l'utente ha già creato e a cui
ha appena detto sì, e ogni step `MEDIUM` successivo chiede di nuovo, perché un grant è un uso solo.

**Il browser può smettere di aspettare** prima che un `run` lungo finisca — la pagina si chiude, il
telefono si blocca, la tailnet cade. Il `run` continua sul Mac, come continua quando si interrompe
`ela task run` al terminale, e la pagina successiva mostra lo stato vero del task letto dalle rotte.
Dichiarato.

**Il tetto decide che cosa si vede** (dec. F2-a): il confronto del filtro F2 dell'orchestratore, con
la `privacy` che l'`Identity` porta e il `max_privacy` della domanda. Per un task che il tetto non
ammette la pagina non porta lo scopo, i `targets`, la frase né gli argomenti dichiarati: mostra
l'id, lo stato, la capability, il rischio e le ore, e dice che il contenuto resta sul Mac. Il «sì» da
lì è rifiutato con `ApprovalOutOfReachError`, che è `409` `not_answerable` come le altre due
impossibilità — già risposta, troppo tardi — perché non si approva ciò che non si vede (§30).

## 7. Fermare un task da lontano

La rotta c'è già (`POST /tasks/{task_id}/cancel`), firmata dall'identità che il middleware ha
risolto. Per il companion è un'aggiunta a `COMPANION_ROUTES` e **una pagina di conferma**, perché
senza JavaScript una conferma è una pagina: `GET /companion/cancel?id=…` dice che cosa si ferma e
che è irreversibile, e il suo modulo manda il `POST`.

**Toglie soltanto**, ed è la ragione per cui è la prima rotta che ha senso dare a un telefono: un
task `CANCELLED` non fa più niente, e fermarsi è il verso di §33. Il prezzo, detto: è
irreversibile, e chi ruba il telefono può fermare i task dell'utente — non leggerne di più, non
farne di nuovi. Vale anche per un task `LOCAL_ONLY` di cui la pagina non mostra il contenuto
(§6): fermare non chiede di vedere.

**L'attore è `USER` con l'id dell'iPhone**, non `DEVICE`. È la distinzione di ADR 0037 §15 —
«chi approva, conia un codice o revoca un nodo è una persona, non un dispositivo» —: un iPhone è
dove sta la persona, un nodo è una macchina che lavora. L'id resta quello che il middleware ha
risolto, così l'audit dice **da dove** è arrivato l'atto.

## 8. Il campanello: un metodo per voce, e un timeout misurato

**ntfy.sh, gratis, con un argomento casuale di 128 bit trattato come un segreto** (dec. E1). Costa
zero; E1+ o E3 restano possibili il giorno in cui l'utente vorrà pagare per togliere i campanelli
falsi. È anche l'unica delle quattro che fa letteralmente ciò che il punto fermo 5 chiede — **la
notifica apre la pagina**, con un tocco solo, misurato il 2026-09-20 — senza un account, e ciò a
cui rinuncia rispetto a Pushover, la cifratura, protegge un testo che per costruzione non porta
niente dell'utente.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `Bell` | §7, §8, §57 | async | `name`, `ready`, `approval_waiting` |

**Un metodo per voce, non un enum.** Il port ha un metodo per ogni evento che suona, e oggi uno
solo, `approval_waiting(risk)`. Un enum con un membro invita ad aggiungere voci senza scrittore; un
metodo obbliga ogni evento futuro a entrare con il suo chiamante e la sua decisione (la review del
2026-09-19). **Nessun parametro è una stringa**: il rischio è del catalogo, quindi «niente
dell'utente nel testo» è vero per costruzione — `mypy --strict` rifiuta una frase dove il metodo
vuole un `RiskLevel` — e l'adattatore compone il testo da una tabella sua, con le chiavi di
`tokens.json`: titolo «ELA», corpo «WAITING APPROVAL · MEDIUM». La **regola 56** legge le voci **dal
port** e pretende un chiamante solo per ciascuna, e nessun parametro `str`: una voce nuova arriva
con il suo chiamante o non arriva.

**Chi suona, e quanto può trattenere il `run`.** L'executor, dentro `_ask`, **dopo** che la domanda
è salvata e il task aspetta: un campanello non annuncia mai una domanda che non c'è. È quindi sul
percorso del `run`, e il timeout dell'adattatore è ciò che limita l'attesa dell'utente: **5 s**,
costante e dichiarato, contro la misura di 0,43 s di P4 — una dozzina di volte il peggiore dei tre
tempi misurati. Un test con un fornitore finto lento prova che il `run` non viene trattenuto oltre.

**Un campanello che non suona non fa fallire niente**: la domanda aspetta comunque sulla pagina e
nella CLI, e l'esito si scrive. Una morte fra la domanda salvata e il campanello lascia una domanda
senza campanello: dichiarato, e costa poco — la pagina la mostra alla prossima occhiata.

**Nell'audit, sì.** `BELL_RUNG`, attore `SYSTEM`, con il rischio, il fornitore, l'id
dell'approvazione e se è stato consegnato; **mai** l'argomento di ntfy né l'URL. Nessun campo
«voce»: avrebbe un valore solo, e che cosa ha suonato lo dice già l'id della domanda.

**Non è una capability** (deciso il 2026-09-19): è l'infrastruttura con cui ELA **chiede** il
consenso, non un'azione verso lo scopo dell'utente. Non porta contenuto per costruzione; chiedere
il consenso per poter chiedere il consenso è circolare; la politica è la configurazione
dell'utente — senza argomento, nessun campanello; e la scelta *se* disturbare è §8, la Fase 15.

**L'URL del tocco è fisso**, e viene dall'indirizzo su cui questo processo **ascolta davvero** —
quello che `api/server.py` ha legato —, non dall'impostazione: se all'avvio la tailnet non c'era,
ELA ascolta sul solo loopback e un campanello aprirebbe un indirizzo muto. Senza quell'indirizzo il
campanello non è pronto, e `/diagnostics` lo dice. Nessun pulsante d'azione (punto fermo 5): il sì
si dà sulla pagina, dov'è la domanda. La priorità è una costante.

## 9. Che cosa chiude la Fase 12, e che cosa si sposta con una casa

Ogni rimando del repository alla Fase 12 e a M12.5 è stato censito prima della spec (M12.5, dec. G).
Quelli onorati qui stanno nelle sezioni sopra. Quelli che **non si applicano** a un companion sono
questi, con la ragione, perché un rimando senza risposta è un debito che nessuno ritrova: `If-Match`
ed `ETag` (ADR 0037 §9) — il companion non annuncia; `performance` e `power_source` (ADR 0037 §10) —
non riporta; la rilettura della revisione (M12.3 dec. L) e la specie «residente» della CLI (M12.3
dec. M) — non è un processo; ADR 0039 §7, «quando il Core non risponde» — il browser mostra la sua
pagina d'errore; ADR 0031, «ogni nodo nuovo moltiplica le scelte di piattaforma» — il companion non
ha codice di piattaforma, e la regola resta in piedi per chi ne avrà; i cinque minuti della decisione
(ADR 0011) — al companion non arriva nessuna decisione; la creazione idempotente di un task
dall'iPhone (ADR 0008) — creare task è fuori scope.

E questi **si spostano, con la casa nuova**, approvati dall'utente il 2026-09-19. La Fase 12 si
chiude e loro restano:

| Che cosa resta | Casa |
|---|---|
| `launchd` e l'eseguibile firmato di ELA (ADR 0029 §16, ADR 0039 §6) | una milestone sua, prima di M17.3 |
| I pesi di §17, «da ritarare in Fase 12 con dati reali»: misurati, non ritarati (ADR 0017) | la Fase 13, quando due nodi competeranno davvero |
| La deriva dell'orologio di un nodo contro i cinque minuti (M12.2) | la stessa |
| Spostare un lavoro già in corso da un nodo a un altro (§12 del design) | la stessa |
| L'iPhone che conosce il contesto di una conversazione avuta al Mac (§22) | la Fase 15, la memoria |
| I livelli di attenzione e la telefonata (§7, ADR 0042 §5) | la Fase 15 |
| Dove uno Shortcut tiene un segreto, e come riceve un codice (ADR 0037 §7) | la milestone che darà voce all'iPhone, con la sua misura |
| La negativa delle rotte diverse, `model.misrouted` (ADR 0040) | la milestone del tetto di spesa (§30): è la prima che avrà una chiave del modello |
| Lo stato finale di un task il cui nodo tace a metà lavoro (ADR 0040) | la stessa, insieme alla riga sopra: entrambe vogliono il PC come nodo |

## 10. Vincoli dichiarati

Ciò che M12.5 **non** fa, o fa a un prezzo, detto una volta e per intero. Ogni riga è una decisione
presa con gli occhi aperti, non una svista che qualcuno troverà:

- **Il companion non prende lavoro, e non recita la suite dei nodi**: si misura contro il suo
  contratto, con il solo cookie (dec. A).
- **Lo Shortcut di M12.5 non parla a ELA**: apre una pagina. Uno Shortcut con un segreto è della
  milestone che darà voce all'iPhone (dec. A, C.2).
- **L'ultimo contatto è la parola del registro, e un companion non è mai disponibile** (dec. B).
- **Il cookie porta la credenziale durevole**, senza rotazione come il segreto di un nodo, per 400
  giorni; `Secure` no, perché è `http` (dec. C.1).
- **Che cosa porti con sé un backup iCloud dell'iPhone non è stabilito** per i cookie del browser
  (dec. C.2).
- **Il prefisso `/companion/` si vede da chi bussa senza credenziali**, e una credenziale buona su un
  percorso che non esiste riceve un `404`: ADR 0023 §7 e ADR 0037 §4 rivisti (dec. C.3).
- **Il companion vive nel browser predefinito dell'iPhone**, non per forza in Safari: cambiare
  browser predefinito vuol dire **riarruolarsi**, perché i cookie di un browser non si vedono da un
  altro (dec. C.0, misurato in P2).
- **Con Chrome la cronologia e le schede possono sincronizzarsi sull'account Google**: per questo gli
  URL del companion portano solo id opachi (dec. C.0, dec. D).
- **L'app web della schermata Home copia i cookie quando la si aggiunge, e poi li tiene separati**:
  non vede né revoche né riarruolamenti fatti nel browser, e resta fuori scope (dec. C.0, misurato).
- **`SameSite=Lax` e non `Strict`**: `Strict` è stato trattenuto in due casi reali, e le pagine `GET`
  del companion non hanno effetti; i `POST` restano difesi da `Lax` e dal controllo dell'`Origin`
  (dec. C.1, misurato).
- **Un cookie si cancella solo quando è stato presentato e non vale**: senza cookie il 401 non porta
  nessun `Set-Cookie`, perché un browser può trattenere una credenziale buona (dec. C.3, misurato).
- **Con «Non disturbare» il campanello tace**, e la notifica resta nel Centro Notifiche: decidere
  quando passarci sopra è §7 e §34, la Fase 15 (dec. E, misurato).
- **Il timeout dell'adattatore del campanello è 5 s**, costante e dichiarato, contro una misura di
  0,43 s (dec. E).
- **http sulla tailnet**: la cifratura è di WireGuard (dec. D).
- **La pagina di arruolamento è senza identità visiva**, con il carattere di default del browser
  (dec. D).
- **Le pagine del companion sono nel tema scuro** (dec. D).
- **ELA gira dal repository**: il percorso di `apps/` si deriva dal package (dec. D).
- **La presenza mostra tre stati**, e gli altri aspettano M17.2 (dec. D).
- **Il campanello suona ogni approvazione, anche con l'utente al Mac** (dec. E).
- **Il campanello suona sul percorso del `run`**, trattenuto al più dal timeout costante
  dell'adattatore (dec. E).
- **Con E1, chi conosce l'argomento legge i campanelli e ne suona di falsi**, e il testo — senza
  niente dell'utente — e l'indirizzo del Mac sulla tailnet passano in chiaro da ntfy.sh, da FCM e da
  APNs (dec. E).
- **L'argomento del campanello passa per un momento dagli appunti del Mac e da Handoff** (dec. E).
- **Una morte fra la domanda e il campanello lascia una domanda senza campanello** (dec. E).
- **Il dispositivo, le conseguenze e la reversibilità non si nominano in una domanda** (dec. F).
- **Nessun tetto di rischio per il companion finché nessuna domanda supera `MEDIUM`** (dec. F.3).
- **Dall'iPhone, la voce si approva senza sentire** (dec. F.4).
- **Un «sì» dall'iPhone prosegue il task finché gli step restano su `local`**; uno step affidato a un
  altro nodo aspetta un `run` (dec. H).
- **Il browser può smettere di aspettare un `run` lungo**: il `run` continua, e la pagina successiva
  mostra lo stato vero (dec. H).

## Conseguenze

- Una colonna imposta in più su `devices` e una su `enrollments`; la regola 44 si estende a `role`,
  con il suo caso negativo in `tests/architecture/violations.py`.
- `DeviceOut` porta `role`, e `ela device list` lo mostra; la tabella di `ela node enroll` **non
  cambia** — P3 ha misurato che un doppio clic nel Terminale prende il codice intero e si ferma alla
  cella dopo, ed è così che il codice arriva sull'iPhone.
- Una riga in più in `FAILURES` (`EnrollmentRoleError` → `422` `invalid`), con la richiesta che la
  produce in `tests/api/test_failures.py`.
- Ogni costruzione di un `Device` dichiara il ruolo: non c'è un default nel dominio, perché il
  default sarebbe quello silenzioso — il ruolo con le rotte.
- **Tre regole di architettura nuove** — le pagine leggono le rotte (55), il campanello suona un
  metodo (56), un compositore solo per una pagina (57) —, ciascuna con il suo caso negativo, e due
  estese, la 46 (il cookie e l'argomento del campanello sono segreti) e la 47 (il cookie è un
  portatore d'identità come l'header). Le regole di `apps/ios/` non camminano Python: vivono in
  `tests/ios/`, e il README della cartella le nomina con il loro test.
- **Un port nuovo**, `Bell`, e un adattatore, `ela.providers.ntfy`; due variabili d'ambiente, in
  `.env.example` e in `VARIABLES`.
- **Otto rotte nuove** sotto `/companion/`, e `/openapi.json` non le descrive come descrive le
  altre: una pagina non è una forma del filo, e ciò che la prova è `tests/api/test_companion.py`.
- **Un tipo di evento nuovo**, `BELL_RUNG`, con il suo scrittore.
- **Il companion non recita la suite dei nodi**: ha il suo contratto, e le frasi della suite di
  M12.2 che promettevano il contrario si correggono dove stanno (dec. A).
- I totali di oggi: **cinquantasette** regole, **ventisei** port, **trentasette** rotte. Li appunta
  `tests/docs/test_adr_companion.py`, che è l'ADR più recente che li muove.
