"""Business-logic operations for worktree creation and removal."""

from collections.abc import Callable
from pathlib import Path

from wt_tool import display


def create_worktrees(
    branch_list: list[str],
    base: str,
    root: Path,
    wt_dir_name: str,
    repo_name: str,
    agent_cmd: str,
    *,
    add_worktree_fn: Callable,
    ensure_session_fn: Callable,
    make_session_name_fn: Callable,
) -> tuple[list[str], list[str]]:
    """Create worktrees and tmux sessions. Returns (successes, failures)."""
    failures: list[str] = []
    successes: list[str] = []
    for branch in branch_list:
        wt_path = root / wt_dir_name / branch
        if wt_path.exists():
            display.print_error(f"Worktree already exists: {wt_path}")
            failures.append(branch)
            continue
        display.print_info(f"Creating worktree '{branch}' from '{base}'...")
        try:
            add_worktree_fn(root, branch, wt_path, base)
        except SystemExit:
            failures.append(branch)
            continue
        session = make_session_name_fn(repo_name, branch)
        ensure_session_fn(session, wt_path, agent_cmd)
        display.print_success(f"Created: {wt_path}")
        successes.append(branch)
    return successes, failures


def remove_worktrees(
    branch_list: list[str],
    root: Path,
    wt_dir_name: str,
    repo_name: str,
    cwd: Path,
    force: bool = False,
    *,
    get_status_fn: Callable,
    has_session_fn: Callable,
    remove_worktree_fn: Callable,
    delete_branch_fn: Callable,
    kill_session_fn: Callable,
    make_session_name_fn: Callable,
) -> tuple[list[str], list[str], list[str]]:
    """Remove worktrees, branches, sessions. Returns (successes, failures, skipped)."""
    skipped: list[str] = []
    to_remove: list[str] = []

    for branch in branch_list:
        wt_path = (root / wt_dir_name / branch).resolve()
        if cwd == wt_path or wt_path in cwd.parents:
            display.print_error(
                f"Skipping '{branch}': cannot remove the worktree you are currently inside\n"
                f"  cd {root} && wt rm {branch} --non-interactive"
            )
            skipped.append(branch)
            continue
        if not (root / wt_dir_name / branch).exists():
            display.print_error(f"No worktree found at {root / wt_dir_name / branch}")
            skipped.append(branch)
            continue
        to_remove.append(branch)

    if not to_remove:
        return [], [], skipped

    dirty = [] if force else [b for b in to_remove if get_status_fn(root / wt_dir_name / b)]

    active = [b for b in to_remove if has_session_fn(make_session_name_fn(repo_name, b))]
    if active:
        display.print_info(f"Active tmux sessions: {', '.join(active)}")

    failures: list[str] = []
    successes: list[str] = []
    for branch in to_remove:
        if branch in dirty:
            display.print_error(
                f"Skipping '{branch}': uncommitted changes (use --force to override)"
            )
            failures.append(branch)
            continue
        try:
            remove_worktree_fn(root, root / wt_dir_name / branch)
            delete_branch_fn(root, branch)
            kill_session_fn(make_session_name_fn(repo_name, branch))
            display.print_success(f"Removed '{branch}'")
            successes.append(branch)
        except SystemExit:
            failures.append(branch)

    return successes, failures, skipped
