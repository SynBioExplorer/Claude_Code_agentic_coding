"""Verification command execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from claude_orchestrator.utils.git import get_modified_files, run_command

if TYPE_CHECKING:
    from claude_orchestrator.schemas.status import OrchestrationState
    from claude_orchestrator.schemas.tasks import TaskSpec, VerificationCheck


@dataclass
class CheckResult:
    """Result of a single verification check."""

    command: str
    resolved_command: str
    type: str
    required: bool
    passed: bool
    output: str = ""
    error: str = ""
    duration_ms: int = 0


@dataclass
class VerificationResult:
    """Complete verification result for a task."""

    task_id: str
    all_passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    verified_at: str = ""

    def __post_init__(self) -> None:
        if not self.verified_at:
            self.verified_at = datetime.now().isoformat()


def resolve_verification_command(
    command: str,
    task_spec: TaskSpec,
    worktree: Path,
) -> str:
    """Resolve template placeholders in verification commands.

    Supported placeholders:
    - {modified_files}: Files modified by this task
    - {modified_tests}: Test files for modified source files

    Args:
        command: Command template with placeholders
        task_spec: Task specification
        worktree: Path to the task's worktree

    Returns:
        Command with placeholders resolved
    """
    if "{modified_files}" in command:
        modified = get_modified_files(worktree)
        files_str = " ".join(sorted(modified)) or "."
        command = command.replace("{modified_files}", files_str)

    if "{modified_tests}" in command:
        modified = get_modified_files(worktree)
        test_files = resolve_test_files(modified, worktree)
        tests_str = " ".join(sorted(test_files)) or "tests/"
        command = command.replace("{modified_tests}", tests_str)

    return command


def resolve_test_files(modified_files: set[str], worktree: Path) -> list[str]:
    """Map modified source files to their test files.

    Convention: test file for src/foo.py is tests/test_foo.py

    Args:
        modified_files: Set of modified file paths
        worktree: Path to the worktree

    Returns:
        List of test file paths
    """
    test_files: list[str] = []

    for f in modified_files:
        # If it's already a test file, include it
        if f.startswith("tests/") or "_test.py" in f or "test_" in f:
            if (worktree / f).exists():
                test_files.append(f)
            continue

        # Map source file to test file
        if f.startswith("src/") and f.endswith(".py"):
            base = Path(f).stem
            parent = Path(f).parent.name

            candidates = [
                f"tests/test_{base}.py",
                f"tests/{base}_test.py",
                f"tests/test_{parent}_{base}.py",
                f"tests/{parent}/test_{base}.py",
            ]

            for candidate in candidates:
                if (worktree / candidate).exists():
                    test_files.append(candidate)
                    break

    return test_files


def verify_task(
    task_id: str,
    task_spec: TaskSpec,
    worktree_base: Path,
    global_state: OrchestrationState | None = None,
) -> VerificationResult:
    """Execute all verification commands for a task.

    Args:
        task_id: Task identifier
        task_spec: Task specification with verification commands
        worktree_base: Base path for worktrees
        global_state: Global orchestration state (for env hash validation)

    Returns:
        VerificationResult with all check results
    """
    worktree = worktree_base / task_id
    results: list[CheckResult] = []

    for check in task_spec.verification:
        result = run_verification_check(check, task_spec, worktree)
        results.append(result)

    # Determine overall pass/fail
    all_passed = all(r.passed for r in results if r.required)

    return VerificationResult(
        task_id=task_id,
        all_passed=all_passed,
        checks=results,
    )


def run_verification_check(
    check: VerificationCheck,
    task_spec: TaskSpec,
    worktree: Path,
) -> CheckResult:
    """Run a single verification check.

    Args:
        check: Verification check specification
        task_spec: Task specification
        worktree: Path to the worktree

    Returns:
        CheckResult with pass/fail and output
    """
    # Resolve command templates
    resolved = resolve_verification_command(check.command, task_spec, worktree)

    # Execute the command
    cmd_result = run_command(resolved, cwd=worktree, timeout=300)

    return CheckResult(
        command=check.command,
        resolved_command=resolved,
        type=check.type.value,
        required=check.required,
        passed=cmd_result.returncode == 0,
        output=cmd_result.stdout,
        error=cmd_result.stderr,
        duration_ms=cmd_result.duration_ms,
    )


def run_global_verification(
    commands: list[str],
    project_root: Path,
) -> list[CheckResult]:
    """Run global verification commands (post-merge).

    Args:
        commands: List of command templates
        project_root: Root directory of the project

    Returns:
        List of check results
    """
    results: list[CheckResult] = []

    for command in commands:
        # Global commands typically don't have {modified_*} placeholders
        cmd_result = run_command(command, cwd=project_root, timeout=600)

        results.append(
            CheckResult(
                command=command,
                resolved_command=command,
                type="global",
                required=True,
                passed=cmd_result.returncode == 0,
                output=cmd_result.stdout,
                error=cmd_result.stderr,
                duration_ms=cmd_result.duration_ms,
            )
        )

    return results
