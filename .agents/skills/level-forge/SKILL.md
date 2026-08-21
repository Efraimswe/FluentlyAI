---
name: level-forge
description: >-
  Architectural decomposition and quest engine for software engineering projects.
  Transforms any project idea into a 4-tier hierarchy: Master Specs, Level 1 (MVP), Medium Tasks,
  and atomic 2-10 minute Micro-Steps. Tracks progress per level in tasks_level_{N}.json and maintains
  chronological dev logs (completed steps, solved bugs, architectural decisions) in history_level_{N}.json.
  Activates on /forge, /quest, /done, /breakdown, /log commands or when the user asks to plan, track,
  log, or breakdown a software project.
---

# LevelForge: Architectural Quest Engine

LevelForge eliminates developer procrastination and cognitive overload by breaking software projects into atomic, 2–10 minute actionable micro-tasks with dedicated level-by-level task tracking and dev logs.

---

## 1. Directory Structure (`quests/`)

When activated for a project, manage all state in the `quests/` folder at the project root:

```text
quests/
├── master_functional.md     # Complete product vision & functional specification
├── master_technical.md      # Complete system architecture & tech specification
├── level_1_mvp.md           # Level 1 specification (Lean deployable MVP)
├── tasks_level_1.json       # Tasks, micro-steps, progress & streak for Level 1
└── history_level_1.json     # Chronological dev logs: completions, solved bugs, decisions
```

*(When advancing to Level 2, the engine creates `level_2.md`, `tasks_level_2.json`, and `history_level_2.json`)*

---

## 2. Level Tasks Schema (`quests/tasks_level_{N}.json`)

Stores all medium tasks, atomic micro-steps, and progress for the active level:

```json
{
  "version": "1.0.0",
  "project_name": "<Project Name>",
  "current_level": 1,
  "level_title": "Level 1: <MVP Title>",
  "streak_days": 1,
  "last_activity_date": "YYYY-MM-DD",
  "progress": {
    "total_tasks": 0,
    "completed_tasks": 0,
    "total_micro_steps": 0,
    "completed_micro_steps": 0,
    "percentage": 0
  },
  "phases": [
    {
      "id": "phase-1",
      "title": "<Phase Title>",
      "tasks": [
        {
          "id": "TASK-01",
          "title": "<Medium Task Title>",
          "status": "todo | in_progress | done",
          "deliverables": ["path/to/file1", "path/to/file2"],
          "micro_steps": [
            {
              "id": "STEP-01",
              "title": "<Actionable 2-10 min action>",
              "est_minutes": 5,
              "status": "todo | in_progress | done"
            }
          ]
        }
      ]
    }
  ]
}
```

---

## 3. History & Dev Log Schema (`quests/history_level_{N}.json`)

A clean, chronological array of dev log entries for the active level capturing completed steps, tasks, bugs encountered, and applied solutions:

```json
[
  {
    "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
    "type": "PROJECT_INIT | STEP_DONE | TASK_DONE | BUG_SOLVED | DECISION | LEVEL_CLEARED",
    "title": "<Short event title>",
    "details": "<What was completed, what bug was encountered or how it was solved>"
  }
]
```

---

## 4. Command Execution Procedures

### 4.1. `/forge <Project Idea>`
When initializing a project:
1. **Master Specs:** Write `quests/master_functional.md` and `quests/master_technical.md`.
2. **Level 1 MVP Spec:** Write `quests/level_1_mvp.md`.
3. **Tasks File:** Write `quests/tasks_level_1.json` with 4–6 Medium Tasks and decomposed 2–10 min Micro-Steps for the first task.
4. **History Log:** Initialize `quests/history_level_1.json` with `PROJECT_INIT` entry.
5. **Output Initial Dashboard:** Call `/quest` to show the first step.

---

### 4.2. `/quest` (Status & Next Action)
1. Read `quests/tasks_level_{current_level}.json`.
2. Calculate percentage: `Math.round((completed_micro_steps / total_micro_steps) * 100)`.
3. Locate the first micro-step with `status != "done"`.
4. Render the ASCII Dashboard:

```text
┌─────────────────────────────────────────────────────────────┐
│ 🚀 LEVEL {current_level}: {level_title}       🔥 Стрик: {streak_days} дн.│
│ Прогресс: [{filled_bar}{empty_bar}] {percentage}% ({completed}/{total} шагов)│
└─────────────────────────────────────────────────────────────┘

🎯 ТЕКУЩАЯ ТАСКА: [{task_id}] {task_title}

⚡️ СЛЕДУЮЩИЙ ШАГ НА {est_minutes} МИНУТ:
👉 [{step_id}]: {step_title}

💡 ЧТО СДЕЛАТЬ ПРЯМО СЕЙЧАС:
1. {Exact step-by-step instruction}
2. {Exact file path and code snippet to paste or terminal command to run}

Как сделаешь — напиши `/done`.
```

---

### 4.3. `/done [step_id]` (Complete Step & Log)
When a step is completed:
1. **Verify Deliverables:** Check workspace files.
2. **Update Tasks:** Mark step as `"done"` in `quests/tasks_level_{N}.json` and update progress counters.
3. **Write Log:** Append a `STEP_DONE` entry to `quests/history_level_{N}.json`:
   ```json
   {
     "timestamp": "<current ISO time>",
     "type": "STEP_DONE",
     "title": "Completed {step_id}",
     "details": "{step_title}"
   }
   ```
4. **Task / Level Clearance:**
   - If all micro-steps in the task are done: mark task `"done"`, increment `completed_tasks`, log `TASK_DONE`.
   - If all tasks in Level are done: log `LEVEL_CLEARED` and offer to unlock Level 2 (`tasks_level_2.json` / `history_level_2.json`).
5. **Auto-Advance:** Render `/quest` dashboard with next step.

---

### 4.4. Problem & Bug Logging (`BUG_SOLVED` / `DECISION`)
Whenever a problem is encountered and resolved during development:
Append an entry directly to `quests/history_level_{N}.json`:
```json
{
  "timestamp": "<current ISO time>",
  "type": "BUG_SOLVED",
  "title": "<Problem Title>",
  "details": "<What went wrong and what exact solution was applied>"
}
```

---

### 4.5. `/breakdown [task_id]`
Split a large task into 4–8 micro-steps (2–5 mins each) inside `quests/tasks_level_{N}.json`.

---

### 4.6. `/log` or `/history`
Read `quests/history_level_{N}.json` and render the dev log feed:
```text
📜 ИСТОРИЯ И ЛОГИ LEVEL {N}:
• [14:10] 🚀 [PROJECT_INIT] Инициализация 1-го уровня MVP.
• [14:18] ✅ [STEP_DONE] STEP-02: Настроен FastAPI роутер.
• [14:22] 🛠 [BUG_SOLVED] Ошибка CORS при подключении WebSocket — добавлен CORSMiddleware.
• [14:30] 🏆 [TASK_DONE] TASK-02: Настройка бэкенда полностью завершена.
```

---

## 5. Core Behavioral Rules

1. **Zero Cognitive Friction:** Provide exact file names, code snippets, and commands.
2. **Atomic Steps Only:** Every micro-step must take **2–10 minutes**.
3. **Dedicated Level Files:** Never mix tasks or history between different levels.
4. **Live Dev Logs:** Always record solved issues and architectural decisions in `history_level_{N}.json` so no context is ever lost.
5. **Streak Calculation:** If `last_activity_date` is yesterday, increment `streak_days` by 1. If today, keep it. If >1 day, reset to 1.
