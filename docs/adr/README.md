# Architecture Decision Records

Ogni decisione architetturale significativa viene registrata qui (spec §48: "ogni modifica
architetturale significativa deve essere documentata"). Un ADR è immutabile: se una decisione
cambia, si scrive un nuovo ADR che sostituisce il precedente.

## Indice

| ID | Titolo | Stato |
|----|--------|-------|
| [0001](0001-stack.md) | Stack tecnico del Core | Accettata |
| [0002](0002-architecture-rules.md) | Regole di dipendenza e come vengono verificate | Accettata |
| [0003](0003-domain-model.md) | Forma del domain model: identità, tempo, immutabilità, ordine del rischio | Accettata |
| [0004](0004-task-transitions.md) | Transizioni di stato del Task e forma della funzione `transition` | Accettata |

## Template

Nome file: `NNNN-titolo-breve.md` (numero progressivo a 4 cifre).

```markdown
# NNNN. Titolo della decisione

- **Stato:** Proposta | Accettata | Deprecata | Sostituita da NNNN
- **Data:** AAAA-MM-GG
- **Riferimenti spec:** §N, §M

## Contesto

Qual è il problema o la forza in gioco che richiede una decisione.

## Decisione

Cosa si è deciso, in forma attiva ("Usiamo X per Y").

## Alternative considerate

- **Alternativa A** — perché è stata scartata.
- **Alternativa B** — perché è stata scartata.

## Conseguenze

Effetti positivi, negativi e vincoli che la decisione introduce (inclusi i test di
architettura che la rendono verificabile).
```
