# Skill Priority System (HUP-11)

## Priority Order

1. **User-authored skills** in `/home/alex/hermes/memory/skills/` — highest priority, override everything
2. **Clean profile skills** in `/home/alex/hermes/skills/` — standard workspace skills
3. **Bundled/upstream optional skills** — from `~/.hermes/hermes-agent/optional-skills/` — enabled explicitly via `hermes skills install`
4. **Legacy archive** — old Sonya/B17/temp-mail/news skills — **never loaded unless Alex explicitly asks**

## Loading Rules

- Same name/domain: user skill wins over bundled
- Discovery: Hermes CLI scans `memory/skills/`, `skills/`, then `optional-skills/`
- `SKILL.md` frontmatter must contain `name`, `description`, `version`, `author`
- Legacy skills without `metadata.hermes.category` are treated as lowest priority

## Cleanup

```bash
# List all loaded skills with source path
hermes skills list

# Identify legacy skills (no modern frontmatter)
find ~/.hermes/skills -name SKILL.md -exec grep -L "metadata.hermes" {} \;

# Archive legacy skills
mv ~/.hermes/skills/sonya-legacy ~/.hermes/skills/.archive/
```

## Adding a User Skill

```bash
mkdir -p /home/alex/hermes/memory/skills/<skill-name>
# Write SKILL.md with frontmatter
# Hermes auto-discovers on next start
```
