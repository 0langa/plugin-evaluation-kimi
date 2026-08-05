from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "eval_all.py"
    spec = importlib.util.spec_from_file_location("plugin_eval_eval_all", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_plugin(root: Path, name: str) -> Path:
    plugin = root / name
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text('{"name": "demo"}')
    return plugin


def test_discover_plugins_accepts_a_single_plugin_root(tmp_path: Path) -> None:
    script = _load_script()
    plugin = _make_plugin(tmp_path, "single")

    assert script.discover_plugins(plugin) == [plugin]


def test_discover_plugins_accepts_a_container_of_plugin_roots(tmp_path: Path) -> None:
    script = _load_script()
    first = _make_plugin(tmp_path, "alpha")
    second = _make_plugin(tmp_path, "beta")
    (tmp_path / "not-a-plugin").mkdir()

    assert script.discover_plugins(tmp_path) == [first, second]
