# 0054. Il «ferma» a metà corsa: la fermata arriva al tool prima del suo punto di non ritorno; e il runner della CI con una versione scritta

- **Stato:** Proposta. Aperta il 2026-09-30 dal primo commit di M6.3c, che paga il debito di ADR 0053
  §2 prima della SPEC (decisione 8 della sessione di M6.3c): questo commit scrive solo il §1. Il resto
  lo scrive la SPEC di M6.3c, che si mostra prima di implementare.
- **Data:** 2026-09-30
- **Riferimenti spec:** §51, §52, §53
- **Milestone:** M6.3c

## Contesto

M6.3c ripara M6.3: un task fermato mentre il suo tool gira fa rispondere `run` con un `409` e lascia lo
step `RUNNING` dentro un task finale (`docs/milestones/M6.3c.md`). Prima di quella riparazione la
milestone paga un debito che non è suo per materia ma lo è per data: **il runner della CI, da fissare
entro il 2026-10-19** (ADR 0053 §2), il giorno in cui `ubuntu-latest` comincia a passare a Ubuntu 26.

Le decisioni sul «ferma» a metà corsa le scrive la SPEC, e le sezioni che seguono il §1 arrivano con
lei.

## Decisione

### 1. Il debito di ADR 0053 §2, saldato: Ubuntu 24.04 scritto nel file, e le azioni su Node.js 24

`.github/workflows/ci.yml` cambia in cinque righe, e ogni riga ha la sua ragione:

| Che cosa | Prima | Dopo | Perché questa |
|---|---|---|---|
| il runner di `make check` su Linux | `ubuntu-latest` | `ubuntu-24.04` | è l'immagine che `ubuntu-latest` risolveva nell'ultima CI verde di `main` prima del pagamento (run `36732243902`, «Image: ubuntu-24.04», versione `20260920.314.1`): fissarla non cambia niente di ciò che la suite ha già visto, compreso il Chrome Headless Shell di ADR 0052 |
| il checkout | `actions/checkout@v4` | `actions/checkout@v7` | l'ultima maggiore (v7.0.1 del 2026-07-20), su `node24`; le sue novità dalla v4 — le credenziali in un file a parte (v6), il checkout di una fork rifiutato per `pull_request_target` e `workflow_run` (v7) — non toccano un workflow che risponde a `push` e `pull_request` |
| la cache del browser | `actions/cache/restore@v4`, `actions/cache/save@v4` | `actions/cache/restore@v6`, `actions/cache/save@v6` | l'ultima maggiore (v6.1.0 del 2026-06-26), su `node24`; la v6 cambia il modulo (ESM), non gli ingressi |
| uv | `astral-sh/setup-uv@v6` | `astral-sh/setup-uv@v10.2.0` | l'ultima versione (2026-09-21), su `node24`. **Dalla v8.0.0 setup-uv non pubblica più tag maggiori**, solo tag completi e immutabili, quindi è l'unica azione fissata a una versione intera. Le due rotture in mezzo non toccano questo file: la v9 non pota più la cache (più spazio di cache, non un comportamento diverso), e la v10 spegne la cache con `enable-cache: auto` su `pull_request_target`, `workflow_run` e `release` — il file dice `enable-cache: true` e non risponde a quegli eventi |

Che ogni azione giri su `node24` è letto dal suo `action.yml` al tag scelto (`runs.using`), non dalle
note di rilascio. `macos-latest` e `windows-latest` restano come sono: non sono di questa decisione (ADR
0053 §1). Ubuntu 26 resta di ADR 0053 §3: si passa quando Playwright lo supporta, misurato, in un commit
che dice perché.

**La prova**: la CI di `92e4d5b` è verde sui tre job (run `36737326073`, 2026-09-30), e le annotazioni dei
job non hanno più gli avvisi di Node.js 20 né quello su `ubuntu-latest` che la CI di `main` a `a7e6ba0` (run
`36732243902`) stampava.

**La difesa girata**: `tests/docs/test_adr_ci_runner.py` affermava il debito com'era; ora afferma che il
runner di Linux è una versione scritta di Ubuntu e che nessuna delle azioni degli avvisi è rimasta. Il
suo caso negativo: un file che rimette l'etichetta che si muove, o una delle azioni vecchie, deve di
nuovo il debito.

## Alternative considerate

- **Fissare le azioni al loro commit, come setup-uv suggerisce.** Scartata qui: è una scelta di catena di
  fornitura che vale per tutte le azioni del file, non per una, e il debito non la chiede. Il file le
  fissa tutte a un tag.
- **La maggiore più bassa su `node24`** (checkout v5, cache v5). Scartata: il debito chiede le azioni
  aggiornate, e l'ultima maggiore è quella che riceve le correzioni.
- **`ubuntu-22.04`.** Scartata: la suite non ci ha mai girato, e fissare il sistema che si sta già usando
  è l'unica scelta che non cambia niente.

## Conseguenze

- Il nome del job diventa `make check (ubuntu-24.04)`. `main` non ha una protezione di branch
  (`gh api repos/{owner}/{repo}/branches/main/protection` risponde 404, il 2026-09-30), quindi nessun
  controllo richiesto porta il nome vecchio.
- I documenti delle milestone passate che dicono `ubuntu-latest` descrivono la CI del loro tempo, e non
  si riscrivono.
- La tabella dei debiti di `docs/STATO.md` legge il pagamento da questo ADR: ADR 0053 §2 passa a
  «saldato da ADR 0054 §1».
