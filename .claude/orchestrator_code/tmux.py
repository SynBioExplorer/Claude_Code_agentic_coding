#!/usr/bin/env python3
"""
Tmux session management for headless orchestration.

Provides utilities for creating worker sessions and waiting for signal files.

Usage:
    python3 ~/.claude/orchestrator_code/tmux.py create-session <session-name> [--cwd <dir>]
    python3 ~/.claude/orchestrator_code/tmux.py wait-signal <signal-file> [--timeout 600]
"""

import os
import subprocess
import time
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
        # Kill existing session if it exists
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


def main():
    import argparse
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


if __name__ == "__main__":
    main()
