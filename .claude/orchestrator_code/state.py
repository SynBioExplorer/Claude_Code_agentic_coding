#!/usr/bin/env python3
"""
Orchestration State Management.

Manages .orchestration-state.json for tracking execution.

Usage:
    python3 ~/.claude/orchestrator_code/state.py init "User request" tasks.yaml
    python3 ~/.claude/orchestrator_code/state.py status
    python3 ~/.claude/orchestrator_code/state.py update task-a executing
    python3 ~/.claude/orchestrator_code/state.py update task-a completed
"""

import json
import uuid
import sys
import os
import fcntl
import tempfile
import time
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


STATE_FILE = ".orchestration-state.json"


def atomic_write_json(filepath: Path, data: dict) -> bool:
    """Write JSON atomically using temp file + fsync + rename pattern.

    This prevents corruption from partial writes and ensures data is
    flushed to disk before the rename.

    Args:
        filepath: Path to the target file
        data: Dictionary to write as JSON

    Returns:
        True if write succeeded
    """
    # Create temp file in same directory to ensure same filesystem (for atomic rename)
    dir_path = filepath.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd = None
    temp_path = None
    try:
        # Create temp file
        fd, temp_path = tempfile.mkstemp(
            suffix='.tmp',
            prefix=filepath.stem + '_',
            dir=str(dir_path)
        )

        # Write data
        content = json.dumps(data, indent=2)
        os.write(fd, content.encode('utf-8'))

        # Fsync to ensure data is on disk
        os.fsync(fd)
        os.close(fd)
        fd = None

        # Atomic rename
        os.rename(temp_path, filepath)
        temp_path = None

        return True

    except Exception as e:
        # Clean up on failure
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        raise e


def safe_read_json(filepath: Path, max_retries: int = 3) -> dict | None:
    """Safely read JSON file with retry on parse failure.

    If file is being written, may get partial content. Retry with backoff.

    Args:
        filepath: Path to JSON file
        max_retries: Number of retries on parse failure

    Returns:
        Parsed dict or None if file doesn't exist
    """
    import time

    if not filepath.exists():
        return None

    for attempt in range(max_retries):
        try:
            content = filepath.read_text()
            return json.loads(content)
        except json.JSONDecodeError:
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))  # Backoff: 0.1s, 0.2s, 0.3s
                continue
            # Last attempt failed, return None instead of crashing
            return None
    return None


def load_plan(path: str) -> dict:
    """Load plan from YAML or JSON file."""
    p = Path(path)
    content = p.read_text()

    if p.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise ImportError("PyYAML not installed. Run: pip install pyyaml")
        return yaml.safe_load(content)
    else:
        return json.loads(content)


def compute_env_hash() -> str:
    """Compute environment hash from lockfile."""
    import hashlib
    lockfiles = ["uv.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"]
    for lf in lockfiles:
        p = Path(lf)
        if p.exists():
            return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return "no-lock"


def init_state(request: str, tasks_file: str = "tasks.yaml", open_monitoring: bool = True) -> dict:
    """Initialize orchestration state from tasks file.

    Args:
        request: Original user request
        tasks_file: Path to tasks YAML file
        open_monitoring: If True, automatically open monitoring windows
    """
    plan = load_plan(tasks_file)
    env_hash = compute_env_hash()

    state = {
        "request_id": str(uuid.uuid4()),
        "original_request": plan.get("request", request),
        "created_at": datetime.now().isoformat(),
        "environment": {
            "hash": env_hash,
            "installed_at": datetime.now().isoformat()
        },
        "tasks": {
            t["id"]: {"status": "pending", "worktree": f".worktrees/{t['id']}"}
            for t in plan.get("tasks", [])
        },
        "current_phase": "initializing",
        "iteration": 1
    }

    # Use atomic write to prevent corruption
    atomic_write_json(Path(STATE_FILE), state)

    # Auto-open monitoring windows
    if open_monitoring:
        try:
            from monitoring import open_monitoring_windows
            open_monitoring_windows(str(Path.cwd()))
        except Exception as e:
            print(f"Warning: Could not open monitoring windows: {e}")

    return state


def load_state() -> dict | None:
    """Load existing state or return None.

    Uses safe_read_json to handle partial writes gracefully.
    """
    return safe_read_json(Path(STATE_FILE))


def save_state(state: dict):
    """Save state to file atomically.

    Uses atomic_write_json to prevent corruption from partial writes.
    """
    atomic_write_json(Path(STATE_FILE), state)


def update_task(task_id: str, new_status: str, error: str = None) -> dict:
    """Update a task's status with file locking to prevent lost updates.

    Uses fcntl.flock to ensure read-modify-write is atomic across
    concurrent Supervisor calls.
    """
    state_path = Path(STATE_FILE)
    lock_path = state_path.with_suffix('.lock')
    lock_path.touch(exist_ok=True)

    lock_file = open(lock_path, 'r+')
    try:
        # Acquire exclusive lock with timeout via non-blocking retry
        deadline = time.time() + 10  # 10 second timeout
        while True:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (IOError, OSError):
                if time.time() > deadline:
                    raise TimeoutError("Could not acquire state lock within 10 seconds")
                time.sleep(0.05)

        # Read-modify-write while holding lock
        state = load_state()
        if state is None:
            raise ValueError("No orchestration state found")

        if task_id not in state["tasks"]:
            raise ValueError(f"Task {task_id} not found")

        state["tasks"][task_id]["status"] = new_status
        state["tasks"][task_id]["updated_at"] = datetime.now().isoformat()
        if error:
            state["tasks"][task_id]["error"] = error

        save_state(state)
        return state
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def get_effective_status(task_id: str, task_info: dict) -> str:
    """Get the effective status of a task by checking worktree status file.

    The worktree status file has the most up-to-date status from the worker.
    Falls back to the state file status if no worktree status exists.
    Uses safe_read_json to handle partial writes gracefully.
    """
    status_file = Path(f".worktrees/{task_id}/.task-status.json")
    task_status = safe_read_json(status_file)
    if task_status:
        return task_status.get("status", "unknown")
    return task_info.get("status", "pending")


def get_status_summary() -> dict:
    """Get summary of all task statuses."""
    state = load_state()
    if state is None:
        return {"error": "No orchestration state found"}

    results = {
        "pending": [], "executing": [], "completed": [],
        "failed": [], "verified": [], "merged": []
    }

    for task_id, task_info in state.get("tasks", {}).items():
        status = get_effective_status(task_id, task_info)
        results.get(status, results["pending"]).append(task_id)

    return {
        "summary": results,
        "request_id": state.get("request_id"),
        "phase": state.get("current_phase"),
        "iteration": state.get("iteration"),
        "env_hash": state.get("environment", {}).get("hash")
    }


def cleanup_worktree(task_id: str) -> bool:
    """Clean up an incomplete worktree."""
    import subprocess
    worktree_path = Path(f".worktrees/{task_id}")

    if not worktree_path.exists():
        return True

    try:
        # Try to remove worktree via git
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            capture_output=True, check=False
        )
        # Try to delete branch
        subprocess.run(
            ["git", "branch", "-D", f"task/{task_id}"],
            capture_output=True, check=False
        )
        return True
    except Exception:
        return False


def resume_orchestration(dry_run: bool = False, open_monitoring: bool = True) -> dict:
    """Resume interrupted orchestration.

    Handles tasks stuck in 'executing' status and provides summary of
    what needs to continue.

    Args:
        dry_run: If True, only report what would be done without making changes
        open_monitoring: If True, reopen monitoring windows

    Returns:
        dict with restarted_tasks, ready_for_verification, ready_for_merge lists
    """
    state = load_state()
    if state is None:
        return {"error": "No orchestration state found"}

    tasks_to_restart = []
    ready_for_verification = []
    ready_for_merge = []
    worktrees_cleaned = []

    for task_id, task_info in state["tasks"].items():
        status = get_effective_status(task_id, task_info)

        if status == "executing":
            # Task was interrupted - needs restart
            worktree = Path(f".worktrees/{task_id}")
            if worktree.exists() and not dry_run:
                if cleanup_worktree(task_id):
                    worktrees_cleaned.append(task_id)

            tasks_to_restart.append(task_id)
            if not dry_run:
                update_task(task_id, "pending")

        elif status == "completed":
            # Completed but not verified yet
            ready_for_verification.append(task_id)

        elif status == "verified":
            # Verified but not merged yet
            ready_for_merge.append(task_id)

    # Kill any orphaned worker tmux sessions
    if not dry_run:
        import subprocess
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                sessions = result.stdout.strip().split('\n')
                for session in sessions:
                    if session.startswith('worker-'):
                        task_id = session.replace('worker-', '')
                        if task_id in tasks_to_restart:
                            subprocess.run(
                                ["tmux", "kill-session", "-t", f"={session}"],
                                capture_output=True, check=False
                            )
        except Exception:
            pass

    # Reopen monitoring windows
    if not dry_run and open_monitoring:
        try:
            from monitoring import open_monitoring_windows
            open_monitoring_windows(str(Path.cwd()))
        except Exception as e:
            print(f"Warning: Could not open monitoring windows: {e}")

    return {
        "dry_run": dry_run,
        "restarted_tasks": tasks_to_restart,
        "worktrees_cleaned": worktrees_cleaned,
        "ready_for_verification": ready_for_verification,
        "ready_for_merge": ready_for_merge,
        "request_id": state.get("request_id"),
        "env_hash": state.get("environment", {}).get("hash")
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manage orchestration state")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize state from tasks file")
    init_parser.add_argument("request", help="Original user request")
    init_parser.add_argument("tasks_file", nargs="?", default="tasks.yaml", help="Tasks file")
    init_parser.add_argument("--no-monitoring", action="store_true",
                            help="Do not auto-open monitoring windows")

    # status command
    status_parser = subparsers.add_parser("status", help="Show status summary")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # update command
    update_parser = subparsers.add_parser("update", help="Update task status")
    update_parser.add_argument("task_id", help="Task ID")
    update_parser.add_argument("status", help="New status")
    update_parser.add_argument("--error", help="Error message if failed")

    # resume command
    resume_parser = subparsers.add_parser("resume", help="Resume interrupted orchestration")
    resume_parser.add_argument("--dry-run", action="store_true",
                              help="Show what would be done without making changes")
    resume_parser.add_argument("--no-monitoring", action="store_true",
                              help="Do not reopen monitoring windows")
    resume_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "init":
        state = init_state(args.request, args.tasks_file,
                          open_monitoring=not args.no_monitoring)
        print(f"✓ Initialized orchestration state")
        print(f"  Request ID: {state['request_id']}")
        print(f"  Env hash: {state['environment']['hash']}")
        print(f"  Tasks: {len(state['tasks'])}")

    elif args.command == "status":
        summary = get_status_summary()
        if "error" in summary:
            print(summary["error"])
            sys.exit(1)

        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            s = summary["summary"]
            print(f"\nOrchestration Status (Request: {summary['request_id'][:8]}...)")
            print(f"Phase: {summary['phase']} | Iteration: {summary['iteration']}")
            print(f"\nTask Status Summary:")
            print(f"  Pending:   {len(s['pending'])} - {s['pending']}")
            print(f"  Executing: {len(s['executing'])} - {s['executing']}")
            print(f"  Completed: {len(s['completed'])} - {s['completed']}")
            print(f"  Verified:  {len(s['verified'])} - {s['verified']}")
            print(f"  Merged:    {len(s['merged'])} - {s['merged']}")
            print(f"  Failed:    {len(s['failed'])} - {s['failed']}")

    elif args.command == "update":
        update_task(args.task_id, args.status, args.error)
        print(f"✓ Updated {args.task_id} -> {args.status}")

    elif args.command == "resume":
        result = resume_orchestration(
            dry_run=args.dry_run,
            open_monitoring=not args.no_monitoring
        )
        if "error" in result:
            print(result["error"])
            sys.exit(1)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            mode = "[DRY RUN] " if result["dry_run"] else ""
            print(f"\n{mode}Resume Orchestration (Request: {result['request_id'][:8]}...)")
            print(f"Environment hash: {result['env_hash']}")

            if result["restarted_tasks"]:
                print(f"\n{mode}Tasks reset to pending (were executing):")
                for t in result["restarted_tasks"]:
                    print(f"  - {t}")
            else:
                print("\nNo tasks stuck in executing state")

            if result["worktrees_cleaned"]:
                print(f"\n{mode}Worktrees cleaned up:")
                for t in result["worktrees_cleaned"]:
                    print(f"  - .worktrees/{t}")

            if result["ready_for_verification"]:
                print(f"\nTasks ready for verification:")
                for t in result["ready_for_verification"]:
                    print(f"  - {t}")

            if result["ready_for_merge"]:
                print(f"\nTasks ready for merge:")
                for t in result["ready_for_merge"]:
                    print(f"  - {t}")

            if not result["dry_run"]:
                print("\n✓ Resume complete. Continue from Stage 2 (spawn workers).")


if __name__ == "__main__":
    main()
