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
from datetime import datetime
from pathlib import Path


def wait_for_signal_file(signal_file: str, timeout: int = 600) -> bool:
    """Wait for a signal file to appear.
    
    Args:
        signal_file: Path to the signal file to wait for
        timeout: Maximum seconds to wait (default: 600 = 10 minutes)
        
    Returns:
        True if signal file appeared, False if timeout
    """
    start_time = time.time()
    while not os.path.exists(signal_file):
        if time.time() - start_time > timeout:
            return False
        time.sleep(1)
    return True


def create_worker_session(session_name: str, cwd: str = None) -> dict:
    """Create a tmux session for a worker with proper shell initialization.
    
    This ensures conda and claude commands are available on macOS by
    sourcing shell profile files.
    
    Args:
        session_name: Name for the tmux session
        cwd: Working directory for the session (optional)
        
    Returns:
        dict with success status and any error message
    """
    try:
        # Kill existing session if it exists (handles orphaned sessions)
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True, check=False
        )
        
        # Create new detached session
        create_cmd = ["tmux", "new-session", "-d", "-s", session_name]
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
            ["tmux", "send-keys", "-t", session_name, init_cmd, "Enter"],
            capture_output=True, check=False
        )
        
        # Small delay to let shell initialization complete
        time.sleep(0.5)
        
        return {"success": True, "session": session_name}
        
    except Exception as e:
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


def verify_process_running(session_name: str, wait_seconds: int = 5) -> dict:
    """Verify that a process is actually running in the tmux session.
    
    Captures pane output and checks for signs of activity or failure.
    
    Args:
        session_name: Target tmux session
        wait_seconds: Seconds to wait before checking (let process start)
        
    Returns:
        dict with running status, output sample, and any detected errors
    """
    time.sleep(wait_seconds)
    
    if not check_session_exists(session_name):
        return {"running": False, "error": "Session does not exist"}
    
    # Capture recent output
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


def cleanup_signals() -> dict:
    """Remove all old signal files to ensure clean slate.
    
    Returns:
        dict with count of removed files
    """
    signals_dir = Path(".orchestrator/signals")
    if not signals_dir.exists():
        return {"removed": 0}
    
    removed = 0
    for f in signals_dir.glob("*.done"):
        f.unlink()
        removed += 1
    for f in signals_dir.glob("*.verified"):
        f.unlink()
        removed += 1
    
    return {"removed": removed}


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
    session_name = f"worker-{task_id}"
    
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
    
    # Verify the process is actually running
    if verify_startup:
        verify_result = verify_process_running(session_name, wait_seconds=5)
        if not verify_result["running"]:
            return {
                "success": False,
                "error": verify_result.get("error", "Process failed to start"),
                "output_sample": verify_result.get("output_sample", "")
            }
    
    return {"success": True, "session": session_name}


def monitor_with_timeout(
    task_id: str,
    signal_file: str,
    timeout: int = 1800,
    check_interval: int = 30
) -> dict:
    """Monitor a task with timeout, killing if it exceeds max duration.
    
    Args:
        task_id: Task identifier
        signal_file: Signal file to wait for
        timeout: Maximum seconds to wait (default 30 minutes)
        check_interval: Seconds between checks
        
    Returns:
        dict with completion status and timing info
    """
    session_name = f"worker-{task_id}"
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        
        # Check if signal file appeared
        if os.path.exists(signal_file):
            return {
                "completed": True,
                "timeout": False,
                "elapsed_seconds": int(elapsed)
            }
        
        # Check timeout
        if elapsed > timeout:
            # Save logs before killing
            save_session_logs(session_name)
            
            # Kill the session
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
    verify_parser.add_argument("--wait", type=int, default=5, help="Seconds to wait before checking")
    
    # save-logs command
    logs_parser = subparsers.add_parser("save-logs", help="Save session logs to file")
    logs_parser.add_argument("session_name", help="Session name")
    logs_parser.add_argument("--output", help="Output file path")
    
    # cleanup-signals command
    subparsers.add_parser("cleanup-signals", help="Remove old signal files")
    
    # cleanup-orphans command
    orphans_parser = subparsers.add_parser("cleanup-orphans", help="Kill orphaned worker sessions")
    orphans_parser.add_argument("--no-save-logs", action="store_true", help="Don't save logs before killing")
    
    # spawn-worker command
    spawn_parser = subparsers.add_parser("spawn-worker", help="Spawn worker with prompt file")
    spawn_parser.add_argument("task_id", help="Task ID")
    spawn_parser.add_argument("--prompt-file", required=True, help="Path to prompt file")
    spawn_parser.add_argument("--cwd", required=True, help="Working directory")
    spawn_parser.add_argument("--no-verify", action="store_true", help="Skip startup verification")
    
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
        result = verify_process_running(args.session_name, args.wait)
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
        result = cleanup_signals()
        print(f"✓ Removed {result['removed']} signal files")
        
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

