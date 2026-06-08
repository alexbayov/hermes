#!/bin/bash
# Template: Atomic question to Viktor via direct endpoint (terminal tool, NOT execute_code)
# Why terminal: execute_code times out after ~30s and SYSTEM BLOCKS re-runs after timeout.
# Viktor needs 200-300s. Use terminal with timeout=300.
#
# Usage: write_file this to /tmp/viktor_q.sh, then terminal(command="bash /tmp/viktor_q.sh", timeout=300)

QUESTION="$1"
MAX_TOKENS="${2:-1500}"

PAYLOAD=$(cat <<EOF
{
  "model": "viktor",
  "messages": [{"role": "user", "content": "$QUESTION"}],
  "max_tokens": $MAX_TOKENS
}
EOF
)

resp=$(curl -s -X POST http://127.0.0.1:8799/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer viktor" \
  -d "$PAYLOAD" \
  --max-time 300)

# Extract content safely (OpenAI format)
python3 -c "
import json, sys
try:
    r = json.loads('$resp'.replace(\"'\", \"\\'\"))
    print(r['choices'][0]['message']['content'])
except Exception as e:
    print('RAW:', r)
    print('ERROR:', e)
"
