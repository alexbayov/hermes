# Hermes — Development Roadmap

> Единственный источник правды по открытым задачам.  
> Детальные спеки — в отдельных файлах, здесь только статус.

**Аудит:** 2026-06-12 · Верифицировано по фактическому наличию файлов в репо.

---

## Track A · Self-Improvement Loop

**Статус: 🔄 АКТИВНАЯ РАЗРАБОТКА**  
Спек: `plans/gpt55-selfimprovement-loop.md`  
Архитектура: `docs/architecture/self-improvement-loop.md`

| Фаза | Что делает | Файлы | Статус |
|------|-----------|-------|--------|
| 1 | Observation + LoopGuard | `selfimprovement/observation.py`, `loopguard.py` | ✅ Done |
| 2 | Assessment + Strategy | `selfimprovement/assessment.py`, `strategy.py` | ✅ Done |
| 3 | Validation + Rollback | `selfimprovement/validation.py`, `rollback.py` | 🔄 PR #14 |
| 4 | Modification engine | `selfimprovement/modification.py` | 📋 Next |
| 5 | Orchestrator + HTTP API | `selfimprovement/selfimprovement.py` | 📋 Backlog |

---

## Track B · Memory System v2

**Статус: ⏸ ПАУЗА после P0**  
Спек: `plans/eni-memory-v2-spec.md`  
Код P0-слоя: `plans/victor-p0-implementation.md` (уже реализован в `scripts/`)

| Приоритет | Что делает | Файлы | Статус |
|-----------|-----------|-------|--------|
| P0 | DB utils, WAL, миграции | `scripts/db_utils.py`, `init_db.py`, `migrate_schema.py` | ✅ Done |
| P1 | Откат хода | `scripts/rollback_turn.py` | 📋 Не начато |
| P1 | Оптимизация memory.md | обновить `scripts/session_end_start.py` | 📋 Не начато |
| P1 | Оптимизация цепочки контекста | обновить `scripts/resume_context.py` | 📋 Не начато |
| P2 | Компакция сессий | `scripts/compact_parents.py` | 📋 Не начато |
| P2 | Валидация + repair | обновить `scripts/validate_last_turn.py` | 📋 Не начато |
| P3 | Бэкап БД | `scripts/backup_db.py` | 📋 Не начато |
| P3 | Replay journal | обновить `scripts/persist.py` | 📋 Не начато |
| P4 | Journal sync (optional) | `scripts/sync_journal.py` | ⏸ Отложено |

> ⚠️ P1–P3 в спеке `eni-memory-v2-spec.md` помечены чекбоксами `[x]` — файлы **не существуют**.  
> Верифицировано аудитом 2026-06-12. Агент ранее ложно отчитывался о выполнении.

---

## Справочные документы (только чтение)

| Файл | Содержимое |
|------|----------|
| `plans/viktor-architecture-review-2026-06-08.md` | Ревью SQLite-архитектуры от Viktor · главный открытый пункт: `retention.py` |
| `docs/architecture/self-improvement-loop.md` | Диаграмма архитектуры Track A |
| `docs/behavior-exams.md` | Протокол поведенческих тестов агента |
| `docs/decision-log-protocol.md` | Как логируются решения |

---

## Архивировано

| Файл | Причина |
|------|--------|
| `plans/p1-implementation.md` | Устарел — заменён `eni-memory-v2-spec.md` |
| `models.json` | Устарел — роутинг через внутреннюю прокси |
