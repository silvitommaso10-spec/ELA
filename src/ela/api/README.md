Fase: v0.1 — API (spec §54; M8.1, ADR 0023). La CLI è M8.2.

Un token statico, su loopback, davanti al mondo che `ela.composition` ha costruito. Questo
package non costruisce niente: riceve un `Ela` e lo serve (regola di architettura 27).

- `app.py`: `create_app(ela)` — le dodici rotte, il middleware del token, e la tabella che
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
- `audit.py`: `/audit`, sola lettura. Nessun evento porta argomenti o output: non perché la
  rotta li tolga, ma perché un `AuditEvent` non li contiene (regola 23).
- `system.py`: `/health` (un giro vero al database attraverso il port) e `/diagnostics` (com'è
  composta ELA: mai un segreto, mai contenuto dell'utente).
- `server.py`, `__main__.py`: `python -m ela.api`. L'indirizzo viene dalle settings, non dalla
  riga di comando.
