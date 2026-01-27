"""Integration tests for worktree management.

These tests require git to be installed and available.
They create actual git repositories for testing.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from claude_orchestrator.worktree.manager import WorktreeManager


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    (repo_path / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Create main branch if not exists
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo_path, capture_output=True)

    return repo_path


class TestWorktreeManager:
    """Integration tests for WorktreeManager."""

    def test_create_worktree(self, git_repo: Path) -> None:
        """Test creating a worktree."""
        manager = WorktreeManager(repo_root=git_repo)
        worktree_path, result = manager.create_worktree("task-a")

        assert result.returncode == 0
        assert worktree_path.exists()
        assert (worktree_path / "README.md").exists()

        # Clean up
        manager.delete_worktree("task-a", force=True)

    def test_list_worktrees(self, git_repo: Path) -> None:
        """Test listing worktrees."""
        manager = WorktreeManager(repo_root=git_repo)

        # Create a worktree
        manager.create_worktree("task-a")

        worktrees = manager.list_worktrees()

        # Should have at least 2: main and task-a
        assert len(worktrees) >= 2

        task_worktree = next((wt for wt in worktrees if wt.task_id == "task-a"), None)
        assert task_worktree is not None
        assert task_worktree.branch == "task/task-a"

        # Clean up
        manager.delete_worktree("task-a", force=True)

    def test_worktree_exists(self, git_repo: Path) -> None:
        """Test checking worktree existence."""
        manager = WorktreeManager(repo_root=git_repo)

        assert not manager.worktree_exists("task-a")

        manager.create_worktree("task-a")
        assert manager.worktree_exists("task-a")

        manager.delete_worktree("task-a", force=True)
        assert not manager.worktree_exists("task-a")

    def test_get_worktree(self, git_repo: Path) -> None:
        """Test getting worktree info."""
        manager = WorktreeManager(repo_root=git_repo)

        assert manager.get_worktree("task-a") is None

        manager.create_worktree("task-a")
        wt = manager.get_worktree("task-a")

        assert wt is not None
        assert wt.task_id == "task-a"
        assert wt.branch == "task/task-a"

        manager.delete_worktree("task-a", force=True)

    def test_delete_worktree(self, git_repo: Path) -> None:
        """Test deleting a worktree."""
        manager = WorktreeManager(repo_root=git_repo)

        worktree_path, _ = manager.create_worktree("task-a")
        assert worktree_path.exists()

        result = manager.delete_worktree("task-a", force=True)
        assert result.returncode == 0
        assert not worktree_path.exists()

    def test_merge_worktree(self, git_repo: Path) -> None:
        """Test merging a worktree."""
        manager = WorktreeManager(repo_root=git_repo)

        # Create worktree and make changes
        worktree_path, _ = manager.create_worktree("task-a")

        # Create a new file in the worktree
        (worktree_path / "new_file.py").write_text("# New file")
        subprocess.run(["git", "add", "new_file.py"], cwd=worktree_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add new file"],
            cwd=worktree_path,
            capture_output=True,
        )

        # Merge back to main
        result = manager.merge_worktree("task-a", delete_after=True)

        assert result.returncode == 0
        # New file should now be in main
        assert (git_repo / "new_file.py").exists()

    def test_cleanup_all_worktrees(self, git_repo: Path) -> None:
        """Test cleaning up all worktrees."""
        manager = WorktreeManager(repo_root=git_repo)

        # Create multiple worktrees
        manager.create_worktree("task-a")
        manager.create_worktree("task-b")
        manager.create_worktree("task-c")

        removed = manager.cleanup_all_worktrees(force=True)

        assert len(removed) == 3
        assert set(removed) == {"task-a", "task-b", "task-c"}

        # Verify all removed
        assert not manager.worktree_exists("task-a")
        assert not manager.worktree_exists("task-b")
        assert not manager.worktree_exists("task-c")

    def test_get_worktree_path(self, git_repo: Path) -> None:
        """Test getting worktree path."""
        manager = WorktreeManager(repo_root=git_repo)

        path = manager.get_worktree_path("task-a")
        expected = git_repo / ".worktrees" / "task-a"

        assert path == expected


class TestWorktreeIsolation:
    """Tests for worktree isolation behavior."""

    def test_changes_isolated_to_worktree(self, git_repo: Path) -> None:
        """Test that changes in worktree don't affect main."""
        manager = WorktreeManager(repo_root=git_repo)

        worktree_path, _ = manager.create_worktree("task-a")

        # Make changes in worktree
        (worktree_path / "worktree_only.py").write_text("# Worktree only")

        # Main should not have this file
        assert not (git_repo / "worktree_only.py").exists()

        # Clean up
        manager.delete_worktree("task-a", force=True)

    def test_worktrees_independent(self, git_repo: Path) -> None:
        """Test that worktrees are independent of each other."""
        manager = WorktreeManager(repo_root=git_repo)

        wt_a, _ = manager.create_worktree("task-a")
        wt_b, _ = manager.create_worktree("task-b")

        # Create different files in each
        (wt_a / "file_a.py").write_text("# File A")
        (wt_b / "file_b.py").write_text("# File B")

        # Each should only have its own file
        assert (wt_a / "file_a.py").exists()
        assert not (wt_a / "file_b.py").exists()

        assert (wt_b / "file_b.py").exists()
        assert not (wt_b / "file_a.py").exists()

        # Clean up
        manager.cleanup_all_worktrees(force=True)
