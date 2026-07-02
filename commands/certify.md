---
description: Full quality certification with badge
argument-hint: <path>
---

Run the complete PluginEval certification pipeline (all three layers + Elo ranking) and assign a quality badge.

This can take 15-20 minutes and reuses the current Codex CLI authentication for all model calls.

## Running

```bash
uv run plugin-eval certify $ARGUMENTS --output markdown
```

If no target path is supplied, ask for the plugin or skill path before running certification.
