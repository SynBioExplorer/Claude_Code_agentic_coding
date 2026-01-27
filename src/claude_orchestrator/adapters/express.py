"""Express Node.js framework adapter."""

from __future__ import annotations

from pathlib import Path

from claude_orchestrator.adapters.base import AnchorPattern, BaseAdapter, GeneratedCode


class ExpressNodeAdapter(BaseAdapter):
    """Adapter for Express.js Node.js projects."""

    name = "express-node"

    supported_actions = {
        "add_router",
        "add_middleware",
    }

    def get_region_markers(self) -> dict[str, tuple[str, str]]:
        """Return JavaScript-style region markers."""
        return {
            "imports": ("// === AUTO:IMPORTS ===", "// === END:IMPORTS ==="),
            "routers": ("// === AUTO:ROUTERS ===", "// === END:ROUTERS ==="),
            "middleware": ("// === AUTO:MIDDLEWARE ===", "// === END:MIDDLEWARE ==="),
        }

    def get_anchor_patterns(self) -> dict[str, AnchorPattern]:
        """Return anchor patterns for Express files."""
        return {
            "imports": AnchorPattern(
                target_files=[
                    "app.js",
                    "src/app.js",
                    "index.js",
                    "src/index.js",
                    "app.ts",
                    "src/app.ts",
                ],
                anchor_regex=r"^const express = require|^import express from",
                position="after",
                fallback="end_of_imports",
            ),
            "routers": AnchorPattern(
                target_files=[
                    "app.js",
                    "src/app.js",
                    "index.js",
                    "src/index.js",
                    "app.ts",
                    "src/app.ts",
                ],
                anchor_regex=r"const app\s*=\s*express\(\)|const app:\s*Express\s*=\s*express\(\)",
                position="after",
                fallback="serialize",
            ),
            "middleware": AnchorPattern(
                target_files=[
                    "app.js",
                    "src/app.js",
                    "index.js",
                    "src/index.js",
                    "app.ts",
                    "src/app.ts",
                ],
                anchor_regex=r"const app\s*=\s*express\(\)",
                position="after",
                fallback="serialize",
            ),
        }

    def generate_code(self, action: str, intent: dict) -> GeneratedCode:
        """Generate code for an Express intent."""
        if action not in self.supported_actions:
            raise ValueError(f"Unsupported action: {action}")

        if action == "add_router":
            return self._generate_router(intent)
        elif action == "add_middleware":
            return self._generate_middleware(intent)

        return GeneratedCode()

    def _generate_router(self, intent: dict) -> GeneratedCode:
        """Generate router registration code."""
        router_path = intent["router_path"]  # e.g., "./routes/auth"
        prefix = intent["prefix"]
        use_typescript = intent.get("typescript", False)

        # Derive variable name from path
        # ./routes/auth -> authRouter
        parts = router_path.replace("./", "").replace("/", "_").split("_")
        var_name = parts[-1] + "Router"

        # Import
        if use_typescript:
            import_line = f'import {var_name} from "{router_path}";'
        else:
            import_line = f'const {var_name} = require("{router_path}");'

        # Registration
        body_line = f'app.use("{prefix}", {var_name});'

        return GeneratedCode(
            imports=[import_line],
            body=[body_line],
        )

    def _generate_middleware(self, intent: dict) -> GeneratedCode:
        """Generate middleware registration code."""
        middleware_name = intent["middleware_name"]
        import_from = intent.get("import_from", "")
        is_builtin = intent.get("builtin", False)
        options = intent.get("options", {})
        use_typescript = intent.get("typescript", False)

        imports: list[str] = []
        body_lines: list[str] = []

        if is_builtin:
            # Built-in Express middleware like json(), urlencoded()
            if options:
                opts_str = ", ".join(f"{k}: {repr(v)}" for k, v in options.items())
                body_lines.append(f"app.use(express.{middleware_name}({{ {opts_str} }}));")
            else:
                body_lines.append(f"app.use(express.{middleware_name}());")
        else:
            # Third-party middleware
            if import_from:
                if use_typescript:
                    imports.append(f'import {middleware_name} from "{import_from}";')
                else:
                    imports.append(f'const {middleware_name} = require("{import_from}");')

            if options:
                opts_str = ", ".join(f"{k}: {repr(v)}" for k, v in options.items())
                body_lines.append(f"app.use({middleware_name}({{ {opts_str} }}));")
            else:
                body_lines.append(f"app.use({middleware_name}());")

        return GeneratedCode(
            imports=imports,
            body=body_lines,
        )

    def get_implied_resources(self, action: str, intent: dict) -> list[str]:
        """Return resources implied by this intent."""
        if action == "add_router":
            prefix = intent.get("prefix", "/")
            return [f"route:{prefix}"]
        elif action == "add_middleware":
            name = intent.get("middleware_name", "")
            if name:
                return [f"middleware:{name}"]
        return []

    def detect_applicability(self, project_root: Path) -> float:
        """Detect if this is an Express.js project."""
        confidence = 0.0

        # Check for package.json with express dependency
        package_json = project_root / "package.json"
        if package_json.exists():
            try:
                import json

                data = json.loads(package_json.read_text())
                deps = data.get("dependencies", {})
                dev_deps = data.get("devDependencies", {})

                if "express" in deps or "express" in dev_deps:
                    confidence += 0.5

                # Extra confidence for @types/express (TypeScript)
                if "@types/express" in dev_deps:
                    confidence += 0.2
            except Exception:
                pass

        # Check for app.js or similar entry point
        entry_files = [
            "app.js",
            "src/app.js",
            "index.js",
            "src/index.js",
            "app.ts",
            "src/app.ts",
        ]

        for entry in entry_files:
            path = project_root / entry
            if path.exists():
                try:
                    content = path.read_text()
                    if "express()" in content or "require('express')" in content:
                        confidence += 0.3
                    if "import express from" in content:
                        confidence += 0.3
                except Exception:
                    pass
                break

        return min(confidence, 1.0)
