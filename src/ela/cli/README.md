Fase: v0.1 — CLI (spec §54; M8.2, ADR 0024).

La riga di comando di ELA, e un **client** dell'API locale: stesso token, stessa porta, nessun
secondo mondo costruito in proprio (regola di architettura 28). ADR 0023 §1 dava per scontato il
contrario; ADR 0024 §2 dice perché la direzione è cambiata — due processi che scrivono lo stesso
database avrebbero il lock di `run` in uno solo, un mondo costruito dichiara vivo il nodo `local`
e poi esce, e un «sì» entrerebbe da una seconda porta dove la regola 19 ne concede una.

- `app.py`: l'app typer e i diciassette comandi. `main()` è ciò che `ela` e `python -m ela.cli`
  chiamano.
- `client.py`: `connect()` — il **seam** che i test sostituiscono — apre un `httpx.Client` con il
  token in header. Timeout asimmetrico: 5 secondi per connettersi, nessuno per la risposta, perché
  `run` percorre il piano dentro la richiesta. `ApiRefusal` porta il codice e il messaggio
  dell'API, `Unreachable` dice che ELA non è avviata.
- `errors.py`: i quattro codici di uscita (0, 1, 2, 3) e il decoratore che li applica a ogni
  comando. Sono un contratto per chi scrive uno script: un «no» di ELA non esce mai come un'ELA
  spenta.
- `output.py`: colonne allineate e `--json`. Niente cornici e niente colore: l'uscita si legge in
  una pipe quanto su un terminale.
- `tasks.py`, `audit.py`, `nodes.py`, `system.py`: i comandi, uno per rotta. `task plan` manda il
  file com'è — la forma del piano è dell'API, ed è temporanea finché non c'è il Planner (§13).
- `setup.py`: `init`, l'unico comando che scrive su questa macchina. Un solo file, `.env`, con un
  token generato e **mai stampato**; su un `.env` che c'è già non tocca niente e dice cosa manca.
- `serve.py`: **l'unico modulo che importa `ela.api`** (esenzione per percorso della regola 28):
  è il comando che avvia il processo, e senza di lui non c'è nessuno con cui parlare.
