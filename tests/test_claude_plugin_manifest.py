"""Tests for the Claude Code plugin manifest."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_claude_plugin_manifest_is_valid_json():
    payload = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert payload["name"] == "plugin-evaluation-kimi"
    assert payload["skills"] == "./skills/"
    # agents/ and commands/ are intentionally omitted: Claude Code
    # auto-discovers those conventional top-level folders without a
    # manifest declaration, and declaring them as bare directory strings
    # fails `claude plugin validate` ("agents: Invalid input").
    assert "agents" not in payload
    assert "commands" not in payload


def test_claude_plugin_manifest_paths_resolve():
    payload = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    rel = payload["skills"].removeprefix("./")
    assert (ROOT / rel).is_dir(), f"skills path {payload['skills']} does not resolve"
    assert (ROOT / "agents").is_dir()
    assert (ROOT / "commands").is_dir()


def test_codex_manifest_is_unmodified_by_claude_code_addition():
    payload = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert payload["name"] == "plugin-evaluation-kimi"
    assert payload["skills"] == "./skills/"


def test_kimi_plugin_manifest_is_valid_json():
    payload = json.loads((ROOT / "kimi.plugin.json").read_text(encoding="utf-8"))
    assert payload["name"] == "plugin-evaluation-kimi"
    assert payload["skills"] == "./skills/"
    assert payload["commands"] == "./commands/"
    assert "mcpServers" not in payload
    assert "tools" not in payload
    assert "apps" not in payload
