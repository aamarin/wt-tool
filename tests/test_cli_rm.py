from pathlib import Path

from typer.testing import CliRunner

from wt_tool.cli import app
from wt_tool.config import Config

runner = CliRunner()


def _cfg():
    return Config(wt_dir_name="wt", projects_dir=Path("/projects"), agent_cmd="claude")


def _setup(mocker, tmp_path):
    mocker.patch("wt_tool.cli.load_config", return_value=_cfg())
    mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=tmp_path)
    mocker.patch("wt_tool.cli.git.get_repo_name", return_value="myrepo")
    mocker.patch("wt_tool.cli.tmux.kill_session")
    mocker.patch("wt_tool.cli.tmux.has_session", return_value=False)
    mocker.patch("wt_tool.cli.git.get_status_porcelain", return_value="")
    mocker.patch("wt_tool.cli.git.remove_worktree")
    mocker.patch("wt_tool.cli.git.delete_branch")


class TestRmConfirmation:
    def test_single_branch_prompts_before_remove(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        (tmp_path / "wt" / "feat-a").mkdir(parents=True)
        remove_wt = mocker.patch("wt_tool.cli.git.remove_worktree")
        result = runner.invoke(app, ["rm", "feat-a"], input="y\n")
        assert result.exit_code == 0
        remove_wt.assert_called_once()

    def test_single_branch_abort_on_no(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        (tmp_path / "wt" / "feat-a").mkdir(parents=True)
        remove_wt = mocker.patch("wt_tool.cli.git.remove_worktree")
        result = runner.invoke(app, ["rm", "feat-a"], input="n\n")
        assert result.exit_code != 0
        remove_wt.assert_not_called()

    def test_multi_branch_single_confirmation(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        for b in ["feat-a", "feat-b"]:
            (tmp_path / "wt" / b).mkdir(parents=True)
        mocker.patch("wt_tool.cli.display.print_rm_summary")
        result = runner.invoke(app, ["rm", "feat-a", "feat-b"], input="y\n")
        assert result.exit_code == 0
        assert result.output.count("[y/N]") == 1

    def test_non_interactive_skips_confirmation(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        (tmp_path / "wt" / "feat-a").mkdir(parents=True)
        remove_wt = mocker.patch("wt_tool.cli.git.remove_worktree")
        result = runner.invoke(app, ["rm", "feat-a", "--non-interactive"])
        assert result.exit_code == 0
        remove_wt.assert_called_once()

    def test_no_args_non_interactive_exits_1(self, mocker, tmp_path):
        mocker.patch("wt_tool.cli.load_config", return_value=_cfg())
        mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=tmp_path)
        result = runner.invoke(app, ["rm", "--non-interactive"])
        assert result.exit_code == 1


class TestRmFlags:
    def test_nonexistent_worktree_exits_1(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        result = runner.invoke(app, ["rm", "ghost", "--non-interactive"])
        assert result.exit_code == 1

    def test_kills_tmux_session(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        (tmp_path / "wt" / "feat-a").mkdir(parents=True)
        kill = mocker.patch("wt_tool.cli.tmux.kill_session")
        runner.invoke(app, ["rm", "feat-a", "--non-interactive"])
        kill.assert_called_once()

    def test_dirty_aborts_without_force(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        (tmp_path / "wt" / "feat-a").mkdir(parents=True)
        mocker.patch("wt_tool.cli.git.get_status_porcelain", return_value=" M file.py")
        remove_wt = mocker.patch("wt_tool.cli.git.remove_worktree")
        result = runner.invoke(app, ["rm", "feat-a", "--non-interactive"])
        assert result.exit_code == 1
        remove_wt.assert_not_called()

    def test_dirty_proceeds_with_force(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        (tmp_path / "wt" / "feat-a").mkdir(parents=True)
        mocker.patch("wt_tool.cli.git.get_status_porcelain", return_value=" M file.py")
        remove_wt = mocker.patch("wt_tool.cli.git.remove_worktree")
        result = runner.invoke(app, ["rm", "feat-a", "--force", "--non-interactive"])
        assert result.exit_code == 0
        remove_wt.assert_called_once()

    def test_active_session_warning_shown(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        (tmp_path / "wt" / "feat-a").mkdir(parents=True)
        mocker.patch("wt_tool.cli.tmux.has_session", return_value=True)
        result = runner.invoke(app, ["rm", "feat-a", "--non-interactive"], catch_exceptions=False)
        assert result.exit_code == 0
        combined = (result.output or "") + (getattr(result, "stderr", "") or "")
        assert "active" in combined.lower() or "session" in combined.lower()

    def test_self_deletion_guard(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        wt_path = tmp_path / "wt" / "feat-a"
        wt_path.mkdir(parents=True)
        mocker.patch("wt_tool.cli.os.getcwd", return_value=str(wt_path))
        result = runner.invoke(app, ["rm", "feat-a", "--non-interactive"])
        assert result.exit_code == 1

    def test_multi_self_deletion_skips_cwd_continues_rest(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        cwd_wt = tmp_path / "wt" / "feat-a"
        cwd_wt.mkdir(parents=True)
        (tmp_path / "wt" / "feat-b").mkdir(parents=True)
        mocker.patch("wt_tool.cli.os.getcwd", return_value=str(cwd_wt))
        delete_br = mocker.patch("wt_tool.cli.git.delete_branch")
        runner.invoke(app, ["rm", "feat-a", "feat-b", "--non-interactive"])
        deleted = [c[0][1] for c in delete_br.call_args_list]
        assert "feat-b" in deleted
        assert "feat-a" not in deleted

    def test_exit_code_0_all_succeed(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        for b in ["feat-a", "feat-b"]:
            (tmp_path / "wt" / b).mkdir(parents=True)
        result = runner.invoke(app, ["rm", "feat-a", "feat-b", "--non-interactive"])
        assert result.exit_code == 0

    def test_exit_code_1_nothing_removed(self, mocker, tmp_path):
        _setup(mocker, tmp_path)
        result = runner.invoke(app, ["rm", "feat-a", "feat-b", "--non-interactive"])
        assert result.exit_code == 1
