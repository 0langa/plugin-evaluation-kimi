"""Codex-native structured inference backend for PluginEval."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CodexResponse:
    data: Any
    final_text: str
    usage: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return int(self.usage.get("input_tokens", 0)) + int(self.usage.get("output_tokens", 0))


def build_codex_command(
    codex_bin: str,
    *,
    schema_path: Path | None = None,
    output_path: Path | None = None,
    model: str | None = None,
) -> list[str]:
    command = [
        codex_bin,
        "--disable",
        "plugins",
        "--disable",
        "hooks",
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--ignore-user-config",
        "--ignore-rules",
        "--json",
    ]
    if model and model != "auto":
        command.extend(["--model", model])
    if schema_path is not None:
        command.extend(["--output-schema", str(schema_path)])
    if output_path is not None:
        command.extend(["--output-last-message", str(output_path)])
    command.append("-")
    return command


def parse_codex_events(stdout: str) -> tuple[str, dict[str, int], list[str]]:
    final_text = ""
    usage: dict[str, int] = {}
    errors: list[str] = []
    for raw_line in stdout.splitlines():
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if event_type == "item.completed" and item.get("type") == "agent_message":
            final_text = str(item.get("text") or "")
        elif event_type == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = {
                str(key): int(value)
                for key, value in event["usage"].items()
                if isinstance(value, int)
            }
        elif event_type in {"error", "turn.failed"}:
            errors.append(str(event.get("message") or event.get("error") or event))
    return final_text, usage, errors


def parse_json_response(text: str) -> Any:
    stripped = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    return json.loads(stripped)


async def query_codex(
    prompt: str,
    *,
    system: str = "",
    schema: dict[str, Any] | None = None,
    model: str | None = None,
    timeout_seconds: int = 240,
) -> CodexResponse:
    """Run an isolated, read-only Codex evaluation and return structured output."""

    codex_bin = shutil.which("codex")
    if codex_bin is None:
        raise RuntimeError("Codex CLI was not found on PATH. Install Codex and authenticate first.")

    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    with tempfile.TemporaryDirectory(prefix="plugin-eval-codex-") as temp_dir:
        temp_root = Path(temp_dir)
        schema_path = temp_root / "schema.json" if schema is not None else None
        output_path = temp_root / "last-message.json"
        if schema_path is not None:
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
        command = build_codex_command(
            codex_bin,
            schema_path=schema_path,
            output_path=output_path,
            model=model,
        )
        env = dict(os.environ)
        env["NO_COLOR"] = "1"
        start = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=temp_root,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(full_prompt.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError(
                f"Codex evaluation timed out after {timeout_seconds} seconds."
            ) from exc

        duration_ms = int((time.monotonic() - start) * 1000)
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        event_text, usage, event_errors = parse_codex_events(stdout)
        final_text = output_path.read_text(encoding="utf-8") if output_path.exists() else event_text
        if process.returncode != 0 or event_errors:
            detail = "; ".join(event_errors) or stderr.strip()[-1200:] or "unknown Codex error"
            raise RuntimeError(f"Codex evaluation failed: {detail}")
        if not final_text.strip():
            raise RuntimeError(f"Codex returned no final response. stderr: {stderr.strip()[-800:]}")
        try:
            data = parse_json_response(final_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Codex returned invalid JSON: {final_text[:800]}") from exc
        return CodexResponse(data=data, final_text=final_text, usage=usage, duration_ms=duration_ms)
