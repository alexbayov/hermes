#!/usr/bin/env bash
# token-check.sh — Verify GitHub PAT before using it for git operations
# Usage: bash token-check.sh <TOKEN>
# Exit 0 = token valid, 1 = invalid/expired, 2 = missing repo scope

TOKEN="${1:-$GITHUB_TOKEN}"
if [ -z "$TOKEN" ]; then
  echo "error: No token provided. Pass as arg or set GITHUB_TOKEN env var."
  exit 1
fi

RESP=$(curl -s -w "\n%{http_code}" -H "Authorization: token $TOKEN" https://api.github.com/user)
BODY=$(echo "$RESP" | sed '$d')
HTTP_CODE=$(echo "$RESP" | tail -n1)

if [ "$HTTP_CODE" != "200" ]; then
  echo "error: Token invalid (HTTP $HTTP_CODE). $BODY"
  echo "Check: https://github.com/settings/tokens"
  echo "Generate a CLASSIC token with 'repo' scope (fine-grained tokens do NOT work for git push)."
  exit 1
fi

LOGIN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('login','unknown'))" 2>/dev/null || echo "unknown")
echo "Token valid for user: $LOGIN"

# Check scopes (returned in x-oauth-scopes header)
SCOPES=$(curl -s -I -H "Authorization: token $TOKEN" https://api.github.com/user | grep -i "x-oauth-scopes" | sed 's/x-oauth-scopes: //i' | tr -d '\r')
if [ -n "$SCOPES" ]; then
  echo "Scopes: $SCOPES"
  if ! echo "$SCOPES" | grep -q "repo"; then
    echo "warning: Token lacks 'repo' scope. Git push will fail."
    exit 2
  fi
fi

echo "Token OK for git operations."
exit 0
