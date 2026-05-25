from unittest.mock import MagicMock, patch

import pytest

from wt.fzf import run_fzf, FzfAborted


class TestRunFzf:
    def test_returns_selected_line(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "main\n"
        with patch("subprocess.run", return_value=mock_result):
            result = run_fzf(["main", "dev", "feature"])
        assert result == "main"

    def test_strips_whitespace(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  main  \n"
        with patch("subprocess.run", return_value=mock_result):
            result = run_fzf(["main"])
        assert result == "main"

    def test_raises_on_user_cancel(self):
        mock_result = MagicMock()
        mock_result.returncode = 130  # Escape / Ctrl-C
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(FzfAborted):
                run_fzf(["main"])

    def test_raises_on_no_match(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(FzfAborted):
                run_fzf([])

    def test_passes_choices_as_stdin(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "main\n"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            run_fzf(["main", "dev"])
            _, kwargs = mock_run.call_args
            assert kwargs["input"] == "main\ndev"

    def test_preview_cmd_included(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "main\n"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            run_fzf(["main"], preview_cmd="echo {}")
            args = mock_run.call_args[0][0]
            assert "--preview" in args
            assert "echo {}" in args

    def test_delimiter_and_with_nth(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "main|/path\n"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            run_fzf(["main|/path"], delimiter="|", with_nth="1")
            args = mock_run.call_args[0][0]
            assert "--delimiter" in args
            assert "|" in args
            assert "--with-nth" in args
            assert "1" in args
