"""Boundary validation for worktree isolation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from claude_orchestrator.utils.git import get_file_diff_stats, get_modified_files, run_command

if TYPE_CHECKING:
    from claude_orchestrator.schemas.config import OrchestrationConfig
    from claude_orchestrator.schemas.tasks import TaskSpec


# Default forbidden patterns - files that workers should never modify
DEFAULT_FORBIDDEN_PATTERNS: list[str] = [
    r"node_modules/",
    r"__pycache__/",
    r"\.pyc$",
    r"vendor/",
    r"dist/",
    r"build/",
    r"\.generated\.",
    r"\.min\.(js|css)$",
]

# Common lockfiles - derived from ecosystem configs
COMMON_LOCKFILES: list[str] = [
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
    "requirements.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
    "packages.lock.json",
    "composer.lock",
]


@dataclass
class BoundaryViolation:
    """A boundary violation found during validation."""

    type: str
    file: str
    message: str
    pattern: str | None = None
    lines_changed: int | None = None
    threshold: int | None = None


@dataclass
class BoundaryResult:
    """Result of boundary validation."""

    valid: bool
    violations: list[BoundaryViolation] = field(default_factory=list)

    def add_violation(self, violation: BoundaryViolation) -> None:
        """Add a violation and mark result as invalid."""
        self.violations.append(violation)
        self.valid = False


def get_lockfile_patterns(config: OrchestrationConfig | None = None) -> list[str]:
    """Get regex patterns for lockfiles.

    Args:
        config: Configuration with ecosystem settings

    Returns:
        List of regex patterns matching lockfiles
    """
    patterns: list[str] = []

    # From ecosystem config
    if config:
        for eco_config in config.dependencies.ecosystems.values():
            lockfile = eco_config.lockfile
            if lockfile:
                escaped = re.escape(lockfile)
                patterns.append(f"(^|/){escaped}$")

    # Common lockfiles as fallback
    for lockfile in COMMON_LOCKFILES:
        escaped = re.escape(lockfile)
        pattern = f"(^|/){escaped}$"
        if pattern not in patterns:
            patterns.append(pattern)

    return patterns


def check_forbidden_patterns(
    file_path: str,
    config: OrchestrationConfig | None = None,
) -> str | None:
    """Check if a file matches any forbidden pattern.

    Args:
        file_path: Path to check
        config: Configuration with forbidden patterns

    Returns:
        Matching pattern if found, None otherwise
    """
    forbidden = (
        config.boundaries.forbidden_patterns
        if config
        else DEFAULT_FORBIDDEN_PATTERNS
    )

    for pattern in forbidden:
        if re.search(pattern, file_path):
            return pattern

    return None


def check_lockfile_pattern(
    file_path: str,
    config: OrchestrationConfig | None = None,
) -> str | None:
    """Check if a file is a lockfile.

    Args:
        file_path: Path to check
        config: Configuration with ecosystem settings

    Returns:
        Matching pattern if file is a lockfile, None otherwise
    """
    patterns = get_lockfile_patterns(config)

    for pattern in patterns:
        if re.search(pattern, file_path):
            return pattern

    return None


def validate_boundaries(
    task_id: str,
    task_spec: TaskSpec,
    config: OrchestrationConfig | None = None,
    worktree_base: Path | None = None,
) -> BoundaryResult:
    """Validate file boundaries for a task.

    Checks:
    1. Files modified are in files_write or files_append
    2. No forbidden patterns (node_modules, __pycache__, etc.)
    3. No lockfile modifications (only Supervisor can modify)
    4. Churn detection (excessive line changes)
    5. Format-only changes (for whitespace-insensitive files)

    Args:
        task_id: Task identifier
        task_spec: Task specification with file boundaries
        config: Configuration for thresholds and patterns
        worktree_base: Base path for worktrees

    Returns:
        BoundaryResult with validity and any violations
    """
    result = BoundaryResult(valid=True)

    # Determine worktree path
    if worktree_base:
        worktree_path = worktree_base / task_id
    else:
        worktree_path = Path(f".worktrees/{task_id}")

    # Get modified files
    modified = get_modified_files(worktree_path)
    allowed = set(task_spec.files_write) | set(task_spec.files_append)

    # Check 1: Files outside allowlist
    unauthorized = modified - allowed
    for f in unauthorized:
        result.add_violation(
            BoundaryViolation(
                type="unauthorized_file",
                file=f,
                message=f"Modified file not in files_write or files_append: {f}",
            )
        )

    # Check 2: Forbidden patterns
    forbidden_patterns = (
        config.boundaries.forbidden_patterns if config else DEFAULT_FORBIDDEN_PATTERNS
    )
    for f in modified:
        for pattern in forbidden_patterns:
            if re.search(pattern, f):
                result.add_violation(
                    BoundaryViolation(
                        type="forbidden_pattern",
                        file=f,
                        pattern=pattern,
                        message=f"Worker cannot modify files matching {pattern}",
                    )
                )
                break

    # Check 3: Lockfile modifications
    lockfile_patterns = get_lockfile_patterns(config)
    for f in modified:
        for pattern in lockfile_patterns:
            if re.search(pattern, f):
                result.add_violation(
                    BoundaryViolation(
                        type="forbidden_lockfile",
                        file=f,
                        pattern=pattern,
                        message=f"Worker cannot modify lockfile: {f}. Only Supervisor can modify lockfiles.",
                    )
                )
                break

    # Check 4: Excessive churn
    if config and config.boundaries.reject_excessive_churn:
        churn_threshold = config.boundaries.churn_threshold_lines

        for f in modified & allowed:
            stats = get_file_diff_stats(worktree_path, f)

            if stats.lines_changed > churn_threshold:
                if not task_spec.allow_large_changes:
                    result.add_violation(
                        BoundaryViolation(
                            type="excessive_churn",
                            file=f,
                            lines_changed=stats.lines_changed,
                            threshold=churn_threshold,
                            message=f"Excessive changes ({stats.lines_changed} lines) in {f}. "
                            f"Threshold: {churn_threshold}. Set allow_large_changes: true to override.",
                        )
                    )

    # Check 5: Format-only changes
    if config and config.boundaries.reject_formatting_churn:
        allowlist = set(config.boundaries.formatting_check_allowlist)
        denylist = set(config.boundaries.formatting_check_denylist)

        for f in modified & allowed:
            if is_formatting_only_change(worktree_path, f, allowlist, denylist):
                result.add_violation(
                    BoundaryViolation(
                        type="formatting_only",
                        file=f,
                        message=f"File {f} has only formatting changes (whitespace-only diff).",
                    )
                )

    return result


def is_formatting_only_change(
    worktree: Path,
    file_path: str,
    allowlist: set[str],
    denylist: set[str],
) -> bool:
    """Detect if changes are only whitespace/formatting.

    Only applies to whitespace-insensitive file types.

    Args:
        worktree: Path to the worktree
        file_path: Path to the file
        allowlist: File extensions to check
        denylist: File extensions to skip

    Returns:
        True if changes are formatting-only
    """
    ext = Path(file_path).suffix.lower()
    name = Path(file_path).name

    # Check denylist first (whitespace-sensitive files)
    if ext in denylist or name in denylist:
        return False

    # Only check allowlisted types
    if ext not in allowlist:
        return False

    # Use git diff ignoring whitespace
    result = run_command(
        f'git diff -w --quiet main -- "{file_path}"',
        cwd=worktree,
    )

    # Exit code 0 = no semantic diff (only whitespace changes)
    return result.returncode == 0


def check_unauthorized_files(
    modified: set[str],
    allowed: set[str],
) -> list[BoundaryViolation]:
    """Check for files modified outside the allowlist.

    Args:
        modified: Set of modified file paths
        allowed: Set of allowed file paths

    Returns:
        List of violations for unauthorized files
    """
    violations: list[BoundaryViolation] = []

    unauthorized = modified - allowed
    for f in unauthorized:
        violations.append(
            BoundaryViolation(
                type="unauthorized_file",
                file=f,
                message=f"Modified file not in files_write: {f}",
            )
        )

    return violations
