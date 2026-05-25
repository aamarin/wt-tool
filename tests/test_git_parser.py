from pathlib import Path

from wt.git import parse_worktrees, parse_ahead_behind

PORCELAIN_NORMAL = """\
worktree /Users/andremarin/Development/pfms
HEAD abc123def456abc123def456abc123def456abc12
branch refs/heads/main

worktree /Users/andremarin/Development/pfms/wt/264-admin
HEAD def456abc123def456abc123def456abc123def45
branch refs/heads/264-admin

worktree /Users/andremarin/Development/pfms/wt/302-feature
HEAD 789abc123def456abc123def456abc123def456ab
branch refs/heads/302-feature

"""

PORCELAIN_DETACHED = """\
worktree /Users/andremarin/Development/pfms
HEAD abc123def456abc123def456abc123def456abc12
branch refs/heads/main

worktree /Users/andremarin/Development/pfms/wt/detached-head
HEAD def456abc123def456abc123def456abc123def45
detached

"""

PORCELAIN_BARE = """\
worktree /Users/andremarin/Development/pfms
HEAD abc123def456abc123def456abc123def456abc12
bare

"""


class TestParseWorktrees:
    def test_parses_branch_names(self):
        result = parse_worktrees(PORCELAIN_NORMAL)
        assert len(result) == 3
        assert result[0].branch == "main"
        assert result[1].branch == "264-admin"
        assert result[2].branch == "302-feature"

    def test_parses_paths(self):
        result = parse_worktrees(PORCELAIN_NORMAL)
        assert result[1].path == Path("/Users/andremarin/Development/pfms/wt/264-admin")

    def test_parses_head_sha(self):
        result = parse_worktrees(PORCELAIN_NORMAL)
        assert result[0].head == "abc123def456abc123def456abc123def456abc12"

    def test_detached_head_branch_is_none(self):
        # This is the AWK bug case — detached HEAD must not inherit previous branch value
        result = parse_worktrees(PORCELAIN_DETACHED)
        assert result[1].branch is None

    def test_bare_worktree(self):
        result = parse_worktrees(PORCELAIN_BARE)
        assert result[0].bare is True
        assert result[0].branch is None

    def test_strips_refs_heads_prefix(self):
        result = parse_worktrees(PORCELAIN_NORMAL)
        assert not any(b.startswith("refs/") for b in [result[0].branch, result[1].branch] if b)

    def test_empty_output(self):
        assert parse_worktrees("") == []

    def test_no_trailing_newline(self):
        # should handle output without final blank line
        stripped = PORCELAIN_NORMAL.rstrip("\n")
        result = parse_worktrees(stripped)
        assert len(result) == 3


class TestParseAheadBehind:
    def test_ahead_only(self):
        assert parse_ahead_behind("## main...origin/main [ahead 3]") == (3, 0)

    def test_behind_only(self):
        assert parse_ahead_behind("## main...origin/main [behind 5]") == (0, 5)

    def test_both(self):
        assert parse_ahead_behind("## main...origin/main [ahead 2, behind 4]") == (2, 4)

    def test_neither(self):
        assert parse_ahead_behind("## main...origin/main") == (0, 0)

    def test_no_tracking_branch(self):
        assert parse_ahead_behind("## main") == (0, 0)
