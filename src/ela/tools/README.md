Fase: v0.1 — implementazioni concrete delle capability (spec §28, §29; M5.1, ADR 0013) e i loro
verifier (spec §20, §63; M5.2, ADR 0014).

- `base.py`: `Tool`, la base di ogni tool — verifica della decisione (ADR 0005 §5), tempi,
  forma del risultato; un fallimento è un `ExecutionResult` FAILED con un codice, mai un'eccezione.
- `echo.py`: `EchoTool` per `core.echo` (SAFE).
- `notes.py`: `WriteNoteTool` per `workspace.write_note` (LOW): scrive solo dentro la workspace
  (`ELA_WORKSPACE_DIR`), rifiuta `..`, percorsi assoluti, backslash, link simbolici e tutto ciò che
  risolve fuori dalla radice, prima di toccare il disco; `resolve_workspace` condivisa con il
  verifier.
- `verify.py`: `Verifier`, la base di ogni verifier — il contratto del port (`check_verifiable`)
  una volta sola, la sottoclasse scrive `_check` per condizione; `conditions` è il vocabolario che
  un piano può usare, `failure_codes` ciò che può riportare.
- `verifiers.py`: `EchoVerifier` (`echo.message_matches`) e `WriteNoteVerifier` (`note.exists`,
  `note.content_matches`: rilegge il file con `O_RDONLY | O_NOFOLLOW` e confronta lo SHA-256 con
  quello del `body` richiesto; nel fallimento solo le dimensioni, mai gli hash). Il modulo non
  ha alcun percorso di scrittura (regola 18).
- `registry.py`: `ToolRegistry` (port `ToolRegistryPort`), `VerifierRegistry` (port
  `VerifierRegistryPort`), entrambi immutabili; `tools_v01` e `verifiers_v01`, una coppia per
  capability.
- `settings.py`: `WorkspaceSettings` (`ELA_WORKSPACE_DIR`, default `~/.ela/workspace`).

Nessun tool conosce il Guardian; nessun verifier conosce il tool; l'unico modulo che chiama
`Tool.execute` e `complete_step` è `ela.executive.executor` (regole 16 e 17). Il tool e il
verifier di `model.complete` arrivano con M7.2.
