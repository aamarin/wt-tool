import os
import subprocess
from pathlib import Path


def make_session_name(branch: str) -> str:
    # tmux parses colons as session:window:pane — use branch only for now
    return branch


def has_session(session: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", f"={session}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def create_session(session: str, path: Path, agent_cmd: str) -> None:
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session, "-n", "term", "-c", str(path)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["tmux", "new-window", "-t", session, "-n", "deploy", "-c", str(path)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["tmux", "new-window", "-t", session, "-n", "agent", "-c", str(path)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", f"{session}:agent", agent_cmd, "Enter"],
        check=True, capture_output=True,
    )


def kill_session(session: str) -> None:
    subprocess.run(
        ["tmux", "kill-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ensure_session(session: str, path: Path, agent_cmd: str) -> None:
    if not has_session(session):
        create_session(session, path, agent_cmd)


def attach(session: str) -> None:
    if os.environ.get("TMUX"):
        os.execvp("tmux", ["tmux", "switch-client", "-t", session])
    else:
        os.execvp("tmux", ["tmux", "attach", "-t", session])
