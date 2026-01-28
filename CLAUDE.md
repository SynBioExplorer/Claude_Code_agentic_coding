# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This repository contains the architecture specification for a **Claude Code Multi-Agent Orchestration System** - a design for coordinated parallel task execution using git worktrees, DAG-based scheduling, and automated verification.

The specification is in `ARCHITECTURE_8.md`.

## Architecture Summary

The system consists of five agent types:

1. **Planner-Architect** (opus model): Analyzes requests, designs architecture, decomposes into parallel tasks, generates interface contracts, and performs holistic reviews
2. **Supervisor** (sonnet model): Orchestrates execution, manages worktrees/tmux sessions, monitors progress, handles merges
3. **Worker** (sonnet model): Executes individual tasks in isolated git worktrees
4. **Verifier** (sonnet model): Per-task mechanical validation (tests, boundaries, contracts, environment hash)
5. **Integration-Checker** (sonnet model): Post-merge checks (full test suite, security scanning, type checking)

## Key Concepts

### Physical Isolation
Each worker operates in a separate git worktree under `.worktrees/<task-id>/`

### File + Resource Ownership
Tasks declare `files_write`, `files_read`, `resources_write` to prevent conflicts. Resources are logical identifiers (routes, DI bindings, config keys).

### Structured Patch Intents
Workers submit structured intents for "hot files" (e.g., main.py) instead of raw code. Framework adapters (FastAPI, Express, Spring) generate canonical code with multi-region routing.

### Interface Contracts
Cross-task dependencies use version-stamped interface stubs in `contracts/` directory.

### Verification Requirements
Every task MUST have executable verification commands. The Verifier checks:
- Test execution
- File boundary compliance
- Contract version consistency
- Environment hash matching

### Risk-Based Approval
Plans are scored based on sensitive paths, scale, hot files, dependencies, and test coverage. Auto-approval threshold is configurable (default: 25).

## Configuration

Project configuration lives in `.claude-agents.yaml` with sections for:
- `orchestration`: Model selection, parallelism limits, merge strategy
- `approval`: Risk thresholds and sensitive patterns
- `verification`: Executable check requirements
- `boundaries`: Churn detection, forbidden patterns
- `patch_intents`: Framework adapter settings
- `dependencies`: Ecosystem-specific package management

## Pre-Commit: Global/Local Sync Check

**IMPORTANT**: Before committing changes to this repository, always verify that files are in sync between the global Claude config (`~/.claude/`) and the repo (`.claude/`).

Run this check:
```bash
echo "=== Agents ===" && for f in supervisor.md verifier.md integration-checker.md worker.md planner-architect.md; do diff -q ~/.claude/agents/$f .claude/agents/$f 2>/dev/null && echo "$f: ✓" || echo "$f: DIFFERS"; done && echo "" && echo "=== Orchestrator Code ===" && for f in state.py monitoring.py dashboard.py environment.py verify.py tasks.py dag.py risk.py conflict.py contracts.py; do diff -q ~/.claude/orchestrator_code/$f .claude/orchestrator_code/$f 2>/dev/null && echo "$f: ✓" || echo "$f: DIFFERS"; done && echo "" && echo "=== Skills ===" && diff -q ~/.claude/skills/orchestrate/SKILL.md .claude/skills/orchestrate/SKILL.md 2>/dev/null && echo "SKILL.md: ✓" || echo "SKILL.md: DIFFERS"
```

If files differ, sync them before committing:
- If repo has newer changes: `cp .claude/<path> ~/.claude/<path>`
- If global has newer changes: `cp ~/.claude/<path> .claude/<path>`

This ensures users who install from this repo get the same files that work in the global config.

## Implementation Notes

When implementing this specification:
- Core protocol is language/framework agnostic
- Framework adapters are optional - system falls back to file serialization
- Region markers (`# === AUTO:ROUTERS ===`) are auto-inserted via anchor patterns
- Lockfiles can only be modified by Supervisor, never Workers
- Environment hash ensures all workers use consistent dependencies
