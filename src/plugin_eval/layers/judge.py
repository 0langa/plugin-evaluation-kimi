"""Layer 2: semantic skill evaluation through a structured LLM backend."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plugin_eval.llm_backend import query_llm
from plugin_eval.models import LayerResult
from plugin_eval.parser import ParsedSkill, parse_skill

ORCHESTRATION_RUBRIC = """
Score 0.0 — Poor: Skill behaves as an autonomous supervisor and obscures its contract.
Score 0.25 — Below average: Skill mixes unrelated coordination with its core workflow.
Score 0.5 — Average: Skill is usable but has ambiguous inputs, outputs, or ownership.
Score 0.75 — Good: Skill is a focused reusable workflow with clear inputs and outputs.
Score 1.0 — Excellent: Cohesive Codex workflow, explicit contract, composable, no unrelated control plane.
""".strip()

SCOPE_RUBRIC = """
Score 0.0 — Too thin: Stub or trivial wrapper with near-zero unique value.
Score 0.25 — Under-scoped: Covers only a narrow slice; misses obvious related tasks.
Score 0.5 — Average: Reasonable scope but either too broad or somewhat narrow.
Score 0.75 — Well-scoped: Covers one coherent domain; neither bloated nor sparse.
Score 1.0 — Perfectly calibrated: Minimal surface area, maximum cohesion, ideal composability.
""".strip()

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "triggering": {
            "type": "object",
            "properties": {
                "predictions": {
                    "type": "array",
                    "minItems": 10,
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"},
                            "should_trigger": {"type": "boolean"},
                            "would_trigger": {"type": "boolean"},
                        },
                        "required": ["prompt", "should_trigger", "would_trigger"],
                        "additionalProperties": False,
                    },
                },
                "precision": {"type": "number", "minimum": 0, "maximum": 1},
                "recall": {"type": "number", "minimum": 0, "maximum": 1},
                "f1": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["predictions", "precision", "recall", "f1"],
            "additionalProperties": False,
        },
        "orchestration": {
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["score", "reasoning", "evidence"],
            "additionalProperties": False,
        },
        "output_quality": {
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "simulations": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string"},
                            "expected_output": {"type": "string"},
                            "quality_notes": {"type": "string"},
                        },
                        "required": ["task", "expected_output", "quality_notes"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["score", "simulations"],
            "additionalProperties": False,
        },
        "scope": {
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "assessment": {"type": "string"},
            },
            "required": ["score", "assessment"],
            "additionalProperties": False,
        },
    },
    "required": ["triggering", "orchestration", "output_quality", "scope"],
    "additionalProperties": False,
}


@dataclass
class JudgeConfig:
    judges: int = 1
    auth: str = "codex"
    concurrency: int = 4
    provider: str = "codex"
    model: str | None = None


class JudgeAnalyzer:
    """Semantic skill evaluation using isolated Codex runs."""

    def __init__(self, config: JudgeConfig) -> None:
        self.config = config
        self._sem = asyncio.Semaphore(config.concurrency)

    async def analyze_skill(self, skill_or_dir: Path | ParsedSkill) -> LayerResult:
        skill = skill_or_dir if isinstance(skill_or_dir, ParsedSkill) else parse_skill(skill_or_dir)
        system = (
            "You are an expert evaluator of OpenAI Codex skills. Evaluate only the supplied "
            "skill text. Do not use tools or outside facts. Follow the JSON schema exactly."
        )
        prompt = f"""Evaluate this Codex skill on four dimensions.

Triggering: Generate exactly 10 prompts, 5 that SHOULD trigger this skill and 5 that should NOT.
Predict whether Codex's skill router would trigger it, then compute precision, recall, and F1.

Orchestration rubric:
{ORCHESTRATION_RUBRIC}

Scope rubric:
{SCOPE_RUBRIC}

Output quality: simulate exactly 3 realistic tasks and assess whether these instructions would
produce correct, complete, useful Codex responses.

<skill name="{skill.name}">
{skill.raw_content[:12000]}
</skill>"""
        async with self._sem:
            response = await query_llm(
                prompt,
                provider=self.config.provider,
                system=system,
                schema=JUDGE_SCHEMA,
                model=self.config.model,
        )
        result = response.data
        required_keys = {"triggering", "orchestration", "output_quality", "scope"}
        if not isinstance(result, dict) or not required_keys.issubset(result):
            raise RuntimeError(
                "Judge backend returned JSON with the wrong shape. "
                f"Expected keys {sorted(required_keys)}, got: {result!r}"
            )
        triggering = result["triggering"]
        orchestration = result["orchestration"]
        output_quality = result["output_quality"]
        scope = result["scope"]
        score = max(
            0.0,
            min(
                1.0,
                triggering["f1"] * 0.30
                + orchestration["score"] * 0.30
                + output_quality["score"] * 0.25
                + scope["score"] * 0.15,
            ),
        )
        return LayerResult(
            layer="judge",
            score=score,
            sub_scores={
                "triggering_accuracy": triggering["f1"],
                "orchestration_fitness": orchestration["score"],
                "output_quality": output_quality["score"],
                "scope_calibration": scope["score"],
            },
            metadata={
                **result,
                "backend": self.config.provider,
                "usage": response.usage,
                "duration_ms": response.duration_ms,
            },
        )

    async def assess_triggering(self, skill: Path | ParsedSkill) -> dict:
        return (await self.analyze_skill(skill)).metadata["triggering"]

    async def assess_orchestration(self, skill: Path | ParsedSkill) -> dict:
        return (await self.analyze_skill(skill)).metadata["orchestration"]

    async def assess_output_quality(self, skill: Path | ParsedSkill) -> dict:
        return (await self.analyze_skill(skill)).metadata["output_quality"]

    async def assess_scope(self, skill: Path | ParsedSkill) -> dict:
        return (await self.analyze_skill(skill)).metadata["scope"]
