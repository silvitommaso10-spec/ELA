# 0053. Il runner della CI ha una versione scritta: Ubuntu fissato, le azioni aggiornate, e Ubuntu 26 misurato prima di entrarci

- **Stato:** **Accettata il 2026-09-30**: decisione di Tommaso e del revisore, nella review della
  registrazione del branch `docs-registrazioni-e-ordine` (decisione 5). Il debito del §2 lo paga M6.3c,
  come suo primo commit.
- **Data:** 2026-09-30
- **Riferimenti spec:** §51, §52, §53
- **Milestone:** nessuna la costruisce qui: l'ha scritta un branch di registrazione, perché un debito
  datato si scrive in un ADR (`docs/STATO.md` §6, nella forma di ADR 0035 §7) e quel branch non ne aveva
  uno. È un debito per il criterio di ADR 0025 §1: oggi c'è un file che fa la cosa nel modo sbagliato. La
  paga M6.3c.

## Contesto

La CI del 2026-09-30 sul branch `docs-registrazioni-e-ordine` (run `36723231105`, a `aa8e7f9`, verde sui
tre job) ha stampato due avvisi:

- **`ubuntu-latest` passa a Ubuntu 26 a partire dal 2026-10-19** (`actions/runner-images`, issue
  14748);
- **le azioni che puntano a Node.js 20 sono deprecate**, e il runner le fa già girare su Node.js 24:
  `actions/checkout@v4`, `actions/cache/restore@v4`, `astral-sh/setup-uv@v6`.

`.github/workflows/ci.yml` oggi fa girare `make check` sulla matrice `os: [ubuntu-latest, macos-latest]`
e la suite del nodo su `windows-latest`, con `actions/checkout@v4`, `astral-sh/setup-uv@v6`,
`actions/cache/restore@v4` e `actions/cache/save@v4`. Da M13.4 il job di `make check` installa il Chrome
Headless Shell di Playwright (`uv run playwright install --only-shell chromium`, ADR 0052 §16) e la
suite lo lancia davvero. **Un'etichetta che cambia sistema da sola è la CI che cambia senza un commit**:
il 2026-10-19 la suite girerebbe su un Ubuntu che nessuno ha provato, con un browser di cui nessuno ha
misurato il supporto.

## Decisione

### 1. Il runner ha una versione scritta, e le azioni sono aggiornate

Il job di `make check` su Linux gira su **una versione esplicita di Ubuntu**, scritta nel file, non su
`ubuntu-latest`; e **le azioni che puntano a Node.js 20 si aggiornano**. Quale versione e quali azioni lo
scrive M6.3c nel suo primo commit, con la ragione accanto. `macos-latest` e `windows-latest` non sono di
questa decisione.

### 2. Un debito datato: il runner della CI, da fissare entro il 2026-10-19

**Debito a carico di M6.3c**, dichiarato il **2026-09-30**, dagli avvisi della CI della registrazione
`docs-registrazioni-e-ordine` (decisione 5 della sua review). **La scadenza è il 2026-10-19**, il giorno
in cui `ubuntu-latest` comincia a passare a Ubuntu 26; sta nel titolo perché la tabella dei debiti di
`docs/STATO.md` non ha una colonna per lei.

M6.3c lo paga **come suo primo commit**: il runner fissato a una versione esplicita di Ubuntu, e le azioni
aggiornate (§1).

**Non si ripara qui**: un branch di registrazione non porta codice, e il file della CI è codice della
milestone che lo cambia.

**La difesa più piccola**:
`tests/docs/test_adr_ci_runner.py::test_the_ci_still_runs_on_the_moving_label_with_the_node_20_actions`
afferma il file com'è — `ubuntu-latest` nella matrice di `make check`, e le azioni degli avvisi. Il giorno
in cui fallisce il debito si sta pagando: si scrive il pagamento nell'ADR di M6.3c, e il test si gira.

### 3. Ubuntu 26, dopo e misurato

**Il passaggio a Ubuntu 26 si fa dopo, deliberatamente, quando Playwright lo supporta**: misurato, non
scoperto. Il giorno in cui si fa, la versione scritta al §1 cambia in un commit che dice perché, con la
suite verde su quella versione.

## Alternative considerate

- **Lasciare `ubuntu-latest` e vedere il 2026-10-19 se la suite regge.** Scartata: la CI cambierebbe
  senza un commit, e il job di `make check` dipende da un browser il cui supporto per quel sistema nessuno
  ha misurato.
- **Passare subito a Ubuntu 26.** Scartata per la stessa ragione, in anticipo: il supporto di Playwright
  non è misurato.
- **Scrivere il debito solo nel documento di M6.3c.** Scartata: la tabella dei debiti di `docs/STATO.md`
  legge gli ADR, e un debito con una scadenza che la tabella non mostra è un debito che nessuno vede
  arrivare.

## Conseguenze

- Il primo commit di M6.3c tocca `.github/workflows/ci.yml`, e il suo ADR scrive il pagamento di §2.
- Il test della difesa gira in `make check` e ha il suo caso negativo: un file con il runner fissato e le
  azioni aggiornate non è più il debito.
