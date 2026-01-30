#!/usr/bin/env python3
"""
Verification utilities for task completion.

Validates file boundaries, runs verification commands, checks environment.

Usage:
    python3 ~/.claude/orchestrator_code/verify.py boundaries task-a tasks.yaml
    python3 ~/.claude/orchestrator_code/verify.py commands task-a tasks.yaml
    python3 ~/.claude/orchestrator_code/verify.py full task-a tasks.yaml
"""

import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


FORBIDDEN_PATTERNS = [
    "node_modules/",
    "__pycache__/",
    ".git/",
    "*.pyc",
    ".env",
    "*.lock",  # lockfiles should only be modified by supervisor
]


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


def get_task_spec(tasks_file: str, task_id: str) -> dict | None:
    """Get task specification by ID."""
    plan = load_plan(tasks_file)
    for task in plan.get("tasks", []):
        if task["id"] == task_id:
            return task
    return None


def get_modified_files(worktree_path: str) -> list:
    """Get list of files modified in worktree."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1..HEAD"],
            cwd=worktree_path,
            capture_output=True, text=True, check=True
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        # Try comparing against main
        result = subprocess.run(
            ["git", "diff", "--name-only", "main...HEAD"],
            cwd=worktree_path,
            capture_output=True, text=True
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def validate_boundaries(task_id: str, tasks_file: str = "tasks.yaml") -> dict:
    """Validate that only allowed files were modified."""
    task = get_task_spec(tasks_file, task_id)
    if task is None:
        return {"valid": False, "error": f"Task {task_id} not found"}

    worktree_path = f".worktrees/{task_id}"
    if not Path(worktree_path).exists():
        return {"valid": False, "error": f"Worktree not found: {worktree_path}"}

    modified = get_modified_files(worktree_path)
    allowed = set(task.get("files_write", []))

    # Check for unauthorized modifications
    unauthorized = []
    forbidden = []

    for f in modified:
        # Check forbidden patterns
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.endswith("/"):
                if f.startswith(pattern) or f"/{pattern}" in f:
                    forbidden.append(f)
                    break
            elif pattern.startswith("*"):
                if f.endswith(pattern[1:]):
                    forbidden.append(f)
                    break
            elif pattern in f:
                forbidden.append(f)
                break
        else:
            # Check if in allowed list
            if f not in allowed:
                unauthorized.append(f)

    return {
        "valid": len(unauthorized) == 0 and len(forbidden) == 0,
        "modified": modified,
        "allowed": list(allowed),
        "unauthorized": unauthorized,
        "forbidden": forbidden
    }


def validate_task_verification(task: dict) -> tuple[bool, str]:
    """Validate that a task has proper verification commands.

    Per ARCHITECTURE spec, verification commands are a HARD REQUIREMENT.
    Tasks with empty verification arrays are invalid.

    Args:
        task: Task specification dict

    Returns:
        tuple of (is_valid, error_message)
    """
    verification = task.get("verification", [])

    if not verification:
        return False, "Task has no verification commands (HARD REQUIREMENT)"

    # Check each verification command has required fields
    for i, v in enumerate(verification):
        if not v.get("command"):
            return False, f"Verification {i} has no command"

    return True, ""


def run_verification_commands(
    task_id: str,
    tasks_file: str = "tasks.yaml",
    fail_fast: bool = True
) -> dict:
    """Run all verification commands for a task.

    Args:
        task_id: Task identifier
        tasks_file: Path to tasks YAML file
        fail_fast: If True, stop on first required command failure (default True)
    """
    task = get_task_spec(tasks_file, task_id)
    if task is None:
        return {"success": False, "error": f"Task {task_id} not found"}

    # Validate verification commands exist (HARD REQUIREMENT)
    valid, error = validate_task_verification(task)
    if not valid:
        return {"success": False, "error": error, "validation_failed": True}

    worktree_path = f".worktrees/{task_id}"
    if not Path(worktree_path).exists():
        return {"success": False, "error": f"Worktree not found: {worktree_path}"}

    results = []
    all_passed = True

    for verification in task.get("verification", []):
        command = verification.get("command", "")
        vtype = verification.get("type", "check")
        required = verification.get("required", True)

        # Resolve placeholders
        modified_files = get_modified_files(worktree_path)
        command = command.replace("{modified_files}", " ".join(modified_files))

        # Run command with configurable timeout (default 5 minutes, allow up to 10)
        timeout_seconds = verification.get("timeout", 300)
        if timeout_seconds > 600:
            timeout_seconds = 600  # Cap at 10 minutes

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            passed = result.returncode == 0
        except subprocess.TimeoutExpired:
            passed = False
            result = type('obj', (object,), {
                'stdout': '',
                'stderr': f'Timeout after {timeout_seconds} seconds'
            })()

        if required and not passed:
            all_passed = False

        results.append({
            "command": command,
            "type": vtype,
            "required": required,
            "passed": passed,
            "stdout": result.stdout[:1000] if passed else "",
            "stderr": result.stderr[:1000] if not passed else ""
        })

        # Fail-fast: stop on first required command failure
        if fail_fast and required and not passed:
            return {
                "success": False,
                "results": results,
                "passed": sum(1 for r in results if r["passed"]),
                "failed": sum(1 for r in results if not r["passed"]),
                "stopped_early": True,
                "failed_at": command
            }

    return {
        "success": all_passed,
        "results": results,
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"])
    }


def full_verify(task_id: str, tasks_file: str = "tasks.yaml", env_hash: str = None) -> dict:
    """Run full verification suite."""
    # 1. Boundary check
    boundary_result = validate_boundaries(task_id, tasks_file)

    # 2. Verification commands
    command_result = run_verification_commands(task_id, tasks_file)

    # 3. Environment hash check
    env_valid = True
    if env_hash:
        from environment import verify_env_hash
        worktree_path = Path(f".worktrees/{task_id}")
        env_valid, actual, _ = verify_env_hash(env_hash, worktree_path)

    all_valid = boundary_result["valid"] and command_result["success"] and env_valid

    return {
        "valid": all_valid,
        "boundaries": boundary_result,
        "commands": command_result,
        "environment": {"valid": env_valid, "expected": env_hash}
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Task verification utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # boundaries command
    bound_parser = subparsers.add_parser("boundaries", help="Check file boundaries")
    bound_parser.add_argument("task_id", help="Task ID")
    bound_parser.add_argument("tasks_file", nargs="?", default="tasks.yaml")
    bound_parser.add_argument("--json", action="store_true")

    # commands command
    cmd_parser = subparsers.add_parser("commands", help="Run verification commands")
    cmd_parser.add_argument("task_id", help="Task ID")
    cmd_parser.add_argument("tasks_file", nargs="?", default="tasks.yaml")
    cmd_parser.add_argument("--json", action="store_true")

    # full command
    full_parser = subparsers.add_parser("full", help="Full verification suite")
    full_parser.add_argument("task_id", help="Task ID")
    full_parser.add_argument("tasks_file", nargs="?", default="tasks.yaml")
    full_parser.add_argument("--env-hash", help="Expected environment hash")
    full_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "boundaries":
        result = validate_boundaries(args.task_id, args.tasks_file)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["valid"]:
                print(f"✓ Boundaries valid for {args.task_id}")
                print(f"  Modified: {result['modified']}")
            else:
                print(f"✗ Boundary violations for {args.task_id}")
                if result.get("unauthorized"):
                    print(f"  Unauthorized: {result['unauthorized']}")
                if result.get("forbidden"):
                    print(f"  Forbidden: {result['forbidden']}")
        sys.exit(0 if result["valid"] else 1)

    elif args.command == "commands":
        result = run_verification_commands(args.task_id, args.tasks_file)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["success"]:
                print(f"✓ All verification commands passed ({result['passed']}/{result['passed']})")
            else:
                print(f"✗ Verification failed ({result['passed']}/{result['passed'] + result['failed']} passed)")
                for r in result["results"]:
                    status = "✓" if r["passed"] else "✗"
                    print(f"  {status} {r['command']}")
                    if not r["passed"] and r["stderr"]:
                        print(f"    Error: {r['stderr'][:200]}")
        sys.exit(0 if result["success"] else 1)

    elif args.command == "full":
        result = full_verify(args.task_id, args.tasks_file, args.env_hash)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["valid"]:
                print(f"✓ Full verification passed for {args.task_id}")
            else:
                print(f"✗ Verification failed for {args.task_id}")
                if not result["boundaries"]["valid"]:
                    print(f"  Boundary issues: {result['boundaries'].get('unauthorized', [])}")
                if not result["commands"]["success"]:
                    print(f"  Command failures: {result['commands']['failed']}")
                if not result["environment"]["valid"]:
                    print(f"  Environment mismatch")
        sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
