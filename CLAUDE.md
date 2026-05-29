# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Development install (edits take effect immediately)
uv tool install --editable .

# Run all tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_git_parser.py -v

# Run a single test by name
uv run pytest tests/test_tmux.py::TestMakeSessionName::test_sanitizes_colons -v
```

## Architecture

`wt` is a CLI tool that pairs git worktrees with tmux sessions. It is installed as the `wt` binary via `uv tool install`.

**Module responsibilities:**

- `cli.py` — Typer app with all commands (`new`, `open`, `rm`, `ls`, `status`, `prune`, `global`, `config set/show`, `install agent-skill`). Thin handlers that delegate to the other modules. Shell completion is enabled; custom `autocompletion=` callbacks in `open`, `rm`, `new`, and `global` provide branch/target completions using silent git helpers that never print to stderr.
- `config.py` — Config resolution: env vars take precedence over `~/.config/wt/config.json`. `load_config()` always returns a fully-resolved `Config` dataclass; individual `resolve_*()` functions return `None` when a value was never explicitly set (used to detect first-run prompts).
- `git.py` — Two layers: a pure `parse_worktrees()` function that parses `git worktree list --porcelain` output (no subprocess, fully testable), and subprocess wrappers for git operations. `_run()` calls `typer.Exit(1)` on failure.
- `tmux.py` — Session lifecycle. Each worktree gets a session with three windows: `term`, `deploy`, `agent`. `attach()` uses `os.execvp` to replace the current process with tmux (switches client if already inside tmux, otherwise attaches).
- `fzf.py` — Thin wrapper around the `fzf` binary. Raises `FzfAborted` on exit codes 1 or 130 (no selection / Ctrl-C).
- `display.py` — Rich tables and status messages. Errors go to `err_console` (stderr); success/info go to `console` (stdout).

**Worktree layout convention:**

```
repo-root/
├── .git/
└── wt/           ← controlled by WT_DIR_NAME (default: "wt")
    ├── branch-a/
    └── branch-b/
```

`wt global` scans `WT_PROJECTS_DIR` for `*/wt/` directories and namespaces tmux sessions as `{repo}__{branch}` to avoid cross-repo collisions.

### Picker UI

`wt open` and `wt global` use a Rich table + numbered prompt (not fzf). The table shows `# | Branch | State | Sync | Age | Path` with live status. Missing/stale worktree paths render as `✗ missing` and cannot be selected — the user is told to run `wt prune`.

`wt new` is the only command that uses fzf — for interactive base-branch selection when the base is not supplied as an argument.

### Agent skill

The `using-wt` skill in `wt_tool/skills/using-wt/` is bundled in the package and installed via `wt install agent-skill`. The install destination is saved to `agent_skills_dir` in the config file so upgrades reuse it.

## Testing approach

Pure functions (`parse_worktrees`, `parse_ahead_behind`, config defaults) are tested without mocking. Subprocess boundaries (`tmux`, `fzf`, `git`) are tested with `pytest-mock`. The test suite does not hit a real filesystem or real git repo for unit tests.

## Config file

`~/.config/wt/config.json` — keys: `agent_cmd`, `projects_dir`, `agent_skills_dir`. Env vars (`WT_AGENT_CMD`, `WT_PROJECTS_DIR`, `WT_DIR_NAME`) override file values at runtime.
