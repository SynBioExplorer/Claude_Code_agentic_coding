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
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


STATE_FILE = ".orchestration-state.json"


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
            return hashlib.sha256(p.read_bytes()).hexdigest()[:8]
    return "no-lock"


def init_state(request: str, tasks_file: str = "tasks.yaml") -> dict:
    """Initialize orchestration state from tasks file."""
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

    Path(STATE_FILE).write_text(json.dumps(state, indent=2))
    return state


def load_state() -> dict | None:
    """Load existing state or return None."""
    p = Path(STATE_FILE)
    if p.exists():
        return json.loads(p.read_text())
    return None


def save_state(state: dict):
    """Save state to file."""
    Path(STATE_FILE).write_text(json.dumps(state, indent=2))


def update_task(task_id: str, new_status: str, error: str = None) -> dict:
    """Update a task's status."""
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
        # Check worktree status file for latest
        status_file = Path(f".worktrees/{task_id}/.task-status.json")
        if status_file.exists():
            task_status = json.loads(status_file.read_text())
            status = task_status.get("status", "unknown")
        else:
            status = task_info.get("status", "pending")

        results.get(status, results["pending"]).append(task_id)

    return {
        "summary": results,
        "request_id": state.get("request_id"),
        "phase": state.get("current_phase"),
        "iteration": state.get("iteration"),
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

    # status command
    status_parser = subparsers.add_parser("status", help="Show status summary")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # update command
    update_parser = subparsers.add_parser("update", help="Update task status")
    update_parser.add_argument("task_id", help="Task ID")
    update_parser.add_argument("status", help="New status")
    update_parser.add_argument("--error", help="Error message if failed")

    args = parser.parse_args()

    if args.command == "init":
        state = init_state(args.request, args.tasks_file)
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


if __name__ == "__main__":
    main()
