# Manual External Delegation — Prompt Template

## When to use

All primary strong-model paths (Victor, Qwen, etc.) are down. The user has access to a high-capability external model (GPT-5.5, Claude Desktop, Cursor Pro, etc.) and wants to delegate architecture or code generation **manually** via copy-paste.

## Prompt anatomy

A delegation prompt must be **self-contained** — the external model has zero context about your project, tooling, or prior conversations. Every byte of necessary context must be in the prompt.

### 1. Role & Persona (1 paragraph)
- Who the model should be (e.g., "staff/principal system architect")
- Domain and constraints

### 2. Explicit Deliverables (numbered list)
- Exact files, classes, functions, modules expected
- File names and responsibilities

### 3. Technical Requirements (bullet list)
- Language version, runtime, concurrency model
- Frameworks and versions (Pydantic v2, FastAPI, etc.)
- Storage, observability, deployment targets

### 4. Data Models (Pydantic / dataclass specs)
- Every model the system operates on
- Field names, types, optional/required, validation rules

### 5. Architecture Principles (5–7 max)
- How the system should behave under failure
- Guarantees (backward compatibility, reproducibility, idempotence)

### 6. Integration Points (bullet list)
- Event sources, notification sinks, config files, API endpoints
- Contract expectations

### 7. Output Format (explicit sections)
- Architecture Overview (Mermaid / PlantUML diagrams)
- Component Breakdown (interface + key methods per component)
- Data Flow (sequence diagram)
- Implementation Plan (order, dependencies, test strategy)
- Appendix: Full Code (production-ready, copy-paste ready)

### 8. Quality Gates (checklist style)
- Type hints on all public methods
- Docstrings (Google / NumPy style)
- Custom exception hierarchy
- Structured logging (JSON formatter)
- Test target coverage
- Security constraints (no eval, no arbitrary execution, sandbox)

### 9. Constraints & No-Go List
- What the model must NOT do (external API calls, cloud dependencies, eval)
- Resource limits (CPU, memory)
- Scope boundaries

### 10. Language & Tone (1 sentence)
- Russian or English
- Concise vs verbose preference

## Concrete example (2026-06-12 session)

**Task**: Design a production-ready `self-improvement` module for an AI assistant.
**Target model**: GPT-5.5
**Result**: 5.9 KB prompt → full architecture document with 8 Python modules.

### Deliverables used in that session

1. `loopguard.py` — cycle/stall detection via SHA1 fingerprinting + ring buffer
2. `observation.py` — metrics collection (latency, errors, intent drift) → SQLite/JSONL
3. `assessment.py` — quality scoring, comparative analysis, ROI calculator
4. `strategy.py` — improvement strategy generator, A/B framework, constraint checking
5. `modification.py` — AST-based safe code patching, git integration, backups
6. `validation.py` — unit + integration tests, drift detection, perf regression
7. `rollback.py` — time-travel state recovery, cascading rollback, integrity checks
8. `selfimprovement.py` — orchestrator event loop, scheduler, circuit breaker

### Tech stack specified
- Python 3.11+, asyncio
- Pydantic v2, SQLite, GitPython, AST/libcst, FastAPI, prometheus-client

### Architecture principles specified
- **Fail-safe**: sandboxed validation before merge, one-call rollback
- **Observability**: full trace for every decision (why, what, when, result)
- **Incremental**: small patches, frequent measurement, fast feedback
- **Human-in-the-loop**: critical mods require approval, rest is autonomous
- **Deterministic**: seed control, reproducible builds, idempotent operations

### Data models specified
- `Observation`, `AssessmentResult`, `Strategy`, `Modification`, `ValidationReport`, `RollbackPoint`

### Quality gates specified
- Google-style docstrings, 80%+ pytest coverage, structlog JSON, no eval, custom exceptions

### No-go list
- No external AI API calls from components (self-contained)
- Local filesystem only, no cloud deps
- CPU/memory efficient (fixed-size ring buffer, bounded queues)
- Backward compatible: module failure must not crash the main system

## Post-delegation agent workflow

After the user pastes the response:

1. **Extract** code blocks into files using `write_file` / `patch`
2. **Validate** each with `python3 -m py_compile`
3. **Test** with `pytest` if available
4. **Commit** to feature branch (`git checkout -b feature/...`)
5. **Push** and open PR (`gh pr create`)
6. **Monitor CI**, fix failures, merge when green

## Pitfalls learned

- **Do NOT assume the external model remembers anything** — each prompt must be fully self-contained. Even schema/table names must be re-defined if needed in a follow-up.
- **Size limit**: some UIs truncate very long prompts. If the prompt exceeds the model's context window or the chat UI limit, split into: (a) architecture overview first, (b) code component-by-component in subsequent messages.
- **Code formatting**: explicitly ask for ` ```python ` code blocks so extraction is trivial.
- **Diagrams**: Mermaid works in most chat UIs; PlantUML requires a renderer.
- **Security reminder**: always include the no-go list, especially `no eval` and `no arbitrary code execution`. Production-grade models sometimes generate dangerous patterns (e.g., `eval(patches)`) unless explicitly forbidden.
