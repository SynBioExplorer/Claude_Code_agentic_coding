"""Tests for boundary validation."""

import pytest

from claude_orchestrator.schemas.config import OrchestrationConfig
from claude_orchestrator.worktree.isolation import (
    BoundaryViolation,
    check_forbidden_patterns,
    check_lockfile_pattern,
    check_unauthorized_files,
    get_lockfile_patterns,
)


class TestCheckForbiddenPatterns:
    """Tests for check_forbidden_patterns."""

    def test_node_modules_forbidden(self) -> None:
        """Test node_modules is forbidden."""
        result = check_forbidden_patterns("node_modules/package/index.js")
        assert result is not None
        assert "node_modules" in result

    def test_pycache_forbidden(self) -> None:
        """Test __pycache__ is forbidden."""
        result = check_forbidden_patterns("src/__pycache__/module.pyc")
        assert result is not None
        assert "__pycache__" in result

    def test_vendor_forbidden(self) -> None:
        """Test vendor directory is forbidden."""
        result = check_forbidden_patterns("vendor/lib/file.go")
        assert result is not None
        assert "vendor" in result

    def test_dist_forbidden(self) -> None:
        """Test dist directory is forbidden."""
        result = check_forbidden_patterns("dist/bundle.js")
        assert result is not None
        assert "dist" in result

    def test_build_forbidden(self) -> None:
        """Test build directory is forbidden."""
        result = check_forbidden_patterns("build/output.exe")
        assert result is not None
        assert "build" in result

    def test_generated_file_forbidden(self) -> None:
        """Test .generated. files are forbidden."""
        result = check_forbidden_patterns("src/types.generated.ts")
        assert result is not None
        assert "generated" in result

    def test_minified_js_forbidden(self) -> None:
        """Test .min.js files are forbidden."""
        result = check_forbidden_patterns("public/app.min.js")
        assert result is not None
        assert "min" in result

    def test_minified_css_forbidden(self) -> None:
        """Test .min.css files are forbidden."""
        result = check_forbidden_patterns("public/styles.min.css")
        assert result is not None
        assert "min" in result

    def test_normal_file_allowed(self) -> None:
        """Test normal source files are allowed."""
        result = check_forbidden_patterns("src/services/auth.py")
        assert result is None

    def test_test_file_allowed(self) -> None:
        """Test test files are allowed."""
        result = check_forbidden_patterns("tests/test_auth.py")
        assert result is None


class TestCheckLockfilePattern:
    """Tests for check_lockfile_pattern."""

    def test_package_lock_json(self) -> None:
        """Test package-lock.json is detected."""
        result = check_lockfile_pattern("package-lock.json")
        assert result is not None

    def test_pnpm_lock_yaml(self) -> None:
        """Test pnpm-lock.yaml is detected."""
        result = check_lockfile_pattern("pnpm-lock.yaml")
        assert result is not None

    def test_yarn_lock(self) -> None:
        """Test yarn.lock is detected."""
        result = check_lockfile_pattern("yarn.lock")
        assert result is not None

    def test_uv_lock(self) -> None:
        """Test uv.lock is detected."""
        result = check_lockfile_pattern("uv.lock")
        assert result is not None

    def test_poetry_lock(self) -> None:
        """Test poetry.lock is detected."""
        result = check_lockfile_pattern("poetry.lock")
        assert result is not None

    def test_cargo_lock(self) -> None:
        """Test Cargo.lock is detected."""
        result = check_lockfile_pattern("Cargo.lock")
        assert result is not None

    def test_go_sum(self) -> None:
        """Test go.sum is detected."""
        result = check_lockfile_pattern("go.sum")
        assert result is not None

    def test_gemfile_lock(self) -> None:
        """Test Gemfile.lock is detected."""
        result = check_lockfile_pattern("Gemfile.lock")
        assert result is not None

    def test_nested_lockfile(self) -> None:
        """Test nested lockfile is detected."""
        result = check_lockfile_pattern("packages/api/package-lock.json")
        assert result is not None

    def test_normal_file_not_lockfile(self) -> None:
        """Test normal files are not detected as lockfiles."""
        result = check_lockfile_pattern("src/lock.py")
        assert result is None


class TestGetLockfilePatterns:
    """Tests for get_lockfile_patterns."""

    def test_includes_common_lockfiles(self) -> None:
        """Test common lockfiles are included."""
        patterns = get_lockfile_patterns()

        # Should match common lockfiles
        lockfiles = [
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "uv.lock",
            "poetry.lock",
            "Cargo.lock",
            "go.sum",
            "Gemfile.lock",
        ]

        for lockfile in lockfiles:
            matched = any(
                __import__("re").search(p, lockfile)
                for p in patterns
            )
            assert matched, f"{lockfile} should be matched"

    def test_config_lockfile_included(self) -> None:
        """Test lockfile from config is included."""
        config = OrchestrationConfig()
        config.dependencies.ecosystems["python"] = type(
            "EcosystemConfig",
            (),
            {"manager": "uv", "manifest": "pyproject.toml", "lockfile": "custom.lock"},
        )()

        patterns = config.get_lockfile_patterns()

        matched = any(
            __import__("re").search(p, "custom.lock")
            for p in patterns
        )
        assert matched


class TestCheckUnauthorizedFiles:
    """Tests for check_unauthorized_files."""

    def test_no_violations(self) -> None:
        """Test no violations when all files allowed."""
        modified = {"src/a.py", "src/b.py"}
        allowed = {"src/a.py", "src/b.py", "src/c.py"}

        violations = check_unauthorized_files(modified, allowed)
        assert violations == []

    def test_unauthorized_file_detected(self) -> None:
        """Test unauthorized file is detected."""
        modified = {"src/a.py", "src/unauthorized.py"}
        allowed = {"src/a.py"}

        violations = check_unauthorized_files(modified, allowed)

        assert len(violations) == 1
        assert violations[0].type == "unauthorized_file"
        assert violations[0].file == "src/unauthorized.py"

    def test_multiple_violations(self) -> None:
        """Test multiple unauthorized files detected."""
        modified = {"src/a.py", "src/b.py", "src/c.py"}
        allowed = {"src/a.py"}

        violations = check_unauthorized_files(modified, allowed)

        assert len(violations) == 2
        unauthorized_files = {v.file for v in violations}
        assert unauthorized_files == {"src/b.py", "src/c.py"}
