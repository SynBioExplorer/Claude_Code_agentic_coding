# Claude Code Multi-Agent Orchestration System

## Architecture Overview

A coordinated multi-agent system for Claude Code that enables parallel task execution with intelligent dependency management, git worktree isolation, and automated review cycles.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER REQUEST                                    │
│                     "Add authentication + dashboard"                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PLANNER-ARCHITECT                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Analyze    │→ │  Design     │→ │  Generate   │→ │  Output     │        │
│  │  Codebase   │  │  Architecture│  │  Contracts  │  │  Task DAG   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                              │
│  Outputs: tasks.yaml, contracts/, execution-plan.md                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
                 ┌─────────────┐      ┌─────────────────┐
                 │ Human Gate  │      │ Auto-approve if │
                 │ (Y/N/Edit)  │      │ risk_score < T  │
                 └──────┬──────┘      └────────┬────────┘
                        └──────────┬───────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            SUPERVISOR                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Parse DAG  │→ │  Spawn      │→ │  Monitor    │→ │  Merge &    │        │
│  │             │  │  Worktrees  │  │  Progress   │  │  Handoff    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                              │
│  Manages: tmux sessions, git worktrees, .task-status.json polling            │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│      WORKER A       │ │      WORKER B       │ │      WORKER C       │
│  ┌───────────────┐  │ │  ┌───────────────┐  │ │  ┌───────────────┐  │
│  │ worktree/     │  │ │  │ worktree/     │  │ │  │ worktree/     │  │
│  │ task-a/       │  │ │  │ task-b/       │  │ │  │ task-c/       │  │
│  └───────────────┘  │ │  └───────────────┘  │ │  └───────────────┘  │
│  Files: auth.py     │ │  Files: api.py      │ │  Files: utils.py    │
│  Status: .json      │ │  Status: .json      │ │  Status: .json      │
└─────────────────────┘ └─────────────────────┘ └─────────────────────┘
                 │                   │                   │
                 └───────────────────┼───────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              VERIFIER                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Run Tests  │→ │  Check      │→ │  Validate   │→ │  Pass/Fail  │        │
│  │  & Lint     │  │  Contracts  │  │  Boundaries │  │  Per Task   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                              │
│  Per-task verification before merge. No architectural judgment.              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PLANNER-ARCHITECT (Review Mode)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Evaluate   │→ │  Check      │→ │  Assess     │→ │  Accept or  │        │
│  │  Integration│  │  Architecture│  │  Quality    │  │  Iterate    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                              │
│  Holistic review after all tasks merged. Max 3 iterations before escalation. │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Layering

This specification separates **core orchestration protocol** from **framework-specific adapters**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CORE ORCHESTRATION PROTOCOL                          │
│                                                                              │
│  • DAG-based task scheduling                                                 │
│  • Git worktree isolation                                                    │
│  • File + Resource ownership & conflict detection                            │
│  • Interface contracts & version hashing                                     │
│  • State machine (task lifecycle, contract renegotiation)                    │
│  • Verifier (mechanical checks)                                              │
│  • Risk-based approval gates                                                 │
│  • Environment hash verification                                             │
│                                                                              │
│  Language/framework agnostic. Works with any ecosystem.                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FRAMEWORK ADAPTERS                                  │
│                                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  FastAPI    │  │  Express    │  │  Spring     │  │  (none)     │        │
│  │  Python     │  │  Node.js    │  │  Java       │  │  Fallback   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                              │
│  • Intent schemas (add_router, add_middleware, etc.)                         │
│  • Code generation templates (multi-region output)                           │
│  • Region marker conventions + anchor patterns                               │
│  • Implied resource declarations                                             │
│                                                                              │
│  If no adapter exists → intents disabled → hot files use serialization.     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key principle:** The core protocol makes no assumptions about language or framework. Adapters provide framework-specific capabilities. If no adapter matches, the system falls back to file-level serialization (safe but less parallel).

---

## Core Design Principles

### 1. Physical Isolation via Git Worktrees
Each worker agent operates in a separate git worktree, providing filesystem-level isolation without the overhead of full repository clones.

```bash
repo/
├── .git/                    # Shared git database
├── main/                    # Main working directory
└── .worktrees/
    ├── task-a/              # Worker A's isolated filesystem
    ├── task-b/              # Worker B's isolated filesystem
    └── task-c/              # Worker C's isolated filesystem
```

**Why this works:** Agents literally cannot see or corrupt each other's in-progress work. Merges are explicit git operations, not file overwrites.

### 2. DAG-Based Task Scheduling
Tasks are organized as a Directed Acyclic Graph (DAG), not a flat list. This enables maximum parallelism while respecting dependencies.

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Task A   │     │ Task B   │     │ Task C   │
│ auth.py  │     │ api.py   │     │ utils.py │
└────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │
     │ (file overlap) │ (reads auth)   │ (independent)
     ▼                ▼                │
┌──────────┐     ┌──────────┐          │
│ Task D   │     │ Task E   │◄─────────┘
│ auth.py  │     │ api.py,  │  (E also writes utils.py)
│ (logout) │     │ utils.py │
└──────────┘     └──────────┘

Execution: [A, B, C] parallel → wait → [D, E] parallel (E waits for C)
```

### 3. File + Resource Ownership Matrix

The Planner-Architect assigns both **file** and **resource** ownership per task.

**Files** are filesystem paths. **Resources** are logical identifiers for framework concepts (routes, DI bindings, config keys) that may conflict even when files don't overlap.

| Task | files_write | resources_write | Depends On |
|------|-------------|-----------------|------------|
| task-a | `auth.py` | `route:/auth`, `di:AuthService` | — |
| task-b | `users.py` | `route:/users`, `di:UserService` | task-a |
| task-c | `config.py` | `config:AUTH_SECRET` | — |
| task-d | `auth.py` | `route:/auth/refresh` | task-a |

**Conflict rules:**
- Same `files_write` → sequential execution
- Same `resources_write` → sequential execution (even if different files)
- Intents auto-emit implied resources (see below)

```yaml
# Task schema with resources
tasks:
  - id: task-a
    files_write: ["src/services/auth.py", "src/routes/auth.py"]
    files_read: ["src/models/user.py"]
    
    # Explicit resource declarations (optional, for non-intent resources)
    resources_write:
      - "route:/auth"
      - "route:/auth/login"
      - "route:/auth/logout"
      - "di:AuthService"
    resources_read:
      - "config:DATABASE_URL"
    
    # Intents auto-emit implied resources (see Structured Patch Intents)
    patch_intents:
      - file: "src/main.py"
        action: "add_router"
        intent:
          router_module: "src.routes.auth"
          prefix: "/auth"
          # IMPLIED: resources_write += ["route:/auth"]
```

**Resource conflict detection:**

```python
def detect_resource_conflicts(tasks: list[dict]) -> list[Conflict]:
    """Detect conflicts on both files and resources."""
    conflicts = []
    
    # Collect all writes
    file_writes = defaultdict(list)    # file -> [task_ids]
    resource_writes = defaultdict(list) # resource -> [task_ids]
    
    for task in tasks:
        for f in task.get("files_write", []):
            file_writes[f].append(task["id"])
        
        # Explicit resources
        for r in task.get("resources_write", []):
            resource_writes[r].append(task["id"])
        
        # Implied resources from intents
        for intent in task.get("patch_intents", []):
            implied = get_implied_resources(intent)
            for r in implied:
                resource_writes[r].append(task["id"])
    
    # Check for conflicts (multiple writers without dependency)
    for file, writers in file_writes.items():
        if len(writers) > 1:
            if not tasks_ordered_by_dependency(writers, tasks):
                conflicts.append(Conflict(
                    type="file",
                    target=file,
                    tasks=writers
                ))
    
    for resource, writers in resource_writes.items():
        if len(writers) > 1:
            if not tasks_ordered_by_dependency(writers, tasks):
                conflicts.append(Conflict(
                    type="resource",
                    target=resource,
                    tasks=writers
                ))
    
    return conflicts


def get_implied_resources(intent: dict) -> list[str]:
    """Extract implied resources from an intent."""
    action = intent["action"]
    data = intent.get("intent", {})
    
    if action == "add_router":
        prefix = data.get("prefix", "/")
        return [f"route:{prefix}"]
    
    elif action == "add_dependency":
        func_name = data.get("function_name", "")
        return [f"di:{func_name}"]
    
    elif action == "add_config":
        key = data.get("key", "")
        return [f"config:{key}"]
    
    elif action == "add_middleware":
        name = data.get("middleware_class", "")
        return [f"middleware:{name}"]
    
    return []
```

### 4. Interface Contracts (Stub Generation + Version Hashing)
Before parallel execution begins, the Planner-Architect generates interface stubs for cross-task dependencies. Workers code against frozen, version-stamped interfaces.

```python
# contracts/auth_interface.py (generated before workers start)
"""
Contract: AuthServiceProtocol
Version: c7a3f2b (commit hash when contract was created)
Generated: 2025-01-27T10:00:00Z
"""
from typing import Protocol

class AuthServiceProtocol(Protocol):
    def login(self, username: str, password: str) -> dict:
        """Returns {token: str, expires_at: datetime}"""
        ...
    
    def logout(self, token: str) -> bool:
        ...
```

**Contract Version Enforcement:**

Every contract is stamped with a commit hash. Workers record which contract version they built against:

```json
// .task-status.json
{
  "task_id": "task-b",
  "contracts_used": {
    "AuthServiceProtocol": {
      "version": "c7a3f2b",
      "methods_used": ["login", "verify"]
    }
  }
}
```

### 5. Sequential Handoff for Overlapping Files/Resources
When tasks must modify the same file or resource, the DAG enforces ordering:

```yaml
tasks:
  - id: task-a
    files_write: [src/auth.py]
    resources_write: ["route:/auth"]
    depends_on: []
    
  - id: task-d
    files_write: [src/auth.py]  # Same file!
    resources_write: ["route:/auth/refresh"]
    depends_on: [task-a]        # Forced sequential execution
```

### 6. Executable Verification Required

**HARD REQUIREMENT:** Every task MUST define at least one executable verification command.

```yaml
# INVALID - will be rejected at planning time
tasks:
  - id: task-a
    verification: []  # ❌ REJECTED: No verification defined

# VALID
tasks:
  - id: task-a
    verification:
      - command: "pytest tests/test_auth.py"
        type: "test"
        required: true
```

**Verification command resolution:**

> **IMPORTANT:** Per-task `verification` commands are **authoritative**. Template placeholders like `{modified_tests}` use heuristic mapping that may be incorrect for monorepos or nonstandard layouts. When in doubt, specify explicit test paths in per-task verification commands.

Per-task `verification` commands are **authoritative**. Template placeholders like `{modified_tests}` are resolved as follows:

```python
def resolve_verification_command(command: str, task: dict, worktree: str) -> str:
    """Resolve template placeholders in verification commands."""
    
    if "{modified_files}" in command:
        # Get files modified by this task (from git diff)
        modified = get_modified_files(worktree)
        command = command.replace("{modified_files}", " ".join(modified))
    
    if "{modified_tests}" in command:
        # Convention: test file for src/foo.py is tests/test_foo.py
        modified = get_modified_files(worktree)
        test_files = []
        
        for f in modified:
            if f.startswith("tests/"):
                test_files.append(f)
            elif f.startswith("src/"):
                # Map src/services/auth.py -> tests/test_auth.py
                base = Path(f).stem
                candidates = [
                    f"tests/test_{base}.py",
                    f"tests/{base}_test.py",
                    f"tests/test_{Path(f).parent.name}_{base}.py"
                ]
                for candidate in candidates:
                    if Path(worktree, candidate).exists():
                        test_files.append(candidate)
                        break
        
        command = command.replace("{modified_tests}", " ".join(test_files) or "tests/")
    
    return command
```

**Note:** If template resolution yields no files, the command uses sensible defaults (e.g., `tests/`). Per-task explicit commands always override global templates.

### 7. Environment Hash Verification

**INVARIANT:** All workers must execute against the same environment hash.

```python
# Stage 0.5: Environment setup records hash
env_result = setup_environment(tasks, config)
state["environment"]["hash"] = env_result.env_hash
state["environment"]["installed_at"] = datetime.now().isoformat()

# Worker startup: record env_hash being used
# .task-status.json
{
  "task_id": "task-a",
  "environment": {
    "hash": "a3f2c7b1",
    "verified_at": "2025-01-27T10:30:05Z"
  }
}

# Verifier: check env_hash matches
def validate_environment(task_status: dict, global_state: dict) -> EnvResult:
    """Ensure worker used the correct environment."""
    
    expected_hash = global_state["environment"]["hash"]
    actual_hash = task_status.get("environment", {}).get("hash")
    
    if actual_hash != expected_hash:
        return EnvResult(
            valid=False,
            error=f"Environment mismatch: task used {actual_hash}, "
                  f"expected {expected_hash}. Worker may have stale dependencies."
        )
    
    return EnvResult(valid=True)
```

### 8. Risk-Based Approval Gates

Auto-approval is not arbitrary. The system computes a **risk score** for each execution plan.

```python
def compute_risk_score(plan: ExecutionPlan) -> RiskScore:
    """Compute risk score for auto-approval decision."""
    
    score = 0
    factors = []
    
    # Factor 1: Sensitive paths
    SENSITIVE_PATTERNS = [
        (r"auth|security|crypto", 20),
        (r"payment|billing|stripe", 25),
        (r"prod|production|deploy", 30),
        (r"admin|sudo|root", 15),
        (r"\.env|secret|key|token", 25),
        (r"migration|schema|database", 15),
    ]
    
    for task in plan.tasks:
        for path in task.files_write:
            for pattern, weight in SENSITIVE_PATTERNS:
                if re.search(pattern, path, re.IGNORECASE):
                    score += weight
                    factors.append(f"sensitive_path:{path}:{pattern}")
    
    # Factor 2: Scale
    num_tasks = len(plan.tasks)
    num_files = sum(len(t.files_write) for t in plan.tasks)
    
    if num_tasks > 5:
        score += (num_tasks - 5) * 5
        factors.append(f"many_tasks:{num_tasks}")
    
    if num_files > 10:
        score += (num_files - 10) * 3
        factors.append(f"many_files:{num_files}")
    
    # Factor 3: Hot files (intents)
    hot_file_count = sum(len(t.patch_intents) for t in plan.tasks)
    if hot_file_count > 3:
        score += (hot_file_count - 3) * 5
        factors.append(f"many_hot_files:{hot_file_count}")
    
    # Factor 4: Dependency changes
    if any(t.deps_required for t in plan.tasks):
        new_deps = sum(
            len(t.deps_required.get("runtime", []))
            for t in plan.tasks
        )
        score += new_deps * 3
        factors.append(f"new_dependencies:{new_deps}")
    
    # Factor 5: Contract complexity
    if len(plan.contracts) > 3:
        score += (len(plan.contracts) - 3) * 5
        factors.append(f"many_contracts:{len(plan.contracts)}")
    
    # Factor 6: Verification coverage
    tasks_with_tests = sum(
        1 for t in plan.tasks
        if any(v["type"] == "test" for v in t.verification)
    )
    test_coverage_ratio = tasks_with_tests / len(plan.tasks)
    if test_coverage_ratio < 1.0:
        score += int((1.0 - test_coverage_ratio) * 20)
        factors.append(f"incomplete_test_coverage:{test_coverage_ratio:.0%}")
    
    return RiskScore(
        value=score,
        factors=factors,
        auto_approve=score < plan.config.auto_approve_threshold
    )
```

**Risk thresholds (configurable):**

| Risk Score | Action |
|------------|--------|
| 0-25 | Auto-approve |
| 26-50 | Human review recommended |
| 51+ | Human review required |

---

## Agent Specifications

### Planner-Architect Agent

**Role:** Analyze requests, design architecture, decompose into parallel tasks, review completed work holistically.

**Modes:**
- **Plan Mode:** Input = user request → Output = `tasks.yaml` + `contracts/` + `execution-plan.md`
- **Review Mode:** Input = verified work from all tasks → Output = Accept / Iterate with feedback

**Tools:** `Read`, `Grep`, `Glob`, `Bash` (for running tests/linters)

**Model:** `opus` (reasoning-intensive)

**Planning Process:**

1. **Codebase Analysis**
2. **Architecture Design** (if feature requires it)
3. **Interface Contract Generation**
4. **Task Decomposition**
   - Assign file ownership
   - Assign resource ownership (explicit + implied from intents)
   - Detect file/resource conflicts → force ordering
   - **ENFORCE:** Every task MUST have ≥1 verification command
5. **Output Generation**

---

### Verifier Agent

**Role:** Execute deterministic verification checks on individual tasks. No architectural judgment—purely mechanical validation.

**Tools:** `Bash`, `Read`

**Model:** `sonnet` (execution-focused, lower cost)

**Responsibilities:**

1. **Execute Verification Commands**
   ```python
   def verify_task(task_id: str, task_spec: dict, global_state: dict) -> VerificationResult:
       results = []
       worktree = f".worktrees/{task_id}"
       
       for check in task_spec["verification"]:
           # Resolve templates
           command = resolve_verification_command(check["command"], task_spec, worktree)
           
           result = run_command(command, cwd=worktree)
           results.append({
               "command": check["command"],
               "resolved_command": command,
               "type": check["type"],
               "required": check["required"],  # Record per-result
               "passed": result.returncode == 0,
               "output": result.stdout,
               "error": result.stderr,
               "duration_ms": result.duration
           })
       
       return VerificationResult(
           task_id=task_id,
           all_passed=all(r["passed"] for r in results if r["required"]),  # Reference r["required"]
           checks=results
       )
   ```

2. **Validate File Boundaries (with Churn Detection)**
   ```python
   def validate_boundaries(task_id: str, task_spec: dict, config: dict) -> BoundaryResult:
       worktree_path = f".worktrees/{task_id}"
       
       modified = get_modified_files(worktree_path)
       allowed = set(task_spec["files_write"]) | set(task_spec.get("files_append", []))
       
       violations = []
       
       # Check 1: Files outside allowlist
       unauthorized = modified - allowed
       for f in unauthorized:
           violations.append({
               "type": "unauthorized_file",
               "file": f,
               "message": f"Modified file not in files_write: {f}"
           })
       
       # Check 2: Forbidden patterns (always blocked)
       FORBIDDEN_PATTERNS = [
           r"node_modules/",
           r"__pycache__/",
           r"\.pyc$",
           r"vendor/",
           r"dist/",
           r"build/",
           r"\.generated\.",  # Generated files
           r"\.min\.(js|css)$",
       ]
       
       # Dynamically add lockfile patterns from ecosystem config
       # This catches pnpm-lock.yaml, package-lock.json, yarn.lock, etc.
       lockfile_patterns = get_lockfile_patterns(config)
       # e.g., ["pnpm-lock\\.yaml$", "package-lock\\.json$", "yarn\\.lock$", 
       #        "uv\\.lock$", "poetry\\.lock$", "requirements\\.lock$",
       #        "Cargo\\.lock$", "go\\.sum$", "Gemfile\\.lock$"]
       
       for f in modified:
           for pattern in FORBIDDEN_PATTERNS:
               if re.search(pattern, f):
                   violations.append({
                       "type": "forbidden_pattern",
                       "file": f,
                       "pattern": pattern,
                       "message": f"Worker cannot modify files matching {pattern}"
                   })
           
           # Check lockfiles separately (derived from config)
           for lockfile_pattern in lockfile_patterns:
               if re.search(lockfile_pattern, f):
                   violations.append({
                       "type": "forbidden_lockfile",
                       "file": f,
                       "message": f"Worker cannot modify lockfile: {f}. "
                                  f"Only Supervisor can modify lockfiles."
                   })
       
       # Check 3: Churn detection
       if config.get("reject_excessive_churn", True):
           churn_threshold = config.get("churn_threshold_lines", 500)
           
           for f in modified & allowed:
               stats = get_file_diff_stats(worktree_path, f)
               
               if stats["lines_changed"] > churn_threshold:
                   if not task_spec.get("allow_large_changes", False):
                       violations.append({
                           "type": "excessive_churn",
                           "file": f,
                           "lines_changed": stats["lines_changed"],
                           "threshold": churn_threshold
                       })
       
       # Check 4: Format-only changes (allowlist-based)
       if config.get("reject_formatting_churn", True):
           for f in modified & allowed:
               if is_formatting_only_change(worktree_path, f, config):
                   violations.append({
                       "type": "formatting_only",
                       "file": f,
                       "message": "File has only formatting changes."
                   })
       
       return BoundaryResult(valid=len(violations) == 0, violations=violations)
   
   
   def get_lockfile_patterns(config: dict) -> list[str]:
       """Derive lockfile regex patterns from ecosystem config.
       
       This ensures we catch all lockfile variants (pnpm-lock.yaml, 
       package-lock.json, yarn.lock, etc.) rather than just \.lock$.
       """
       patterns = []
       
       # From explicit ecosystem config
       ecosystems = config.get("dependencies", {}).get("ecosystems", {})
       for eco_name, eco_config in ecosystems.items():
           lockfile = eco_config.get("lockfile", "")
           if lockfile:
               # Escape for regex and anchor to filename
               escaped = re.escape(lockfile)
               patterns.append(f"(^|/){escaped}$")
       
       # Always include common lockfiles as fallback
       COMMON_LOCKFILES = [
           "package-lock.json",
           "pnpm-lock.yaml", 
           "yarn.lock",
           "uv.lock",
           "poetry.lock",
           "requirements.lock",
           "Pipfile.lock",
           "Cargo.lock",
           "go.sum",
           "Gemfile.lock",
           "packages.lock.json",  # .NET
           "composer.lock",       # PHP
       ]
       
       for lockfile in COMMON_LOCKFILES:
           escaped = re.escape(lockfile)
           pattern = f"(^|/){escaped}$"
           if pattern not in patterns:
               patterns.append(pattern)
       
       return patterns
   
   
   def is_formatting_only_change(worktree: str, file_path: str, config: dict) -> bool:
       """Detect if changes are only whitespace/formatting.
       
       Only applies to whitespace-insensitive file types.
       """
       # Allowlist: file types where whitespace is NOT semantic
       FORMATTING_CHECK_ALLOWLIST = {
           ".js", ".ts", ".jsx", ".tsx",  # JavaScript/TypeScript
           ".json",                        # JSON
           ".md", ".rst",                  # Markdown/RST (mostly)
           ".css", ".scss", ".less",       # Stylesheets
           ".html", ".xml",                # Markup
           ".java", ".kt",                 # JVM languages
           ".go", ".rs",                   # Go, Rust
           ".c", ".cpp", ".h",             # C/C++
           ".cs",                          # C#
           ".rb",                          # Ruby
           ".php",                         # PHP
       }
       
       # Denylist: file types where whitespace IS semantic
       FORMATTING_CHECK_DENYLIST = {
           ".py",       # Python (indentation)
           ".yaml", ".yml",  # YAML (indentation)
           ".mk", "Makefile",  # Makefiles (tabs)
           ".haml",     # Haml (indentation)
           ".pug", ".jade",  # Pug/Jade (indentation)
           ".coffee",   # CoffeeScript (indentation)
           ".slim",     # Slim (indentation)
       }
       
       ext = Path(file_path).suffix.lower()
       name = Path(file_path).name
       
       # Check denylist first (explicit exclusion)
       if ext in FORMATTING_CHECK_DENYLIST or name in FORMATTING_CHECK_DENYLIST:
           return False  # Don't flag as formatting-only for these types
       
       # Only check allowlisted types
       if ext not in FORMATTING_CHECK_ALLOWLIST:
           return False  # Unknown type, don't flag
       
       # Use git diff ignoring whitespace
       result = run_command(
           f"git -C {worktree} diff -w --quiet main -- {file_path}"
       )
       # Exit code 0 = no semantic diff (only whitespace)
       return result.returncode == 0
   ```

3. **Check Contract Versions**

4. **Verify Environment Hash**
   ```python
   def validate_environment(task_status: dict, global_state: dict) -> EnvResult:
       expected_hash = global_state["environment"]["hash"]
       actual_hash = task_status.get("environment", {}).get("hash")
       
       if actual_hash != expected_hash:
           return EnvResult(
               valid=False,
               error=f"Environment mismatch: {actual_hash} != {expected_hash}"
           )
       return EnvResult(valid=True)
   ```

**Output:**

```json
{
  "task_id": "task-a",
  "verification_passed": true,
  "boundaries_valid": true,
  "contracts_valid": true,
  "environment_valid": true,
  "checks": [...],
  "boundary_checks": {
    "unauthorized_files": [],
    "forbidden_patterns": [],
    "excessive_churn": [],
    "formatting_only": []
  }
}
```

---

### Supervisor Agent

**Role:** Orchestrate execution, manage worktrees and tmux sessions, monitor progress, handle merges.

*(Unchanged from ARCHITECTURE_6.md)*

---

### Worker Agent

**Role:** Execute a single task within an isolated worktree.

**Worker Constraints:**
- **MUST** only modify files listed in `files_write`
- **MUST** only claim resources listed in `resources_write` (or implied by intents)
- **MUST** read interfaces from `contracts/`, not guess
- **MUST** update `.task-status.json` on every significant step
- **MUST** record `environment.hash` at startup
- **MUST NOT** modify files outside assignment
- **MUST** use structured patch intents for hot files (when adapter available)
- **MUST NOT** modify lockfiles, generated files, or vendor directories

---

## Structured Patch Intents & Framework Adapters

### Overview

Workers submit **structured intents** instead of raw code for hot files. The Integrator generates canonical code using **framework-specific adapters** that produce **multi-region output**.

```
┌─────────────────────────────────────────────────────────────────┐
│                  STRUCTURED PATCH INTENTS                        │
│                                                                  │
│  Worker submits intent:                                          │
│    {                                                             │
│      "action": "add_router",                                     │
│      "intent": {                                                 │
│        "router_module": "src.routes.auth",                       │
│        "prefix": "/auth",                                        │
│        "tags": ["authentication"]                                │
│      }                                                           │
│    }                                                             │
│                                                                  │
│  Adapter produces MULTI-REGION output:                           │
│    {                                                             │
│      "imports": ["from src.routes.auth import router as ..."],   │
│      "body": ["app.include_router(auth_router, prefix=...)"]     │
│    }                                                             │
│                                                                  │
│  Integrator routes to appropriate regions:                       │
│    imports → AUTO:IMPORTS region                                 │
│    body    → AUTO:ROUTERS region                                 │
│                                                                  │
│  Implied resources auto-emitted:                                 │
│    resources_write += ["route:/auth"]                            │
└─────────────────────────────────────────────────────────────────┘
```

### Adapter Protocol (Multi-Region Output)

```python
@dataclass
class GeneratedCode:
    """Multi-region output from adapter code generation."""
    imports: list[str] = field(default_factory=list)   # → AUTO:IMPORTS
    body: list[str] = field(default_factory=list)      # → action-specific region
    config: list[str] = field(default_factory=list)    # → AUTO:CONFIG (if any)


class FrameworkAdapter(Protocol):
    """Interface for framework-specific adapters."""
    
    @property
    def name(self) -> str:
        """Adapter identifier (e.g., 'fastapi-python', 'express-node')."""
        ...
    
    @property
    def supported_actions(self) -> set[str]:
        """Set of intent actions this adapter can handle."""
        ...
    
    def generate_code(self, action: str, intent: dict) -> GeneratedCode:
        """Generate multi-region code for the given intent.
        
        Returns:
            GeneratedCode with imports, body, and optional config.
        """
        ...
    
    def get_region_markers(self) -> dict[str, tuple[str, str]]:
        """Return region markers for each region type.
        
        Returns:
            Dict mapping region name to (start_marker, end_marker).
        """
        ...
    
    def get_anchor_patterns(self) -> dict[str, AnchorPattern]:
        """Return anchor patterns for auto-inserting region markers.
        
        Returns:
            Dict mapping region name to AnchorPattern.
        """
        ...
    
    def get_implied_resources(self, action: str, intent: dict) -> list[str]:
        """Return resources implied by an intent."""
        ...
    
    def detect_applicability(self, project_root: Path) -> float:
        """Return confidence (0-1) that this adapter applies to the project."""
        ...


@dataclass
class AnchorPattern:
    """Defines where to insert region markers in a file."""
    target_files: list[str]       # e.g., ["main.py", "src/main.py", "app.py"]
    anchor_regex: str             # Pattern to find insertion point
    position: str                 # "after" | "before"
    fallback: str                 # "serialize" | "error" | "end_of_file" | 
                                  # "start_of_file" | "end_of_imports"
```

### Built-in Adapters

| Adapter | Language | Framework | Supported Actions |
|---------|----------|-----------|-------------------|
| `fastapi-python` | Python | FastAPI | `add_router`, `add_middleware`, `add_dependency`, `add_config` |
| `express-node` | Node.js | Express | `add_router`, `add_middleware` |
| `nextjs-node` | Node.js | Next.js | `add_route`, `add_middleware`, `add_config` |
| `spring-java` | Java | Spring Boot | `add_controller`, `add_bean`, `add_config` |
| `generic` | Any | None | `add_import`, `append_to_list` (basic only) |

### Fallback Behavior

**If no adapter matches the project:**
1. Patch intents are **disabled**
2. Hot files revert to **file ownership serialization**
3. Tasks writing to the same hot file execute sequentially
4. Warning logged: "No adapter for project type. Hot file parallelism disabled."

### Region Markers + Anchor Patterns

**Region markers** define where generated code is inserted:

```python
# src/main.py (FastAPI example with region markers)

from fastapi import FastAPI

app = FastAPI()

# === AUTO:IMPORTS ===
from src.routes.auth import router as auth_router
from src.routes.users import router as users_router
# === END:IMPORTS ===

# === AUTO:MIDDLEWARE ===
app.add_middleware(CORSMiddleware, allow_origins=["*"])
# === END:MIDDLEWARE ===

# === AUTO:ROUTERS ===
app.include_router(auth_router, prefix="/auth", tags=["authentication"])
app.include_router(users_router, prefix="/users", tags=["users"])
# === END:ROUTERS ===
```

**Anchor patterns** define where to auto-insert markers if missing:

```python
class FastAPIPythonAdapter:
    
    def get_anchor_patterns(self) -> dict[str, AnchorPattern]:
        return {
            "imports": AnchorPattern(
                target_files=["main.py", "src/main.py", "app.py", "src/app.py"],
                anchor_regex=r"^from fastapi import|^import fastapi",
                position="after",
                fallback="end_of_imports"  # After last import statement
            ),
            "routers": AnchorPattern(
                target_files=["main.py", "src/main.py", "app.py", "src/app.py"],
                anchor_regex=r"app\s*=\s*FastAPI\(",
                position="after",
                fallback="serialize"  # If can't find FastAPI(), fall back
            ),
            "middleware": AnchorPattern(
                target_files=["main.py", "src/main.py", "app.py", "src/app.py"],
                anchor_regex=r"app\s*=\s*FastAPI\(",
                position="after",
                fallback="serialize"
            ),
            "dependencies": AnchorPattern(
                target_files=["dependencies.py", "src/dependencies.py", "deps.py"],
                anchor_regex=r"^from typing import|^import typing",
                position="after",
                fallback="start_of_file"
            ),
        }
```

### FastAPI Adapter Implementation (Multi-Region)

```python
class FastAPIPythonAdapter:
    """Adapter for FastAPI Python projects."""
    
    name = "fastapi-python"
    
    supported_actions = {
        "add_router",
        "add_middleware", 
        "add_dependency",
        "add_config",
    }
    
    def get_region_markers(self) -> dict[str, tuple[str, str]]:
        return {
            "imports": ("# === AUTO:IMPORTS ===", "# === END:IMPORTS ==="),
            "routers": ("# === AUTO:ROUTERS ===", "# === END:ROUTERS ==="),
            "middleware": ("# === AUTO:MIDDLEWARE ===", "# === END:MIDDLEWARE ==="),
            "dependencies": ("# === AUTO:DEPENDENCIES ===", "# === END:DEPENDENCIES ==="),
            "config": ("# === AUTO:CONFIG ===", "# === END:CONFIG ==="),
        }
    
    def generate_code(self, action: str, intent: dict) -> GeneratedCode:
        if action == "add_router":
            return self._generate_router(intent)
        elif action == "add_dependency":
            return self._generate_dependency(intent)
        elif action == "add_middleware":
            return self._generate_middleware(intent)
        else:
            raise ValueError(f"Unsupported action: {action}")
    
    def _generate_router(self, intent: dict) -> GeneratedCode:
        """Generate router registration with SEPARATE imports and body."""
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
            parts.append(f", dependencies=[{', '.join(deps)}]")
        parts.append(")")
        body_line = "".join(parts)
        
        return GeneratedCode(
            imports=[import_line],
            body=[body_line]
        )
    
    def _generate_dependency(self, intent: dict) -> GeneratedCode:
        """Generate DI function with SEPARATE imports and body."""
        func_name = intent["function_name"]
        return_type = intent["return_type"]
        import_from = intent["import_from"]
        import_name = intent["import_name"]
        is_async = intent.get("is_async", False)
        cache = intent.get("cache", False)
        
        # Import
        import_line = f"from {import_from} import {import_name}"
        
        # Function body
        body_lines = []
        if cache:
            body_lines.append("@lru_cache")
        
        async_prefix = "async " if is_async else ""
        body_lines.append(f"{async_prefix}def {func_name}() -> {return_type}:")
        body_lines.append(f"    return {import_name}()")
        
        return GeneratedCode(
            imports=[import_line],
            body=body_lines
        )
    
    def _generate_middleware(self, intent: dict) -> GeneratedCode:
        """Generate middleware registration."""
        cls = intent["middleware_class"]
        import_from = intent["import_from"]
        kwargs = intent.get("kwargs", {})
        
        import_line = f"from {import_from} import {cls}"
        
        kwargs_str = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
        body_line = f"app.add_middleware({cls}, {kwargs_str})"
        
        return GeneratedCode(
            imports=[import_line],
            body=[body_line]
        )
    
    def get_implied_resources(self, action: str, intent: dict) -> list[str]:
        """Return resources implied by this intent."""
        if action == "add_router":
            prefix = intent.get("prefix", "/")
            return [f"route:{prefix}"]
        elif action == "add_dependency":
            func_name = intent.get("function_name", "")
            return [f"di:{func_name}"]
        elif action == "add_middleware":
            cls = intent.get("middleware_class", "")
            return [f"middleware:{cls}"]
        return []
    
    def detect_applicability(self, project_root: Path) -> float:
        """Detect if this is a FastAPI project."""
        confidence = 0.0
        
        # Check explicit candidate paths (not glob, for predictability)
        candidate_paths = [
            project_root / "main.py",
            project_root / "app.py",
            project_root / "src" / "main.py",
            project_root / "src" / "app.py",
            project_root / "app" / "main.py",
        ]
        
        for path in candidate_paths:
            if path.exists():
                content = path.read_text()
                if "from fastapi import" in content or "import fastapi" in content:
                    confidence += 0.4
                if "FastAPI()" in content:
                    confidence += 0.3
        
        for req_file in ["pyproject.toml", "requirements.txt"]:
            path = project_root / req_file
            if path.exists() and "fastapi" in path.read_text().lower():
                confidence += 0.3
        
        return min(confidence, 1.0)
```

### Integrator Implementation (Multi-Region Routing)

```python
class Integrator:
    """Routes generated code to appropriate regions."""
    
    def __init__(self, adapter: FrameworkAdapter):
        self.adapter = adapter
        self.markers = adapter.get_region_markers()
    
    def apply_intents(self, file_path: str, intents: list[dict]) -> str:
        """Apply all intents, routing generated code to correct regions."""
        
        content = read_file(file_path)
        
        # Collect all generated code
        all_imports = []
        body_by_action = defaultdict(list)  # action -> lines
        
        for intent in intents:
            action = intent["action"]
            generated = self.adapter.generate_code(action, intent["intent"])
            
            # Collect imports (always go to imports region)
            all_imports.extend(generated.imports)
            
            # Collect body (goes to action-specific region)
            region = self._get_body_region(action)
            body_by_action[region].extend(generated.body)
        
        # Insert imports into imports region
        if all_imports:
            content = self._insert_into_region(
                content,
                self.markers["imports"][0],
                self.markers["imports"][1],
                all_imports
            )
        
        # Insert body lines into their respective regions
        for region, lines in body_by_action.items():
            if lines and region in self.markers:
                content = self._insert_into_region(
                    content,
                    self.markers[region][0],
                    self.markers[region][1],
                    lines
                )
        
        return content
    
    def _get_body_region(self, action: str) -> str:
        """Map action to body region name."""
        mapping = {
            "add_router": "routers",
            "add_middleware": "middleware",
            "add_dependency": "dependencies",
            "add_config": "config",
        }
        return mapping.get(action, action)
    
    def _insert_into_region(
        self,
        content: str,
        start_marker: str,
        end_marker: str,
        new_lines: list[str]
    ) -> str:
        """Insert lines into a marked region, deduplicating."""
        
        lines = content.split("\n")
        
        start_idx = None
        end_idx = None
        
        for i, line in enumerate(lines):
            if start_marker in line:
                start_idx = i
            elif end_marker in line:
                end_idx = i
                break
        
        if start_idx is None or end_idx is None:
            raise RegionNotFoundError(
                f"Region markers not found: {start_marker} ... {end_marker}"
            )
        
        existing_lines = lines[start_idx + 1:end_idx]
        existing_set = set(line.strip() for line in existing_lines if line.strip())
        
        lines_to_add = [
            line for line in new_lines
            if line.strip() and line.strip() not in existing_set
        ]
        
        result_lines = (
            lines[:end_idx] +
            lines_to_add +
            lines[end_idx:]
        )
        
        return "\n".join(result_lines)
    
    def ensure_region_markers(self, file_path: str, actions: list[str]) -> str:
        """Add missing region markers using anchor patterns."""
        
        content = read_file(file_path)
        anchors = self.adapter.get_anchor_patterns()
        
        # Determine which regions we need
        needed_regions = {"imports"}  # Always need imports
        for action in actions:
            region = self._get_body_region(action)
            needed_regions.add(region)
        
        for region in needed_regions:
            if region not in self.markers:
                continue
            
            start_marker, end_marker = self.markers[region]
            
            if start_marker in content:
                continue  # Already has markers
            
            if region not in anchors:
                log.warning(f"No anchor pattern for region '{region}', skipping")
                continue
            
            anchor = anchors[region]
            content = self._insert_markers_at_anchor(
                content, start_marker, end_marker, anchor
            )
        
        return content
    
    def _insert_markers_at_anchor(
        self,
        content: str,
        start_marker: str,
        end_marker: str,
        anchor: AnchorPattern
    ) -> str:
        """Insert region markers at the anchor location."""
        
        lines = content.split("\n")
        
        # Find anchor
        anchor_idx = None
        for i, line in enumerate(lines):
            if re.search(anchor.anchor_regex, line):
                anchor_idx = i
                if anchor.position == "after":
                    anchor_idx += 1
                break
        
        if anchor_idx is None:
            # Fallback behavior
            if anchor.fallback == "serialize":
                raise AnchorNotFoundError(
                    f"Anchor pattern not found: {anchor.anchor_regex}. "
                    f"Hot file will use serialization."
                )
            elif anchor.fallback == "end_of_file":
                anchor_idx = len(lines)
            elif anchor.fallback == "start_of_file":
                anchor_idx = 0
            elif anchor.fallback == "end_of_imports":
                # Find last import statement
                for i, line in enumerate(lines):
                    if line.startswith("import ") or line.startswith("from "):
                        anchor_idx = i + 1
                if anchor_idx is None:
                    anchor_idx = 0
        
        # Insert markers
        marker_block = [
            "",
            start_marker,
            end_marker,
            ""
        ]
        
        result_lines = lines[:anchor_idx] + marker_block + lines[anchor_idx:]
        return "\n".join(result_lines)
```

---

## Dependency Management

### Ecosystem-Specific Lockfile Policy

Dependencies are installed **once** at Stage 0.5, before any workers spawn. Each ecosystem uses its canonical lockfile mechanism.

| Ecosystem | Package Manager | Manifest | Lockfile |
|-----------|-----------------|----------|----------|
| Python | pip/uv/poetry | `requirements.txt` or `pyproject.toml` | `requirements.lock` or `uv.lock` or `poetry.lock` |
| Node.js | npm | `package.json` | `package-lock.json` |
| Node.js | pnpm | `package.json` | `pnpm-lock.yaml` |
| Node.js | yarn | `package.json` | `yarn.lock` |
| Go | go mod | `go.mod` | `go.sum` |
| Rust | cargo | `Cargo.toml` | `Cargo.lock` |
| Ruby | bundler | `Gemfile` | `Gemfile.lock` |
| .NET | nuget | `*.csproj` | `packages.lock.json` |

### Environment Hash Tracking

```python
def setup_environment(tasks: list[dict], config: dict) -> EnvironmentResult:
    """Install dependencies and record env_hash."""
    
    # ... collect and install deps ...
    
    # Compute hash from lockfile
    lockfile = eco_config["lockfile"]
    env_hash = hashlib.sha256(
        Path(lockfile).read_bytes()
    ).hexdigest()[:8]
    
    return EnvironmentResult(
        success=True,
        env_hash=env_hash,  # Workers must use this
        ecosystem=ecosystem,
        packages_installed=count
    )
```

---

## State Machine & Contract Renegotiation

*(Unchanged from ARCHITECTURE_6.md)*

---

## Configuration

### Project-Level Config (.claude-agents.yaml)

```yaml
# .claude-agents.yaml

orchestration:
  planner_model: "opus"
  supervisor_model: "sonnet"
  worker_model: "sonnet"
  verifier_model: "sonnet"
  max_parallel_workers: 5
  max_iterations: 3
  merge_strategy: "merge_bubble"
  worktree_dir: ".worktrees"

# Risk-based approval
approval:
  auto_approve_threshold: 25
  
  sensitive_patterns:
    - pattern: "auth|security|crypto"
      weight: 20
    - pattern: "payment|billing"
      weight: 25
    - pattern: "prod|deploy"
      weight: 30
    - pattern: "migration|schema"
      weight: 15
  
  always_require_human:
    - "**/.env*"
    - "**/migrations/**"
    - "**/secrets/**"

# Verification
verification:
  require_executable_checks: true
  min_checks_per_task: 1
  
  # Template resolution for {modified_files}, {modified_tests}
  template_resolution:
    test_file_patterns:
      - "tests/test_{basename}.py"
      - "tests/{basename}_test.py"
      - "**/*_test.py"
    fallback_on_no_match: "tests/"  # Run all tests if can't map

# Boundary enforcement
boundaries:
  enforce_via_git_diff: true
  
  # Churn detection
  reject_excessive_churn: true
  churn_threshold_lines: 500
  
  # Format-only detection (only for whitespace-insensitive types)
  reject_formatting_churn: true
  formatting_check_allowlist:
    - ".js"
    - ".ts"
    - ".jsx"
    - ".tsx"
    - ".json"
    - ".css"
    - ".html"
    - ".java"
    - ".go"
    - ".rs"
  formatting_check_denylist:
    - ".py"      # Indentation-sensitive
    - ".yaml"
    - ".yml"
    - ".mk"
    - "Makefile"
  
  # Forbidden patterns (static, always blocked)
  forbidden_patterns:
    - "node_modules/"
    - "__pycache__/"
    - "vendor/"
    - "dist/"
    - "build/"
    - "\\.generated\\."
    - "\\.min\\.(js|css)$"
  
  # Lockfiles are derived from dependencies.ecosystems config
  # (pnpm-lock.yaml, package-lock.json, uv.lock, etc.)
  # Workers cannot modify any lockfile; only Supervisor can.

# Framework adapter
patch_intents:
  enabled: true
  adapter: "auto"  # auto | fastapi-python | express-node | none
  
  hot_files:
    - path: "src/main.py"
      actions: ["add_router", "add_middleware"]
    - path: "src/dependencies.py"
      actions: ["add_dependency"]
  
  fallback: "serialize"
  
  region_markers:
    auto_insert: true
    style: "comment"

# Resource conflict detection
resources:
  # Enable resource-level conflict detection
  enabled: true
  # Intents auto-emit implied resources
  auto_emit_from_intents: true

# Dependencies
dependencies:
  install_phase: "stage_0.5"
  detect_conflicts_early: true
  allow_worker_installs: false
  
  # Environment hash verification
  verify_env_hash: true
  
  ecosystems:
    python:
      manager: "uv"
      manifest: "pyproject.toml"
      lockfile: "uv.lock"
    node:
      manager: "pnpm"
      manifest: "package.json"
      lockfile: "pnpm-lock.yaml"

# Contract management
contracts:
  version_enforcement: true
  max_renegotiations: 2
  track_renegotiations: true

# Quality gates
quality:
  verifier_checks:
    - "pytest {modified_tests}"
    - "ruff check {modified_files}"
    - "mypy {modified_files}"
  
  post_merge_checks:
    - "pytest"
    - "ruff check ."

# Phase barriers
phases:
  stabilization_gate: true
  
  barrier_checks:
    - name: "tests"
      command: "pytest"
      required: true
    - name: "lint"
      command: "ruff check ."
      required: true
```

---

## Anti-Patterns to Avoid

### 1. Tasks Without Executable Verification

```yaml
# BAD
tasks:
  - id: task-a
    verification: []  # ❌ REJECTED

# GOOD
tasks:
  - id: task-a
    verification:
      - command: "pytest tests/test_auth.py"
        type: "test"
        required: true
```

### 2. Resource Conflicts Without Dependencies

```yaml
# BAD: Both tasks register same route, no ordering
tasks:
  - id: task-a
    resources_write: ["route:/auth"]
    depends_on: []
  - id: task-b
    resources_write: ["route:/auth"]  # Conflict!
    depends_on: []

# GOOD: Explicit ordering
tasks:
  - id: task-a
    resources_write: ["route:/auth"]
    depends_on: []
  - id: task-b
    resources_write: ["route:/auth/v2"]  # Different resource
    depends_on: [task-a]                  # Or same resource with dependency
```

### 3. Missing Region Markers for Hot Files

```python
# BAD: No markers, Integrator can't insert safely
app = FastAPI()

# GOOD: Markers present
app = FastAPI()

# === AUTO:ROUTERS ===
# === END:ROUTERS ===
```

### 4. Drive-By Refactoring

```yaml
# BAD: Excessive changes without justification
tasks:
  - id: task-a
    files_write: [src/auth.py]
    # Worker changes 800 lines → rejected

# GOOD: Explicit acknowledgment
tasks:
  - id: task-refactor
    files_write: [src/auth.py]
    allow_large_changes: true
```

### 5. Environment Hash Mismatch

```json
// BAD: Worker used different environment
{
  "task_id": "task-a",
  "environment": {
    "hash": "deadbeef"  // ≠ global state hash
  }
}
// Verifier rejects: "Environment mismatch"
```

### 6. Format-Only Changes to Indentation-Sensitive Files

```python
# BAD: Worker only reformatted Python file
# Verifier catches this for .js/.ts but NOT .py (whitespace is semantic)

# The allowlist prevents false positives on Python/YAML/Makefile
```

---

## Summary

This architecture enables:

1. **Safe Parallelism** — Git worktrees provide physical isolation
2. **Intelligent Scheduling** — DAG-based execution on files AND resources
3. **No Merge Conflicts** — File ownership + resource ownership + structured intents
4. **Semantic Safety** — Interface contracts prevent API mismatches
5. **Separation of Concerns** — Verifier (mechanical) vs Planner-Architect (judgment)
6. **Multi-Region Code Generation** — Adapters produce imports/body separately
7. **Anchor-Based Marker Insertion** — Defined placement policy per adapter
8. **Environment Consistency** — env_hash verification prevents "works on my worktree"
9. **Safe Format Detection** — Allowlist-based, respects indentation-sensitive languages
10. **Verified Templates** — {modified_tests} resolution is defined, not magic
11. **Risk-Based Approval** — Explicit scoring function
12. **Framework Agnostic** — Core protocol + optional adapters
13. **Ecosystem-Aware Dependencies** — Canonical lockfiles per ecosystem
14. **Human Oversight** — Approval gates and escalation paths

The system transforms complex multi-file features into coordinated parallel execution with deterministic, conflict-free merging.
