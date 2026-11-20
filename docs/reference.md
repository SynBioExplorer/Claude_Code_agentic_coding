# Reference

Operational detail behind the [README](../README.md). It describes the scripts and agent definitions at HEAD. Paths such as `~/.claude/orchestrator_code/` assume the install steps in the README. Most scripts read `tasks.yaml`, `.orchestrator/` and `.worktrees/` relative to the current directory, so run them from the project root.

## Scripts

All scripts are in `.claude/orchestrator_code/`. The last column says whether the agent definitions in `.claude/agents/` call the script.

| Script | Purpose | Example | Called by the agents |
|--------|---------|---------|----------------------|
| `tmux.py` | Create and spawn agent sessions, wait for signal files, monitor with a timeout and blocked-task detection, save logs, clean up orphaned sessions, pre-flight check | `tmux.py spawn-agent worker-task-a --prompt-file p.md --cwd .worktrees/task-a` | all |
| `dag.py` | Validate dependency IDs and cycles, print execution waves | `dag.py tasks.yaml` | planner, supervisor |
| `conflict.py` | Report file, read-write and resource conflicts between tasks that no dependency orders | `conflict.py tasks.yaml` | planner |
| `risk.py` | Compute the risk score | `risk.py --config .claude-agents.yaml tasks.yaml` | planner |
| `contracts.py` | Generate a Protocol stub stamped with the git hash | `contracts.py MyProtocol login logout -o contracts/my.py` | planner |
| `environment.py` | Hash the lockfiles, verify a hash | `environment.py --verify abc123` | supervisor, verifier |
| `verify.py` | Boundary check, verification commands, both together | `verify.py full task-a tasks.yaml --env-hash abc123` | verifier |
| `tasks.py` | Task readiness, status summary, blocked tasks | `tasks.py blocked` | supervisor (`blocked` only) |
| `state.py` | Create and update `.orchestration-state.json`, resume, staging lock | `state.py init "request" tasks.yaml`, `state.py status`, `state.py resume --dry-run` | staging lock only |
| `context.py` | Shared knowledge store and prompt injection | `context.py get-for-task task-a --tasks-file tasks.yaml` | supervisor, worker |
| `mailbox.py` | Messages between workers, broadcasts | `mailbox.py send task-b "API changed" --from worker-task-a` | supervisor, worker |
| `worktree.py` | Create, delete, merge, list and clean up task worktrees | `worktree.py create task-a --base main` | no |
| `git.py` | Git helpers used by `worktree.py` | `git.py modified .worktrees/task-a` | no |
| `dashboard.py` | Live status table (needs `rich`) | `dashboard.py --refresh 2` or `--once` | no |
| `workers_view.py` | Live output of the worker tmux panes | `workers_view.py` | no |
| `monitoring.py` | Open the dashboard and worker windows (macOS) | `monitoring.py open` | no |

`dag.py`, `conflict.py`, `risk.py`, `environment.py`, `verify.py`, `tasks.py`, `state.py` (`status` and `resume`) and `tmux.py preflight` accept `--json`. The other scripts print text only.

## Task fields

`tasks.yaml` has a `request`, a `created_at`, a list of `tasks` and an optional list of `contracts`. Which script reads which task field:

| Field | Required | Read by |
|-------|----------|---------|
| `id` | yes | all |
| `description` | no | `context.py` (keyword lookup) |
| `files_write` | yes | `conflict.py`, `risk.py`, `verify.py boundaries`, `context.py` |
| `files_read` | no | `conflict.py` (read-write conflicts), `context.py` |
| `resources_write` | no | `conflict.py` |
| `depends_on` | no | `dag.py`, `conflict.py`, `tasks.py` |
| `verification[]` with `command`, `type`, `required`, optional `timeout` | at least one | `state.py init`, `verify.py`; `risk.py` looks for `type: test` |
| `context_keys` | no | `context.py get-for-task` |
| `deps_required.runtime` | no | `risk.py` |
| `patch_intents` | no | `conflict.py` (implied resources), `risk.py` (count); nothing applies them |
| `contracts[]` with `name`, `version`, `file_path`, `methods`, `consumers` | no | `risk.py` (count) |

`files_append` and `allow_large_changes` appear in `ARCHITECTURE_8.md` but no script reads them.

## Risk scoring

`risk.py` adds the points below. Each path in a task's `files_write` earns the weight of the first sensitive pattern that matches it (a case-insensitive regular expression search).

| Factor | Points |
|--------|--------|
| Path matches `auth\|security\|crypto` | 20 |
| Path matches `payment\|billing\|stripe` | 25 |
| Path matches `prod\|production\|deploy` | 30 |
| Path matches `admin\|sudo\|root` | 15 |
| Path matches `\.env\|secret\|key\|token` | 25 |
| Path matches `migration\|schema\|database` | 15 |
| Tasks beyond 5 | 5 each |
| `files_write` entries beyond 10 | 3 each |
| `patch_intents` beyond 3 | 5 each |
| Runtime packages in `deps_required` | 3 each |
| Contracts beyond 3 | 5 each |
| Tasks with no verification of `type: test` | `int((1 - share of tasks with a test) * 20)` |

A score at or below the threshold (default 25) is auto-approved. Up to twice the threshold the status is `REQUIRES REVIEW`, and above that `HIGH RISK`. The planner definition asks the user for approval when the score is above 25.

Patterns and the threshold can be set in `.claude-agents.yaml`, found in the current directory or passed with `--config`. This is the only part of that file any script reads. A `sensitive_patterns` list replaces the defaults instead of extending them, and the patterns are regular expressions, not globs:

```yaml
risk:
  sensitive_patterns:
    - pattern: "auth|security|crypto"
      weight: 20
    - pattern: "internal/proprietary/"
      weight: 50
  auto_approve_threshold: 30
```

Patterns with nested quantifiers are rejected, and each match has a one-second alarm.

## Monitoring

None of the agent definitions starts these; run them by hand, or let `state.py init` open them.

- `dashboard.py` shows a table of task status, agent and progress, read from `.orchestration-state.json` and each `.worktrees/<id>/.task-status.json`. It needs `rich`, and it shows "No active orchestration" until `state.py init "request" tasks.yaml` has created the state file. Options: `--refresh <seconds>` and `--once`.
- `workers_view.py` shows the recent output of every `worker-*` tmux session using `tmux capture-pane`. The scripts avoid `tmux attach` because it crashed with a conda-installed tmux on macOS (see the comments in `workers_view.py` and `monitoring.py`).
- `monitoring.py open` opens the dashboard and the worker view in two Terminal or iTerm windows through AppleScript. `state.py init` and `state.py resume` do the same unless given `--no-monitoring`.

## Context and mailbox

`context.py` keeps project knowledge in `.context/knowledge.json` with file locking. `context.py get-for-task <id>` builds the block that the supervisor places in a worker's prompt, taking entries named in the task's `context_keys` first, then entries that match keywords in its description, then entries that match its file paths. It returns nothing if the store is empty. Workers can also run `context.py add`, `get`, `list` and `search`.

`mailbox.py` passes messages between workers while they run. Each task has an inbox directory `.orchestrator/mailbox/<task-id>/`, and `broadcast/` holds messages for everyone. Messages are JSON files written to a temporary name and renamed, so a reader never sees a partial file; reading renames `msg-<id>.json` to `msg-<id>.read.json`, and a per-worker `.seen-by-<task-id>` file stops broadcasts being delivered twice. Commands: `init --tasks ...`, `send`, `broadcast`, `check` (returns unread messages and marks them read), `peek` (counts only) and `cleanup`. The message type is a free string, with `info` as the default; the specification lists `api_change`, `dependency_installed`, `warning` and `blocking`.

Context injection gives a worker its starting knowledge when it is spawned. The mailbox carries changes that happen after that. The mailbox directory is resolved from the current directory, as noted under Limitations in the README.

## Dependency requests

Workers cannot install packages or touch lockfiles. When a worker needs a missing package:

1. It writes `{"status": "blocked", "blocked_reason": "...", "needs_dependency": "pandas>=2.0"}` to `.task-status.json` and creates its `.done` signal so that the run does not wait for it.
2. `tmux.py monitor` returns exit code 2 for a blocked task, and `tasks.py blocked` lists the blocked tasks.
3. The supervisor keeps watching the other workers. When none is left running, it batches the requests, checks them for version conflicts and asks the user.
4. If the user approves, the supervisor installs the packages with `uv add`, recomputes the environment hash, sends each blocked worker a `dependency_installed` message and restarts it.

By default no package is installed without asking, because mid-run installs would change the environment hash, can install arbitrary code and can create version conflicts between workers. `supervisor.md` describes an optional `dependencies.auto_approve` setting in `.claude-agents.yaml`; no script reads it.

## Escalation

After three review iterations without acceptance, or on an unrecoverable error or a third contract renegotiation, the planner stops. It keeps the `staging` branch, the `.worktrees/` directories and `.orchestrator/logs/`, writes `.orchestrator/escalation-report.md` with a root-cause analysis, and offers three options: fix by hand and run `state.py resume`, re-plan with a different decomposition, or abort, which deletes `staging` and prunes worktrees. The user decides, because automatic rollback could discard useful partial work and re-planning could repeat the same mistake.

## Resuming and status

```bash
python3 ~/.claude/orchestrator_code/state.py status
python3 ~/.claude/orchestrator_code/state.py resume --dry-run   # report only
python3 ~/.claude/orchestrator_code/state.py resume
```

`resume` resets tasks stuck in `executing` to `pending`, kills the tmux session of each restarted task, removes its worktree and reopens the monitoring windows. Uncommitted work in a worktree is committed to the task branch first unless `--force` is given. It lists tasks that are ready for verification or for merge. Execution then continues from Stage 2 of `supervisor.md`. These commands need the state file from `state.py init`.

## Files created during a run

```
your-project/
  tasks.yaml                    plan written by the planner
  execution-plan.md             readable summary of the plan
  contracts/                    interface Protocol stubs
  .orchestration-state.json     only if state.py init was run
  .context/knowledge.json       shared context, if used
  .orchestrator/
    signals/                    <task-id>.done, .verified, .failed, integration.*, orchestration.*
    logs/                       saved tmux output and scanner output
    prompts/                    the prompt written for each spawned agent
    mailbox/                    one inbox per task, and broadcast/
    staging.lock                flock file for the staging branch
    escalation-report.md        only after an escalation
  .worktrees/<task-id>/         temporary worktree, with its .task-status.json
```

## Platform notes

- The scripts and `supervisor.md` assume the default branch is called `main`. Only `worktree.py create` and `git.py modified` accept `--base`.
- Agents are started with `--dangerously-skip-permissions --permission-mode bypassPermissions`. For a plan at or below the risk threshold nothing asks you first.
- Each tmux session exports `NODE_OPTIONS='--max-old-space-size=16384'` (a 16 GB heap). Reduce it in `tmux.py` on a small machine.
- State and lock files use `fcntl`, and `risk.py` uses `SIGALRM`, so a POSIX system is required.
- `monitoring.py` uses AppleScript and works only on macOS. If `conda` is on the PATH it is activated in the worker window; otherwise `python3` just has to be on the PATH.

## Troubleshooting

```bash
python3 ~/.claude/orchestrator_code/tmux.py list                    # worker sessions
tmux capture-pane -t =worker-<task-id>: -p | tail -30               # recent output of one worker
tmux kill-session -t =worker-<task-id>                              # stop one worker
python3 ~/.claude/orchestrator_code/tmux.py cleanup-orphans         # stop all worker sessions, saving logs first
git worktree list                                                   # then: git worktree remove .worktrees/<task-id>
python3 ~/.claude/orchestrator_code/tasks.py blocked                # workers waiting for a package
```

If tmux reports "server exited unexpectedly" and `which tmux` points into a conda environment, install tmux with Homebrew or MacPorts and put it first on the PATH, or avoid `tmux attach` and use `capture-pane` or `workers_view.py`. A stale tmux socket can be removed with `rm -f /private/tmp/tmux-$(id -u)/default`.
