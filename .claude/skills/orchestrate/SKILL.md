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

### Verification
Every task must have verification commands (tests). The verifier runs them before allowing merge.

## Artifacts Created

- `tasks.yaml` - Task definitions with file/resource ownership
- `contracts/` - Interface Protocol stubs
- `.worktrees/<task-id>/` - Isolated git worktrees (temporary)
- `.orchestration-state.json` - Execution state

## Live Monitoring (Auto-Opens)

When orchestration starts, 3 terminal windows open automatically:

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

## Orchestrator Utilities

Python scripts in `~/.claude/orchestrator_code/`:

| Script | Purpose |
|--------|---------|
| `dashboard.py` | Live monitoring with context usage |
| `risk.py` | Compute risk score |
| `conflict.py` | Detect file/resource conflicts |
| `dag.py` | Validate DAG, detect cycles |
| `contracts.py` | Generate Protocol stubs |
| `environment.py` | Compute/verify env hash |
| `state.py` | Manage orchestration state |
| `tasks.py` | Check task readiness |
| `verify.py` | Full verification suite |
