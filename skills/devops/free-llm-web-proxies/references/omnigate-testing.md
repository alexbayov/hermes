# Testing Local Gateway Endpoints (OmniGate-style)

Use these recipes to verify a local LLM gateway that aggregates multiple upstream text proxies.

## Prerequisites

Gateway running on a known port (e.g. `http://localhost:8888/v1`).

## 1. List available models

```bash
curl -s http://localhost:8888/v1/models | python3 -m json.tool
```

Expected: JSON with `data[].id` and `data[].owned_by`. Confirms upstream proxies are reachable.

## 2. Basic chat completion

```bash
curl -s http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role":"user","content":"ping"}],
    "max_tokens": 50
  }' | python3 -m json.tool
```

Expected: `choices[0].message.content` with a non-empty response. `finish_reason: stop`.

## 3. Tool calling loop

Send a request with `tools` and `tool_choice: auto`:

```bash
curl -s http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-chat",
    "messages": [
      {"role":"user","content":"What is 12345 * 67890?"}
    ],
    "tools": [{
      "type": "function",
      "function": {
        "name": "calculator",
        "description": "Evaluate math",
        "parameters": {
          "type": "object",
          "properties": {
            "expression": {"type":"string"}
          },
          "required": ["expression"]
        }
      }
    }],
    "tool_choice": "auto",
    "max_tokens": 200
  }'
```

Expected: `choices[0].message.tool_calls` array with `name` and `arguments`. `finish_reason: tool_calls`.

Then complete the loop by feeding the tool result back:

```bash
curl -s http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-chat",
    "messages": [
      {"role":"user","content":"What is 12345 * 67890?"},
      {"role":"assistant","content":null,"tool_calls":[{"id":"call_1","type":"function","function":{"name":"calculator","arguments":"{\"expression\":\"12345 * 67890\"}"}}]},
      {"role":"tool","tool_call_id":"call_1","content":"838102050"}
    ],
    "max_tokens": 200
  }'
```

Expected: Final text answer. `finish_reason: stop`.

## 4. Context retention

Include multi-turn history and ask a question referencing an earlier turn:

```json
{"messages": [
  {"role":"user","content":"My name is Alex."},
  {"role":"assistant","content":"Nice to meet you, Alex!"},
  {"role":"user","content":"What is my name?"}
]}
```

Expected: Assistant remembers "Alex".

## 5. Image generation (usually NOT supported)

```bash
curl -s http://localhost:8888/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.7-max","prompt":"a cat","n":1}'
```

If response is `{"detail": "Not Found"}`, the gateway does not proxy image generation. Use a separate image provider (FAL, OpenAI, etc.).

## Quick health check one-liner

```bash
curl -sf http://localhost:8888/v1/models >/dev/null && echo "OK" || echo "DOWN"
```

## Observed behavior with known upstreams

### DeepSeek via FreeDeepseekAPI (port 9655)
- **Tool calling**: Works. Model returns `tool_calls` with `finish_reason: tool_calls`. After feeding `role: tool` result, model finalizes with `finish_reason: stop`.
- **Context retention**: Works across 4+ turns. Model remembers injected facts (e.g., user's name).
- **Streaming**: Supported via SSE.
- **Image generation**: Not supported. `POST /v1/images/generations` returns `{"detail": "Not Found"}`.

### Qwen via FreeQwenApi (port 3264)
- **Text chat**: Works. `qwen3.7-max` and others respond correctly.
- **Tool calling**: Works (model returns `tool_calls` or text depending on prompt).
- **Context retention**: Works.
- **Image generation**: Not supported. Qwen models (even `qwen-vl`) are **vision-capable** (understand images) but **not image-generating**. They cannot produce images.
- **Streaming**: Supported.

### General limitation: text-only gateways
OmniGate-style proxies aggregate text-chat endpoints. They do **not** proxy `/v1/images/generations`. If image generation is needed, use a separate provider (FAL, OpenAI DALL-E, Stable Diffusion, etc.).