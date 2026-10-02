Fase: post-0.1 — applicazioni client per i dispositivi (spec §48).

- `design-system/` — il design system di ELA (M17.1, ADR 0042): i token, i componenti e la
  pagina-campionario che ogni superficie eredita. §48 non la prevede: la documenta l'ADR. Non è
  Python, e le sue regole vivono in `tests/design/`.
- `ios/` — le pagine del companion iPhone (M12.5, ADR 0043): i modelli che `ela.api` compone e
  serve al browser del telefono, e la guida per arruolarlo. Non è Python, e le sue regole vivono
  in `tests/ios/`.
- `command-center/` — le pagine del Command Center (M17.2, ADR 0044): i modelli che `ela.api`
  compone e serve al browser del Mac, l'impronta delle capability, e la guida per arruolarlo. §48
  non la prevede: la documenta l'ADR. Non è Python, e le sue regole vivono in
  `tests/command_center/`.
- `desktop/` — segnaposto di §48.

Una regola attraversa `ios/` e `command-center/`, e per questo sta qui: **dove si legge l'esito di un
task** (M6.3c, ADR 0054 §8). Ogni funzione delle loro pagine che legge una rotta con lo stato di un
task — e ogni comando di `ela` che fa lo stesso — è nell'impronta `docs/outcomes.txt`, generata da
`scripts/generate_outcomes.py`; e ciascuna rende `halt`, cioè che cosa aveva fatto lo step in corso
quando il task è stato fermato, oppure il documento della milestone che l'ha fatta suonare dice perché
no. La difende `tests/docs/test_outcomes.py`, e le frasi di ogni valore stanno nei test delle due
superfici (`tests/api/test_console.py`, `tests/api/test_companion.py`).
