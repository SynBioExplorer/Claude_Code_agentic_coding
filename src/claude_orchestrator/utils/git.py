"""Git operations utility functions."""

from __future__ import annotations

import subprocess
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


def run_command(
    command: str,
    cwd: str | Path | None = None,
    timeout: int = 60,
) -> CommandResult:
    """Run a shell command and return the result.

    Args:
        command: Shell command to execute
        cwd: Working directory for the command
        timeout: Timeout in seconds

    Returns:
        CommandResult with returncode, stdout, stderr
    """
    import time

    start = time.time()

    try:
        result = subprocess.run(
            command,
            shell=True,
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
    # Get both staged and unstaged changes
    result = run_command(
        f"git diff --name-only {base}...HEAD",
        cwd=worktree,
    )

    if result.returncode != 0:
        # Fall back to comparing working tree
        result = run_command(
            f"git diff --name-only {base}",
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
        f"git diff --numstat main -- {file_path}",
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
            result = run_command(f"git add {f}", cwd=cwd)
            if result.returncode != 0:
                return result

    # Commit
    # Escape quotes in message
    safe_message = message.replace('"', '\\"')
    return run_command(f'git commit -m "{safe_message}"', cwd=cwd)


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
    cmd = f"git checkout -b {branch_name}"
    if start_point:
        cmd += f" {start_point}"
    return run_command(cmd, cwd=cwd)


def checkout_branch(branch_name: str, cwd: str | Path | None = None) -> CommandResult:
    """Checkout an existing branch.

    Args:
        branch_name: Branch to checkout
        cwd: Working directory

    Returns:
        CommandResult from git checkout
    """
    return run_command(f"git checkout {branch_name}", cwd=cwd)


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
    cmd = f"git merge {branch_name}"
    if message:
        safe_message = message.replace('"', '\\"')
        cmd += f' -m "{safe_message}"'
    return run_command(cmd, cwd=cwd)


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
    flag = "-D" if force else "-d"
    return run_command(f"git branch {flag} {branch_name}", cwd=cwd)


def stash_changes(cwd: str | Path | None = None, message: str | None = None) -> CommandResult:
    """Stash uncommitted changes.

    Args:
        cwd: Working directory
        message: Stash message

    Returns:
        CommandResult from git stash
    """
    cmd = "git stash"
    if message:
        safe_message = message.replace('"', '\\"')
        cmd += f' push -m "{safe_message}"'
    return run_command(cmd, cwd=cwd)


def stash_pop(cwd: str | Path | None = None) -> CommandResult:
    """Pop the most recent stash.

    Args:
        cwd: Working directory

    Returns:
        CommandResult from git stash pop
    """
    return run_command("git stash pop", cwd=cwd)
