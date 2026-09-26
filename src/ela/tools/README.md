Fase: v0.1 — implementazioni concrete delle capability (spec §28, §29; M5.1, ADR 0013) e i loro
verifier (spec §20, §63; M5.2, ADR 0014).

- `base.py`: `Tool`, la base di ogni tool — verifica della decisione (ADR 0005 §5), tempi,
  forma del risultato; un fallimento è un `ExecutionResult` FAILED con un codice, mai un'eccezione.
- `echo.py`: `EchoTool` per `core.echo` (SAFE).
- `model.py`: `ModelCompleteTool` per `model.complete` (MEDIUM; M7.2, ADR 0021). Tiene **un**
  `ModelProvider` come dato, costruisce la `ProviderRequest`, e riporta il codice e il `retryable`
  che il provider ha dichiarato (ADR 0020 §7). Non sceglie il modello: lo decide il `model_hint`
  degli argomenti o il default del provider — il Model Router è M7.3. È `idempotent = False`, il
  primo tool a esserlo: l'executor lo esegue sotto il protocollo STARTED e non lo esegue mai due
  volte per lo stesso step. È l'unico modulo che chiama `.complete(` su un provider (regola 25).
- `paths.py`: `classify(root, path)`, dove porta un percorso — forma, risoluzione, link,
  raggiungibilità, esistenza, tipo — in un solo ordine con sette codici `path.*`, condivisa dal
  tool e dal verifier così che non possano divergere; `resolve_workspace`,
  `is_relative_note_path`. Il bersaglio risolto che una domanda mostra, e se un file c'è già, non
  sta più qui: lo dice il `prospect` del tool, con la stessa funzione che decide l'esecuzione
  (M13.1, ADR 0045 §6-bis). Solo `resolve`/`is_symlink`/`is_junction`/`lstat`: nessuna scrittura
  (regola 18). Da M13.3 la forma è **una per ogni sistema** (ADR 0048 §4): niente `:`, nessun nome
  che Windows riserva a un dispositivo (`RESERVED_ON_WINDOWS`, una copia di `ntpath` che un test sa
  accorgersi di quando invecchia), nessun componente che finisce con un punto o uno spazio; e una
  giunzione è un link.
  Da M13.1 il secondo codice è `path.outside_root` e non più `path.outside_workspace`: la
  workspace era l'unica radice che esistesse, e un nome che indica il confine sbagliato è una
  diagnosi falsa anche quando l'esito è giusto (ADR 0045 §5).
- `notes.py`: `WriteNoteTool` per `workspace.write_note` (LOW): scrive solo dentro la workspace
  (`ELA_WORKSPACE_DIR`), rifiuta ciò che `classify` rifiuta prima di toccare il disco; un
  bersaglio irraggiungibile o non regolare è `io.error` con il motivo condiviso.
- `verify.py`: `Verifier`, la base di ogni verifier — il contratto del port (`check_verifiable`)
  una volta sola, la sottoclasse scrive `_check` per condizione; `conditions` è il vocabolario che
  un piano può usare, `failure_codes` ciò che può riportare.
- `verifiers.py`: `EchoVerifier` (`echo.message_matches`), `ModelCompleteVerifier`
  (`model.answered`: il risultato porta un testo, il provider e il modello che l'hanno prodotto, e
  la `ProviderUsage` della chiamata — richiamare il modello per confrontare costerebbe di nuovo e
  manderebbe fuori il contenuto una seconda volta) e `WriteNoteVerifier` (`note.exists`,
  `note.content_matches`: rilegge il file con `O_RDONLY | O_NOFOLLOW` e confronta lo SHA-256 con
  quello del `body` richiesto; nel fallimento solo le dimensioni, mai gli hash; un percorso che
  `classify` rifiuta fallisce con il codice della classificazione, lo stesso del tool); e
  `FsWriteVerifier`/`FsReadVerifier` (`fs.file_exists`, `fs.content_matches`), che chiedono la
  stessa cosa allo stesso posto — per una scrittura i byte sono quelli approvati, per una lettura
  quelli che il tool dice di aver letto, e in tutti e due i casi è il file a decidere. Il modulo
  non ha alcun percorso di scrittura (regola 18).
  Da M13.2 `TerminalRunVerifier` (`terminal.exit_code_matches`, `terminal.output_whole`,
  `terminal.program_unchanged`): dice che il programma è finito da sé con il codice che il **piano**
  si aspettava, che l'uscita è intera, e che il programma sul disco è ancora quello fissato
  all'avvio — mai che l'effetto sia avvenuto. Legge il disco del Core: `terminal.run` non viaggia.
- `registry.py`: `ToolRegistry` (port `ToolRegistryPort`), `VerifierRegistry` (port
  `VerifierRegistryPort`), entrambi immutabili; `tools_v01` e `verifiers_v01`, una coppia per
  capability. Il registro rifiuta un tool che non dichiara `idempotent`, `audit_numbers` e, da
  M13.3, `relocatable` — e `relocatable` vero accanto a `idempotent` falso (ADR 0048 §6).
  `node_tools` e `node_verifiers` sono ciò che un nodo costruisce: l'eco, il modello, le due voci, e
  su un nodo che ha una radice `fs.read` e `fs.write` con i loro verifier, che sono l'insieme
  `VERIFIED_ON_THE_NODE` — lo stesso che la composizione passa all'orchestratore (ADR 0048 §7).
- `fs.py`: `FsReadTool` per `fs.read` (MEDIUM) e `FsWriteTool` per `fs.write` (**HIGH**, la prima
  capability `HIGH` di ELA; M13.1, ADR 0045). Leggono e scrivono **fuori dalla workspace**, dentro
  la radice che `ELA_FS_ROOT` dichiara — che nessuno dei due crea mai: una radice assente è
  `fs.no_root`, non un `mkdir`. `overwrite` è un'asserzione sul mondo e non una richiesta: il tool
  la rilegge prima di scrivere e rifiuta se è cambiata **nei due versi**. Il contenuto di una
  lettura riuscita e la sua dimensione (`bytes`) stanno nel risultato; nell'audit va il percorso,
  mai i byte (M13.1b). Una lettura fallita porta le dimensioni nell'errore, per scelta (ADR 0045
  §8). Da M13.3 viaggiano verso un nodo che ha una radice, con il verifier sul nodo (ADR 0048 §7), e
  rispondono ad `asserted` — ciò che la chiamata afferma, senza guardare un disco — per la domanda di
  uno step su un nodo (ADR 0048 §8). `fs.read` è ripetibile e non ripiazzabile.
- `terminal.py`: `TerminalRunTool` per `terminal.run` (**HIGH**; M13.2, ADR 0047). Un comando è
  `argv`, dal piano al processo: `["/" + program, *args]`, senza shell e senza `PATH`. Decide in un
  punto solo, letto dalla domanda e dall'esecuzione, ciò che si sa senza lanciare — il programma è
  uno di quelli fissati all'avvio, la cartella sta nello scope di M13.1, gli argomenti si possono
  passare — e dà al lanciatore (`CommandLauncher`) l'ambiente chiuso, la cartella, il timeout, il
  respiro e le due metà del tetto. L'uscita torna in testa e coda (`stream`, `CommandOutput`), il
  taglio dichiarato in byte grezzi; i numeri del comando vanno nell'audit per `audit_numbers`.
  `idempotent = False`: un comando interrotto non si rilancia mai.
- `programs.py`: `Programs`, l'identità di ogni programma dichiarato — il file a cui porta e lo
  sha256 — fissata all'avvio e riconfrontata dal tool (prima della domanda e prima dell'`exec`) e dal
  verifier; tre codici `terminal.*`. Solo letture (regola 18).
- `settings.py`: `WorkspaceSettings` (`ELA_WORKSPACE_DIR`, default `~/.ela/workspace`).

Nessun tool conosce il Guardian; nessun verifier conosce il tool; l'unico modulo che chiama
`Tool.execute` e `complete_step` è `ela.executive.executor` (regole 16 e 17). Da M7.2 le tre
capability di §29 hanno tutte tool e verifier.
