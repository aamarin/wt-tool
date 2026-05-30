import importlib.resources
import os
import shutil
from pathlib import Path
from typing import Annotated, List, Optional

import typer

from wt_tool import git, tmux, display
from wt_tool.git import WorktreeInfo
from wt_tool.display import StatusRow
from wt_tool.config import (
    load_config,
    resolve_projects_dir, save_projects_dir,
    resolve_agent_skills_dir, save_agent_skills_dir,
    resolve_agent_cmd, save_agent_cmd,
)

app = typer.Typer(
    name="wt",
    help="git worktree + tmux workflow tool",
    no_args_is_help=False,
    invoke_without_command=True,
)



@app.callback()
def default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        open_cmd()

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
    cfg = load_config()
    root = git.get_main_worktree_root_silent()
    if root is None:
        return []
    worktrees = git.list_worktrees_silent(root)
    return [wt.branch for wt in worktrees if wt.path.is_relative_to(root / cfg.wt_dir_name) and wt.branch]


def _complete_base_branches() -> list[str]:
    root = git.get_main_worktree_root_silent()
    if root is None:
        return []
    return git.list_branches_silent(root)


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
                if not wt.path.is_relative_to(repo_root / cfg.wt_dir_name) or not wt.branch:
                    continue
                choices.append(f"{repo_name}/{wt.branch}")
        return choices
    except Exception:
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

    repo_name = git.get_repo_name(root)
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
        session = tmux.make_session_name(repo_name, wt.branch)
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

        open_rows: list[display.OpenRow] = []
        has_missing = False
        for wt in managed:
            if not wt.path.exists():
                has_missing = True
                open_rows.append(display.OpenRow(
                    label=wt.branch or "detached",
                    path=str(wt.path),
                    is_dirty=False, ahead=0, behind=0, last_commit_ts=0,
                    is_missing=True,
                ))
            else:
                dirty = bool(git.get_status_porcelain_silent(wt.path))
                sb_line = git.get_status_sb(wt.path)
                ahead, behind = git.parse_ahead_behind(sb_line)
                ts = git.get_last_commit_timestamp(wt.path)
                open_rows.append(display.OpenRow(
                    label=wt.branch or "detached",
                    path=str(wt.path),
                    is_dirty=dirty, ahead=ahead, behind=behind,
                    last_commit_ts=ts,
                ))

        display.print_open_table(open_rows)
        if has_missing:
            display.print_info("Some worktrees are missing on disk. Run `wt prune` to clean up.")

        selected: WorktreeInfo | None = None
        while selected is None:
            try:
                raw = typer.prompt("\nOpen [branch name or # or q to quit]").strip()
            except (KeyboardInterrupt, typer.Abort):
                raise typer.Exit(0)
            if raw == "q":
                raise typer.Exit(0)
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(managed):
                    if open_rows[idx - 1].is_missing:
                        display.print_error(f"'{managed[idx - 1].branch}' is missing on disk — run `wt prune` to clean up.")
                    else:
                        selected = managed[idx - 1]
                else:
                    display.print_error(f"Enter a number between 1 and {len(managed)}")
            else:
                match = next((wt for wt in managed if wt.branch == raw), None)
                if match:
                    match_idx = managed.index(match)
                    if open_rows[match_idx].is_missing:
                        display.print_error(f"'{raw}' is missing on disk — run `wt prune` to clean up.")
                    else:
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

    repo_name = git.get_repo_name(root)
    session = tmux.make_session_name(repo_name, branch)
    tmux.ensure_session(session, wt_path, cfg.agent_cmd)

    if non_interactive:
        print(str(wt_path))
    else:
        tmux.attach(session)


@app.command()
def new(
    branches: Annotated[Optional[List[str]], typer.Argument(help="New branch name(s)", autocompletion=_complete_base_branches)] = None,
    base: Annotated[Optional[str], typer.Option("--base", "-b", help="Base branch (also accepted as last positional)", autocompletion=_complete_base_branches)] = None,
    non_interactive: Annotated[bool, typer.Option("--non-interactive", help="Error if args missing; no tmux attach")] = False,
) -> None:
    """Create one or more new worktrees and tmux sessions."""
    from wt_tool.operations import create_worktrees

    cfg = load_config()
    root = git.get_main_worktree_root()

    # Resolve branch list
    if not branches:
        if non_interactive:
            display.print_error("--non-interactive requires branch and base arguments")
            raise typer.Exit(1)
        branch_list = [typer.prompt("New branch name").strip()]
    else:
        branch_list = list(branches)

    # Extract base from last positional when --base not given
    if base is None and len(branch_list) >= 2:
        base = branch_list[-1]
        branch_list = branch_list[:-1]

    # Prompt for base if still unresolved
    if base is None:
        if non_interactive:
            display.print_error("--non-interactive requires branch and base arguments")
            raise typer.Exit(1)
        git.fetch_all(root)
        all_branches = git.list_branches(root)
        if not all_branches:
            display.print_error("No branches found to base from")
            raise typer.Exit(1)
        display.print_branch_table(all_branches)
        while base is None:
            try:
                raw = typer.prompt("\nBase branch [name or # or q to quit]").strip()
            except (KeyboardInterrupt, typer.Abort):
                raise typer.Exit(0)
            if raw == "q":
                raise typer.Exit(0)
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(all_branches):
                    base = all_branches[idx - 1]
                else:
                    display.print_error(f"Enter a number between 1 and {len(all_branches)}")
            elif raw in all_branches:
                base = raw
            else:
                display.print_error(f"Unknown branch '{raw}'")

    # Agent cmd — prompt once if not configured
    agent_cmd = cfg.agent_cmd
    if not non_interactive and resolve_agent_cmd() is None:
        display.print_info("No agent command configured.")
        raw = typer.prompt("Agent command (launched in agent window, leave blank to skip)", default="claude")
        agent_cmd = raw.strip()
        save_agent_cmd(agent_cmd)

    repo_name = git.get_repo_name(root)
    successes, failures = create_worktrees(
        branch_list, base, root, cfg.wt_dir_name, repo_name, agent_cmd,
        add_worktree_fn=git.add_worktree,
        ensure_session_fn=tmux.ensure_session,
        make_session_name_fn=tmux.make_session_name,
    )

    # Attach (single branch, interactive) or print paths
    if not non_interactive and len(branch_list) == 1 and successes:
        session = tmux.make_session_name(repo_name, successes[0])
        tmux.attach(session)
    else:
        for branch in successes:
            print(str(root / cfg.wt_dir_name / branch))

    if len(branch_list) > 1:
        if failures:
            display.print_error(f"Failed: {', '.join(failures)}")
        display.print_success(f"Created {len(successes)}/{len(branch_list)} worktrees")

    if failures:
        raise typer.Exit(1)


@app.command()
def rm(
    branches: Annotated[Optional[List[str]], typer.Argument(help="Branch(es) to remove", autocompletion=_complete_managed_branches)] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip dirty check")] = False,
    non_interactive: Annotated[bool, typer.Option("--non-interactive", help="Skip confirmation prompts")] = False,
) -> None:
    """Remove one or more worktrees, branches, and tmux sessions."""
    from wt_tool.operations import remove_worktrees
    from wt_tool.display import RmSummaryRow

    cfg = load_config()
    root = git.get_main_worktree_root()
    cwd = Path(os.getcwd()).resolve()

    if not branches:
        if non_interactive:
            display.print_error("--non-interactive requires at least one branch argument")
            raise typer.Exit(1)
        worktrees = git.list_worktrees(root)
        managed = [wt for wt in worktrees if cfg.wt_dir_name in wt.path.parts and wt.branch]
        if not managed:
            display.print_error("No managed worktrees found")
            raise typer.Exit(1)
        display.print_branch_table([wt.branch for wt in managed if wt.branch])
        selected: str | None = None
        while selected is None:
            try:
                raw = typer.prompt("\nRemove [branch name or # or q to quit]").strip()
            except (KeyboardInterrupt, typer.Abort):
                raise typer.Exit(0)
            if raw == "q":
                raise typer.Exit(0)
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(managed):
                    selected = managed[idx - 1].branch
                else:
                    display.print_error(f"Enter a number between 1 and {len(managed)}")
            else:
                match = next((wt.branch for wt in managed if wt.branch == raw), None)
                if match:
                    selected = match
                else:
                    display.print_error(f"Unknown branch '{raw}'")
        branch_list = [selected]
    else:
        branch_list = list(branches)

    repo_name = git.get_repo_name(root)

    if len(branch_list) > 1:
        visible = [b for b in branch_list if (root / cfg.wt_dir_name / b).exists()]
        if visible:
            dirty_preview = [] if force else [b for b in visible if git.get_status_porcelain(root / cfg.wt_dir_name / b)]
            active_preview = [b for b in visible if tmux.has_session(tmux.make_session_name(repo_name, b))]
            display.print_rm_summary([
                RmSummaryRow(branch=b, path=str(root / cfg.wt_dir_name / b),
                             is_dirty=(b in dirty_preview), session_active=(b in active_preview))
                for b in visible
            ])
        if not non_interactive:
            typer.confirm(f"Remove {len(visible)} worktrees?", abort=True)
    else:
        if not non_interactive:
            typer.confirm(f"Remove worktree + branch '{branch_list[0]}'?", abort=True)

    successes, failures, skipped = remove_worktrees(
        branch_list, root, cfg.wt_dir_name, repo_name, cwd, force,
        get_status_fn=git.get_status_porcelain,
        has_session_fn=tmux.has_session,
        remove_worktree_fn=git.remove_worktree,
        delete_branch_fn=git.delete_branch,
        kill_session_fn=tmux.kill_session,
        make_session_name_fn=tmux.make_session_name,
    )

    if len(branch_list) > 1:
        if failures or skipped:
            display.print_error(f"Failed/skipped: {', '.join(failures + skipped)}")
        display.print_success(f"Removed {len(successes)}/{len(branch_list)} worktrees")

    if not successes or failures:
        raise typer.Exit(1)


@app.command(name="global")
def global_cmd(
    target: Annotated[Optional[str], typer.Argument(help="repo/branch to open directly", autocompletion=_complete_global_targets)] = None,
    non_interactive: Annotated[bool, typer.Option("--non-interactive", help="Error if no target; no table, no tmux attach")] = False,
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

    labels: list[str] = []
    wt_paths: list[Path] = []
    repo_names: list[str] = []
    branches: list[str] = []
    open_rows: list[display.OpenRow] = []

    for wt_dir in sorted(wt_dirs):
        repo_root = wt_dir.parent
        repo_name = git.get_repo_name(repo_root)
        for wt in git.list_worktrees_silent(repo_root):
            if cfg.wt_dir_name not in wt.path.parts or not wt.branch:
                continue
            label = f"{repo_name}/{wt.branch}"
            labels.append(label)
            wt_paths.append(wt.path)
            repo_names.append(repo_name)
            branches.append(wt.branch)

            if not wt.path.exists():
                open_rows.append(display.OpenRow(
                    label=label, path=str(wt.path),
                    is_dirty=False, ahead=0, behind=0, last_commit_ts=0,
                    is_missing=True,
                ))
            else:
                dirty = bool(git.get_status_porcelain_silent(wt.path))
                sb_line = git.get_status_sb(wt.path)
                ahead, behind = git.parse_ahead_behind(sb_line)
                ts = git.get_last_commit_timestamp(wt.path)
                open_rows.append(display.OpenRow(
                    label=label, path=str(wt.path),
                    is_dirty=dirty, ahead=ahead, behind=behind,
                    last_commit_ts=ts,
                ))

    if not open_rows:
        display.print_error("No managed worktrees found across projects")
        raise typer.Exit(1)

    if target is not None:
        try:
            idx = labels.index(target)
        except ValueError:
            display.print_error(f"No worktree found for '{target}'")
            raise typer.Exit(1)
        if open_rows[idx].is_missing:
            display.print_error(f"'{target}' is missing on disk — run `wt prune` to clean up.")
            raise typer.Exit(1)
        wt_path = wt_paths[idx]
        repo_name = repo_names[idx]
        branch = branches[idx]
    else:
        if non_interactive:
            display.print_error("--non-interactive requires a repo/branch argument")
            raise typer.Exit(1)

        has_missing = any(r.is_missing for r in open_rows)
        display.print_open_table(open_rows)
        if has_missing:
            display.print_info("Some worktrees are missing on disk. Run `wt prune` to clean up.")

        selected_idx: int | None = None
        while selected_idx is None:
            try:
                raw = typer.prompt("\nOpen [repo/branch or # or q to quit]").strip()
            except (KeyboardInterrupt, typer.Abort):
                raise typer.Exit(0)
            if raw == "q":
                raise typer.Exit(0)
            if raw.isdigit():
                i = int(raw)
                if 1 <= i <= len(labels):
                    if open_rows[i - 1].is_missing:
                        display.print_error(f"'{labels[i - 1]}' is missing on disk — run `wt prune` to clean up.")
                    else:
                        selected_idx = i - 1
                else:
                    display.print_error(f"Enter a number between 1 and {len(labels)}")
            else:
                try:
                    candidate = labels.index(raw)
                    if open_rows[candidate].is_missing:
                        display.print_error(f"'{raw}' is missing on disk — run `wt prune` to clean up.")
                    else:
                        selected_idx = candidate
                except ValueError:
                    display.print_error(f"Unknown entry '{raw}'")

        wt_path = wt_paths[selected_idx]
        repo_name = repo_names[selected_idx]
        branch = branches[selected_idx]

    session = tmux.make_session_name(repo_name, branch)
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
