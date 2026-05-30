from pathlib import Path


# ── Shared fakes ──────────────────────────────────────────────────────────────

def _make_session_name(repo, branch):
    return f"{repo}__{branch}"


class FakeTmux:
    def __init__(self):
        self.created: list[str] = []
        self.killed: list[str] = []

    def ensure_session(self, session, path, agent_cmd):
        self.created.append(session)

    def kill_session(self, session):
        self.killed.append(session)

    def has_session(self, session):
        return False


class FakeGit:
    def __init__(self, tmp_path: Path, *, dirty_branches: set | None = None, fail_on: set | None = None):
        self.tmp_path = tmp_path
        self.dirty_branches = dirty_branches or set()
        self.fail_on = fail_on or set()
        self.added: list[str] = []
        self.removed: list[str] = []
        self.deleted: list[str] = []

    def add_worktree(self, root, branch, wt_path, base):
        if branch in self.fail_on:
            raise SystemExit(1)
        wt_path.mkdir(parents=True, exist_ok=True)
        self.added.append(branch)

    def remove_worktree(self, root, wt_path):
        branch = wt_path.name
        if branch in self.fail_on:
            raise SystemExit(1)
        self.removed.append(branch)

    def delete_branch(self, root, branch):
        self.deleted.append(branch)

    def get_status_porcelain(self, wt_path):
        return " M file.py" if wt_path.name in self.dirty_branches else ""


# ── create_worktrees tests ────────────────────────────────────────────────────

class TestCreateWorktrees:
    def test_happy_path_single(self, tmp_path):
        from wt_tool.operations import create_worktrees
        git = FakeGit(tmp_path)
        tmux = FakeTmux()
        successes, failures = create_worktrees(
            ["feat-a"], "main", tmp_path, "wt", "repo", "claude",
            add_worktree_fn=git.add_worktree,
            ensure_session_fn=tmux.ensure_session,
            make_session_name_fn=_make_session_name,
        )
        assert successes == ["feat-a"]
        assert failures == []
        assert git.added == ["feat-a"]
        assert tmux.created == ["repo__feat-a"]

    def test_happy_path_multi(self, tmp_path):
        from wt_tool.operations import create_worktrees
        git = FakeGit(tmp_path)
        tmux = FakeTmux()
        successes, failures = create_worktrees(
            ["feat-a", "feat-b", "feat-c"], "main", tmp_path, "wt", "repo", "claude",
            add_worktree_fn=git.add_worktree,
            ensure_session_fn=tmux.ensure_session,
            make_session_name_fn=_make_session_name,
        )
        assert successes == ["feat-a", "feat-b", "feat-c"]
        assert failures == []
        assert len(tmux.created) == 3

    def test_already_exists_skipped(self, tmp_path):
        from wt_tool.operations import create_worktrees
        (tmp_path / "wt" / "feat-a").mkdir(parents=True)
        git = FakeGit(tmp_path)
        tmux = FakeTmux()
        successes, failures = create_worktrees(
            ["feat-a", "feat-b"], "main", tmp_path, "wt", "repo", "claude",
            add_worktree_fn=git.add_worktree,
            ensure_session_fn=tmux.ensure_session,
            make_session_name_fn=_make_session_name,
        )
        assert successes == ["feat-b"]
        assert failures == ["feat-a"]

    def test_partial_failure_continues(self, tmp_path):
        from wt_tool.operations import create_worktrees
        git = FakeGit(tmp_path, fail_on={"feat-a"})
        tmux = FakeTmux()
        successes, failures = create_worktrees(
            ["feat-a", "feat-b"], "main", tmp_path, "wt", "repo", "claude",
            add_worktree_fn=git.add_worktree,
            ensure_session_fn=tmux.ensure_session,
            make_session_name_fn=_make_session_name,
        )
        assert successes == ["feat-b"]
        assert failures == ["feat-a"]

    def test_all_fail_returns_empty_successes(self, tmp_path):
        from wt_tool.operations import create_worktrees
        git = FakeGit(tmp_path, fail_on={"feat-a", "feat-b"})
        tmux = FakeTmux()
        successes, failures = create_worktrees(
            ["feat-a", "feat-b"], "main", tmp_path, "wt", "repo", "claude",
            add_worktree_fn=git.add_worktree,
            ensure_session_fn=tmux.ensure_session,
            make_session_name_fn=_make_session_name,
        )
        assert successes == []
        assert set(failures) == {"feat-a", "feat-b"}


# ── remove_worktrees tests ────────────────────────────────────────────────────

class TestRemoveWorktrees:
    def _make_wt(self, tmp_path, *branches):
        for b in branches:
            (tmp_path / "wt" / b).mkdir(parents=True)

    def test_happy_path_single(self, tmp_path):
        from wt_tool.operations import remove_worktrees
        self._make_wt(tmp_path, "feat-a")
        git = FakeGit(tmp_path)
        tmux = FakeTmux()
        successes, failures, skipped = remove_worktrees(
            ["feat-a"], tmp_path, "wt", "repo", tmp_path,
            get_status_fn=git.get_status_porcelain,
            has_session_fn=tmux.has_session,
            remove_worktree_fn=git.remove_worktree,
            delete_branch_fn=git.delete_branch,
            kill_session_fn=tmux.kill_session,
            make_session_name_fn=_make_session_name,
        )
        assert successes == ["feat-a"]
        assert failures == []
        assert skipped == []
        assert git.deleted == ["feat-a"]

    def test_happy_path_multi(self, tmp_path):
        from wt_tool.operations import remove_worktrees
        self._make_wt(tmp_path, "feat-a", "feat-b", "feat-c")
        git = FakeGit(tmp_path)
        tmux = FakeTmux()
        successes, failures, skipped = remove_worktrees(
            ["feat-a", "feat-b", "feat-c"], tmp_path, "wt", "repo", tmp_path,
            get_status_fn=git.get_status_porcelain,
            has_session_fn=tmux.has_session,
            remove_worktree_fn=git.remove_worktree,
            delete_branch_fn=git.delete_branch,
            kill_session_fn=tmux.kill_session,
            make_session_name_fn=_make_session_name,
        )
        assert successes == ["feat-a", "feat-b", "feat-c"]
        assert failures == []

    def test_nonexistent_path_skipped(self, tmp_path):
        from wt_tool.operations import remove_worktrees
        git = FakeGit(tmp_path)
        tmux = FakeTmux()
        successes, failures, skipped = remove_worktrees(
            ["ghost"], tmp_path, "wt", "repo", tmp_path,
            get_status_fn=git.get_status_porcelain,
            has_session_fn=tmux.has_session,
            remove_worktree_fn=git.remove_worktree,
            delete_branch_fn=git.delete_branch,
            kill_session_fn=tmux.kill_session,
            make_session_name_fn=_make_session_name,
        )
        assert successes == []
        assert skipped == ["ghost"]

    def test_self_deletion_guard_skips_branch(self, tmp_path):
        from wt_tool.operations import remove_worktrees
        cwd_wt = tmp_path / "wt" / "feat-a"
        self._make_wt(tmp_path, "feat-a", "feat-b")
        git = FakeGit(tmp_path)
        tmux = FakeTmux()
        successes, failures, skipped = remove_worktrees(
            ["feat-a", "feat-b"], tmp_path, "wt", "repo", cwd_wt,
            get_status_fn=git.get_status_porcelain,
            has_session_fn=tmux.has_session,
            remove_worktree_fn=git.remove_worktree,
            delete_branch_fn=git.delete_branch,
            kill_session_fn=tmux.kill_session,
            make_session_name_fn=_make_session_name,
        )
        assert "feat-b" in successes
        assert "feat-a" in skipped
        assert "feat-a" not in git.deleted

    def test_dirty_branch_skipped_without_force(self, tmp_path):
        from wt_tool.operations import remove_worktrees
        self._make_wt(tmp_path, "feat-a", "feat-b")
        git = FakeGit(tmp_path, dirty_branches={"feat-a"})
        tmux = FakeTmux()
        successes, failures, skipped = remove_worktrees(
            ["feat-a", "feat-b"], tmp_path, "wt", "repo", tmp_path,
            get_status_fn=git.get_status_porcelain,
            has_session_fn=tmux.has_session,
            remove_worktree_fn=git.remove_worktree,
            delete_branch_fn=git.delete_branch,
            kill_session_fn=tmux.kill_session,
            make_session_name_fn=_make_session_name,
        )
        assert "feat-b" in successes
        assert "feat-a" in failures
        assert "feat-a" not in git.deleted

    def test_dirty_branch_proceeds_with_force(self, tmp_path):
        from wt_tool.operations import remove_worktrees
        self._make_wt(tmp_path, "feat-a")
        git = FakeGit(tmp_path, dirty_branches={"feat-a"})
        tmux = FakeTmux()
        successes, failures, skipped = remove_worktrees(
            ["feat-a"], tmp_path, "wt", "repo", tmp_path, force=True,
            get_status_fn=git.get_status_porcelain,
            has_session_fn=tmux.has_session,
            remove_worktree_fn=git.remove_worktree,
            delete_branch_fn=git.delete_branch,
            kill_session_fn=tmux.kill_session,
            make_session_name_fn=_make_session_name,
        )
        assert successes == ["feat-a"]
        assert failures == []

    def test_partial_failure_continues(self, tmp_path):
        from wt_tool.operations import remove_worktrees
        self._make_wt(tmp_path, "feat-a", "feat-b")
        git = FakeGit(tmp_path, fail_on={"feat-a"})
        tmux = FakeTmux()
        successes, failures, skipped = remove_worktrees(
            ["feat-a", "feat-b"], tmp_path, "wt", "repo", tmp_path,
            get_status_fn=git.get_status_porcelain,
            has_session_fn=tmux.has_session,
            remove_worktree_fn=git.remove_worktree,
            delete_branch_fn=git.delete_branch,
            kill_session_fn=tmux.kill_session,
            make_session_name_fn=_make_session_name,
        )
        assert "feat-b" in successes
        assert "feat-a" in failures
