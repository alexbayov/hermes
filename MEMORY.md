# Alex's Memory

## Environment

- OS: Ubuntu 26.04 LTS, x86_64
- Shell: bash primary, zsh secondary
- Python: 3.11+, use venv
- Node.js: available via npm/npx
- Git: user.name "alex"

## Bash Conventions

- `set -euo pipefail` in all scripts
- Quote paths with spaces using double quotes
- Prefer `workdir` parameter in bash tool over `cd && cmd`
- JSON-in-curl: use `cat <<'EOF'` (HERE-docs) to avoid quote parsing failures
- Prefer Hermes native tools (read_file, search_files) over shell `grep`/`cat`/`head`/`tail`/`sed`/`awk`

## Python Conventions

- venv for isolated environments, never system pip
- `pathlib.Path` over `os.path`
- `get_hermes_home()` from `hermes_constants` for all HERMES_HOME paths (never hardcode `~/.hermes`)
- `tmp_path` fixtures in tests, not hardcoded `/tmp`

## Project Paths

- Custom workspace: `/home/alex/hermes/` — docs, profile, memory, bin, logs
- Upstream core: `~/.hermes/hermes-agent/` — read-only, never modify directly
- HumanitZ: `~/Загрузки/HumanitZ-InsaneRamZes/` — launcher `~/humanitz.sh`

## Git Rules

- Commits only when explicitly asked
- Inspect `git status`, `git diff`, `git log --oneline -10` before staging
- No force-push, no empty commits, no rebase unless explicitly requested

## Security

- Never log full API keys; reference variable names only
- Credentials in `.env` only, never in markdown/logs/commits

## Hermes Specific

- Testing: use `scripts/run_tests.sh`, never `pytest` directly
- Config lock: `_config_lock: true` in config.yaml means no auto-expansion
- HUP workflow: state → log → work → update → summary
