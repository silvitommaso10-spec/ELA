Fase: v0.1 — Model Provider abstraction e ProviderRegistry (spec §26, §50, §54).

- `registry.py` — `ProviderRegistry`, il registro dei provider (port `ProviderRegistryPort`).
- `anthropic/` — l'adapter Anthropic: **l'unico posto in cui `import anthropic` è ammesso**
  (regola di architettura 24, contratto import-linter 10, ADR 0020).

Importare `ela.providers` non importa nessun SDK: l'adapter si prende esplicitamente con
`from ela.providers.anthropic import anthropic_provider`.

Chi *chiama* un provider è uno solo: `ela.tools.model`, il tool di `model.complete` (regola di
architettura 25, ADR 0021 §5). Un provider risponde a chiunque; che il contenuto dell'utente esca
solo dietro una decisione del Guardian è una proprietà di quel modulo, non della chiamata.
