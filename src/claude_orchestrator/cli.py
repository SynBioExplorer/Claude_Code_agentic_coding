"""CLI interface for the Claude Orchestrator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from claude_orchestrator import __version__
from claude_orchestrator.core.dag import topological_sort, validate_dag
from claude_orchestrator.core.risk import compute_risk_score, get_risk_summary
from claude_orchestrator.core.state import OrchestrationStatePersistence
from claude_orchestrator.schemas.config import OrchestrationConfig
from claude_orchestrator.schemas.status import TaskState
from claude_orchestrator.worktree.manager import WorktreeManager

console = Console()


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """Claude Code Multi-Agent Orchestration System.

    Coordinate parallel task execution with git worktree isolation
    and automated verification.
    """
    pass


@main.command()
@click.argument("request", required=False)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to config file (.claude-agents.yaml)",
)
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
def plan(request: str | None, config: str | None, dry_run: bool) -> None:
    """Create an execution plan for a request.

    This invokes the Planner-Architect agent to analyze the codebase
    and generate tasks.yaml with parallelizable tasks.
    """
    if not request:
        request = click.prompt("Enter your request")

    console.print(f"\n[bold blue]Planning:[/bold blue] {request}\n")

    # Load config
    config_path = Path(config) if config else Path(".claude-agents.yaml")
    cfg = OrchestrationConfig.load(config_path)

    if dry_run:
        console.print("[yellow]Dry run mode - no agents will be spawned[/yellow]\n")
        console.print("Would spawn Planner-Architect agent with:")
        console.print(f"  Model: {cfg.orchestration.planner_model}")
        console.print(f"  Request: {request}")
        return

    # In a full implementation, this would spawn the Planner-Architect agent
    console.print("[dim]This would spawn the Planner-Architect agent.[/dim]")
    console.print("[dim]The agent would analyze the codebase and generate tasks.yaml[/dim]")


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed status")
def status(as_json: bool, verbose: bool) -> None:
    """Show current orchestration status."""
    persistence = OrchestrationStatePersistence()
    state = persistence.load()

    if not state:
        if as_json:
            click.echo(json.dumps({"status": "no_orchestration", "message": "No active orchestration"}))
        else:
            console.print("[yellow]No active orchestration found.[/yellow]")
        return

    if as_json:
        click.echo(json.dumps(state.model_dump(mode="json"), indent=2))
        return

    # Display status
    console.print(Panel(f"[bold]Orchestration: {state.request_id}[/bold]"))
    console.print(f"Request: {state.original_request}")
    console.print(f"Phase: {state.current_phase}")
    console.print(f"Iteration: {state.iteration}/3")

    if state.environment:
        console.print(f"Environment Hash: {state.environment.hash}")

    # Task table
    table = Table(title="\nTasks")
    table.add_column("ID", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Started", style="dim")
    table.add_column("Completed", style="dim")

    for task_id, task_status in state.tasks.items():
        status_style = _get_status_style(task_status.status)
        table.add_row(
            task_id,
            f"[{status_style}]{task_status.status.value}[/{status_style}]",
            task_status.started_at or "-",
            task_status.completed_at or "-",
        )

    console.print(table)

    if verbose:
        # Show additional details
        for task_id, task_status in state.tasks.items():
            if task_status.error:
                console.print(f"\n[red]Error in {task_id}:[/red] {task_status.error}")
            if task_status.verification_result:
                vr = task_status.verification_result
                passed = "[green]PASSED[/green]" if vr.verification_passed else "[red]FAILED[/red]"
                console.print(f"\n{task_id} verification: {passed}")


def _get_status_style(status: TaskState) -> str:
    """Get Rich style for a task status."""
    styles = {
        TaskState.PENDING: "dim",
        TaskState.BLOCKED: "yellow",
        TaskState.EXECUTING: "blue",
        TaskState.VERIFYING: "cyan",
        TaskState.VERIFIED: "green",
        TaskState.MERGING: "magenta",
        TaskState.MERGED: "green bold",
        TaskState.FAILED: "red bold",
    }
    return styles.get(status, "white")


@main.command()
@click.option("--force", "-f", is_flag=True, help="Force abort even with pending work")
def abort(force: bool) -> None:
    """Abort the current orchestration.

    This will stop all workers, clean up worktrees, and reset state.
    """
    persistence = OrchestrationStatePersistence()
    state = persistence.load()

    if not state:
        console.print("[yellow]No active orchestration to abort.[/yellow]")
        return

    # Check for active tasks
    active_tasks = [
        tid for tid, ts in state.tasks.items()
        if ts.status in (TaskState.EXECUTING, TaskState.VERIFYING, TaskState.MERGING)
    ]

    if active_tasks and not force:
        console.print(f"[yellow]Active tasks: {', '.join(active_tasks)}[/yellow]")
        if not click.confirm("Abort will terminate these tasks. Continue?"):
            return

    console.print("[bold red]Aborting orchestration...[/bold red]")

    # Clean up worktrees
    wm = WorktreeManager()
    removed = wm.cleanup_all_worktrees(force=force)
    if removed:
        console.print(f"Removed worktrees: {', '.join(removed)}")

    # Clean up tmux sessions
    from claude_orchestrator.utils.tmux import cleanup_worker_sessions

    cleaned = cleanup_worker_sessions()
    if cleaned:
        console.print(f"Cleaned sessions: {', '.join(cleaned)}")

    # Delete state file
    persistence.delete()
    console.print("[green]Orchestration aborted.[/green]")


@main.command()
@click.argument("tasks_file", type=click.Path(exists=True), default="tasks.yaml")
def validate(tasks_file: str) -> None:
    """Validate a tasks.yaml file.

    Checks for:
    - Valid YAML structure
    - Required fields present
    - No circular dependencies
    - No file/resource conflicts
    """
    import yaml

    from claude_orchestrator.core.conflict import detect_all_conflicts, get_conflict_summary
    from claude_orchestrator.schemas.tasks import ExecutionPlan

    console.print(f"[bold]Validating:[/bold] {tasks_file}\n")

    try:
        with open(tasks_file) as f:
            data = yaml.safe_load(f)

        plan = ExecutionPlan.model_validate(data)
        console.print("[green]✓[/green] Schema validation passed")

        # Validate DAG
        validate_dag(plan.tasks)
        console.print("[green]✓[/green] DAG validation passed (no cycles)")

        # Get parallel waves
        waves = topological_sort(plan.tasks)
        console.print(f"[green]✓[/green] Execution waves: {len(waves)}")
        for i, wave in enumerate(waves):
            console.print(f"    Wave {i + 1}: {', '.join(wave)}")

        # Check for conflicts
        conflicts = detect_all_conflicts(plan.tasks)
        if conflicts:
            console.print(f"\n[red]✗[/red] Found conflicts:")
            console.print(get_conflict_summary(conflicts))
        else:
            console.print("[green]✓[/green] No file/resource conflicts")

        # Compute risk score
        risk = compute_risk_score(plan)
        console.print(f"\n{get_risk_summary(risk)}")

    except Exception as e:
        console.print(f"[red]✗[/red] Validation failed: {e}")
        sys.exit(1)


@main.command()
@click.option("--all", "show_all", is_flag=True, help="Show all worktrees")
def worktrees(show_all: bool) -> None:
    """List active worktrees."""
    wm = WorktreeManager()
    wts = wm.list_worktrees()

    if not wts:
        console.print("[yellow]No worktrees found.[/yellow]")
        return

    table = Table(title="Git Worktrees")
    table.add_column("Task ID", style="cyan")
    table.add_column("Branch", style="green")
    table.add_column("Path")
    table.add_column("Type", style="dim")

    for wt in wts:
        if not show_all and wt.is_main:
            continue

        wt_type = "main" if wt.is_main else "task"
        table.add_row(
            wt.task_id or "-",
            wt.branch,
            str(wt.path),
            wt_type,
        )

    console.print(table)


@main.command()
@click.option("--force", "-f", is_flag=True, help="Force cleanup")
def cleanup(force: bool) -> None:
    """Clean up stale worktrees and sessions."""
    console.print("[bold]Cleaning up...[/bold]\n")

    # Worktrees
    wm = WorktreeManager()
    stale = wm.cleanup_stale_worktrees()
    if stale:
        console.print(f"Removed stale worktrees: {', '.join(stale)}")
    else:
        console.print("No stale worktrees found.")

    # tmux sessions
    from claude_orchestrator.utils.tmux import cleanup_worker_sessions

    cleaned = cleanup_worker_sessions()
    if cleaned:
        console.print(f"Cleaned sessions: {', '.join(cleaned)}")
    else:
        console.print("No worker sessions found.")

    console.print("\n[green]Cleanup complete.[/green]")


@main.command()
@click.argument("output", type=click.Path(), default=".claude-agents.yaml")
def init(output: str) -> None:
    """Initialize a new configuration file."""
    output_path = Path(output)

    if output_path.exists():
        if not click.confirm(f"{output} already exists. Overwrite?"):
            return

    config = OrchestrationConfig()
    config.save(output_path)
    console.print(f"[green]Created:[/green] {output}")


@main.command()
def version() -> None:
    """Show version information."""
    console.print(f"Claude Orchestrator v{__version__}")


if __name__ == "__main__":
    main()
