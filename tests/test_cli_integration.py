import subprocess
from pathlib import Path
import pytest
from typer.testing import CliRunner
from wt_tool.cli import app
from wt_tool.config import Config

runner = CliRunner()


@pytest.fixture
def git_repo(tmp_path):
    """Real git repo with one empty commit on the default branch."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    result = subprocess.run(["git", "branch", "--show-current"], cwd=tmp_path, capture_output=True, text=True, check=True)
    default_branch = result.stdout.strip()
    return tmp_path, default_branch


def _mock_tmux(mocker):
    mocker.patch("wt_tool.cli.tmux.ensure_session")
    mocker.patch("wt_tool.cli.tmux.kill_session")
    mocker.patch("wt_tool.cli.tmux.has_session", return_value=False)
    mocker.patch("wt_tool.cli.tmux.attach")


def _cfg(root):
    return Config(wt_dir_name="wt", projects_dir=root.parent, agent_cmd="claude")


class TestNewIntegration:
    def test_creates_single_worktree_on_disk(self, mocker, git_repo):
        root, base = git_repo
        mocker.patch("wt_tool.cli.load_config", return_value=_cfg(root))
        mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=root)
        mocker.patch("wt_tool.cli.resolve_agent_cmd", return_value="claude")
        _mock_tmux(mocker)
        result = runner.invoke(app, ["new", "feat-a", base, "--non-interactive"])
        assert result.exit_code == 0
        assert (root / "wt" / "feat-a").is_dir()

    def test_creates_multiple_worktrees_on_disk(self, mocker, git_repo):
        root, base = git_repo
        mocker.patch("wt_tool.cli.load_config", return_value=_cfg(root))
        mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=root)
        mocker.patch("wt_tool.cli.resolve_agent_cmd", return_value="claude")
        _mock_tmux(mocker)
        result = runner.invoke(app, ["new", "feat-a", "feat-b", base, "--non-interactive"])
        assert result.exit_code == 0
        assert (root / "wt" / "feat-a").is_dir()
        assert (root / "wt" / "feat-b").is_dir()

    def test_already_exists_skipped_exits_1(self, mocker, git_repo):
        root, base = git_repo
        mocker.patch("wt_tool.cli.load_config", return_value=_cfg(root))
        mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=root)
        mocker.patch("wt_tool.cli.resolve_agent_cmd", return_value="claude")
        _mock_tmux(mocker)
        runner.invoke(app, ["new", "feat-a", base, "--non-interactive"])
        result = runner.invoke(app, ["new", "feat-a", base, "--non-interactive"])
        assert result.exit_code == 1

    def test_creates_session_per_branch(self, mocker, git_repo):
        root, base = git_repo
        mocker.patch("wt_tool.cli.load_config", return_value=_cfg(root))
        mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=root)
        mocker.patch("wt_tool.cli.resolve_agent_cmd", return_value="claude")
        ensure = mocker.patch("wt_tool.cli.tmux.ensure_session")
        mocker.patch("wt_tool.cli.tmux.kill_session")
        mocker.patch("wt_tool.cli.tmux.has_session", return_value=False)
        mocker.patch("wt_tool.cli.tmux.attach")
        runner.invoke(app, ["new", "feat-a", "feat-b", base, "--non-interactive"])
        assert ensure.call_count == 2


class TestRmIntegration:
    def _create_wt(self, root, branch):
        subprocess.run(
            ["git", "worktree", "add", str(root / "wt" / branch), "-b", branch],
            cwd=root, check=True, capture_output=True,
        )

    def test_removes_single_worktree_from_disk(self, mocker, git_repo):
        root, base = git_repo
        mocker.patch("wt_tool.cli.load_config", return_value=_cfg(root))
        mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=root)
        mocker.patch("wt_tool.cli.tmux.kill_session")
        mocker.patch("wt_tool.cli.tmux.has_session", return_value=False)
        self._create_wt(root, "feat-a")
        assert (root / "wt" / "feat-a").is_dir()
        result = runner.invoke(app, ["rm", "feat-a", "--non-interactive"])
        assert result.exit_code == 0
        assert not (root / "wt" / "feat-a").exists()

    def test_removes_multiple_worktrees_from_disk(self, mocker, git_repo):
        root, base = git_repo
        mocker.patch("wt_tool.cli.load_config", return_value=_cfg(root))
        mocker.patch("wt_tool.cli.git.get_main_worktree_root", return_value=root)
        mocker.patch("wt_tool.cli.tmux.kill_session")
        mocker.patch("wt_tool.cli.tmux.has_session", return_value=False)
        for b in ["feat-a", "feat-b"]:
            self._create_wt(root, b)
        result = runner.invoke(app, ["rm", "feat-a", "feat-b", "--non-interactive"])
        assert result.exit_code == 0
        assert not (root / "wt" / "feat-a").exists()
        assert not (root / "wt" / "feat-b").exists()
