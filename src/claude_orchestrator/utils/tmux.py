"""tmux session management for worker coordination."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from claude_orchestrator.utils.git import CommandResult, run_command


@dataclass
class TmuxSession:
    """Information about a tmux session."""

    name: str
    windows: int = 1
    attached: bool = False
    created_at: str = ""


def is_tmux_available() -> bool:
    """Check if tmux is available on the system.

    Returns:
        True if tmux is installed and accessible
    """
    result = run_command("which tmux")
    return result.returncode == 0


def create_session(
    session_name: str,
    working_dir: str | Path | None = None,
    command: str | None = None,
) -> CommandResult:
    """Create a new tmux session.

    Args:
        session_name: Name for the session
        working_dir: Working directory for the session
        command: Initial command to run (optional)

    Returns:
        CommandResult from tmux new-session
    """
    cmd_parts = ["tmux", "new-session", "-d", "-s", session_name]

    if working_dir:
        cmd_parts.extend(["-c", str(working_dir)])

    if command:
        cmd_parts.append(command)

    return run_command(" ".join(cmd_parts))


def kill_session(session_name: str) -> CommandResult:
    """Kill a tmux session.

    Args:
        session_name: Name of session to kill

    Returns:
        CommandResult from tmux kill-session
    """
    return run_command(f"tmux kill-session -t {session_name}")


def session_exists(session_name: str) -> bool:
    """Check if a tmux session exists.

    Args:
        session_name: Name of session to check

    Returns:
        True if session exists
    """
    result = run_command(f"tmux has-session -t {session_name} 2>/dev/null")
    return result.returncode == 0


def list_sessions() -> list[TmuxSession]:
    """List all tmux sessions.

    Returns:
        List of TmuxSession objects
    """
    result = run_command('tmux list-sessions -F "#{session_name}:#{session_windows}:#{session_attached}"')

    if result.returncode != 0:
        return []

    sessions: list[TmuxSession] = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(":")
        if len(parts) >= 3:
            sessions.append(
                TmuxSession(
                    name=parts[0],
                    windows=int(parts[1]) if parts[1].isdigit() else 1,
                    attached=parts[2] == "1",
                )
            )

    return sessions


def send_keys(session_name: str, keys: str, enter: bool = True) -> CommandResult:
    """Send keys to a tmux session.

    Args:
        session_name: Target session
        keys: Keys/command to send
        enter: Whether to send Enter key after

    Returns:
        CommandResult from tmux send-keys
    """
    # Escape special characters
    escaped = keys.replace('"', '\\"').replace("$", "\\$")
    cmd = f'tmux send-keys -t {session_name} "{escaped}"'

    if enter:
        cmd += " Enter"

    return run_command(cmd)


def capture_output(
    session_name: str,
    lines: int = 100,
    start_line: int | None = None,
) -> str:
    """Capture output from a tmux session.

    Args:
        session_name: Target session
        lines: Number of lines to capture
        start_line: Starting line (negative for from end)

    Returns:
        Captured output text
    """
    cmd = f"tmux capture-pane -t {session_name} -p"

    if start_line is not None:
        cmd += f" -S {start_line}"

    cmd += f" | tail -n {lines}"

    result = run_command(cmd)
    return result.stdout if result.returncode == 0 else ""


def wait_for_prompt(
    session_name: str,
    prompt_pattern: str = r"\$",
    timeout: int = 60,
    poll_interval: float = 0.5,
) -> bool:
    """Wait for a prompt to appear in a tmux session.

    Args:
        session_name: Target session
        prompt_pattern: Regex pattern for the prompt
        timeout: Timeout in seconds
        poll_interval: Time between checks

    Returns:
        True if prompt appeared, False if timeout
    """
    import re
    import time

    start = time.time()

    while time.time() - start < timeout:
        output = capture_output(session_name, lines=5)
        if re.search(prompt_pattern, output):
            return True
        time.sleep(poll_interval)

    return False


def run_in_session(
    session_name: str,
    command: str,
    wait_for_completion: bool = True,
    timeout: int = 300,
) -> tuple[bool, str]:
    """Run a command in a tmux session and optionally wait for completion.

    Args:
        session_name: Target session
        command: Command to run
        wait_for_completion: Whether to wait for command to finish
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, output)
    """
    # Send the command
    result = send_keys(session_name, command)
    if result.returncode != 0:
        return False, f"Failed to send command: {result.stderr}"

    if not wait_for_completion:
        return True, ""

    # Wait for prompt to return
    if wait_for_prompt(session_name, timeout=timeout):
        output = capture_output(session_name, lines=50)
        return True, output

    return False, "Command timed out"


def create_worker_session(
    task_id: str,
    worktree_path: str | Path,
    env_vars: dict[str, str] | None = None,
) -> CommandResult:
    """Create a tmux session for a worker agent.

    Args:
        task_id: Task identifier (used as session name)
        worktree_path: Path to the worktree
        env_vars: Environment variables to set

    Returns:
        CommandResult from session creation
    """
    session_name = f"worker-{task_id}"

    # Create session in worktree directory
    result = create_session(session_name, working_dir=worktree_path)

    if result.returncode != 0:
        return result

    # Set environment variables if provided
    if env_vars:
        for key, value in env_vars.items():
            send_keys(session_name, f"export {key}={value}")

    return result


def cleanup_worker_sessions() -> list[str]:
    """Clean up all worker tmux sessions.

    Returns:
        List of session names that were cleaned up
    """
    cleaned: list[str] = []

    for session in list_sessions():
        if session.name.startswith("worker-"):
            result = kill_session(session.name)
            if result.returncode == 0:
                cleaned.append(session.name)

    return cleaned
