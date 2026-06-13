"""Import shim for hermes-agent/agent/automation_tool.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "hermes-agent" / "agent" / "automation_tool.py"
_spec = importlib.util.spec_from_file_location("_hermes_automation_tool", _SRC)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

AutomationRunRequest = _module.AutomationRunRequest
AutomationRunResult = _module.AutomationRunResult
AutomationToolError = _module.AutomationToolError
build_automation_command = _module.build_automation_command
run_automation_recipe = _module.run_automation_recipe
summarize_automation_result = _module.summarize_automation_result

__all__ = [
    "AutomationRunRequest",
    "AutomationRunResult",
    "AutomationToolError",
    "build_automation_command",
    "run_automation_recipe",
    "summarize_automation_result",
]
