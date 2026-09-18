# 0041. La suite in parallelo: `-n auto` con gli stessi gate, un test che non condivide niente con un altro, il controllo Linux sulla CI, e il debito della suite che aspetta

- **Stato:** Accettata
- **Data:** 2026-09-18
- **Riferimenti spec:** §48, §51, §53
- **Milestone:** nessuna — una sessione sulla velocità della suite, sul branch `suite-speed`, con le
  decisioni dell'utente del 2026-09-18.
- **Continua:** il commit `f613363` del 2026-09-12 («una esecuzione sola, due gate»), che non ha un
  ADR e il cui commento nel `Makefile` è il precedente di questo; ADR 0031 §6 (un test afferma solo
  ciò di cui ha costruito le precondizioni); ADR 0035 §7 (la forma di un debito datato).

## Contesto

`make check` durava **294 s** di orologio, e la suite ne prendeva **279,9**: il 95%. Misurato il
2026-09-18 su questo Mac (10 core) con l'alimentatore attaccato, con `--durations=0` perché la
misura dicesse anche dove va il tempo — 2709 righe, 266 s dei 279,9:

| Dove | Quanto |
|---|---|
| `tests/architecture/` | **94 s** — `test_rules_detect_violations.py` 57 s, `test_exemptions.py` 28 s, `test_layers.py` 8 s |
| i property test (hypothesis), 17 file | 47 s |
| i 15 file che lanciano sottoprocessi | 25 s — metà è `tests/cli/test_no_colour.py`, che rilancia la suite della CLI |
| `tests/conformance/test_node_contract.py` | 25 s — un Core vero su un database vero per ogni storia; l'orologio è un `FakeClock` |
| gli sleep veri | circa 8 s (§5) |

Fuori dalla suite pesavano solo `detect-secrets` (12 s); ruff, import-linter, mypy, il gate critico
e il controllo delle milestone stavano sotto il secondo ciascuno. Il tempo di CPU (231 s di user)
era **meno** di quello d'orologio: la suite passava parte del tempo ad aspettare, su un core solo.

Il precedente del 2026-09-12 aveva tolto la seconda esecuzione della suite a parità di severità, e
l'aveva provato con i numeri: il totale del gate non era cambiato di una riga. Questo ADR fa la
stessa cosa con i core.

## 1. La suite gira in parallelo, e i gate non cambiano

`pytest-xdist` entra fra le dipendenze di sviluppo, e **`-n auto` entra in `addopts`**, così vale
per `make check`, per `make check-linux` e per la CI senza che nessuno debba ricordarselo. La
copertura resta misurata da pytest-cov, che con xdist ricompone da solo la misura dei worker nello
stesso `.coverage` che il gate critico legge.

| | Prima | Dopo, due giri |
|---|---|---|
| `make check`, orologio | 294 s | 87 s / 93 s |
| la suite | 279,9 s | 73,3 s / 79,6 s |
| CPU (user) | 231 s | 550 s / 573 s |
| test | 6451 passati, 4 saltati | 6451 passati, 4 saltati |
| tutto `ela` | 10702 stmt (347 mancanti), 1786 branch (2 parziali) | identico |
| **il gate critico** | **8002 stmt, 1428 branch, 0 mancanti** | **identico** |

**La prova che la severità è la stessa** è quella del precedente: stessi test, stessi skip, e il
totale del gate critico identico prima e dopo, statement e branch. `make check-linux` dà gli stessi
6431 passati e 24 saltati del giro seriale, con gli stessi totali: i 24 skip invece dei 4 provano
che il plugin `-p tests.foreign_machine` arriva nei worker, perché senza di lui la macchina finta
non ci sarebbe. Il comando del job Windows (`tests/node`, `tests/conformance`,
`tests/composition/test_build_node.py`) gira anch'esso in parallelo: 160 passati in 6,4 s, contro
22,2 s con `-n0`.

## 2. Il negativo del gate critico si misura come la suite

`tests/scripts/test_coverage_gates.py` prova che un branch non preso rende rosso il gate leggendo
un file di dati condiviso, su un progetto usa-e-getta misurato «exactly as `make test` measures
ela». Da oggi `make test` misura attraverso i worker, e quella frase sarebbe stata letteralmente
falsa: un criterio falso si corregge, non si lascia perché benigno. Il progetto usa-e-getta ha ora
due file di test, gira con **`-n 2`**, e la fixture **controlla** di essere passata dai worker
(«2 workers [2 items]») invece di assumerlo. Il gate su `app/spare` resta rosso e quello su
`app/measured` verde, con i dati ricomposti.

## 3. Un test non condivide niente con un altro

In parallelo, due test che usano lo stesso file SQLite, la stessa porta o la stessa cartella di
stato si pestano i piedi. **È un difetto d'isolamento del test, e si ripara nel test** — `tmp_path`,
la porta 0, `monkeypatch` per l'ambiente e per la cartella di lavoro —; **i test non si mettono in
fila**. Se una collisione non si può riparare nella sessione che la trova, si dichiara con il motivo.

Il 2026-09-18 non ne è comparsa nessuna: quattro giri paralleli verdi (`make check` due volte,
`make check-linux`, il comando del job Windows), e la lettura della suite non ne mostra — nessuna
porta fissa, `chdir` e variabili d'ambiente sempre attraverso `monkeypatch`, i file in `tmp_path`.
**È un'assenza osservata, non dimostrata**: xdist distribuisce i test in modo dinamico, e un giro
diverso può metterne vicini due che oggi non lo sono stati. La difesa è il parallelo stesso: una
collisione si presenta come un test rosso.

## 4. Il controllo Linux è la CI sul branch

`make check-linux` prima di ogni push nasceva dal 2026-09-08, quando la CI si è accorta di una suite
che ereditava la macchina undici minuti **dopo** il merge. Da oggi il merge esige la CI verde su
entrambi i runner all'ultimo commit del branch, e quel controllo lo fa una macchina Linux vera
invece di un Mac che ne finge due cose. `make check-linux` resta, per **riprodurre in locale una CI
rossa su ubuntu**.

E `make check` si lancia **una volta, alla fine della milestone, prima del riepilogo**; durante il
lavoro girano solo i test del pezzo che si tocca. Su un file solo il parallelo costa poco (1,4 s
contro 0,8 s con `-n0`), quindi non serve spegnerlo per lavorare. Le regole sono in `CLAUDE.md`, e
`docs/STATO.md`, il commento di `check-linux` nel `Makefile` e `tests/foreign_machine.py` dicono la
stessa cosa.

## 5. Un debito datato: i test che aspettano, e le difese che costano un terzo della suite

Le durate della misura di base dicono due cose che questa sessione non ripara.

**I test che aspettano una durata invece di un evento** — circa 8 s in tutto:

| Test | Durata | Che cosa aspetta |
|---|---|---|
| `tests/infrastructure/machine/test_spawn.py`, i tre test sulla cancellazione (`test_a_cancelled_wait_kills_the_child_instead_of_orphaning_it`, `test_a_cancelled_wait_on_a_child_fed_on_stdin_kills_it`, `test_a_cancelled_playback_kills_the_child_and_frees_the_audio`) | 1,06 s l'uno | `asyncio.sleep(0.15)` perché il figlio esista, poi `asyncio.sleep(0.9)` oltre l'istante in cui avrebbe scritto, e un figlio che dorme 0,6 s |
| `tests/infrastructure/machine/test_microphone_smoke.py::test_a_cancelled_call_closes_the_microphone` (solo macOS) | 2,14 s | `asyncio.sleep(1.5)` perché il registratore giri, `asyncio.sleep(0.5)` perché si chiuda |
| `tests/infrastructure/machine/test_microphone_smoke.py::test_the_child_carries_its_own_deadline_and_outlives_nobody` (solo macOS) | 1,64 s | `time.sleep(0.2)` a giri, finché il figlio non chiude alla sua scadenza di un secondo |
| `tests/perception/test_core.py::test_the_loop_keeps_ticking_until_it_is_cancelled` | 1,00 s | aspetta l'evento, ma il ciclo batte ogni secondo di tempo vero (`perception_loop_interval_seconds=1`) e non ha un orologio iniettato |
| `tests/api/test_server.py::test_a_stop_wakes_the_node_that_waits` | 0,08 s | `asyncio.sleep(0.05)` perché la richiesta sia in volo |

Restano fuori, perché la lentezza è ciò che provano: i `sleep(0)` che cedono il turno, i timeout da
0,05 s di `test_spawn.py`, e lo `SlowEcho` di `tests/node/support.py` — un rinnovo avviene solo
mentre un tool sta ancora girando. `test_microphone_smoke.py` è già a carico della stessa milestone
per un'altra ragione (ADR 0038: afferma i numeri di una registrazione senza costruirne la
precondizione). La riparazione è un evento o un orologio iniettato, **non una durata più corta**: si
aspetta l'evento, mai una durata (ADR 0006 §13).

**I test di architettura: 94 s su 279,9**, un terzo della suite —
`tests/architecture/test_rules_detect_violations.py` 57 s, `test_exemptions.py` 28 s,
`test_layers.py` 8 s. Non erano fra i sospettati, e non sono stati indagati.

**La cautela, scritta con il debito:** sono le difese del repository. Prima si misura dove va il
tempo dentro quei file, e la riparazione non toglie un caso — se un giorno costano 10 s, coprono
ancora ogni regola e ogni esenzione.

**Debito a carico della milestone sulla disciplina della suite**, dichiarato il **2026-09-18**,
accanto a ciò che ADR 0035 §7 (pagato da ADR 0036 §10) e ADR 0038 le hanno già messo a carico.

La difesa è la più piccola possibile, nella forma di ADR 0035 §7: `tests/docs/test_adr_parallel.py`
verifica che le attese elencate qui sopra siano ancora nei loro file. Il giorno in cui qualcuno le
ripara, quel test fallisce: il pagamento si scrive in un ADR, e il test si gira, come per ADR 0035
§7 in M11.2. La metà sui test di architettura non ha una difesa che non sia un cronometro, e un
cronometro dentro un test è la cosa che questo debito vuole togliere: la tiene `docs/STATO.md` §6,
dove il debito resta aperto finché un ADR non lo salda.

## Alternative considerate

- **Mettere in fila i test che si pestano i piedi** (un gruppo xdist, o `-n0` per un file) —
  scartata: nasconde un difetto d'isolamento invece di ripararlo, e la fila cresce a ogni
  collisione che nessuno ripara (§3).
- **Un numero fisso di worker** — scartata: il Mac e i runner hanno core diversi, e un numero giusto
  su una macchina è sbagliato sull'altra. `-n auto` chiede alla macchina.
- **Togliere o ridurre i property test e i test di architettura** — scartata: la condizione era la
  stessa severità, e il debito di §5 dice come si riparano senza togliere un caso.
- **Tenere `make check-linux` prima di ogni push** — scartata: la CI fa la stessa domanda a una
  macchina Linux vera, e il merge la esige verde; `make check-linux` finge soltanto
  `platform.system()` e i binari di Apple (§4).

## Conseguenze

- **Il guadagno è d'orologio, non di lavoro.** La CPU più che raddoppia (da 231 s a 550–573 s di
  user): ogni worker importa e raccoglie la suite per conto suo.
- **Ogni test nuovo deve reggere il parallelo** (§3), e una collisione si ripara nel test.
- **`tests/cli/test_no_colour.py` rilancia la suite della CLI**, e con `addopts` la rilancia anch'essa
  in parallelo, dentro il parallelo di fuori: funziona, e la CPU contesa è accettata.
- **I numeri di questo ADR sono una misura datata**, non i totali di oggi: la suite crescerà, e il
  commento del `Makefile` porta la stessa misura con la sua data.
- **La difesa** del debito di §5 è `tests/docs/test_adr_parallel.py`, che verifica anche che
  `addopts` e le dipendenze di sviluppo dicano ciò che dice §1.
