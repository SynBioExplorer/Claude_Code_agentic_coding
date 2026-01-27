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
    ├─ Detect conflicts (embedded Python)
    ├─ Compute risk score (embedded Python)
    │
    ▼ [If risk ≤ 25: auto-approve, else ask user]
    │
supervisor (sonnet)
    │
    ├─ Create git worktrees
    ├─ Compute environment hash
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
    ├─ Run verification commands
    ├─ Validate boundaries (embedded Python)
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

## Invocation

**IMPORTANT:** Invoke the planner-architect agent immediately using the Task tool with:
- `subagent_type: "planner-architect"`
- `model: "opus"`
- Pass the full user request as the prompt

The planner-architect has all algorithms embedded as executable Python - no external dependencies required.
