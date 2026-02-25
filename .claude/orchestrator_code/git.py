#!/usr/bin/env python3
"""Git operations utility functions.

Standalone version for .claude/orchestrator_code with no internal package imports.

Usage:
    python3 ~/.claude/orchestrator_code/git.py modified <worktree_path>
    python3 ~/.claude/orchestrator_code/git.py diff-stats <worktree_path> <file>
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    """Result of a shell command execution."""

    returncode: int
    stdout: str
    stderr: str
    duration_ms: int = 0


@dataclass
class FileDiffStats:
    """Statistics for a file diff."""

    lines_added: int
    lines_removed: int
    lines_changed: int


import re

# Valid task ID pattern - prevents shell injection via branch names
SAFE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_./-]*$')


def validate_ref_name(name: str) -> str:
    """Validate a git ref name (branch, tag) is safe.

    Raises ValueError if the name contains characters that could enable
    shell injection when used in git commands.
    """
    if not SAFE_ID_PATTERN.match(name):
        raise ValueError(
            f"Unsafe git ref name: {name!r}. "
            f"Must match {SAFE_ID_PATTERN.pattern}"
        )
    return name


def run_command(
    command: str | list[str],
    cwd: str | Path | None = None,
    timeout: int = 60,
) -> CommandResult:
    """Run a command and return the result.

    Args:
        command: Command as argument list (preferred) or shell string (legacy)
        cwd: Working directory for the command
        timeout: Timeout in seconds

    Returns:
        CommandResult with returncode, stdout, stderr
    """
    start = time.time()
    use_shell = isinstance(command, str)

    try:
        result = subprocess.run(
            command,
            shell=use_shell,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.time() - start) * 1000)

        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start) * 1000)
        return CommandResult(
            returncode=-1,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            duration_ms=duration_ms,
        )
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return CommandResult(
            returncode=-1,
            stdout="",
            stderr=str(e),
            duration_ms=duration_ms,
        )


def get_repo_root(path: str | Path | None = None) -> Path | None:
    """Get the root directory of a git repository.

    Args:
        path: Path within the repository (defaults to cwd)

    Returns:
        Path to repository root, or None if not in a repo
    """
    result = run_command("git rev-parse --show-toplevel", cwd=path)
    if result.returncode == 0:
        return Path(result.stdout.strip())
    return None


def get_current_branch(cwd: str | Path | None = None) -> str | None:
    """Get the current git branch name.

    Args:
        cwd: Working directory

    Returns:
        Branch name, or None if detached or not in a repo
    """
    result = run_command("git rev-parse --abbrev-ref HEAD", cwd=cwd)
    if result.returncode == 0:
        branch = result.stdout.strip()
        return None if branch == "HEAD" else branch
    return None


def get_current_commit(cwd: str | Path | None = None) -> str | None:
    """Get the current commit hash.

    Args:
        cwd: Working directory

    Returns:
        Full commit hash, or None if not in a repo
    """
    result = run_command("git rev-parse HEAD", cwd=cwd)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def get_short_commit(cwd: str | Path | None = None) -> str | None:
    """Get the short commit hash (7 characters).

    Args:
        cwd: Working directory

    Returns:
        Short commit hash, or None if not in a repo
    """
    result = run_command("git rev-parse --short HEAD", cwd=cwd)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def get_modified_files(worktree: str | Path, base: str = "main") -> set[str]:
    """Get files modified in a worktree compared to base branch.

    Args:
        worktree: Path to the worktree
        base: Base branch to compare against

    Returns:
        Set of modified file paths (relative to worktree)
    """
    validate_ref_name(base)
    # Get both staged and unstaged changes
    result = run_command(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=worktree,
    )

    if result.returncode != 0:
        # Fall back to comparing working tree
        result = run_command(
            ["git", "diff", "--name-only", base],
            cwd=worktree,
        )

    if result.returncode == 0:
        return {f.strip() for f in result.stdout.strip().split("\n") if f.strip()}

    return set()


def get_staged_files(cwd: str | Path | None = None) -> set[str]:
    """Get files staged for commit.

    Args:
        cwd: Working directory

    Returns:
        Set of staged file paths
    """
    result = run_command("git diff --cached --name-only", cwd=cwd)
    if result.returncode == 0:
        return {f.strip() for f in result.stdout.strip().split("\n") if f.strip()}
    return set()


def get_unstaged_files(cwd: str | Path | None = None) -> set[str]:
    """Get files with unstaged changes.

    Args:
        cwd: Working directory

    Returns:
        Set of file paths with unstaged changes
    """
    result = run_command("git diff --name-only", cwd=cwd)
    if result.returncode == 0:
        return {f.strip() for f in result.stdout.strip().split("\n") if f.strip()}
    return set()


def get_file_diff_stats(worktree: str | Path, file_path: str) -> FileDiffStats:
    """Get diff statistics for a specific file.

    Args:
        worktree: Path to the worktree
        file_path: Path to the file (relative to worktree)

    Returns:
        FileDiffStats with lines added, removed, and total changed
    """
    result = run_command(
        ["git", "diff", "--numstat", "main", "--", file_path],
        cwd=worktree,
    )

    if result.returncode == 0 and result.stdout.strip():
        parts = result.stdout.strip().split()
        if len(parts) >= 2:
            try:
                added = int(parts[0]) if parts[0] != "-" else 0
                removed = int(parts[1]) if parts[1] != "-" else 0
                return FileDiffStats(
                    lines_added=added,
                    lines_removed=removed,
                    lines_changed=added + removed,
                )
            except ValueError:
                pass

    return FileDiffStats(lines_added=0, lines_removed=0, lines_changed=0)


def commit_changes(
    cwd: str | Path,
    message: str,
    files: list[str] | None = None,
) -> CommandResult:
    """Commit changes in a working directory.

    Args:
        cwd: Working directory
        message: Commit message
        files: Specific files to commit (None for all staged)

    Returns:
        CommandResult from git commit
    """
    # Stage files if specified
    if files:
        for f in files:
            result = run_command(["git", "add", f], cwd=cwd)
            if result.returncode != 0:
                return result

    # Commit using argument list (no shell escaping needed)
    return run_command(["git", "commit", "-m", message], cwd=cwd)


def create_branch(
    branch_name: str,
    cwd: str | Path | None = None,
    start_point: str | None = None,
) -> CommandResult:
    """Create a new branch.

    Args:
        branch_name: Name for the new branch
        cwd: Working directory
        start_point: Starting commit/branch (defaults to HEAD)

    Returns:
        CommandResult from git branch
    """
    validate_ref_name(branch_name)
    cmd = ["git", "checkout", "-b", branch_name]
    if start_point:
        validate_ref_name(start_point)
        cmd.append(start_point)
    return run_command(cmd, cwd=cwd)


def checkout_branch(branch_name: str, cwd: str | Path | None = None) -> CommandResult:
    """Checkout an existing branch.

    Args:
        branch_name: Branch to checkout
        cwd: Working directory

    Returns:
        CommandResult from git checkout
    """
    validate_ref_name(branch_name)
    return run_command(["git", "checkout", branch_name], cwd=cwd)


def merge_branch(
    branch_name: str,
    cwd: str | Path | None = None,
    message: str | None = None,
) -> CommandResult:
    """Merge a branch into the current branch.

    Args:
        branch_name: Branch to merge
        cwd: Working directory
        message: Merge commit message

    Returns:
        CommandResult from git merge
    """
    validate_ref_name(branch_name)
    cmd = ["git", "merge", branch_name]
    if message:
        cmd.extend(["-m", message])
    return run_command(cmd, cwd=cwd)


def abort_merge(cwd: str | Path | None = None) -> CommandResult:
    """Abort a merge in progress.
    
    Args:
        cwd: Working directory
        
    Returns:
        CommandResult from git merge --abort
    """
    return run_command("git merge --abort", cwd=cwd)


def delete_branch(
    branch_name: str,
    cwd: str | Path | None = None,
    force: bool = False,
) -> CommandResult:
    """Delete a branch.

    Args:
        branch_name: Branch to delete
        cwd: Working directory
        force: Force delete even if not merged

    Returns:
        CommandResult from git branch -d/-D
    """
    validate_ref_name(branch_name)
    flag = "-D" if force else "-d"
    return run_command(["git", "branch", flag, branch_name], cwd=cwd)


def stash_changes(cwd: str | Path | None = None, message: str | None = None) -> CommandResult:
    """Stash uncommitted changes.

    Args:
        cwd: Working directory
        message: Stash message

    Returns:
        CommandResult from git stash
    """
    cmd = ["git", "stash"]
    if message:
        cmd.extend(["push", "-m", message])
    return run_command(cmd, cwd=cwd)


def stash_pop(cwd: str | Path | None = None) -> CommandResult:
    """Pop the most recent stash.

    Args:
        cwd: Working directory

    Returns:
        CommandResult from git stash pop
    """
    return run_command("git stash pop", cwd=cwd)


def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Git utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # modified command
    mod_parser = subparsers.add_parser("modified", help="Get modified files in worktree")
    mod_parser.add_argument("worktree", help="Path to worktree")
    mod_parser.add_argument("--base", default="main", help="Base branch")
    
    # diff-stats command
    diff_parser = subparsers.add_parser("diff-stats", help="Get diff stats for a file")
    diff_parser.add_argument("worktree", help="Path to worktree")
    diff_parser.add_argument("file", help="File to get stats for")
    
    # repo-root command
    subparsers.add_parser("repo-root", help="Get repository root")
    
    args = parser.parse_args()
    
    if args.command == "modified":
        files = get_modified_files(args.worktree, args.base)
        print(json.dumps(list(files), indent=2))
        
    elif args.command == "diff-stats":
        stats = get_file_diff_stats(args.worktree, args.file)
        print(json.dumps({
            "lines_added": stats.lines_added,
            "lines_removed": stats.lines_removed,
            "lines_changed": stats.lines_changed
        }, indent=2))
        
    elif args.command == "repo-root":
        root = get_repo_root()
        print(root if root else "Not in a git repository")


if __name__ == "__main__":
    main()
