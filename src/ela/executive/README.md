Fase: v0.1 — Executive Core (spec §12): l'executor della pipeline Planner → Capability → Guardian
→ Authorization → Tool → Device → Audit di §27 (M5.1, ADR 0013).

- `executor.py`: `Executor.execute(task_id, step_id, arguments, approval=None)` esegue **uno
  step** (una capability) di un task EXECUTING: legge lo step dal piano, sceglie o genera il grant,
  chiama `authorize`, e con una decisione `ALLOWED` in mano consuma il grant, chiama il tool,
  scrive `TOOL_EXECUTED` e chiude lo step (`complete_step` / `fail_step`). `DENIED` porta il task
  in DENIED, `REQUIRES_APPROVAL` costruisce l'`Approval` e lo mette in attesa. È l'unico modulo del
  Core che chiama `Tool.execute` (regola 16).
- `errors.py`: `ExecutorError`, le precondizioni che rifiutano prima di scrivere.

Il Planner (§13) e l'orchestrator che percorre il grafo degli step arrivano con M6.2.
