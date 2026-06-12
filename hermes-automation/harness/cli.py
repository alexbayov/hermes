"""Command line interface for Hermes automation harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from harness.engine.executor import run_site_config
from harness.engine.result import result_to_dict


def _load_fields(value: str | None) -> dict[str, Any]:
    """Load input fields from a JSON/YAML file or inline JSON object."""
    if not value:
        return {}

    candidate = Path(value)
    if candidate.exists():
        text = candidate.read_text(encoding="utf-8")
        if candidate.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(text) or {}
        else:
            data = json.loads(text or "{}")
    else:
        data = json.loads(value)

    if not isinstance(data, dict):
        raise ValueError("fields must be a JSON/YAML object")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes-automation",
        description="Run declarative Hermes web automation recipes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a site YAML recipe and print JSON result")
    run.add_argument("--recipe", required=True, help="Path to sites/*.yaml recipe")
    run.add_argument("--task-id", required=True, help="Stable task/checkpoint id")
    run.add_argument(
        "--fields",
        help="JSON/YAML file path or inline JSON object with recipe field values",
    )
    run.add_argument("--state-dir", default="state", help="Checkpoint directory")
    run.add_argument("--artifacts-dir", default="artifacts", help="Artifacts directory")
    run.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--reset", action="store_true", help="Discard previous checkpoint")
    run.add_argument("--executable-path", help="Chrome/Chromium executable path")
    run.add_argument(
        "--no-actions",
        action="store_true",
        help="Omit per-action results from JSON output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        fields = _load_fields(args.fields)
        result = run_site_config(
            args.recipe,
            task_id=args.task_id,
            fields=fields,
            state_dir=args.state_dir,
            artifacts_dir=args.artifacts_dir,
            headless=args.headless,
            reset=args.reset,
            executable_path=args.executable_path,
        )
        payload = result_to_dict(
            result,
            state_dir=args.state_dir,
            include_actions=not args.no_actions,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if result.success else 2

    parser.error(f"unknown command: {args.command}")
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
