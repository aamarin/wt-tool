import time
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table
from rich.text import Text

from wt_tool.git import WorktreeInfo

console = Console()
err_console = Console(stderr=True)


@dataclass
class StatusRow:
    branch: str
    path: str
    is_dirty: bool
    ahead: int
    behind: int
    last_commit_ts: int
    session_active: bool


@dataclass
class OpenRow:
    label: str
    path: str
    is_dirty: bool
    ahead: int
    behind: int
    last_commit_ts: int
    is_missing: bool = False


def print_error(msg: str) -> None:
    err_console.print(f"[red]✗[/red] {msg}")


def print_success(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def print_info(msg: str) -> None:
    console.print(f"[cyan]→[/cyan] {msg}")


def print_open_table(rows: list[OpenRow]) -> None:
    """Print numbered worktree table for interactive selection."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Branch")
    table.add_column("State", justify="center")
    table.add_column("Sync", justify="center")
    table.add_column("Age", justify="right")
    table.add_column("Path", style="dim")

    now = int(time.time())
    stale_threshold = 3 * 24 * 3600

    for i, row in enumerate(rows, 1):
        if row.is_missing:
            state: str = "[red]✗ missing[/red]"
            sync: str = "[dim]-[/dim]"
            age: str = "[dim]-[/dim]"
        else:
            state = "⚠" if row.is_dirty else "✓"
            sync = _format_sync(row.ahead, row.behind)
            age = _format_age(row.last_commit_ts, now, stale_threshold)
        table.add_row(str(i), row.label, state, sync, age, row.path)

    console.print(table)


def print_worktree_table(worktrees: list[WorktreeInfo], wt_dir_name: str = "wt") -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Branch")
    table.add_column("Path", style="dim")

    # use main worktree root as base for relative paths
    main_root = worktrees[0].path if worktrees else None

    for wt in worktrees:
        if wt_dir_name not in wt.path.parts:
            continue
        if wt.branch:
            branch_cell: Text | str = wt.branch
        else:
            branch_cell = Text("detached", style="dim")
        if main_root:
            try:
                display_path = str(wt.path.relative_to(main_root))
            except ValueError:
                display_path = str(wt.path)
        else:
            display_path = str(wt.path)
        table.add_row(branch_cell, display_path)

    console.print(table)


def print_status_table(rows: list[StatusRow]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Branch")
    table.add_column("State", justify="center")
    table.add_column("Sync", justify="center")
    table.add_column("Age", justify="right")
    table.add_column("Session", justify="center")

    now = int(time.time())
    stale_threshold = 3 * 24 * 3600

    for row in rows:
        state = "⚠" if row.is_dirty else "✅"
        sync = _format_sync(row.ahead, row.behind)
        age = _format_age(row.last_commit_ts, now, stale_threshold)
        session = "🟢" if row.session_active else "⚪"
        table.add_row(row.branch, state, sync, age, session)

    console.print(table)


def _format_sync(ahead: int, behind: int) -> str:
    if ahead and behind:
        return f"[yellow]⇅ {ahead}↑{behind}↓[/yellow]"
    if ahead:
        return f"[green]↑{ahead}[/green]"
    if behind:
        return f"[red]↓{behind}[/red]"
    return "[dim]-[/dim]"


def _format_age(ts: int, now: int, stale_threshold: int) -> str:
    if not ts:
        return "[dim]-[/dim]"
    age_secs = max(0, now - ts)
    if age_secs > stale_threshold:
        return f"[yellow]{_human_age(age_secs)}[/yellow]"
    return _human_age(age_secs)


def _human_age(seconds: int) -> str:
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"
