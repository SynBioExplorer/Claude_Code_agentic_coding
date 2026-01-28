#!/usr/bin/env python3
"""
Live terminal dashboard for orchestration monitoring.

Usage:
    python3 ~/.claude/orchestrator_code/dashboard.py
    python3 ~/.claude/orchestrator_code/dashboard.py --refresh 2
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich import box
except ImportError:
    print("Dashboard requires 'rich' library. Install with:")
    print("  pip install rich")
    sys.exit(1)


console = Console()

STATUS_ICONS = {
    "pending": ("○", "dim"),
    "executing": ("●", "yellow"),
    "running": ("●", "yellow"),
    "in_progress": ("●", "yellow"),
    "completed": ("✓", "green"),
    "done": ("✓", "green"),
    "verified": ("✓", "green"),
    "merged": ("✓", "cyan"),
    "failed": ("✗", "red"),
    "error": ("✗", "red"),
}


def get_tmux_sessions() -> dict:
    """Get active tmux worker sessions."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True
        )
        sessions = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return {s.replace("worker-", ""): True for s in sessions if s.startswith("worker-")}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}


def get_tmux_pane_content(session_name: str, lines: int = 100) -> str:
    """Capture recent output from a tmux session.

    Uses -e flag to capture escape sequences (for status line) and
    captures more lines to ensure we get the current status area.
    """
    try:
        # Try to capture the visible pane content including status area
        # -p prints to stdout, -S -100 captures last 100 lines
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p", "-S", f"-{lines}"],
            capture_output=True, text=True
        )
        content = result.stdout if result.returncode == 0 else ""

        # Also try to capture the last visible line (often has status info)
        if not content.strip():
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p"],
                capture_output=True, text=True
            )
            content = result.stdout if result.returncode == 0 else ""

        return content
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def parse_context_usage(pane_content: str) -> tuple:
    """Parse context window usage from Claude CLI output.

    Returns (used, total, percentage) or (None, None, None) if not found.
    """
    import re

    # Claude Code shows context in various formats in the status line:
    # - "45.2k / 200k" or "45.2k/200k"
    # - "Context: 12.5k / 200k"
    # - Unicode characters like "◐ 45.2k/200k"
    # - Progress indicators
    # - "12500 / 200000 tokens"

    patterns = [
        # Pattern: "45.2k / 200k" or "45.2k/200k" with optional k suffix
        r'(\d+(?:\.\d+)?)\s*k?\s*/\s*(\d+(?:\.\d+)?)\s*k',
        # Pattern with explicit 'k' on both sides
        r'(\d+(?:\.\d+)?)k\s*/\s*(\d+(?:\.\d+)?)k',
        # Pattern: raw numbers like "45200 / 200000"
        r'(\d{4,})\s*/\s*(\d{4,})',
        # Pattern: "Context: ..." prefix
        r'[Cc]ontext[:\s]+(\d+(?:\.\d+)?k?)\s*/\s*(\d+(?:\.\d+)?k?)',
        # Pattern with tokens label
        r'(\d+(?:\.\d+)?k?)\s*(?:tokens?\s*)?/\s*(\d+(?:\.\d+)?k?)\s*(?:tokens?)?',
        # Pattern: percentage with total like "50% of 200k"
        r'(\d+)%\s*(?:of\s*)?(\d+(?:\.\d+)?k)',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, pane_content)
        if matches:
            # Take the last match (most recent)
            match = matches[-1]
            used_str, total_str = match[0], match[1]

            def parse_k(s):
                s = str(s).lower().strip()
                if s.endswith('k'):
                    return float(s[:-1]) * 1000
                val = float(s)
                # If it's a small number but we expect tokens, might be 'k' implied
                # Numbers over 100 are likely raw token counts
                return val

            try:
                used = parse_k(used_str)
                total = parse_k(total_str)

                # Handle percentage pattern
                if '%' in pattern:
                    pct = float(used_str)
                    used = total * pct / 100
                else:
                    pct = (used / total * 100) if total > 0 else 0

                # Sanity check: total should be reasonable (1k to 500k range)
                if 1000 <= total <= 500000:
                    return used, total, pct
            except (ValueError, ZeroDivisionError):
                continue

    return None, None, None


def format_context(used, total, pct) -> Text:
    """Format context usage with color coding."""
    if used is None:
        return Text("-", style="dim")

    # Format as "45k/200k (23%)"
    def fmt(n):
        if n >= 1000:
            return f"{n/1000:.1f}k"
        return str(int(n))

    # Color based on usage percentage
    if pct >= 80:
        color = "red"
    elif pct >= 60:
        color = "yellow"
    else:
        color = "green"

    text = Text()
    text.append(f"{fmt(used)}", style=color)
    text.append(f"/{fmt(total)}", style="dim")
    text.append(f" ({pct:.0f}%)", style=color)
    return text


def get_session_context(task_id: str) -> tuple:
    """Get context usage for a worker session."""
    session_name = f"worker-{task_id}"
    content = get_tmux_pane_content(session_name)
    if content:
        return parse_context_usage(content)
    return None, None, None


def load_orchestration_state() -> dict:
    """Load main orchestration state."""
    state_file = Path(".orchestration-state.json")
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except json.JSONDecodeError:
            # File might be partially written, return empty
            return {}
    return {}


def load_task_status(task_id: str) -> dict:
    """Load individual task status from worktree."""
    status_file = Path(f".worktrees/{task_id}/.task-status.json")
    if status_file.exists():
        try:
            return json.loads(status_file.read_text())
        except json.JSONDecodeError:
            # File might be partially written, return empty
            return {}
    return {}


def get_elapsed_time(state: dict) -> str:
    """Calculate elapsed time from start."""
    started = state.get("started_at")
    if not started:
        return "not started"

    try:
        start_time = datetime.fromisoformat(started.replace("Z", "+00:00"))
        elapsed = datetime.now(start_time.tzinfo) - start_time
        minutes, seconds = divmod(int(elapsed.total_seconds()), 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    except (ValueError, TypeError):
        return "unknown"


def get_progress_text(task_status: dict) -> str:
    """Get progress description from task status."""
    if not task_status:
        return "Waiting..."

    progress = task_status.get("progress", {})
    status = task_status.get("status", "pending")

    if status == "failed":
        return task_status.get("error", "Failed")[:30]

    if status == "completed":
        return task_status.get("summary", "Done")[:30]

    # Show what's been done
    files_created = len(progress.get("files_created", []))
    files_modified = len(progress.get("files_modified", []))
    tests_written = len(progress.get("tests_written", []))

    parts = []
    if files_created:
        parts.append(f"{files_created} created")
    if files_modified:
        parts.append(f"{files_modified} modified")
    if tests_written:
        parts.append(f"{tests_written} tests")

    return ", ".join(parts) if parts else "Working..."


def build_dashboard() -> Panel:
    """Build the dashboard display."""
    state = load_orchestration_state()
    tmux_sessions = get_tmux_sessions()

    # Header info
    request = state.get("request", "No active orchestration")[:60]
    elapsed = get_elapsed_time(state)
    phase = state.get("phase", "idle")
    iteration = state.get("iteration", 0)

    # Build task table
    table = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold")
    table.add_column("Task", style="cyan", width=16)
    table.add_column("Status", width=10)
    table.add_column("Agent", width=12)
    table.add_column("Progress", style="dim")

    tasks = state.get("tasks", {})

    counts = {"active": 0, "verified": 0, "failed": 0, "pending": 0}

    for task_id, task_info in tasks.items():
        status = task_info.get("status", "pending")
        task_status = load_task_status(task_id)

        # Override with live status from worktree if available
        if task_status:
            status = task_status.get("status", status)

        # Determine agent
        is_tmux_active = task_id in tmux_sessions
        if is_tmux_active:
            agent = "worker"
            status = "executing"
        elif status in ("verified", "merged"):
            agent = "verifier"
        elif status == "pending":
            agent = "-"
        else:
            agent = "worker"

        # Count stats
        if status in ("executing", "running", "in_progress"):
            counts["active"] += 1
        elif status in ("verified", "merged", "completed", "done"):
            counts["verified"] += 1
        elif status == "failed":
            counts["failed"] += 1
        else:
            counts["pending"] += 1

        # Status icon
        icon, color = STATUS_ICONS.get(status, ("?", "white"))
        status_text = Text(f"{icon} {status}", style=color)

        # Progress
        progress = get_progress_text(task_status)

        table.add_row(task_id[:16], status_text, agent, progress[:35])

    # If no tasks, show placeholder
    if not tasks:
        table.add_row("-", Text("○ idle", style="dim"), "-", "No tasks")

    # Summary line
    summary = Text()
    summary.append(f"Workers: {counts['active']} active", style="yellow" if counts['active'] else "dim")
    summary.append("  │  ")
    summary.append(f"Verified: {counts['verified']}", style="green" if counts['verified'] else "dim")
    summary.append("  │  ")
    summary.append(f"Failed: {counts['failed']}", style="red" if counts['failed'] else "dim")
    summary.append("  │  ")
    summary.append(f"Pending: {counts['pending']}", style="dim")

    # Build header
    header = Text()
    header.append("ORCHESTRATION STATUS", style="bold white")
    header.append(f"          phase: ", style="dim")
    header.append(phase, style="cyan")
    header.append(f"  │  elapsed: ", style="dim")
    header.append(elapsed, style="white")
    if iteration > 0:
        header.append(f"  │  iteration: ", style="dim")
        header.append(f"{iteration}/3", style="yellow")

    # Combine into panel
    content = Text()
    content.append("\n")
    content.append("Request: ", style="dim")
    content.append(request, style="white")
    content.append("\n\n")

    # Create layout
    layout = Layout()
    layout.split_column(
        Layout(Panel(header, box=box.SIMPLE), size=3),
        Layout(Panel(Text(f"Request: {request}"), box=box.SIMPLE), size=3),
        Layout(table),
        Layout(Panel(summary, box=box.SIMPLE), size=3),
    )

    return Panel(
        layout,
        title="[bold cyan]Claude Orchestrator[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
    )


def build_simple_dashboard() -> Table:
    """Build a simpler dashboard that works better with Live."""
    state = load_orchestration_state()
    tmux_sessions = get_tmux_sessions()

    # Main table
    table = Table(
        title="[bold cyan]ORCHESTRATION STATUS[/bold cyan]",
        box=box.ROUNDED,
        expand=True,
        show_header=True,
        header_style="bold",
        border_style="cyan",
    )

    table.add_column("Task", style="cyan", width=16)
    table.add_column("Status", width=12)
    table.add_column("Agent", width=8)
    table.add_column("Context", width=16)
    table.add_column("Progress")

    # Get info
    request = state.get("request", "No active orchestration")[:50]
    elapsed = get_elapsed_time(state)
    phase = state.get("phase", "idle")
    tasks = state.get("tasks", {})

    counts = {"active": 0, "verified": 0, "failed": 0, "pending": 0}
    total_context_used = 0
    total_context_max = 0

    if not tasks:
        table.add_row("-", Text("○ idle", style="dim"), "-", Text("-", style="dim"), "No active orchestration")
    else:
        for task_id, task_info in tasks.items():
            status = task_info.get("status", "pending")
            task_status = load_task_status(task_id)

            if task_status:
                status = task_status.get("status", status)

            is_tmux_active = task_id in tmux_sessions
            if is_tmux_active:
                agent = "worker"
                status = "executing"
            elif status in ("verified", "merged"):
                agent = "done"
            elif status == "pending":
                agent = "-"
            else:
                agent = "worker"

            if status in ("executing", "running", "in_progress"):
                counts["active"] += 1
            elif status in ("verified", "merged", "completed", "done"):
                counts["verified"] += 1
            elif status == "failed":
                counts["failed"] += 1
            else:
                counts["pending"] += 1

            icon, color = STATUS_ICONS.get(status, ("?", "white"))
            status_text = Text(f"{icon} {status}", style=color)
            progress = get_progress_text(task_status)

            # Get context usage for active workers
            if is_tmux_active:
                used, total, pct = get_session_context(task_id)
                context_text = format_context(used, total, pct)
                if used and total:
                    total_context_used += used
                    total_context_max += total
            else:
                context_text = Text("-", style="dim")

            table.add_row(task_id[:16], status_text, agent, context_text, progress[:35])

    # Caption with summary
    def fmt_k(n):
        if n >= 1000:
            return f"{n/1000:.1f}k"
        return str(int(n))

    context_summary = ""
    if total_context_max > 0:
        total_pct = total_context_used / total_context_max * 100
        ctx_color = "red" if total_pct >= 80 else ("yellow" if total_pct >= 60 else "green")
        context_summary = f"  │  [{ctx_color}]Ctx: {fmt_k(total_context_used)}/{fmt_k(total_context_max)}[/{ctx_color}]"

    table.caption = (
        f"[dim]Request:[/dim] {request}\n"
        f"[dim]Phase:[/dim] [cyan]{phase}[/cyan]  │  "
        f"[dim]Elapsed:[/dim] {elapsed}  │  "
        f"[yellow]Active: {counts['active']}[/yellow]  │  "
        f"[green]Done: {counts['verified']}[/green]  │  "
        f"[red]Failed: {counts['failed']}[/red]"
        f"{context_summary}"
    )

    return table


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Orchestration dashboard")
    parser.add_argument("--refresh", "-r", type=float, default=1.0, help="Refresh interval in seconds")
    parser.add_argument("--once", action="store_true", help="Show once and exit")
    args = parser.parse_args()

    if args.once:
        console.print(build_simple_dashboard())
        return

    console.print("[cyan]Starting dashboard... Press Ctrl+C to exit[/cyan]\n")

    try:
        with Live(build_simple_dashboard(), console=console, refresh_per_second=1) as live:
            while True:
                time.sleep(args.refresh)
                live.update(build_simple_dashboard())
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard stopped[/dim]")


if __name__ == "__main__":
    main()
