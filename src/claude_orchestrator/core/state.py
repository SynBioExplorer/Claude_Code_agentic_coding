"""Task lifecycle state machine and orchestration state management."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from claude_orchestrator.schemas.status import (
    EnvironmentInfo,
    OrchestrationState,
    TaskState,
    TaskStatus,
)


class StateTransitionError(Exception):
    """Error raised when an invalid state transition is attempted."""

    pass


# Valid state transitions
VALID_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {TaskState.EXECUTING, TaskState.BLOCKED},
    TaskState.BLOCKED: {TaskState.PENDING, TaskState.EXECUTING},
    TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.FAILED},
    TaskState.VERIFYING: {TaskState.VERIFIED, TaskState.FAILED, TaskState.EXECUTING},
    TaskState.VERIFIED: {TaskState.MERGING},
    TaskState.MERGING: {TaskState.MERGED, TaskState.FAILED},
    TaskState.MERGED: set(),  # Terminal state
    TaskState.FAILED: {TaskState.PENDING, TaskState.EXECUTING},  # Can retry
}


class TaskStateMachine:
    """State machine for task lifecycle management."""

    def __init__(self, task_id: str, initial_state: TaskState = TaskState.PENDING):
        """Initialize state machine for a task.

        Args:
            task_id: Task identifier
            initial_state: Starting state
        """
        self.task_id = task_id
        self._state = initial_state
        self._history: list[tuple[TaskState, str]] = [
            (initial_state, datetime.now().isoformat())
        ]

    @property
    def state(self) -> TaskState:
        """Get current state."""
        return self._state

    @property
    def history(self) -> list[tuple[TaskState, str]]:
        """Get state transition history."""
        return self._history.copy()

    def can_transition_to(self, new_state: TaskState) -> bool:
        """Check if transition to new state is valid.

        Args:
            new_state: Target state

        Returns:
            True if transition is valid
        """
        return new_state in VALID_TRANSITIONS.get(self._state, set())

    def transition_to(self, new_state: TaskState) -> None:
        """Transition to a new state.

        Args:
            new_state: Target state

        Raises:
            StateTransitionError: If transition is invalid
        """
        if not self.can_transition_to(new_state):
            raise StateTransitionError(
                f"Invalid transition: {self._state.value} -> {new_state.value} "
                f"for task {self.task_id}"
            )

        self._state = new_state
        self._history.append((new_state, datetime.now().isoformat()))

    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self._state in (TaskState.MERGED, TaskState.FAILED)

    def is_active(self) -> bool:
        """Check if task is actively being worked on."""
        return self._state in (TaskState.EXECUTING, TaskState.VERIFYING, TaskState.MERGING)


@dataclass
class OrchestrationStatePersistence:
    """Handles persistence of orchestration state."""

    state_file: Path = field(default_factory=lambda: Path(".orchestration-state.json"))

    def save(self, state: OrchestrationState) -> None:
        """Save orchestration state to file.

        Args:
            state: State to save
        """
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        data = state.model_dump(mode="json")
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    def load(self) -> OrchestrationState | None:
        """Load orchestration state from file.

        Returns:
            OrchestrationState if file exists, None otherwise
        """
        if not self.state_file.exists():
            return None

        try:
            with open(self.state_file) as f:
                data = json.load(f)
            return OrchestrationState.model_validate(data)
        except Exception:
            return None

    def exists(self) -> bool:
        """Check if state file exists."""
        return self.state_file.exists()

    def delete(self) -> None:
        """Delete state file."""
        if self.state_file.exists():
            self.state_file.unlink()


def create_initial_state(
    request_id: str,
    original_request: str,
    task_ids: list[str],
) -> OrchestrationState:
    """Create initial orchestration state.

    Args:
        request_id: Unique identifier for this run
        original_request: Original user request
        task_ids: List of task IDs to track

    Returns:
        Initialized OrchestrationState
    """
    tasks = {
        task_id: TaskStatus(task_id=task_id, status=TaskState.PENDING)
        for task_id in task_ids
    }

    return OrchestrationState(
        request_id=request_id,
        original_request=original_request,
        tasks=tasks,
        current_phase="initializing",
        started_at=datetime.now().isoformat(),
    )


def update_task_status(
    state: OrchestrationState,
    task_id: str,
    new_status: TaskState,
    **kwargs: Any,
) -> OrchestrationState:
    """Update a task's status in the orchestration state.

    Args:
        state: Current orchestration state
        task_id: Task to update
        new_status: New status
        **kwargs: Additional fields to update (error, merge_commit, etc.)

    Returns:
        Updated orchestration state
    """
    if task_id not in state.tasks:
        state.tasks[task_id] = TaskStatus(task_id=task_id)

    task = state.tasks[task_id]
    task.status = new_status

    # Update timestamps
    if new_status == TaskState.EXECUTING and not task.started_at:
        task.started_at = datetime.now().isoformat()
    elif new_status in (TaskState.MERGED, TaskState.FAILED):
        task.completed_at = datetime.now().isoformat()

    # Update additional fields
    for key, value in kwargs.items():
        if hasattr(task, key):
            setattr(task, key, value)

    return state


def set_environment(
    state: OrchestrationState,
    env_hash: str,
) -> OrchestrationState:
    """Set the global environment hash.

    Args:
        state: Current orchestration state
        env_hash: Environment hash from lockfile

    Returns:
        Updated orchestration state
    """
    state.environment = EnvironmentInfo(
        hash=env_hash,
        verified_at=datetime.now().isoformat(),
    )
    return state


def get_ready_tasks(
    state: OrchestrationState,
    task_deps: dict[str, list[str]],
) -> list[str]:
    """Get task IDs that are ready to execute.

    A task is ready when:
    - Its status is PENDING
    - All its dependencies are MERGED

    Args:
        state: Current orchestration state
        task_deps: Map of task_id -> list of dependency task_ids

    Returns:
        List of ready task IDs
    """
    ready: list[str] = []

    for task_id, status in state.tasks.items():
        if status.status != TaskState.PENDING:
            continue

        deps = task_deps.get(task_id, [])
        all_deps_merged = all(
            state.tasks.get(dep_id, TaskStatus(task_id=dep_id)).status == TaskState.MERGED
            for dep_id in deps
        )

        if all_deps_merged:
            ready.append(task_id)

    return ready


def get_blocked_tasks(
    state: OrchestrationState,
    task_deps: dict[str, list[str]],
) -> list[str]:
    """Get task IDs that are blocked by failed dependencies.

    Args:
        state: Current orchestration state
        task_deps: Map of task_id -> list of dependency task_ids

    Returns:
        List of blocked task IDs
    """
    blocked: list[str] = []

    for task_id, status in state.tasks.items():
        if status.status == TaskState.BLOCKED:
            blocked.append(task_id)
            continue

        if status.status != TaskState.PENDING:
            continue

        deps = task_deps.get(task_id, [])
        any_dep_failed = any(
            state.tasks.get(dep_id, TaskStatus(task_id=dep_id)).status == TaskState.FAILED
            for dep_id in deps
        )

        if any_dep_failed:
            blocked.append(task_id)

    return blocked


def complete_orchestration(
    state: OrchestrationState,
    success: bool,
    summary: str,
) -> OrchestrationState:
    """Mark orchestration as complete.

    Args:
        state: Current orchestration state
        success: Whether orchestration succeeded
        summary: Summary message

    Returns:
        Updated orchestration state
    """
    state.success = success
    state.summary = summary
    state.completed_at = datetime.now().isoformat()
    state.current_phase = "completed"
    return state
