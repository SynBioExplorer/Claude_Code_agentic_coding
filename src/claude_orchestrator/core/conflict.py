"""File and resource conflict detection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from claude_orchestrator.core.dag import tasks_ordered_by_dependency

if TYPE_CHECKING:
    from claude_orchestrator.schemas.tasks import TaskSpec


class ConflictType(str, Enum):
    """Type of conflict detected."""

    FILE = "file"
    RESOURCE = "resource"


@dataclass
class Conflict:
    """A detected conflict between tasks."""

    type: ConflictType
    target: str  # File path or resource identifier
    tasks: list[str]  # Task IDs involved in the conflict
    message: str | None = None

    def __str__(self) -> str:
        task_list = ", ".join(self.tasks)
        return f"{self.type.value} conflict on '{self.target}' between tasks: [{task_list}]"


def get_implied_resources(intent: dict) -> list[str]:
    """Extract implied resources from a patch intent.

    Args:
        intent: A patch intent dictionary with 'action' and 'intent' keys

    Returns:
        List of implied resource identifiers
    """
    action = intent.get("action", "")
    data = intent.get("intent", {})

    if action == "add_router":
        prefix = data.get("prefix", "/")
        return [f"route:{prefix}"]

    elif action == "add_dependency":
        func_name = data.get("function_name", "")
        if func_name:
            return [f"di:{func_name}"]

    elif action == "add_config":
        key = data.get("key", "")
        if key:
            return [f"config:{key}"]

    elif action == "add_middleware":
        name = data.get("middleware_class", "")
        if name:
            return [f"middleware:{name}"]

    return []


def detect_file_conflicts(tasks: list[TaskSpec]) -> list[Conflict]:
    """Detect conflicts where multiple tasks write to the same file.

    Args:
        tasks: List of task specifications

    Returns:
        List of file conflicts (tasks writing same file without dependency ordering)
    """
    conflicts: list[Conflict] = []

    # Collect all file writes
    file_writes: dict[str, list[str]] = defaultdict(list)  # file -> [task_ids]

    for task in tasks:
        for f in task.files_write:
            file_writes[f].append(task.id)

    # Check for conflicts
    for file_path, writers in file_writes.items():
        if len(writers) > 1:
            # Multiple tasks write to this file
            # Check if they're properly ordered by dependency
            if not tasks_ordered_by_dependency(writers, tasks):
                conflicts.append(
                    Conflict(
                        type=ConflictType.FILE,
                        target=file_path,
                        tasks=writers,
                        message=f"Multiple tasks write to '{file_path}' without dependency ordering",
                    )
                )

    return conflicts


def detect_resource_conflicts(tasks: list[TaskSpec]) -> list[Conflict]:
    """Detect conflicts on logical resources (routes, DI bindings, config keys).

    Resources can conflict even when files don't overlap.

    Args:
        tasks: List of task specifications

    Returns:
        List of resource conflicts
    """
    conflicts: list[Conflict] = []

    # Collect all resource writes
    resource_writes: dict[str, list[str]] = defaultdict(list)  # resource -> [task_ids]

    for task in tasks:
        # Explicit resources
        for r in task.resources_write:
            resource_writes[r].append(task.id)

        # Implied resources from intents
        for intent in task.patch_intents:
            implied = get_implied_resources(intent.model_dump())
            for r in implied:
                resource_writes[r].append(task.id)

    # Check for conflicts
    for resource, writers in resource_writes.items():
        if len(writers) > 1:
            # Multiple tasks claim this resource
            if not tasks_ordered_by_dependency(writers, tasks):
                conflicts.append(
                    Conflict(
                        type=ConflictType.RESOURCE,
                        target=resource,
                        tasks=writers,
                        message=f"Multiple tasks claim resource '{resource}' without dependency ordering",
                    )
                )

    return conflicts


def detect_all_conflicts(tasks: list[TaskSpec]) -> list[Conflict]:
    """Detect both file and resource conflicts.

    Args:
        tasks: List of task specifications

    Returns:
        Combined list of all conflicts
    """
    file_conflicts = detect_file_conflicts(tasks)
    resource_conflicts = detect_resource_conflicts(tasks)
    return file_conflicts + resource_conflicts


def suggest_dependency_fix(conflict: Conflict, tasks: list[TaskSpec]) -> list[tuple[str, str]]:
    """Suggest dependency additions to fix a conflict.

    Args:
        conflict: The conflict to fix
        tasks: All task specifications

    Returns:
        List of (dependent_task_id, dependency_task_id) tuples to add
    """
    # Simple strategy: chain tasks in order they appear
    task_ids = conflict.tasks
    suggestions: list[tuple[str, str]] = []

    for i in range(1, len(task_ids)):
        # Make each task depend on the previous one
        suggestions.append((task_ids[i], task_ids[i - 1]))

    return suggestions


def get_conflict_summary(conflicts: list[Conflict]) -> str:
    """Generate a human-readable summary of conflicts.

    Args:
        conflicts: List of conflicts

    Returns:
        Formatted summary string
    """
    if not conflicts:
        return "No conflicts detected."

    lines = [f"Found {len(conflicts)} conflict(s):"]
    lines.append("")

    file_conflicts = [c for c in conflicts if c.type == ConflictType.FILE]
    resource_conflicts = [c for c in conflicts if c.type == ConflictType.RESOURCE]

    if file_conflicts:
        lines.append(f"File Conflicts ({len(file_conflicts)}):")
        for c in file_conflicts:
            lines.append(f"  - {c.target}: tasks {c.tasks}")

    if resource_conflicts:
        lines.append(f"\nResource Conflicts ({len(resource_conflicts)}):")
        for c in resource_conflicts:
            lines.append(f"  - {c.target}: tasks {c.tasks}")

    return "\n".join(lines)
