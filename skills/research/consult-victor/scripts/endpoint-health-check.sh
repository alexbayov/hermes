#!/usr/bin/env bash
# Quick health check for Viktor direct endpoint.
# Returns 0 if at least one endpoint responds with a valid model list.
# Returns 1 if both endpoints are dead.

AUTH="Bearer viktor"
TIMEOUT=5

for url in "http://127.0.0.1:8799/v1/models" "http://172.17.0.1:8799/v1/models"; do
    resp=$(curl -s --max-time "$TIMEOUT" "$url" -H "Authorization: $AUTH" 2>/dev/null)
    if echo "$resp" | grep -q '"id":"viktor"'; then
        echo "Viktor direct ($url): READY"
        exit 0
    fi
done

echo "Viktor direct: DOWN — both endpoints unresponsive"
echo "Hints:"
echo "  ss -tlnp | grep 8799   # check listener"
echo "  docker ps | grep viktor  # check container"
echo "  ps aux | grep viktor     # check process"
exit 1
