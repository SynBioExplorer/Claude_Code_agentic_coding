---
name: orchestrate
description: Start multi-agent orchestration for complex multi-file features
---

# Multi-Agent Orchestration

Use the **planner-architect** agent to analyze, plan, and orchestrate implementation for:

$ARGUMENTS

The planner-architect will:
1. Analyze the codebase structure and patterns
2. Design the architecture and interface contracts
3. Decompose into parallel tasks with file/resource ownership
4. Generate `tasks.yaml` and contracts
5. Spawn the supervisor to execute workers in parallel via tmux
6. Review the integrated result and iterate if needed (max 3 iterations)

**IMPORTANT:** Invoke the planner-architect agent immediately using the Task tool with:
- `subagent_type: "planner-architect"`
- `model: "opus"`
- Pass the full user request as the prompt
