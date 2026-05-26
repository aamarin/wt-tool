from unittest.mock import MagicMock, patch
from pathlib import Path

from wt_tool.tmux import has_session, make_session_name, ensure_session


class TestHasSession:
    def test_returns_true_when_session_exists(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            assert has_session("my-branch") is True
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "=my-branch" in args  # exact-match prefix

    def test_returns_false_when_session_missing(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            assert has_session("nonexistent") is False

    def test_uses_exact_match_prefix(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            has_session("dev")
            args = mock_run.call_args[0][0]
            # Must use =dev not dev to avoid prefix matching
            assert "=dev" in args
            assert "dev" not in [a for a in args if a == "dev"]


class TestMakeSessionName:
    def test_returns_branch_as_is(self):
        assert make_session_name("264-admin") == "264-admin"
        assert make_session_name("main") == "main"

    def test_no_colons(self):
        name = make_session_name("my-branch")
        assert ":" not in name

    def test_sanitizes_colons(self):
        # tmux interprets colons as session:window:pane separator
        assert make_session_name("feat:my-feature") == "feat-my-feature"
        assert make_session_name("a:b:c") == "a-b-c"


class TestEnsureSession:
    def test_creates_when_missing(self):
        with patch("wt_tool.tmux.has_session", return_value=False) as mock_has, \
             patch("wt_tool.tmux.create_session") as mock_create:
            ensure_session("my-branch", Path("/tmp/path"), "claude")
            mock_create.assert_called_once_with("my-branch", Path("/tmp/path"), "claude")

    def test_skips_when_already_exists(self):
        with patch("wt_tool.tmux.has_session", return_value=True), \
             patch("wt_tool.tmux.create_session") as mock_create:
            ensure_session("my-branch", Path("/tmp/path"), "claude")
            mock_create.assert_not_called()
