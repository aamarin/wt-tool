import time

from wt_tool.display import (
    OpenRow,
    _format_age,
    _format_sync,
    print_branch_table,
    print_open_table,
)


def _row(label: str, **kwargs) -> OpenRow:
    defaults = dict(
        path=f"/repo/wt/{label}",
        is_dirty=False,
        ahead=0,
        behind=0,
        last_commit_ts=0,
        is_missing=False,
    )
    defaults.update(kwargs)
    return OpenRow(label=label, **defaults)


class TestPrintBranchTable:
    def test_renders_without_error(self):
        print_branch_table(["main", "develop", "feat/x"])

    def test_single_branch(self):
        print_branch_table(["main"])

    def test_empty_list(self):
        print_branch_table([])


class TestPrintOpenTable:
    def test_renders_without_error(self):
        rows = [_row("feat/a"), _row("fix/b"), _row("chore/c")]
        print_open_table(rows)

    def test_single_row(self):
        print_open_table([_row("main")])

    def test_missing_row(self):
        print_open_table([_row("stale-branch", is_missing=True)])

    def test_dirty_row(self):
        print_open_table([_row("feat/wip", is_dirty=True)])

    def test_mixed_status(self):
        rows = [
            _row(
                "feat/a",
                is_dirty=True,
                ahead=2,
                last_commit_ts=int(time.time()) - 3600,
            ),
            _row("fix/b", behind=1, last_commit_ts=int(time.time()) - 86400),
            _row("stale", is_missing=True),
        ]
        print_open_table(rows)

    def test_global_style_labels(self):
        rows = [
            _row("myrepo/feat/a"),
            _row("other-repo/main"),
        ]
        print_open_table(rows)


class TestFormatSync:
    def test_ahead_only(self):
        assert "↑3" in _format_sync(3, 0)

    def test_behind_only(self):
        assert "↓5" in _format_sync(0, 5)

    def test_diverged(self):
        result = _format_sync(2, 4)
        assert "2↑" in result
        assert "4↓" in result

    def test_in_sync(self):
        assert _format_sync(0, 0) == "[dim]-[/dim]"


class TestFormatAge:
    def test_no_timestamp(self):
        assert _format_age(0, 1000, 259200) == "[dim]-[/dim]"

    def test_recent(self):
        now = int(time.time())
        result = _format_age(now - 3600, now, 259200)
        assert "h" in result

    def test_stale_highlighted(self):
        now = int(time.time())
        ts = now - (4 * 24 * 3600)
        result = _format_age(ts, now, 259200)
        assert "yellow" in result
