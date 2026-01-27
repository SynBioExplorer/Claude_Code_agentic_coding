"""Pydantic models for .task-status.json task status tracking."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskState(str, Enum):
    """Task lifecycle states."""

    PENDING = "pending"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    MERGING = "merging"
    MERGED = "merged"
    FAILED = "failed"
    BLOCKED = "blocked"


class ContractUsage(BaseModel):
    """Record of contract usage by a task."""

    version: str = Field(..., description="Contract version hash used")
    methods_used: list[str] = Field(
        default_factory=list, description="Methods actually called"
    )
    verified_at: str | None = Field(
        default=None, description="ISO timestamp when usage was verified"
    )


class EnvironmentInfo(BaseModel):
    """Environment hash tracking for a task."""

    hash: str = Field(..., description="Environment hash from lockfile")
    verified_at: str = Field(..., description="ISO timestamp when hash was recorded")


class VerificationCheckResult(BaseModel):
    """Result of a single verification check."""

    command: str = Field(..., description="Original command template")
    resolved_command: str = Field(..., description="Command with templates resolved")
    type: str = Field(..., description="Check type (test, lint, typecheck, custom)")
    required: bool = Field(..., description="Whether this check was required")
    passed: bool = Field(..., description="Whether the check passed")
    output: str = Field(default="", description="Stdout from command")
    error: str = Field(default="", description="Stderr from command")
    duration_ms: int = Field(default=0, description="Execution time in milliseconds")


class BoundaryViolation(BaseModel):
    """A single boundary violation detected."""

    type: str = Field(
        ..., description="Violation type (unauthorized_file, forbidden_pattern, etc.)"
    )
    file: str = Field(..., description="File that caused the violation")
    message: str = Field(..., description="Human-readable violation description")
    pattern: str | None = Field(default=None, description="Pattern that was matched")
    lines_changed: int | None = Field(
        default=None, description="Lines changed (for churn violations)"
    )
    threshold: int | None = Field(
        default=None, description="Threshold exceeded (for churn violations)"
    )


class VerificationResult(BaseModel):
    """Complete verification result for a task."""

    task_id: str = Field(..., description="Task that was verified")
    verification_passed: bool = Field(..., description="All required checks passed")
    boundaries_valid: bool = Field(..., description="File boundaries respected")
    contracts_valid: bool = Field(..., description="Contract versions compatible")
    environment_valid: bool = Field(..., description="Environment hash matches")
    checks: list[VerificationCheckResult] = Field(
        default_factory=list, description="Individual check results"
    )
    boundary_violations: list[BoundaryViolation] = Field(
        default_factory=list, description="Boundary violations found"
    )
    verified_at: str = Field(..., description="ISO timestamp of verification")


class TaskStatus(BaseModel):
    """Status tracking for a single task in .task-status.json."""

    task_id: str = Field(..., description="Task identifier")
    status: TaskState = Field(default=TaskState.PENDING, description="Current task state")

    # Environment tracking
    environment: EnvironmentInfo | None = Field(
        default=None, description="Environment hash info"
    )

    # Contract usage tracking
    contracts_used: dict[str, ContractUsage] = Field(
        default_factory=dict, description="Map of contract name to usage info"
    )

    # Worktree info
    worktree_path: str | None = Field(
        default=None, description="Path to task's worktree"
    )
    worktree_branch: str | None = Field(
        default=None, description="Branch name in worktree"
    )

    # Progress tracking
    started_at: str | None = Field(
        default=None, description="ISO timestamp when task started"
    )
    completed_at: str | None = Field(
        default=None, description="ISO timestamp when task completed"
    )

    # Verification results
    verification_result: VerificationResult | None = Field(
        default=None, description="Results from Verifier agent"
    )

    # Error tracking
    error: str | None = Field(default=None, description="Error message if failed")
    retry_count: int = Field(default=0, description="Number of retry attempts")

    # Merge info
    merge_commit: str | None = Field(
        default=None, description="Commit hash after merge"
    )

    def is_complete(self) -> bool:
        """Check if task has completed (successfully or not)."""
        return self.status in (TaskState.MERGED, TaskState.FAILED)

    def is_ready_to_verify(self) -> bool:
        """Check if task is ready for verification."""
        return self.status == TaskState.EXECUTING and self.completed_at is not None

    def is_verified(self) -> bool:
        """Check if task has passed verification."""
        return (
            self.status in (TaskState.VERIFIED, TaskState.MERGING, TaskState.MERGED)
            and self.verification_result is not None
            and self.verification_result.verification_passed
        )


class OrchestrationState(BaseModel):
    """Global orchestration state for tracking all tasks."""

    request_id: str = Field(..., description="Unique identifier for this orchestration run")
    original_request: str = Field(..., description="Original user request")

    # Environment info
    environment: EnvironmentInfo | None = Field(
        default=None, description="Global environment hash"
    )

    # Task tracking
    tasks: dict[str, TaskStatus] = Field(
        default_factory=dict, description="Map of task_id to status"
    )

    # Phase tracking
    current_phase: str = Field(
        default="planning", description="Current orchestration phase"
    )
    iteration: int = Field(default=1, description="Current iteration (max 3)")

    # Contract renegotiation tracking
    contract_renegotiations: dict[str, int] = Field(
        default_factory=dict, description="Map of contract name to renegotiation count"
    )

    # Timestamps
    started_at: str = Field(..., description="ISO timestamp when orchestration started")
    completed_at: str | None = Field(
        default=None, description="ISO timestamp when orchestration completed"
    )

    # Outcome
    success: bool | None = Field(
        default=None, description="Final outcome (None if in progress)"
    )
    summary: str | None = Field(default=None, description="Summary of outcome")

    def get_pending_tasks(self) -> list[str]:
        """Get task IDs that are pending."""
        return [
            tid for tid, status in self.tasks.items()
            if status.status == TaskState.PENDING
        ]

    def get_ready_tasks(self, completed_tasks: set[str]) -> list[str]:
        """Get task IDs ready to execute (dependencies satisfied)."""
        # This would need the task DAG to properly check dependencies
        # For now, return pending tasks
        return self.get_pending_tasks()

    def all_tasks_complete(self) -> bool:
        """Check if all tasks have completed."""
        return all(status.is_complete() for status in self.tasks.values())

    def any_task_failed(self) -> bool:
        """Check if any task has failed."""
        return any(
            status.status == TaskState.FAILED for status in self.tasks.values()
        )
