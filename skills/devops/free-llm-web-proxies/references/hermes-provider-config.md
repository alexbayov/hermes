# Hermes Provider Configuration for Free Web Proxies

## Minimal config (config.yaml)

```yaml
providers:
  qwen-free:
    name: "Qwen Free"
    base_url: "http://localhost:3264/v1"
    api_key: "no-auth"
    models:
      qwen-2.5-72b: {}
      qwen-coder: {}

  deepseek-free:
    name: "DeepSeek Free"
    base_url: "http://localhost:9655/v1"
    api_key: "no-auth"
    models:
      deepseek-v4-pro: {}
      deepseek-reasoner: {}
      deepseek-chat-search: {}
```

## Hermes CLI commands

```bash
# Qwen
hermes config set providers.qwen-free.name "Qwen Free"
hermes config set providers.qwen-free.base_url "http://localhost:3264/v1"
hermes config set providers.qwen-free.api_key "no-auth"

# DeepSeek
hermes config set providers.deepseek-free.name "DeepSeek Free"
hermes config set providers.deepseek-free.base_url "http://localhost:9655/v1"
hermes config set providers.deepseek-free.api_key "no-auth"
```

## OmniRoute integration (if using proxy aggregator)

If the proxy supports Anthropic Messages API (e.g. FreeDeepseekAPI has `/anthropic/v1/messages`), you can also route Claude Code or other Anthropic clients through it:

```yaml
providers:
  deepseek-anthropic:
    name: "DeepSeek Anthropic Shim"
    base_url: "http://localhost:9655/anthropic/v1"
    api_key: "no-auth"
```

## Model aliases to map

### FreeQwenApi (port 3264)

- `qwen-2.5-72b` — general chat
- `qwen-coder` — coding tasks

### FreeDeepseekAPI (port 9655)

- `deepseek-chat` — default chat
- `deepseek-v3` — alias for default
- `deepseek-reasoner` / `deepseek-r1` — reasoning mode
- `deepseek-chat-search` — with web search
- `deepseek-reasoner-search` — reasoning + web search
- `deepseek-v4-pro` — V4 Pro model
- `deepseek-expert` — expert mode

Always verify with `curl http://localhost:<port>/v1/models` to see actual live model list.

## Fallback / round-robin pattern

If you have multiple free proxies and want Hermes to failover:

```yaml
providers:
  qwen-free:
    ...
  deepseek-free:
    ...
  # Add official API as fallback with real key
  openrouter:
    base_url: "https://openrouter.ai/api/v1"
    api_key: "${OPENROUTER_KEY}"
```

Hermes will use the first available provider in the configured order; if one is down (auth expired, 502), it will retry with the next.

## Restarting Hermes after provider changes

```bash
# Option 1: reload gateway (if supported)
hermes gateway reload

# Option 2: full restart
hermes restart

# Option 3: just the agent process
pkill -f hermes-agent || true
hermes run
```
