# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This repository contains the architecture specification for a **Claude Code Multi-Agent Orchestration System** - a design for coordinated parallel task execution using git worktrees, DAG-based scheduling, and automated verification.

The specification is in `ARCHITECTURE_8.md`.

## Architecture Summary

The system consists of four agent types:

1. **Planner-Architect** (opus model): Analyzes requests, designs architecture, decomposes into parallel tasks, generates interface contracts, and performs holistic reviews
2. **Supervisor** (sonnet model): Orchestrates execution, manages worktrees/tmux sessions, monitors progress, handles merges
3. **Worker** (sonnet model): Executes individual tasks in isolated git worktrees
4. **Verifier** (sonnet model): Runs mechanical validation checks (tests, linting, boundary enforcement)

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

## Implementation Notes

When implementing this specification:
- Core protocol is language/framework agnostic
- Framework adapters are optional - system falls back to file serialization
- Region markers (`# === AUTO:ROUTERS ===`) are auto-inserted via anchor patterns
- Lockfiles can only be modified by Supervisor, never Workers
- Environment hash ensures all workers use consistent dependencies
