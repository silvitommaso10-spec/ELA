Fase: v0.1 — Device Registry e Device Orchestrator (spec §16, §17, §54).

M6.1 (ADR 0016): `DeviceRegistry` — heartbeat con scadenza, disponibilità derivata in lettura,
nodo `local` auto-registrabile con id deterministico. Persistenza in `devices` via
`SqlDeviceRegistry`. Il Device Orchestrator (§17) è M6.2.

M13.3 (ADR 0048 §2): `LocalHeartbeat` — il battito di `local` lo scrive il Core, e soltanto lui:
prima di ogni piazzamento, su richiesta del runner attraverso il port `LocalBeat`, e a un periodo di
un terzo del TTL, nel ciclo che il lifespan avvia. Dalla review dell'implementazione (ADR 0048 §13)
il battito porta anche lo stato di `local`, `BUSY` mentre uno step gira lì: la domanda la risponde il
Task Engine (`running_on`) e la composizione la passa come passa la lettura dell'alimentazione.
`POWER_POINTS` `AC` vale 20.

M13.3 (ADR 0048 §7): F7 legge un insieme in più. `DeviceOrchestrator` riceve `carried`, le
capability che un nodo verifica sulla propria macchina, e `UNVERIFIABLE` scatta per ciò il cui
verifier legge la macchina **e nessun nodo porta**: `fs.*` viaggia, la nota, la percezione e il
terminale no.
