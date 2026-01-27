# Claude Code Multi-Agent Orchestration System

A coordinated multi-agent system for Claude Code that enables parallel task execution with intelligent dependency management, git worktree isolation, and automated review cycles.

## Overview

This system transforms complex multi-file features into coordinated parallel execution with deterministic, conflict-free merging. It uses:

- **Git Worktrees** for physical isolation between workers
- **DAG-Based Scheduling** for intelligent parallelism
- **Interface Contracts** for safe cross-task dependencies
- **Structured Patch Intents** for hot file modifications
- **Risk-Based Approval Gates** for safe automation

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER REQUEST                                    │
│                     "Add authentication + dashboard"                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PLANNER-ARCHITECT (opus)                            │
│  Analyzes codebase → Designs architecture → Generates contracts → Task DAG   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            SUPERVISOR (sonnet)                               │
│  Creates worktrees → Spawns workers → Monitors progress → Handles merges     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│    WORKER A         │ │    WORKER B         │ │    WORKER C         │
│  .worktrees/task-a  │ │  .worktrees/task-b  │ │  .worktrees/task-c  │
└─────────────────────┘ └─────────────────────┘ └─────────────────────┘
                │                   │                   │
                └───────────────────┼───────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            VERIFIER (sonnet)                                 │
│  Runs tests → Checks boundaries → Validates contracts → Reports pass/fail    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd Claude_Code_agentic_coding

# Install with pip
pip install -e .

# Or with uv
uv pip install -e .
```

## Quick Start

### 1. Initialize Configuration

```bash
claude-orchestrate init
```

This creates `.claude-agents.yaml` with default settings.

### 2. Create an Execution Plan

```bash
claude-orchestrate plan "Add user authentication with JWT tokens"
```

The Planner-Architect will:
- Analyze your codebase
- Design the implementation
- Generate `tasks.yaml` with parallel tasks
- Create interface contracts in `contracts/`

### 3. Validate the Plan

```bash
claude-orchestrate validate tasks.yaml
```

This checks for:
- Valid YAML structure
- No circular dependencies
- No file/resource conflicts
- Risk assessment

### 4. Monitor Progress

```bash
claude-orchestrate status
```

Shows the current orchestration state, task statuses, and any errors.

### 5. Clean Up

```bash
claude-orchestrate cleanup
```

Removes stale worktrees and tmux sessions.

## Configuration

### `.claude-agents.yaml`

```yaml
orchestration:
  planner_model: "opus"
  supervisor_model: "sonnet"
  worker_model: "sonnet"
  verifier_model: "sonnet"
  max_parallel_workers: 5
  max_iterations: 3

approval:
  auto_approve_threshold: 25
  sensitive_patterns:
    - pattern: "auth|security|crypto"
      weight: 20
    - pattern: "payment|billing"
      weight: 25

verification:
  require_executable_checks: true
  min_checks_per_task: 1

boundaries:
  reject_excessive_churn: true
  churn_threshold_lines: 500

dependencies:
  verify_env_hash: true
  ecosystems:
    python:
      manager: "uv"
      lockfile: "uv.lock"
```

## Key Concepts

### File & Resource Ownership

Each task declares which files and resources it will modify:

```yaml
tasks:
  - id: task-auth
    files_write:
      - "src/services/auth.py"
      - "src/routes/auth.py"
    resources_write:
      - "route:/auth"
      - "di:AuthService"
```

Conflicts are detected at planning time. Tasks modifying the same file/resource must have explicit dependencies.

### Interface Contracts

For cross-task dependencies, contracts define stable interfaces:

```python
# contracts/auth_interface.py
class AuthServiceProtocol(Protocol):
    def login(self, username: str, password: str) -> dict:
        """Returns {token: str, expires_at: datetime}"""
        ...
```

Workers code against these contracts. The Verifier ensures compatibility.

### Structured Patch Intents

For "hot files" (main.py, app.py), workers use structured intents instead of raw edits:

```yaml
patch_intents:
  - file: "src/main.py"
    action: "add_router"
    intent:
      router_module: "src.routes.auth"
      prefix: "/auth"
```

The framework adapter generates canonical code and routes it to the correct region markers.

### Verification

Every task **must** have verification commands:

```yaml
verification:
  - command: "pytest tests/test_auth.py"
    type: test
    required: true
  - command: "ruff check src/services/auth.py"
    type: lint
    required: true
```

The Verifier executes these and also checks:
- File boundaries respected
- Contract versions compatible
- Environment hash matches

### Risk Scoring

Plans are scored based on:
- Sensitive paths (auth, payment, prod)
- Number of tasks and files
- New dependencies
- Contract complexity
- Test coverage

Low-risk plans (score < 25) can be auto-approved.

## Agent Definitions

Custom agents are defined in `.claude/agents/`:

| Agent | Model | Role |
|-------|-------|------|
| `planner-architect` | opus | Analyzes, plans, generates contracts, reviews |
| `supervisor` | sonnet | Creates worktrees, spawns workers, merges |
| `worker` | sonnet | Executes tasks in isolated worktrees |
| `verifier` | sonnet | Runs mechanical verification checks |

## CLI Commands

```bash
# Initialize configuration
claude-orchestrate init

# Create execution plan
claude-orchestrate plan "your request"

# Validate a plan
claude-orchestrate validate tasks.yaml

# Check status
claude-orchestrate status
claude-orchestrate status --verbose
claude-orchestrate status --json

# List worktrees
claude-orchestrate worktrees

# Clean up
claude-orchestrate cleanup

# Abort orchestration
claude-orchestrate abort
claude-orchestrate abort --force
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=claude_orchestrator

# Run specific test file
pytest tests/unit/test_dag.py
```

### Project Structure

```
src/claude_orchestrator/
├── cli.py                 # CLI interface
├── core/
│   ├── dag.py            # DAG scheduling
│   ├── conflict.py       # Conflict detection
│   ├── risk.py           # Risk scoring
│   ├── state.py          # State machine
│   ├── contracts.py      # Contract management
│   └── environment.py    # Environment hashing
├── worktree/
│   ├── manager.py        # Worktree operations
│   └── isolation.py      # Boundary validation
├── adapters/
│   ├── base.py           # Adapter protocol
│   ├── fastapi.py        # FastAPI adapter
│   ├── express.py        # Express adapter
│   └── generic.py        # Fallback adapter
├── integrator/
│   ├── regions.py        # Region markers
│   └── merge.py          # Code merging
├── verification/
│   ├── runner.py         # Verification execution
│   ├── boundaries.py     # Boundary checks
│   └── churn.py          # Churn detection
├── schemas/
│   ├── tasks.py          # Task models
│   ├── status.py         # Status models
│   └── config.py         # Config models
└── utils/
    ├── git.py            # Git operations
    └── tmux.py           # tmux management
```

## License

MIT

## See Also

- [ARCHITECTURE_8.md](ARCHITECTURE_8.md) - Full architecture specification
- [.claude/agents/](/.claude/agents/) - Agent definitions
