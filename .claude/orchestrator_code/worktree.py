#!/usr/bin/env python3
"""Git worktree management for task isolation.

Standalone version for .claude/orchestrator_code.

Usage:
    python3 ~/.claude/orchestrator_code/worktree.py create <task-id> [--base main]
    python3 ~/.claude/orchestrator_code/worktree.py delete <task-id> [--force]
    python3 ~/.claude/orchestrator_code/worktree.py merge <task-id> [--target main]
    python3 ~/.claude/orchestrator_code/worktree.py list
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

# Import from local git.py
from git import CommandResult, run_command, get_repo_root, get_current_branch, abort_merge


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""

    path: Path
    branch: str
    commit: str
    task_id: str | None = None
    is_main: bool = False


class WorktreeManager:
    """Manages git worktrees for task isolation."""

    def __init__(
        self,
        repo_root: Path | None = None,
        worktree_dir: str = ".worktrees",
    ):
        """Initialize worktree manager.

        Args:
            repo_root: Root of the git repository
            worktree_dir: Directory name for worktrees (relative to repo root)
        """
        self.repo_root = repo_root or get_repo_root() or Path.cwd()
        self.worktree_dir = self.repo_root / worktree_dir

    def create_worktree(
        self,
        task_id: str,
        base_branch: str = "main",
    ) -> tuple[Path, CommandResult]:
        """Create a new worktree for a task.

        Args:
            task_id: Unique task identifier
            base_branch: Branch to base the worktree on

        Returns:
            Tuple of (worktree_path, CommandResult)
        """
        worktree_path = self.worktree_dir / task_id
        branch_name = f"task/{task_id}"

        # Ensure worktree directory exists
        self.worktree_dir.mkdir(parents=True, exist_ok=True)

        # Create worktree with new branch
        result = run_command(
            f"git worktree add -b {branch_name} {worktree_path} {base_branch}",
            cwd=self.repo_root,
        )

        return worktree_path, result

    def delete_worktree(self, task_id: str, force: bool = False) -> CommandResult:
        """Delete a worktree.

        Args:
            task_id: Task identifier
            force: Force removal even with uncommitted changes

        Returns:
            CommandResult from git worktree remove
        """
        worktree_path = self.worktree_dir / task_id
        force_flag = "--force" if force else ""

        result = run_command(
            f"git worktree remove {force_flag} {worktree_path}",
            cwd=self.repo_root,
        )

        # Also delete the branch if it exists
        branch_name = f"task/{task_id}"
        run_command(
            f"git branch -d {branch_name}",
            cwd=self.repo_root,
        )

        return result

    def merge_worktree(
        self,
        task_id: str,
        target_branch: str = "main",
        delete_after: bool = True,
    ) -> CommandResult:
        """Merge a worktree's changes into the target branch.

        If merge fails, automatically aborts to prevent dirty repo state.

        Args:
            task_id: Task identifier
            target_branch: Branch to merge into
            delete_after: Delete worktree after merge

        Returns:
            CommandResult from git merge
        """
        branch_name = f"task/{task_id}"

        # Checkout target branch in main repo
        checkout_result = run_command(
            f"git checkout {target_branch}",
            cwd=self.repo_root,
        )
        if checkout_result.returncode != 0:
            return checkout_result

        # Merge the task branch
        result = run_command(
            f'git merge {branch_name} -m "Merge task {task_id}"',
            cwd=self.repo_root,
        )

        # If merge failed, abort to prevent dirty repo state
        if result.returncode != 0:
            abort_merge(cwd=self.repo_root)
            return result

        if delete_after:
            self.delete_worktree(task_id)

        return result

    def list_worktrees(self) -> list[WorktreeInfo]:
        """List all worktrees.

        Returns:
            List of WorktreeInfo for all worktrees
        """
        result = run_command(
            "git worktree list --porcelain",
            cwd=self.repo_root,
        )

        if result.returncode != 0:
            return []

        worktrees: list[WorktreeInfo] = []
        current_wt: dict[str, str] = {}

        for line in result.stdout.strip().split("\n"):
            if not line:
                if current_wt:
                    wt_path = Path(current_wt.get("worktree", ""))
                    branch = current_wt.get("branch", "").replace("refs/heads/", "")
                    commit = current_wt.get("HEAD", "")

                    # Determine if this is a task worktree
                    task_id = None
                    if wt_path.parent == self.worktree_dir:
                        task_id = wt_path.name
                    elif branch.startswith("task/"):
                        task_id = branch[5:]

                    worktrees.append(
                        WorktreeInfo(
                            path=wt_path,
                            branch=branch,
                            commit=commit,
                            task_id=task_id,
                            is_main=wt_path == self.repo_root,
                        )
                    )
                    current_wt = {}
            elif line.startswith("worktree "):
                current_wt["worktree"] = line[9:]
            elif line.startswith("HEAD "):
                current_wt["HEAD"] = line[5:]
            elif line.startswith("branch "):
                current_wt["branch"] = line[7:]

        # Handle last entry
        if current_wt:
            wt_path = Path(current_wt.get("worktree", ""))
            branch = current_wt.get("branch", "").replace("refs/heads/", "")
            commit = current_wt.get("HEAD", "")

            task_id = None
            if wt_path.parent == self.worktree_dir:
                task_id = wt_path.name
            elif branch.startswith("task/"):
                task_id = branch[5:]

            worktrees.append(
                WorktreeInfo(
                    path=wt_path,
                    branch=branch,
                    commit=commit,
                    task_id=task_id,
                    is_main=wt_path == self.repo_root,
                )
            )

        return worktrees

    def get_worktree(self, task_id: str) -> WorktreeInfo | None:
        """Get worktree info for a specific task.

        Args:
            task_id: Task identifier

        Returns:
            WorktreeInfo if found, None otherwise
        """
        worktrees = self.list_worktrees()
        for wt in worktrees:
            if wt.task_id == task_id:
                return wt
        return None

    def get_worktree_path(self, task_id: str) -> Path:
        """Get the path to a task's worktree.

        Args:
            task_id: Task identifier

        Returns:
            Path to the worktree directory
        """
        return self.worktree_dir / task_id

    def worktree_exists(self, task_id: str) -> bool:
        """Check if a worktree exists for a task.

        Args:
            task_id: Task identifier

        Returns:
            True if worktree exists
        """
        return self.get_worktree(task_id) is not None

    def cleanup_stale_worktrees(self) -> list[str]:
        """Clean up stale worktrees (missing directories).

        Returns:
            List of task IDs that were cleaned up
        """
        # Prune worktrees with missing working directories
        run_command("git worktree prune", cwd=self.repo_root)

        # Find any remaining directories without worktree entries
        cleaned: list[str] = []

        if self.worktree_dir.exists():
            active_tasks = {wt.task_id for wt in self.list_worktrees() if wt.task_id}

            for entry in self.worktree_dir.iterdir():
                if entry.is_dir() and entry.name not in active_tasks:
                    # Stale directory - remove it
                    shutil.rmtree(entry)
                    cleaned.append(entry.name)

        return cleaned

    def cleanup_all_worktrees(self, force: bool = False) -> list[str]:
        """Remove all task worktrees.

        Args:
            force: Force removal even with uncommitted changes

        Returns:
            List of task IDs that were removed
        """
        removed: list[str] = []

        for wt in self.list_worktrees():
            if wt.task_id and not wt.is_main:
                result = self.delete_worktree(wt.task_id, force=force)
                if result.returncode == 0:
                    removed.append(wt.task_id)

        return removed


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Manage git worktrees for tasks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create command
    create_parser = subparsers.add_parser("create", help="Create a worktree for a task")
    create_parser.add_argument("task_id", help="Task identifier")
    create_parser.add_argument("--base", default="main", help="Base branch")

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a task worktree")
    delete_parser.add_argument("task_id", help="Task identifier")
    delete_parser.add_argument("--force", action="store_true", help="Force deletion")

    # merge command
    merge_parser = subparsers.add_parser("merge", help="Merge worktree into target branch")
    merge_parser.add_argument("task_id", help="Task identifier")
    merge_parser.add_argument("--target", default="main", help="Target branch")
    merge_parser.add_argument("--keep", action="store_true", help="Keep worktree after merge")

    # list command
    subparsers.add_parser("list", help="List all worktrees")

    # cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up stale worktrees")
    cleanup_parser.add_argument("--force", action="store_true", help="Force cleanup all")

    args = parser.parse_args()
    wm = WorktreeManager()

    if args.command == "create":
        path, result = wm.create_worktree(args.task_id, args.base)
        if result.returncode == 0:
            print(f"✓ Created worktree: {path}")
        else:
            print(f"✗ Failed: {result.stderr}")
            exit(1)

    elif args.command == "delete":
        result = wm.delete_worktree(args.task_id, force=args.force)
        if result.returncode == 0:
            print(f"✓ Deleted worktree for task: {args.task_id}")
        else:
            print(f"✗ Failed: {result.stderr}")
            exit(1)

    elif args.command == "merge":
        result = wm.merge_worktree(args.task_id, args.target, delete_after=not args.keep)
        if result.returncode == 0:
            print(f"✓ Merged task/{args.task_id} into {args.target}")
        else:
            print(f"✗ Merge failed (auto-aborted): {result.stderr}")
            exit(1)

    elif args.command == "list":
        worktrees = wm.list_worktrees()
        if worktrees:
            print("Worktrees:")
            for wt in worktrees:
                task_info = f" (task: {wt.task_id})" if wt.task_id else ""
                main_info = " [MAIN]" if wt.is_main else ""
                print(f"  {wt.branch}{task_info}{main_info}")
                print(f"    Path: {wt.path}")
        else:
            print("No worktrees found")

    elif args.command == "cleanup":
        if args.force:
            removed = wm.cleanup_all_worktrees(force=True)
            print(f"Removed {len(removed)} worktrees: {removed}")
        else:
            cleaned = wm.cleanup_stale_worktrees()
            print(f"Cleaned {len(cleaned)} stale worktrees: {cleaned}")


if __name__ == "__main__":
    main()
