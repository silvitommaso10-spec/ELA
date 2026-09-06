Fase: v0.1 — Device Registry e Device Orchestrator (spec §16, §17, §54).

M6.1 (ADR 0016): `DeviceRegistry` — heartbeat con scadenza, disponibilità derivata in lettura,
nodo `local` auto-registrabile con id deterministico. Persistenza in `devices` via
`SqlDeviceRegistry`. Il Device Orchestrator (§17) è M6.2.
