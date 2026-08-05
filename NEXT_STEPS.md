# Plugin Evaluation Kimi (PluginEval) — Status & Roadmap
_Portfolio audit: 2026-07-11_

## What this is
PluginEval is a three-layer quality-evaluation framework for AI-agent plugins and skills: instant static analysis, a structured LLM judge, and Monte Carlo routing simulations (50-100 isolated runs) that together produce composite 0-100 scores, per-dimension grades, confidence intervals, and platinum/gold/silver/bronze badges. The stack is Python 3.12+ with pydantic, typer, and rich — plus shell-out backends for the Codex and Kimi CLIs (`codex_backend.py`, `kimi_backend.py`, default provider "kimi") and plugin surfaces (2 agents, 3 commands, 1 skill) that make the evaluator itself installable in Claude Code, Codex, and Kimi Code.

## Current state
This is the most substantial codebase of the four audited repos, and it is proven in use: on 2026-07-06 it produced the full marketplace quality baseline — 22 skills across 8 plugins certified at deep depth — recorded in the marketplace repo's `docs/plugin-evaluation-baseline-matrix.md` with per-skill JSON artifacts. The working tree is clean and pushed to origin.

The standalone seams identified after the monorepo import are now closed:

- The README links to the in-repository evaluation methodology.
- `scripts/eval_all.py` accepts either this plugin root or an explicit plugin-container directory via `--plugins-dir`.
- The stale `ty` import path was removed; Ruff and `ty` now pass locally.
- Naming is drifty: the package is `plugin-evaluation-kimi` with Kimi as the default provider (`provider_defaults.py`), while the README calls the project "plugin-eval" and describes it as being "for OpenAI Codex plugins".

The marketplace baseline run also exposed real product issues:

- The frontmatter parser combines `description` and `when_to_use`, so trigger metadata is recognized for both supported forms.
- Kimi-provider runs failed during the baseline due to hook JSON pollution and a broken RECALL hook path, so every certification fell back to `--provider codex` — notable for a package named after Kimi.
- The `code_template_quality` dimension reports 0.000/unmeasured in composite output.
- There is no Claude backend yet (`docs/claude-code.md` explicitly defers `claude_backend.py` as a follow-up), and no LICENSE file despite the marketplace registry claiming MIT. Tags through `v0.1.2` exist, and the CI workflow defines compile, Ruff, `ty`, and pytest gates.

## Definition of "finished"
Version 1.0 means all of the following are true:

- A full `certify` run completes cleanly with the Kimi backend, with hook interference isolated.
- A `claude_backend.py` exists so all three ecosystem clients can drive judging.
- The test suite, Ruff, and `ty` run in CI on every push, and a tagged v1.0 release with a LICENSE backs the marketplace listing.

## Roadmap

### Phase 1 — Now (next 1-2 weeks)
- Add a LICENSE file (MIT per the marketplace registry).

### Phase 2 — Next (2-6 weeks)
- Debug the Kimi backend failures observed during the 2026-07-06 baseline (hook JSON pollution and a broken RECALL hook path): isolate the child CLI environment the way `codex_backend.py` disables plugins and hooks, then re-certify one skill per provider as a smoke test.
- Implement `claude_backend.py` shelling out to the `claude` CLI, mirroring the Codex backend's ephemeral read-only sandbox, as `docs/claude-code.md` proposes.
- Resolve the naming drift: pick one public name (plugin-eval versus plugin-evaluation-kimi) and align the README title, pyproject description, and the marketplace listing.
- Wire the `code_template_quality` dimension so it is actually measured or formally excluded from the composite instead of reporting 0.000.

### Phase 3 — Later (optional/stretch)
- Populate the Elo/corpus path (`elo.py`, `corpus.py`, `plugin-eval init`) so badges can carry the Elo thresholds the methodology documents; the baseline matrix notes Elo is not currently produced by `score`/`certify`.
- Offer a marketplace-wide batch mode (certify every `skills/*/SKILL.md` under a registry root) to replace the manual per-skill loop used for the 2026-07-06 baseline.
- Publish scored badges back into marketplace listings automatically.

## Effort to "finished"
M (1-4 weeks). The engine, statistics layers, and test suite are done and battle-tested, but v1.0 requires real debugging (Kimi backend reliability), one new backend, and parser work — more than cleanup, less than a rebuild, for part-time solo work.
