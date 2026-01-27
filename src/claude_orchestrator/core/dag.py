"""DAG-based task scheduling with topological sorting."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_orchestrator.schemas.tasks import ExecutionPlan, TaskSpec


@dataclass
class TaskNode:
    """A node in the task DAG."""

    task_id: str
    depends_on: set[str] = field(default_factory=set)
    dependents: set[str] = field(default_factory=set)  # Tasks that depend on this one


@dataclass
class DAGValidationError(Exception):
    """Error raised when DAG validation fails."""

    message: str
    details: dict[str, list[str]] | None = None


def parse_task_dag(tasks: list[TaskSpec]) -> dict[str, TaskNode]:
    """Parse tasks into a DAG representation.

    Args:
        tasks: List of task specifications

    Returns:
        Dictionary mapping task_id to TaskNode
    """
    nodes: dict[str, TaskNode] = {}

    # First pass: create nodes
    for task in tasks:
        nodes[task.id] = TaskNode(
            task_id=task.id,
            depends_on=set(task.depends_on),
        )

    # Second pass: populate dependents
    for task_id, node in nodes.items():
        for dep_id in node.depends_on:
            if dep_id in nodes:
                nodes[dep_id].dependents.add(task_id)

    return nodes


def detect_cycles(nodes: dict[str, TaskNode]) -> list[list[str]]:
    """Detect cycles in the task DAG.

    Uses DFS-based cycle detection.

    Args:
        nodes: Dictionary of task nodes

    Returns:
        List of cycles found (each cycle is a list of task IDs)
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {node_id: WHITE for node_id in nodes}
    parent: dict[str, str | None] = {node_id: None for node_id in nodes}
    cycles: list[list[str]] = []

    def dfs(node_id: str) -> None:
        color[node_id] = GRAY

        for dep_id in nodes[node_id].depends_on:
            if dep_id not in nodes:
                continue  # Skip missing dependencies (handled elsewhere)

            if color[dep_id] == GRAY:
                # Found a cycle - reconstruct it
                cycle = [dep_id]
                current = node_id
                while current != dep_id:
                    cycle.append(current)
                    current = parent.get(current)
                    if current is None:
                        break
                cycle.append(dep_id)
                cycle.reverse()
                cycles.append(cycle)

            elif color[dep_id] == WHITE:
                parent[dep_id] = node_id
                dfs(dep_id)

        color[node_id] = BLACK

    for node_id in nodes:
        if color[node_id] == WHITE:
            dfs(node_id)

    return cycles


def validate_dag(tasks: list[TaskSpec]) -> None:
    """Validate the task DAG.

    Checks for:
    - Missing dependencies (task references non-existent task)
    - Circular dependencies (cycles in the DAG)

    Args:
        tasks: List of task specifications

    Raises:
        DAGValidationError: If validation fails
    """
    task_ids = {task.id for task in tasks}
    nodes = parse_task_dag(tasks)

    # Check for missing dependencies
    missing_deps: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        for dep_id in task.depends_on:
            if dep_id not in task_ids:
                missing_deps[task.id].append(dep_id)

    if missing_deps:
        raise DAGValidationError(
            message="Tasks reference non-existent dependencies",
            details=dict(missing_deps),
        )

    # Check for cycles
    cycles = detect_cycles(nodes)
    if cycles:
        raise DAGValidationError(
            message="Circular dependencies detected",
            details={"cycles": [" -> ".join(c) for c in cycles]},
        )


def topological_sort(tasks: list[TaskSpec]) -> list[list[str]]:
    """Perform topological sort to get parallel execution waves.

    Returns tasks grouped by execution wave. Tasks in the same wave
    can be executed in parallel (no dependencies between them).

    Args:
        tasks: List of task specifications

    Returns:
        List of waves, where each wave is a list of task IDs that
        can be executed in parallel
    """
    # Validate first
    validate_dag(tasks)

    nodes = parse_task_dag(tasks)
    task_ids = {task.id for task in tasks}

    # Calculate in-degree for each node
    in_degree: dict[str, int] = {task_id: 0 for task_id in task_ids}
    for task in tasks:
        for dep_id in task.depends_on:
            if dep_id in task_ids:
                in_degree[task.id] += 1

    waves: list[list[str]] = []

    # Keep processing until all tasks are assigned to waves
    remaining = set(task_ids)

    while remaining:
        # Find all tasks with no remaining dependencies
        wave = [
            task_id
            for task_id in remaining
            if in_degree[task_id] == 0
        ]

        if not wave:
            # This shouldn't happen if validate_dag passed
            raise DAGValidationError(
                message="Unable to compute execution order - possible cycle",
                details={"remaining": list(remaining)},
            )

        waves.append(sorted(wave))  # Sort for deterministic ordering

        # Remove these tasks and update in-degrees
        for task_id in wave:
            remaining.remove(task_id)
            for dependent_id in nodes[task_id].dependents:
                if dependent_id in remaining:
                    in_degree[dependent_id] -= 1

    return waves


def get_task_dependencies(task_id: str, nodes: dict[str, TaskNode]) -> set[str]:
    """Get all transitive dependencies of a task.

    Args:
        task_id: The task to get dependencies for
        nodes: The DAG nodes

    Returns:
        Set of all task IDs that this task depends on (transitively)
    """
    visited: set[str] = set()
    stack = list(nodes[task_id].depends_on)

    while stack:
        current = stack.pop()
        if current in visited or current not in nodes:
            continue
        visited.add(current)
        stack.extend(nodes[current].depends_on)

    return visited


def get_task_dependents(task_id: str, nodes: dict[str, TaskNode]) -> set[str]:
    """Get all tasks that transitively depend on this task.

    Args:
        task_id: The task to get dependents for
        nodes: The DAG nodes

    Returns:
        Set of all task IDs that depend on this task (transitively)
    """
    visited: set[str] = set()
    stack = list(nodes[task_id].dependents)

    while stack:
        current = stack.pop()
        if current in visited or current not in nodes:
            continue
        visited.add(current)
        stack.extend(nodes[current].dependents)

    return visited


def compute_critical_path(tasks: list[TaskSpec]) -> list[str]:
    """Compute the critical path through the task DAG.

    The critical path is the longest chain of dependent tasks,
    which determines the minimum execution time.

    Args:
        tasks: List of task specifications

    Returns:
        List of task IDs on the critical path
    """
    nodes = parse_task_dag(tasks)
    task_ids = {task.id for task in tasks}

    # Compute longest path to each node
    longest_path: dict[str, int] = {}
    predecessor: dict[str, str | None] = {}

    # Process in topological order
    waves = topological_sort(tasks)

    for wave in waves:
        for task_id in wave:
            # Find the longest path to this node
            max_length = 0
            max_pred = None

            for dep_id in nodes[task_id].depends_on:
                if dep_id in longest_path:
                    if longest_path[dep_id] + 1 > max_length:
                        max_length = longest_path[dep_id] + 1
                        max_pred = dep_id

            longest_path[task_id] = max_length
            predecessor[task_id] = max_pred

    # Find the endpoint of the critical path
    if not longest_path:
        return []

    end_task = max(longest_path.keys(), key=lambda x: longest_path[x])

    # Reconstruct the path
    path: list[str] = []
    current: str | None = end_task
    while current is not None:
        path.append(current)
        current = predecessor[current]

    path.reverse()
    return path


def tasks_ordered_by_dependency(task_ids: list[str], tasks: list[TaskSpec]) -> bool:
    """Check if tasks with the same resource/file are ordered by dependency.

    Args:
        task_ids: List of task IDs that share a resource
        tasks: All task specifications

    Returns:
        True if the tasks form a chain (each depends on previous), False otherwise
    """
    if len(task_ids) <= 1:
        return True

    # Build a map of task_id -> task
    task_map = {t.id: t for t in tasks}

    # Check if tasks form a dependency chain
    # For N tasks, we need N-1 dependency edges between them
    deps_between: set[tuple[str, str]] = set()

    for tid in task_ids:
        task = task_map.get(tid)
        if task:
            for dep in task.depends_on:
                if dep in task_ids:
                    deps_between.add((tid, dep))

    # If we have a proper chain, we should have len(task_ids) - 1 edges
    # Also verify no parallel paths (each node has at most one incoming/outgoing)
    in_count: dict[str, int] = defaultdict(int)
    out_count: dict[str, int] = defaultdict(int)

    for dependent, dependency in deps_between:
        in_count[dependent] += 1
        out_count[dependency] += 1

    # For a valid chain:
    # - Exactly one node has in_count 0 (start)
    # - Exactly one node has out_count 0 (end)
    # - All others have in_count 1 and out_count 1
    starts = [t for t in task_ids if in_count[t] == 0]
    ends = [t for t in task_ids if out_count[t] == 0]

    return len(starts) == 1 and len(ends) == 1 and len(deps_between) == len(task_ids) - 1
