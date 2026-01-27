"""Tests for DAG scheduling."""

import pytest

from claude_orchestrator.core.dag import (
    DAGValidationError,
    compute_critical_path,
    detect_cycles,
    parse_task_dag,
    tasks_ordered_by_dependency,
    topological_sort,
    validate_dag,
)
from claude_orchestrator.schemas.tasks import TaskSpec, VerificationCheck, VerificationType


def make_task(
    task_id: str,
    depends_on: list[str] | None = None,
    files_write: list[str] | None = None,
) -> TaskSpec:
    """Helper to create a TaskSpec for testing."""
    return TaskSpec(
        id=task_id,
        description=f"Test task {task_id}",
        files_write=files_write or [f"src/{task_id}.py"],
        depends_on=depends_on or [],
        verification=[
            VerificationCheck(
                command=f"pytest tests/test_{task_id}.py",
                type=VerificationType.TEST,
                required=True,
            )
        ],
    )


class TestParseTaskDAG:
    """Tests for parse_task_dag."""

    def test_empty_tasks(self) -> None:
        """Test parsing empty task list."""
        nodes = parse_task_dag([])
        assert nodes == {}

    def test_single_task(self) -> None:
        """Test parsing single task."""
        tasks = [make_task("a")]
        nodes = parse_task_dag(tasks)

        assert len(nodes) == 1
        assert "a" in nodes
        assert nodes["a"].depends_on == set()
        assert nodes["a"].dependents == set()

    def test_linear_dependency(self) -> None:
        """Test parsing linear dependency chain."""
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
            make_task("c", depends_on=["b"]),
        ]
        nodes = parse_task_dag(tasks)

        assert nodes["a"].dependents == {"b"}
        assert nodes["b"].depends_on == {"a"}
        assert nodes["b"].dependents == {"c"}
        assert nodes["c"].depends_on == {"b"}

    def test_diamond_dependency(self) -> None:
        """Test parsing diamond dependency pattern."""
        #     a
        #    / \
        #   b   c
        #    \ /
        #     d
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
            make_task("c", depends_on=["a"]),
            make_task("d", depends_on=["b", "c"]),
        ]
        nodes = parse_task_dag(tasks)

        assert nodes["a"].dependents == {"b", "c"}
        assert nodes["d"].depends_on == {"b", "c"}


class TestDetectCycles:
    """Tests for detect_cycles."""

    def test_no_cycles(self) -> None:
        """Test detecting no cycles in valid DAG."""
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
            make_task("c", depends_on=["b"]),
        ]
        nodes = parse_task_dag(tasks)
        cycles = detect_cycles(nodes)

        assert cycles == []

    def test_self_loop(self) -> None:
        """Test detecting self-loop cycle."""
        tasks = [make_task("a", depends_on=["a"])]
        nodes = parse_task_dag(tasks)
        cycles = detect_cycles(nodes)

        assert len(cycles) == 1
        assert "a" in cycles[0]

    def test_two_node_cycle(self) -> None:
        """Test detecting two-node cycle."""
        tasks = [
            make_task("a", depends_on=["b"]),
            make_task("b", depends_on=["a"]),
        ]
        nodes = parse_task_dag(tasks)
        cycles = detect_cycles(nodes)

        assert len(cycles) >= 1


class TestValidateDAG:
    """Tests for validate_dag."""

    def test_valid_dag(self) -> None:
        """Test validating a valid DAG."""
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
        ]
        # Should not raise
        validate_dag(tasks)

    def test_missing_dependency(self) -> None:
        """Test detecting missing dependency."""
        tasks = [make_task("a", depends_on=["nonexistent"])]

        with pytest.raises(DAGValidationError) as exc_info:
            validate_dag(tasks)

        assert "non-existent dependencies" in str(exc_info.value.message)

    def test_cycle_detected(self) -> None:
        """Test detecting cycles."""
        tasks = [
            make_task("a", depends_on=["b"]),
            make_task("b", depends_on=["a"]),
        ]

        with pytest.raises(DAGValidationError) as exc_info:
            validate_dag(tasks)

        assert "Circular dependencies" in str(exc_info.value.message)


class TestTopologicalSort:
    """Tests for topological_sort."""

    def test_empty_tasks(self) -> None:
        """Test sorting empty task list."""
        waves = topological_sort([])
        assert waves == []

    def test_single_task(self) -> None:
        """Test sorting single task."""
        tasks = [make_task("a")]
        waves = topological_sort(tasks)

        assert waves == [["a"]]

    def test_independent_tasks(self) -> None:
        """Test sorting independent tasks into single wave."""
        tasks = [
            make_task("a"),
            make_task("b"),
            make_task("c"),
        ]
        waves = topological_sort(tasks)

        assert len(waves) == 1
        assert set(waves[0]) == {"a", "b", "c"}

    def test_linear_chain(self) -> None:
        """Test sorting linear dependency chain."""
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
            make_task("c", depends_on=["b"]),
        ]
        waves = topological_sort(tasks)

        assert len(waves) == 3
        assert waves[0] == ["a"]
        assert waves[1] == ["b"]
        assert waves[2] == ["c"]

    def test_diamond_pattern(self) -> None:
        """Test sorting diamond dependency pattern."""
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
            make_task("c", depends_on=["a"]),
            make_task("d", depends_on=["b", "c"]),
        ]
        waves = topological_sort(tasks)

        assert len(waves) == 3
        assert waves[0] == ["a"]
        assert set(waves[1]) == {"b", "c"}  # b and c can run in parallel
        assert waves[2] == ["d"]


class TestTasksOrderedByDependency:
    """Tests for tasks_ordered_by_dependency."""

    def test_single_task(self) -> None:
        """Test single task is always ordered."""
        tasks = [make_task("a")]
        assert tasks_ordered_by_dependency(["a"], tasks)

    def test_ordered_chain(self) -> None:
        """Test properly ordered chain."""
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
        ]
        assert tasks_ordered_by_dependency(["a", "b"], tasks)

    def test_unordered_tasks(self) -> None:
        """Test unordered tasks."""
        tasks = [
            make_task("a"),
            make_task("b"),  # No dependency on a
        ]
        assert not tasks_ordered_by_dependency(["a", "b"], tasks)


class TestCriticalPath:
    """Tests for compute_critical_path."""

    def test_single_task(self) -> None:
        """Test critical path for single task."""
        tasks = [make_task("a")]
        path = compute_critical_path(tasks)

        assert path == ["a"]

    def test_linear_chain(self) -> None:
        """Test critical path is the full chain."""
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
            make_task("c", depends_on=["b"]),
        ]
        path = compute_critical_path(tasks)

        assert path == ["a", "b", "c"]

    def test_parallel_branches(self) -> None:
        """Test critical path selects longest branch."""
        tasks = [
            make_task("a"),
            make_task("b", depends_on=["a"]),
            make_task("c", depends_on=["a"]),
            make_task("d", depends_on=["b"]),
        ]
        path = compute_critical_path(tasks)

        # Critical path should be a -> b -> d (length 3)
        assert path == ["a", "b", "d"]
