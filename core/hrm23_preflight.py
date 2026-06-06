"""
hrm23_preflight.py — Cheap Insurance / Preflight Layer for Hermes.

Checks at startup:
1. Config lock is enabled (config_lock must be true)
2. Provider base URL and default model are set (OpenAI-compatible via Fireworks)
3. Tool-loop guardrails are active (warnings + hard-stop)
4. Memory limits are configured (char_limit 2200, flush_min_turns 6)
5. Token budget sanity (max_turns set)
6. Quick network connectivity check to the provider endpoint

Returns a dict with pass/fail per check and a summary boolean.
"""

import os
import sys
import yaml
import httpx
from pathlib import Path
from typing import Any, Dict


CONFIG_PATH = Path(os.environ.get("HERMES_HOME", "/home/alex/hermes/profile")) / "config.yaml"


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    """Load and return the Hermes profile config."""
    if not path.exists():
        raise FileNotFoundError(f"Config not found at {path}")
    with open(path, "r") as f:
        return yaml.safe_load(f)


def check_config_lock(config: Dict[str, Any]) -> Dict[str, Any]:
    """Verify _config_lock is true."""
    locked = config.get("_config_lock", False)
    return {"check": "config_lock", "passed": locked is True, "detail": "enabled" if locked else "DISABLED — config can be modified at runtime without guard"}


def check_provider(config: Dict[str, Any]) -> Dict[str, Any]:
    """Verify provider is configured (OpenAI-compatible via Fireworks)."""
    model = config.get("model", {})
    base_url = model.get("base_url", "")
    default_model = model.get("default", "")
    provider = model.get("provider", "")
    errors = []
    if not base_url:
        errors.append("Missing base_url")
    if not default_model:
        errors.append("Missing default model")
    if not provider:
        errors.append("Missing provider")
    return {
        "check": "provider",
        "passed": len(errors) == 0,
        "detail": f"{provider} / {default_model}" if not errors else "; ".join(errors),
    }


def check_tool_loop_guardrails(config: Dict[str, Any]) -> Dict[str, Any]:
    """Verify tool-loop guardrails are active (warnings + hard-stop)."""
    guardrails = config.get("tool_loop_guardrails", {})
    warnings = guardrails.get("warnings_enabled", False)
    hard_stop = guardrails.get("hard_stop_enabled", False)
    errors = []
    if not warnings:
        errors.append("warnings_enabled is false")
    if not hard_stop:
        errors.append("hard_stop_enabled is false")
    return {
        "check": "tool_loop_guardrails",
        "passed": warnings and hard_stop,
        "detail": "warnings + hard-stop active" if not errors else "; ".join(errors),
    }


def check_memory_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    """Verify memory context size enforcer (2200 chars, flush after 6 turns)."""
    memory = config.get("memory", {})
    char_limit = memory.get("memory_char_limit", 0)
    flush_turns = memory.get("flush_min_turns", 0)
    errors = []
    if char_limit != 2200:
        errors.append(f"memory_char_limit={char_limit} (expected 2200)")
    if flush_turns != 6:
        errors.append(f"flush_min_turns={flush_turns} (expected 6)")
    return {
        "check": "memory_limits",
        "passed": len(errors) == 0,
        "detail": f"char_limit={char_limit}, flush_turns={flush_turns}" if not errors else "; ".join(errors),
    }


def check_token_budget(config: Dict[str, Any]) -> Dict[str, Any]:
    """Verify max_turns is set (basic token budget sanity)."""
    agent = config.get("agent", {})
    max_turns = agent.get("max_turns", 0)
    return {
        "check": "token_budget",
        "passed": max_turns > 0,
        "detail": f"max_turns={max_turns}" if max_turns > 0 else "max_turns not set — unlimited turns risk unbounded cost",
    }


async def check_connectivity(base_url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Quick network check to the provider endpoint."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # HEAD /v1/models to verify endpoint is reachable, not a full auth test
            resp = await client.head(f"{base_url.rstrip('/')}/models")
            return {
                "check": "connectivity",
                "passed": resp.status_code < 500,
                "detail": f"HTTP {resp.status_code}" if resp.status_code < 500 else f"server error HTTP {resp.status_code}",
            }
    except httpx.TimeoutException:
        return {"check": "connectivity", "passed": False, "detail": "timeout"}
    except httpx.ConnectError:
        return {"check": "connectivity", "passed": False, "detail": "connection refused"}
    except Exception as e:
        return {"check": "connectivity", "passed": False, "detail": str(e)}


async def run_all(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Run all preflight checks and return a summary dict."""
    if config is None:
        config = load_config()

    results = [
        check_config_lock(config),
        check_provider(config),
        check_tool_loop_guardrails(config),
        check_memory_limits(config),
        check_token_budget(config),
    ]

    # Connectivity requires the provider URL
    base_url = config.get("model", {}).get("base_url", "")
    if base_url:
        conn_result = await check_connectivity(base_url)
        results.append(conn_result)
    else:
        results.append({"check": "connectivity", "passed": False, "detail": "skipped — no base_url configured"})

    all_passed = all(r["passed"] for r in results)
    return {"passed": all_passed, "checks": results}


def format_report(summary: Dict[str, Any]) -> str:
    """Pretty-print the preflight report."""
    lines = []
    status = "✅ ALL CHECKS PASSED" if summary["passed"] else "❌ SOME CHECKS FAILED"
    lines.append(f"HRM-23 Preflight: {status}")
    lines.append("")
    for c in summary["checks"]:
        icon = "✅" if c["passed"] else "❌"
        lines.append(f"  {icon}  {c['check']}: {c['detail']}")
    return "\n".join(lines)


# ---- CLI entry point ----
if __name__ == "__main__":
    import asyncio

    try:
        cfg = load_config()
    except FileNotFoundError as e:
        print(f"FATAL: {e}")
        sys.exit(1)

    report = asyncio.run(run_all(cfg))
    print(format_report(report))
    sys.exit(0 if report["passed"] else 1)