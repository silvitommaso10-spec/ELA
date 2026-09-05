Fase: v0.1 — catalogo delle capability di §28–§29 (M4.1, ADR 0010), Permission Guardian di
§27, §29, §33 (M4.2, ADR 0011) e nascita delle autorizzazioni da un'approvazione di §30 (M4.3,
ADR 0012).

- `capabilities.py`: `CapabilityRegistry` immutabile, limitato a MEDIUM, validazione JSON Schema
  degli argomenti, catalogo `catalogue_v01` (`core.echo`, `workspace.write_note`,
  `model.complete`).
- `scope.py`: cosa vuol dire "dentro lo scope" (prefisso di percorso, regole fail-safe).
- `guardian.py`: `PermissionGuardian` — `decide` (port, sincrono, puro, non solleva mai) e
  `authorize` (decide e scrive `PERMISSION_DECIDED`); `RISK_POLICY`, la policy v0.1 per rischio.

- `authorizations.py`: `authorization_from_approval` — la funzione pura che trasforma
  un'`Approval` GRANTED in un'`Authorization` monouso legata a task, step, capability e bersagli
  approvati; otto controlli in ordine (`CHECKS`), `ApprovalMismatchError` al primo che fallisce;
  `DEFAULT_AUTHORIZATION_TTL` (1 ora), `MAX_AUTHORIZATION_TTL` (24 ore).

Fuori da questo package nessuno chiama `decide` (regola 14), costruisce una decisione `ALLOWED`
(regola 12) né costruisce o allarga un'`Authorization` (regola 15): l'executor (M5) chiama
`authorize`, genera il grant con `authorization_from_approval`, lo salva, lo consuma
(`AuthorizationStore.consume`) e poi esegue il tool.
