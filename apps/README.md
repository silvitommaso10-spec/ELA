Fase: post-0.1 — applicazioni client per i dispositivi (spec §48).

- `design-system/` — il design system di ELA (M17.1, ADR 0042): i token, i componenti e la
  pagina-campionario che ogni superficie eredita. §48 non la prevede: la documenta l'ADR. Non è
  Python, e le sue regole vivono in `tests/design/`.
- `ios/` — le pagine del companion iPhone (M12.5, ADR 0043): i modelli che `ela.api` compone e
  serve al browser del telefono, e la guida per arruolarlo. Non è Python, e le sue regole vivono
  in `tests/ios/`.
- `desktop/` — segnaposto di §48.
