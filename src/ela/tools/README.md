Fase: v0.1 — implementazioni concrete delle capability (spec §28, §29; M5.1, ADR 0013) e i loro
verifier (spec §20, §63; M5.2, ADR 0014).

- `base.py`: `Tool`, la base di ogni tool — verifica della decisione (ADR 0005 §5), tempi,
  forma del risultato; un fallimento è un `ExecutionResult` FAILED con un codice, mai un'eccezione.
- `echo.py`: `EchoTool` per `core.echo` (SAFE).
- `paths.py`: `classify(root, path)`, dove porta un percorso di nota — forma, risoluzione, link,
  raggiungibilità, esistenza, tipo — in un solo ordine con sette codici `path.*`, condivisa dal
  tool e dal verifier così che non possano divergere; `resolve_workspace`,
  `is_relative_note_path`. Solo `resolve`/`is_symlink`/`lstat`: nessuna scrittura (regola 18).
- `notes.py`: `WriteNoteTool` per `workspace.write_note` (LOW): scrive solo dentro la workspace
  (`ELA_WORKSPACE_DIR`), rifiuta ciò che `classify` rifiuta prima di toccare il disco; un
  bersaglio irraggiungibile o non regolare è `io.error` con il motivo condiviso.
- `verify.py`: `Verifier`, la base di ogni verifier — il contratto del port (`check_verifiable`)
  una volta sola, la sottoclasse scrive `_check` per condizione; `conditions` è il vocabolario che
  un piano può usare, `failure_codes` ciò che può riportare.
- `verifiers.py`: `EchoVerifier` (`echo.message_matches`) e `WriteNoteVerifier` (`note.exists`,
  `note.content_matches`: rilegge il file con `O_RDONLY | O_NOFOLLOW` e confronta lo SHA-256 con
  quello del `body` richiesto; nel fallimento solo le dimensioni, mai gli hash; un percorso che
  `classify` rifiuta fallisce con il codice della classificazione, lo stesso del tool). Il modulo
  non ha alcun percorso di scrittura (regola 18).
- `registry.py`: `ToolRegistry` (port `ToolRegistryPort`), `VerifierRegistry` (port
  `VerifierRegistryPort`), entrambi immutabili; `tools_v01` e `verifiers_v01`, una coppia per
  capability.
- `settings.py`: `WorkspaceSettings` (`ELA_WORKSPACE_DIR`, default `~/.ela/workspace`).

Nessun tool conosce il Guardian; nessun verifier conosce il tool; l'unico modulo che chiama
`Tool.execute` e `complete_step` è `ela.executive.executor` (regole 16 e 17). Il tool e il
verifier di `model.complete` arrivano con M7.2.
