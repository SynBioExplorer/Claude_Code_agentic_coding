#!/usr/bin/env python3
"""
Monitoring window manager for orchestration.

Opens Terminal/iTerm windows for dashboard and workers view.

The approach: Instead of creating tmux sessions first and then opening Terminal
windows to attach, we open Terminal windows that CREATE the tmux sessions.
This ensures the sessions are owned by the Terminal process and stay alive.
"""

import subprocess
import sys
import os
import time
import shutil
import shlex

def get_terminal_app():
    """Detect which terminal app to use."""
    # Check if iTerm is installed
    if os.path.exists("/Applications/iTerm.app"):
        return "iTerm"
    return "Terminal"


def ensure_tmux_server():
    """Ensure tmux server is running, clean up stale socket if needed."""
    # Check if tmux server is alive
    result = subprocess.run(
        ["tmux", "list-sessions"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return True  # Server is running

    # Server not running - check for stale socket
    uid = os.getuid()
    socket_dir = f"/private/tmp/tmux-{uid}"
    socket_path = os.path.join(socket_dir, "default")

    if os.path.exists(socket_path):
        # Socket exists but server is dead - remove it
        try:
            os.remove(socket_path)
            print(f"  Cleaned up stale tmux socket")
        except OSError as e:
            print(f"  Warning: Could not remove stale socket: {e}", file=sys.stderr)

    return True

def open_terminal_with_command(command: str, app: str = None):
    """Open a new terminal window that runs a command."""
    if app is None:
        app = get_terminal_app()

    # Escape for AppleScript double-quoted strings:
    # 1. Backslashes must be doubled: \ -> \\
    # 2. Double quotes must be escaped: " -> \"
    escaped_cmd = command.replace("\\", "\\\\").replace('"', '\\"')

    if app == "iTerm":
        script = f'''
        tell application "iTerm"
            create window with default profile
            tell current session of current window
                write text "{escaped_cmd}"
            end tell
        end tell
        '''
    else:
        # Terminal.app - use do script which runs in a new window
        script = f'''
        tell application "Terminal"
            do script "{escaped_cmd}"
            activate
        end tell
        '''

    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to open {app} window: {e.stderr.decode()}", file=sys.stderr)
        return False

def open_monitoring_windows(project_dir: str = None):
    """
    Set up and open all monitoring windows.

    Opens 2 Terminal windows:
    1. Dashboard - runs the live dashboard directly
    2. Workers - placeholder that will show worker output

    The Terminal windows own the processes, so they stay alive.
    """
    if project_dir is None:
        project_dir = os.getcwd()

    print("Opening monitoring windows...")
    app = get_terminal_app()
    print(f"  Using: {app}")

    # Clean up stale tmux socket if needed
    ensure_tmux_server()

    # Use shlex.quote for proper shell escaping of paths with special characters
    quoted_dir = shlex.quote(project_dir)

    # Dashboard window - run dashboard directly (no tmux needed for this)
    dashboard_cmd = f"cd {quoted_dir} && echo '=== ORCHESTRATION DASHBOARD ===' && python3 ~/.claude/orchestrator_code/dashboard.py"
    if open_terminal_with_command(dashboard_cmd, app):
        print("  Opened Dashboard window")
    else:
        print("  FAILED to open Dashboard window")

    # Workers window - use live capture view instead of tmux attach
    # (tmux attach crashes with conda's tmux on macOS)
    # This uses watch + capture-pane to show live output without attaching
    workers_cmd = f"cd {quoted_dir} && source /opt/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/anaconda3/etc/profile.d/conda.sh 2>/dev/null || true; python3 ~/.claude/orchestrator_code/workers_view.py"
    if open_terminal_with_command(workers_cmd, app):
        print("  Opened Workers window (live capture view)")
    else:
        print("  FAILED to open Workers window")

    print("\nMonitoring windows opened!")
    print(f"  Dashboard: Live status table")
    print(f"  Workers:   Live capture view (no tmux attach)")


def setup_worker_panes(task_ids: list):
    """
    Set up split panes in the workers tmux session to show each worker.

    Call this AFTER spawning worker tmux sessions (worker-<task-id>).
    """
    workers_session = "orchestrator-workers"

    # Check if workers session exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", workers_session],
        capture_output=True
    )
    if result.returncode != 0:
        print(f"Workers session not found. Open monitoring first.", file=sys.stderr)
        return False

    for i, task_id in enumerate(task_ids):
        worker_session = f"worker-{task_id}"

        if i == 0:
            # First pane - use existing pane, kill any placeholder
            subprocess.run(["tmux", "send-keys", "-t", workers_session, "C-c"], capture_output=True)
            time.sleep(0.1)
        else:
            # Split for additional workers
            split_flag = "-h" if i % 2 == 1 else "-v"
            subprocess.run([
                "tmux", "split-window", "-t", workers_session, split_flag
            ], capture_output=True)

        # Show live output from this worker
        watch_cmd = f"watch -n1 'tmux capture-pane -t {worker_session} -p -S -30 2>/dev/null || echo \"[{task_id}] waiting...\"'"
        subprocess.run([
            "tmux", "send-keys", "-t", workers_session, watch_cmd, "Enter"
        ], capture_output=True)

    # Rebalance all panes
    subprocess.run([
        "tmux", "select-layout", "-t", workers_session, "tiled"
    ], capture_output=True)

    print(f"Set up {len(task_ids)} worker panes")
    return True

def add_worker_pane(task_id: str):
    """Add a pane to the workers window for a new worker."""
    workers_session = "orchestrator-workers"
    worker_session = f"worker-{task_id}"

    # Check if workers session exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", workers_session],
        capture_output=True
    )
    if result.returncode != 0:
        print(f"Workers session '{workers_session}' not found. Open monitoring windows first.")
        return False

    # Count existing panes
    result = subprocess.run(
        ["tmux", "list-panes", "-t", workers_session, "-F", "#{pane_index}"],
        capture_output=True, text=True
    )
    pane_count = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0

    if pane_count == 1:
        # First worker - kill any placeholder command and use existing pane
        subprocess.run(["tmux", "send-keys", "-t", workers_session, "C-c"], capture_output=True)
        time.sleep(0.2)
    else:
        # Split for new worker - alternate horizontal/vertical for tiled layout
        split_flag = "-h" if pane_count % 2 == 1 else "-v"
        subprocess.run([
            "tmux", "split-window", "-t", workers_session, split_flag
        ], capture_output=True)

    # Show live output from worker session
    watch_cmd = f"watch -n1 'tmux capture-pane -t {worker_session} -p -S -30 2>/dev/null || echo \"[{task_id}] waiting/completed\"'"
    subprocess.run([
        "tmux", "send-keys", "-t", workers_session, watch_cmd, "Enter"
    ], capture_output=True)

    # Rebalance panes to tile layout
    subprocess.run([
        "tmux", "select-layout", "-t", workers_session, "tiled"
    ], capture_output=True)

    print(f"Added worker pane for {task_id}")
    return True

def close_monitoring():
    """Close monitoring sessions."""
    # Kill the workers tmux session
    result = subprocess.run(["tmux", "kill-session", "-t", "orchestrator-workers"], capture_output=True)
    if result.returncode == 0:
        print("Closed orchestrator-workers tmux session")
    else:
        print("orchestrator-workers session not found (may already be closed)")

    # Note: Dashboard runs directly in Terminal, user closes that window manually
    print("Note: Close the Dashboard Terminal window manually if still open")


def status():
    """Show status of monitoring components."""
    # Check workers tmux session
    result = subprocess.run(
        ["tmux", "has-session", "-t", "orchestrator-workers"],
        capture_output=True
    )
    workers_status = "running" if result.returncode == 0 else "not running"
    print(f"orchestrator-workers (tmux): {workers_status}")

    # Dashboard runs in Terminal directly, can't easily check
    print("dashboard: runs in Terminal window (check manually)")

    # List any worker sessions
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        sessions = result.stdout.strip().split('\n')
        worker_sessions = [s for s in sessions if s.startswith('worker-')]
        if worker_sessions:
            print(f"\nActive worker sessions ({len(worker_sessions)}):")
            for s in worker_sessions:
                print(f"  - {s}")
        else:
            print("\nNo active worker sessions")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manage orchestration monitoring windows")
    parser.add_argument("command", choices=["open", "add-worker", "setup-panes", "close", "status"],
                       help="Command to run")
    parser.add_argument("--project-dir", "-d", help="Project directory (default: current dir)")
    parser.add_argument("--task-id", "-t", help="Task ID (for add-worker)")
    parser.add_argument("--task-ids", nargs="+", help="Multiple task IDs (for setup-panes)")

    args = parser.parse_args()

    if args.command == "open":
        open_monitoring_windows(args.project_dir)
    elif args.command == "add-worker":
        if not args.task_id:
            print("Error: --task-id required for add-worker", file=sys.stderr)
            sys.exit(1)
        add_worker_pane(args.task_id)
    elif args.command == "setup-panes":
        if not args.task_ids:
            print("Error: --task-ids required for setup-panes", file=sys.stderr)
            sys.exit(1)
        setup_worker_panes(args.task_ids)
    elif args.command == "close":
        close_monitoring()
    elif args.command == "status":
        status()

if __name__ == "__main__":
    main()
