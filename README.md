# plugin-eval

Three-layer quality evaluation framework for OpenAI Codex plugins and skills.

## Quick Start

```bash
cd plugins/plugin-eval
uv sync --extra dev

# Evaluate a skill (static only, instant)
uv run plugin-eval score path/to/skill --depth quick

# Evaluate with a structured Codex judge (~20-60s)
uv run plugin-eval score path/to/skill --depth standard

# Full certification (all layers, ~5 min)
uv run plugin-eval certify path/to/skill
```

## Layers

1. **Static Analysis** — Structural checks, anti-pattern detection. Instant, free.
2. **Codex Judge** — Semantic evaluation (triggering, orchestration, output, scope). One isolated structured Codex run per skill.
3. **Monte Carlo** — Statistical reliability via 50–100 isolated Codex routing simulations.

## Commands

| CLI                   | Description                   |
| --------------------- | ----------------------------- |
| `plugin-eval score`   | Score a plugin or skill       |
| `plugin-eval certify` | Full certification with badge |
| `plugin-eval compare` | Head-to-head comparison       |
| `plugin-eval init`    | Build corpus for Elo ranking  |

PluginEval calls the installed `codex` CLI with ephemeral sessions, a read-only sandbox,
plugins and hooks disabled, and JSON Schema constrained output. It reuses the current Codex
login; no separate Anthropic SDK or API key is required.

## Documentation

See **[docs/plugin-eval.md](../../docs/plugin-eval.md)** for the full reference: layers, dimensions, scoring formula, anti-patterns, statistical methods, and project structure.
