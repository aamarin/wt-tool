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
