---
name: operating-playbook
description: Fixed meta-loop for web automation tasks — provider check → recipe index → reuse or author → verify → save. Eliminates improvisation.
version: "1.0"
author: alex+eni
platforms: [linux, macos]
metadata:
  hermes:
    tags: [operating-playbook, meta-loop, reuse-first, discipline]
    category: productivity
---

# Operating Playbook — Fixed Meta-Loop

## Purpose

This skill gives Hermes a **fixed, deterministic execution loop** for web automation tasks. Instead of "figuring out what to do" each run, Hermes follows the same 6-step sequence every time. This eliminates improvisation, provider drift, and recipe re-invention.

## Trigger

Activate this skill when:
- A web automation task is assigned ("зарегайся на X", "пройди онбординг на Y")
- A YAML recipe needs to be run or authored
- The `web-automation` skill is needed but you're unsure where to start

## The Loop (6 Steps)

Hermes MUST execute these steps in order. No skipping, no reordering, no improvisation.

### Step 1: Load Task

Extract from the user's request:
- **Domain/URL** of the target site
- **Task description** (e.g., "signup", "onboarding", "form fill")
- **Fields** needed (email, password, etc.)

### Step 2: Check Providers

- Read `config/providers.yaml`
- Verify the configured mail provider is accessible
- Synthesize email address via `mail.get_email_address()` — **NEVER use any other email service**
- If provider is unreachable → escalate to LO, do NOT substitute

### Step 3: Search Recipe Index

- Load `sites/index.yaml`
- Search for a working recipe by domain or task name
- If found AND `status == working` → proceed to Step 4a
- If not found OR `status == broken` → proceed to Step 4b

### Step 4a: Run Existing Recipe

- Load the `site_file` from the index
- Run `run_site_config(...)` with the recipe
- On success → update `last_green` in index
- On failure → mark recipe as broken, then go to Step 4b

### Step 4b: Author New Recipe

- Activate the `web-automation` skill
- Follow the 6-step authoring workflow: recon → chunk → actions → fields_schema → success → test
- Save as `sites/<name>.yaml` — **ALWAYS a YAML recipe, NEVER a standalone .py script**
- Run it

**🚫 Anti-pattern (PROHIBITED):** Writing standalone scripts like `spaceship_v1.py`, `signup_v2.py`, or any manual playwright/selenium code outside `harness/`. These bypass the engine, lose checkpoint/resume, and produce silent multi-iteration stalls. Only YAML recipes are acceptable.

### Step 5: Verify

- Every step must have a `success` postcondition
- On failure: inspect `failure.png` and `trace.zip`
- Fix locators or step logic
- Re-run until green

### Step 6: Save and Update Index

- On successful full-run:
  - Recipe is saved in `sites/<name>.yaml`
  - `sites/index.yaml` is updated: `status: working`, `last_green: now`
- On failure:
  - Recipe is saved but marked `status: broken`
  - Report to LO: what failed, suggested fix

## Integration with SOUL.md

This skill implements rules 9 (providers) and 10 (reuse-first) from SOUL.md. The loop is the **mechanical** implementation of those **mental** rules.

## Integration with web-automation skill

- `web-automation` is used only in Step 4b (authoring).
- This skill provides the **when** and **what order**; `web-automation` provides the **how**.
- Do NOT activate `web-automation` without going through this loop first.

## Provider Discipline (reinforced)

The mail provider is read from `config/providers.yaml` — ONE file, ONE provider. Hermes MUST NOT:
- Choose a different email service
- "Fall back" to another provider if the configured one is down
- Generate an email address outside `mail.get_email_address()`

Provider unreachable → **escalate to LO**, do not improvise.

## Reuse-First Discipline (reinforced)

Before writing a SINGLE line of YAML:
1. Check `sites/index.yaml` for a working recipe matching this domain/task.
2. If found → use it. Even if "it might be slightly different" — run it first, then adjust.
3. Only author a new recipe when the index has no working match.

This eliminates the "starting from scratch every time" antipattern.
