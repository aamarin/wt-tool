from pathlib import Path
from unittest.mock import patch

import pytest

from wt_tool.cli import (
    _complete_base_branches,
    _complete_global_targets,
    _complete_managed_branches,
)
from wt_tool.git import WorktreeInfo


def _make_worktree(path: str, branch: str | None) -> WorktreeInfo:
    return WorktreeInfo(path=Path(path), head="abc123", branch=branch)


@pytest.fixture(autouse=True)
def fixed_wt_dir_name(monkeypatch):
    monkeypatch.setenv("WT_DIR_NAME", "wt")


class TestCompleteManagedBranches:
    def test_returns_managed_branch_names(self):
        worktrees = [
            _make_worktree("/repo", "main"),
            _make_worktree("/repo/wt/feat-a", "feat-a"),
            _make_worktree("/repo/wt/feat-b", "feat-b"),
        ]
        with (
            patch(
                "wt_tool.cli.git.get_main_worktree_root_silent",
                return_value=Path("/repo"),
            ),
            patch("wt_tool.cli.git.list_worktrees_silent", return_value=worktrees),
        ):
            result = _complete_managed_branches()
        assert result == ["feat-a", "feat-b"]

    def test_excludes_main_worktree(self):
        worktrees = [
            _make_worktree("/repo", "main"),
            _make_worktree("/repo/wt/only-branch", "only-branch"),
        ]
        with (
            patch(
                "wt_tool.cli.git.get_main_worktree_root_silent",
                return_value=Path("/repo"),
            ),
            patch("wt_tool.cli.git.list_worktrees_silent", return_value=worktrees),
        ):
            result = _complete_managed_branches()
        assert "main" not in result
        assert result == ["only-branch"]

    def test_excludes_detached_head(self):
        worktrees = [
            _make_worktree("/repo/wt/detached", None),
            _make_worktree("/repo/wt/normal", "normal"),
        ]
        with (
            patch(
                "wt_tool.cli.git.get_main_worktree_root_silent",
                return_value=Path("/repo"),
            ),
            patch("wt_tool.cli.git.list_worktrees_silent", return_value=worktrees),
        ):
            result = _complete_managed_branches()
        assert result == ["normal"]

    def test_excludes_worktree_if_repo_parent_named_wt(self):
        # Repo lives at ~/wt/myrepo — main worktree path contains "wt" but is not
        # under root/wt, so it must not appear in completions.
        worktrees = [
            _make_worktree("/home/user/wt/myrepo", "main"),
            _make_worktree("/home/user/wt/myrepo/wt/feat", "feat"),
        ]
        with (
            patch(
                "wt_tool.cli.git.get_main_worktree_root_silent",
                return_value=Path("/home/user/wt/myrepo"),
            ),
            patch("wt_tool.cli.git.list_worktrees_silent", return_value=worktrees),
        ):
            result = _complete_managed_branches()
        assert result == ["feat"]
        assert "main" not in result

    def test_returns_empty_list_when_not_in_git_repo(self):
        with patch("wt_tool.cli.git.get_main_worktree_root_silent", return_value=None):
            result = _complete_managed_branches()
        assert result == []


class TestCompleteBaseBranches:
    def test_returns_branch_list(self):
        with (
            patch(
                "wt_tool.cli.git.get_main_worktree_root_silent",
                return_value=Path("/repo"),
            ),
            patch(
                "wt_tool.cli.git.list_branches_silent",
                return_value=["main", "origin/feat"],
            ),
        ):
            result = _complete_base_branches()
        assert result == ["main", "origin/feat"]

    def test_returns_empty_list_when_not_in_git_repo(self):
        with patch("wt_tool.cli.git.get_main_worktree_root_silent", return_value=None):
            result = _complete_base_branches()
        assert result == []


class TestCompleteGlobalTargets:
    def test_returns_repo_branch_strings(self, tmp_path):
        repo_dir = tmp_path / "myrepo"
        wt_dir = repo_dir / "wt"
        wt_dir.mkdir(parents=True)

        worktrees = [
            _make_worktree(str(repo_dir), "main"),
            _make_worktree(str(wt_dir / "feat-x"), "feat-x"),
        ]

        with patch("wt_tool.cli.resolve_projects_dir", return_value=tmp_path), \
             patch("wt_tool.cli.git.get_repo_name", return_value="myrepo"), \
             patch("wt_tool.cli.git.list_worktrees_silent", return_value=worktrees):
            result = _complete_global_targets()

        assert result == ["myrepo/feat-x"]

    def test_excludes_main_worktree_even_if_parent_named_wt(self, tmp_path):
        # Repo at tmp_path/wt/myrepo — main worktree path has "wt" in it
        wt_container = tmp_path / "wt"
        repo_dir = wt_container / "myrepo"
        wt_dir = repo_dir / "wt"
        wt_dir.mkdir(parents=True)

        worktrees = [
            _make_worktree(str(repo_dir), "main"),
            _make_worktree(str(wt_dir / "feat-y"), "feat-y"),
        ]

        with patch("wt_tool.cli.resolve_projects_dir", return_value=wt_container), \
             patch("wt_tool.cli.git.get_repo_name", return_value="myrepo"), \
             patch("wt_tool.cli.git.list_worktrees_silent", return_value=worktrees):
            result = _complete_global_targets()

        assert result == ["myrepo/feat-y"]
        assert "myrepo/main" not in result

    def test_returns_empty_list_when_projects_dir_not_configured(self):
        with patch("wt_tool.cli.resolve_projects_dir", return_value=None):
            result = _complete_global_targets()
        assert result == []

    def test_returns_empty_list_on_exception(self):
        with patch(
            "wt_tool.cli.resolve_projects_dir",
            side_effect=RuntimeError("fail"),
        ):
            result = _complete_global_targets()
        assert result == []
