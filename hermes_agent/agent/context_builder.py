"""Import shim for hermes-agent/agent/context_builder.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "hermes-agent" / "agent" / "context_builder.py"
_spec = importlib.util.spec_from_file_location("_hermes_context_builder", _SRC)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

AutomationContextInput = _module.AutomationContextInput
SkillContext = _module.SkillContext
build_automation_context = _module.build_automation_context
choose_relevant_skills = _module.choose_relevant_skills

__all__ = [
    "AutomationContextInput",
    "SkillContext",
    "build_automation_context",
    "choose_relevant_skills",
]
