# Viktor Direct Endpoint Troubleshooting

## Problem: both endpoints return empty / connection refused

**Symptoms:**
```bash
curl -s http://127.0.0.1:8799/v1/models -H "Authorization: Bearer viktor"
# → connection refused (exit 7) OR empty response (exit 52)

curl -s http://172.17.0.1:8799/v1/models -H "Authorization: Bearer viktor"
# → same failure
```

**Root causes checked in this session (2026-06-11):**
1. `ss -tlnp | grep 8799` showed `socat` listening — but backend process was dead
2. `docker ps` / `docker ps -a` — no Victor-related containers running or stopped
3. `ps aux | grep -i 'viktor|claude'` — no inference backend process found
4. `lsof -i :8799` — only `socat` held the port, nothing behind it

**Diagnosis:** Socat listens on `172.17.0.1:8799` and forwards to `127.0.0.1:8799`. If the SSH tunnel (127.0.0.1:8799 → remote Victor) is dead, both paths fail. Socat creates the *illusion* of a live port because it binds and accepts connections, but then has nowhere to forward.

**Resolution path:**
1. Determine if the backend is dockerized or bare-metal
2. Check systemd / supervisord / screen sessions for the Victor inference process
3. If no process found — **inform user immediately** that Victor is offline and offer local execution or delayed retry

## Time limit policy

**Do NOT spend more than 2 minutes probing endpoint availability.**
- 1 quick curl to each endpoint (5s timeout)
- 1 check of `ss` / `docker ps` / `ps` if curls fail
- If all dead → report to user and fallback

Spending 10+ minutes on fruitless endpoint probing was a major time sink in the 2026-06-11 session. The user prefers fast failure + local execution over long debugging of external infrastructure.

**Transparency rule:** After 2–3 failed probes, pause and tell the user exactly what was checked (e.g., "127.0.0.1:8799 refused, 172.17.0.1:8799 refused, no docker container, no matching process"). Ask for direction before continuing. Silent iteration beyond this point frustrates the user.
