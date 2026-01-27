---
name: orchestrate
description: Start multi-agent orchestration for complex multi-file features
---

# Multi-Agent Orchestration

Use the **planner-architect** agent to analyze, plan, and orchestrate implementation for:

$ARGUMENTS

## Pipeline Overview

```
planner-architect (opus + ultrahard thinking)
    │
    ├─ Analyze codebase
    ├─ Generate tasks.yaml + contracts/
    ├─ Detect conflicts:  python3 ~/.claude/orchestrator_code/conflict.py
    ├─ Compute risk score: python3 ~/.claude/orchestrator_code/risk.py
    │
    ▼ [If risk ≤ 25: auto-approve, else ask user]
    │
supervisor (sonnet)
    │
    ├─ Create git worktrees
    ├─ Compute env hash: python3 ~/.claude/orchestrator_code/environment.py
    ├─ Init state: python3 ~/.claude/orchestrator_code/state.py init
    ├─ Spawn workers in tmux (TRUE PARALLEL)
    │
    ├────────┬────────┐
    ▼        ▼        ▼
 worker   worker   worker  (sonnet, in tmux)
    │        │        │
    └────────┴────────┘
             │
             ▼
verifier (opus)
    │
    ├─ Verify: python3 ~/.claude/orchestrator_code/verify.py full <task-id>
    ├─ Validate boundaries
    ├─ Check contract versions
    ├─ Verify environment hash
    │
    ▼
supervisor → merge verified tasks
    │
    ▼
planner-architect (Review Mode)
    │
    └─ Accept or iterate (max 3x)
```

## What Gets Created

- `tasks.yaml` - Parallel task definitions with file/resource ownership
- `contracts/` - Interface Protocol stubs for cross-task dependencies
- `.orchestration-state.json` - Execution state tracking
- `.worktrees/<task-id>/` - Isolated git worktrees per task

## Orchestrator Utilities

Reusable Python scripts in `~/.claude/orchestrator_code/`:

| Script | Purpose |
|--------|---------|
| `risk.py` | Compute risk score for approval gate |
| `conflict.py` | Detect file/resource conflicts |
| `dag.py` | Validate DAG, detect cycles, show execution waves |
| `contracts.py` | Generate Protocol contract stubs |
| `environment.py` | Compute/verify environment hash from lockfiles |
| `state.py` | Manage orchestration state |
| `tasks.py` | Check task readiness and status |
| `verify.py` | Full verification suite (boundaries, commands, env) |

## Invocation

**IMPORTANT:** Invoke the planner-architect agent immediately using the Task tool with:
- `subagent_type: "planner-architect"`
- `model: "opus"`
- Pass the full user request as the prompt

The planner-architect will use `~/.claude/orchestrator_code/` utilities for all analysis.
