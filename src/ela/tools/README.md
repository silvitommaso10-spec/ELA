Fase: v0.1 — implementazioni concrete delle capability (spec §28, §29; M5.1, ADR 0013).

- `base.py`: `Tool`, la base di ogni tool — verifica della decisione (ADR 0005 §5), tempi,
  forma del risultato; un fallimento è un `ExecutionResult` FAILED con un codice, mai un'eccezione.
- `echo.py`: `EchoTool` per `core.echo` (SAFE).
- `notes.py`: `WriteNoteTool` per `workspace.write_note` (LOW): scrive solo dentro la workspace
  (`ELA_WORKSPACE_DIR`), rifiuta `..`, percorsi assoluti, backslash, link simbolici e tutto ciò che
  risolve fuori dalla radice, prima di toccare il disco.
- `registry.py`: `ToolRegistry` (port `ToolRegistryPort`, immutabile) e `tools_v01`.
- `settings.py`: `WorkspaceSettings` (`ELA_WORKSPACE_DIR`, default `~/.ela/workspace`).

Nessun tool conosce il Guardian; l'unico modulo che chiama `Tool.execute` è
`ela.executive.executor` (regola 16). Il tool di `model.complete` arriva con M7.2.
