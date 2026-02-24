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
- **Git** - For worktree management (must be initialized in project)
- **tmux** - For parallel worker execution
- **Python 3.10+** - For orchestrator utilities
- **rich** - `pip install rich` for live dashboard
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
| `supervisor` | sonnet | Creates git worktrees, spawns workers in tmux, monitors progress, handles merges, mediates dependency requests |
| `worker` | sonnet | Executes single task in isolated worktree, respects file boundaries |
| `verifier` | haiku | Per-task mechanical checks with failure categorization (logic error vs env issue vs timeout) |
| `integration-checker` | sonnet | Post-merge checks: full test suite, security scanning, type checking |

## Orchestrator Utilities

Standalone Python scripts in `~/.claude/orchestrator_code/`:

| Script | Purpose | Example |
|--------|---------|---------|
| `tmux.py` | Tmux session management, monitoring | `python3 ~/.claude/orchestrator_code/tmux.py spawn-agent worker-1 --prompt-file p.md --cwd .` |
| `risk.py` | Compute risk score | `python3 ~/.claude/orchestrator_code/risk.py tasks.yaml` |
| `conflict.py` | Detect file/resource conflicts | `python3 ~/.claude/orchestrator_code/conflict.py tasks.yaml` |
| `dag.py` | Validate DAG, show execution waves | `python3 ~/.claude/orchestrator_code/dag.py tasks.yaml` |
| `contracts.py` | Generate Protocol stubs | `python3 ~/.claude/orchestrator_code/contracts.py MyProtocol login logout -o contracts/my.py` |
| `environment.py` | Compute/verify env hash | `python3 ~/.claude/orchestrator_code/environment.py --verify abc123` |
| `state.py` | Manage orchestration state | `python3 ~/.claude/orchestrator_code/state.py init/status/resume` |
| `tasks.py` | Check task readiness, blocked tasks | `python3 ~/.claude/orchestrator_code/tasks.py blocked` |
| `verify.py` | Full verification suite | `python3 ~/.claude/orchestrator_code/verify.py full task-a tasks.yaml` |
| `context.py` | Shared context store, prompt injection | `python3 ~/.claude/orchestrator_code/context.py get-for-task task-a` |
| `mailbox.py` | Inter-worker messaging and broadcasts | `python3 ~/.claude/orchestrator_code/mailbox.py send task-b "API changed" --from worker-task-a` |
| `dashboard.py` | Live monitoring dashboard | `python3 ~/.claude/orchestrator_code/dashboard.py` |
| `workers_view.py` | Live worker output panels | `python3 ~/.claude/orchestrator_code/workers_view.py` |
| `monitoring.py` | Open/manage monitoring windows | `python3 ~/.claude/orchestrator_code/monitoring.py open` |

All scripts support `--json` for machine-readable output.

### Live Dashboard

Monitor orchestration in real-time:

```bash
# Start live dashboard (updates every second)
python3 ~/.claude/orchestrator_code/dashboard.py

# Custom refresh rate
python3 ~/.claude/orchestrator_code/dashboard.py --refresh 2

# Show once and exit
python3 ~/.claude/orchestrator_code/dashboard.py --once
```

Requires `rich` library: `pip install rich`

**Dashboard Output:**

```
                              ORCHESTRATION STATUS
╭───────────────────┬───────────────┬──────────┬──────────────────┬────────────╮
│ Task              │ Status        │ Agent    │ Context          │ Progress   │
├───────────────────┼───────────────┼──────────┼──────────────────┼────────────┤
│ task-auth-service │ ● executing   │ worker   │ 45.2k/200.0k     │ Working... │
│                   │               │          │ (23%)            │            │
│ task-auth-routes  │ ● executing   │ worker   │ 12.1k/200.0k     │ Working... │
│                   │               │          │ (6%)             │            │
│ task-user-model   │ ✓ verified    │ done     │ -                │ Complete   │
│ task-api-tests    │ ○ pending     │ -        │ -                │ Waiting... │
╰───────────────────┴───────────────┴──────────┴──────────────────┴────────────╯
                           Request: Add user authentication
  Phase: executing  │  Elapsed: 3m 42s  │  Active: 2  │  Done: 1  │  Failed: 0
                                  Ctx: 57.3k/400.0k
```

### Workers View

Live output from all workers (uses `capture-pane`, avoids tmux attach issues):

```bash
python3 ~/.claude/orchestrator_code/workers_view.py
```

**Workers View Output:**

```
WORKERS VIEW (Ctrl+C to exit)
Found 3 worker sessions

┌─────────────────────────────────┬─────────────────────────────────┐
│ task-auth-service               │ task-auth-routes                │
│                                 │                                 │
│ Implementing login method...    │ Adding /login endpoint...       │
│ ⠋ Writing src/services/auth.py │ ⠙ Reading contract interface    │
│                                 │                                 │
├─────────────────────────────────┴─────────────────────────────────┤
│ task-user-model                                                   │
│                                                                   │
│ ✓ Task completed successfully                                     │
│ Tests passed: 12/12                                               │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Auto-Opening Monitoring Windows

When `state.py init` runs, monitoring windows open automatically (macOS). Use `--no-monitoring` to disable:

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  MAIN AGENT     │  │   DASHBOARD     │  │    WORKERS      │
│                 │  │                 │  │ ┌─────┬───────┐ │
│  Supervisor/    │  │ Task   Status   │  │ │wkr-a│ wkr-b │ │
│  Planner runs   │  │ task-a ●running │  │ ├─────┼───────┤ │
│  here           │  │ task-b ○pending │  │ │wkr-c│ wkr-d │ │
│                 │  │                 │  │ └─────┴───────┘ │
│  (your current  │  │ Ctx: 45k/200k   │  │  live output    │
│   terminal)     │  │                 │  │  from workers   │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

- **Main**: Your Claude Code session (supervisor/planner-architect)
- **Dashboard**: Live status table with context window usage per worker
- **Workers**: Split panes showing real-time output from each worker

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
- **Pre-flight checks**: Dry-run dependency resolution (`uv sync --dry-run`, `npm install --dry-run`)
- **Cleanup trap**: Registers signal handlers to clean up worktrees on exit/interrupt
- Creates a **staging branch** from main (protects main from broken integrations)
- Opens monitoring windows (Dashboard + Workers view)
- Creates isolated git worktrees (`.worktrees/<task-id>/`)
- Spawns worker agents in tmux sessions for true parallelism
- **Non-blocking monitoring**: If one worker is blocked (needs dependency), continues monitoring healthy workers
- Monitors progress via `.task-status.json` files

### 3. Verification Phase (Two-Tier)

The system uses a **two-tier verification** approach where each agent owns its merge decision:

**Tier 1: Per-Task Verification (haiku)**
1. Worker marks task `completed` in `.task-status.json`
2. Supervisor spawns Verifier agent for THAT task
3. Verifier checks:
   - Task tests (pytest, npm test, etc.)
   - File boundaries (only files in `files_write` modified)
   - Contract versions consistency
   - Environment hash matching
   - **Contract type verification (REQUIRED)**: `mypy --strict` or equivalent to catch signature mismatches
4. **If passed: Verifier merges task to staging** (atomic verify-then-merge)
5. Verifier signals `.verified` (merged) or `.failed` (no merge)
6. **Incremental integration check**: Supervisor runs full test suite on staging immediately
   - If tests fail, we know exactly which task broke the build
   - No need to wait for all tasks to find integration issues

**Why contract type verification?** Unit tests might not catch type mismatches (e.g., `def auth(user: str)` vs `def auth(user: User)`). Static type checking catches these before integration.

**Tier 2: Final Integration Check (sonnet)**
After all tasks have `.verified` signals AND incremental checks passed:
1. Integration-Checker checks out staging branch
2. Runs full test suite (not just task-specific)
3. Security scanning (bandit, npm audit, etc.)
4. Type checking across all modified files
5. **If passed: Integration-Checker merges staging to main**
6. Signals `integration.passed` (main updated) or `integration.failed` (main untouched)

**Why agents own merges:**
- Atomic: No window between "verified" and "merged" where state could change
- Clear ownership: Agent that validates makes the merge decision
- Simpler Supervisor: Just spawns agents and waits for signals

### 4. Review Phase (opus)

After integration passes and staging is promoted to main:
- Planner-architect (opus) reviews the integrated result holistically
- Evaluates: Does implementation fulfill the request? Is architecture coherent?
- Accept or iterate (max 3 iterations)
- If max iterations reached → **Escalation Protocol**

### 5. Escalation Protocol

After max iterations (3) without successful review, orchestration cannot simply retry:

1. **Pause**: Stop all retry attempts
2. **Preserve state**: Keep staging branch, worktrees, and logs for debugging
3. **Generate report**: `.orchestrator/escalation-report.md` with root cause analysis
4. **Present options to user**:
   - **Manual fix**: User fixes issues, runs `state.py resume`
   - **Re-plan**: Generate new tasks.yaml with different decomposition
   - **Abort**: Clean up everything, restore main to original commit

**Why user decides:** Automatic rollback could discard valuable partial progress. Re-planning could repeat the same mistakes. Only the user has context to make the right call.

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

### Context Injection (Push-Based)

The Supervisor injects relevant project context directly into worker prompts, rather than workers pulling context at runtime:

```bash
# Supervisor looks up context and injects into prompt
CONTEXT=$(python3 ~/.claude/orchestrator_code/context.py get-for-task task-auth --tasks-file tasks.yaml)
```

Tasks can specify explicit context keys:
```yaml
tasks:
  - id: task-auth-service
    context_keys: ["auth-rules", "jwt-config"]  # Injected into worker prompt
```

This is better than pull-based because:
- Workers don't waste tokens searching for context
- Supervisor has global view of what's relevant
- No risk of workers missing important context

### Inter-Worker Mailbox

Workers are isolated in separate git worktrees, but sometimes one worker's discoveries need to reach another mid-execution — an API signature change, a naming convention, or a new dependency installed by the Supervisor.

The mailbox system provides push-based messaging between workers:

- **Targeted messages**: Worker A sends directly to Worker B's inbox
- **Broadcasts**: Supervisor or any worker sends to all workers at once

**Use cases:**
- Worker changes a function signature that another worker will consume via a contract
- Supervisor installs a requested dependency and notifies all workers
- Worker discovers a naming convention that others should follow

**CLI examples:**

```bash
# Send a message to a specific worker
python3 ~/.claude/orchestrator_code/mailbox.py send task-b "Changed login() return type" --from worker-task-a

# Broadcast to all workers
python3 ~/.claude/orchestrator_code/mailbox.py broadcast "Using UUID primary keys" --from supervisor

# Check inbox (marks messages as read)
python3 ~/.claude/orchestrator_code/mailbox.py check task-b

# Peek at inbox (unread count only, no side effects)
python3 ~/.claude/orchestrator_code/mailbox.py peek task-b
```

**Relationship to context injection:** Context injection (`context.py`) provides the initial state at worker spawn time — persistent project knowledge pulled into the prompt. The mailbox provides runtime updates during execution — ephemeral notifications pushed to inboxes as events happen.

### Dependency Resolution (RFC Model)

When workers discover missing dependencies, the Supervisor mediates:

```
Worker → "I need pandas>=2.0" → Supervisor checks conflicts → User approves → Install → Restart worker
```

1. **Worker signals blocked**: Writes `{"status": "blocked", "needs_dependency": "pandas>=2.0"}` to `.task-status.json`
2. **Supervisor detects**: `python3 ~/.claude/orchestrator_code/tasks.py blocked`
3. **Conflict check**: Supervisor checks for version conflicts with other workers
4. **User approval**: Supervisor asks user before installing (security boundary)
5. **Install & restart**: Supervisor installs, recomputes env hash, restarts worker

The Supervisor is the only entity that can modify lockfiles. Workers request, Supervisor decides.

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

**Thresholds (default):**
- **0-25**: Auto-approve
- **26-50**: Recommend review
- **51+**: Require approval

**Custom Configuration:**

Sensitive patterns and thresholds can be customized via `.claude-agents.yaml`:

```yaml
risk:
  sensitive_patterns:
    - pattern: "auth|security|crypto"
      weight: 20
    - pattern: "internal/proprietary/*"
      weight: 50
  auto_approve_threshold: 30
```

Use with: `python3 ~/.claude/orchestrator_code/risk.py --config .claude-agents.yaml tasks.yaml`

## Files Created During Orchestration

```
your-project/
├── tasks.yaml                    # Execution plan
├── contracts/                    # Interface Protocol stubs
│   └── auth_interface.py
├── .orchestration-state.json     # Execution state
├── .orchestrator/
│   ├── signals/                  # Worker signal files
│   ├── logs/                     # Worker logs
│   ├── prompts/                  # Generated worker prompts
│   └── mailbox/                  # Inter-worker message inboxes
│       ├── task-auth-service/
│       ├── task-auth-routes/
│       └── broadcast/
└── .worktrees/                   # Isolated worktrees (temporary)
    ├── task-auth-service/
    │   └── .task-status.json
    └── task-auth-routes/
        └── .task-status.json
```

## Troubleshooting

### Resume interrupted orchestration

If orchestration was interrupted (user stopped, crash, etc.):

```bash
# See what would be done (dry-run)
python3 ~/.claude/orchestrator_code/state.py resume --dry-run

# Actually resume
python3 ~/.claude/orchestrator_code/state.py resume
```

This will:
- Reset tasks stuck in "executing" to "pending"
- Clean up incomplete worktrees and orphaned tmux sessions
- Reopen monitoring windows
- Report tasks ready for verification or merge

Then continue from supervisor Stage 2 (spawn workers for pending tasks).

### Check orchestration status
```bash
python3 ~/.claude/orchestrator_code/state.py status
```

### View monitoring windows
```bash
# Dashboard (runs directly, no tmux)
python3 ~/.claude/orchestrator_code/dashboard.py

# Workers view (uses capture-pane, avoids tmux attach crash on macOS/conda)
python3 ~/.claude/orchestrator_code/workers_view.py
```

### List tmux worker sessions
```bash
tmux list-sessions | grep "worker-"
```

### View worker output
```bash
# Recommended: use capture-pane (no crash)
tmux capture-pane -t "worker-<task-id>" -p | tail -30

# Or use workers_view.py for live multi-pane view
python3 ~/.claude/orchestrator_code/workers_view.py
```

### Handle blocked tasks (missing dependencies)

If a worker discovers it needs a package that isn't installed:

```bash
# Check for blocked tasks
python3 ~/.claude/orchestrator_code/tasks.py blocked

# Or check specific task
python3 ~/.claude/orchestrator_code/tmux.py check-blocked <task-id>
```

Output:
```
Task: task-data-analysis
Reason: Missing required dependency
Needs dependency: pandas>=2.0

To resolve, install: pandas>=2.0
Then restart orchestration.
```

The monitor command also detects blocked status automatically (exit code 2).

**Why not auto-install?** Workers can't install dependencies mid-execution because:
- It would break environment hash consistency
- Security risk (arbitrary package installation)
- Could cause version conflicts between workers

### Kill stuck worker
```bash
tmux kill-session -t "worker-<task-id>"
```

### Clean up worktrees
```bash
git worktree list
git worktree remove .worktrees/<task-id>
```

### Kill all orchestration sessions
```bash
# Kill all worker sessions
tmux list-sessions -F '#{session_name}' | grep '^worker-' | xargs -I {} tmux kill-session -t {}

# Clean up stale tmux socket (if server crashed)
rm -f /private/tmp/tmux-$(id -u)/default
```

### tmux "server exited unexpectedly" (macOS with conda only)

This error **only affects conda's tmux package** on macOS. It's a bug in how conda builds/packages tmux, not tmux itself.

**Solution:** Use the official tmux binary instead of conda's:

```bash
# Check which tmux you're using
which tmux
# If it shows /opt/miniconda3/bin/tmux or similar conda path, that's the problem

# Fix options (choose one):
brew install tmux                    # Homebrew
sudo port install tmux               # MacPorts
# Or compile from source: https://github.com/tmux/tmux
```

After installing, ensure the non-conda tmux is first in your PATH, or use the full path.

**Workaround (if you must use conda's tmux):**

```bash
# Use capture-pane instead of attach:
tmux capture-pane -t worker-task-a -p  # ✓ works

# Or use the workers view:
python3 ~/.claude/orchestrator_code/workers_view.py  # ✓ works
```

## License

MIT

## See Also

- [ARCHITECTURE_8.md](ARCHITECTURE_8.md) - Full architecture specification
- [.claude/agents/](.claude/agents/) - Agent definitions
- [.claude/orchestrator_code/](.claude/orchestrator_code/) - Utility scripts
