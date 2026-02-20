---
name: orchestrate
description: Use when the user asks to "orchestrate", "run parallel tasks", "multi-agent execution", "decompose into tasks", or wants to implement complex multi-file features using coordinated agents with git worktrees.
version: 1.1.0
dependencies: rich>=13.0.0
---

# Multi-Agent Orchestration

This skill coordinates parallel task execution for complex multi-file features using git worktrees, DAG-based scheduling, and specialized agents.

## When This Skill Applies

Use this skill when the user wants to:
- Implement features spanning multiple files that can be parallelized
- Use multi-agent coordination for complex tasks
- Decompose a large request into independent parallel tasks
- Execute work in isolated git worktrees

## Pre-Flight Check

Before orchestrating, run a pre-flight check to verify the environment is ready:

```bash
python3 ~/.claude/orchestrator_code/tmux.py preflight
```

This verifies: tmux, claude, git repo, pyyaml, rich, NODE_OPTIONS, and ulimit. Fix any failures before proceeding.

## How to Execute

**Immediately spawn the planner-architect agent** using the Task tool:

```
Task tool parameters:
  subagent_type: "planner-architect"
  model: "opus"
  prompt: <the user's full request>
```

Do not analyze or plan yourself - delegate to the planner-architect agent which has specialized capabilities for this workflow.

## Pipeline Overview

```
User Request
     │
     ▼
PLANNER-ARCHITECT (opus)
├─ Analyze codebase
├─ Decompose into parallel tasks
├─ Generate tasks.yaml + contracts/
├─ Compute risk score
│   └─ 0-25: auto-approve
│   └─ 26-50: recommend review
│   └─ 51+: require approval
     │
     ▼
SUPERVISOR (sonnet)
├─ Opens 3 monitoring windows (Dashboard, Workers, Main)
├─ Create git worktrees (.worktrees/<task-id>/)
├─ Spawn workers in tmux sessions
     │
     ├──────────┼──────────┐
     ▼          ▼          ▼
  WORKER     WORKER     WORKER (sonnet, parallel in tmux)
  task-a     task-b     task-c
     │          │          │
     └──────────┴──────────┘
               │
               ▼
VERIFIER (opus)
├─ Run tests
├─ Validate file boundaries
├─ Check contract versions
├─ Verify environment hash
               │
               ▼
SUPERVISOR → merge verified tasks to main
               │
               ▼
PLANNER-ARCHITECT (Review Mode)
└─ Accept or iterate (max 3 iterations)
```

## Key Concepts

### File Ownership
Each task declares exclusive `files_write` - only that task can modify those files. Prevents merge conflicts.

### Interface Contracts
Cross-task dependencies use Protocol stubs in `contracts/`. Workers code against contracts, not implementations.

### Verification (Per-Task, Before Merge)
Verification happens **per-task, immediately after worker completion** - not batch at the end:
1. Worker marks task `completed`
2. Supervisor spawns Verifier for that task
3. Verifier checks: tests, boundaries, contracts, environment
4. If passed: Supervisor merges to main
5. Repeat for next completed task

## Artifacts Created

- `tasks.yaml` - Task definitions with file/resource ownership
- `contracts/` - Interface Protocol stubs
- `.worktrees/<task-id>/` - Isolated git worktrees (temporary)
- `.orchestration-state.json` - Execution state

## Live Monitoring (Auto-Opens)

When `state.py init` runs, monitoring windows open automatically (use `--no-monitoring` to disable):

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  MAIN AGENT     │  │   DASHBOARD     │  │    WORKERS      │
│  Supervisor/    │  │  Live status    │  │ ┌─────┬───────┐ │
│  Planner runs   │  │  + context      │  │ │wkr-a│ wkr-b │ │
│  here           │  │  window usage   │  │ ├─────┼───────┤ │
│                 │  │                 │  │ │wkr-c│ wkr-d │ │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Prerequisites

- **git** - Must be initialized in project directory
- **tmux** - For parallel worker sessions
- **rich** - Python library for dashboard (`pip install rich`)

## Resuming Interrupted Orchestration

If orchestration was interrupted (user stopped, crash, etc.):

```bash
# See what would be done (dry-run)
python3 ~/.claude/orchestrator_code/state.py resume --dry-run

# Actually resume
python3 ~/.claude/orchestrator_code/state.py resume
```

This will:
1. Reset tasks stuck in "executing" to "pending"
2. Clean up incomplete worktrees and orphaned tmux sessions
3. Reopen monitoring windows
4. Report tasks ready for verification or merge

Then continue from Stage 2 (spawn workers for pending tasks).

## Orchestrator Utilities

Python scripts in `~/.claude/orchestrator_code/`:

| Script | Purpose |
|--------|---------|
| `state.py init` | Initialize state (auto-opens monitoring) |
| `state.py resume` | Resume interrupted orchestration |
| `state.py status` | Check orchestration status |
| `monitoring.py` | Open monitoring windows (dashboard + workers) |
| `dashboard.py` | Live status table with context usage |
| `workers_view.py` | Live worker output (uses capture-pane, not attach) |
| `risk.py` | Compute risk score |
| `conflict.py` | Detect file/resource conflicts |
| `dag.py` | Validate DAG, detect cycles |
| `contracts.py` | Generate Protocol stubs |
| `environment.py` | Compute/verify env hash |
| `tasks.py` | Check task readiness |
| `verify.py` | Full verification suite |
| `context.py` | Shared knowledge store (with file locking) |
| `git.py` | Git operations with abort_merge() |
| `worktree.py` | Worktree management with auto-abort |

### tmux.py Commands (Headless Execution)

| Command | Purpose |
|---------|---------|
| `tmux.py spawn-worker <id> --prompt-file <f> --cwd <d>` | Spawn worker with verified startup |
| `tmux.py verify-running <session>` | Check if process is running (not crashed) |
| `tmux.py monitor <id> --signal-file <f> --timeout <s>` | Poll with timeout enforcement |
| `tmux.py save-logs <session>` | Save pane output before cleanup |
| `tmux.py cleanup-signals` | Remove old .done/.verified files |
| `tmux.py cleanup-orphans` | Kill orphaned worker sessions |
| `tmux.py preflight` | Run pre-flight environment checks |
| `tmux.py list` | List all worker-* sessions |
