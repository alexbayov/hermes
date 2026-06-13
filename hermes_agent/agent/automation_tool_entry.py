"""Import shim for hermes-agent/agent/automation_tool_entry.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_HERMES_AGENT = _ROOT / "hermes-agent"
if str(_HERMES_AGENT) not in sys.path:
    sys.path.insert(0, str(_HERMES_AGENT))
_SRC = _HERMES_AGENT / "agent" / "automation_tool_entry.py"
_spec = importlib.util.spec_from_file_location("_hermes_automation_tool_entry", _SRC)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

TOOL_NAME = _module.TOOL_NAME
AUTOMATION_TOOL_DEFINITION = _module.AUTOMATION_TOOL_DEFINITION
handle_run_browser_automation_recipe = _module.handle_run_browser_automation_recipe

__all__ = ["TOOL_NAME", "AUTOMATION_TOOL_DEFINITION", "handle_run_browser_automation_recipe"]
