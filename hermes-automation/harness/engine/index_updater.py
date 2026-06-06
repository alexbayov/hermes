"""Recipe index management.

HRM-21: Maps domain/task → sites/*.yaml. Updated on successful runs.
Called from CLI/runner wrapper, NOT from executor (keeps engine domain-agnostic).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("hermes.index")

DEFAULT_INDEX_PATH = Path(__file__).parent.parent.parent / "sites" / "index.yaml"


def load_index(index_path: str | Path | None = None) -> dict:
    """Load the recipe index."""
    path = Path(index_path or DEFAULT_INDEX_PATH)
    if not path.exists():
        return {"recipes": {}}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"recipes": {}}


def find_recipe(
    domain: str,
    task: str | None = None,
    index_path: str | Path | None = None,
) -> dict | None:
    """Find a working recipe by domain (exact match) or task name."""
    idx = load_index(index_path)
    recipes = idx.get("recipes", {})

    # Exact match by domain
    for name, recipe in recipes.items():
        if recipe.get("domain") == domain and recipe.get("status") == "working":
            return recipe

    # Match by task name
    if task:
        for name, recipe in recipes.items():
            if recipe.get("task") == task and recipe.get("status") == "working":
                return recipe

    return None


def update_recipe_status(
    recipe_name: str,
    *,
    status: str = "working",
    domain: str | None = None,
    task: str | None = None,
    site_file: str | None = None,
    index_path: str | Path | None = None,
) -> None:
    """Atomically update recipe status/date in the index.

    Called after a successful run (result.success is True).
    """
    path = Path(index_path or DEFAULT_INDEX_PATH)
    idx = load_index(path)

    if recipe_name not in idx.get("recipes", {}):
        idx.setdefault("recipes", {})[recipe_name] = {}

    recipe = idx["recipes"][recipe_name]
    recipe["status"] = status
    recipe["last_green"] = datetime.now(timezone.utc).isoformat()

    if domain is not None:
        recipe["domain"] = domain
    if task is not None:
        recipe["task"] = task
    if site_file is not None:
        recipe["site_file"] = site_file

    # Atomic write
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(idx, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def mark_recipe_broken(
    recipe_name: str,
    index_path: str | Path | None = None,
) -> None:
    """Mark a recipe as broken."""
    update_recipe_status(recipe_name, status="broken", index_path=index_path)
