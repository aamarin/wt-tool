# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev install (changes take effect without reinstall)
uv tool install --editable .

# Run all tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_git_parser.py -v

# Run a single test
uv run pytest tests/test_git_parser.py::TestParseWorktrees::test_detached_head_branch_is_none -v
```

## Architecture

```
wt_tool/
├── cli.py       # typer app — thin command handlers, all user-facing logic
├── config.py    # Config dataclass; env vars take precedence over config file
├── git.py       # porcelain parser + subprocess wrappers
├── tmux.py      # session lifecycle; attach via os.execvp (replaces process)
├── fzf.py       # interactive picker wrapper (used only by wt new for base-branch selection)
└── display.py   # rich tables and styled output
```

`wt` pairs each git worktree with a tmux session. The worktree layout is `{repo-root}/wt/{branch}/`. Sessions for `wt global` are namespaced `{repo_name}__{branch}` to avoid collisions across repos.

### Picker UI

`wt open` and `wt global` use a Rich table + numbered prompt (not fzf). The table shows `# | Branch | State | Sync | Age | Path` with live status. Missing/stale worktree paths render as `✗ missing` and cannot be selected — the user is told to run `wt prune`.

`wt new` is the only command that uses fzf — for interactive base-branch selection when the base is not supplied as an argument.

### Key design decisions

**Pure functions vs subprocess boundaries.** `parse_worktrees()` and `parse_ahead_behind()` in `git.py` are pure parsers tested without mocking. All subprocess calls (tmux, fzf, git) are isolated at module boundaries and tested with `pytest-mock`.

**Config resolution precedence.** Env vars (`WT_DIR_NAME`, `WT_PROJECTS_DIR`, `WT_AGENT_CMD`) always override `~/.config/wt/config.json`. `load_config()` returns a frozen `Config` dataclass; individual `resolve_*()` functions return `None` when a value was never explicitly set (used to prompt users on first run).

**`--non-interactive` flag.** All commands that touch interactive UI or tmux attach support `--non-interactive`: errors if required args are missing, prints the worktree path to stdout, and skips tmux attach. Used by shell functions (`wo`) to get a path for `cd`.

**`tmux.attach()` uses `os.execvp`.** This replaces the `wt` process with tmux — the calling shell's job control sees tmux directly, not a subprocess.

**tmux session names.** Colons are replaced with dashes because tmux parses `session:window:pane` on the `:` character.

### Configuration

Persistent config lives at `~/.config/wt/config.json`. The `wt config set` command writes individual keys without clobbering others. `agent-cmd` and `projects-dir` are the only user-settable keys; `wt-dir-name` is env-var only (`WT_DIR_NAME`).

### Agent skill

The `using-wt` skill in `wt_tool/skills/using-wt/` is bundled in the package and installed via `wt install agent-skill`. The install destination is saved to `agent_skills_dir` in the config file so upgrades reuse it.
