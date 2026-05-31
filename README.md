# wt

Turn git branches into isolated, persistent development environments.

`wt` pairs each git worktree with a tmux session — three windows pre-configured
for terminal work, deployment, and an AI agent. Switch between branches instantly
without losing running processes, staged changes, or shell history.

```
wt new 264-auth-flow main    # new branch → worktree + tmux session
wt open                      # table picker: branch, state, sync, age
wt global                    # same table picker across all repos
wt status                    # health check: dirty, sync, age, sessions
```

---

## Why

git stash → switch branch → rebuild → re-stash is expensive. Worktrees solve
the filesystem problem but leave you managing sessions by hand. `wt` automates
both: one command creates the worktree, opens the tmux session, and starts your
agent in a dedicated window.

---

## Requirements

| Tool | Version | Purpose |
|------|---------|---------|
| Python | ≥ 3.11 | runtime |
| git | ≥ 2.15 | worktree support |
| tmux | ≥ 3.2 | session management |
| uv | any | installation |

Install dependencies on macOS:

```bash
brew install git tmux uv
```

---

## Installation

```bash
uv tool install git+https://github.com/aamarin/wt-tool
```

Verify:

```bash
wt --help
```

### Upgrading

```bash
uv tool upgrade wt-tool
```

### Uninstalling

```bash
uv tool uninstall wt-tool
```

---

## Agent skill

Install the `using-wt` skill so your AI agent knows how to use the tool:

```bash
wt install agent-skill
```

Defaults to `~/.agents/skills/`. Override once with `--path`:

```bash
wt install agent-skill --path ~/.claude/skills/
```

The chosen path is saved to `~/.config/wt/config.json` — subsequent installs
(e.g. after upgrading) reuse it without prompting.

---

## Development install

```bash
git clone https://github.com/aamarin/wt-tool
cd wt-tool
uv tool install --editable .
```

Changes to source take effect immediately — no reinstall needed.

Run tests:

```bash
uv run pytest tests/ -v
```

---

## How it works

```
repo/
├── .git/
├── src/                   ← main worktree (your existing checkout)
└── wt/
    ├── 264-auth-flow/     ← wt new 264-auth-flow
    ├── 302-api-refactor/  ← wt new 302-api-refactor
    └── fix-login-bug/     ← wt new fix-login-bug
```

Each worktree gets a tmux session with three windows:

| Window | Purpose |
|--------|---------|
| `term` | General terminal, cwd set to worktree root |
| `deploy` | Long-running dev server or build process |
| `agent` | AI agent (default: `claude`) |

Sessions persist across detaches. Re-running `wt open` reconnects to the
existing session — running processes are untouched.

---

## Commands

### `wt new [branch...] [base]`

Create one or more new worktrees and tmux sessions.

```bash
wt new 264-auth-flow              # shows Rich table to pick base branch
wt new 264-auth-flow main         # base branch specified as last positional
wt new 264-auth-flow --base main  # explicit --base/-b flag
wt new feat-a feat-b main         # multiple branches from same base (last positional = base)
wt new feat-a feat-b --base main  # same via --base/-b flag
```

- Fetches all remotes before creating
- Creates each worktree at `{repo-root}/wt/{branch}/`
- Single branch: creates tmux session and attaches; multi-branch: prints paths instead

### `wt open [branch]`

Open an existing worktree session. Running `wt` with no arguments is equivalent.

```bash
wt                            # same as wt open
wt open                       # Rich table with branch, state, sync, age — select by # or name
wt open 264-auth-flow         # open directly by name
```

Worktrees missing on disk show `✗ missing` and cannot be selected; run `wt prune` to remove them.

### `wt global [repo/branch]`

Select across all repos under `WT_PROJECTS_DIR`.

```bash
wt global                     # Rich table across all managed repos — entries as repo/branch
wt global myrepo/264-auth     # open directly
```

Sessions are namespaced per repo (`repo__branch`) so same-named branches
across repos never collide.

### `wt status`

Show health of all worktrees in the current repo.

```
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━┳━━━━━━━━━┓
┃ Branch             ┃ State ┃ Sync ┃ Age ┃ Session ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━╇━━━━━━━━━┩
│ 264-auth-flow      │  ⚠    │ ↓2   │ 3h  │   🟢    │
│ 302-api-refactor   │  ✅   │  -   │ 1d  │   ⚪    │
│ fix-login-bug      │  ✅   │ ↑1   │ 20m │   🟢    │
└────────────────────┴───────┴──────┴─────┴─────────┘
```

| Column | Meaning |
|--------|---------|
| State | ⚠ dirty working tree / ✅ clean |
| Sync | ↑N ahead, ↓N behind, ⇅ diverged, - in sync |
| Age | time since last commit |
| Session | 🟢 tmux session active / ⚪ inactive |

### `wt ls`

List all worktrees in the current repo.

```bash
wt ls
```

### `wt rm [branch...]`

Remove one or more worktrees, delete branches, and kill tmux sessions.

```bash
wt rm                                           # interactive picker — select from Rich table
wt rm 264-auth-flow                             # prompts for confirmation
wt rm 264-auth-flow --non-interactive           # skip confirmation
wt rm feat-a feat-b feat-c                      # remove multiple; single confirmation with summary
wt rm feat-a feat-b --non-interactive           # skip confirmation
wt rm 264-auth-flow --force                     # skip dirty check (uncommitted changes OK)
```

Cannot remove a worktree you are currently inside — it is skipped with an error in multi-branch mode.

### `wt prune`

Clean up stale worktree references (runs `git worktree prune`).

```bash
wt prune
```

---

## Configuration

### Persistent config (recommended)

Use `wt config set` to save values to `~/.config/wt/config.json`:

```bash
wt config set agent-cmd "claude --model claude-opus-4-7"
wt config set projects-dir ~/Work
wt config show   # inspect current values
```

### Environment variables

Env vars take precedence over saved config. Add to your shell profile for
machine-level overrides:

```bash
export WT_DIR_NAME="wt"              # worktree directory name (default: wt)
export WT_PROJECTS_DIR="$HOME/Development"  # root for wt global
export WT_AGENT_CMD="claude"         # agent window command
```

### Disabling agent auto-launch

The agent window is always created. To leave it at a bare shell (no command sent):

```bash
wt config set agent-cmd ""
# or: export WT_AGENT_CMD=""
```

---

## Shell integration (optional)

Add a shell function to `cd` into a worktree in your current shell:

```bash
# ~/.zshrc or ~/.bashrc
function wo() {
  local path
  path=$(wt open "$1" --non-interactive) && cd "$path"
}
```

```bash
wo 264-auth-flow    # cd into that worktree
```

---

## Architecture

```
wt_tool/
├── cli.py       # typer app — thin command handlers
├── config.py    # env var resolution
├── git.py       # porcelain parser + subprocess wrappers
├── tmux.py      # session lifecycle; attach via os.execvp
└── display.py   # rich tables
```

Python handles orchestration and parsing. `git` and `tmux` are invoked
as subprocesses — not reimplemented.

---

## Testing

```bash
uv run pytest tests/ -v
```

Pure functions (porcelain parser, ahead/behind regex, config defaults) are tested
without mocking. Subprocess boundaries (tmux, git) are tested with
`pytest-mock`.

---

## Contributing

1. Fork and clone
2. `uv tool install --editable .`
3. Make changes — tests run with `uv run pytest`
4. Open a PR

Please open an issue before starting significant work.

---

## License

MIT
