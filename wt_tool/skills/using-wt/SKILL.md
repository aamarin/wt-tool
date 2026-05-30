---
name: using-wt
description: Guides correct use of the wt environment management tool. Use when starting work on a new branch, switching between active work streams, inspecting environment health, or when using-git-worktrees Step 1a asks for a native worktree tool.
---

# using-wt: Isolated Development Environments

## Overview

`wt` treats each git branch as a complete, isolated development environment — a linked worktree on the filesystem combined with a persistent tmux session at runtime. Agents work *inside* environments; the environment lifecycle is managed by the human.

## Core Principles

**Isolation** — each branch lives in its own worktree with no shared working directory.

**Persistence** — worktrees and tmux sessions survive between sessions. You can leave and return without losing context.

**Parallelism** — multiple environments can coexist and run independently. Independent tasks can be worked concurrently.

**Stateless design** — `wt` stores no internal registry or metadata. Git, the filesystem, and tmux are the source of truth. Do not look for a state file; inspect them directly.

## Mental Model

```
branch = environment
environment = worktree (wt/<branch>/) + tmux session (<repo>__<branch>)
```

Each environment has:
- **Filesystem isolation**: a git linked worktree at `wt/<branch>/` relative to repo root
- **Runtime isolation**: a tmux session named `<branch>` with three windows:
  - `term` — general terminal work
  - `deploy` — servers, watchers, long-running processes
  - `agent` — agent process; `$WT_AGENT_CMD` (default: `claude`) is launched here automatically on session creation

Worktrees are in `wt/` (not `.worktrees/`). This is intentional — the directory name matches the tool name.

**Session naming:** tmux sessions are named `<repo>__<branch>` (double underscore) for all commands — local and global. This avoids cross-repo collisions when `wt global` spans multiple projects. Colons in branch names are replaced with dashes (tmux parses `session:window:pane` notation). If you see sessions named only `<branch>` without a repo prefix, those are orphans from a pre-unification migration — they are benign and can be killed manually via `tmux kill-session -t <old-name>`.

All commands resolve the main repo root via `git worktree list` (not `git rev-parse --show-toplevel`), so they work correctly whether called from the main repo or from inside a linked worktree.

## tmux vs wt

```
wt   → choose which environment to enter
tmux → operate inside an environment
```

Do not confuse these. `wt open` selects context. tmux window navigation moves within it.

## Commands

Two layers: agent control plane and human UI. Never mix them.

### Agent control plane (no tmux side effects, safe to script)

All commands accept `--non-interactive` to suppress prompts and tmux attach.

```bash
wt ls                                      # list all worktrees: branch name + path
wt status                                  # health: dirty, sync, stale, tmux active
wt prune                                   # cleanup stale worktree refs
wt new <branch> <base> --non-interactive   # create worktree + session, print path
wt open <branch> --non-interactive         # ensure session exists, print path
wt rm <branch> --non-interactive           # remove worktree + branch + session, no confirm
wt global <repo>/<branch> --non-interactive  # ensure session exists, print path
```

`wt open <branch> --non-interactive` is the primary agent entry point for existing worktrees:
```bash
path=$(wt open feature/api --non-interactive)   # prints path to stdout, errors to stderr
cd "$path"
```

`wt status` columns: `branch | dirty(⚠/✅) | sync(↑N/↓N/⇅/-) | lifecycle(stale/-) | runtime(🟢/⚪)`

### Human UI (tmux attach/switch — do not call from agents)

```bash
wt                           # same as wt open (default when no args given)
wt open                      # Rich table picker, attaches tmux session
wt open <branch>             # direct switch to branch, attaches tmux session
wt global                    # Rich table across all repos under WT_PROJECTS_DIR
wt global <repo>/<branch>    # direct cross-repo switch
wt new [branch]              # omitting base shows Rich table to pick base branch
wt rm <branch>               # requires y/N confirm
```

**Config:**
- `WT_PROJECTS_DIR` — root scanned by `wt global` (default: `~/Development`); prompted on first run if unset
- `WT_AGENT_CMD` — command launched in `agent` window on new session creation (default: `claude`)

Both can be persisted to `~/.config/wt/config.json` via `wt config set`:

```bash
wt config set agent-cmd "claude --model claude-opus-4-7"
wt config set projects-dir ~/Work
wt config show   # inspect current values (file + env)
```

Env vars still take precedence over saved config.

**Shell autocomplete:** Tab completion is available for all subcommands, flags, and branch/target arguments. Enable it by adding the appropriate line for your shell to your profile (run `wt --install-completion` to get the snippet).

## Workflows

### Start new work

If you know the base branch, create and enter directly:

```bash
wt new <branch> <base> --non-interactive   # e.g. wt new feature/search dev --non-interactive
path=$(wt open <branch> --non-interactive) # get path, confirm session ready
cd "$path"
```

If you don't know the right base, tell the user:
> "Run `wt new <branch-name>` to create the environment — you'll pick the base branch — then I'll continue."

### Resume existing work

```bash
path=$(wt open <branch> --non-interactive)   # errors if worktree doesn't exist
cd "$path"
```

### Parallel workstreams

Multiple independent environments can coexist. For example, two debugging contexts:

```
wt new debug/api main     → user creates first environment
wt new debug/ui main      → user creates second environment
```

Agents then work in `wt/debug/api/` and `wt/debug/ui/` independently. Use `wt status` to see all active environments and their health at a glance.

### Clean up a finished environment

After a branch is merged — regardless of how (PR, local merge, any tool) — clean up
the worktree and tmux session:

```bash
path=$(wt open <next-branch> --non-interactive)   # move to next environment first
cd "$path"
wt rm <merged-branch> --non-interactive            # removes worktree + branch + tmux session
```

`wt rm` handles all three: filesystem worktree, git branch reference, and tmux session.
Tools that use raw `git worktree remove` + `git branch -d` miss the tmux cleanup —
always use `wt rm` instead.

`wt rm` blocks with an error if `$PWD` is inside the target worktree.

**Orphaned sessions from naming migration:** If `tmux ls` shows sessions named only `<branch>` (without a repo prefix), these are pre-migration orphans. They are harmless — `wt` will not attach to or manage them — but they consume tmux server resources. Kill them manually:

```bash
tmux kill-session -t <old-branch-name>
```

### Inspect before acting

```bash
wt status
```

Check for stale environments, diverged branches, or missing tmux sessions before touching code in an existing environment.

## Rules

**Do:**
- Use `wt open <branch> --non-interactive` to enter an existing worktree — prints path, no tmux attach
- Use `wt new <branch> <base> --non-interactive` to create; errors if worktree already exists
- Use `wt rm <branch> --non-interactive` after `cd`-ing out of the worktree first
- Run `wt ls` and `wt status` freely — read-only
- Tell the user to run `wt open`, `wt global`, and `wt rm` without `--non-interactive` — those are human UI

**Don't:**
- Call `wt open` or `wt global` from agent code — they attach tmux sessions and are human UI
- Run `wt new <branch>` without a base — the interactive picker will block
- Run `wt rm <branch>` from inside that worktree — the self-deletion guard will block it
- Use raw `git worktree add` — it bypasses the tmux session setup
- Look for a wt state file or registry — there is none; git + filesystem + tmux are authoritative
- Create duplicate environments for the same branch — check `wt ls` first

## Relationship to `using-git-worktrees`

When `using-git-worktrees` reaches Step 1a ("is there a native worktree tool?"), the answer is **yes**: `wt new <branch>` is that native tool. Ask the user to run it, skip the git fallback, and skip the `.worktrees/` gitignore check — `wt/` is already handled by the tool.

## Red Flags

- Calling `wt open` or `wt global` from agent code — these attach tmux (human UI layer)
- Calling `wt new <branch>` without a base — the interactive picker will block; always supply both args
- Calling `wt rm` without `--non-interactive` from agent code — requires interactive confirmation
- Using `wt open <branch> --non-interactive` on a branch with no existing worktree — it errors; use `wt new <branch> <base> --non-interactive` to create first
- Using `git worktree add` directly — tmux session won't be created
- Looking for worktrees under `.worktrees/` — they live under `wt/`
- Assuming a tmux session exists without checking `wt status` runtime column (🟢/⚪)
- Reusing one branch for unrelated tasks — breaks isolation, the core invariant
- Using `wt global <repo>/<branch>` with a branch that lives only in the main worktree, not under `wt/` — global only shows managed worktrees, not the main checkout
