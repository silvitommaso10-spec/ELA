# 0069. La disciplina della suite: un posto solo per gli skip, i test che aspettano un evento, e il costo di un binario vero

- **Stato:** **Proposta** il **2026-11-17**, con l'implementazione di M9.5 sul branch `m9.5-la-pulizia-della-suite`
  (`docs/milestones/M9.5.md`, la SPEC e la review delle tre SPEC a `ad1826c`, decisioni 56–81), per diventare Accettata
  con un commit suo dopo la prova a mano della sezione 33 di `docs/GETTING_STARTED.md` sull'ultimo commit del branch
  (decisione 81). **Le «Righe riviste» che questo ADR porta sono scritte**, con il marchio sulla riga «Stato:»
  degli ADR che rivede — ADR 0052 e ADR 0063.
- **Data:** 2026-11-17
- **Riferimenti spec:** §48, §51, §53
- **Milestone:** [M9.5](../milestones/M9.5.md)
- **Continua:** ADR 0031 §6 (un test afferma solo ciò di cui ha costruito le precondizioni), ADR 0035 §7 (la forma di
  un debito datato), ADR 0006 §13 (si aspetta un evento, mai una durata), ADR 0026 §6 (un tetto di tempo in un test
  misura la macchina). **Paga** ADR 0047 §18 e ADR 0041 §5; **rivede** come si applica la soglia di ADR 0052 §16 (§3); **ridichiara** il
  debito di ADR 0063 §12, a carico di M13.11 (§4).

## Contesto

Dal 2026-09-09 più di un documento metteva qualcosa «a carico della milestone sulla disciplina della suite», e M9.5 è
quella milestone: **le liste che si accorgono di essere false**. Tre debiti datati le erano a carico — ADR 0047 §18 (gli
skip sul sistema che il test copre, che nessuno vede), ADR 0041 §5 (i test che aspettano, e le difese che costano un
terzo della suite), ADR 0063 §12 (il costo dei test di M13.9, sopra la soglia) —, e le voci che il suo documento
eredita per nome. I censimenti, le misure e le regole scritte prima dei numeri stanno nel documento della milestone; le
uscite intere in `.git/m9.5-reference/`. **Il taglio è deciso** (decisione 56): ciò che M9.5 non salda in questa
sessione è un debito nuovo, a carico di M9.8 (§5).

## Decisione

### 1. Il debito di ADR 0047 §18, saldato: un posto solo per gli skip, e la guardia

**Il posto solo è `tests/machines.py`.** Ogni condizione che legge la macchina — il sistema, il kernel, un programma,
il binario di Claude Code della wheel, la storia di `main`, l'utente che i bit di un modo vincolano, il volume che non
distingue le maiuscole, un runner della CI, il permesso di Registrazione dello schermo, un ingresso audio che si apre,
il browser del profilo — è lì, con un nome, **una lettura** — fatta una volta in un processo, e solo quando un test che
ne ha bisogno sta per girare: due costano, una chiede un permesso a macOS — e **dove deve valere, per dichiarazione**.
Dove il prodotto ha già la condizione, la lettura è del prodotto: `account.SUPPORTED`, `bundled_binary`, il registratore
di ELA, la sonda dei permessi. Un test dice di che cosa ha bisogno con `needs(...)`, mai con uno `skipif` suo.

**La guardia** è l'hook `pytest_runtest_setup` di `tests/conftest.py`, prima di ogni altra parte del set-up: dove manca
una condizione che lì **non** deve valere, il test è saltato con la ragione nel riepilogo; dove ne manca una che lì
**deve** valere, **il test è rosso**, e dice che cosa manca e dove doveva esserci. La decisione è una funzione pura,
`decision`, con i suoi casi negativi in `tests/test_machines.py`, che non si salta mai; **ogni dichiarazione è
esercitata da quella funzione nei due valori** della sua lettura, sulle tre macchine della CI. La guardia di
`tests/tools/test_terminal_limits.py`, il modello del debito, e le due copie che `test_agent_session.py` ne aveva fatto,
**sono tolte**: la guardia è l'hook, per ogni test.

**E le due guardie simili non ci sono più** (decisione 95 della review a `42bac98`):
`test_on_the_runners_the_permissions_bite` — il file `tests/tools/test_permissions_bite.py` — e
`test_on_a_mac_the_two_spellings_are_one_folder_and_the_test_above_ran`. Dicevano una volta, da sole, ciò che la guardia
dice per ogni test che ha bisogno di `PERMISSIONS_BITE` o di `IGNORES_CASE`: **una guardia sola**. Prima di toglierle,
un mutante per ciascuna — la lettura che risponde «manca» dove la condizione deve valere —: la guardia ha fatto rossi
gli undici test che prendono `PERMISSIONS_BITE`, sotto `GITHUB_ACTIONS=true`, e i cinque che prendono `IGNORES_CASE`, su
questo Mac (`.git/m9.5-reference/guardie-95/mutanti-95.txt`); per ogni dichiarazione lo prova la funzione pura,
`test_every_declaration_is_exercised_in_both_values_on_the_machines_of_the_ci` di `tests/test_machines.py`. Con loro è
tolta `ON_A_RUNNER`, la condizione che solo la prima prendeva. Le liste dei saltati cambiano per una riga sola, detta
prima: `test_permissions_bite.py`, che fuori da un runner era saltato.

**Che cosa vuol dire «la macchina» quando è finta.** Ogni condizione si confronta con la macchina nella stessa lettura
con cui scatta: una condizione sul sistema legge `platform.system()`, che `-p tests.foreign_machine` finge; una sul
kernel legge `sys.platform` o `/proc`, che non finge. La guardia non ha un'idea della macchina sua.

**Le condizioni dell'utente** (decisione 65): sui job della CI un test saltato perché chi esegue è root è un rosso;
altrove è ciò che il test copre, con la ragione nello skip. La sessione cloud come root resta quella che `CLAUDE.md`
tratta a parte.

**La regola a mondo chiuso** (`tests/architecture/test_skips_are_written_in_one_place.py`): fuori da `tests/machines.py`
nessuno scrive `pytest.mark.skipif`, `pytest.mark.skip`, `pytest.mark.xfail`, `pytest.skip`, `pytest.importorskip`,
`pytest.xfail` — per esclusione, qualunque cosa legga —, con il caso negativo su una suite costruita lì. **Due
esenzioni, ciascuna una condizione e non un elenco, ciascuna provata necessaria** — tolta, la regola parla (decisione
68): le storie che un kit della conformance dichiara di non poter recitare (la condizione è `kit.unsupported`, non il
file), e i controlli fermi della misura di M13.9, finché il test che ne tiene lo sha256 lo tiene.

**Un test che non gira su nessun job della CI è rosso ovunque**, salvo che un posto dichiarato dica perché: il calcolo
legge dalle dichiarazioni i job che lo raccolgono e dove tutte le sue condizioni devono valere — la riga del job di
Windows da `.github/workflows/ci.yml` —, e i posti dichiarati sono `tests/windows.py` e la ragione `nowhere` di una
condizione. Oggi un test solo non gira su nessun job, `test_sapi_smoke.py`, e la sua ragione è in `tests/windows.py`.

**Il browser del profilo** (decisione 64): `tests/profile_browser.py` è un cliente del posto solo e tiene i suoi due
versi (`built_through_the_fixture` e `NEVER_BUILT`); i 165 test passano tutti dal posto solo, e nessuno porta la
marca due volte (misurato: 165, 0 doppi). Il modulo di `test_account_browser.py` non ha più una marca sua: il test del
registro, che non costruisce il browser, gira su ubuntu e sotto `make check-linux` (decisione 66).

**Il test che lo difendeva si è girato**:
`tests/docs/test_adr_terminal.py::test_the_watch_on_skips_is_the_guard_of_the_one_place`.

### 2. Il debito di ADR 0041 §5, saldato: le cinque attese, e i test di architettura

**Le cinque attese**, una per una, con ciò che sono:

- **i tre test di `test_spawn.py` sulla cancellazione** aspettano un evento: il figlio scrive il suo pid per prima cosa
  e non finisce mai da sé; dopo che la cancellazione è risalita — il lanciatore uccide e raccoglie prima di rialzarla —
  il pid non c'è più. Né un lanciatore che rialzasse senza uccidere né uno che aspettasse la fine del figlio passano;
- **`test_a_cancelled_call_closes_the_microphone`** trova il registratore **per parentela** — il figlio che la chiamata
  ha avviato, con il suo istante di partenza — e non per nome fra tutti i processi della macchina: un processo
  qualunque con il nome del modulo lo faceva rosso (misurato il 2026-11-14); «si chiude» è un fatto quando la
  cancellazione è risalita. **Afferma che il registratore non c'è più, non chi l'ha ucciso** — asyncio uccide il figlio
  di una chiamata rilasciata —: **la kill del lanciatore la tengono i tre test di `test_spawn.py`**, che il mutante «rialza
  senza uccidere» lo prendono (decisione 91 della review a `42bac98`);
- **`test_the_child_carries_its_own_deadline_and_outlives_nobody` non era un'attesa che decide** (decisione 69): il
  ciclo aspettava l'evento, l'uscita del figlio, e ciò che costa tempo è la scadenza del figlio, che è il soggetto. Ora
  `child.wait`, lo stesso evento senza cadenza;
- **`test_the_loop_keeps_ticking_until_it_is_cancelled` resta una cadenza, con la ragione accanto**: il verdetto non
  dipende dalla durata — il test aspetta l'evento, due letture —, `PerceptionCore` non prende un sonno, e una giuntura
  in `src/` non è la riparazione di una causa misurata (decisione 25). **Il pagamento lo dice apertamente**: il secondo
  di tempo vero resta;
- **`test_a_stop_wakes_the_node_that_waits`** afferma ciò che il gestore ha fatto, non quanto ci ha messo: `_taken` di
  `ela/api/nodes.py` è avvolto con `monkeypatch.setattr` sul nome — un nome cambiato è un rosso —, chiamando quello vero;
  la prima lettura è l'evento «in volo», e dopo la fermata il gestore legge una volta sola e risponde. Il cronometro
  «< window / 2» è tolto (ADR 0026 §6).

**`SlowEcho` di `tests/node/support.py`**, che §5 lasciava fuori «perché la lentezza è ciò che prova», **qui si legge
in un altro modo** (decisione 70): i suoi 0,05 s costruiscono la precondizione «il tool gira ancora», ed è una delle
attese del debito nuovo di M9.8 (§5).

**I test di architettura** (la metà di §5, con la sua cautela): misurati prima — `test_violation_is_reported` da solo,
87,46 s, di cui `ast.walk` 44,7 e `ast.parse` 18,3: il tempo va nel leggere, non nel decidere —, e riparati dentro la
regola (ii): **un albero si legge una volta per il suo contenuto**, `parsed` e `walked` di `tests/architecture/rules.py`,
una strada sola per tutte le regole (decisione 77). La chiave è il contenuto, mai il percorso: un caso che cambia un
file ha un testo suo, e un albero suo; il caso negativo — lo stesso percorso, il contenuto cambiato, e la regola vede il
cambiamento — è in `tests/architecture/test_the_trees_are_read_for_their_content.py`. Prima, il censimento delle
scritture sugli alberi: due, tutte e due in un dizionario della regola. `test_every_audit_event_type_has_a_writer`, che
la registrazione eredita per nome, legge i nomi d'attributo di ogni modulo una volta per processo. **Nessun caso è
tolto**: gli id raccolti prima e dopo sono gli stessi, confrontati come liste, e i casi che sono i mutanti delle regole
muoiono ancora. I numeri di prima sono nel documento della milestone. **Dopo**, nei due giri del «dopo» a
`05f8675` (§4): i test di architettura pesano 186,24 s e 210,37 s di lavoro, il **9,00 %** e il **7,61 %** del tempo dei
test, contro 772,15 s e 894,91 s, il 29,02 % e il 29,52 %, a `8220b20`. Il dopo conta anche la regola nuova degli skip.
`test_violation_is_reported` scende da 243,05 s a 52,79 s (`.git/m9.5-reference/tempo/quota-giri-dopo-1-2.txt`).

**Il test che lo difendeva si è girato**:
`tests/docs/test_adr_parallel.py::test_the_tests_that_waited_wait_for_an_event_or_say_why`.

### 3. La soglia di ADR 0052 §16 per una milestone che porta un binario vero: due volte il 10 %

**Rivede come si applica la soglia di ADR 0052 §16**, apertamente (decisione 79). Per una milestone che porta un
binario vero — un programma che i suoi test lanciano, che nessun finto porta —, **la soglia del 10 % vale due volte**:
per la parte dei suoi test che non lancia il binario, e per la parte che lo lancia, **ciascuna misurata dentro il giro
all'ultimo commit della milestone**, nelle condizioni di ADR 0052 §16, con i numeri nell'ADR della milestone.

**«Lancia un binario vero» si deriva, non si elenca**: un test è del binario se prende una condizione o una fixture del
posto solo che nomina un binario vero lanciato — `PROFILE_BROWSER`, `CLAUDE_CODE`, con `binary=True` in
`tests/machines.py`, e la marca che la raccolta mette dove un test prende il browser del profilo —; `of_a_binary` lo
dice dalle marche, mai da un elenco di file. **Vale per le milestone future, prima dei loro numeri.**

### 4. Un debito datato: il debito di ADR 0063 §12, ridichiarato — la parte di M13.9 senza binario, sopra la soglia

**Debito a carico di M13.11, la milestone del browser sul PC**, dichiarato il **2026-11-17**, dai due giri del «dopo»
di M9.5, con la regola di §3 (decisione 79 della review a `ad1826c`, decisione 93 della review a `42bac98`). **Una parte
di M13.9 sta sopra il 10 %, e la regola dice che allora il debito non è pagato: passa di mano.**

**La misura.** Due giri di `make check` con `--durations=0 --durations-min=0` a `05f8675`, nelle condizioni della misura
di M9.5 (`.git/m9.5-reference/tempo/`: `conditions.py`, `run_make_check.py`; `giro-dopo-1-run.txt` e
`giro-dopo-2-run.txt`, tutti e due «CONTA»). Il secondo giro è partito al secondo tentativo, quando le condizioni sono
tornate: la prima volta un processo del sistema stava sopra il 25 % di un core (`giro-dopo-2-nota.txt`). **Gli id di
M13.9** sono quelli del giro conforme del 13 ottobre, attribuiti da git (`by_milestone.py`), letti dal lato largo; dei
1195, oggi se ne raccolgono 1183. **Del binario o no** lo dicono le marche (`of_a_binary`, §3): 35 sono del binario — i
test del browser del profilo, in `test_account_browser.py` e `test_account_login.py`. **La parte c, contata per
milestone** (`conta_costruzioni.py`): delle 1598 costruzioni del Core della suite, 260 sono dei test di M13.9 — già nel
loro tempo — e 1338 degli altri. Ognuna di queste paga il ritardo misurato il 13 ottobre, +3,20 ms, e in più ci sono undici
import a +4,39 ms: **c = 4,33 s**, tutto sulla parte senza binario. **`detect-secrets` è fuori**, con la sua ragione
(decisione 78): legge ogni file che git conosce. Riletto qui, come la decisione chiedeva: **30,85 s** (17,14 s il
30 settembre, 30,20 s il 14 novembre). I numeri interi sono in `m13.9-dopo.txt`.

| Giro | `make check` | Del binario | Senza binario, con c | M13.9 in una parte |
|---|---|---|---|---|
| 1 | 357,31 s | 10,43 s — **3,32 %** | 32,85 s — **10,46 %** | 43,28 s — 13,78 % |
| 2 | 423,93 s | 13,54 s — **3,63 %** | 37,74 s — **10,13 %** | 51,28 s — 13,76 % |

Le percentuali sono quelle della soglia: «sopra un `make check` senza M13.9» (ADR 0052 §16). Come quota del giro, la
parte senza binario è il 9,19 % e l'8,90 %. Con il rapporto della copertura intero sulla stessa parte, la lettura più
larga, è il 10,66 % e il 10,29 %.

**Che cosa decide.** **La parte c**: senza di lei la parte senza binario starebbe all'8,96 % e all'8,86 %. Il ritardo di
+3,20 ms a costruzione è di tutto il branch misurato il 13 ottobre, M13.4b–M13.9, e qui è contato tutto su M13.9: è il
lato largo che ADR 0052 §16 prescrive. Quanto di quel ritardo sia di M13.9 non è misurato, e oggi non si può misurare:
non c'è un albero «senza la sola M13.9». Perché la parte stesse sotto nei due giri, il ritardo di M13.9 dovrebbe essere
sotto i 2,22 ms a costruzione. **E il denominatore**: la riparazione dei test di architettura (§2) ha tolto agli altri
test più di quanto il debito pesasse — il tempo dei test è sceso da 2660,74 s a 2068,64 s di lavoro —, e la quota di
M13.9 è salita senza che nessuno toccasse i suoi test. È ciò che la SPEC di M9.5 aveva previsto: «togliere tempo agli
altri lo peggiora».

**Dove pesa** (`m13.9-dopo-per-file.txt`): `test_account_window.py`, `test_console_browser.py`,
`test_browser_routes.py`, `tests/api/test_vault.py`, `test_no_password_anywhere.py` e
`tests/infrastructure/machine/test_vault.py`, ciascuno fra lo 0,5 e l'1,1 % del tempo dei test; poi la parte c.

**Lo paga M13.11, con la stessa regola**: i due giri del «dopo» al suo ultimo commit, nelle condizioni, con le due parti
lette così. Se stanno sotto il 10 % è pagato. Se no, la milestone si ferma e lo dice, con i numeri.

**La difesa più piccola**:
`tests/docs/test_adr_accounts.py::test_the_debt_of_the_cost_changes_hands_with_its_numbers_and_who_inherits_it_says_so`
tiene questa sezione nella forma che `docs/STATO.md` legge, con i suoi numeri, e tiene che M13.11 la nomini fra ciò che
eredita.

### 5. Un debito datato: le attese che nessun elenco conosceva

**Debito a carico di M9.8**, dichiarato il **2026-11-17**, dal taglio di M9.5 (decisione 56 della review a `ad1826c`).

Il censimento di tutte le attese a durata della suite (`.git/m9.5-reference/censimento-attese/`, a `8220b20`) ne ha
trovate 37 che decidono un verdetto, in 27 funzioni: cinque erano le righe di ADR 0041 §5 (§2), **ventidue non erano
in nessun elenco**. Restano, e sono di [M9.8](../milestones/M9.8.md):

- le ventidue funzioni, ciascuna con l'evento che il censimento ha letto o dedotto — `SlowEcho` fra loro (§2), e la
  pagina dei quattro secondi di `test_the_files_of_a_page.py`, che la SPEC di M9.8 decide (decisione 70);
- **le letture dell'uscita prima dello stato** negli altri file della forma di M13.4g, con `why_not` in comune
  (decisione 76): la sua SPEC rifà il censimento togliendo i test che leggono chiavi scritte anche da un fallimento;
- **la regola per cui un'attesa a durata nuova non entra in silenzio**, la cui forma non è decisa (decisione 71):
  377 etichette scritte a mano che nessun test può verificare sarebbero una lista a mano, e una V etichettata B
  passerebbe. La domanda aperta: la classe si deriva dalla forma dell'attesa dove si può — un tetto la cui scadenza fa
  cadere il test è B per forma —, e l'etichetta resta solo dove la forma non lo dice;
- e il criterio della registrazione di M9.5 «nessun test aspetta una durata dove può aspettare un evento», che M9.5
  soddisfa per le cinque attese di ADR 0041 §5 e passa a M9.8 per le altre.

La difesa è la più piccola, nella forma di ADR 0035 §7: `tests/docs/test_adr_suite_discipline.py` verifica che
ciascuna delle ventidue attese sia ancora nella sua funzione. Il giorno in cui qualcuno la ripara, quel test fallisce: il
pagamento si scrive in un ADR, e il test si gira.

### 6. Le voci che la registrazione eredita per nome

- **Il microfono**: oltre al registratore per parentela (§2), **un ingresso audio che si apre** è una condizione del
  posto solo, letta pigra dal registratore di ELA, che decide (decisione 73). Deve valere sul runner di macOS: nel log
  del giro verde 43554146346 i tre test del microfono girano e passano lì, e uno afferma chiavi che il registratore
  scrive solo quando la coda si è aperta. I numeri di una registrazione si affermano solo dove l'ingresso si è aperto.
- **Il verifier che non deve leggere il disco** (decisione 72): conta ogni lettura del disco tranne quelle della
  funzione di traccia attiva — riconosciuta dalla sua pila: una funzione dal suo codice, un oggetto di C come il
  `CTracer` della copertura dal pacchetto del suo tipo — e del macchinario degli import. **Il rosso del 2026-10-10 non si
  riproduce**, e la sua causa — `os.path.realpath` del tracciatore della copertura, sei `lstat` — resta un'inferenza;
  si è riparata la dipendenza che si è potuta costruire: un tracciatore finto che legge il disco dentro la finestra,
  rosso sul codice di prima.
- **I test degli script delle prove prendono l'ambiente dichiarato**: un test a mondo chiuso,
  `tests/docs/test_every_proof_script_test_takes_the_declared_environment.py`, trova dal sorgente ogni modulo che nomina
  uno script `scripts/prova_*.py` — il percorso, il glob, l'import — e afferma che prende `_only_the_declared_environment`
  dove pytest la dà: nel modulo o in un `conftest.py` della sua cartella. Rosso prima su nove moduli; il nono che la
  rilettura aveva trovato, `tests/cli/test_section_22_on_the_cli.py`, la prende dal `conftest.py` di `tests/cli/`.
- **Il job di Windows** mostra fallimenti, errori e skip: `-ra` al posto di `-rs`, e nessun `-q` suo; il test ricava le
  lettere da `addopts` di `pyproject.toml`, e il job non ne mostra mai meno (decisione 74).
- **Il test di `ela perception`** che dice «nothing» ha una sonda sua dal 2026-10-11 (`d41e7b6`, M13.9): già pagato.

### 7. Il log della suite: uno strumento, non una difesa

`tests/suite_log.py` (decisione 75): acceso dalla variabile `SUITE_LOG` — non `ELA_`, lo spazio del prodotto, che la
fixture dell'ambiente dichiarato svuota —, scrive una riga JSON per test — l'id, il worker, l'istante d'inizio, le
durate di set-up, chiamata e teardown, l'esito — in un file per processo. **Senza la variabile non scrive niente**, e ciò
che `make check` stampa in locale non cambia. I due job di `make check` la mettono, e un passo con `if: always()` e
`continue-on-error: true` porta la cartella via come artifact: **un suo fallimento non fa rosso un job**. È ciò che è
mancato a M13.4g il 2026-11-12: un rosso diceva il suo worker, e niente di ciò che quel worker aveva fatto prima.

## Alternative considerate

- **Un elenco degli skip attesi**, scritto a mano: la forma che ADR 0047 §18 vieta — un elenco diventa falso senza
  accorgersene.
- **Un'esenzione per specie** — gli skip «fuori dal sistema che coprono», come i test POSIX: scartata (decisione 67), la
  regola decide per esclusione e resta semplice; si sono spostati nel posto solo, con la marca `POSIX`.
- **I test di architettura solo su ubuntu**: proposta con i numeri e non presa (decisione 58): la forma della CI non
  cambia.
- **Un sonno iniettabile in `PerceptionCore`**: una giuntura in `src/` che non ripara una causa misurata (decisione 25).

## Conseguenze

- Uno skip sul sistema che un test copre fa rossa la suite, per ogni condizione della macchina, ricavato dalle
  dichiarazioni del posto solo; un test che non gira su nessun job lo dice; uno `skipif` scritto altrove è rosso.
- Le liste dei saltati di `make check` e di `make check-linux` sono le stesse prima e dopo, file per file, salvo le righe
  dette in anticipo: il test del registro, che ora gira su ubuntu (decisione 66), e `test_permissions_bite.py`, che
  fuori da un runner era saltato ed è tolto con la sua guardia (decisione 95).
- Il primo giro della CI è la misura delle dichiarazioni: se un runner non ha ciò che una dichiarazione dice, quel rosso
  si legge e la dichiarazione si corregge con la misura del runner, in un commit — mai saltando, mai rilanciando
  (decisione 64).

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0052** §16 — «la soglia del 10 %» di un giro conforme: per una milestone che porta un binario vero vale due volte, per la parte dei suoi test che non lancia il binario e per quella che lo lancia, ciascuna dentro il giro all'ultimo commit della milestone; la parte del binario si deriva dalle marche del posto solo (§3).
- **ADR 0063** §12 — il debito del costo dei test di M13.9, «a carico di M9.5»: misurato con la regola di §3 nei due giri del «dopo», la parte senza binario sta sopra il 10 %, e il debito passa di mano, a carico di M13.11 (§4).
