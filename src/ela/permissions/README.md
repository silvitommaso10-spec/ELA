Fase: v0.1 — catalogo delle capability di §28–§29 (M4.1, ADR 0010) e Permission Guardian di
§27, §29, §33 (M4.2, ADR 0011).

- `capabilities.py`: `CapabilityRegistry` immutabile, limitato a MEDIUM, validazione JSON Schema
  degli argomenti, catalogo `catalogue_v01` (`core.echo`, `workspace.write_note`,
  `model.complete`).
- `scope.py`: cosa vuol dire "dentro lo scope" (prefisso di percorso, regole fail-safe).
- `guardian.py`: `PermissionGuardian` — `decide` (port, sincrono, puro, non solleva mai) e
  `authorize` (decide e scrive `PERMISSION_DECIDED`); `RISK_POLICY`, la policy v0.1 per rischio.

Fuori da questo package nessuno chiama `decide` (regola 14) né costruisce una decisione `ALLOWED`
(regola 12): l'executor (M5) chiama `authorize`.
