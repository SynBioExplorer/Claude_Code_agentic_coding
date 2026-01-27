"""Tests for conflict detection."""

import pytest

from claude_orchestrator.core.conflict import (
    Conflict,
    ConflictType,
    detect_all_conflicts,
    detect_file_conflicts,
    detect_resource_conflicts,
    get_conflict_summary,
    get_implied_resources,
    suggest_dependency_fix,
)
from claude_orchestrator.schemas.tasks import (
    PatchIntent,
    TaskSpec,
    VerificationCheck,
    VerificationType,
)


def make_task(
    task_id: str,
    files_write: list[str] | None = None,
    resources_write: list[str] | None = None,
    depends_on: list[str] | None = None,
    patch_intents: list[dict] | None = None,
) -> TaskSpec:
    """Helper to create a TaskSpec for testing."""
    intents = []
    if patch_intents:
        for pi in patch_intents:
            intents.append(
                PatchIntent(
                    file=pi.get("file", "main.py"),
                    action=pi.get("action", "add_router"),
                    intent=pi.get("intent", {}),
                )
            )

    return TaskSpec(
        id=task_id,
        description=f"Test task {task_id}",
        files_write=files_write or [],
        resources_write=resources_write or [],
        depends_on=depends_on or [],
        patch_intents=intents,
        verification=[
            VerificationCheck(
                command=f"pytest tests/test_{task_id}.py",
                type=VerificationType.TEST,
                required=True,
            )
        ],
    )


class TestGetImpliedResources:
    """Tests for get_implied_resources."""

    def test_add_router_intent(self) -> None:
        """Test extracting route resource from add_router intent."""
        intent = {
            "action": "add_router",
            "intent": {"prefix": "/auth"},
        }
        resources = get_implied_resources(intent)

        assert resources == ["route:/auth"]

    def test_add_dependency_intent(self) -> None:
        """Test extracting DI resource from add_dependency intent."""
        intent = {
            "action": "add_dependency",
            "intent": {"function_name": "get_auth_service"},
        }
        resources = get_implied_resources(intent)

        assert resources == ["di:get_auth_service"]

    def test_add_config_intent(self) -> None:
        """Test extracting config resource from add_config intent."""
        intent = {
            "action": "add_config",
            "intent": {"key": "AUTH_SECRET"},
        }
        resources = get_implied_resources(intent)

        assert resources == ["config:AUTH_SECRET"]

    def test_add_middleware_intent(self) -> None:
        """Test extracting middleware resource from add_middleware intent."""
        intent = {
            "action": "add_middleware",
            "intent": {"middleware_class": "CORSMiddleware"},
        }
        resources = get_implied_resources(intent)

        assert resources == ["middleware:CORSMiddleware"]

    def test_unknown_action(self) -> None:
        """Test unknown action returns empty list."""
        intent = {"action": "unknown_action", "intent": {}}
        resources = get_implied_resources(intent)

        assert resources == []


class TestDetectFileConflicts:
    """Tests for detect_file_conflicts."""

    def test_no_conflicts(self) -> None:
        """Test no conflicts when files are disjoint."""
        tasks = [
            make_task("a", files_write=["src/a.py"]),
            make_task("b", files_write=["src/b.py"]),
        ]
        conflicts = detect_file_conflicts(tasks)

        assert conflicts == []

    def test_file_conflict_detected(self) -> None:
        """Test detecting file write conflict."""
        tasks = [
            make_task("a", files_write=["src/shared.py"]),
            make_task("b", files_write=["src/shared.py"]),
        ]
        conflicts = detect_file_conflicts(tasks)

        assert len(conflicts) == 1
        assert conflicts[0].type == ConflictType.FILE
        assert conflicts[0].target == "src/shared.py"
        assert set(conflicts[0].tasks) == {"a", "b"}

    def test_no_conflict_with_dependency(self) -> None:
        """Test no conflict when tasks are ordered by dependency."""
        tasks = [
            make_task("a", files_write=["src/shared.py"]),
            make_task("b", files_write=["src/shared.py"], depends_on=["a"]),
        ]
        conflicts = detect_file_conflicts(tasks)

        assert conflicts == []


class TestDetectResourceConflicts:
    """Tests for detect_resource_conflicts."""

    def test_no_conflicts(self) -> None:
        """Test no conflicts when resources are disjoint."""
        tasks = [
            make_task("a", resources_write=["route:/auth"]),
            make_task("b", resources_write=["route:/users"]),
        ]
        conflicts = detect_resource_conflicts(tasks)

        assert conflicts == []

    def test_explicit_resource_conflict(self) -> None:
        """Test detecting explicit resource conflict."""
        tasks = [
            make_task("a", resources_write=["route:/api"]),
            make_task("b", resources_write=["route:/api"]),
        ]
        conflicts = detect_resource_conflicts(tasks)

        assert len(conflicts) == 1
        assert conflicts[0].type == ConflictType.RESOURCE
        assert conflicts[0].target == "route:/api"

    def test_implied_resource_conflict(self) -> None:
        """Test detecting conflict from implied resources."""
        tasks = [
            make_task(
                "a",
                patch_intents=[{"action": "add_router", "intent": {"prefix": "/auth"}}],
            ),
            make_task(
                "b",
                patch_intents=[{"action": "add_router", "intent": {"prefix": "/auth"}}],
            ),
        ]
        conflicts = detect_resource_conflicts(tasks)

        assert len(conflicts) == 1
        assert conflicts[0].target == "route:/auth"

    def test_explicit_and_implied_conflict(self) -> None:
        """Test conflict between explicit and implied resources."""
        tasks = [
            make_task("a", resources_write=["route:/auth"]),
            make_task(
                "b",
                patch_intents=[{"action": "add_router", "intent": {"prefix": "/auth"}}],
            ),
        ]
        conflicts = detect_resource_conflicts(tasks)

        assert len(conflicts) == 1


class TestDetectAllConflicts:
    """Tests for detect_all_conflicts."""

    def test_no_conflicts(self) -> None:
        """Test no conflicts in clean setup."""
        tasks = [
            make_task("a", files_write=["src/a.py"], resources_write=["route:/a"]),
            make_task("b", files_write=["src/b.py"], resources_write=["route:/b"]),
        ]
        conflicts = detect_all_conflicts(tasks)

        assert conflicts == []

    def test_both_conflict_types(self) -> None:
        """Test detecting both file and resource conflicts."""
        tasks = [
            make_task(
                "a",
                files_write=["src/shared.py"],
                resources_write=["route:/api"],
            ),
            make_task(
                "b",
                files_write=["src/shared.py"],
                resources_write=["route:/api"],
            ),
        ]
        conflicts = detect_all_conflicts(tasks)

        assert len(conflicts) == 2
        types = {c.type for c in conflicts}
        assert types == {ConflictType.FILE, ConflictType.RESOURCE}


class TestSuggestDependencyFix:
    """Tests for suggest_dependency_fix."""

    def test_two_task_conflict(self) -> None:
        """Test suggestion for two-task conflict."""
        conflict = Conflict(
            type=ConflictType.FILE,
            target="src/shared.py",
            tasks=["a", "b"],
        )
        tasks = [
            make_task("a", files_write=["src/shared.py"]),
            make_task("b", files_write=["src/shared.py"]),
        ]
        suggestions = suggest_dependency_fix(conflict, tasks)

        assert suggestions == [("b", "a")]

    def test_three_task_conflict(self) -> None:
        """Test suggestion for three-task conflict."""
        conflict = Conflict(
            type=ConflictType.FILE,
            target="src/shared.py",
            tasks=["a", "b", "c"],
        )
        tasks = [
            make_task("a", files_write=["src/shared.py"]),
            make_task("b", files_write=["src/shared.py"]),
            make_task("c", files_write=["src/shared.py"]),
        ]
        suggestions = suggest_dependency_fix(conflict, tasks)

        assert suggestions == [("b", "a"), ("c", "b")]


class TestGetConflictSummary:
    """Tests for get_conflict_summary."""

    def test_no_conflicts(self) -> None:
        """Test summary for no conflicts."""
        summary = get_conflict_summary([])
        assert summary == "No conflicts detected."

    def test_with_conflicts(self) -> None:
        """Test summary with conflicts."""
        conflicts = [
            Conflict(
                type=ConflictType.FILE,
                target="src/shared.py",
                tasks=["a", "b"],
            ),
            Conflict(
                type=ConflictType.RESOURCE,
                target="route:/api",
                tasks=["c", "d"],
            ),
        ]
        summary = get_conflict_summary(conflicts)

        assert "2 conflict(s)" in summary
        assert "File Conflicts" in summary
        assert "Resource Conflicts" in summary
        assert "src/shared.py" in summary
        assert "route:/api" in summary
