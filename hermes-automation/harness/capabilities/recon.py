"""DOM-first reconnaissance capability.

HRM-25: Fast interactive element dump for locator selection during authoring.
One call — no polling, no vision. Returns role/label/text/selector for every
visible interactive element on the page.
"""

from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import Page


def dump_interactive(page: Page) -> str:
    """Dump all visible interactive elements as a readable list.

    Uses Playwright accessibility snapshot — cheap, single round-trip.
    Returns formatted text suitable for LLM locator selection.
    """
    snapshot = page.accessibility.snapshot()
    if not snapshot:
        return "(no accessible elements found)"

    elements = _flatten_interactive(snapshot)
    lines = []
    for el in elements:
        lines.append(
            f"[{el.get('role', '?')}] "
            f"name='{el.get('name', '')}' "
            f"text='{el.get('text', '')[:60]}' "
            f"sel='{el.get('selector', '')}'"
        )
    return "\n".join(lines)


def dump_interactive_json(page: Page) -> str:
    """Same as dump_interactive but returns JSON for programmatic use."""
    snapshot = page.accessibility.snapshot()
    if not snapshot:
        return "[]"
    return json.dumps(_flatten_interactive(snapshot), indent=2, ensure_ascii=False)


def _flatten_interactive(node: dict, depth: int = 0) -> list[dict[str, Any]]:
    """Recursively collect interactive nodes from accessibility tree."""
    result = []
    role = node.get("role", "").lower()
    if depth > 20:
        return result

    # Collect buttons, links, textboxes, checkboxes, comboboxes, menuitems
    if role in ("button", "link", "textbox", "checkbox", "combobox",
                "menuitem", "radio", "switch", "tab", "option", "listbox"):
        result.append({
            "role": role,
            "name": node.get("name", ""),
            "text": _node_text(node),
            "selector": _build_selector(node),
            "checked": node.get("checked"),
            "disabled": node.get("disabled"),
        })

    for child in node.get("children", []):
        if isinstance(child, dict):
            result.extend(_flatten_interactive(child, depth + 1))

    return result


def _node_text(node: dict) -> str:
    """Extract visible text from node and children."""
    parts = []
    name = node.get("name", "")
    value = node.get("value", "")
    if name:
        parts.append(str(name))
    if value and value != name:
        parts.append(str(value))
    for child in node.get("children", []):
        if isinstance(child, dict):
            child_text = _node_text(child)
            if child_text:
                parts.append(child_text)
    return " ".join(parts)[:120]


def _build_selector(node: dict) -> str:
    """Build best-effort CSS selector from role and name."""
    role = node.get("role", "")
    name = node.get("name", "")
    if role and name:
        return f'[role="{role}"][aria-label="{name}"]'
    if name:
        return f'[aria-label="{name}"]'
    return ""
