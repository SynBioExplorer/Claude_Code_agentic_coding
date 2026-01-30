#!/usr/bin/env python3
"""
Tmux session management for headless orchestration.

Provides utilities for creating worker sessions, waiting for signal files,
verifying process health, timeout handling, and log persistence.

Usage:
    python3 ~/.claude/orchestrator_code/tmux.py create-session <session-name> [--cwd <dir>]
    python3 ~/.claude/orchestrator_code/tmux.py wait-signal <signal-file> [--timeout 600]
    python3 ~/.claude/orchestrator_code/tmux.py verify-running <session-name>
    python3 ~/.claude/orchestrator_code/tmux.py save-logs <session-name> [--output <file>]
    python3 ~/.claude/orchestrator_code/tmux.py cleanup-signals
    python3 ~/.claude/orchestrator_code/tmux.py cleanup-orphans
    python3 ~/.claude/orchestrator_code/tmux.py spawn-worker <task-id> --prompt-file <file> --cwd <dir>
"""

import os
import subprocess
import time
import shutil
import uuid
from datetime import datetime
from pathlib import Path


# Constants for atomic operations
SIGNAL_SUFFIX_TMP = ".tmp"
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_STALE_THRESHOLD = 90  # seconds - consider worker hung if no heartbeat for this long


def create_signal_file(signal_file: str, content: str = "") -> bool:
    """Create a signal file atomically using write-tmp-then-rename pattern.

    This prevents TOCTOU races where a file appears to exist but is incomplete
    or where cleanup removes it during creation.

    Args:
        signal_file: Path to the signal file to create
        content: Optional content to write (default empty)

    Returns:
        True if created successfully, False otherwise
    """
    signal_path = Path(signal_file)
    tmp_path = signal_path.with_suffix(signal_path.suffix + SIGNAL_SUFFIX_TMP)

    try:
        # Ensure parent directory exists
        signal_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first
        tmp_path.write_text(content or datetime.now().isoformat())

        # Atomic rename (on POSIX systems, rename is atomic within same filesystem)
        tmp_path.rename(signal_path)
        return True
    except Exception as e:
        # Clean up temp file if it exists
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return False


def wait_for_signal_file(signal_file: str, timeout: int = 600, poll_interval: float = 0.5) -> bool:
    """Wait for a signal file to appear with atomic read verification.

    Uses faster polling (0.5s instead of 1s) and verifies file is fully written
    by checking it's not a .tmp file and has content.

    Args:
        signal_file: Path to the signal file to wait for
        timeout: Maximum seconds to wait (default: 600 = 10 minutes)
        poll_interval: Seconds between checks (default: 0.5)

    Returns:
        True if signal file appeared and is valid, False if timeout
    """
    start_time = time.time()
    signal_path = Path(signal_file)

    while True:
        if time.time() - start_time > timeout:
            return False

        # Check if signal file exists (not the .tmp version)
        if signal_path.exists() and not signal_path.with_suffix(signal_path.suffix + SIGNAL_SUFFIX_TMP).exists():
            # Verify the file has content (fully written)
            try:
                content = signal_path.read_text()
                if content:  # Non-empty = valid signal
                    return True
            except Exception:
                pass  # File might be in transition, keep waiting

        time.sleep(poll_interval)


def create_worker_session(
    session_name: str,
    cwd: str = None,
    verify_claude: bool = True,
    init_timeout: float = 5.0
) -> dict:
    """Create a tmux session for a worker with proper shell initialization.

    This ensures conda and claude commands are available on macOS by
    sourcing shell profile files. Includes verification that claude is available.

    Args:
        session_name: Name for the tmux session
        cwd: Working directory for the session (optional)
        verify_claude: Whether to verify 'claude' command is available (default True)
        init_timeout: Seconds to wait for shell initialization (default 5.0)

    Returns:
        dict with success status and any error message
    """
    try:
        # Generate unique session suffix to avoid race with duplicate names
        unique_session = f"{session_name}-{uuid.uuid4().hex[:6]}"

        # Create new detached session with unique name first
        create_cmd = ["tmux", "new-session", "-d", "-s", unique_session]
        if cwd:
            create_cmd.extend(["-c", cwd])

        result = subprocess.run(create_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {"success": False, "error": f"Failed to create session: {result.stderr}"}

        # Source shell profile to ensure conda/claude are available
        # This is critical for macOS where PATH isn't set in non-interactive shells
        # NOTE: Many .zshrc files have `[[ $- != *i* ]] && return` which exits early
        # in non-interactive shells. We explicitly source conda first to avoid this.
        init_cmd = (
            "source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || "
            "source ~/anaconda3/etc/profile.d/conda.sh 2>/dev/null || "
            "source /opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh 2>/dev/null || "
            "source ~/.zshrc 2>/dev/null || "
            "source ~/.bash_profile 2>/dev/null || "
            "true"
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", unique_session, init_cmd, "Enter"],
            capture_output=True, check=False
        )

        # Wait for shell initialization (increased from 0.5s to configurable, default 5s)
        # This is critical for conda activation which can take 1-3 seconds on cold start
        time.sleep(init_timeout)

        # Verify claude command is available if requested
        if verify_claude:
            # Use 'which claude' to verify command is in PATH
            verify_cmd = "which claude > /dev/null 2>&1 && echo 'CLAUDE_OK' || echo 'CLAUDE_NOT_FOUND'"
            subprocess.run(
                ["tmux", "send-keys", "-t", unique_session, verify_cmd, "Enter"],
                capture_output=True, check=False
            )
            time.sleep(0.5)

            # Capture pane output to check result
            capture_result = subprocess.run(
                ["tmux", "capture-pane", "-t", unique_session, "-p", "-S", "-5"],
                capture_output=True, text=True, timeout=5
            )
            output = capture_result.stdout if capture_result.returncode == 0 else ""

            if "CLAUDE_NOT_FOUND" in output:
                # Clean up the session we created
                subprocess.run(
                    ["tmux", "kill-session", "-t", unique_session],
                    capture_output=True, check=False
                )
                return {
                    "success": False,
                    "error": "claude command not found in PATH after shell initialization. "
                             "Ensure claude is installed and PATH is correctly set in shell profile."
                }

        # Now that we've verified the session works, kill any old session with the target name
        # and rename our session to the target name
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True, check=False
        )

        # Rename our uniquely-named session to the requested name
        subprocess.run(
            ["tmux", "rename-session", "-t", unique_session, session_name],
            capture_output=True, check=False
        )

        return {"success": True, "session": session_name}

    except Exception as e:
        # Try to clean up on error
        try:
            subprocess.run(
                ["tmux", "kill-session", "-t", unique_session],
                capture_output=True, check=False
            )
        except Exception:
            pass
        return {"success": False, "error": str(e)}


def send_command(session_name: str, command: str) -> dict:
    """Send a command to a tmux session.
    
    Args:
        session_name: Target tmux session
        command: Command to execute
        
    Returns:
        dict with success status
    """
    try:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", session_name, command, "Enter"],
            capture_output=True, text=True
        )
        return {"success": result.returncode == 0}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_session_exists(session_name: str) -> bool:
    """Check if a tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True
    )
    return result.returncode == 0


def verify_process_running(
    session_name: str,
    wait_seconds: int = 10,
    early_exit_on_failure: bool = True
) -> dict:
    """Verify that a process is actually running in the tmux session.

    Captures pane output and checks for signs of activity or failure.
    Increased default wait from 5s to 10s to handle larger model initialization.

    Args:
        session_name: Target tmux session
        wait_seconds: Seconds to wait before checking (default 10, increased from 5)
        early_exit_on_failure: If True, check for failures during wait period

    Returns:
        dict with running status, output sample, and any detected errors
    """
    # Early failure detection during wait period
    if early_exit_on_failure:
        check_interval = 1.0
        elapsed = 0.0

        while elapsed < wait_seconds:
            if not check_session_exists(session_name):
                return {"running": False, "error": "Session does not exist"}

            # Quick check for early failures
            try:
                result = subprocess.run(
                    ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-20"],
                    capture_output=True, text=True, timeout=5
                )
                output = result.stdout if result.returncode == 0 else ""

                # Check for critical failures that warrant early exit
                critical_failures = [
                    "command not found",
                    "No such file or directory",
                    "Permission denied",
                    "CLAUDE_NOT_FOUND",
                    "ModuleNotFoundError",
                    "segmentation fault",
                    "killed",
                    "OOM",
                ]

                for failure in critical_failures:
                    if failure.lower() in output.lower():
                        return {
                            "running": False,
                            "error": f"Early failure detected: {failure}",
                            "output_sample": output[-500:] if len(output) > 500 else output,
                            "elapsed_before_failure": elapsed
                        }
            except Exception:
                pass

            time.sleep(check_interval)
            elapsed += check_interval
    else:
        time.sleep(wait_seconds)

    if not check_session_exists(session_name):
        return {"running": False, "error": "Session does not exist"}

    # Capture recent output for final check
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-50"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout if result.returncode == 0 else ""
    except Exception as e:
        return {"running": False, "error": f"Failed to capture pane: {e}"}

    # Check for common failure indicators
    failure_indicators = [
        "command not found",
        "error:",
        "Error:",
        "ERROR",
        "authentication failed",
        "rate limit",
        "Permission denied",
        "No such file or directory",
        "ModuleNotFoundError",
        "ImportError",
    ]

    detected_errors = []
    for indicator in failure_indicators:
        if indicator.lower() in output.lower():
            detected_errors.append(indicator)

    # Check if shell prompt is back (process exited quickly)
    # Common prompts: $, %, >, or username@hostname patterns
    lines = output.strip().split('\n')
    last_lines = lines[-3:] if len(lines) >= 3 else lines

    prompt_patterns = ["$ ", "% ", "> ", "❯ "]
    shell_returned = any(
        any(p in line for p in prompt_patterns)
        for line in last_lines
    )

    if detected_errors:
        return {
            "running": False,
            "error": f"Detected errors: {', '.join(detected_errors)}",
            "output_sample": output[-500:] if len(output) > 500 else output
        }

    if shell_returned and "claude" not in output.lower():
        return {
            "running": False,
            "error": "Process appears to have exited (shell prompt returned)",
            "output_sample": output[-500:] if len(output) > 500 else output
        }

    return {
        "running": True,
        "output_sample": output[-500:] if len(output) > 500 else output
    }


def capture_session_logs(session_name: str, lines: int = 1000) -> str:
    """Capture logs from a tmux session.
    
    Args:
        session_name: Target tmux session
        lines: Number of lines to capture (default 1000)
        
    Returns:
        Captured log content
    """
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p", "-S", f"-{lines}"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def save_session_logs(session_name: str, output_file: str = None) -> dict:
    """Save session logs to a file before cleanup.
    
    Args:
        session_name: Target tmux session
        output_file: Output file path (default: .orchestrator/logs/{session_name}_{timestamp}.log)
        
    Returns:
        dict with success status and file path
    """
    logs = capture_session_logs(session_name)
    
    if not logs:
        return {"success": False, "error": "No logs captured"}
    
    # Create logs directory
    logs_dir = Path(".orchestrator/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = logs_dir / f"{session_name}_{timestamp}.log"
    else:
        output_file = Path(output_file)
    
    try:
        output_file.write_text(logs)
        return {"success": True, "file": str(output_file), "lines": len(logs.split('\n'))}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_worker_sessions() -> list:
    """List all worker tmux sessions."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return []
        sessions = result.stdout.strip().split('\n')
        return [s for s in sessions if s.startswith('worker-')]
    except Exception:
        return []


def ensure_signals_dir() -> Path:
    """Ensure the signals directory exists."""
    signals_dir = Path(".orchestrator/signals")
    signals_dir.mkdir(parents=True, exist_ok=True)
    return signals_dir


def cleanup_signals(orchestration_id: str = None, max_age_hours: float = 2.0) -> dict:
    """Remove old signal files while protecting current orchestration's signals.

    Only removes signals that are:
    1. Not from the current orchestration (if orchestration_id provided)
    2. Older than max_age_hours (default 2 hours)

    This prevents the race condition where cleanup removes a signal file
    that a worker just created.

    Args:
        orchestration_id: Current orchestration ID to protect (optional)
        max_age_hours: Only remove files older than this (default 2.0)

    Returns:
        dict with count of removed files and protected files
    """
    signals_dir = Path(".orchestrator/signals")
    if not signals_dir.exists():
        return {"removed": 0, "protected": 0}

    removed = 0
    protected = 0
    cutoff_time = time.time() - (max_age_hours * 3600)

    for pattern in ["*.done", "*.verified", "*.heartbeat"]:
        for f in signals_dir.glob(pattern):
            try:
                # Check file age
                file_mtime = f.stat().st_mtime
                if file_mtime > cutoff_time:
                    # File is recent, check if it belongs to current orchestration
                    if orchestration_id:
                        content = f.read_text()
                        if orchestration_id in content:
                            protected += 1
                            continue
                    else:
                        # No orchestration_id provided, protect all recent files
                        protected += 1
                        continue

                # Old file or not from current orchestration - safe to remove
                f.unlink()
                removed += 1
            except Exception:
                pass  # File might have been removed by another process

    # Also clean up any orphaned .tmp files
    for f in signals_dir.glob("*.tmp"):
        try:
            if f.stat().st_mtime < cutoff_time:
                f.unlink()
                removed += 1
        except Exception:
            pass

    return {"removed": removed, "protected": protected}


def cleanup_orphaned_sessions(save_logs: bool = True) -> dict:
    """Kill all orphaned worker sessions, optionally saving logs first.
    
    Args:
        save_logs: Whether to save logs before killing (default True)
        
    Returns:
        dict with list of cleaned sessions and saved log files
    """
    sessions = list_worker_sessions()
    cleaned = []
    logs_saved = []
    
    for session in sessions:
        # Save logs first if requested
        if save_logs:
            result = save_session_logs(session)
            if result["success"]:
                logs_saved.append(result["file"])
        
        # Kill the session
        subprocess.run(
            ["tmux", "kill-session", "-t", session],
            capture_output=True, check=False
        )
        cleaned.append(session)
    
    return {"cleaned": cleaned, "logs_saved": logs_saved}


def spawn_worker_with_prompt_file(
    task_id: str,
    prompt_file: str,
    cwd: str,
    verify_startup: bool = True
) -> dict:
    """Spawn a worker using a prompt file instead of inline command.

    This avoids shell escaping issues with complex prompts.

    Args:
        task_id: Task identifier
        prompt_file: Path to file containing the prompt
        cwd: Working directory (worktree path)
        verify_startup: Whether to verify the process started (default True)

    Returns:
        dict with success status and verification results
    """
    return spawn_agent(f"worker-{task_id}", prompt_file, cwd, verify_startup)


def spawn_agent(
    session_name: str,
    prompt_file: str,
    cwd: str,
    verify_startup: bool = True
) -> dict:
    """Spawn any agent type using a prompt file.

    Generic function for spawning workers, verifiers, integration-checkers, etc.
    All agents are spawned with --dangerously-skip-permissions for headless execution.

    Args:
        session_name: Tmux session name (e.g., "worker-task-a", "verifier-task-a")
        prompt_file: Path to file containing the prompt
        cwd: Working directory for the agent
        verify_startup: Whether to verify the process started (default True)

    Returns:
        dict with success status and verification results
    """
    # Create the session
    result = create_worker_session(session_name, cwd)
    if not result["success"]:
        return result

    # Verify prompt file exists
    if not Path(prompt_file).exists():
        return {"success": False, "error": f"Prompt file not found: {prompt_file}"}

    # Send command using file-based prompt (avoids escaping issues)
    cmd = f'claude --dangerously-skip-permissions --permission-mode bypassPermissions -p "$(cat {prompt_file})"'
    send_result = send_command(session_name, cmd)

    if not send_result.get("success"):
        return {"success": False, "error": "Failed to send command to session"}

    # Verify the process is actually running (use new default of 10s with early exit)
    if verify_startup:
        verify_result = verify_process_running(session_name, wait_seconds=10, early_exit_on_failure=True)
        if not verify_result["running"]:
            return {
                "success": False,
                "error": verify_result.get("error", "Process failed to start"),
                "output_sample": verify_result.get("output_sample", "")
            }

    return {"success": True, "session": session_name}


def check_heartbeat(task_id: str, stale_threshold: float = HEARTBEAT_STALE_THRESHOLD) -> dict:
    """Check if a worker's heartbeat is fresh.

    Workers should write to .orchestrator/signals/<task-id>.heartbeat every 30 seconds.

    Args:
        task_id: Task identifier
        stale_threshold: Seconds after which heartbeat is considered stale (default 90)

    Returns:
        dict with heartbeat status
    """
    heartbeat_file = Path(f".orchestrator/signals/{task_id}.heartbeat")

    if not heartbeat_file.exists():
        return {"has_heartbeat": False, "stale": True, "reason": "No heartbeat file"}

    try:
        mtime = heartbeat_file.stat().st_mtime
        age = time.time() - mtime
        is_stale = age > stale_threshold

        return {
            "has_heartbeat": True,
            "stale": is_stale,
            "age_seconds": int(age),
            "last_update": datetime.fromtimestamp(mtime).isoformat()
        }
    except Exception as e:
        return {"has_heartbeat": False, "stale": True, "reason": str(e)}


def update_heartbeat(task_id: str) -> bool:
    """Update the heartbeat file for a task.

    Called by workers periodically to indicate they're still alive.

    Args:
        task_id: Task identifier

    Returns:
        True if updated successfully
    """
    return create_signal_file(
        f".orchestrator/signals/{task_id}.heartbeat",
        content=datetime.now().isoformat()
    )


def monitor_with_timeout(
    task_id: str,
    signal_file: str,
    timeout: int = 1800,
    check_interval: int = 30,
    heartbeat_timeout: int = 300
) -> dict:
    """Monitor a task with timeout and heartbeat checking.

    Now includes heartbeat monitoring: if no heartbeat for heartbeat_timeout seconds,
    the task is considered hung and killed early rather than waiting for full timeout.

    Args:
        task_id: Task identifier
        signal_file: Signal file to wait for
        timeout: Maximum seconds to wait (default 30 minutes)
        check_interval: Seconds between checks (default 30)
        heartbeat_timeout: Kill task if no heartbeat for this long (default 5 minutes)

    Returns:
        dict with completion status and timing info
    """
    session_name = f"worker-{task_id}"
    start_time = time.time()
    last_heartbeat_check = 0

    while True:
        elapsed = time.time() - start_time

        # Check if signal file appeared (use atomic verification)
        signal_path = Path(signal_file)
        if signal_path.exists():
            try:
                content = signal_path.read_text()
                if content:  # Non-empty = valid signal
                    return {
                        "completed": True,
                        "timeout": False,
                        "elapsed_seconds": int(elapsed)
                    }
            except Exception:
                pass

        # Check heartbeat (faster detection of hung workers)
        if elapsed > 60:  # Only check heartbeat after 1 minute (give worker time to start)
            heartbeat = check_heartbeat(task_id, stale_threshold=heartbeat_timeout)
            if heartbeat["has_heartbeat"] and heartbeat["stale"]:
                # Worker has stopped sending heartbeats - likely hung
                save_session_logs(session_name)

                subprocess.run(
                    ["tmux", "kill-session", "-t", session_name],
                    capture_output=True, check=False
                )

                return {
                    "completed": False,
                    "timeout": False,
                    "hung": True,
                    "elapsed_seconds": int(elapsed),
                    "error": f"Worker appears hung (no heartbeat for {heartbeat['age_seconds']}s)"
                }

        # Check overall timeout
        if elapsed > timeout:
            save_session_logs(session_name)

            subprocess.run(
                ["tmux", "kill-session", "-t", session_name],
                capture_output=True, check=False
            )

            return {
                "completed": False,
                "timeout": True,
                "elapsed_seconds": int(elapsed),
                "error": f"Task exceeded timeout of {timeout} seconds"
            }

        # Check if session still exists (might have crashed)
        if not check_session_exists(session_name):
            return {
                "completed": False,
                "timeout": False,
                "elapsed_seconds": int(elapsed),
                "error": "Session terminated unexpectedly"
            }

        time.sleep(check_interval)


def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Tmux session management")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # create-session command
    create_parser = subparsers.add_parser("create-session", help="Create a worker session")
    create_parser.add_argument("session_name", help="Session name")
    create_parser.add_argument("--cwd", help="Working directory")
    
    # wait-signal command
    wait_parser = subparsers.add_parser("wait-signal", help="Wait for a signal file")
    wait_parser.add_argument("signal_file", help="Path to signal file")
    wait_parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds")
    
    # list command
    subparsers.add_parser("list", help="List worker sessions")
    
    # verify-running command
    verify_parser = subparsers.add_parser("verify-running", help="Verify process is running in session")
    verify_parser.add_argument("session_name", help="Session name")
    verify_parser.add_argument("--wait", type=int, default=10, help="Seconds to wait before checking (default 10)")
    verify_parser.add_argument("--no-early-exit", action="store_true", help="Disable early exit on failure detection")
    
    # save-logs command
    logs_parser = subparsers.add_parser("save-logs", help="Save session logs to file")
    logs_parser.add_argument("session_name", help="Session name")
    logs_parser.add_argument("--output", help="Output file path")
    
    # cleanup-signals command
    cleanup_sig_parser = subparsers.add_parser("cleanup-signals", help="Remove old signal files")
    cleanup_sig_parser.add_argument("--orchestration-id", help="Protect signals from this orchestration")
    cleanup_sig_parser.add_argument("--max-age-hours", type=float, default=2.0, help="Only remove files older than this")

    # heartbeat commands
    hb_check_parser = subparsers.add_parser("check-heartbeat", help="Check worker heartbeat status")
    hb_check_parser.add_argument("task_id", help="Task ID")
    hb_check_parser.add_argument("--threshold", type=int, default=90, help="Stale threshold in seconds")

    hb_update_parser = subparsers.add_parser("update-heartbeat", help="Update worker heartbeat")
    hb_update_parser.add_argument("task_id", help="Task ID")

    # create-signal command (atomic signal file creation)
    sig_parser = subparsers.add_parser("create-signal", help="Create signal file atomically")
    sig_parser.add_argument("signal_file", help="Path to signal file")
    sig_parser.add_argument("--content", help="Optional content to write")
    
    # cleanup-orphans command
    orphans_parser = subparsers.add_parser("cleanup-orphans", help="Kill orphaned worker sessions")
    orphans_parser.add_argument("--no-save-logs", action="store_true", help="Don't save logs before killing")
    
    # spawn-worker command
    spawn_parser = subparsers.add_parser("spawn-worker", help="Spawn worker with prompt file")
    spawn_parser.add_argument("task_id", help="Task ID")
    spawn_parser.add_argument("--prompt-file", required=True, help="Path to prompt file")
    spawn_parser.add_argument("--cwd", required=True, help="Working directory")
    spawn_parser.add_argument("--no-verify", action="store_true", help="Skip startup verification")

    # spawn-agent command (generic - for verifier, integration-checker, reviewer, etc.)
    agent_parser = subparsers.add_parser("spawn-agent", help="Spawn any agent type with prompt file")
    agent_parser.add_argument("session_name", help="Tmux session name (e.g., verifier-task-a)")
    agent_parser.add_argument("--prompt-file", required=True, help="Path to prompt file")
    agent_parser.add_argument("--cwd", required=True, help="Working directory")
    agent_parser.add_argument("--no-verify", action="store_true", help="Skip startup verification")
    
    # monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor task with timeout")
    monitor_parser.add_argument("task_id", help="Task ID")
    monitor_parser.add_argument("--signal-file", required=True, help="Signal file to wait for")
    monitor_parser.add_argument("--timeout", type=int, default=1800, help="Timeout in seconds")
    
    args = parser.parse_args()
    
    if args.command == "create-session":
        result = create_worker_session(args.session_name, args.cwd)
        if result["success"]:
            print(f"✓ Created session: {result['session']}")
        else:
            print(f"✗ Failed: {result['error']}")
            exit(1)
            
    elif args.command == "wait-signal":
        print(f"Waiting for signal: {args.signal_file} (timeout: {args.timeout}s)")
        if wait_for_signal_file(args.signal_file, args.timeout):
            print(f"✓ Signal received: {args.signal_file}")
        else:
            print(f"✗ Timeout waiting for: {args.signal_file}")
            exit(1)
            
    elif args.command == "list":
        sessions = list_worker_sessions()
        if sessions:
            print("Worker sessions:")
            for s in sessions:
                print(f"  - {s}")
        else:
            print("No worker sessions found")
            
    elif args.command == "verify-running":
        result = verify_process_running(
            args.session_name,
            wait_seconds=args.wait,
            early_exit_on_failure=not args.no_early_exit
        )
        print(json.dumps(result, indent=2))
        if not result["running"]:
            exit(1)
            
    elif args.command == "save-logs":
        result = save_session_logs(args.session_name, args.output)
        if result["success"]:
            print(f"✓ Saved {result['lines']} lines to: {result['file']}")
        else:
            print(f"✗ Failed: {result['error']}")
            exit(1)
            
    elif args.command == "cleanup-signals":
        result = cleanup_signals(
            orchestration_id=args.orchestration_id,
            max_age_hours=args.max_age_hours
        )
        print(f"✓ Removed {result['removed']} signal files, protected {result['protected']}")

    elif args.command == "check-heartbeat":
        result = check_heartbeat(args.task_id, stale_threshold=args.threshold)
        print(json.dumps(result, indent=2))
        if result.get("stale"):
            exit(1)

    elif args.command == "update-heartbeat":
        if update_heartbeat(args.task_id):
            print(f"✓ Updated heartbeat for {args.task_id}")
        else:
            print(f"✗ Failed to update heartbeat for {args.task_id}")
            exit(1)

    elif args.command == "create-signal":
        if create_signal_file(args.signal_file, content=args.content or ""):
            print(f"✓ Created signal file: {args.signal_file}")
        else:
            print(f"✗ Failed to create signal file: {args.signal_file}")
            exit(1)
        
    elif args.command == "cleanup-orphans":
        result = cleanup_orphaned_sessions(save_logs=not args.no_save_logs)
        if result["cleaned"]:
            print(f"✓ Cleaned {len(result['cleaned'])} sessions: {result['cleaned']}")
            if result["logs_saved"]:
                print(f"  Logs saved: {result['logs_saved']}")
        else:
            print("No orphaned sessions found")
            
    elif args.command == "spawn-worker":
        result = spawn_worker_with_prompt_file(
            args.task_id,
            args.prompt_file,
            args.cwd,
            verify_startup=not args.no_verify
        )
        if result["success"]:
            print(f"✓ Spawned worker: {result['session']}")
        else:
            print(f"✗ Failed: {result['error']}")
            if "output_sample" in result:
                print(f"Output:\n{result['output_sample']}")
            exit(1)

    elif args.command == "spawn-agent":
        result = spawn_agent(
            args.session_name,
            args.prompt_file,
            args.cwd,
            verify_startup=not args.no_verify
        )
        if result["success"]:
            print(f"✓ Spawned agent: {result['session']}")
        else:
            print(f"✗ Failed: {result['error']}")
            if "output_sample" in result:
                print(f"Output:\n{result['output_sample']}")
            exit(1)
            
    elif args.command == "monitor":
        print(f"Monitoring task {args.task_id} (timeout: {args.timeout}s)")
        result = monitor_with_timeout(
            args.task_id,
            args.signal_file,
            args.timeout
        )
        print(json.dumps(result, indent=2))
        if not result["completed"]:
            exit(1)


if __name__ == "__main__":
    main()

