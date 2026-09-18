Fase: post-0.1 — Power Node Windows (spec §4.1).

Implementato in M12.4 come **Work Node**, non come il Power Node di §4.1: lo stesso ciclo del nodo
macOS, e nessuna capability nuova — GPU, rendering e automazione di Windows restano fuori. Il codice
vive in `src/ela/node/` — non qui (ADR 0039 §1) —, e ciò che è di Windows sta in
`src/ela/infrastructure/machine/windows.py`. Si avvia con `uv run ela node run`, in primo piano, in
una finestra di PowerShell; la prova con il Core su un Mac è in `docs/GETTING_STARTED.md` §12.
