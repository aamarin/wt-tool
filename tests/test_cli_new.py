from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from wt_tool.cli import app
from wt_tool.config import Config

runner = CliRunner()

BRANCHES = ["develop", "feat/x", "main"]


def _cfg():
    return Config(wt_dir_name="wt", projects_dir=Path("/projects"), agent_cmd="claude")


class TestNewBranchPicker:
    """Interactive base-branch picker in `wt new` when base arg is omitted."""

    def _setup(self, mocker, tmp_path):
        mocker.patch("wt_tool.cli.load_config", return_value=_cfg())
        mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=tmp_path)
        mocker.patch("wt_tool.cli.git.fetch_all")
        mocker.patch("wt_tool.cli.git.list_branches", return_value=BRANCHES)
        mocker.patch("wt_tool.cli.display.print_branch_table")
        mocker.patch("wt_tool.cli.git.get_repo_name", return_value="myrepo")
        mocker.patch("wt_tool.cli.tmux.ensure_session")
        mocker.patch("wt_tool.cli.tmux.attach")
        mocker.patch("wt_tool.cli.resolve_agent_cmd", return_value="claude")
        mocker.patch("wt_tool.cli.resolve_wt_dir_name", return_value="wt")
        return mocker.patch("wt_tool.cli.git.add_worktree")

    def test_number_selects_branch(self, mocker, tmp_path):
        add_wt = self._setup(mocker, tmp_path)
        result = runner.invoke(app, ["new", "my-feature"], input="2\n")
        assert result.exit_code == 0
        assert add_wt.call_args[0][3] == BRANCHES[1]  # "feat/x"

    def test_name_selects_branch(self, mocker, tmp_path):
        add_wt = self._setup(mocker, tmp_path)
        result = runner.invoke(app, ["new", "my-feature"], input="main\n")
        assert result.exit_code == 0
        assert add_wt.call_args[0][3] == "main"

    def test_quit_exits_cleanly(self, mocker, tmp_path):
        add_wt = self._setup(mocker, tmp_path)
        result = runner.invoke(app, ["new", "my-feature"], input="q\n")
        assert result.exit_code == 0
        add_wt.assert_not_called()

    def test_out_of_range_loops_then_selects(self, mocker, tmp_path):
        add_wt = self._setup(mocker, tmp_path)
        result = runner.invoke(app, ["new", "my-feature"], input="99\n1\n")
        assert result.exit_code == 0
        assert add_wt.call_args[0][3] == BRANCHES[0]  # "develop"

    def test_unknown_name_loops_then_selects(self, mocker, tmp_path):
        add_wt = self._setup(mocker, tmp_path)
        result = runner.invoke(app, ["new", "my-feature"], input="nope\nmain\n")
        assert result.exit_code == 0
        assert add_wt.call_args[0][3] == "main"

    def test_non_interactive_requires_base(self, mocker, tmp_path):
        self._setup(mocker, tmp_path)
        result = runner.invoke(app, ["new", "my-feature", "--non-interactive"])
        assert result.exit_code == 1

    def test_base_arg_bypasses_picker(self, mocker, tmp_path):
        add_wt = self._setup(mocker, tmp_path)
        result = runner.invoke(app, ["new", "my-feature", "main", "--non-interactive"])
        assert result.exit_code == 0
        assert add_wt.call_args[0][3] == "main"


class TestNewMultiBranch:
    def _setup(self, mocker, tmp_path):
        mocker.patch("wt_tool.cli.load_config", return_value=_cfg())
        mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=tmp_path)
        mocker.patch("wt_tool.cli.git.get_repo_name", return_value="myrepo")
        mocker.patch("wt_tool.cli.tmux.ensure_session")
        mocker.patch("wt_tool.cli.tmux.attach")
        mocker.patch("wt_tool.cli.git.add_worktree")
        mocker.patch("wt_tool.cli.resolve_agent_cmd", return_value="claude")

    def test_creates_from_last_positional_base(self, mocker, tmp_path):
        self._setup(mocker, tmp_path)
        add_wt = mocker.patch("wt_tool.cli.git.add_worktree")
        result = runner.invoke(app, ["new", "feat-a", "feat-b", "main", "--non-interactive"])
        assert result.exit_code == 0
        assert add_wt.call_count == 2
        bases = [c[0][3] for c in add_wt.call_args_list]
        assert bases == ["main", "main"]

    def test_creates_from_base_flag(self, mocker, tmp_path):
        self._setup(mocker, tmp_path)
        add_wt = mocker.patch("wt_tool.cli.git.add_worktree")
        result = runner.invoke(app, ["new", "feat-a", "feat-b", "--base", "main", "--non-interactive"])
        assert result.exit_code == 0
        assert add_wt.call_count == 2
        bases = [c[0][3] for c in add_wt.call_args_list]
        assert bases == ["main", "main"]

    def test_no_attach_for_multiple_branches(self, mocker, tmp_path):
        self._setup(mocker, tmp_path)
        attach = mocker.patch("wt_tool.cli.tmux.attach")
        runner.invoke(app, ["new", "feat-a", "feat-b", "main"])
        attach.assert_not_called()

    def test_prints_paths_for_multiple(self, mocker, tmp_path):
        self._setup(mocker, tmp_path)
        result = runner.invoke(app, ["new", "feat-a", "feat-b", "main", "--non-interactive"])
        assert "feat-a" in result.output
        assert "feat-b" in result.output

    def test_two_positionals_treats_last_as_base(self, mocker, tmp_path):
        """wt new feat-a feat-b → creates feat-a from feat-b (backward compat, no prompt)."""
        self._setup(mocker, tmp_path)
        add_wt = mocker.patch("wt_tool.cli.git.add_worktree")
        result = runner.invoke(app, ["new", "feat-a", "feat-b", "--non-interactive"])
        assert result.exit_code == 0
        assert add_wt.call_count == 1
        assert add_wt.call_args[0][1] == "feat-a"
        assert add_wt.call_args[0][3] == "feat-b"

    def test_exit_code_1_when_all_fail(self, mocker, tmp_path):
        self._setup(mocker, tmp_path)
        mocker.patch("wt_tool.cli.resolve_agent_cmd", return_value="claude")
        (tmp_path / "wt" / "feat-a").mkdir(parents=True)
        (tmp_path / "wt" / "feat-b").mkdir(parents=True)
        result = runner.invoke(app, ["new", "feat-a", "feat-b", "main", "--non-interactive"])
        assert result.exit_code == 1
