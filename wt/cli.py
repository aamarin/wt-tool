import os
import time
from pathlib import Path
from typing import Annotated, Optional

import typer

from wt import git, tmux, fzf, display
from wt.config import load_config
from wt.display import StatusRow

app = typer.Typer(
    name="wt",
    help="git worktree + tmux workflow tool",
    no_args_is_help=True,
    add_completion=False,
)

_OPEN_PREVIEW = (
    'echo "== PATH =="; echo {2}; echo; '
    'echo "== STATUS =="; git -C {2} status -sb; echo; '
    'st=$(git -C {2} status --porcelain); '
    'if [ -n "$st" ]; then '
    '  echo "== DIFF =="; git -C {2} diff --color | head -200; '
    'else '
    '  echo "== LAST COMMITS =="; git -C {2} log --oneline -5; '
    'fi'
)


@app.command()
def ls() -> None:
    """List all worktrees in the current repo."""
    cfg = load_config()
    root = git.get_main_worktree_root()
    worktrees = git.list_worktrees(root)
    display.print_worktree_table(worktrees, cfg.wt_dir_name)


@app.command()
def prune() -> None:
    """Prune stale worktree references."""
    root = git.get_main_worktree_root()
    git.prune_worktrees(root)
    display.print_success("Pruned stale worktree references")


@app.command()
def status() -> None:
    """Show health of all worktrees (dirty, sync, age, sessions)."""
    cfg = load_config()
    root = git.get_main_worktree_root()
    worktrees = git.list_worktrees(root)

    rows: list[StatusRow] = []
    for wt in worktrees:
        if wt.bare or wt.branch is None:
            continue
        # skip main worktree (not inside wt_dir_name)
        if cfg.wt_dir_name not in wt.path.parts:
            continue

        dirty = bool(git.get_status_porcelain(wt.path))
        sb_line = git.get_status_sb(wt.path)
        ahead, behind = git.parse_ahead_behind(sb_line)
        ts = git.get_last_commit_timestamp(wt.path)
        session = tmux.make_session_name(wt.branch)
        active = tmux.has_session(session)

        rows.append(StatusRow(
            branch=wt.branch,
            path=str(wt.path),
            is_dirty=dirty,
            ahead=ahead,
            behind=behind,
            last_commit_ts=ts,
            session_active=active,
        ))

    if not rows:
        display.print_info("No worktrees found")
        return
    display.print_status_table(rows)


@app.command()
def ensure(
    branch: Annotated[str, typer.Argument(help="Branch / worktree name")],
) -> None:
    """Ensure worktree + session exist (non-interactive). Prints path."""
    cfg = load_config()
    root = git.get_main_worktree_root()
    wt_path = root / cfg.wt_dir_name / branch

    if not wt_path.exists():
        git.fetch_all(root)
        git.add_worktree(root, branch, wt_path, branch)

    session = tmux.make_session_name(branch)
    tmux.ensure_session(session, wt_path, cfg.agent_cmd)
    print(str(wt_path))


@app.command(name="open")
def open_cmd(
    branch: Annotated[Optional[str], typer.Argument(help="Branch to open")] = None,
) -> None:
    """Open a worktree session, using fzf selector if branch omitted."""
    cfg = load_config()
    root = git.get_main_worktree_root()
    worktrees = git.list_worktrees(root)

    # filter to managed worktrees only
    managed = [
        wt for wt in worktrees
        if cfg.wt_dir_name in wt.path.parts and wt.branch
    ]

    if not managed:
        display.print_error("No worktrees found. Use `wt new` to create one.")
        raise typer.Exit(1)

    if branch is None:
        choices = [
            f"{wt.branch}|{wt.path}" for wt in managed
        ]
        try:
            selected = fzf.run_fzf(
                choices,
                prompt="open > ",
                preview_cmd=_OPEN_PREVIEW,
                delimiter="|",
                with_nth="1",
            )
        except fzf.FzfAborted:
            raise typer.Exit(0)
        branch = selected.split("|")[0]
        wt_path = Path(selected.split("|")[1])
    else:
        match = next((wt for wt in managed if wt.branch == branch), None)
        if not match:
            display.print_error(f"No worktree for branch '{branch}'")
            raise typer.Exit(1)
        wt_path = match.path

    session = tmux.make_session_name(branch)
    tmux.ensure_session(session, wt_path, cfg.agent_cmd)
    tmux.attach(session)


@app.command()
def new(
    branch: Annotated[Optional[str], typer.Argument(help="New branch name")] = None,
    base: Annotated[Optional[str], typer.Argument(help="Base branch")] = None,
) -> None:
    """Create a new worktree and tmux session."""
    cfg = load_config()
    root = git.get_main_worktree_root()

    if branch is None:
        branch = typer.prompt("New branch name")

    if base is None:
        git.fetch_all(root)
        branches = git.list_branches(root)
        if not branches:
            display.print_error("No branches found to base from")
            raise typer.Exit(1)
        try:
            base = fzf.run_fzf(branches, prompt="base branch > ")
        except fzf.FzfAborted:
            raise typer.Exit(0)

    wt_path = root / cfg.wt_dir_name / branch

    if wt_path.exists():
        display.print_error(f"Worktree already exists: {wt_path}")
        raise typer.Exit(1)

    display.print_info(f"Creating worktree '{branch}' from '{base}'...")
    git.add_worktree(root, branch, wt_path, base)

    session = tmux.make_session_name(branch)
    tmux.ensure_session(session, wt_path, cfg.agent_cmd)
    display.print_success(f"Created: {wt_path}")
    tmux.attach(session)


@app.command()
def rm(
    branch: Annotated[str, typer.Argument(help="Branch / worktree to remove")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Remove a worktree, branch, and tmux session."""
    cfg = load_config()
    root = git.get_main_worktree_root()
    wt_path = root / cfg.wt_dir_name / branch

    cwd = Path(os.getcwd()).resolve()
    if cwd == wt_path.resolve() or wt_path.resolve() in cwd.parents:
        display.print_error("Cannot remove worktree you are currently inside")
        raise typer.Exit(1)

    if not wt_path.exists():
        display.print_error(f"No worktree found at {wt_path}")
        raise typer.Exit(1)

    if not yes:
        typer.confirm(f"Remove worktree + branch '{branch}'?", abort=True)

    git.remove_worktree(root, wt_path)
    git.delete_branch(root, branch)
    session = tmux.make_session_name(branch)
    tmux.kill_session(session)
    display.print_success(f"Removed '{branch}'")


@app.command(name="global")
def global_cmd(
    target: Annotated[Optional[str], typer.Argument(help="repo:branch to open directly")] = None,
) -> None:
    """Select a worktree across all repos under WT_PROJECTS_DIR."""
    cfg = load_config()

    wt_dirs = [
        p for p in cfg.projects_dir.glob(f"*/{cfg.wt_dir_name}")
        if p.is_dir()
    ]

    if not wt_dirs:
        display.print_error(f"No worktree dirs found under {cfg.projects_dir}")
        raise typer.Exit(1)

    choices: list[str] = []
    for wt_dir in sorted(wt_dirs):
        repo_root = wt_dir.parent
        repo_name = git.get_repo_name(repo_root)
        try:
            worktrees = git.list_worktrees(repo_root)
        except SystemExit:
            continue
        for wt in worktrees:
            if cfg.wt_dir_name not in wt.path.parts or not wt.branch:
                continue
            choices.append(f"{repo_name}/{wt.branch}|{wt.path}|{repo_root}")

    if not choices:
        display.print_error("No managed worktrees found across projects")
        raise typer.Exit(1)

    if target is not None:
        match = next((c for c in choices if c.split("|")[0] == target), None)
        if not match:
            display.print_error(f"No worktree found for '{target}'")
            raise typer.Exit(1)
        selected = match
    else:
        try:
            selected = fzf.run_fzf(
                choices,
                prompt="global > ",
                preview_cmd=_OPEN_PREVIEW,
                delimiter="|",
                with_nth="1",
            )
        except fzf.FzfAborted:
            raise typer.Exit(0)

    parts = selected.split("|")
    wt_path = Path(parts[1])
    label = parts[0]
    branch = label.split("/", 1)[1] if "/" in label else label

    session = tmux.make_session_name(branch)
    tmux.ensure_session(session, wt_path, cfg.agent_cmd)
    tmux.attach(session)
