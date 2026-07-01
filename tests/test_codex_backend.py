import json
from pathlib import Path

from plugin_eval.codex_backend import build_codex_command, parse_codex_events, parse_json_response


def test_build_codex_command_is_ephemeral_read_only_and_isolated(tmp_path: Path) -> None:
    command = build_codex_command(
        "codex",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        model="gpt-test",
    )

    assert command[:5] == ["codex", "--disable", "plugins", "--disable", "hooks"]
    assert "--ephemeral" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--model") + 1] == "gpt-test"
    assert command[-1] == "-"


def test_parse_codex_events_extracts_message_usage_and_errors() -> None:
    events = "\n".join(
        [
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": '{"score": 0.9}'},
                }
            ),
            json.dumps(
                {"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 5}}
            ),
        ]
    )

    text, usage, errors = parse_codex_events(events)
    assert parse_json_response(text) == {"score": 0.9}
    assert usage == {"input_tokens": 20, "output_tokens": 5}
    assert errors == []
