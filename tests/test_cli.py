from pathlib import Path

from typer.testing import CliRunner

from plugin_eval.cli import app

runner = CliRunner()


class TestCLI:
    def test_score_quick(self, sample_skill_dir: Path):
        result = runner.invoke(app, ["score", str(sample_skill_dir), "--depth", "quick"])
        assert result.exit_code == 0

    def test_score_json_output(self, sample_skill_dir: Path):
        result = runner.invoke(
            app, ["score", str(sample_skill_dir), "--depth", "quick", "--output", "json"]
        )
        assert result.exit_code == 0
        assert '"composite"' in result.stdout

    def test_score_markdown_output(self, sample_skill_dir: Path):
        result = runner.invoke(
            app, ["score", str(sample_skill_dir), "--depth", "quick", "--output", "markdown"]
        )
        assert result.exit_code == 0
        assert "PluginEval Report" in result.stdout

    def test_score_nonexistent_path(self, tmp_path: Path):
        result = runner.invoke(app, ["score", str(tmp_path / "nonexistent")])
        assert result.exit_code == 2

    def test_plugin_eval_at_deep_depth_emits_downgrade_warning(
        self, sample_plugin_dir: Path
    ) -> None:
        """Plugin-level evaluation only runs the static layer; certify-style
        invocations at deep depth must warn the user that the deeper layers
        were skipped, not silently produce a static-only report.
        """
        result = runner.invoke(
            app,
            ["certify", str(sample_plugin_dir), "--output", "markdown"],
        )
        assert result.exit_code == 0
        # Click 8.3+ exposes stdout/stderr as separate attributes by default.
        assert "warning" in result.stderr.lower()
        assert "plugin-level" in result.stderr.lower()
        assert "deep" in result.stderr.lower()

    def test_plugin_eval_at_quick_depth_does_not_warn(
        self, sample_plugin_dir: Path
    ) -> None:
        """No warning when the requested depth is already static-only."""
        result = runner.invoke(
            app,
            ["score", str(sample_plugin_dir), "--depth", "quick"],
        )
        assert result.exit_code == 0
        assert "warning" not in result.stderr.lower()

    def test_compare_runs(self, sample_skill_dir: Path, poor_skill_dir: Path) -> None:
        result = runner.invoke(
            app,
            ["compare", str(sample_skill_dir), str(poor_skill_dir), "--depth", "quick"],
        )
        assert result.exit_code == 0
        assert "Head-to-Head" in result.stdout

    def test_compare_declares_winner_only_when_scores_actually_differ(
        self, sample_skill_dir: Path, poor_skill_dir: Path
    ) -> None:
        """Regression test: the Overall row used to display scores at .0f
        precision (e.g. two skills that differ by 0.1 both show "93/100")
        while still declaring a non-Tie Winner from the full-precision
        comparison underneath — a self-contradictory table. One decimal
        place must be shown so any declared winner is visibly justified.
        """
        result = runner.invoke(
            app,
            ["compare", str(sample_skill_dir), str(poor_skill_dir), "--depth", "quick"],
        )
        assert result.exit_code == 0
        overall_line = next(line for line in result.stdout.splitlines() if "Overall" in line)
        cells = [cell.strip() for cell in overall_line.split("|")]
        # cells: ['', '**Overall**', '<a>/100', '<b>/100', '<winner>', '']
        score_a = float(cells[2].split("/")[0])
        score_b = float(cells[3].split("/")[0])
        winner = cells[4]
        if winner == "Tie":
            assert score_a == score_b
        elif winner == "A":
            assert score_a > score_b
        elif winner == "B":
            assert score_b > score_a

    def test_init_indexes_skills_when_pointed_at_plugins_parent(
        self, sample_plugin_dir: Path, tmp_path: Path
    ) -> None:
        """init expects <source>/<plugin>/skills/<skill>/SKILL.md -- pointing
        it at the parent directory containing the plugin (sample_plugin_dir's
        parent, i.e. tmp_path) is the correct usage.
        """
        corpus_dir = tmp_path / "corpus-correct"
        result = runner.invoke(
            app,
            ["init", str(sample_plugin_dir.parent), "--corpus-dir", str(corpus_dir)],
        )
        assert result.exit_code == 0
        assert "Corpus initialized with 1 skills" in result.stdout
        assert "warning" not in result.stderr.lower()

    def test_init_warns_when_pointed_at_a_single_plugin_directory(
        self, sample_plugin_dir: Path, tmp_path: Path
    ) -> None:
        """Regression test: init previously silently reported "0 skills" with
        no explanation when pointed one level too deep (at a single plugin's
        own root, which already has a skills/ folder) -- the single most
        likely mistake, since the CLI help text just says "plugins directory"
        without clarifying the expected two-level shape.
        """
        corpus_dir = tmp_path / "corpus-empty"
        result = runner.invoke(
            app,
            ["init", str(sample_plugin_dir), "--corpus-dir", str(corpus_dir)],
        )
        assert result.exit_code == 0
        assert "Corpus initialized with 0 skills" in result.stdout
        assert "warning" in result.stderr.lower()
        assert "skills/ folder" in result.stderr
        # Rich hard-wraps long paths across lines in the captured output
        # (inserting a bare newline mid-word, no space), so compare with
        # newlines removed entirely rather than the raw path string.
        dewrapped_stderr = result.stderr.replace("\n", "")
        assert str(sample_plugin_dir.parent) in dewrapped_stderr

    def test_compare_accepts_provider_option(
        self, sample_skill_dir: Path, poor_skill_dir: Path
    ) -> None:
        """Regression test: compare previously had no --provider/--model/--auth
        options at all (unlike score/certify), so a caller could not select
        the evaluation backend for anything above --depth quick.
        """
        result = runner.invoke(
            app,
            [
                "compare",
                str(sample_skill_dir),
                str(poor_skill_dir),
                "--depth",
                "quick",
                "--provider",
                "codex",
            ],
        )
        assert result.exit_code == 0
