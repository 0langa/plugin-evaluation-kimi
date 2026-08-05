import json
import os
from typing import BinaryIO
from unittest.mock import MagicMock, patch

from plugin_eval.kimi_backend import _parse_json_response, query_kimi

SIMULATION_SCHEMA_REQUIRED = {"activated", "quality_score", "response"}


def test_parse_json_response_handles_nested_fence_inside_string_value() -> None:
    """Regression test: the model's actual JSON answer is well-formed, but
    its own "response" field quotes a ```bash example command -- a second,
    inner set of triple backticks. The old regex `\\`\\`\\`(?:json)?\\s*([\\s\\S]+?)\\s*\\`\\`\\`​`
    is non-greedy and has no concept of JSON string escaping, so it matched
    from the outer opening fence to that INNER fence's own backticks,
    truncating the extracted text mid-response before the JSON's closing
    brace. Confirmed live: 3/50 real Monte Carlo runs against RECALL's
    save-insight skill failed exactly this way even though Kimi's answer
    was complete, valid JSON.
    """
    text = (
        "• UserPromptSubmit hook\n\n  {\"continue\": true}\n\n"
        "• ```json\n"
        "  {\n"
        '    "activated": true,\n'
        '    "quality_score": 0.95,\n'
        '    "response": "Saved requirement to RECALL.\\n\\n'
        "```bash\\npython ./scripts/recall_skill.py save-insight requirements "
        '\\"The health check endpoint must not require authentication.\\"\\n```"\n'
        "  }\n"
        "  ```"
    )
    data = _parse_json_response(
        text,
        schema={"required": sorted(SIMULATION_SCHEMA_REQUIRED)},
    )
    assert data["activated"] is True
    assert data["quality_score"] == 0.95
    assert "```bash" in data["response"]


def test_parse_json_response_still_prefers_clean_fenced_json() -> None:
    """Common case: a single well-formed fence with no nested backticks."""
    text = '```json\n{"activated": true, "quality_score": 0.8, "response": "ok"}\n```'
    data = _parse_json_response(
        text,
        schema={"required": sorted(SIMULATION_SCHEMA_REQUIRED)},
    )
    assert data == {"activated": True, "quality_score": 0.8, "response": "ok"}


def test_parse_json_response_finds_json_after_hook_noise_with_no_fence() -> None:
    """Plain (non-fenced) JSON preceded by hook boilerplate must still parse."""
    text = '• UserPromptSubmit hook\n\n  {"continue": true}\n\n{"activated": false, "quality_score": 0.0, "response": "n/a"}'
    data = _parse_json_response(
        text,
        schema={"required": sorted(SIMULATION_SCHEMA_REQUIRED)},
    )
    assert data["activated"] is False


def test_temp_dir_cleanup_errors_do_not_discard_a_successful_result() -> None:
    """Regression test: on Windows, deleting the per-call temp dir on
    __exit__ can race a just-killed child process that hasn't released its
    file handle yet (WinError 32). Since the return statement lives inside
    the `with tempfile.TemporaryDirectory(...)` block, an unguarded cleanup
    exception discards an already-successful, already-parsed result.
    Confirmed live: 1/50 real Monte Carlo runs failed with exactly this
    PermissionError despite Kimi's response having already parsed
    correctly. ignore_cleanup_errors=True (Python 3.10+; this project
    requires >=3.12) must be passed.
    """
    import tempfile as tempfile_module

    seen_kwargs: list[dict] = []
    real_temporary_directory = tempfile_module.TemporaryDirectory

    def recording_temp_dir(*args, **kwargs):
        seen_kwargs.append(kwargs)
        return real_temporary_directory(*args, **kwargs)

    def fake_popen(
        command: object,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdout: BinaryIO | None = None,
        stderr: BinaryIO | None = None,
        creationflags: int = 0,
    ) -> MagicMock:
        assert stdout is not None
        stdout.write(json.dumps({"ok": True}).encode("utf-8"))
        stdout.flush()
        process = MagicMock()
        process.poll.return_value = 0
        process.returncode = 0
        return process

    with (
        patch("plugin_eval.kimi_backend.shutil.which", return_value="kimi"),
        patch("plugin_eval.kimi_backend.subprocess.Popen", side_effect=fake_popen),
        patch(
            "plugin_eval.kimi_backend.tempfile.TemporaryDirectory",
            side_effect=recording_temp_dir,
        ),
    ):
        import asyncio

        asyncio.run(query_kimi("test prompt", timeout_seconds=5))

    assert len(seen_kwargs) == 1
    assert seen_kwargs[0].get("ignore_cleanup_errors") is True


def test_kimi_subprocess_runs_isolated_from_the_caller_cwd() -> None:
    """Regression test: kimi_backend used to launch the `kimi -p ...`
    subprocess with cwd=os.getcwd() (the caller's real working directory).
    Unlike Codex (codex_backend.py's --disable plugins --disable hooks
    --ignore-user-config), the Kimi CLI has no flag to suppress
    project-scoped hooks for a single -p invocation. If the caller's cwd is
    an activated project with a Kimi hook (e.g. RECALL's UserPromptSubmit
    hook), that hook fires inside the "clean" evaluation subprocess and
    injects extra text into stdout before the actual JSON response,
    corrupting parsing. Confirmed live: 4/50 Monte Carlo runs failed with
    "Kimi Code returned invalid JSON" containing an injected "Curated
    RECALL project memory" block. The subprocess must run from an isolated
    temp directory instead, never the real cwd.
    """
    seen_cwd: list[str] = []

    def fake_popen(
        command: object,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdout: BinaryIO | None = None,
        stderr: BinaryIO | None = None,
        creationflags: int = 0,
    ) -> MagicMock:
        assert cwd is not None
        assert stdout is not None
        seen_cwd.append(cwd)
        stdout.write(json.dumps({"ok": True}).encode("utf-8"))
        stdout.flush()
        process = MagicMock()
        process.poll.return_value = 0
        process.returncode = 0
        return process

    with (
        patch("plugin_eval.kimi_backend.shutil.which", return_value="kimi"),
        patch("plugin_eval.kimi_backend.subprocess.Popen", side_effect=fake_popen),
    ):
        import asyncio

        asyncio.run(query_kimi("test prompt", timeout_seconds=5))

    assert len(seen_cwd) == 1
    assert seen_cwd[0] != os.getcwd()
    # Must be a real, existing directory at call time (not None/cwd fallback).
    assert seen_cwd[0] is not None
