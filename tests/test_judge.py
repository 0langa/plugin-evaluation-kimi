from pathlib import Path
from unittest.mock import patch

import pytest

from plugin_eval.codex_backend import CodexResponse
from plugin_eval.layers.judge import JudgeAnalyzer, JudgeConfig

JUDGE_RESULT = {
    "triggering": {
        "predictions": [
            {"prompt": f"prompt {index}", "should_trigger": index < 5, "would_trigger": index < 5}
            for index in range(10)
        ],
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    },
    "orchestration": {"score": 0.82, "reasoning": "Focused", "evidence": ["Clear contract"]},
    "output_quality": {
        "score": 0.79,
        "simulations": [{"task": "a", "expected_output": "b", "quality_notes": "c"}] * 3,
    },
    "scope": {"score": 0.88, "assessment": "Well scoped"},
}


class TestJudgeConfig:
    def test_default_config(self):
        config = JudgeConfig()
        assert config.judges == 1
        assert config.auth == "codex"


class TestJudgeAnalyzer:
    @pytest.mark.asyncio
    @patch("plugin_eval.layers.judge.query_llm")
    async def test_full_analysis(self, mock_query, sample_skill_dir: Path):
        mock_query.return_value = CodexResponse(JUDGE_RESULT, "{}", {"input_tokens": 100})
        analyzer = JudgeAnalyzer(JudgeConfig())
        result = await analyzer.analyze_skill(sample_skill_dir)

        assert result.layer == "judge"
        assert result.score > 0
        assert result.sub_scores["triggering_accuracy"] == 1.0
        assert result.metadata["backend"] == "codex"
        mock_query.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("plugin_eval.layers.judge.query_llm")
    async def test_individual_assessment_uses_codex_result(
        self, mock_query, sample_skill_dir: Path
    ):
        mock_query.return_value = CodexResponse(JUDGE_RESULT, "{}")
        analyzer = JudgeAnalyzer(JudgeConfig())

        result = await analyzer.assess_orchestration(sample_skill_dir)
        assert result["score"] == 0.82
