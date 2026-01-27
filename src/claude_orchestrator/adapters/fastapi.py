"""FastAPI Python framework adapter."""

from __future__ import annotations

from pathlib import Path

from claude_orchestrator.adapters.base import AnchorPattern, BaseAdapter, GeneratedCode


class FastAPIPythonAdapter(BaseAdapter):
    """Adapter for FastAPI Python projects."""

    name = "fastapi-python"

    supported_actions = {
        "add_router",
        "add_middleware",
        "add_dependency",
        "add_config",
    }

    def get_region_markers(self) -> dict[str, tuple[str, str]]:
        """Return Python-style region markers."""
        return {
            "imports": ("# === AUTO:IMPORTS ===", "# === END:IMPORTS ==="),
            "routers": ("# === AUTO:ROUTERS ===", "# === END:ROUTERS ==="),
            "middleware": ("# === AUTO:MIDDLEWARE ===", "# === END:MIDDLEWARE ==="),
            "dependencies": ("# === AUTO:DEPENDENCIES ===", "# === END:DEPENDENCIES ==="),
            "config": ("# === AUTO:CONFIG ===", "# === END:CONFIG ==="),
        }

    def get_anchor_patterns(self) -> dict[str, AnchorPattern]:
        """Return anchor patterns for FastAPI files."""
        return {
            "imports": AnchorPattern(
                target_files=["main.py", "src/main.py", "app.py", "src/app.py"],
                anchor_regex=r"^from fastapi import|^import fastapi",
                position="after",
                fallback="end_of_imports",
            ),
            "routers": AnchorPattern(
                target_files=["main.py", "src/main.py", "app.py", "src/app.py"],
                anchor_regex=r"app\s*=\s*FastAPI\(",
                position="after",
                fallback="serialize",
            ),
            "middleware": AnchorPattern(
                target_files=["main.py", "src/main.py", "app.py", "src/app.py"],
                anchor_regex=r"app\s*=\s*FastAPI\(",
                position="after",
                fallback="serialize",
            ),
            "dependencies": AnchorPattern(
                target_files=["dependencies.py", "src/dependencies.py", "deps.py"],
                anchor_regex=r"^from typing import|^import typing",
                position="after",
                fallback="start_of_file",
            ),
        }

    def generate_code(self, action: str, intent: dict) -> GeneratedCode:
        """Generate code for a FastAPI intent."""
        if action not in self.supported_actions:
            raise ValueError(f"Unsupported action: {action}")

        if action == "add_router":
            return self._generate_router(intent)
        elif action == "add_middleware":
            return self._generate_middleware(intent)
        elif action == "add_dependency":
            return self._generate_dependency(intent)
        elif action == "add_config":
            return self._generate_config(intent)

        return GeneratedCode()

    def _generate_router(self, intent: dict) -> GeneratedCode:
        """Generate router registration code."""
        module = intent["router_module"]
        name = intent.get("router_name", "router")
        prefix = intent["prefix"]
        tags = intent.get("tags", [])
        deps = intent.get("dependencies", [])

        # Import goes to AUTO:IMPORTS region
        alias = module.split(".")[-1] + "_router"
        import_line = f"from {module} import {name} as {alias}"

        # Registration goes to AUTO:ROUTERS region
        parts = [f'app.include_router({alias}, prefix="{prefix}"']
        if tags:
            parts.append(f", tags={tags}")
        if deps:
            deps_str = ", ".join(deps)
            parts.append(f", dependencies=[{deps_str}]")
        parts.append(")")
        body_line = "".join(parts)

        return GeneratedCode(
            imports=[import_line],
            body=[body_line],
        )

    def _generate_middleware(self, intent: dict) -> GeneratedCode:
        """Generate middleware registration code."""
        cls = intent["middleware_class"]
        import_from = intent["import_from"]
        kwargs = intent.get("kwargs", {})

        import_line = f"from {import_from} import {cls}"

        kwargs_str = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
        body_line = f"app.add_middleware({cls}, {kwargs_str})"

        return GeneratedCode(
            imports=[import_line],
            body=[body_line],
        )

    def _generate_dependency(self, intent: dict) -> GeneratedCode:
        """Generate dependency injection function code."""
        func_name = intent["function_name"]
        return_type = intent["return_type"]
        import_from = intent["import_from"]
        import_name = intent["import_name"]
        is_async = intent.get("is_async", False)
        cache = intent.get("cache", False)

        # Import
        import_line = f"from {import_from} import {import_name}"

        # Function body
        body_lines: list[str] = []
        if cache:
            body_lines.append("@lru_cache")

        async_prefix = "async " if is_async else ""
        body_lines.append(f"{async_prefix}def {func_name}() -> {return_type}:")
        body_lines.append(f"    return {import_name}()")

        return GeneratedCode(
            imports=[import_line],
            body=body_lines,
        )

    def _generate_config(self, intent: dict) -> GeneratedCode:
        """Generate configuration code."""
        key = intent["key"]
        value = intent["value"]
        description = intent.get("description", "")

        # Config setting
        if description:
            body_line = f'{key} = {repr(value)}  # {description}'
        else:
            body_line = f"{key} = {repr(value)}"

        return GeneratedCode(
            config=[body_line],
        )

    def get_implied_resources(self, action: str, intent: dict) -> list[str]:
        """Return resources implied by this intent."""
        if action == "add_router":
            prefix = intent.get("prefix", "/")
            return [f"route:{prefix}"]
        elif action == "add_dependency":
            func_name = intent.get("function_name", "")
            if func_name:
                return [f"di:{func_name}"]
        elif action == "add_middleware":
            cls = intent.get("middleware_class", "")
            if cls:
                return [f"middleware:{cls}"]
        elif action == "add_config":
            key = intent.get("key", "")
            if key:
                return [f"config:{key}"]
        return []

    def detect_applicability(self, project_root: Path) -> float:
        """Detect if this is a FastAPI project."""
        confidence = 0.0

        # Check explicit candidate paths
        candidate_paths = [
            project_root / "main.py",
            project_root / "app.py",
            project_root / "src" / "main.py",
            project_root / "src" / "app.py",
            project_root / "app" / "main.py",
        ]

        for path in candidate_paths:
            if path.exists():
                try:
                    content = path.read_text()
                    if "from fastapi import" in content or "import fastapi" in content:
                        confidence += 0.4
                    if "FastAPI()" in content:
                        confidence += 0.3
                except Exception:
                    pass

        # Check dependency files
        for req_file in ["pyproject.toml", "requirements.txt"]:
            path = project_root / req_file
            if path.exists():
                try:
                    content = path.read_text().lower()
                    if "fastapi" in content:
                        confidence += 0.3
                except Exception:
                    pass

        return min(confidence, 1.0)
