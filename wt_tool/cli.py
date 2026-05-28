import importlib.resources
import os
import shutil
from pathlib import Path
from typing import Annotated, Optional

import typer

from wt_tool import git, tmux, fzf, display
from wt_tool.git import WorktreeInfo
from wt_tool.config import (
    load_config,
    resolve_projects_dir, save_projects_dir,
    resolve_agent_skills_dir, save_agent_skills_dir,
    resolve_agent_cmd, save_agent_cmd,
)
from wt_tool.display import StatusRow

app = typer.Typer(
    name="wt",
    help="git worktree + tmux workflow tool",
    no_args_is_help=True,
)

_OPEN_PREVIEW = (
    'echo "== PATH =="; echo "{2}"; echo; '
    'echo "== STATUS =="; git -C "{2}" status -sb; echo; '
    'st=$(git -C "{2}" status --porcelain); '
    'if [ -n "$st" ]; then '
    '  echo "== DIFF =="; git -C "{2}" diff --color | head -200; '
    'else '
    '  echo "== LAST COMMITS =="; git -C "{2}" log --oneline -5; '
    'fi'
)


def _complete_managed_branches() -> list[str]:
    try:
        cfg = load_config()
        root = git.get_main_worktree_root()
        worktrees = git.list_worktrees(root)
        return [wt.branch for wt in worktrees if cfg.wt_dir_name in wt.path.parts and wt.branch]
    except (Exception, SystemExit):
        return []


def _complete_base_branches() -> list[str]:
    try:
        root = git.get_main_worktree_root()
        return git.list_branches(root)
    except (Exception, SystemExit):
        return []


def _complete_global_targets() -> list[str]:
    try:
        cfg = load_config()
        projects_dir = resolve_projects_dir()
        if projects_dir is None:
            return []
        wt_dirs = [p for p in projects_dir.glob(f"*/{cfg.wt_dir_name}") if p.is_dir()]
        choices = []
        for wt_dir in sorted(wt_dirs):
            repo_root = wt_dir.parent
            repo_name = git.get_repo_name(repo_root)
            for wt in git.list_worktrees_silent(repo_root):
                if cfg.wt_dir_name not in wt.path.parts or not wt.branch:
                    continue
                choices.append(f"{repo_name}/{wt.branch}")
        return choices
    except (Exception, SystemExit):
        return []


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


@app.command(name="open")
def open_cmd(
    branch: Annotated[Optional[str], typer.Argument(help="Branch to open", autocompletion=_complete_managed_branches)] = None,
    non_interactive: Annotated[bool, typer.Option("--non-interactive", help="Print path and ensure session; no tmux attach")] = False,
) -> None:
    """Open a worktree session, using an interactive table if branch omitted."""
    cfg = load_config()
    root = git.get_main_worktree_root()
    worktrees = git.list_worktrees(root)

    managed = [
        wt for wt in worktrees
        if cfg.wt_dir_name in wt.path.parts and wt.branch
    ]

    if not managed:
        display.print_error("No worktrees found. Use `wt new` to create one.")
        raise typer.Exit(1)

    if branch is None:
        if non_interactive:
            display.print_error("--non-interactive requires a branch argument")
            raise typer.Exit(1)
        display.print_open_table(managed)
        selected: WorktreeInfo | None = None
        while selected is None:
            try:
                raw = typer.prompt("\nOpen [branch name or #]").strip()
            except (KeyboardInterrupt, typer.Abort):
                raise typer.Exit(0)
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(managed):
                    selected = managed[idx - 1]
                else:
                    display.print_error(f"Enter a number between 1 and {len(managed)}")
            else:
                match = next((wt for wt in managed if wt.branch == raw), None)
                if match:
                    selected = match
                else:
                    display.print_error(f"Unknown branch '{raw}'")
        branch = selected.branch
        wt_path = selected.path
    else:
        match = next((wt for wt in managed if wt.branch == branch), None)
        if not match:
            display.print_error(f"No worktree for branch '{branch}'")
            display.print_info(f"Run: wt new {branch} <base>")
            raise typer.Exit(1)
        wt_path = match.path

    session = tmux.make_session_name(branch)
    tmux.ensure_session(session, wt_path, cfg.agent_cmd)

    if non_interactive:
        print(str(wt_path))
    else:
        tmux.attach(session)


@app.command()
def new(
    branch: Annotated[Optional[str], typer.Argument(help="New branch name")] = None,
    base: Annotated[Optional[str], typer.Argument(help="Base branch", autocompletion=_complete_base_branches)] = None,
    non_interactive: Annotated[bool, typer.Option("--non-interactive", help="Error if args missing; no fzf, no tmux attach")] = False,
) -> None:
    """Create a new worktree and tmux session."""
    cfg = load_config()
    root = git.get_main_worktree_root()

    if branch is None:
        if non_interactive:
            display.print_error("--non-interactive requires branch and base arguments")
            raise typer.Exit(1)
        branch = typer.prompt("New branch name")

    if base is None:
        if non_interactive:
            display.print_error("--non-interactive requires branch and base arguments")
            raise typer.Exit(1)
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

    agent_cmd = cfg.agent_cmd
    if not non_interactive and resolve_agent_cmd() is None:
        display.print_info("No agent command configured.")
        raw = typer.prompt("Agent command (launched in agent window, leave blank to skip)", default="claude")
        agent_cmd = raw.strip()
        save_agent_cmd(agent_cmd)

    display.print_info(f"Creating worktree '{branch}' from '{base}'...")
    git.add_worktree(root, branch, wt_path, base)

    session = tmux.make_session_name(branch)
    tmux.ensure_session(session, wt_path, agent_cmd)
    display.print_success(f"Created: {wt_path}")

    if not non_interactive:
        tmux.attach(session)
    else:
        print(str(wt_path))


@app.command()
def rm(
    branch: Annotated[str, typer.Argument(help="Branch / worktree to remove", autocompletion=_complete_managed_branches)],
    non_interactive: Annotated[bool, typer.Option("--non-interactive", help="Skip confirmation")] = False,
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

    if not non_interactive:
        typer.confirm(f"Remove worktree + branch '{branch}'?", abort=True)

    git.remove_worktree(root, wt_path)
    git.delete_branch(root, branch)
    session = tmux.make_session_name(branch)
    tmux.kill_session(session)
    display.print_success(f"Removed '{branch}'")


@app.command(name="global")
def global_cmd(
    target: Annotated[Optional[str], typer.Argument(help="repo/branch to open directly", autocompletion=_complete_global_targets)] = None,
    non_interactive: Annotated[bool, typer.Option("--non-interactive", help="Error if no target; no fzf, no tmux attach")] = False,
) -> None:
    """Select a worktree across all repos under WT_PROJECTS_DIR."""
    cfg = load_config()

    projects_dir = resolve_projects_dir()
    if projects_dir is None:
        if non_interactive:
            display.print_error("WT_PROJECTS_DIR is not configured. Run: wt global")
            raise typer.Exit(1)
        display.print_info("WT_PROJECTS_DIR is not configured.")
        raw = typer.prompt(
            "Where are your projects?",
            default=str(Path.home() / "Development"),
        )
        projects_dir = Path(raw).expanduser().resolve()
        save_projects_dir(projects_dir)
        display.print_success(f"Saved projects dir: {projects_dir}")

    wt_dirs = [
        p for p in projects_dir.glob(f"*/{cfg.wt_dir_name}")
        if p.is_dir()
    ]

    if not wt_dirs:
        display.print_error(f"No worktree dirs found under {projects_dir}")
        raise typer.Exit(1)

    choices: list[str] = []
    for wt_dir in sorted(wt_dirs):
        repo_root = wt_dir.parent
        repo_name = git.get_repo_name(repo_root)
        for wt in git.list_worktrees_silent(repo_root):
            if cfg.wt_dir_name not in wt.path.parts or not wt.branch:
                continue
            choices.append(f"{repo_name}/{wt.branch}\t{wt.path}\t{repo_name}")

    if not choices:
        display.print_error("No managed worktrees found across projects")
        raise typer.Exit(1)

    if target is not None:
        match = next((c for c in choices if c.split("\t", maxsplit=1)[0] == target), None)
        if not match:
            display.print_error(f"No worktree found for '{target}'")
            raise typer.Exit(1)
        selected = match
    else:
        if non_interactive:
            display.print_error("--non-interactive requires a repo/branch argument")
            raise typer.Exit(1)
        try:
            selected = fzf.run_fzf(
                choices,
                prompt="global > ",
                preview_cmd=_OPEN_PREVIEW,
                delimiter="\t",
                with_nth="1",
            )
        except fzf.FzfAborted:
            raise typer.Exit(0)

    parts = selected.split("\t", maxsplit=2)
    wt_path = Path(parts[1])
    repo_name = parts[2]
    label = parts[0]
    branch = label.split("/", 1)[1] if "/" in label else label

    session = tmux.make_session_name(f"{repo_name}__{branch}")
    tmux.ensure_session(session, wt_path, cfg.agent_cmd)

    if non_interactive:
        print(str(wt_path))
    else:
        tmux.attach(session)


config_app = typer.Typer(name="config", help="Get and set wt configuration.", no_args_is_help=True)
app.add_typer(config_app)

_VALID_KEYS = ("agent-cmd", "projects-dir")


@config_app.command(name="set")
def config_set(
    key: Annotated[str, typer.Argument(help=f"Config key: {', '.join(_VALID_KEYS)}")],
    value: Annotated[str, typer.Argument(help="Value to set")],
) -> None:
    """Set a configuration value."""
    if key == "agent-cmd":
        save_agent_cmd(value)
        display.print_success(f"agent-cmd = {value}")
    elif key == "projects-dir":
        save_projects_dir(Path(value).expanduser().resolve())
        display.print_success(f"projects-dir = {value}")
    else:
        display.print_error(f"Unknown key '{key}'. Valid keys: {', '.join(_VALID_KEYS)}")
        raise typer.Exit(1)


@config_app.command(name="show")
def config_show() -> None:
    """Show current configuration (file + env)."""
    cfg = load_config()
    typer.echo(f"agent-cmd    = {cfg.agent_cmd}")
    typer.echo(f"projects-dir = {cfg.projects_dir}")
    typer.echo(f"wt-dir-name  = {cfg.wt_dir_name}")


install_app = typer.Typer(name="install", help="Install wt integrations.", no_args_is_help=True)
app.add_typer(install_app)


@install_app.command(name="agent-skill")
def install_agent_skill(
    path: Annotated[Optional[str], typer.Option("--path", "-p", help="Target skills directory")] = None,
) -> None:
    """Install the using-wt agent skill to your skills directory."""
    _DEFAULT_SKILLS_DIR = Path.home() / ".agents" / "skills"

    if path is not None:
        skills_dir = Path(path).expanduser().resolve()
        save_agent_skills_dir(skills_dir)
    else:
        skills_dir = resolve_agent_skills_dir()
        if skills_dir is None:
            raw = typer.prompt(
                "Where are your agent skills?",
                default=str(_DEFAULT_SKILLS_DIR),
            )
            skills_dir = Path(raw).expanduser().resolve()
            save_agent_skills_dir(skills_dir)

    dest = skills_dir / "using-wt"

    skill_src = importlib.resources.files("wt_tool") / "skills" / "using-wt"
    with importlib.resources.as_file(skill_src) as src:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

    display.print_success(f"Installed using-wt skill → {dest}")
