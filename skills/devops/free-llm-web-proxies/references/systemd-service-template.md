# Systemd Service Template for Web API Proxies

Copy-pasteable unit for any Node.js reverse-engineered proxy. Replace placeholders in `<angle_brackets>`.

```ini
[Unit]
Description=<Proxy Name> API Proxy
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/<repo-dir>

# Mandatory for headless/VPS: skip interactive menu
Environment=NON_INTERACTIVE=1

# Optional: custom auth path (if not in repo root)
# Environment=DEEPSEEK_AUTH_PATH=/opt/<repo-dir>/<service>-auth.json

# Optional: custom port override
# Environment=PORT=<custom-port>

# Optional: Node env
# Environment=NODE_ENV=production

ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=5

# Security hardening (optional, may need tweaking for Chrome subprocesses)
# NoNewPrivileges=true
# ProtectSystem=strict
# ProtectHome=true

User=root
Group=root

[Install]
WantedBy=multi-user.target
```

## Install commands

```bash
cat > /etc/systemd/system/<service>.service << 'EOF'
[paste unit above]
EOF
systemctl daemon-reload
systemctl start <service>.service
systemctl enable <service>.service
journalctl -u <service>.service -f --no-pager
```

## Common values

| Repo | Service name | Repo dir | Default port | Auth file |
|------|-------------|----------|--------------|-----------|
| FreeQwenApi | `qwen-api` | `/opt/FreeQwenApi` | 3264 | `session/tokens.json` + `session/cookies.json` |
| FreeDeepseekAPI | `deepseek-api` | `/opt/FreeDeepseekAPI` | 9655 | `deepseek-auth.json` |

## Health check

```bash
curl -sf http://localhost:<port>/health || curl -sf http://localhost:<port>/v1/models
```

If either returns non-empty JSON, the proxy is alive and authenticated.
