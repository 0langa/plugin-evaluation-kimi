# plugin-eval

Three-layer quality evaluation framework for OpenAI Codex plugins and skills.

## Quick Start

```bash
cd plugin-evaluation-kimi
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

## Claude Code

This repo's `agents/`, `commands/`, and `skills/` folders are already in
Claude Code's native format. A `.claude-plugin/plugin.json` manifest at the
repo root points at the same folders — no duplication. See
[docs/claude-code.md](docs/claude-code.md) for install and provider details.

## Kimi Code

The repo also ships `kimi.plugin.json` for Kimi Code. Install from an interactive Kimi session with:

```text
/plugins install <path-to-plugin-evaluation-kimi>
/reload
```

Kimi registers the `skills/` directory and namespaced slash commands from `commands/`, such as
`/plugin-evaluation-kimi:eval <path> --depth quick`.

## Documentation

See **[docs/plugin-eval.md](../../docs/plugin-eval.md)** for the full reference: layers, dimensions, scoring formula, anti-patterns, statistical methods, and project structure.
