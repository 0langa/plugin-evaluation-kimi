"""Kimi Code CLI structured inference backend for PluginEval."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KimiResponse:
    data: Any
    final_text: str
    usage: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return int(self.usage.get("input_tokens", 0)) + int(self.usage.get("output_tokens", 0))


def _get_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return winreg.QueryValueEx(key, name)[0]
        except OSError:
            return None
    return None


def _schema_required_keys(schema: dict[str, Any] | None) -> set[str]:
    if not schema:
        return set()
    required = schema.get("required")
    if isinstance(required, list):
        return {str(item) for item in required}
    return set()


def _scan_json_candidates(text: str, required_keys: set[str]) -> tuple[Any, list[Any]]:
    """Scan every `{`/`[` position with a real JSON decoder (not regex).

    Returns (match, all_candidates). `match` is the first candidate dict
    containing all required_keys, or None. Because this uses
    json.JSONDecoder.raw_decode, embedded characters inside a JSON string
    value (including literal ``` sequences) are handled correctly -- unlike
    a regex-based fence search, which has no concept of JSON string
    escaping and can be fooled by markdown fences nested inside a JSON
    string field.
    """
    decoder = json.JSONDecoder()
    candidates: list[Any] = []
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            data, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        candidates.append(data)
        if isinstance(data, dict) and required_keys.issubset(data.keys()):
            return data, candidates
    return None, candidates


def _parse_json_response(text: str, schema: dict[str, Any] | None = None) -> Any:
    original = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text).strip()
    required_keys = _schema_required_keys(schema)

    # Fast path: a single ```json ... ``` fence with nothing else inside it.
    # Tried first (cheap, common case), but NOT trusted blindly -- if the
    # JSON's own string values contain embedded ``` (e.g. a "response" field
    # that itself quotes a ```bash example command), the first non-greedy
    # regex match stops at that inner fence, truncating the real JSON well
    # before its closing brace. Confirmed live: 3/50 Monte Carlo runs failed
    # this way even though the model's full response was valid JSON.
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", original)
    if fence_match:
        fenced = fence_match.group(1).strip()
        try:
            data = json.loads(fenced)
            if (
                not required_keys
                or not isinstance(data, dict)
                or required_keys.issubset(data.keys())
            ):
                return data
        except json.JSONDecodeError:
            pass

    # Always fall back to scanning the ORIGINAL untouched text, not the
    # (possibly truncated) fenced text -- raw_decode correctly skips over
    # nested ``` sequences because they're just ordinary characters inside
    # a properly escaped JSON string as far as a real JSON parser is
    # concerned.
    match, candidates = _scan_json_candidates(original, required_keys)
    if match is not None:
        return match
    if required_keys:
        raise json.JSONDecodeError(
            f"No JSON object contains required keys: {sorted(required_keys)}",
            original,
            0,
        )
    if candidates:
        return candidates[-1]
    raise json.JSONDecodeError("No JSON object found", original, 0)


def _kimi_command(model: str | None, prompt: str) -> list[str]:
    kimi_bin = shutil.which("kimi")
    if kimi_bin is None:
        raise RuntimeError("Kimi Code CLI was not found on PATH. Install it and run `kimi login`.")
    command = [kimi_bin, "-p", prompt]
    selected_model = model or _get_env("PLUGIN_EVAL_KIMI_MODEL")
    if selected_model:
        command.extend(["--model", selected_model])
    return command


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _query_sync(
    prompt: str,
    *,
    system: str,
    schema: dict[str, Any] | None,
    model: str | None,
    timeout_seconds: int,
) -> KimiResponse:
    instructions = f"{system}\n\n{prompt}" if system else prompt
    if schema is not None:
        instructions = (
            f"{instructions}\n\nReturn only valid JSON matching this JSON Schema. "
            f"Do not include markdown fences or explanatory text.\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
    start = time.monotonic()
    env = dict(os.environ)
    user_key = _get_env("PLUGIN_EVAL_KIMI_API_KEY")
    if user_key and "PLUGIN_EVAL_KIMI_API_KEY" not in env:
        env["PLUGIN_EVAL_KIMI_API_KEY"] = user_key
    # ignore_cleanup_errors: on Windows, deleting the temp dir on __exit__ can
    # race a just-killed child process that hasn't fully released its file
    # handle yet (WinError 32, "used by another process"). Since the return
    # statements below live inside this with-block, a cleanup-time exception
    # would discard an already-successful, already-parsed result. Confirmed
    # live: 1/50 Monte Carlo runs failed with exactly this PermissionError
    # despite Kimi's response having already parsed correctly.
    with tempfile.TemporaryDirectory(
        prefix="plugin-eval-kimi-", ignore_cleanup_errors=True
    ) as temp_dir:
        stdout_path = os.path.join(temp_dir, "stdout.txt")
        stderr_path = os.path.join(temp_dir, "stderr.txt")
        with open(stdout_path, "w+b") as stdout_file, open(stderr_path, "w+b") as stderr_file:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            process = subprocess.Popen(
                _kimi_command(model, instructions),
                # Run from the isolated temp dir, not the caller's real cwd.
                # Unlike Codex (see codex_backend.py's --disable plugins
                # --disable hooks --ignore-user-config), the Kimi CLI has no
                # flag to suppress project-scoped hooks for a single -p
                # invocation. If the caller's cwd is a project with an
                # active Kimi hook (e.g. RECALL's UserPromptSubmit hook),
                # that hook fires inside this "clean" evaluation subprocess
                # and injects extra text into stdout before the actual
                # response, corrupting JSON parsing (confirmed live: 4/50
                # Monte Carlo runs failed with "Kimi Code returned invalid
                # JSON" containing an injected "Curated RECALL project
                # memory" block). The skill content is passed entirely via
                # the prompt text, so the subprocess has no need to run from
                # the real project directory at all.
                cwd=temp_dir,
                env=env,
                stdout=stdout_file,
                stderr=stderr_file,
                creationflags=creationflags,
            )
            last_text = ""
            while True:
                duration_ms = int((time.monotonic() - start) * 1000)
                stdout_file.flush()
                stderr_file.flush()
                with open(stdout_path, encoding="utf-8", errors="replace") as reader:
                    last_text = reader.read()
                if last_text.strip():
                    try:
                        data = _parse_json_response(last_text, schema)
                    except json.JSONDecodeError:
                        data = None
                    if data is not None:
                        _stop_process_tree(process)
                        return KimiResponse(
                            data=data,
                            final_text=last_text.strip(),
                            usage={},
                            duration_ms=duration_ms,
                        )
                if process.poll() is not None:
                    with open(stderr_path, encoding="utf-8", errors="replace") as reader:
                        stderr_text = reader.read()
                    if process.returncode != 0:
                        detail = (stderr_text or last_text or "unknown Kimi CLI error").strip()[-1200:]
                        raise RuntimeError(f"Kimi Code evaluation failed: {detail}")
                    try:
                        data = _parse_json_response(last_text, schema)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(
                            f"Kimi Code returned invalid JSON: {last_text[:800]}"
                        ) from exc
                    return KimiResponse(
                        data=data,
                        final_text=last_text.strip(),
                        usage={},
                        duration_ms=duration_ms,
                    )
                if time.monotonic() - start > timeout_seconds:
                    process.kill()
                    raise RuntimeError(
                        f"Kimi Code evaluation timed out after {timeout_seconds} seconds."
                    )
                time.sleep(1)


async def query_kimi(
    prompt: str,
    *,
    system: str = "",
    schema: dict[str, Any] | None = None,
    model: str | None = None,
    timeout_seconds: int = 240,
) -> KimiResponse:
    return await asyncio.to_thread(
        _query_sync,
        prompt,
        system=system,
        schema=schema,
        model=model,
        timeout_seconds=timeout_seconds,
    )
