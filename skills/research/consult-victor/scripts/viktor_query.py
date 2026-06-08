"""Direct Viktor query tool — bypasses broken Odysseus proxy.

Uses OpenAI-compatible endpoint at 127.0.0.1:8799 (SSH tunnel) or 172.17.0.1:8799 (socat).
Viktor is SLOW (200-500s) — do not panic, just wait.
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

# Two independent paths to same endpoint
ENDPOINTS = [
    "http://127.0.0.1:8799/v1/chat/completions",
    "http://172.17.0.1:8799/v1/chat/completions",
]
AUTH = "Bearer viktor"
TIMEOUT = 600  # seconds — Viktor writes code for 200-500s


def _probe_endpoints() -> str:
    """Return first live endpoint."""
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(
                url.replace("/chat/completions", "/models"),
                headers={"Authorization": AUTH},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return url
        except Exception:
            continue
    raise RuntimeError("No Viktor endpoint is reachable. Check SSH tunnel / socat.")


def query(
    message: str,
    system: str = "You are a senior software engineer. Provide production-ready code. Be concise, code-only where possible.",
    max_tokens: int = 4000,
    temperature: float = 0.1,
    endpoint: str | None = None,
) -> str:
    """Send atomic question to Viktor. Returns raw text response."""
    url = endpoint or _probe_endpoints()
    body = json.dumps({
        "model": "viktor",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": AUTH},
        method="POST",
    )

    start = time.time()
    print(f"[viktor] Querying {url} (timeout={TIMEOUT}s)...", file=sys.stderr)

    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
        elapsed = time.time() - start
        print(f"[viktor] Response in {elapsed:.1f}s", file=sys.stderr)

        if "choices" not in data:
            raise RuntimeError(f"Unexpected response format: {json.dumps(data)[:500]}")

        return data["choices"][0]["message"]["content"]


def query_file(
    question_path: str,
    output_path: str | None = None,
    **kwargs,
) -> str:
    """Read question from file, write response to file (or stdout)."""
    question = Path(question_path).read_text(encoding="utf-8").strip()
    response = query(question, **kwargs)

    if output_path:
        Path(output_path).write_text(response, encoding="utf-8")
        print(f"[viktor] Wrote {len(response)} chars to {output_path}", file=sys.stderr)
    else:
        print(response)

    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query Viktor directly (bypass Odysseus)")
    parser.add_argument("query", nargs="?", help="Question text (or use --file)")
    parser.add_argument("--file", "-f", help="Read question from file")
    parser.add_argument("--output", "-o", help="Write response to file")
    parser.add_argument("--system", "-s", default="You are a senior software engineer. Provide production-ready code. Be concise, code-only where possible.")
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--endpoint", help="Override endpoint URL")
    args = parser.parse_args()

    if args.file:
        query_file(args.file, args.output, system=args.system, max_tokens=args.max_tokens, temperature=args.temperature, endpoint=args.endpoint)
    elif args.query:
        response = query(args.query, system=args.system, max_tokens=args.max_tokens, temperature=args.temperature, endpoint=args.endpoint)
        if args.output:
            Path(args.output).write_text(response, encoding="utf-8")
            print(f"[viktor] Wrote {len(response)} chars to {args.output}", file=sys.stderr)
        else:
            print(response)
    else:
        parser.print_help()
        sys.exit(1)
