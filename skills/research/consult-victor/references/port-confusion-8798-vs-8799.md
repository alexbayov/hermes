## Distinguishing Viktor from other local services

| Port | Process | What it is | Is Viktor? |
|------|---------|------------|------------|
| **8799** | `socat` (forwards to 127.0.0.1:8799) | Viktor direct endpoint | ✅ Yes |
| **8798** | `hermes-proxy` (Fireworks key rotation) | Returns model `hermes-fireworks` | ❌ No |
| **5000** | `uvicorn` (`/root/toolsapi`) | TempMail + card generator dashboard | ❌ No |
| **7000** | `docker` (Odysseus) | Chat bridge (auth required) | ❌ No |
| **8888** | `python` (unknown backend) | — | ❌ Check first |
| **3264** | `python` (unknown backend) | — | ❌ Check first |
| **8080** | `docker` (SearxNG) | Search engine | ❌ No |
| **8091** | `docker` (ntfy) | Push notifications | ❌ No |
| **8100** | `docker` (ChromaDB) | Vector DB | ❌ No |

**If you see a process on 8798:** Do NOT send Viktor-style requests there. It is the Hermes Dashboard / Fireworks proxy. `curl -H "Authorization: Bearer *** will succeed and return `hermes-fireworks` model, misleading you into thinking Viktor is alive on a different port.

**If you see a process on 5000:** That is `toolsapi` (TempMail + card generator), not Viktor. Do not waste time probing it for chat completions.

**Local services probe (one-liner):**
```bash
ss -tlnp | awk 'NR>1 {print $4}' | sed 's/.*://' | sort -u | while read p; do
  echo "=== port $p ==="
  ss -tlnp | grep ":$p "
done
```
