"""Provider router for PluginEval structured model calls."""

from __future__ import annotations

from typing import Any

from plugin_eval.codex_backend import query_codex
from plugin_eval.kimi_backend import query_kimi


async def query_llm(
    prompt: str,
    *,
    provider: str,
    system: str = "",
    schema: dict[str, Any] | None = None,
    model: str | None = None,
    timeout_seconds: int = 240,
):
    provider_key = (provider or "codex").lower()
    if provider_key == "codex":
        return await query_codex(
            prompt,
            system=system,
            schema=schema,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    if provider_key in {"kimi", "kimi-code", "moonshot"}:
        return await query_kimi(
            prompt,
            system=system,
            schema=schema,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unsupported evaluation provider: {provider}")
