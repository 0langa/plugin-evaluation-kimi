from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from plugin_eval.layers.monte_carlo import (
    MonteCarloAnalyzer,
    MonteCarloConfig,
    SimResult,
    run_simulation,
)


class TestSimResult:
    def test_sim_result(self):
        sr = SimResult(activated=True, quality_score=0.8, tokens=2500, duration_ms=1200)
        assert sr.activated is True
        assert sr.errored is False

    @pytest.mark.asyncio
    @patch("plugin_eval.layers.monte_carlo.query_llm", new_callable=AsyncMock)
    async def test_run_simulation_captures_the_actual_error(self, mock_query):
        """Regression test: a failed simulation used to swallow the exception
        entirely (bare `except Exception: return SimResult(errored=True)`,
        no message captured anywhere), making a nonzero n_errored count
        undiagnosable after the fact.
        """
        mock_query.side_effect = RuntimeError("Kimi Code evaluation timed out after 240 seconds.")
        result = await run_simulation("skill content", "a test prompt")
        assert result.errored is True
        assert "RuntimeError" in result.error_message
        assert "timed out after 240 seconds" in result.error_message


class TestMonteCarloAnalyzer:
    @pytest.mark.asyncio
    @patch("plugin_eval.layers.monte_carlo.run_simulation")
    async def test_run_with_mocked_sims(self, mock_sim, sample_skill_dir: Path):
        mock_sim.return_value = SimResult(
            activated=True, quality_score=0.82, tokens=2800, duration_ms=1500
        )
        config = MonteCarloConfig(n_runs=10, concurrency=2)
        analyzer = MonteCarloAnalyzer(config)
        result = await analyzer.analyze_skill(sample_skill_dir)
        assert result.layer == "monte_carlo"
        assert result.score > 0
        assert "triggering" in result.sub_scores
        assert "output_consistency" in result.sub_scores
        assert "failure_rate" in result.sub_scores

    @pytest.mark.asyncio
    @patch("plugin_eval.layers.monte_carlo.run_simulation")
    async def test_analyze_skill_surfaces_error_samples_in_metadata(
        self, mock_sim, sample_skill_dir: Path
    ):
        """Regression test: metadata only ever reported n_errored (a bare
        count) with no way to see what actually went wrong.
        """
        mock_sim.side_effect = [
            SimResult(
                activated=False,
                quality_score=0.0,
                tokens=0,
                duration_ms=0,
                errored=True,
                error_message="RuntimeError: Kimi Code evaluation failed: connection reset",
            ),
            SimResult(
                activated=False,
                quality_score=0.0,
                tokens=0,
                duration_ms=0,
                errored=True,
                # Same message as above -- should be deduplicated.
                error_message="RuntimeError: Kimi Code evaluation failed: connection reset",
            ),
            SimResult(activated=True, quality_score=0.8, tokens=2000, duration_ms=1000),
        ]
        config = MonteCarloConfig(n_runs=3, concurrency=1)
        analyzer = MonteCarloAnalyzer(config)
        result = await analyzer.analyze_skill(sample_skill_dir)
        assert result.metadata["n_errored"] == 2
        assert result.metadata["error_samples"] == [
            "RuntimeError: Kimi Code evaluation failed: connection reset"
        ]

    def test_statistical_analysis(self):
        """Test the statistical analysis on pre-computed sim results."""
        analyzer = MonteCarloAnalyzer(MonteCarloConfig(n_runs=50))
        results = [
            SimResult(activated=True, quality_score=0.8 + i * 0.002, tokens=2500, duration_ms=1200)
            for i in range(48)
        ] + [
            SimResult(
                activated=False, quality_score=0.0, tokens=500, duration_ms=200, errored=True
            ),
            SimResult(activated=True, quality_score=0.75, tokens=8000, duration_ms=5000),
        ]
        stats = analyzer._compute_statistics(results)
        assert stats["triggering"]["activation_rate"] == pytest.approx(0.98)
        assert stats["failure_rate"]["p_fail"] == pytest.approx(0.02)
        assert stats["output_consistency"]["cv"] < 0.15
