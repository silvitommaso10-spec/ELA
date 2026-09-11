# 0037. L'identità dei nodi: una macchina entra perché l'utente l'ha ammessa, e ne esce quando la revoca

- **Stato:** Accettata. SPEC di M12.1 approvata dall'utente il 2026-09-11, alla quarta stesura:
  D1–D20 prese fra il 2026-09-10 e il 2026-09-11, le domande aperte chiuse lo stesso giorno —
  undici come raccomandato, due in un'altra forma (il bind, dec. A; `available()`, dec. K).
- **Data:** 2026-09-11
- **Riferimenti spec:** §2.1, §4, §6, §15, §16, §17, §32, §33, §56, §57, §58
- **Continua:** ADR 0016 §5, §6; ADR 0017 §4; ADR 0022 §8; ADR 0023 §4, §6, §7; ADR 0024 §2, §8;
  ADR 0026 §1, §6, §7, §10; ADR 0030 §8, §15; ADR 0035 §2, §3, §5, §6; ADR 0036 §10, §12.
- **Estende:** ADR 0002 (due regole nuove, la 46 e la 47, ed estese la 31 e la 44), ADR 0005 (un
  port nuovo, `EnrollmentStore`), ADR 0016 e ADR 0035 (la riga di un nodo ha una terza metà),
  ADR 0017 §4 (il filtro F6, `REVOKED`), ADR 0022 §8 (la lapide, generalizzata), ADR 0023 §4 e §7
  (il bind fuori da loopback, e le identità che il middleware riconosce).

## Contesto

Fino a M12.1 ELA ha avuto un'identità sola da verificare, e non era un nodo: il token dell'API —
«One token, one identity (§2.1), on loopback.» (`api/security.py:3`). I nodi li ha **dichiarati**:
`local` ha un id deterministico perché è *questa* macchina (ADR 0016 §4), e la sua riga la scrive
il processo che quella macchina è. `ActorKind.DEVICE` esiste e nessuna riga di `src/ela` lo usa.

Con un secondo nodo la riga del registro diventa per la prima volta **la parola di qualcun
altro**, e ADR 0035 §5 aveva già scritto che cosa ne discende: un nodo remoto deve provare di
essere sé stesso, con «un'identità, non un id indovinabile», e due processi che dicono di essere
lo stesso nodo vanno «rilevati, nominati e rifiutati, non risolti dall'ordine di arrivo». ADR 0023
§7 teneva l'API su loopback e, scartando il bind aperto, rimandava qui: «un avviso non è un
confine; ELA sulla rete è la storia dei nodi, e avrà il suo ADR». È questo.

L'obiettivo, con le parole della spec (`docs/milestones/M12.1.md`):

> **Una macchina che non è questa entra nel mondo di ELA perché l'utente l'ha ammessa, a ogni
> richiesta prova di essere quella macchina, dice di sé soltanto ciò che solo lei sa — e smette di
> poterlo fare nel momento in cui l'utente la revoca.**

Il criterio di fine è di D2: *un nodo remoto si arruola, manda heartbeat, compare in
`GET /devices` e non riceve mai lavoro; un nodo revocato viene rifiutato.* Nessuna assegnazione,
nessuna esecuzione remota, nessuna suite di conformità: sono M12.2 e ADR 0038.

## 1. Le decisioni della fase, come vincoli ereditati

Le venti decisioni della Fase 12 le ha prese l'utente il 2026-09-10 e il 2026-09-11. Questo ADR
non le riapre e non le riscrive: il testo autorevole, con le correzioni del 2026-09-11 dentro le
loro etichette, è in `docs/milestones/M12.1.md` (§ «Le decisioni della Fase 12»), e M12.2 le cita
da lì come «M12.1, D*n*». Qui stanno le etichette e ciò che ciascuna vincola in questa milestone.

| Etichetta | Decisione | Che cosa vincola in M12.1 |
|---|---|---|
| D1 | La linea è `Tool.execute` | niente viaggia; l'identità deve rendere possibile che la richiesta che porterà un risultato venga da chi l'assegnazione nomina (D10) |
| D2 | Il taglio: due milestone | il perimetro, cioè il criterio di fine; e niente qui può essere un rifiuto che non scatta (§11, §12) |
| D3 | La riga del device ha tre metà | le tre metà (§10) e la regola 44 estesa (§16) |
| D4 | Il trasporto: HTTP, il nodo tira | enrollment, annuncio e heartbeat sono richieste del nodo; la revoca non si spinge, si manifesta alla richiesta successiva (§12) |
| D5 | L'identità: un segreto per nodo, enrollment monouso, revoca dal primo giorno | §5–§9 e §12; il buco del WAL in `.gitignore` e `ela init` riparati qui (§7); `local` resta l'unico id deterministico |
| D6 | La sparizione la decide l'idempotenza del tool | niente di eseguibile: le assegnazioni nascono in M12.2 |
| D7 | Lo stato: il nodo tiene solo la busta da consegnare | gli eventi nuovi li scrive il Core; un nodo non sceglie il proprio attore né il proprio id (§13) |
| D8 | L'assegnazione è un'entità nuova; ADR 0026 resta intatto | un nodo remoto non può diventare il nodo di un piazzamento eseguibile (§11) |
| D9 | I trait | `MISSING_TRAIT` non entra; la sua condizione d'ingresso è un vincolo dichiarato |
| D10 | Il middleware riconosce tre identità | §3 e §4 |
| D11 | `PROVIDER_CALLED` ed `ERROR_RECORDED` escono dall'enum | §14 |
| D12 | `ELA_USER_NAME`: lapide generalizzata, e l'attore è l'identità risolta | §15 |
| D13 | Il nodo revocato: una forma sola, il rifiuto `REVOKED`, in M12.1 | §12; `REVOKED` prodotto da un percorso di produzione (§11) |
| D14 | La riga `STARTED` di un tool remoto nasce quando il nodo reclama | niente di eseguibile: è M12.2 |
| D15 | Un verifier che legge un disco vale solo sulla macchina di quel disco | niente di eseguibile: nessuna chiamata a `Tool.execute` lascia il processo (§11) |
| D16 | Un'assegnazione per nodo alla volta, con una condizione sulla scadenza | niente: è M12.2 |
| D17 | Un nodo revocato con un'assegnazione già reclamata: scadenza immediata | niente di eseguibile; `revoked_at` sulla riga è il fatto che M12.2 leggerà (§12) |
| D18 | La sensibilità del task contro il tetto del nodo | un nodo remoto non si arruola `LOCAL_ONLY` (§5), ed è metà della garanzia di §11 |
| D19 | `OUT_OF_PROCESS` esce; la garanzia la tengono D18 e `PRIVACY` | nessun filtro sui nodi remoti, `Refusal` a sei membri (§11) |

D20 — la sensibilità del task è un campo di dominio — vive in M12.2 e in ADR 0038, che rivede
ADR 0017 §8 per il task; qui non vincola niente di eseguibile, se non che è il commit che la
introduce a ritirare il criterio 8 di M12.1 (D19).

## 2. Il bind: loopback e tailnet, mai `0.0.0.0`, un server solo

ADR 0023 §7 fissa che «solo un indirizzo di loopback è accettato». La decisione dell'utente del
2026-09-11 (M12.1 dec. A, nella forma A4, **contro** la raccomandazione A1):

> «Senza Tailscale ELA parte su loopback solo e `/diagnostics` lo dice. L'uso locale non dipende
> da un demone di terzi, e il confine di sicurezza è l'identità, non l'indirizzo — l'abbiamo già
> deciso.»

Quindi **due indirizzi, un server**. `ELA_API_HOST` resta il loopback di ADR 0023 §7, invariato.
Un secondo indirizzo, facoltativo, deve stare nell'intervallo di Tailscale e si controlla
all'avvio nella stessa forma del primo; `0.0.0.0` continua a fermare l'avvio. Lo stesso processo
serve la stessa app, con lo stesso middleware, da due socket: `uvicorn.Server.serve(sockets=[…])`
(uvicorn 0.52.4). La ragione per cui la stesura scartava due indirizzi — due server da tenere
uguali — con un server solo non esiste. Se all'avvio l'indirizzo della tailnet non esiste — la
tailnet è giù — ELA ascolta sul solo loopback, e `/diagnostics` dice su quali indirizzi ascolta. La
CLI parla sempre al loopback (ADR 0024 §2, invariato).

**Il nome della seconda variabile** la spec lo rimanda a questo documento, e nessuna decisione
approvata lo fissa: resta aperto, e lo chiude il commit che scrive il validatore del bind.

**L'intervallo di Tailscale** (100.64.0.0/10 in IPv4, `fd7a:115c:a1e0::/48` in IPv6) viene dalla
documentazione di Tailscale, non dal repository: prima di scrivere il validatore si verifica con
`tailscale ip` su questa macchina. È uno dei numeri che la spec non decide a occhio.

**Ciò che reggeva «siamo su loopback», voce per voce.** Tutto ciò che ADR 0023 ha scritto
poggiando su quel presupposto, e che cosa ne resta.

| Voce | Poggiava su loopback così | Con la tailnet | Perché |
|---|---|---|---|
| **Il token statico** — «Un token statico è un segreto in un file», senza scadenza e senza rotazione, con «loopback, un'identità, nessun TLS» (ADR 0023, vincoli dichiarati) | una sola identità possibile: chi sta su questa macchina | **regge per la CLI di questa macchina**, e smette di essere l'unica identità | i nodi hanno la propria, e il token non esce dal Mac: nessun nodo lo porta (D10) |
| **Nessun TLS** | nessun byte lasciava la macchina | **regge finché l'indirizzo è della tailnet** | WireGuard cifra da nodo a nodo; è la ragione per cui il secondo indirizzo si controlla sull'intervallo invece di accettare «un IP di rete» |
| **Chi può raggiungere la porta** | i processi di questa macchina | ogni macchina della tailnet dell'utente | da qui §13: i rifiuti anonimi non si scrivono nell'audit. Un segreto di 256 bit non si indovina; i tentativi non hanno limite (vincolo dichiarato) |
| **`GET /tasks/{id}` mostra gli argomenti degli step** — «contenuto dell'utente (§57) che torna **all'utente**, su loopback, dietro il suo token» (ADR 0023 §6) | chi presentava il token era l'utente su questa macchina | **cadrebbe se un'identità di nodo potesse chiamarla**: un segreto rubato leggerebbe il contenuto dell'utente di ogni task | regge con §4: un'identità di nodo non raggiunge `/tasks` |
| **`GET /audit`** | idem | idem | la regola 23 tiene fuori gli argomenti, ma restano i sommari, i nomi dei nodi, gli id dei task: solo il token del Core (§4) |
| **Un «sì» entra da una porta sola** (ADR 0024 §2; regola 19) | la porta era raggiungibile solo da qui | regge **solo se** la porta resta del token del Core | un'identità di nodo che potesse rispondere sarebbe un secondo portatore del «sì» (§4) |
| **`/health` protetta** — «siamo su loopback, e nulla di esterno deve sapere se ELA è viva» (ADR 0023 §7) | «esterno» non esisteva | **regge a maggior ragione** | sulla tailnet «esterno» esiste |
| **Path inesistente → 401; assente e sbagliato → lo stesso 401** (ADR 0023 §7) | un'identità | **regge ed è estesa** | una rotta che l'identità presentata non può chiamare risponde lo **stesso** 401, non un 403 (§4) |
| **`/openapi.json` dietro il middleware** | idem | regge | un nodo non lo raggiunge: non è fra le sue rotte (§4) |
| **`run` sincrono, lock in `app.state`** (`api/app.py:171`) | un solo client | invariato in M12.1 | le connessioni dei nodi in attesa di lavoro sono di M12.2 |
| **La CLI legge `ELA_API_HOST`** (ADR 0024 §2) | si connetteva a `127.0.0.1` | **invariato**: si connette al loopback | l'uso locale non dipende dalla tailnet |

La voce che cade davvero è `GET /tasks/{id}`, e la tiene in piedi soltanto l'elenco chiuso di §4.
Se quell'elenco venisse rovesciato, questa tabella va riscritta, non aggiornata.

## 3. Tre identità, un middleware

Il middleware, sempre in `api/security.py`, riconosce tre identità (D10, M12.1 dec. B):

| Identità | Come si presenta | Dove vale | Che cosa diventa |
|---|---|---|---|
| **il Core** | `Authorization: Bearer <ELA_API_TOKEN>` | ogni rotta tranne quelle che parlano *come* un nodo | `local`, che sulle rotte dell'utente sta per «l'utente a questa macchina» (§15) |
| **un nodo** | `Authorization: Bearer <device_id>.<segreto>` | solo le rotte dei nodi (§4) | il nodo con l'id coniato dal Core, attore `DEVICE` dove un evento lo nomina |
| **un codice di enrollment** | `Authorization: Bearer <codice>` | **solo** `POST /nodes/enroll`, **una volta** | nessuna identità durevole: consumarlo è l'atto che crea quella del nodo |

**Un header solo**, perché la metà iPhone del protocollo deve stare in «una richiesta HTTP con un
header e una risposta JSON» (`docs/STATO.md` §5.1). L'id nella credenziale serve al Core per
sapere con quale hash confrontare: **non è un segreto** — sta in `GET /devices` e nell'audit — e,
uscendo dall'`IdGenerator`, non si indovina; il segreto sì. Il separatore `.` non compare né in un
`token_urlsafe` né in un UUID. Ogni strada che fallisce dà **lo stesso 401**.

**L'identità risolta viaggia con la richiesta** (`request.state`), e le rotte la leggono da lì,
mai dall'header: è la regola 47 (§16). Oggi l'unico lettore dell'header è `api/security.py:50`;
domani le rotte delle approvazioni e della cancellazione vorranno sapere chi ha chiamato (§15), e
la tentazione più breve è leggerlo da sé.

**Il codice di enrollment è un'identità che il middleware riconosce, non un'esenzione**: la
ragione della regola 31 regge intera. Le due forme scartate lo sono dalle parole di D10: il nodo
che porta **anche** `ELA_API_TOKEN` — «Un token comune rende la revoca finta» — e la rotta di
enrollment fuori dal middleware — «Nessuna rotta fuori dal middleware».

## 4. Le identità e le rotte

Un'identità di nodo raggiunge **solo** le rotte dei nodi: `POST /nodes/heartbeat` e
`PUT /nodes/me`; il codice, solo `POST /nodes/enroll` (M12.1 dec. C, nella forma C3). È §33 — nel
dubbio, no — e un elenco che si estende è un elenco chiuso: le rotte del lavoro che un'identità di
nodo potrà chiamare **le aggiunge M12.2, in ADR 0038 letto in unione con questo**, che non si
riscrive.

**La forma**: un elenco `identità → rotte consentite` in `api/security.py`; tutto il resto riceve
lo **stesso** 401, non un 403, che «distinguerebbe «esisti ma no» da «non esisti»» (ADR 0023 §7).
Il verso opposto vale uguale: il token del Core su `POST /nodes/heartbeat` è rifiutato, perché non
è un nodo — l'heartbeat di `local` resta nel processo (`api/tasks.py:119`,
`composition/root.py:434`). Il test si **deriva** da `app.routes`: una rotta aggiunta domani, anche
da M12.2, è coperta per costruzione, e se M12.2 dimentica di estendere l'elenco le sue rotte
rispondono 401 al nodo, che è il verso sicuro.

**Nessun id nei percorsi del nodo.** La decisione dell'utente: «l'identità del nodo viene
dall'autenticazione, mai dal percorso: nessun id nelle rotte del nodo è la cosa che impedisce di
parlare a nome di un altro». L'identità **è** l'id, un nodo parla solo per sé, e la classe di
errori «l'id nel percorso non è quello della credenziale» non esiste.

Le cinque rotte (M12.1 dec. O):

| Metodo | Percorso | Identità | Che cosa fa |
|---|---|---|---|
| `POST` | `/nodes/enrollments` | il Core | conia un codice di enrollment, con la `privacy` imposta, mai `LOCAL_ONLY` (§5); non scrive nell'audit (§13) |
| `POST` | `/nodes/enroll` | un codice di enrollment, una volta | consuma il codice, conia id e segreto, fa nascere la riga; `DEVICE_ENROLLED` |
| `POST` | `/nodes/heartbeat` | un nodo | la metà osservata che il nodo riporta: `last_seen_at` e, se dati, `status`, `current_workload`, `power_source`; nessun evento (ADR 0016 §6) |
| `PUT` | `/nodes/me` | un nodo | la metà dichiarata, condizionale sulla revisione (§9); `DEVICE_ANNOUNCED` se cambia, `DEVICE_IDENTITY_CONFLICT` se la revisione è vecchia |
| `POST` | `/nodes/{device_id}/revoke` | il Core | la revoca (§12); `DEVICE_REVOKED` |

Comandi aggiunti, nella forma della tabella di ADR 0024 §3:

| Comando | Rotta | Uscite |
|---|---|---|
| `ela node enroll` | `POST /nodes/enrollments` | `0` `1` `2` `3` |
| `ela node revoke` | `POST /nodes/{device_id}/revoke` | `0` `1` `2` `3` |

Due comandi di un gruppo `node` **senza** `invoke_without_command`, perché la CLI è un client
(ADR 0024 §2) e ha le quattro uscite di ogni comando che parla con ELA. `ela device list` esiste
già (`GET /devices`) e mostra `revoked_at`. Le tre rotte che chiamano i nodi non hanno un comando,
e il test che vuole ogni rotta raggiungibile dalla riga di comando le trova **classificate per
nome**, non esentate per silenzio.

**Le approvazioni da un nodo non ci sono.** Sono fra i ruoli dell'iPhone (§6), ma il companion è
M12.5, e «questo nodo può rispondere alle approvazioni» è un permesso che l'utente dà **a un nodo
preciso**, della specie di `privacy`: si decide con la milestone che lo usa.

## 5. L'enrollment: chi conia che cosa

Il Core conia tutto; il nodo porta la sua metà dichiarata e nient'altro (D5, M12.1 dec. D).

1. **Il codice.** `ela node enroll --privacy <livello>` chiama `POST /nodes/enrollments` con il
   token del Core. Il Core conia il codice con `secrets.token_urlsafe(32)`, ne tiene **solo
   l'hash**, con la scadenza e la `privacy` imposta, e lo restituisce **una volta**.
2. **`LOCAL_ONLY` resta di `local` (D18).** Il corpo accetta soltanto `TRUSTED` e `CLOUD_ALLOWED`;
   `LOCAL_ONLY` riceve **422** con un messaggio che dice perché — è il livello di questa macchina,
   e un nodo remoto con quel livello riceverebbe ogni task, anche quelli di cui nessuno ha
   dichiarato la sensibilità — e **niente viene coniato**: nessun codice, nessuna riga. La difesa
   sta nel server e non nella CLI, perché la rotta si può chiamare senza di lei; la CLI offre
   comunque solo i due livelli. Nessun campo nuovo entra nella riga: il vincolo è sui valori di un
   campo che c'è già. `--privacy` è **obbligatoria e senza default** — il livello è «always
   declared», come chiede `PrivacyLevel` — e l'utente ha escluso anche il default ipotetico che la
   stesura teneva in serbo.
3. **L'arruolamento.** Il nodo presenta il codice su `POST /nodes/enroll`, con la propria metà
   dichiarata nel corpo. Il corpo **dichiara `extra="forbid"`**: i DTO di `ela.api` ignorano i
   campi sconosciuti (`api/schemas.py:102`, e il default di pydantic), e un nodo che prova a
   scrivere `privacy`, `network`, `revision` o `revoked_at` è guasto oppure ostile — in entrambi i
   casi va visto, con 422. Il Core consuma il codice con una `UPDATE` condizionale —
   `WHERE code_hash = :h AND consumed_at IS NULL AND expires_at > :now`, la forma di ADR 0012 §5 —
   conia l'id con il suo `IdGenerator` e il segreto con `secrets.token_urlsafe(32)`, e fa nascere
   la riga: metà dichiarata dal corpo, `privacy` dal codice, `network` `REMOTE`, revisione 1, mai
   vista — quindi non disponibile, perché «registrare un nodo dichiara che esiste, non che
   risponde» (ADR 0016 §3). Risponde `{device_id, secret, revision}`: **l'unica risposta di ELA che
   contiene il segreto di un nodo**, una volta.
4. **La scadenza del codice** è una costante con un tetto, non una variabile: dieci minuti, perché
   «un TTL senza tetto è una porta che si può lasciare aperta per sempre scrivendo un numero
   grande» (ADR 0023 §3), e una variabile costerebbe `.env.example`, `VARIABLES` e il test che li
   tiene uguali senza che nessuno l'abbia chiesta. Il numero è da misurare su un arruolamento vero,
   soprattutto dallo Shortcut.
5. **L'entropia del codice è quella del segreto.** Si custodisce come SHA-256, e «l'hash di una
   nota breve si inverte per dizionario» (ADR 0014, alternativa F): un codice di sei cifre sotto
   uno SHA-256 lo inverte chiunque legga il database. Si incolla, non si digita.
6. **La finestra di crash, dichiarata.** Se la riga nasce e la risposta si perde, il nodo non ha il
   segreto e il codice è consumato: riprovare dà 401 e un `DEVICE_REJECTED` `code_reused` (§13).
   La riga resta, mai vista; l'utente la vede in `GET /devices` e la revoca. Restituire lo stesso
   segreto a un secondo tentativo vorrebbe tenerlo in chiaro: no.

**Il codice passa per il terminale, e la ragione di ADR 0024 §8 non si applica.** La decisione
dell'utente: «il codice lo porta la persona, il segreto durevole non passa mai da un terminale».
`ela node enroll` **stampa il codice una volta**, con la scadenza accanto. ADR 0024 §8 vieta di
stampare un segreto perché «un segreto su un terminale è un segreto nello scrollback e nella
cronologia», e la ragione di quel divieto è la **durata**: un token nello scrollback resta valido.
Un codice monouso che scade in minuti, nello scrollback, è un valore morto. Il segreto durevole
invece **non si stampa mai**: va dalla risposta dell'enrollment dritto nella custodia del nodo. Dal
lato del nodo il codice si legge da stdin senza eco, mai come argomento (ADR 0024 §2: «un segreto
sulla riga di comando finisce nella cronologia della shell e in `ps`»); come lo riceva uno
Shortcut il repository non lo dice, ed è M12.5.

## 6. Il segreto: SHA-256, e un solo modulo che confronta

**Generazione:** `secrets.token_urlsafe(32)`, 256 bit, la stessa di `ela init`. **Custodia:** lo
SHA-256 (`hashlib.sha256`, già nel repository), mai il segreto (M12.1 dec. E, nella forma E1). La
decisione dell'utente: «SHA-256 basta perché il segreto è casuale ad alta entropia, non una
password. Il confronto passa dalla regola 31 (`compare_digest`), come gli altri». È l'argomento che
ADR 0014 fa al rovescio: un hash protegge soltanto ciò che ha entropia, e per un valore casuale di
256 bit non esiste un dizionario né conta la velocità dell'hash.

**Il confronto.** Il Core calcola lo SHA-256 del segreto presentato e lo confronta con l'hash
custodito con `secrets.compare_digest`, **in `api/security.py`**, accanto al token del Core
(`api/security.py:43`): un solo modulo confronta credenziali, così `SECURITY_MODULE` della regola
31 resta un percorso solo, e sono i suoi `TOKEN_NAMES` a imparare i nomi nuovi (§16).

**Il tempo che separa «id sconosciuto» da «segreto sbagliato»** rivela se un UUID esiste — cosa
che nessuno può indovinare in anticipo. Non è difeso, ed è detto.

**Che cosa il segreto non fa mai**: non compare nell'audit, in un errore, in `GET /devices`, in un
URL, in un log; viaggia solo in un header; l'entità `Device` non ha un campo per il suo hash. È la
regola 46 (§16).

## 7. Dove vive il segreto, lato per lato

Il vincolo dell'utente (D5): **mai in un file che un `git add -A` possa portarsi dietro** (M12.1
dec. F).

| Lato | Dove vive | Che cosa fa M12.1 |
|---|---|---|
| **Core — l'hash del segreto** | nel database: di default `~/.ela/ela.db`, in una cartella `0o700`, fuori dall'albero di lavoro | **ripara il buco del WAL**: con `ELA_DB_URL` dentro il repository, `ela.db-wal` ed `ela.db-shm` non erano ignorati, e in WAL le scritture recenti stanno nel `-wal` finché un checkpoint non le riporta nel file principale. Due righe esplicite, `*.db-wal` e `*.db-shm` — non `*.db-*`, che ignorerebbe cose che nessuno ha nominato — dopo il test che falliva |
| **Core — il codice di enrollment** | solo il suo hash, con la scadenza; in chiaro esiste soltanto nella risposta di `POST /nodes/enrollments` | idem |
| **Nodo macOS (M12.3)** | il repository non lo dice | scrive il vincolo del contratto: **fuori dall'albero di lavoro**, `0o600` dal primo byte in una cartella `0o700`. Se un processo non firmato raggiunga il Keychain si misura in M12.3, contro il muro di ADR 0029 §16: «il passaggio a `launchd` richiede **un eseguibile firmato proprio di ELA**» |
| **Nodo Windows (M12.4)** | il repository non lo dice | su Windows `os.chmod` cambia solo il flag di sola lettura (documentazione di Python, non il repository): il `0o600` lì non protegge. Credential Manager / DPAPI o file: una misura di M12.4 |
| **iPhone / Shortcut (M12.5)** | il repository non lo dice | dove uno Shortcut tiene un segreto, e se uno Shortcut condiviso, esportato o sincronizzato se lo porta con sé: una misura di M12.5 |

**Il lato nodo non ha codice in M12.1** — `nodes/` contiene solo README — e la suite di
conformità di M12.2 **non potrà** verificarlo, perché dove un nodo tiene il segreto non passa per
HTTP: è un vincolo dichiarato.

**`0o600` dal primo byte.** Chi scrive un segreto crea il file con `os.open(path, os.O_WRONLY |
os.O_CREAT | os.O_EXCL, 0o600)`: il modo nasce con il file, l'umask può solo restringerlo, e
`O_EXCL` rende atomico anche «non sovrascrivere mai un file che c'è». `ela init` scriveva `.env`
e poi ne cambiava il modo, e per un istante il file aveva quello dell'umask: riparato in questa
milestone, come bug trovato — prima il test che fallisce, poi il fix — perché gli scrittori di
segreti di M12.3–M12.5 copieranno la forma che trovano nel repository.

## 8. Dove vivono l'hash, il codice e la revoca: il ventiquattresimo port

**Una riga, un fatto** (M12.1 dec. G, nella forma G2). L'hash del segreto e `revoked_at` sono
colonne della riga `devices`; l'entità `Device` porta `revoked_at` e `revision`, **non** l'hash.
La revoca sta così sulla riga che l'orchestratore legge, che è ciò che serve a `REVOKED` (§12), e
l'hash esce dal port solo verso il confronto.

Il codice non è un dispositivo — finché non è consumato non esiste nessun nodo — quindi ha il suo
port, **il ventiquattresimo**: `EnrollmentStore`, async, con l'offerta e il consumo condizionale di
§5, il contract test sul fake e sull'adapter SQL, la riga in `REQUIRED_PORTS`. `DeviceRegistryPort`
guadagna `revoke(device_id, *, at)` (§12) e una scrittura per ogni metà (§9); se dopo le scritture
per metà `update` non ha più chiamanti, esce dal port invece di restarci come porta aperta.

I nomi dei membri li fissa il commit che scrive il port, e sono questi; `tests/docs/test_adr_ports.py`
legge le due tabelle.

Port introdotti:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `EnrollmentStore` | §16 | async | `offer`, `consume` |

Port estesi:

| Port | Spec | Modalità | Membri |
|---|---|---|---|
| `DeviceRegistryPort` | §16 | async | `enroll`, `secret_hash`, `announce`, `observe`, `revoke` |

`enroll` fa nascere la riga con l'hash, e `secret_hash` è l'unica strada dell'hash fuori dal port:
porta al confronto di `api/security.py` (§6). `announce` e `observe` sono le scritture per metà di
§9; la metà che `announce` scrive è `ANNOUNCED_FIELDS` di `ela.ports`, cioè la riga «Dichiarata»
di §10, e un test tiene uguali le due. I rifiuti hanno un nome — `IdentityConflictError`,
`DeviceRevokedError`, e per il codice `EnrollmentConsumedError`, che porta il nodo nato dal codice
(`code_reused`, §13), ed `EnrollmentExpiredError` — e nessuno porta il codice o il suo hash.
`update` resta finché ha un chiamante, per la regola detta sopra.

**La migrazione `0008`**: `revision`, `revoked_at` e `secret_hash` su `devices` — l'ultimo nullo
per `local`, che non si autentica dalla rete — e la tabella `enrollments`; reversibile, con il suo
test di downgrade.

Tabella nuova:

| Tabella | Colonne |
|---|---|
| `enrollments` | `seq`, `code_hash`, `created_at`, `expires_at`, `privacy`, `consumed_at`, `device_id` |

Colonne aggiunte:

| Tabella | Colonne |
|---|---|
| `devices` | `revision`, `revoked_at`, `secret_hash` |

## 9. Una scrittura per ogni metà, e la revisione

ADR 0016 §5 teneva la `UPDATE` condizionale in tasca, «già progettata due volte in questo
repository»; ADR 0035 §5 ne ha fatto un vincolo: la scrittura deve essere condizionale su ciò che
il nodo credeva di aver scritto l'ultima volta. Questa è la terza applicazione, dopo `consume`
(ADR 0012 §5) e `respond`.

Oggi l'heartbeat scrive attraverso `update`, che **sostituisce la riga intera**, dopo averla letta.
Con un solo scrittore è innocuo; con un nodo remoto che annuncia e manda heartbeat — due richieste
che può mandare insieme — un heartbeat che ha letto la riga prima di un annuncio la riscrive con
ciò che aveva letto, e l'annuncio si perde: «Un `update` di configurazione concorrente a un
heartbeat è invece una vera sovrascrittura» (ADR 0016 §5).

**Ogni metà ha la sua istruzione** (M12.1 dec. H, nella forma H2), su colonne disgiunte:

- **l'annuncio** scrive solo le colonne dichiarate, `WHERE id = :id AND revision = :expected AND
  revoked_at IS NULL`, e incrementa la revisione;
- **l'heartbeat** scrive solo le colonne osservate che porta, senza revisione;
- **la revoca** scrive solo `revoked_at`, `WHERE revoked_at IS NULL`.

Se l'`UPDATE` non tocca righe, una `SELECT` nella stessa transazione dice perché — nodo
sconosciuto, revocato, revisione vecchia —: «La sicurezza sta nell'`UPDATE`, la `SELECT` serve solo
al nome dell'errore.» (ADR 0012 §5). **Revisione vecchia ⇒ 409 al nodo e
`DEVICE_IDENTITY_CONFLICT`.** Il nodo riceve la revisione nuova a ogni annuncio riuscito; un
secondo processo con la stessa credenziale e una revisione vecchia perde — non per ordine di
arrivo, ma perché credeva una cosa falsa sulla riga. È ADR 0035 §5 reso istruzione. Il test usa due
connessioni vere sullo stesso file, una barriera fra la lettura e la scrittura, e asserisce sul
`rowcount` — uno e zero — non sulla riga finale.

**I limiti, dichiarati.** Due cloni che mandano solo heartbeat non si vedono: la revisione sta
sulla metà dichiarata. E `local` resta com'è: ADR 0035 §5 lo lascia oscillare e rende
l'oscillazione leggibile, e metterlo sotto la revisione trasformerebbe l'avvio di due ELA sullo
stesso database in un rifiuto di partire, che è una decisione su `local` e non di questa milestone.

## 10. La riga di un nodo ha tre metà

ADR 0035 §2 ha diviso la riga in due metà: dichiarata e osservata. Con un nodo remoto, `privacy`
in quella dichiarata voleva dire che il valore che decide se il contenuto dell'utente può andare su
una macchina sarebbe stato compilato **da quella macchina**. D3 aggiunge una terza metà, e M12.1
colloca i campi che D3 lasciava alla spec (M12.1 dec. I):

| Metà | Chi la scrive | Campi |
|---|---|---|
| Dichiarata | il nodo, su sé stesso | `name`, `os`, `capabilities`, `available_tools`, `performance` |
| Osservata | il registro | `availability`, `last_seen_at`, `status`, `current_workload`, `network`, `power_source` |
| Imposta | l'utente, all'enrollment | `privacy` |

La tabella sostituisce quella di ADR 0035 §2 per chi confronta le metà con il codice; ADR 0035 non
si riscrive. Per `local` il nodo è questo processo, e la sua metà dichiarata la scrive
`ensure_local` come prima (ADR 0035 §2); `privacy` e `network` nascono con la riga (ADR 0016 §4) e
`ensure_local` smette di riscriverle: `DECLARED_FIELDS` perde `network` e `privacy` e guadagna
`performance`.

**«Osservata» vuol dire *scritta dal registro*, non *vera*.** È la precisazione dell'utente del
2026-09-11 dentro D3: «È la riga che regge il nodo che mente su di sé». `status`,
`current_workload` e `power_source` arrivano con l'heartbeat e il loro contenuto è la parola del
nodo; il registro li scrive, non li garantisce. Un nodo compromesso può mentire su ciò che
dichiara e su ciò che riporta, e la menzogna gli vale punti di punteggio; non gli apre il lavoro che
l'utente non gli ha affidato.

**`privacy`, imposta: il tetto di ciò che il nodo può ricevere (D3, D18).** Letta sul confronto di
oggi — F2 rifiuta se `PRIVACY_ORDER[device.privacy] > PRIVACY_ORDER[requirements.max_privacy]`
(`devices/orchestrator.py:318`), e un task che nessuno ha dichiarato arriva con `LOCAL_ONLY` —
`privacy` dice fin dove arriva la sensibilità dei task che un nodo può ricevere: `LOCAL_ONLY`
riceve tutto, quindi è di `local` e di nessun altro (§5). Il valore sicuro per `local`,
«fail-safe: una privacy non dichiarata non è un permesso (§33, §57)» (ADR 0016 §4), è il più
permissivo per un nodo remoto: è la trappola di verso che la conseguenza di D18 chiude.

**`network`, del registro.** Fissata alla nascita della riga: `REMOTE` per ogni nodo che entra
dall'API, `LOCAL` per `local`. Non la dichiara il nodo, perché è un fatto del trasporto e non della
macchina, e vale punti (`NETWORK_POINTS`: 20 contro 5): un nodo che si dichiarasse `LOCAL` si
prenderebbe i punti di questa macchina. Non la impone l'utente, perché non è una policy. **Non
decide chi esegue** (§11).

**`performance`, dichiarata dal nodo.** La ragione di ADR 0035 §2 per tenerla fuori — nessuno può
dichiararla senza sondare — riguardava chi compone ELA parlando per questa macchina; un nodo che
descrive sé stesso si sonda. Un nodo che mente guadagna fino a 15 punti, mai l'idoneità (ADR 0017
§2).

**`power_source`, con l'heartbeat.** Cambia durante una sessione, quindi non è un fatto
dell'annuncio: viaggia con l'heartbeat come `status` e `current_workload` (ADR 0016 §7).
`performance` e `power_source` entrano nel contratto da subito, facoltative e `UNKNOWN` se assenti:
il contratto si scrive una volta e si implementa tre volte (M12.3–M12.5).

**`revision` e `revoked_at` stanno fuori dalle tre metà.** Non descrivono la macchina: sono lo
stato della sua identità. `revision` la scrive l'annuncio riuscito (§9), `revoked_at` la revoca
(§12). Un corpo del nodo che porta `privacy`, `network`, `revoked_at` o `revision` riceve 422 e la
riga non cambia.

## 11. Nessun filtro sui nodi remoti: la garanzia la tengono D18 e `PRIVACY`

**Perché la domanda c'è.** «Non riceve mai lavoro» non è gratis. L'orchestratore giudica **tutti**
i nodi registrati (`devices/orchestrator.py:511`) e il runner esegue **nello stesso processo**
qualunque nodo il piazzamento nomini (`executive/runner.py:219`). Un nodo remoto con un heartbeat
fresco, che dichiara ogni tool e `performance` `HIGH` e riporta `power_source` `AC`, recupera 25
punti sui 15 che la distanza gli toglie, mentre `local` quei due componenti li ha a zero: se fosse
idoneo **vincerebbe**, `DEVICE_SELECTED` lo nominerebbe, e il tool girerebbe su questo Mac. Un
audit che dice che un tool è girato altrove mentre è girato qui è la bugia peggiore che §32 possa
contenere.

**Perché non c'è un filtro (D19).** La quarta stesura ne proponeva uno, un settimo membro di
`Refusal`, `OUT_OF_PROCESS`, destinato a uscire in M12.2. L'utente, il 2026-09-11: «La diagnosi
con solo `PRIVACY` è incompleta, non falsa — il task è `LOCAL_ONLY` e il nodo non lo è, ed è vero.
Un membro del vocabolario chiuso che vive una milestone e poi sparisce è rumore nella catena degli
ADR, e in M12.1 nessun nodo remoto esiste in produzione: quella diagnosi la leggerebbero i test.»
Il membro non entra, e `Requirements` non cambia forma.

**Come regge la garanzia.** Quattro fatti:

- **`POST /nodes/enrollments` rifiuta `LOCAL_ONLY` per un nodo remoto** (D18, §5), e `privacy` non
  la scrive il nodo (§10);
- **`run` non passa mai `max_privacy`** (`api/tasks.py:122`, l'unico chiamante di produzione del
  runner), e il default è `LOCAL_ONLY` (`executive/runner.py:160`), che il runner passa tale e quale
  a `place` e a `confirm` (`executive/runner.py:265-271`);
- quindi **F2 (`devices/orchestrator.py:318`) rifiuta ogni nodo remoto su ogni `run`**, qualunque
  punteggio abbia: `PRIVACY_ORDER` dà zero a `LOCAL_ONLY`, uno a `TRUSTED`, due a `CLOUD_ALLOWED`
  (`devices/orchestrator.py:88`);
- **`ensure_placed`** (`devices/orchestrator.py:267`), che l'executor chiama prima del tool
  (`executive/executor.py:455`), rilancia `refusals` sul nodo della decisione con i requisiti della
  decisione: un `PlacementDecision` costruito a mano che nomini un nodo remoto, con i requisiti che
  `requirements()` costruisce, è rifiutato da sé perché `PRIVACY` scatta — la seconda difesa di ADR
  0026 §1, gratis.

Il limite, detto: un piazzamento costruito a mano **con** un `max_privacy` più largo passa, perché
`ensure_placed` rifiuta solo quando «la decisione è in disaccordo con sé stessa» (ADR 0026 §3). È
il caso del chiamante di produzione che passasse un `max_privacy` più largo prima del ramo remoto di
M12.2, e lo prende il criterio 8 della spec, dal `run` vero.

**`REVOKED` scatta ma, in M12.1, non decide mai da solo.** Compare fra i rifiuti di ogni nodo
remoto revocato, ma quel nodo `PRIVACY` l'ha già rifiutato, e `local` non si revoca (§12). In M12.1
è una diagnosi, quella che D13 chiede; decide da solo quando un task potrà dichiararsi `TRUSTED`
(M12.2, D20). Non è il filtro vacuo di ADR 0026 §7, che nessuna capability reale poteva attivare:
nessun filtro precede il calcolo dei rifiuti, e ogni `POST /tasks/{id}/run` piazza ogni step con
`place`, che giudica **ogni** riga di `devices()` — le revocate comprese — e scrive nell'audit, per
ogni candidato, i suoi rifiuti (`devices/orchestrator.py:604`). Dal momento in cui un nodo remoto è
revocato, ogni `run` scrive una riga in cui quel nodo compare con `PRIVACY` e `REVOKED`; se nessun
nodo è idoneo, `Run.reason` li conta per nome, perché `_summary` (`devices/orchestrator.py:394`)
itera su tutto l'enum.

**`confirm` non cambia una riga.** Rilegge il nodo da `devices()` (`devices/orchestrator.py:546`),
lo trova — la riga di un nodo revocato c'è — e lo giudica: la ragione dice «is no longer eligible»
(`:560`) e nomina `PRIVACY` e `REVOKED`, non «is no longer registered» (`:549`). In M12.1 `confirm`
è raggiunto in produzione solo per `local`, quindi il suo ramo `REVOKED` lo prova un test unitario;
non è una difesa nuova che non scatta, è la stessa funzione `refusals`, che in produzione scatta
attraverso `place`.

**Che cosa ne fa M12.2 (D19).** Il ramo remoto dell'executor va **prima** della sensibilità del
task nell'ordine dei commit, e quell'ordine è un criterio di accettazione di M12.2, non una nota:
finché un task non può dichiararsi più largo di `LOCAL_ONLY`, F2 tiene fuori ogni nodo remoto
anche nel commit in cui l'executor impara a raggiungerne uno. Il criterio 8 di M12.1 lo ritira il
commit che introduce la sensibilità del task, dicendolo. Come l'executor decida che un nodo è
questo processo — per id, e non per `network`, che è un componente del punteggio (ADR 0030 §8) —
lo fissa M12.2.

## 12. La revoca: tenere e marcare, e un rifiuto che dice «revocato»

**La riga resta.** ADR 0016 §6: «chi indaga su un'azione deve poter ricostruire quali nodi
esistevano allora». Una riga cancellata lascerebbe nell'audit `device_id` che non puntano a niente.
E D13: «Una diagnosi che dice "non registrato" quando è "revocato" è falsa, e le ragioni false le
abbiamo appena finite di togliere.» (M12.1 dec. K.)

- **Sul port**: `revoke(device_id, *, at)`, una `UPDATE` condizionale — `SET revoked_at = :at WHERE
  id = :id AND revoked_at IS NULL`. Se non tocca righe, la `SELECT` dice perché: sconosciuto (404)
  o già revocato (200, la riga com'è, **nessun secondo evento**: «Ripetere una risposta identica
  non è un errore: è la stessa risposta.», ADR 0023 §8).
- **`local` non si revoca**: 409 con un codice suo. È questa macchina, non ha un segreto, e
  revocarla lascerebbe il Core senza nessun nodo su cui eseguire e senza un enrollment con cui
  rimediare.
- **Nel middleware**: una credenziale la cui riga ha `revoked_at` riceve **lo stesso 401** di un
  segreto sbagliato, e il motivo va nell'audit, `DEVICE_REJECTED` con motivo `revoked` (§13). Un
  annuncio di un nodo revocato non arriva nemmeno all'`UPDATE`: il middleware lo ferma prima, e
  l'istruzione di §9 porta comunque `revoked_at IS NULL`. La revoca non si spinge (D4): si
  manifesta alla richiesta successiva del nodo revocato.
- **La rotta e il comando**: `POST /nodes/{device_id}/revoke`, solo con il token del Core (§4), ed
  `ela node revoke <device_id>`. L'attore di `DEVICE_REVOKED` è `USER`, con l'id dell'identità che
  il middleware ha risolto per quella chiamata — `local`, l'utente a questa macchina (§15).
- **Che cosa non fa in M12.1**: niente da interrompere, perché non esistono assegnazioni. La
  revoca di un nodo con un'assegnazione già reclamata è scadenza immediata (D17), ed è M12.2; una
  `PermissionDecision` già spedita a un nodo è limitata dai cinque minuti di ADR 0011 §9, ed è
  M12.2.

**Nell'idoneità: `Refusal.REVOKED`, sesto membro (D13).** Scarta un nodo perché l'utente lo ha
revocato, letto da `device.revoked_at`. Ultimo, dopo `DEGRADED`, perché inserirlo prima
rinumererebbe un filtro esistente senza ragione. ADR 0017 è immutabile, quindi la riga sta qui,
nella forma della tabella di ADR 0017 §4, e i test leggono l'unione:

| # | Filtro | Regola | Rifiuto | Perché |
|---|--------|--------|---------|--------|
| F6 | revoca | `device.revoked_at is None` | `REVOKED` | D13; §33: un nodo che l'utente ha revocato non riceve lavoro, qualunque cosa dica il suo ultimo heartbeat |

La forma scartata dalla terza stesura (K2, il revocato fuori dai candidati) è quella che D13 dice
falsa: il nodo sparirebbe dal payload di `DEVICE_SELECTED` invece di comparirvi con la sua ragione.

**`available()` considera `revoked_at`; `seen()` no.** Decisa dall'utente il 2026-09-11, contro la
raccomandazione: «Un nodo revocato disponibile per un TTL è una diagnosi falsa, e la derivazione in
lettura resta tale con una condizione in più.» `available()` risponde a «posso usarlo adesso», e un
nodo revocato non si può usare: la condizione entra lì, letta a ogni lettura come quella del TTL
(ADR 0016 §3). **Non** entra in `seen()`: la `availability` che `seen()` deriva resta il fatto
dell'heartbeat, perché è ciò che la diagnosi F1 dice di sé — «No heartbeat within the TTL»
(`devices/orchestrator.py:115`) — e un nodo revocato con l'heartbeat fresco diagnosticato
`UNAVAILABLE` sarebbe un'altra diagnosi falsa. Due fatti, due nomi: `GET /devices` porta
`available: false` subito, con `revoked_at` accanto; l'orchestratore, che giudica ogni riga di
`devices()`, lo diagnostica `REVOKED` (e `PRIVACY`, finché ogni task è `LOCAL_ONLY`).
`/diagnostics` (`api/system.py:62`) e il Context Core (`context/core.py:271`) leggono `available()`
e ne ereditano la condizione.

## 13. Gli eventi di audit, e quali rifiuti si scrivono

I due eventi di M6.1b **non** si riusano con un altro attore: ADR 0035 §3 li intesta a `SYSTEM` —
«L'attore è `SYSTEM` e non `DEVICE`: `DEVICE` è per un nodo che annuncia **sé stesso**, e il giorno
in cui esisterà firmerà la propria riga» — e ADR 0016 §6 chiede per la registrazione dall'esterno
«il suo `AuditEventType`, il suo attore (`DEVICE` per un nodo che si annuncia, `USER` per una
configurazione manuale)». Nascono cinque eventi (M12.1 dec. L):

| Evento | Quando | Attore |
|---|---|---|
| `DEVICE_ENROLLED` | il codice è consumato e la riga nasce | `USER` |
| `DEVICE_ANNOUNCED` | un nodo scrive la propria metà dichiarata, e qualcosa è cambiato | `DEVICE` |
| `DEVICE_IDENTITY_CONFLICT` | un annuncio con una revisione che non è più quella corrente | `DEVICE` |
| `DEVICE_REJECTED` | una richiesta che nomina un nodo esistente, rifiutata | `SYSTEM` |
| `DEVICE_REVOKED` | l'utente revoca un nodo | `USER` |

Perché ciascuno è un nome suo:

- **`DEVICE_ENROLLED`**: l'ammissione è dell'utente — il codice porta la sua decisione, la
  `privacy` imposta — ed è la configurazione manuale di ADR 0016 §6; l'id è quello dell'identità
  che ha coniato il codice (§15).
- **`DEVICE_ANNOUNCED`**: il primo scrittore di `ActorKind.DEVICE`, il nodo che annuncia sé stesso
  e firma la propria riga (ADR 0035 §3).
- **`DEVICE_IDENTITY_CONFLICT`**: ADR 0035 §5, «rilevati, nominati e rifiutati». Chi scrive **ha**
  il segreto, ed è proprio questo il conflitto.
- **`DEVICE_REJECTED`**: senza, la revoca prometterebbe un motivo nell'audit che non esiste.
  L'attore è `SYSTEM`, con l'id dichiarato nel payload **come dichiarazione**, non come attore:
  un'identità che non si è provata non firma, e chi decide il rifiuto è il Core — «chi sceglie
  scrive, non chi tocca» (ADR 0026 §10). L'obiezione sta nel dominio stesso — «``SYSTEM`` is for
  what no one asked for: schedulers, retries, expiries.» (docstring di `ActorKind`), e un rifiuto è
  la risposta a una richiesta — e l'utente ha chiuso la domanda come raccomandato.
- **`DEVICE_REVOKED`**: una configurazione manuale, ed è l'atto che rende l'identità revocabile
  (D5).

Valgono le regole di M6.1b: il sommario porta **il diff**, non un conteggio (ADR 0035 §3); **se
non cambia niente non si scrive niente**; il segreto, il suo hash e il codice non compaiono mai in
un sommario (regola 46). Coniare un codice non scrive nulla: un codice che scade inutilizzato non
cambia niente nel mondo di ELA, e l'ammissione è un fatto solo, scritto quando accade, con il
sommario che dice quando e da chi il codice era stato coniato. Li scrive il registro, che è già uno
scrittore di audit (ADR 0035 §3); il middleware gli dice perché ha rifiutato. Gli eventi li scrive
il Core, e un nodo non sceglie il proprio attore né il proprio id (D7). L'heartbeat resta fuori
dall'audit: «L'heartbeat resta fuori dall'audit anche allora.» (ADR 0016 §6).

**Quali rifiuti entrano nella catena.** Con il bind sulla tailnet, scrivere ogni 401 nell'audit
vorrebbe dire che qualunque macchina della tailnet scrive righe nella catena di §32 quando vuole.
Quindi `DEVICE_REJECTED` solo quando la richiesta nomina un nodo **che esiste**, con uno di quattro
motivi d'identità, scritti dal registro:

- `bad_secret` — segreto sbagliato per un id noto;
- `revoked` — nodo revocato;
- `route_not_allowed` — nodo su una rotta fuori dal suo elenco (§4);
- `code_reused` — un codice già consumato presentato di nuovo, che nomina il nodo che ha fatto
  nascere: il nodo legittimo che ha perso la risposta, o qualcuno che ha copiato il codice.

I motivi della via del lavoro (`late`, `task_closed`, `not_assigned`, `delivery_conflict`) sono di
M12.2, che scriverà i suoi; `revoked` coincide.

**I rifiuti anonimi non entrano nella catena, ma si contano.** Niente presentato, id sconosciuto,
codice sconosciuto, codice scaduto mai consumato: richieste anonime, a cui il 401 dice già tutto
quello che c'è da dire. Non spariscono: «chi bussa senza nome è un fatto da vedere, non da
incidere per sempre» (l'utente, 2026-09-11). Si contano, per motivo, in un contatore che
`/diagnostics` espone — nella memoria del processo, azzerato a ogni avvio, e dichiarato così. Un
log non è l'alternativa: nessun modulo di `src/ela` usa `logging`, e aprirne uno sarebbe una
superficie nuova.

## 14. Il debito di ADR 0036 §12, saldato

ADR 0036 §12 datò il 2026-09-10 un debito — `PROVIDER_CALLED` esisteva nell'enum e nessun modulo
di `src/ela` lo scriveva — e lo mise a carico di chi aggiungerà il prossimo `AuditEventType`, con
la domanda nel verso giusto: «serve, o va tolto?». **Ha pagato M12.1**, perché aggiunge cinque tipi
di evento (§13): aggiungendoli ha trovato davanti l'unico membro che non scattava, e un secondo che
nessun debito copriva. Il congegno di ADR 0036 §12 ha funzionato come quello di ADR 0035 §7: chi
tocca l'enum decide, invece di aggiungere un tipo accanto a uno morto.

**La risposta (D11): tolti entrambi.**

- **`PROVIDER_CALLED`** fu promesso da ADR 0008 — «`PERMISSION_DECIDED`, `TOOL_EXECUTED`,
  `PROVIDER_CALLED` li scriverà chi chiama il Guardian e chi esegue (M5+)»
  (`docs/adr/0008-task-engine.md:96-97`). Gli altri due hanno avuto uno scrittore; lui no. La
  chiamata a un provider è già nell'audit, dentro `TOOL_EXECUTED`, che porta `usage` (ADR 0036
  §12, ADR 0020 §6).
- **`ERROR_RECORDED`** non aveva uno scrittore e nessun debito lo copriva. L'unico ADR che l'abbia
  considerato l'ha scartato: «`ERROR_RECORDED` solo sul fallimento, nessun evento sul pass» (ADR
  0014, alternativa H). **Gli errori sono già nell'audit, dentro `TASK_FAILED` e `STEP_FAILED`.**
- Nessuno li ha mai scritti, quindi nessuna riga di nessuna catena li porta; e `event_type` è una
  stringa di 32 caratteri senza vincoli sui valori
  (`migrations/versions/0002_audit_events.py:40`): toglierli non chiede una migrazione.

**La difesa generale al posto di quella locale.** Il test **«ogni tipo di evento ha uno
scrittore»**, in `tests/docs/test_adr_nodes.py`: per **ogni** membro di `AuditEventType`,
`writers_of` — la lettura dall'AST di `tests/docs/test_adr_listening.py`, che non scambia un
docstring per uno scrittore — trova almeno un modulo di `src/ela`. Sull'albero di prima falliva
esattamente su `PROVIDER_CALLED` ed `ERROR_RECORDED`; fallisce domani sul prossimo tipo aggiunto
senza chi lo scriva, i cinque di questa milestone compresi. Non è una regola di `RULES`: legge
l'enum contro l'albero, come faceva il guardiano che sostituisce, e vive nel test dell'ADR.

**Il guardiano di ADR 0036 §12 si rovescia.** Era scritto per accorgersi del proprio pagamento —
«Il giorno in cui qualcuno gliene dà uno — o lo toglie dall'enum — quel test fallisce e questa
sezione esce con lui» — e ora asserisce che il membro non c'è più e che un documento di decisione
dice dove è finito il debito: la forma che ADR 0036 §10 usò per ADR 0035 §7. ADR 0036 non si
riscrive. Il pin dei totali passa dalle sue Conseguenze a quelle di questo ADR, man mano che ogni
totale si muove. `docs/STATO.md` §6 legge questa sezione — un pagamento lo registra solo un ADR —
e i debiti datati aperti passano da uno a zero.

## 15. `ELA_USER_NAME` ritirato, e chi agisce è l'identità risolta

ADR 0023 §4: «`responded_by` diventerà un'**identità autenticata** e quel giorno il setting
**sparisce**». Quel giorno è questo (D12, M12.1 dec. N). «Sparisce» ha già una forma in questo
repository, e non è cancellare: con `extra="ignore"` un valore cancellato verrebbe ignorato in
silenzio, e «Una configurazione che smette di funzionare in silenzio lascia chi l'ha scritta
convinto che funzioni ancora (§33)» (ADR 0022 §8). Si rifiuta.

**La lapide, generalizzata.** `RETIRED_SETTINGS` è oggi una tabella di un provider
(`providers/anthropic/settings.py:39`), e il suo validatore conosce una variabile sola: legge la
prima voce (`providers/anthropic/settings.py:101`). `ELA_USER_NAME` vive in `CoreSettings`
(`composition/settings.py:164`), e `composition` importa i provider ma non il contrario. La lapide
diventa **una tabella sola delle variabili ritirate e di ciò che le sostituisce, con un validatore
che le rifiuta tutte**, da qualunque fonte — ambiente, `.env`, argomento — e ogni classe di
settings dichiara ancora il suo campo-lapide, perché il rifiuto copra ogni fonte.

**Dove vive, e perché.** In un modulo nuovo che importa solo la stdlib e pydantic, fuori da
`providers/` e da `composition/`. In `providers/` la tabella di tutta la configurazione resterebbe
dentro un provider, che è la forma di oggi e il suo difetto; in `composition/` le settings dei
provider dovrebbero importare `composition`, che importa i provider: il verso delle dipendenze si
rovescerebbe. Un modulo che non dipende da nessuno dei due può essere importato da entrambi senza
toccare i contratti di `pyproject.toml`: la stessa specie di ragione con cui ADR 0023 §1 disse
perché esiste `composition`.

Variabili ritirate:

| Variabile | Ritirata in | Al suo posto |
|---|---|---|
| `ELA_USER_NAME` | M12.1 | l'identità che il middleware risolve per la chiamata: con il token del Core, `local` |

**Chi prende il suo posto.** `responded_by` (`api/approvals.py:76`) e l'attore di `cancel_task`
(`api/tasks.py:136`) diventano, con le parole di D12, «l'identità che il middleware ha risolto per
quella chiamata, non una costante», letta da `request.state` e non dall'header (regola 47). Lo
stesso vale per l'attore di `DEVICE_ENROLLED` e di `DEVICE_REVOKED`. In M12.1 quelle rotte le
raggiunge solo il token del Core (§4), quindi quell'identità è sempre **`local` — che qui sta per
«l'utente a questa macchina»**, perché chi approva è una persona e non un dispositivo. `ActorKind`
resta `USER`, e l'id è quello di `local`, `LOCAL_DEVICE_ID`: ciò che l'audit guadagna è **da dove**
la risposta è arrivata, risolto e non dichiarato.

Il campo `user_name` esce da `/diagnostics` (`api/system.py:83`, `api/schemas.py:724`) e dalla riga
della CLI (`cli/system.py:58`); la variabile esce da `.env.example` (`:44`) e da `VARIABLES` di
`cli/setup.py`. Impostarla ferma l'avvio con un messaggio che nomina ciò che la sostituisce, e lo
stesso vale ancora per `ELA_ANTHROPIC_MODEL`, che la tabella di ADR 0022 §8 ha ritirato: i test che
leggevano quella tabella leggono l'unione delle due.

## 16. Le regole

Ognuna col suo caso negativo, e scritta **nel commit precedente** a quello che introduce il codice
che difende: «Una difesa scritta dopo la cosa che difende ha una finestra in cui la cosa esiste e
la difesa no» (ADR 0030 §15). La 46, la 47 e la 31 estesa sono nel commit `3337417`, prima del
middleware e delle rotte.

`Regole aggiunte:`

| Regola | Cosa dice | Su | Vale per |
|---|---|---|---|
| 46 `a-nodes-secret-crosses-no-readable-boundary` | i nomi del segreto di un nodo, del suo hash e del codice di enrollment non compaiono dentro un `AuditEvent(...)`, né nelle forme sul filo di `api/schemas.py`; `Device` non ha un campo per l'hash | ogni chiamata ad `AuditEvent` di `ela`; `api/schemas.py`; la classe `Device` | nessuna esenzione oggi: le due risposte che consegnano, una volta, il codice e il segreto la aprono nel commit che le scrive (ADR 0027) |
| 47 `identity-resolved-in-one-place` | nessun modulo di `ela.api` fuori da `api/security.py` legge l'header `authorization`: le rotte leggono l'identità risolta | `ela.api` | nessuna esenzione; muta sull'albero in cui è nata, e il suo silenzio si asserisce |

La 46 è la forma della regola 23 applicata a un valore peggiore di un argomento: un argomento è
contenuto dell'utente, il segreto di un nodo è la chiave per parlare a ELA come una macchina di cui
l'utente si fida — e l'audit è append-only, quindi un segreto scritto lì è scritto per sempre, e
revocare il nodo non lo cancellerebbe. La 47 difende una porta che nessuno ha ancora aperto, e che
D12 apre (§15).

`Regole estese:`

| Regola | Come cambia | Perché |
|---|---|---|
| 31 `constant-time-token` | `TOKEN_NAMES` impara i nomi del segreto di un nodo — `node_secret`, `presented_hash`, `secret_hash` (`tests/architecture/rules.py:415`) — e fuori da `api/security.py` nessun modulo li confronta per valore; `is None` resta permesso ovunque | un solo modulo confronta credenziali, così `SECURITY_MODULE` resta un percorso solo (§6) |
| 44 `a-refresh-touches-only-what-is-declared` | i nomi vietati a `devices/refresh.py` diventano la metà osservata — che comprende `network` e `power_source` — più `privacy`, `revoked_at` e `revision` | il nome dice «a refresh touches only what is declared», ma la regola vietava soltanto la metà osservata (`OBSERVED_FIELDS`, `tests/architecture/rules.py:316`); con la metà imposta e lo stato dell'identità ciò che non è dichiarato cresce, e il costruttore della metà dichiarata diventa anche la strada dell'annuncio remoto (§10) |

L'estensione della 44 entra nel commit che sposta quei campi fuori dalla metà dichiarata, perché
oggi `DECLARED_FIELDS` (`devices/refresh.py:27`) nomina `network` e `privacy`, e una regola che
nasce rossa non difende niente.

## Alternative considerate

- **A1 — un solo indirizzo, sulla tailnet.** Era la raccomandazione; scartata il 2026-09-11:
  legava l'uso locale a un demone di terzi, e senza la tailnet ELA non partiva (§2).
- **A2 — `0.0.0.0` protetto da un firewall.** È l'alternativa che ADR 0023 §7 ha già scartato: un
  firewall è un avviso che vive fuori dal repository.
- **A3 — ELA su loopback, e `tailscale serve` che le inoltra le richieste.** Esclusa da
  `docs/STATO.md` §5.2 («nessuna porta aperta, nessun reverse proxy»); e ogni richiesta arriverebbe
  da `127.0.0.1`, così il presupposto «siamo su loopback» diventerebbe falso senza smettere di
  sembrare vero.
- **mTLS, un certificato client per nodo.** Scartata con D5, quando l'utente ha scelto un segreto
  per nodo con l'enrollment monouso (`docs/milestones/M12.1.md`, D5): taglia fuori l'iPhone, che
  non presenta un certificato client (`docs/STATO.md` §5.1), duplica a livello applicativo ciò che
  WireGuard fa a livello di rete, e vuole una CA locale, revoche, rinnovi.
- **Un token firmato dal Core, HMAC con scadenza** (scartato con D5). È un segreto per
  nodo con più macchinario — formato, claim, deriva d'orologio, rinnovo — e non elimina lo store:
  una revoca vuole comunque una lista.
- **L'identità della tailnet da sola, `whois` sull'indirizzo sorgente** (scartata con D5). È
  un'identità della rete: se un giorno ELA gira senza Tailscale, il protocollo resta senza
  identità e nessuno se ne accorge. Come secondo strato è fuori scope: che cosa arrivi davvero al
  processo non è misurato.
- **Il nodo che porta anche `ELA_API_TOKEN`, e la rotta di enrollment fuori dal middleware.**
  Scartate da D10 (§3).
- **C1 — un'identità di nodo su ogni rotta — e C2 — le rotte dei nodi più le approvazioni.** Con C1
  un segreto rubato vale quanto il token del Core: legge ogni task con gli argomenti, risponde alle
  approvazioni, legge l'audit, revoca gli altri nodi. Con C2 il contenuto dei task resta chiuso, ma
  ogni nodo diventa un portatore del «sì» (§4).
- **Un 403 per una rotta che l'identità presentata non può chiamare.** Distinguerebbe «esisti ma
  no» da «non esisti» (ADR 0023 §7).
- **Il codice scritto in un file, passato come argomento alla CLI del nodo, o copiato negli
  appunti.** Il file va comunque portato sull'altra macchina, e il problema si sposta; l'argomento
  lo vieta ADR 0024 §2; gli appunti sono solo macOS, e con Handoff passano agli altri dispositivi
  Apple dell'utente (§5).
- **Un codice breve, da digitare.** Sotto uno SHA-256 lo inverte chiunque legga il database (§5).
- **Una variabile per la scadenza del codice.** Costerebbe `.env.example`, `VARIABLES` e il test
  che li tiene uguali, senza che nessuno l'abbia chiesta (§5).
- **Restituire lo stesso segreto a un secondo tentativo di enrollment.** Vorrebbe tenerlo in chiaro
  (§5).
- **E2 — HMAC-SHA256 con una chiave del Core.** Protegge da chi legge **solo** il database, ma una
  tabella di SHA-256 di segreti a 256 bit è già non invertibile; aggiunge un secondo segreto, da
  custodire nello stesso `.env` del token (§6).
- **E3 — una derivazione lenta (`hashlib.scrypt`).** Serve a rallentare chi indovina password,
  valori a bassa entropia; il costo lo pagherebbe ogni heartbeat (§6).
- **`*.db-*` in `.gitignore`.** Ignorerebbe cose che nessuno ha nominato (§7).
- **G1 — l'hash come campo di `Device`.** L'entità viaggia ovunque — i DTO, il sommario col diff di
  `DEVICE_REFRESHED`, l'orchestratore, il Context Core — e un campo che esiste è un campo che può
  uscire (§8).
- **G3 — un port delle credenziali che tiene hash, revoca e codici, lontano dalla riga.** Per
  giudicare un nodo revocato l'orchestratore leggerebbe due port, e i due potrebbero dire cose
  diverse (§8).
- **H1 — tutto da un `update` condizionale sulla revisione.** Un heartbeat che incrocia un annuncio
  fallirebbe, e il fallimento sembrerebbe un conflitto di identità: un falso positivo dell'evento
  che deve voler dire «due processi dicono di essere me» (§9).
- **H3 — com'è oggi.** L'annuncio concorrente a un heartbeat si perde (§9).
- **`network` dichiarata dal nodo.** Un nodo che si dichiarasse `LOCAL` si prenderebbe i punti di
  questa macchina (§10).
- **Un filtro sui nodi remoti — la J3 della terza stesura, l'`OUT_OF_PROCESS` della quarta.**
  Tolto da D19: un membro del vocabolario chiuso che vive una milestone e poi sparisce è rumore
  nella catena degli ADR, e un filtro che restringesse i candidati prima dei rifiuti toglierebbe a
  `REVOKED` il suo percorso di produzione (§11).
- **K2 — il nodo revocato fuori dai candidati.** È la forma che D13 dice falsa (§12).
- **Cancellare la riga di un nodo revocato.** Lascerebbe nell'audit `device_id` che non puntano a
  niente (ADR 0016 §6).
- **`available()` invariato, e una forma sola, `REVOKED`.** Era la raccomandazione; scartata
  dall'utente: un nodo revocato disponibile per un TTL è una diagnosi falsa. **La condizione anche
  in `seen()`**: diagnosticherebbe `UNAVAILABLE` un nodo con l'heartbeat fresco (§12).
- **Riusare `DEVICE_REGISTERED` e `DEVICE_REFRESHED` con un altro attore.** ADR 0035 §3 li intesta
  a `SYSTEM`, e il suo test rifiuta proprio `DEVICE` (§13).
- **`DEVICE` come attore di `DEVICE_REJECTED`.** Attribuirebbe un'azione proprio all'identità che
  non è riuscita a provarsi (§13).
- **Ogni 401 nell'audit.** Qualunque macchina della tailnet riempirebbe la catena di §32 a
  comando. **Un log per i rifiuti anonimi**: nessun modulo di `src/ela` usa `logging`, e aprirne uno
  sarebbe una superficie nuova (§13).
- **Cancellare `ELA_USER_NAME` dalle settings.** Con `extra="ignore"` un valore rimasto in un `.env`
  verrebbe ignorato in silenzio (§15).

## Conseguenze

- Una macchina che non è questa si arruola con un id che non ha scelto e una `privacy` che non ha
  scritto, manda heartbeat, compare in `GET /devices` e non riceve lavoro; revocata, riceve lo
  stesso 401 di un segreto sbagliato, e l'orchestratore la dice `REVOKED`.
- ELA ascolta su loopback e, se la tailnet c'è, anche lì: un server, due socket, un middleware.
  Senza la tailnet l'uso locale non cambia.
- Le regole di architettura passano da quarantacinque a **quarantasette**, e due sono estese: la 31
  e la 44.
- I port passano da ventitré a **ventiquattro**: `EnrollmentStore`.
- Le rotte dell'API passano da venti a **venticinque**, e i percorsi serviti, `/openapi.json`
  compreso, da ventuno a ventisei. I comandi della CLI contati da `coded_commands()` passano da 23
  a 25; in `docs/STATO.md`, che conta i comandi registrati, da 22 a 24.
- I tipi di evento dell'audit passano da ventisette a **trenta**: due escono, cinque entrano, e
  nessuno resta senza scrittore. `ActorKind.DEVICE` ha il suo primo scrittore.
- `Refusal` passa da cinque a sei membri: le righe F1–F5 restano in ADR 0017 §4, la F6 sta qui.
- Le capability di produzione restano otto: in M12.1 nessuna capability viaggia.
- La migrazione `0008` aggiunge tre colonne a `devices` e la tabella `enrollments`: le tabelle
  passano da otto a nove.
- `ELA_USER_NAME` ferma l'avvio invece di firmare le approvazioni, e `user_name` esce da
  `/diagnostics`; l'attore di chi risponde e di chi cancella è l'identità risolta.
- `ela.db-wal` ed `ela.db-shm` sono ignorati come il database, e `.env` nasce `0o600`.
- Il debito datato di ADR 0036 §12 è chiuso (§14), e nessun debito datato resta aperto.
- I vincoli dichiarati negli ADR passano da 118 a 134, e gli ADR che ne dichiarano vanno da `0020`
  a `0037`.
- Il criterio 8 di M12.1 — un nodo remoto non riceve mai lavoro — ha una scadenza scritta: lo
  ritira M12.2, nel commit che introduce la sensibilità del task.

### Vincoli dichiarati, da riaprire quando serviranno

- **Un segreto per nodo, senza rotazione**: ruotare è revocare e riarruolare.
- **Un nodo remoto non riceve lavoro fino a M12.2**: lo tengono D18 e `PRIVACY` (D19), e lo ritira
  il commit di M12.2 che introduce la sensibilità del task.
- **Senza la tailnet ELA ascolta sul solo loopback, e `/diagnostics` lo dice**: se all'avvio
  l'indirizzo della tailnet non esiste, l'uso locale funziona e un nodo non raggiunge ELA (§2).
- **Il token del Core resta uno, statico, in un file — ora raggiungibile dalla tailnet**: ADR 0023
  lo dichiarava con «loopback, un'identità, nessun TLS»; nessun nodo lo porta (D10), ma il socket
  della tailnet serve lo stesso middleware di quello di loopback (§2).
- **Due cloni che mandano solo heartbeat non si vedono**: la revisione sta sulla metà dichiarata
  (§9).
- **Un enrollment la cui risposta si perde lascia una riga orfana**, mai vista: l'utente la vede in
  `GET /devices` e la revoca. Restituire lo stesso segreto vorrebbe tenerlo in chiaro (§5).
- **I rifiuti anonimi si contano in `/diagnostics`, non entrano nella catena, e il contatore si azzera a ogni avvio**:
  vive nella memoria del processo (§13).
- **Nessun limite ai tentativi** sulle rotte autenticate: un segreto di 256 bit non si indovina
  (§2, §6).
- **Il tempo di risposta distingue un id sconosciuto da un segreto sbagliato**: rivela se un UUID
  esiste, cosa che nessuno può indovinare in anticipo (§6).
- **Ciò che il nodo riporta di sé resta la sua parola, anche quando lo scrive il registro**:
  «osservata» vuol dire scritta dal registro, non vera — `status`, `current_workload`,
  `power_source` (D3, §10).
- **Il nodo `local` resta fuori dalla revisione**: ADR 0035 §5 lo lascia oscillare, e metterlo sotto
  la revisione è una decisione su `local` (§9).
- **Il codice di enrollment passa per il terminale**: stampato una volta, monouso, con una scadenza
  breve; il segreto durevole non si stampa mai (§5).
- **Dove un nodo tiene il segreto non lo verifica il Core**: non passa per HTTP, e la suite di
  conformità di M12.2 non potrà verificarlo; ognuna di M12.3–M12.5 risponde con una misura (§7).
- **La disponibilità osservata di un nodo revocato resta quella del suo heartbeat: la revoca la dice `REVOKED`**:
  `available()` lo esclude subito, ma `seen()` resta il fatto dell'heartbeat, perché la diagnosi
  `UNAVAILABLE` dice «nessun heartbeat» (§12).
- **`local` sta per l'utente a questa macchina**: chi approva è una persona e non un dispositivo, e
  in M12.1 le rotte delle approvazioni e della cancellazione le raggiunge solo il token del Core
  (§15).
- **`MISSING_TRAIT` non entra finché nessun percorso di produzione può produrlo**: la condizione
  d'ingresso di D9, con le sue parole — la derivazione da `activates_sensor` resta come dato; il
  giorno in cui entra, `local` dichiara il microfono in base al codice, la difesa vera è il
  preflight nell'istante (M11.2 dec. H), e il filtro su `local` va detto vacuo (ADR 0026 §7).
