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
