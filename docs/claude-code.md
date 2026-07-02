# PluginEval For Claude Code

PluginEval is a three-layer quality evaluation engine for Codex-style plugins
and skills. Its `agents/`, `commands/`, and `skills/` folders were already
written in Claude Code's native formats (subagent frontmatter with
`model`/`tools`, `SKILL.md` methodology reference) — this integration only
adds a manifest so Claude Code can discover them.

## Plugin

The Claude Code manifest is `.claude-plugin/plugin.json` at the repository
root. It declares `skills` at the same folder the Codex manifest
(`.codex-plugin/plugin.json`) already uses. `agents/` and `commands/` are
intentionally not declared — Claude Code auto-discovers those conventional
top-level folders without a manifest entry, and declaring them as bare
directory strings fails `claude plugin validate`. Nothing is duplicated or
moved.

Install from a local checkout with a local marketplace
(`.claude-plugin/marketplace.json` next to `plugin.json`, already included):

```text
claude plugin marketplace add <path-to-plugin-evaluation-kimi>
claude plugin install plugin-evaluation-kimi@plugin-evaluation-kimi-local
```

## Running Evaluations From Claude Code

The CLI itself is unchanged and provider-agnostic:

```bash
cd plugin-evaluation-kimi
uv sync --extra dev

uv run plugin-eval score path/to/skill --depth quick
uv run plugin-eval score path/to/skill --depth standard --provider codex
uv run plugin-eval certify path/to/skill --provider kimi
```

- `--provider codex` (or the CLI default provider once configured) shells out
  to the installed `codex` CLI in an ephemeral, read-only, plugins/hooks
  disabled sandbox. It reuses the current Codex login — no separate API key
  is required, and no Kimi credentials are touched.
- `--provider kimi` requires the `kimi` CLI to be installed and authenticated
  (`kimi login`), plus the environment variables below.

There is no dedicated `claude` backend yet (no code shells out to the
`claude` CLI the way `codex_backend.py` shells out to `codex exec`). Using
PluginEval from Claude Code today means running the existing `codex` or
`kimi` provider paths through the CLI; add a `claude_backend.py` as a
follow-up if native Claude-driven judging is needed later.

## Required Environment Variables

Only relevant when `--provider kimi` is selected:

- `PLUGIN_EVAL_KIMI_API_KEY` — Kimi/Moonshot API key. Never hard-code this;
  set it in your shell environment or OS credential store.
- `PLUGIN_EVAL_KIMI_MODEL` — optional override for the Kimi model name.

No `.env.example` exists in this repo (there is no `.env` file to load) —
set these as real environment variables, not in a tracked file.

## Security Notes

- `codex_backend.py` runs Codex in a read-only sandbox with plugins and hooks
  disabled; it cannot write to the evaluated skill/plugin directory.
- Never commit `PLUGIN_EVAL_KIMI_API_KEY` values, shell history containing
  them, or any generated `outputs/`/`work/` evaluation artifacts (already
  covered by `.gitignore`).
