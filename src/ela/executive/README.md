Fase: v0.1 — Executive Core (spec §12): l'executor della pipeline Planner → Capability → Guardian
→ Authorization → Tool → Device → Audit → **Verification** di §27 e §20 (M5.1, ADR 0013; M5.2,
ADR 0014).

- `executor.py`: `Executor.execute(task_id, step_id, arguments, approval=None)` esegue **uno
  step** (una capability) di un task EXECUTING: legge lo step dal piano, sceglie o genera il grant,
  chiama `authorize`, e con una decisione `ALLOWED` in mano consuma il grant, chiama il tool,
  scrive `TOOL_EXECUTED`, chiede al **verifier** se le `success_conditions` dello step valgono,
  scrive `EXECUTION_VERIFIED` e chiude lo step: `complete_step` solo se la verifica è passata;
  altrimenti `fail_step` **e `fail`** (una verifica fallita è un dubbio: il task si ferma). Un
  risultato FAILED del tool chiude solo lo step. `DENIED` porta il task in DENIED,
  `REQUIRES_APPROVAL` costruisce l'`Approval` e lo mette in attesa. Un'azione senza verifier,
  senza condizioni o con una condizione fuori vocabolario non viene eseguita. È l'unico modulo
  del Core che chiama `Tool.execute` (regola 16) e `complete_step` (regola 17).
- `errors.py`: `ExecutorError`, le precondizioni che rifiutano prima di scrivere.

Il Planner (§13) e l'orchestrator che percorre il grafo degli step arrivano con M6.2.
