Fase: v0.1 — Composition root e configurazione (spec §46, §54; M8.1, ADR 0023; due variabili
in più con M8.3, ADR 0025).

La prima cartella di `src/ela/` non prevista da §48, e ADR 0023 §1 dice perché: ciò che sta qui
non appartiene a nessun package esistente, perché un modulo che li conosce tutti non può vivere
dentro uno di loro.

- `settings.py`: `Settings`, l'unico posto in cui ELA legge l'ambiente. Tiene i cinque
  `BaseSettings` già esistenti (persistenza, workspace, device, Anthropic, routing) più i due
  nuovi — `ApiSettings` (token e indirizzo) e `CoreSettings` (chi è l'utente, le durate,
  e da M8.3 anche `ELA_NOTES_SCOPE`, che sta qui e non in `WorkspaceSettings` perché validarlo
  vuol dire chiedere al catalogo — ADR 0025 §5). Ciò che era sparso non era la validazione, che
  vive accanto al codice che protegge: era il punto di lettura.
- `system.py`: `SystemClock` e `UuidGenerator`, le prime implementazioni **di produzione** dei
  port `Clock` e `IdGenerator` — fino a M8.1 esistevano solo i fake, che nessun modulo di
  produzione può importare.
- `root.py`: `build(settings) -> Ela` costruisce tutto una volta sola, nell'ordine di ADR 0023 §5,
  e `Ela` è il mondo costruito. È l'unico modulo che nomina i concreti (regola 27).
- `errors.py`: `ConfigurationError` — una configurazione sbagliata è un messaggio che nomina la
  variabile, non uno stack trace, e ferma l'avvio prima di ogni lavoro.

Chi serve questo mondo su HTTP è `ela.api`. La CLI di M8.2 **non** lo costruisce: parla con il
processo che lo ha costruito, attraverso l'API (ADR 0024 §2, regola 28). Di qui legge soltanto le
settings — `ApiSettings` per un comando qualunque, `Settings.load()` per `ela serve`, che il
processo lo avvia.
