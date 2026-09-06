Fase: v0.1 — Executive Core (spec §12): l'executor della pipeline Planner → Capability → Guardian
→ Authorization → Tool → Device → Audit → **Verification** di §27 e §20 (M5.1, ADR 0013; M5.2,
ADR 0014; M5.3, ADR 0015).

- `executor.py`: `Executor.execute(task_id, step_id, arguments)` esegue **uno step** (una
  capability) di un task EXECUTING: legge lo step dal piano, prende il grant dall'ultima
  `Approval` GRANTED dello step nell'`ApprovalStore` o dai grant di policy, chiama `authorize`, e
  con una decisione `ALLOWED` in mano consuma il grant, chiama il tool, **persiste il risultato**
  nell'`ExecutionResultStore`, scrive `TOOL_EXECUTED`, chiede al **verifier** se le
  `success_conditions` dello step valgono, scrive `EXECUTION_VERIFIED` e chiude lo step:
  `complete_step` solo se la verifica è passata; altrimenti `fail_step` **e `fail`** (una verifica
  fallita è un dubbio: il task si ferma). Un risultato FAILED del tool chiude solo lo step.
  `DENIED` porta il task in DENIED; `REQUIRES_APPROVAL` **persiste** l'`Approval` e mette il task in
  attesa: la risposta arriva dallo store (`respond`, mai dal Core: regola 19). Un'azione senza
  verifier, senza condizioni o con una condizione fuori vocabolario non viene eseguita. **Un retry
  riprende** ciò che un crash ha lasciato a metà: un risultato già nello store non fa girare il
  tool una seconda volta, ma completa l'audit, la verifica o la chiusura dello step
  (`"recovered": true` sugli eventi scritti al retry); una richiesta già nello store viene
  richiesta, non duplicata, e mai se scaduta; uno step FAILED per verifica chiude il task. È
  l'unico modulo del Core che chiama `Tool.execute` (regola 16) e `complete_step` (regola 17).
- `errors.py`: `ExecutorError`, le precondizioni che rifiutano prima di scrivere.

Il Planner (§13) e l'orchestrator che percorre il grafo degli step arrivano con M6.2.
