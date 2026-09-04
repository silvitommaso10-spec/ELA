# 0002. Regole di dipendenza e come vengono verificate

- **Stato:** Accettata
- **Data:** 2026-09-04
- **Riferimenti spec:** §49, §50, §51, §52

## Contesto

La spec chiede che "l'architettura stessa" sia testata (§52): il domain non può importare
infrastruttura, i ports non possono importare provider specifici, le dipendenze devono
rispettare la direzione prevista, i secret non devono finire nel repository. CLAUDE.md fissa
le stesse regole come "non negoziabili". Con i moduli ancora vuoti le regole valgono
banalmente: serve che siano verificate da subito e che i test dimostrino di fallire alla
prima violazione, non solo di passare "a vuoto".

## Decisione

### Le regole

| # | Regola | Moduli soggetti | Cosa possono importare |
|---|--------|-----------------|------------------------|
| 1 | Il dominio è puro | `ela.domain` | stdlib, `pydantic` |
| 2 | I port dipendono solo dal dominio | `ela.ports` | stdlib (`typing` incluso), `ela.domain` |
| 3 | Le librerie di infrastruttura restano ai bordi | tutto `ela` tranne `providers/`, `infrastructure/`, `api/` | tutto tranne `anthropic`, `openai`, `httpx`, `sqlalchemy`, `fastapi`, `typer` |
| 4 | Il core non conosce le implementazioni | `executive/`, `tasks/`, `permissions/`, `audit/` | tutto tranne `ela.providers`, `ela.infrastructure` |

Le regole si applicano a ogni `import` presente nel sorgente, ovunque si trovi: dentro
funzioni, sotto `if TYPE_CHECKING:`, in import relativi. Una dipendenza "solo per i tipi"
resta una dipendenza di direzione sbagliata.

`ela.infrastructure` non esiste ancora (§48 lo colloca fuori da `src/ela`): le regole lo
nominano perché, se e quando verrà creato, sia esente dalla regola 3 e vietato dalla regola 4
senza dover riaprire questo ADR. Non viene creato nessuno stub.

### Due livelli di verifica

Ogni regola è espressa due volte, e le due espressioni si controllano a vicenda.

1. **Contratti import-linter** in `pyproject.toml` (`make lint`, `lint-imports`). Sono
   contratti `forbidden`: elencano i moduli vietati per ciascuna sorgente. Sono leggibili,
   standard e fanno fallire il lint. Il limite è che un contratto `forbidden` vieta solo ciò
   che elenca: non può dire "domain importa *solo* stdlib e pydantic", quindi `import yaml`
   in `domain.py` non lo rompe. Inoltre le liste di package sono scritte a mano e possono
   invecchiare.
2. **Regole pytest** in `tests/architecture/rules.py`. Sono funzioni pure che analizzano
   l'AST di un albero `ela` e restituiscono le violazioni. Sono "closed-world": la regola 1 e
   la regola 2 elencano ciò che è permesso, tutto il resto è violazione; la regola 3 scopre da
   sola i package sotto `src/ela`. `test_layers.py` le applica a `src/ela`.

Tre gruppi di test tengono onesti entrambi i livelli:

- `test_rules_detect_violations.py`: per ogni regola copia `src/ela` in `tmp_path`, scrive
  un modulo che la viola e pretende la violazione; i casi consentiti (per esempio
  `anthropic` in `providers/`) non devono produrne. Senza questi test una regola potrebbe
  passare per sempre perché rotta, non perché rispettata.
- `test_import_linter.py`: verifica che le liste dei contratti coprano tutti i package
  attuali di `ela` (un package nuovo non aggiunto ai contratti fa fallire il test), esegue
  `lint-imports` su una copia temporanea con una violazione e pretende il contratto
  `BROKEN`, e documenta con un test il caso che import-linter non può esprimere.
- `tests/security/test_no_secrets.py`: scansiona i file tracciati (o non ignorati) del repo
  con pattern di chiavi note (`sk-ant-`, `sk-`, `AKIA`, `ghp_`, `xox*-`, `AIza`, chiavi
  private, …) e fallisce se ne trova. I pattern sono verificati in positivo su file
  temporanei con chiavi finte costruite a runtime e in negativo sul file stesso del test.
  Affianca `detect-secrets` (`make secrets`), che copre entropia e keyword.

## Alternative considerate

- **Solo import-linter** — non esprime le regole "solo X" né scopre da solo i package nuovi;
  è però lo strumento standard e rende le regole leggibili nel `pyproject.toml`. Tenuto
  insieme ai test pytest.
- **Solo test pytest** — perde la leggibilità della configurazione e l'integrazione con
  `make lint`; il doppio livello costa poco e i due si verificano a vicenda.
- **Hook di import a runtime** (`sys.meta_path`) — vedrebbe anche gli import dinamici, ma
  solo lungo i percorsi eseguiti dai test: meno prevedibile di un'analisi statica completa.
- **Contratti `layers` di import-linter** — esprimono un ordine tra livelli, non "X importa
  solo Y"; i contratti `forbidden` sono più diretti per queste quattro regole.
- **Permettere `pydantic` nei port** — il prompt della milestone dice "solo domain + stdlib +
  typing"; se i port dovranno esporre modelli propri la regola 2 va allentata con un nuovo
  ADR, non in silenzio.

## Conseguenze

- Ogni nuovo package sotto `src/ela` va aggiunto ai contratti 1, 2 e (se non è un package
  di infrastruttura) 3: `test_contracts_cover_current_packages` lo ricorda.
- Ogni nuova regola architetturale segue lo stesso schema: contratto, regola in `rules.py`,
  caso in `violations.py` (CLAUDE.md, "Qualità").
- Limite accettato: l'analisi è statica. `importlib.import_module("anthropic")` o un import
  costruito a runtime non vengono visti; la review lo intercetta, e un uso del genere nel Core
  è di per sé un segnale di design da respingere.
- I moduli di primo livello di `ela` (per esempio un futuro `ela/settings.py`) sono coperti
  dalla regola 3 solo nella versione pytest: un contratto import-linter con sorgente `ela`
  includerebbe anche `providers/` e `api/`.
- Le regole di §52 che riguardano il comportamento (tool senza Guardian, capability senza
  decisione, transizioni illegali dei task) arrivano con le milestone che introducono quelle
  entità e avranno i propri test.
