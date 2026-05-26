from pathlib import Path

from wt_tool.display import print_open_table
from wt_tool.git import WorktreeInfo


def _wt(branch: str) -> WorktreeInfo:
    return WorktreeInfo(path=Path(f"/repo/wt/{branch}"), head="abc123", branch=branch)


class TestPrintOpenTable:
    def test_returns_branches_in_order(self):
        worktrees = [_wt("feat/a"), _wt("fix/b"), _wt("chore/c")]
        branches = print_open_table(worktrees)
        assert branches == ["feat/a", "fix/b", "chore/c"]

    def test_single_worktree(self):
        branches = print_open_table([_wt("main")])
        assert branches == ["main"]

    def test_detached_head(self):
        wt = WorktreeInfo(path=Path("/repo/wt/detached"), head="abc123", branch=None)
        branches = print_open_table([wt])
        assert branches == ["detached"]
