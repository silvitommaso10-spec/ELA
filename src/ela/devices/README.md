Fase: v0.1 — Device Registry e Device Orchestrator (spec §16, §17, §54).

M6.1 (ADR 0016): `DeviceRegistry` — heartbeat con scadenza, disponibilità derivata in lettura,
nodo `local` auto-registrabile con id deterministico. Persistenza in `devices` via
`SqlDeviceRegistry`. Il Device Orchestrator (§17) è M6.2.

M13.3 (ADR 0048 §2): `LocalHeartbeat` — il battito di `local` lo scrive il Core, e soltanto lui:
prima di ogni piazzamento, su richiesta del runner attraverso il port `LocalBeat`, e a un periodo di
un terzo del TTL, nel ciclo che il lifespan avvia.
