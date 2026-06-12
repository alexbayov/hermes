#!/usr/bin/env python3
"""Extract Supabase/Firebase/Auth0 config from a SPA's minified JS bundle.

Usage:
    python3 extract-supabase-key.py /path/to/bundle.js

Outputs:
    /tmp/supabase_candidates.json   — all candidate keys with lengths
    /tmp/supabase_best_key.txt      — the most likely anon key (if found)
"""
import re, sys, json, base64
from pathlib import Path


def find_jwt_candidates(text: str) -> list:
    """Find all strings that look like JWT tokens and return (token, length)."""
    matches = re.finditer(r'eyJ[a-zA-Z0-9_-]+', text)
    candidates = []
    for m in matches:
        tok = m.group(0)
        if len(tok) > 100:
            candidates.append((tok, len(tok)))
    seen = set()
    unique = []
    for tok, ln in candidates:
        if tok not in seen:
            seen.add(tok)
            unique.append((tok, ln))
    return unique


def decode_jwt_payload(token: str) -> str | None:
    parts = token.split('.')
    if len(parts) < 2:
        return None
    payload = parts[1]
    pad = 4 - (len(payload) % 4)
    if pad != 4:
        payload += '=' * pad
    try:
        return base64.urlsafe_b64decode(payload).decode('utf-8', errors='ignore')
    except Exception:
        return None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/kimchi.js'
    text = Path(path).read_text()

    candidates = find_jwt_candidates(text)
    candidates.sort(key=lambda x: x[1], reverse=True)

    report = []
    best_key = None
    for tok, ln in candidates[:20]:
        payload = decode_jwt_payload(tok)
        hint = ""
        if payload:
            if '"supabase"' in payload:
                hint = "supabase"
            elif '"firebase"' in payload:
                hint = "firebase"
            elif '"auth0"' in payload or '"role":"anon"' in payload:
                hint = "auth"
        report.append({"length": ln, "hint": hint, "token_preview": tok[:60] + "...", "payload_preview": payload[:100] if payload else None})
        if not best_key and hint:
            best_key = tok

    Path('/tmp/supabase_candidates.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Found {len(candidates)} JWT candidates. Top 20 written to /tmp/supabase_candidates.json")

    if best_key:
        Path('/tmp/supabase_best_key.txt').write_text(best_key)
        print(f"Best key ({len(best_key)} chars) saved to /tmp/supabase_best_key.txt")
        print("First 60 chars:", best_key[:60])
    else:
        print("No recognizable auth key found in top candidates.")


if __name__ == '__main__':
    main()
