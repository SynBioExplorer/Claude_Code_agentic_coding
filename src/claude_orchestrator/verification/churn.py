"""Churn detection for verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from claude_orchestrator.utils.git import get_file_diff_stats, get_modified_files, run_command

if TYPE_CHECKING:
    from claude_orchestrator.schemas.config import OrchestrationConfig


# File extensions where whitespace is NOT semantic (safe for formatting check)
FORMATTING_CHECK_ALLOWLIST: set[str] = {
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".json",
    ".md",
    ".rst",
    ".css",
    ".scss",
    ".less",
    ".html",
    ".xml",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".cs",
    ".rb",
    ".php",
}

# File extensions where whitespace IS semantic (skip formatting check)
FORMATTING_CHECK_DENYLIST: set[str] = {
    ".py",
    ".yaml",
    ".yml",
    ".mk",
    ".haml",
    ".pug",
    ".jade",
    ".coffee",
    ".slim",
}

# File names where whitespace is semantic
FORMATTING_CHECK_DENYLIST_NAMES: set[str] = {
    "Makefile",
    "makefile",
    "GNUmakefile",
}


@dataclass
class ChurnResult:
    """Result of churn detection."""

    file_path: str
    lines_added: int
    lines_removed: int
    lines_changed: int
    exceeds_threshold: bool
    threshold: int


@dataclass
class FormattingResult:
    """Result of formatting-only detection."""

    file_path: str
    is_formatting_only: bool
    reason: str


def detect_excessive_churn(
    worktree: Path,
    file_path: str,
    threshold: int = 500,
) -> ChurnResult:
    """Detect if a file has excessive changes.

    Args:
        worktree: Path to the worktree
        file_path: Path to the file
        threshold: Line change threshold

    Returns:
        ChurnResult with change statistics
    """
    stats = get_file_diff_stats(worktree, file_path)

    return ChurnResult(
        file_path=file_path,
        lines_added=stats.lines_added,
        lines_removed=stats.lines_removed,
        lines_changed=stats.lines_changed,
        exceeds_threshold=stats.lines_changed > threshold,
        threshold=threshold,
    )


def detect_all_churn(
    worktree: Path,
    threshold: int = 500,
    base_branch: str = "main",
) -> list[ChurnResult]:
    """Detect churn for all modified files.

    Args:
        worktree: Path to the worktree
        threshold: Line change threshold
        base_branch: Base branch to compare against

    Returns:
        List of ChurnResult for files exceeding threshold
    """
    modified = get_modified_files(worktree, base=base_branch)
    results: list[ChurnResult] = []

    for file_path in modified:
        result = detect_excessive_churn(worktree, file_path, threshold)
        if result.exceeds_threshold:
            results.append(result)

    return results


def is_formatting_only_change(
    worktree: Path,
    file_path: str,
    config: OrchestrationConfig | None = None,
) -> FormattingResult:
    """Detect if changes are only whitespace/formatting.

    Only applies to whitespace-insensitive file types.

    Args:
        worktree: Path to the worktree
        file_path: Path to the file
        config: Configuration with allowlist/denylist

    Returns:
        FormattingResult indicating if changes are formatting-only
    """
    ext = Path(file_path).suffix.lower()
    name = Path(file_path).name

    # Get config or use defaults
    if config:
        allowlist = set(config.boundaries.formatting_check_allowlist)
        denylist = set(config.boundaries.formatting_check_denylist)
    else:
        allowlist = FORMATTING_CHECK_ALLOWLIST
        denylist = FORMATTING_CHECK_DENYLIST

    # Check denylist first (whitespace-sensitive files)
    if ext in denylist or name in FORMATTING_CHECK_DENYLIST_NAMES:
        return FormattingResult(
            file_path=file_path,
            is_formatting_only=False,
            reason=f"File type {ext or name} is whitespace-sensitive",
        )

    # Only check allowlisted types
    if ext not in allowlist:
        return FormattingResult(
            file_path=file_path,
            is_formatting_only=False,
            reason=f"File type {ext} not in formatting check allowlist",
        )

    # Use git diff ignoring whitespace
    result = run_command(
        f'git diff -w --quiet main -- "{file_path}"',
        cwd=worktree,
    )

    if result.returncode == 0:
        return FormattingResult(
            file_path=file_path,
            is_formatting_only=True,
            reason="No semantic changes (whitespace-only diff)",
        )
    else:
        return FormattingResult(
            file_path=file_path,
            is_formatting_only=False,
            reason="Has semantic changes beyond whitespace",
        )


def detect_all_formatting_only(
    worktree: Path,
    config: OrchestrationConfig | None = None,
    base_branch: str = "main",
) -> list[FormattingResult]:
    """Detect formatting-only changes in all modified files.

    Args:
        worktree: Path to the worktree
        config: Configuration
        base_branch: Base branch to compare against

    Returns:
        List of FormattingResult for files with formatting-only changes
    """
    modified = get_modified_files(worktree, base=base_branch)
    results: list[FormattingResult] = []

    for file_path in modified:
        result = is_formatting_only_change(worktree, file_path, config)
        if result.is_formatting_only:
            results.append(result)

    return results


def get_churn_summary(results: list[ChurnResult]) -> str:
    """Generate a summary of churn detection results.

    Args:
        results: List of ChurnResult

    Returns:
        Human-readable summary
    """
    if not results:
        return "No excessive churn detected."

    lines = [f"Excessive churn detected in {len(results)} file(s):"]

    for r in results:
        lines.append(
            f"  - {r.file_path}: {r.lines_changed} lines changed "
            f"(threshold: {r.threshold})"
        )

    return "\n".join(lines)


def get_formatting_summary(results: list[FormattingResult]) -> str:
    """Generate a summary of formatting-only detection results.

    Args:
        results: List of FormattingResult

    Returns:
        Human-readable summary
    """
    if not results:
        return "No formatting-only changes detected."

    lines = [f"Formatting-only changes detected in {len(results)} file(s):"]

    for r in results:
        lines.append(f"  - {r.file_path}")

    return "\n".join(lines)
