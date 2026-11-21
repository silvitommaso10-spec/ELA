# ELA — Executive Life Assistant

## Cosa stai costruendo
ELA è un assistente personale AI distribuito (Core Python, nodi Mac/Windows/iPhone).
La specifica completa è in `docs/spec/ELA_spec.md`. È la fonte di verità: in caso di
dubbio leggila. Non inventare comportamenti non descritti lì.
Nei documenti «§N» è la spec, «§N del design» è `docs/spec/ELA_design.md` (Fase 17),
«ADR NNNN §N» è quell'ADR.

## Regola fondamentale
Lavori su UNA milestone alla volta, quella indicata nel prompt. Non anticipare
milestone future, non creare stub "per dopo", non aggiungere feature non richieste.
***Dal 2026-11-13*** (`docs-roadmap`): **l'ordine delle milestone si legge in `docs/ROADMAP.md`**, il solo posto
dove vive; le file di `docs/STATO.md` sono storia.
Ciclo obbligatorio: SPEC → IMPLEMENTATION → TEST → REVIEW → COMMIT → NEXT
MILESTONE.
Alla fine della milestone committi e pushi sul branch di lavoro. Non fai mai merge su main
e non usi mai --force: il merge lo fa l'utente dopo revisione esterna.
Il titolo del merge ha la forma che `tests/docs/test_changelog.py` legge: la **testa**, prima del
primo «: » o « — », è l'id della milestone in maiuscolo (più id uniti da «+») oppure il nome del
branch; un branch di sola registrazione comincia con `docs-` e non porta codice.

## Prima di scrivere codice
1. Leggi `docs/spec/ELA_spec.md` (sezioni rilevanti) e `docs/adr/`.
2. Scrivi in `docs/milestones/<id>.md` la SPEC della milestone: cosa entra, cosa NON entra,
   criteri di accettazione, test previsti. Fermati e mostramela prima di implementare
   (usa plan mode).
3. Se la spec del documento è ambigua, elenca le interpretazioni possibili e chiedi.
   Non scegliere in silenzio.

## Architettura (non negoziabile)
- `src/ela/domain.py`: entità pure (pydantic), zero I/O, zero import da infrastruttura.
- `src/ela/ports.py`: interfacce (Protocol/ABC). Nessun import di provider concreti.
- Il Core non importa mai `anthropic`, `openai`, `sqlalchemy`, `fastapi`, `httpx`.
  Solo `providers/`, `infrastructure/`, `api/` possono farlo.
- Un Tool non può essere eseguito senza una `PermissionDecision` del Guardian.
  Il Guardian non possiede tool: decide su Capability + contesto.
- Capability (spec, rischio, schema, scope) ≠ Tool (implementazione).
- Task state machine deterministica: transizioni illegali sollevano eccezione.
- Audit Log append-only: nessuna API di update/delete.
- Fail-safe: in caso di dubbio l'azione è DENIED, mai eseguita.
- Nessun secret nel repo. Config via `pydantic-settings` + `.env`.

## Qualità
- `ruff check`, `ruff format`, `mypy --strict src/` devono passare.
- `pytest` deve passare. Moduli security-critical (`permissions/`, `audit/`, `tasks/`):
  100% branch coverage.
- Il gate `cov-critical` del Makefile (`CRITICAL_PACKAGES`) si estende a `permissions/` e
  `audit/` nella stessa milestone in cui il package riceve codice, non dopo.
- Ogni nuova regola architetturale → un architecture test in `tests/architecture/`.
- Le regole di ciò che sta in `apps/` non camminano Python: vivono nei test della loro cartella
  (`tests/design/` per il design system), e il README della cartella nomina ogni regola col test
  che la difende.
- Ogni bug trovato → prima un test che fallisce, poi il fix.
- **I mutanti girano in un worktree loro o con `PYTHONDONTWRITEBYTECODE=1`.** ***Dal 2026-11-17*** (decisione 99 di
  M9.5, review a `42bac98`): un `.pyc` rimasto da un mutante rende falso un verdetto nei due versi — gira un codice che
  sul disco non c'è più —, e il 2026-11-17 è costato un `make check` rosso. Un mutante della stessa lunghezza, rimesso
  nello stesso secondo, aveva lasciato un `.pyc` con lo stesso mtime e la stessa dimensione del sorgente vero
  (`.git/m9.5-reference/make-check-c30a4e3.txt`).
- **Una sonda, una misura o uno strumento dell'officina che importa `ela` la lancia un lanciatore.** ***Dal 2026-11-20***
  (decisione 52 del branch `m13.11-il-browser-sul-pc`): un processo figlio, con la cartella di lavoro in una cartella
  temporanea sua e un ambiente costruito da zero — `PATH`, `HOME` e `USERPROFILE` a una cartella temporanea della sonda, ciò
  che serve a Python, e nient'altro: nessuna `ELA_`, nessuna chiave —, mai dalla cartella del repository. Prima di importare
  `ela` la sonda legge e stampa le sue precondizioni — la cartella di lavoro non è il repository e non ha un `.env`; nessuna
  `ELA_` nell'ambiente; `Path.home()` è la sua cartella — e, se una manca, esce senza importare niente. Non importa mai un
  modulo `__main__` (`ela.api` e `ela.cli` partono all'import), e non chiama `main`, `serve`, `build` né `Settings.load()`
  sulla configurazione vera: importa per nome solo ciò che misura. Il 2026-11-20 una sonda che importava ogni modulo di `ela`
  dalla cartella del repository ha avviato una seconda ELA contro la configurazione vera, e l'ha fermata soltanto la porta
  occupata (`docs/milestones/M13.17b.md`, «L'incidente della sonda dell'ambiente»).
  ***Precisata il 2026-11-20*** (risposta 58 dello stesso branch): **il perimetro è ciò che una sessione scrive e lancia da
  sé** — i file di `.git/<branch>-reference/`: sonde, misure, strumenti, i giri dei mutanti — **e ogni giro della suite fatto
  per misura**; e `scripts/generate_*.py`, quando li lancia una sessione: importano `ela`, e si lanciano chiusi. **Fuori**,
  ciascuno con la sua ragione: `make check`, `make misura-m13.9` e la misura del costo, perché da M13.17b la suite si recinta
  da sé — la cartella di lavoro, la casa, il `.env` (`tests/script_fences.py`) —; gli script di `scripts/` che Tommaso lancia
  seguendo la guida, le prove e le misure, perché li lancia lui, apposta, sulla sua macchina configurata, e più d'uno parla
  con l'ELA vera per mestiere.
- Tutto ciò che gira in `make check` ha un test che ne dimostra il fallimento nel caso
  negativo.
- **`make check` una volta, alla fine della milestone, prima del riepilogo; durante il lavoro solo
  i test del pezzo che si tocca.** In primo piano se sta nel limite del comando, e si aspetta lì;
  altrimenti in sfondo, con l'uscita intera in un file e una sola notifica alla fine. In nessuno dei
  due modi è sorvegliato da un monitor o letto a intervalli — il polling costa più del lavoro che
  sorveglia, e una volta è costato sei ore. **E si legge intero**, dallo schermo o dal file: non si
  passa in una pipe che ne taglia la coda — `| tail`, `| head`, un `grep` che tiene solo le righe
  attese —, perché il riepilogo, i conteggi e l'esito stanno in fondo. Un giro perso perché l'esito
  è finito in una pipe costa novanta secondi. **Lo scopo è quello di prima**: un giro solo, alla fine,
  aspettato e non sorvegliato, e letto per intero.
  ***Rivista il 2026-11-02*** (decisione 1 di `docs-registrazioni-di-novembre`): diceva «si lancia in
  primo piano e si aspetta lì: non in background». Sul Mac un comando in primo piano della sessione si
  interrompe a dieci minuti, e il solo pytest di `make check` ne ha presi quasi dieci — 597,98 secondi —
  nel giro di M13.10 del 2026-10-29 (`.git/m13.10-reference/review-79-88/make-check.txt`): la regola
  com'era non si poteva rispettare.
  ***Chiarita il 2026-11-10*** (decisione 36 di M13.13): **dopo una CI rossa, prima del push della
  riparazione, `make check` una volta — e `make check-linux` se il rosso era di ubuntu — sulla punta
  esatta da pushare.** Quella è la «fine» della riparazione. **E ogni giro di cui si usa l'esito si
  legge intero**: un giro letto solo nell'esito non decide niente, e accanto a lui si scrive che non
  è stato letto intero.
  **Nella sessione cloud, che gira come root**, il gate `cov-critical` manca dei rami che solo un
  sistema che nega raggiunge: `make -k check`, il riepilogo elenca quelle righe, e le giudica la CI
  sul branch. La suite di `main` non si rifà per confronto, salvo per un rosso che non si sa spiegare.
  **Nella sessione cloud il browser dei test è quello del lock**, in `.playwright-browsers/` del repo, che git
  ignora: `PLAYWRIGHT_BROWSERS_PATH=$PWD/.playwright-browsers uv run playwright install --only-shell chromium` una volta
  per sessione, e la stessa variabile per i test e per `make -k check`. Quello di `/opt/pw-browsers` è di un'altra
  revisione: senza questa riga `test_browser.py` e `test_node_variables.py` fanno 21 rossi `BrowserNotInstalled`, che
  nasconderebbero quello vero (review di M14.2, decisione 21; misurato il 2026-10-08: 28 verdi).
- **La CI sul branch è il controllo Linux; `make check-linux` serve per riprodurre in locale una
  CI rossa su ubuntu.** Il merge esige la CI verde all'ultimo commit del branch su tutti e tre i
  suoi job: `make check` su ubuntu e su macos, e la suite del nodo su windows. `make check` gira su
  una macchina sola, e una suite che eredita da quella macchina passa
  lì e fallisce sull'altra — è successo il 2026-09-08, e la CI se n'è accorta undici minuti dopo il
  merge. `make check-linux` rifà la suite e il gate della copertura fingendo l'altra metà della
  matrice. **Ha dei limiti e sono scritti in
  `tests/foreign_machine.py`**: finge `platform.system()` e i binari di Apple che `tests/foreign_machine.py` elenca, e nient'altro
  — resta CPython su macOS, non dimostra che Linux funzioni, e non dice niente su tempi e
  installazione. Verde lì significa che la suite non sta ereditando la macchina; verde sul runner
  vero resta l'unica cosa che conta.
  ***Dal 2026-11-10*** (decisione 35 di M13.13): i browser di questa macchina li trova da sé, e ciò
  che resta diverso dal runner è nel docstring di `tests/foreign_machine.py`, con la data — i saltati
  si confrontano lista per lista, file per file, mai nei totali.
- **Dopo un push si lavora pure in locale, ma non si pusha di nuovo finché il giro di quel push non è
  finito e letto sui tre job.** Un giro annullato da un push non è una verifica: un rosso che nessuno ha
  visto non conta come verde. E la trappola è tolta: in `.github/workflows/ci.yml` `cancel-in-progress`
  è `false`, e un giro partito finisce sempre — lo tiene `tests/docs/test_adr_ci_runner.py`, con il suo
  caso negativo.
  ***Scritta il 2026-11-11*** (decisione 2 di M14.6b): era la decisione 26 di M13.13, per quel branch
  soltanto (`docs/milestones/M13.13.md`). Il 2026-11-03 un giro che sarebbe stato rosso, a `e072864`, è
  stato annullato dal push di `56c672c` dieci minuti dopo, e nessuno l'ha visto.
  ***Precisata il 2026-11-18*** (decisione 129 dell'ultimo blocco di M13.15): **un job che ha eseguito anche un solo
  passo ed è fallito è rosso, e non si rilancia mai.** **Un job mai partito** — nessun passo eseguito, il runner non
  acquisito — non è né verde né rosso: si rifà partire una volta, solo lui, e si scrive; se non parte di nuovo ci si
  ferma. Il fatto: nel giro `44325747456`, a `fe776f4`, il job macos non è partito né al primo tentativo né al secondo
  («The job was not acquired by Runner of type hosted even after multiple attempts»), e non c'è stato un terzo.
  ***Dal 2026-11-20*** (risposta 63 del branch `m13.11-il-browser-sul-pc`): **il passo `make check` dei due job ha un
  limite di tempo, sul passo e non sul job**, e il passo del log della suite resta `if: always()`: una suite appesa si
  taglia con il runner ancora vivo, e il log porta via anche il test in volo, che ha la riga del suo set-up e non quella
  della fine. La regola, prima del numero: il doppio del passo sano più lungo fra i giri dell'officina, arrotondato in su
  ai cinque minuti. Il 2026-11-20 il runner macOS di `a83da54` ha perso la comunicazione dopo 53 minuti di `make check`, e
  non ha lasciato nessun log. Lo tiene `tests/docs/test_adr_ci_runner.py`, con il suo caso negativo.
  ***Rivista il 2026-11-21*** (risposta 67 B dello stesso branch): la regola del doppio dava un numero sopra la caduta che
  doveva tagliare — 65 minuti, e i runner di `a83da54` e di `354bebf` sono caduti a 53m39s e a 56m37s dall'inizio del
  passo, tutti e due senza log. **La regola, prima del numero: il passo macOS sano più lungo più un quarto, arrotondato in
  su ai cinque minuti, e almeno dieci minuti sotto la caduta più corta; se le due cose non stanno insieme, ci si ferma.**
  E prima di `make check` parte **un campionatore della macchina**, `.github/sampler.sh`: ogni 30 secondi scrive carico,
  memoria e processi per nome nella cartella del log della suite, che il passo del log porta via. È uno strumento, non
  una difesa — non fa mai diventare rosso il job —, e lo tiene lo stesso test, con i suoi casi negativi.
- **Un test afferma solo ciò di cui ha costruito le precondizioni.** Se gli serve una macchina
  vera, la dichiara con uno `skipif`, che compare nel riepilogo — un `if` dentro il test no
  (ADR 0031 §6). Una precondizione che non si può costruire dichiarando il sistema si costruisce
  iniettando la dipendenza: `available()` legge il filesystem, non `platform.system()`.
- **Da M6.3c, la prova a mano di una milestone ha uno script in `scripts/`**, con il nome che sceglie
  la SPEC. Lo script esegue i passi meccanici della sezione della guida, confronta ogni uscita con
  quella attesa, stampa per ogni passo PASSATO o FALLITO con l'uscita vera, e scrive tutto in un file.
  Si ferma ad aspettare Invio solo dove serve l'occhio o la mano di Tommaso: leggere un messaggio,
  guardare il telefono, dire sì. Il «ferma» a tempo lo fa lo script. **La guida resta la fonte di
  verità**, e la SPEC dice come script e guida restano allineati. Un giudizio a occhio non si delega
  allo script.
- **Una soglia di tempo si fissa solo dove la macchina la può risolvere.** Su questo Mac il confronto
  dei totali fra giri non risolve il 10 % (ADR 0052 §16): il metodo è la misura dentro il giro.
- **Niente di Tommaso in ciò che ELA installa e serve: `src/` e `apps/`.** Nomi, macchine, percorsi,
  siti, preferenze e identità stanno nella configurazione. `scripts/` e `docs/` sono l'officina, e possono
  nominare le macchine di Tommaso. La lingua e i default del prodotto non sono la sua identità. Il test
  della regola, `tests/architecture/test_the_author_is_not_in_the_product.py`, prova solo ciò che una
  macchina sa riconoscere, e lo dice nel nome — nessun host delle reti Tailscale di `TAILNET_RANGES`, IPv4
  e IPv6, e nessun percorso assoluto dentro la home di un utente, in `src/` e `apps/` —; il resto resta alla
  review. Le sue due eccezioni — una rete scritta con il prefisso, più corto dell'indirizzo e senza bit
  d'host, e il segnaposto `you` — sono in `docs/milestones/M9.6.md`, che porta il test. Se un censimento
  trova qualcosa di suo già scritto lì, lo elenca nel riepilogo e non lo ripara: la riparazione è una
  milestone sua.

## Fine sessione
Produci un riepilogo con: file toccati, test aggiunti, output di `pytest -q --cov`,
cosa hai semplificato o lasciato aperto, domande per la review; e, alla fine di un branch, il
titolo del merge, già scritto nella forma della testa.
***Dal 2026-11-13*** (`docs-roadmap`): **il riepilogo di una sessione si scrive anche in
`.git/<branch>-reference/`**, oltre che dove il prompt lo chiede.
Alla fine della milestone committi e pushi sul branch di lavoro. Non fai mai merge su main
e non usi mai --force: il merge lo fa l'utente dopo revisione esterna.
