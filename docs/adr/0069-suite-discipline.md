# 0069. La disciplina della suite: un posto solo per gli skip, i test che aspettano un evento, e il costo di un binario vero

- **Stato:** **Proposta** il **2026-11-17**, con l'implementazione di M9.5 sul branch `m9.5-la-pulizia-della-suite`
  (`docs/milestones/M9.5.md`, la SPEC e la review delle tre SPEC a `ad1826c`, decisioni 56–81), per diventare Accettata
  con un commit suo dopo la prova a mano della sezione 33 di `docs/GETTING_STARTED.md` sull'ultimo commit del branch
  (decisione 81). **Le «Righe riviste» che questo ADR porta sono scritte**, con il marchio sulla riga «Stato:»
  dell'ADR che rivede — ADR 0052.
- **Data:** 2026-11-17
- **Riferimenti spec:** §48, §51, §53
- **Milestone:** [M9.5](../milestones/M9.5.md)
- **Continua:** ADR 0031 §6 (un test afferma solo ciò di cui ha costruito le precondizioni), ADR 0035 §7 (la forma di
  un debito datato), ADR 0006 §13 (si aspetta un evento, mai una durata), ADR 0026 §6 (un tetto di tempo in un test
  misura la macchina). **Paga** ADR 0047 §18 e ADR 0041 §5; **rivede** come si applica la soglia di ADR 0052 §16 (§3).

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
  cancellazione è risalita;
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
muoiono ancora. I numeri, prima e dopo, sono nel documento della milestone.

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
- Le liste dei saltati di `make check` e di `make check-linux` sono le stesse prima e dopo, file per file, salvo la riga
  detta in anticipo (decisione 66): il test del registro, che ora gira su ubuntu.
- Il primo giro della CI è la misura delle dichiarazioni: se un runner non ha ciò che una dichiarazione dice, quel rosso
  si legge e la dichiarazione si corregge con la misura del runner, in un commit — mai saltando, mai rilanciando
  (decisione 64).

**Righe riviste** — gli ADR non si riscrivono: si leggono con questo accanto, e la riga «Stato:» di ciascuno lo dice,
con la sezione di questo ADR a cui guardare.

- **ADR 0052** §16 — «la soglia del 10 %» di un giro conforme: per una milestone che porta un binario vero vale due volte, per la parte dei suoi test che non lancia il binario e per quella che lo lancia, ciascuna dentro il giro all'ultimo commit della milestone; la parte del binario si deriva dalle marche del posto solo (§3).
