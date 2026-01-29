#!/usr/bin/env python3
"""
Live workers output view using tmux capture-pane.

This avoids the tmux attach crash on macOS with conda's tmux.
Shows live output from all worker-* tmux sessions.
"""

import subprocess
import sys
import time
import os

# Try to import rich for nice formatting, fall back to plain text
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def get_worker_sessions():
    """Get list of worker tmux sessions or windows.

    Detects both:
    - Individual sessions: worker-task-a, worker-task-b, etc.
    - Multi-window sessions: phase5-workers with multiple windows
    """
    try:
        workers = []

        # First, look for individual worker-* sessions
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            sessions = result.stdout.strip().split("\n")
            workers.extend([s for s in sessions if s.startswith("worker-")])

        # Also check for multi-window sessions (e.g., phase5-workers)
        # and list their windows as separate "workers"
        result = subprocess.run(
            ["tmux", "list-windows", "-a", "-F", "#{session_name}:#{window_index}:#{window_name}"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 3:
                    session = parts[0]
                    window_idx = parts[1]
                    window_name = parts[2]
                    # Include windows from worker-related sessions
                    if "worker" in session.lower() or "phase" in session.lower():
                        target = f"{session}:{window_idx}"
                        if target not in workers:
                            workers.append(target)

        return workers if workers else []
    except Exception:
        return []


def capture_pane(target: str, lines: int = 20) -> str:
    """Capture recent output from a tmux session or window.

    Args:
        target: Either "session_name" or "session_name:window_index"
    """
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", target, "-p", "-S", f"-{lines}"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # Clean up and get last N lines
            output = result.stdout.strip()
            output_lines = output.split("\n")
            return "\n".join(output_lines[-lines:])
        return f"[Target not found: {target}]"
    except Exception as e:
        return f"[Error: {e}]"


def run_rich_view():
    """Run the view using rich library."""
    console = Console()

    def make_layout():
        sessions = get_worker_sessions()
        if not sessions:
            return Panel("[dim]No active worker sessions[/dim]", title="Workers")

        layout = Layout()

        # Create panels for each worker
        panels = []
        for session in sessions[:6]:  # Max 6 workers displayed
            task_id = session.replace("worker-", "")
            output = capture_pane(session, lines=15)
            panel = Panel(
                Text(output, style="white"),
                title=f"[cyan]{task_id}[/cyan]",
                border_style="blue"
            )
            panels.append(panel)

        # Arrange in grid
        if len(panels) == 1:
            return panels[0]
        elif len(panels) == 2:
            layout.split_row(Layout(panels[0]), Layout(panels[1]))
        elif len(panels) <= 4:
            layout.split_column(
                Layout(name="top"),
                Layout(name="bottom")
            )
            layout["top"].split_row(*[Layout(p) for p in panels[:2]])
            if len(panels) > 2:
                layout["bottom"].split_row(*[Layout(p) for p in panels[2:4]])
            else:
                layout["bottom"].visible = False
        else:
            layout.split_column(
                Layout(name="top"),
                Layout(name="middle"),
                Layout(name="bottom")
            )
            layout["top"].split_row(*[Layout(p) for p in panels[:2]])
            layout["middle"].split_row(*[Layout(p) for p in panels[2:4]])
            layout["bottom"].split_row(*[Layout(p) for p in panels[4:6]])

        return layout

    console.print("[bold cyan]WORKERS VIEW[/bold cyan] (Ctrl+C to exit)\n")

    try:
        with Live(make_layout(), console=console, refresh_per_second=1) as live:
            while True:
                time.sleep(1)
                live.update(make_layout())
    except KeyboardInterrupt:
        console.print("\n[dim]Exiting...[/dim]")


def run_plain_view():
    """Run simple plain text view."""
    print("WORKERS VIEW (Ctrl+C to exit)")
    print("=" * 60)

    try:
        while True:
            os.system('clear' if os.name != 'nt' else 'cls')
            print("WORKERS VIEW (Ctrl+C to exit)")
            print("=" * 60)

            sessions = get_worker_sessions()
            if not sessions:
                print("\n[No active worker sessions]")
            else:
                for session in sessions:
                    task_id = session.replace("worker-", "")
                    print(f"\n--- {task_id} ---")
                    output = capture_pane(session, lines=10)
                    print(output)
                    print()

            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")


def main():
    print("Starting workers view...")

    # Check if tmux is available
    sessions = get_worker_sessions()
    print(f"Found {len(sessions)} worker sessions")

    if RICH_AVAILABLE:
        run_rich_view()
    else:
        run_plain_view()


if __name__ == "__main__":
    main()
