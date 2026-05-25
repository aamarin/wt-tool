import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import typer


@dataclass
class WorktreeInfo:
    path: Path
    head: str
    branch: Optional[str] = None  # None = detached HEAD
    bare: bool = False


def _run(cmd: list[str], cwd: Optional[Path] = None) -> str:
    try:
        return subprocess.run(
            cmd, cwd=cwd, check=True, capture_output=True, text=True
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        from wt.display import print_error
        print_error(e.stderr.strip() or " ".join(cmd))
        raise typer.Exit(1)


def parse_worktrees(output: str) -> list[WorktreeInfo]:
    """Pure parser for `git worktree list --porcelain` output."""
    worktrees: list[WorktreeInfo] = []
    block: dict[str, str] = {}

    for line in output.splitlines():
        if line == "":
            if "worktree" in block:
                wt = WorktreeInfo(
                    path=Path(block["worktree"]),
                    head=block.get("HEAD", ""),
                    branch=block.get("branch", "").removeprefix("refs/heads/") or None,
                    bare="bare" in block,
                )
                worktrees.append(wt)
            block = {}
        elif line.startswith("worktree "):
            block["worktree"] = line[len("worktree "):]
        elif line.startswith("HEAD "):
            block["HEAD"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            block["branch"] = line[len("branch "):]
        elif line == "bare":
            block["bare"] = "1"
        elif line == "detached":
            pass  # branch stays absent → None

    # trailing block without blank line
    if "worktree" in block:
        wt = WorktreeInfo(
            path=Path(block["worktree"]),
            head=block.get("HEAD", ""),
            branch=block.get("branch", "").removeprefix("refs/heads/") or None,
            bare="bare" in block,
        )
        worktrees.append(wt)

    return worktrees


def get_main_worktree_root() -> Path:
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError:
        from wt.display import print_error
        print_error("Not inside a git repository")
        raise typer.Exit(1)

    worktrees = parse_worktrees(out)
    if not worktrees:
        from wt.display import print_error
        print_error("No worktrees found")
        raise typer.Exit(1)
    return worktrees[0].path


def list_worktrees(root: Path) -> list[WorktreeInfo]:
    out = _run(["git", "worktree", "list", "--porcelain"], cwd=root)
    return parse_worktrees(out + "\n")


def get_repo_name(root: Path) -> str:
    return root.name


def list_branches(root: Path) -> list[str]:
    out = _run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/", "refs/remotes/"],
        cwd=root,
    )
    seen: set[str] = set()
    branches: list[str] = []
    for b in out.splitlines():
        short = b.removeprefix("origin/")
        if short not in seen:
            seen.add(short)
            branches.append(short)
    return sorted(branches)


def add_worktree(root: Path, branch: str, wt_path: Path, base: str) -> None:
    fetch_all(root)
    _run(["git", "worktree", "add", "-b", branch, str(wt_path), base], cwd=root)


def remove_worktree(root: Path, wt_path: Path) -> None:
    _run(["git", "worktree", "remove", "--force", str(wt_path)], cwd=root)


def delete_branch(root: Path, branch: str) -> None:
    try:
        subprocess.run(
            ["git", "branch", "-d", branch],
            cwd=root, check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        from wt.display import print_error
        print_error(f"Branch delete warning: {e.stderr.strip()}")


def prune_worktrees(root: Path) -> None:
    _run(["git", "worktree", "prune"], cwd=root)


def fetch_all(root: Path) -> None:
    try:
        subprocess.run(
            ["git", "fetch", "--all", "--prune"],
            cwd=root, check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError:
        pass  # fetch failures are non-fatal


def get_status_porcelain(wt_path: Path) -> str:
    return _run(["git", "-C", str(wt_path), "status", "--porcelain"])


_AHEAD_BEHIND_RE = re.compile(r"\[(?:ahead (\d+))?(?:, )?(?:behind (\d+))?\]")


def parse_ahead_behind(status_sb_line: str) -> tuple[int, int]:
    """Parse ahead/behind counts from first line of `git status -sb`."""
    m = _AHEAD_BEHIND_RE.search(status_sb_line)
    if not m:
        return 0, 0
    ahead = int(m.group(1)) if m.group(1) else 0
    behind = int(m.group(2)) if m.group(2) else 0
    return ahead, behind


def get_status_sb(wt_path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(wt_path), "status", "-sb"],
            check=True, capture_output=True, text=True,
        ).stdout
        return out.splitlines()[0] if out.strip() else ""
    except subprocess.CalledProcessError:
        return ""


def get_last_commit_timestamp(wt_path: Path) -> int:
    try:
        out = subprocess.run(
            ["git", "-C", str(wt_path), "log", "-1", "--format=%ct"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        return int(out) if out else 0
    except (subprocess.CalledProcessError, ValueError):
        return 0
