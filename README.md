# Plugin Evaluation Kimi

> **Dormant:** Available as-is, with no planned updates. This plugin is no longer part of my maintained workflow. Existing releases remain installable.
> Kimi compatibility is legacy and is not actively tested.

Evaluate plugins and skills with static checks and optional Kimi or Codex judging.

## Quick Start

```bash
cd plugin-evaluation-kimi
uv sync --extra dev

# Evaluate a skill (static only, instant)
uv run plugin-eval score path/to/skill --depth quick

# Evaluate with a structured Kimi judge (~20-60s)
uv run plugin-eval score path/to/skill --depth standard

# Full certification (all layers, ~5 min)
uv run plugin-eval certify path/to/skill
```

## Layers

1. **Static Analysis** — Structural checks, anti-pattern detection. Instant, free.
2. **Model Judge** — Semantic evaluation (triggering, orchestration, output, scope). Kimi is the default; Codex is optional.
3. **Monte Carlo** — Statistical reliability via 50–100 model routing simulations.

## Commands

| CLI                   | Description                   |
| --------------------- | ----------------------------- |
| `plugin-eval score`   | Score a plugin or skill       |
| `plugin-eval certify` | Full certification with badge |
| `plugin-eval compare` | Head-to-head comparison       |
| `plugin-eval init`    | Build corpus for Elo ranking  |

Kimi/Moonshot is the default model provider and reads `PLUGIN_EVAL_KIMI_API_KEY` from the environment. Model judging and simulations can consume paid API credits; the quick static checks make no model calls.

Select `--provider codex` to use the installed Codex CLI and its existing login. This optional backend runs isolated sessions with plugins and hooks disabled and uses the account's Codex allowance.

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

See the in-repository **[evaluation methodology](skills/evaluation-methodology/SKILL.md)** for layers, dimensions, scoring formulas, anti-patterns, statistical methods, and project structure.
