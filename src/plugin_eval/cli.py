"""Typer CLI for plugin-eval."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import typer
from rich.console import Console

from plugin_eval.engine import EvalEngine
from plugin_eval.models import Depth, EvalConfig
from plugin_eval.provider_defaults import DEFAULT_MODEL, DEFAULT_PROVIDER
from plugin_eval.reporter import Reporter

# On Windows, sys.stdout/stderr default to the system codepage (e.g. cp1252)
# instead of UTF-8 whenever the process isn't attached to a real console --
# which is exactly how every non-interactive caller (CI, piping to a file,
# Claude Code's own Bash tool) invokes this CLI. JSON output is defined as
# UTF-8; reporter output also contains non-ASCII characters (e.g. an em dash
# placeholder for ungraded dimensions). Under cp1252, encoding an em dash
# produces byte 0x97, which is not valid UTF-8 and gets read back as a
# replacement character by any UTF-8 consumer downstream. Force UTF-8 explicitly
# rather than relying on locale defaults.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        with contextlib.suppress(ValueError):
            _reconfigure(encoding="utf-8")

app = typer.Typer(
    name="plugin-eval",
    help="Evaluate OpenAI Codex plugins and skills.",
    add_completion=False,
)
console = Console()
stderr_console = Console(stderr=True)


def _detect_target(path: Path) -> str:
    """Return the supported evaluation target type."""
    if (path / "SKILL.md").exists():
        return "skill"
    if (path / ".codex-plugin").exists() or (path / ".claude-plugin").exists():
        return "plugin"
    return "unknown"


def _run_score(
    path: Path,
    depth: Depth,
    output: str,
    verbose: bool,
    concurrency: int,
    auth: str,
    provider: str | None,
    model: str | None,
    threshold: float | None,
) -> int:
    """Core scoring logic; returns exit code."""
    if not path.exists():
        console.print(f"[red]Error: Path does not exist: {path}[/red]")
        raise typer.Exit(code=2)

    config = EvalConfig(
        depth=depth,
        output_format=output,
        verbose=verbose,
        concurrency=concurrency,
        auth=auth,
        provider=provider or DEFAULT_PROVIDER,
        model=model or DEFAULT_MODEL,
    )
    engine = EvalEngine(config)

    target = _detect_target(path)
    if target == "skill":
        result = engine.evaluate_skill(path)
    elif target == "plugin":
        if depth != Depth.QUICK:
            stderr_console.print(
                f"[yellow]warning:[/yellow] plugin-level evaluation only runs the "
                f"static layer; judge and Monte Carlo layers require per-skill "
                f"evaluation. Requested depth [bold]{depth.value}[/bold] will be "
                f"served from the static layer only — confidence label will be "
                f"[bold]Estimated[/bold] regardless. To use the deeper layers, "
                f"point at an individual skill directory."
            )
        result = engine.evaluate_plugin(path)
    else:
        # Attempt skill evaluation as fallback
        result = engine.evaluate_skill(path)

    reporter = Reporter()
    if output == "json":
        typer.echo(reporter.to_json(result))
    elif output == "html":
        typer.echo(reporter.to_html(result))
    else:
        # Default: markdown
        typer.echo(reporter.to_markdown(result))

    if (
        threshold is not None
        and result.composite is not None
        and result.composite.score < threshold
    ):
        return 1

    return 0


@app.command()
def score(
    path: Path = typer.Argument(..., help="Plugin or skill directory to evaluate"),  # noqa: B008
    depth: Depth = typer.Option(Depth.STANDARD, help="Evaluation depth"),  # noqa: B008
    output: str = typer.Option("markdown", help="Output format: json|markdown|html"),  # noqa: B008
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),  # noqa: B008
    concurrency: int = typer.Option(4, help="Max concurrent LLM calls"),  # noqa: B008
    auth: str = typer.Option(
        "codex", help="Deprecated compatibility option; Codex CLI manages auth"
    ),  # noqa: B008
    model: str | None = typer.Option(None, help="Optional Codex model override"),  # noqa: B008
    provider: str | None = typer.Option(
        None, help="Evaluation backend: codex|kimi"
    ),  # noqa: B008
    threshold: float | None = typer.Option(  # noqa: B008
        None, help="Minimum score threshold; exit code 1 if below"
    ),
) -> None:
    """Evaluate a plugin or skill directory and report its quality score."""
    exit_code = _run_score(
        path, depth, output, verbose, concurrency, auth, provider, model, threshold
    )
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


@app.command()
def certify(
    path: Path = typer.Argument(..., help="Plugin or skill directory to certify"),  # noqa: B008
    output: str = typer.Option("markdown", help="Output format: json|markdown|html"),  # noqa: B008
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),  # noqa: B008
    concurrency: int = typer.Option(4, help="Max concurrent LLM calls"),  # noqa: B008
    auth: str = typer.Option(
        "codex", help="Deprecated compatibility option; Codex CLI manages auth"
    ),  # noqa: B008
    model: str | None = typer.Option(None, help="Optional Codex model override"),  # noqa: B008
    provider: str | None = typer.Option(
        None, help="Evaluation backend: codex|kimi"
    ),  # noqa: B008
    threshold: float | None = typer.Option(None, help="Minimum score threshold"),  # noqa: B008
) -> None:
    """Certify a plugin or skill (runs at deep depth)."""
    exit_code = _run_score(
        path, Depth.DEEP, output, verbose, concurrency, auth, provider, model, threshold
    )
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


@app.command()
def init(
    corpus_source: Path = typer.Argument(..., help="Path to plugins directory to index as corpus"),  # noqa: B008
    corpus_dir: Path = typer.Option(  # noqa: B008
        Path.home() / ".plugineval" / "corpus",  # noqa: B008
        help="Where to store corpus index",  # noqa: B008
    ),
) -> None:
    """Initialize corpus from a plugins directory (a directory whose direct
    children are plugin directories, each with its own skills/ subfolder --
    e.g. a marketplace checkout, not a single plugin's own root)."""
    if not corpus_source.exists():
        console.print(f"[red]Error: Source path does not exist: {corpus_source}[/red]")
        raise typer.Exit(code=2)
    from plugin_eval.corpus import Corpus  # lazy import — Task 10

    corpus = Corpus.init_from_source(corpus_source, corpus_dir)
    if corpus.size == 0:
        # init_from_source only looks one level deep: corpus_source/<plugin>/skills/.
        # Silently succeeding with 0 skills gives no signal that the path is
        # one level too shallow or too deep, which is the single most likely
        # mistake (e.g. pointing at a single plugin's own root, which already
        # has a skills/ folder directly -- not one level further down).
        if (corpus_source / "skills").is_dir():
            stderr_console.print(
                f"[yellow]Warning: 0 skills indexed. {corpus_source} looks like a "
                f"single plugin directory (it has its own skills/ folder). "
                f"`init` expects a directory whose children are each a plugin "
                f"directory -- point it at {corpus_source.parent} instead.[/yellow]"
            )
        else:
            stderr_console.print(
                f"[yellow]Warning: 0 skills indexed from {corpus_source}. "
                f"Expected <corpus_source>/<plugin-name>/skills/<skill-name>/SKILL.md "
                f"for at least one plugin directory.[/yellow]"
            )
    console.print(f"[green]Corpus initialized with {corpus.size} skills at {corpus_dir}[/green]")


@app.command()
def compare(
    skill_a: Path = typer.Argument(..., help="First skill directory"),  # noqa: B008
    skill_b: Path = typer.Argument(..., help="Second skill directory"),  # noqa: B008
    depth: Depth = typer.Option(Depth.QUICK, help="Evaluation depth"),  # noqa: B008
    output: str = typer.Option("markdown", help="Output format"),  # noqa: B008
    auth: str = typer.Option(
        "codex", help="Deprecated compatibility option; Codex CLI manages auth"
    ),  # noqa: B008
    model: str | None = typer.Option(None, help="Optional Codex model override"),  # noqa: B008
    provider: str | None = typer.Option(
        None, help="Evaluation backend: codex|kimi"
    ),  # noqa: B008
) -> None:
    """Head-to-head comparison of two skills."""
    for p in (skill_a, skill_b):
        if not p.exists():
            console.print(f"[red]Error: Path does not exist: {p}[/red]")
            raise typer.Exit(code=2)
    config = EvalConfig(
        depth=depth,
        output_format=output,
        auth=auth,
        model=model,
        provider=provider or DEFAULT_PROVIDER,
    )
    engine = EvalEngine(config)
    result_a = engine.evaluate_skill(skill_a)
    result_b = engine.evaluate_skill(skill_b)
    score_a = result_a.composite.score if result_a.composite else 0
    score_b = result_b.composite.score if result_b.composite else 0
    lines = [
        f"# Head-to-Head: {skill_a.name} vs {skill_b.name}",
        "",
        f"| | {skill_a.name} | {skill_b.name} | Winner |",
        "|---|---|---|---|",
        # One decimal place: scores that round to the same integer (e.g.
        # 93.26 vs 93.16, both "93/100" at .0f) were previously displayed
        # as an apparent tie while a "Winner" was still declared below,
        # which read as contradictory/misleading.
        f"| **Overall** | {score_a:.1f}/100 | {score_b:.1f}/100 | {'A' if score_a > score_b else 'B' if score_b > score_a else 'Tie'} |",
    ]
    if result_a.composite and result_b.composite:
        for da, db in zip(
            result_a.composite.dimensions, result_b.composite.dimensions, strict=False
        ):
            winner = "A" if da.score > db.score else "B" if db.score > da.score else "Tie"
            name = da.name.replace("_", " ").title()
            lines.append(f"| {name} | {da.score:.2f} | {db.score:.2f} | {winner} |")
    console.print("\n".join(lines))
