Fase: v0.1 — API (spec §54; M8.1, ADR 0023; due rotte in più con M8.2, ADR 0024; una con
M8.3, ADR 0025).

Un token statico, su loopback, davanti al mondo che `ela.composition` ha costruito. Questo
package non costruisce niente: riceve un `Ela` e lo serve (regola di architettura 27).

- `app.py`: `create_app(ela)` — le quindici rotte, il middleware del token, e la tabella che
  traduce ogni eccezione in uno status. Le pagine di documentazione automatica sono **spente**:
  uno schema senza credenziali racconta la forma dell'API a chiunque scansioni la porta.
  Il `lifespan` chiama `recover()` una volta all'avvio (ADR 0023 §11).
- `security.py`: il token, confrontato a tempo costante. È un **middleware** e non una
  dipendenza: una dipendenza si dimentica su una rotta nuova, e così anche un percorso che non
  esiste risponde 401 — chi non ha il token non impara nemmeno quali rotte ci sono.
- `tasks.py`: `/tasks` — creare, elencare, leggere, **pianificare** (il piano arriva da fuori
  finché il Planner di §13 non esiste), percorrere con `run` (uno alla volta per task),
  fermare (§65).
- `approvals.py`: `/approvals` e le due risposte. **Unica esenzione della regola 19**: è il solo
  modulo di `src/ela` che chiama `respond`, perché un «sì» è dell'utente. `respond` prima,
  l'engine dopo (ADR 0015 §9), e la finestra 5c è riparata qui.
- `audit.py`: `/audit` e `/audit/verify`, sola lettura. Nessun evento porta argomenti o output:
  non perché la rotta li tolga, ma perché un `AuditEvent` non li contiene (regola 23). La verifica
  arriva dal `Protocol` `AuditVerifier` di `ela.audit`, così questo modulo non nomina nessun
  adapter (regola 27, ADR 0024 §4).
- `devices.py`: `/devices` — i nodi, con la disponibilità **derivata** e mai la colonna
  (regola 20). Chi la serve è `ela.cli` con `ela device list`.
- `results.py`: `/tasks/{id}/results` — l'**unica** rotta che restituisce il contenuto prodotto da
  un tool (§63): la risposta di un modello, il corpo di una nota. La regola 29 tiene `output` a un
  solo modello di `schemas.py`, così un campo aggiunto altrove non lo porta fuori da una rotta che
  non era pensata per portarlo (ADR 0025 §4).
- `system.py`: `/health` (un giro vero al database attraverso il port) e `/diagnostics` (com'è
  composta ELA: mai un segreto, mai contenuto dell'utente).
- `server.py`, `__main__.py`: `python -m ela.api`. L'indirizzo viene dalle settings, non dalla
  riga di comando. `ela serve` (M8.2) chiama esattamente questo.
