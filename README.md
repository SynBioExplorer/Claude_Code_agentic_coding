# Claude Code Multi-Agent Orchestration System

A parallel task execution system for Claude Code that uses git worktrees, DAG-based scheduling, and coordinated agents to implement complex multi-file features.

## Overview

This system transforms complex requests into coordinated parallel execution:

![Architecture Diagram](architecture.svg)

## Installation

### 1. Copy agents to your global Claude config

```bash
# Clone this repo (or download the .claude folder)
git clone https://github.com/SynBioExplorer/Claude_Code_agentic_coding.git
cd Claude_Code_agentic_coding

# Copy agents
cp -r .claude/agents/* ~/.claude/agents/

# Copy orchestrator utilities
cp -r .claude/orchestrator_code ~/.claude/

# Copy the orchestrate skill
mkdir -p ~/.claude/skills
cp -r .claude/skills/orchestrate ~/.claude/skills/
```

### 2. Verify installation

```bash
# Test the utilities work
python3 ~/.claude/orchestrator_code/contracts.py TestProtocol method1 method2
python3 ~/.claude/orchestrator_code/environment.py

# Should see no errors
```

### 3. Requirements

- **Claude Code CLI** - The main Claude Code application
- **Git** - For worktree management
- **tmux** - For parallel worker execution
- **Python 3.10+** - For orchestrator utilities
- **PyYAML** (optional) - `pip install pyyaml` for YAML parsing

## Usage

### Quick Start - Use the Skill

In any Claude Code session:

```
/orchestrate Add user authentication with JWT tokens and refresh flow
```

This invokes the planner-architect agent which will:
1. Analyze your codebase
2. Create `tasks.yaml` with parallel task definitions
3. Generate interface contracts in `contracts/`
4. Compute risk score and ask for approval if needed
5. Spawn the supervisor to execute

### Manual Invocation

You can also invoke agents directly:

```
Use the planner-architect agent to design an implementation for:
Add a REST API for user management with CRUD operations
```

## Agents

| Agent | Model | Role |
|-------|-------|------|
| `planner-architect` | opus | Analyzes codebase, decomposes into parallel tasks, generates contracts, reviews integration |
| `supervisor` | sonnet | Creates git worktrees, spawns workers in tmux, monitors progress, handles merges |
| `worker` | sonnet | Executes single task in isolated worktree, respects file boundaries |
| `verifier` | opus | Runs tests, validates boundaries, checks contracts and environment hash |

## Orchestrator Utilities

Standalone Python scripts in `~/.claude/orchestrator_code/`:

| Script | Purpose | Example |
|--------|---------|---------|
| `risk.py` | Compute risk score | `python3 ~/.claude/orchestrator_code/risk.py tasks.yaml` |
| `conflict.py` | Detect file/resource conflicts | `python3 ~/.claude/orchestrator_code/conflict.py tasks.yaml` |
| `dag.py` | Validate DAG, show execution waves | `python3 ~/.claude/orchestrator_code/dag.py tasks.yaml` |
| `contracts.py` | Generate Protocol stubs | `python3 ~/.claude/orchestrator_code/contracts.py MyProtocol login logout -o contracts/my.py` |
| `environment.py` | Compute/verify env hash | `python3 ~/.claude/orchestrator_code/environment.py --verify abc123` |
| `state.py` | Manage orchestration state | `python3 ~/.claude/orchestrator_code/state.py status` |
| `tasks.py` | Check task readiness | `python3 ~/.claude/orchestrator_code/tasks.py ready tasks.yaml` |
| `verify.py` | Full verification suite | `python3 ~/.claude/orchestrator_code/verify.py full task-a tasks.yaml` |

All scripts support `--json` for machine-readable output.

## How It Works

### 1. Planning Phase

The planner-architect:
- Analyzes your codebase structure and patterns
- Decomposes the request into independent, parallelizable tasks
- Assigns file ownership (`files_write`) to prevent conflicts
- Generates interface contracts for cross-task dependencies
- Computes risk score for approval gate

### 2. Execution Phase

The supervisor:
- Creates isolated git worktrees (`.worktrees/<task-id>/`)
- Spawns worker agents in tmux sessions for true parallelism
- Monitors progress via `.task-status.json` files

### 3. Verification Phase

The verifier checks each completed task:
- Runs verification commands (tests, linting)
- Validates file boundaries
- Checks contract versions
- Verifies environment hash

### 4. Integration Phase

After all tasks verified:
- Supervisor merges task branches to main
- Planner-architect reviews the integrated result
- Accept or iterate (max 3 iterations)

## Task Specification Format

```yaml
request: "Original user request"
created_at: "2025-01-27T10:00:00Z"

tasks:
  - id: task-auth-service
    description: "Implement authentication service"
    files_write:
      - "src/services/auth.py"
      - "tests/test_auth.py"
    files_read:
      - "src/models/user.py"
    resources_write:
      - "di:AuthService"
    depends_on: []
    verification:
      - command: "pytest tests/test_auth.py"
        type: test
        required: true

  - id: task-auth-routes
    description: "Add authentication routes"
    files_write:
      - "src/routes/auth.py"
    depends_on: [task-auth-service]  # Must wait for service
    verification:
      - command: "pytest tests/test_auth_routes.py"
        type: test
        required: true

contracts:
  - name: "AuthServiceProtocol"
    version: "abc1234"
    file_path: "contracts/auth_interface.py"
```

## Key Concepts

### File & Resource Ownership

Each task declares exclusive ownership of files:
- `files_write` - Files this task will create/modify
- `resources_write` - Logical resources (routes, DI bindings)

Conflicts are detected at planning time. Overlapping ownership requires explicit `depends_on`.

### Interface Contracts

For cross-task dependencies:

```python
# contracts/auth_interface.py
"""
Contract: AuthServiceProtocol
Version: abc1234
"""
from typing import Protocol

class AuthServiceProtocol(Protocol):
    def login(self, username: str, password: str) -> dict:
        """Returns {token: str, expires_at: datetime}"""
        ...
```

Workers code against contracts. Max 2 renegotiations allowed.

### Risk Scoring

| Factor | Weight |
|--------|--------|
| Sensitive paths (auth, security, crypto) | +20 |
| Payment/billing paths | +25 |
| Prod/deploy paths | +30 |
| Many tasks (>5) | +5 per extra |
| Many files (>10) | +3 per extra |
| New dependencies | +3 per package |
| Incomplete test coverage | +20 × (1 - coverage) |

**Thresholds:**
- **0-25**: Auto-approve
- **26-50**: Recommend review
- **51+**: Require approval

## Files Created During Orchestration

```
your-project/
├── tasks.yaml                    # Execution plan
├── contracts/                    # Interface Protocol stubs
│   └── auth_interface.py
├── .orchestration-state.json     # Execution state
└── .worktrees/                   # Isolated worktrees (temporary)
    ├── task-auth-service/
    │   └── .task-status.json
    └── task-auth-routes/
        └── .task-status.json
```

## Troubleshooting

### Check orchestration status
```bash
python3 ~/.claude/orchestrator_code/state.py status
```

### List tmux worker sessions
```bash
tmux list-sessions | grep "worker-"
```

### View worker output
```bash
tmux attach -t "worker-<task-id>"
# Detach with Ctrl-b d
```

### Kill stuck worker
```bash
tmux kill-session -t "worker-<task-id>"
```

### Clean up worktrees
```bash
git worktree list
git worktree remove .worktrees/<task-id>
```

## License

MIT

## See Also

- [ARCHITECTURE_8.md](ARCHITECTURE_8.md) - Full architecture specification
- [.claude/agents/](.claude/agents/) - Agent definitions
- [.claude/orchestrator_code/](.claude/orchestrator_code/) - Utility scripts
