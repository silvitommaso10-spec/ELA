Fase: v0.1 — Model Provider abstraction e ProviderRegistry (spec §26, §50, §54).

- `registry.py` — `ProviderRegistry`, il registro dei provider (port `ProviderRegistryPort`).
- `anthropic/` — l'adapter Anthropic: **l'unico posto in cui `import anthropic` è ammesso**
  (regola di architettura 24, contratto import-linter 10, ADR 0020).

Importare `ela.providers` non importa nessun SDK: l'adapter si prende esplicitamente con
`from ela.providers.anthropic import anthropic_provider`.
