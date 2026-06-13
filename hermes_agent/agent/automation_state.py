"""Import shim for hermes-agent/agent/automation_state.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "hermes-agent" / "agent" / "automation_state.py"
_spec = importlib.util.spec_from_file_location("_hermes_automation_state", _SRC)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

AutomationTaskStateUpdate = _module.AutomationTaskStateUpdate
state_from_automation_payload = _module.state_from_automation_payload
write_automation_task_state = _module.write_automation_task_state

__all__ = [
    "AutomationTaskStateUpdate",
    "state_from_automation_payload",
    "write_automation_task_state",
]
