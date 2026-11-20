"""Tests for .claude/orchestrator_code/conflict.py.

They need only pytest and the standard library. The script is not in an importable
package, so this module loads it by path. The directory has no __init__.py, so pytest
imports this file as a top-level module and never imports tests/unit or tests/integration.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".claude" / "orchestrator_code" / "conflict.py"
_spec = importlib.util.spec_from_file_location("conflict_script", SCRIPT)
conflict = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conflict)


def task(task_id, depends_on=(), **fields):
    """Build a task dict. Keyword arguments are task fields such as files_write."""
    return {"id": task_id, "depends_on": list(depends_on), **fields}


# Three ways for tasks to claim one shared target: a file, an explicit resource and a
# resource implied by a patch intent. Each entry is (conflict type, target, task fields).
CLAIMS = {
    "file": ("file_write_write", "shared.py", {"files_write": ["shared.py"]}),
    "resource": ("resource", "route:/api", {"resources_write": ["route:/api"]}),
    "implied resource": (
        "resource",
        "route:/api",
        {"patch_intents": [{"action": "add_router", "intent": {"prefix": "/api"}}]},
    ),
}


@pytest.fixture(params=CLAIMS)
def claim(request):
    """Return (conflict type, target, make) for one way of claiming a shared target."""
    conflict_type, target, fields = CLAIMS[request.param]
    return conflict_type, target, lambda task_id, depends_on=(): task(task_id, depends_on, **fields)


# One row per plan. claimants: the tasks that claim the shared target. edges: the
# depends_on list of each task named as a key; a task named only there claims nothing.
# expected: the task list of each conflict reported.
ORDERINGS = [
    pytest.param(["a", "b"], {}, [["a", "b"]], id="two tasks, no dependency"),
    pytest.param(["a", "b"], {"b": ["a"]}, [], id="two tasks, one depends on the other"),
    pytest.param(["a", "b", "c"], {"b": ["a"], "c": ["b"]}, [], id="chain a, b, c"),
    pytest.param(["a", "b", "c"], {}, [["a", "b", "c"]], id="three tasks, no dependency"),
    pytest.param(
        ["a", "b", "c"], {"b": ["a"]}, [["a", "c", "b"]], id="three tasks, only a and b ordered"
    ),
    pytest.param(
        ["a", "b", "c", "d"],
        {"b": ["a"], "c": ["a"], "d": ["b", "c"]},
        [["b", "c", "a", "d"]],
        id="diamond, b and c unordered",
    ),
    pytest.param(
        ["a", "c"], {"b": ["a"], "c": ["b"]}, [], id="ordered through a task that claims nothing"
    ),
]


@pytest.mark.parametrize(("claimants", "edges", "expected"), ORDERINGS)
def test_tasks_claiming_one_target(claim, claimants, edges, expected):
    conflict_type, target, make = claim
    plan = [make(t, edges.get(t, ())) for t in claimants]
    plan += [task(t, deps) for t, deps in edges.items() if t not in claimants]
    assert conflict.detect_conflicts(plan) == [
        {"type": conflict_type, "target": target, "tasks": tasks} for tasks in expected
    ]


# A task that claims a resource both explicitly and through a patch intent is listed twice
# among the claimants of that resource. A task is ordered with itself.
CLAIMED_TWICE = {
    "resources_write": ["route:/api"],
    "patch_intents": [{"action": "add_router", "intent": {"prefix": "/api"}}],
}


def test_task_claiming_a_resource_twice_does_not_conflict_with_itself():
    assert conflict.detect_conflicts([task("a", **CLAIMED_TWICE)]) == []


def test_task_claiming_a_resource_twice_is_ordered_before_a_dependent_task():
    plan = [task("a", **CLAIMED_TWICE), task("b", ["a"], resources_write=["route:/api"])]
    assert conflict.detect_conflicts(plan) == []


# Task "r" reads shared.py and the tasks named in writers write it. edges and expected
# are as above, except that expected holds (type, tasks) pairs.
READ_WRITE = [
    pytest.param(
        ["w"], {}, [("file_read_write", ["r", "w"])], id="reader and writer, no dependency"
    ),
    pytest.param(["w"], {"r": ["w"]}, [], id="reader depends on writer"),
    pytest.param(["w"], {"w": ["r"]}, [], id="writer depends on reader"),
    pytest.param(
        ["w"], {"x": ["w"], "r": ["x"]}, [], id="reader ordered through a task that does not write"
    ),
    pytest.param(
        ["w1", "w2"], {"w2": ["w1"], "r": ["w2"]}, [], id="writers in a chain, reader last"
    ),
    pytest.param(
        ["w1", "w2"],
        {"w2": ["w1"]},
        [("file_read_write", ["r", "w1", "w2"])],
        id="ordered writers, unrelated reader",
    ),
    pytest.param(
        ["w1", "w2"],
        {"w2": ["w1"], "r": ["w1"]},
        [("file_read_write", ["r", "w2"])],
        id="reader ordered after one writer only",
    ),
    pytest.param(
        ["w1", "w2"],
        {"r": ["w1", "w2"]},
        [("file_write_write", ["w1", "w2"])],
        id="unordered writers, reader last",
    ),
]


@pytest.mark.parametrize(("writers", "edges", "expected"), READ_WRITE)
def test_reader_and_writers_of_one_file(writers, edges, expected):
    plan = [task("r", edges.get("r", ()), files_read=["shared.py"])]
    plan += [task(w, edges.get(w, ()), files_write=["shared.py"]) for w in writers]
    plan += [task(t, deps) for t, deps in edges.items() if t != "r" and t not in writers]
    found = [(c["type"], c["tasks"]) for c in conflict.detect_conflicts(plan)]
    assert found == expected


def test_read_write_conflict_format():
    plan = [task("r", files_read=["shared.py"]), task("w", files_write=["shared.py"])]
    assert conflict.detect_conflicts(plan) == [
        {
            "type": "file_read_write",
            "target": "shared.py",
            "tasks": ["r", "w"],
            "detail": "r reads while ['w'] write",
        }
    ]


# The plan that exposed the bug. b depends on a and c depends on nothing, so dag.py puts
# a and c in the same wave.
THREE_WRITERS = [
    task("a", files_write=["shared.py"]),
    task("b", ["a"], files_write=["shared.py"]),
    task("c", files_write=["shared.py"]),
]


def run_script(tmp_path, tasks, *flags):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"tasks": tasks}))
    command = [sys.executable, "-X", "utf8", str(SCRIPT), *flags, str(plan)]
    return subprocess.run(command, capture_output=True, encoding="utf-8")


def test_script_reports_three_writers_as_json(tmp_path):
    result = run_script(tmp_path, THREE_WRITERS, "--json")
    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "conflicts": [
            {"type": "file_write_write", "target": "shared.py", "tasks": ["a", "c", "b"]}
        ],
        "count": 1,
    }


def test_script_suggests_ordering_an_unordered_pair(tmp_path):
    result = run_script(tmp_path, THREE_WRITERS)
    assert result.returncode == 1
    assert "[FILE_WRITE_WRITE] shared.py" in result.stdout
    assert "Tasks: a, c, b" in result.stdout
    assert "Fix: Add dependency: c depends_on [a]" in result.stdout


def test_script_accepts_a_chain(tmp_path):
    chain = [
        task("a", files_write=["shared.py"]),
        task("b", ["a"], files_write=["shared.py"]),
        task("c", ["b"], files_write=["shared.py"]),
    ]
    result = run_script(tmp_path, chain)
    assert result.returncode == 0
    assert "No conflicts detected" in result.stdout
