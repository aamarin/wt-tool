import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "wt" / "config.json"


@dataclass(frozen=True)
class Config:
    wt_dir_name: str
    projects_dir: Path
    agent_cmd: str


def _read_config_file() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            print(
                f"wt: warning: {CONFIG_FILE} contains invalid JSON, ignoring",
                file=sys.stderr,
            )
    return {}


def _write_config_file(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def resolve_projects_dir() -> Path | None:
    """Returns the configured projects dir, or None if never set."""
    if "WT_PROJECTS_DIR" in os.environ:
        return Path(os.environ["WT_PROJECTS_DIR"]).expanduser()
    data = _read_config_file()
    if "projects_dir" in data:
        return Path(data["projects_dir"]).expanduser()
    return None


def save_projects_dir(path: Path) -> None:
    data = _read_config_file()
    data["projects_dir"] = str(path)
    _write_config_file(data)


def resolve_agent_skills_dir() -> Path | None:
    """Returns the saved agent skills dir, or None if never set."""
    data = _read_config_file()
    if "agent_skills_dir" in data:
        return Path(data["agent_skills_dir"]).expanduser()
    return None


def save_agent_skills_dir(path: Path) -> None:
    data = _read_config_file()
    data["agent_skills_dir"] = str(path)
    _write_config_file(data)


def resolve_agent_cmd() -> str | None:
    """Returns the configured agent command, or None if never explicitly set."""
    if "WT_AGENT_CMD" in os.environ:
        return os.environ["WT_AGENT_CMD"]
    data = _read_config_file()
    if "agent_cmd" in data:
        return data["agent_cmd"]
    return None


def save_agent_cmd(cmd: str) -> None:
    data = _read_config_file()
    data["agent_cmd"] = cmd
    _write_config_file(data)


def resolve_wt_dir_name() -> str | None:
    """Returns the configured wt dir name, or None if never explicitly set."""
    if "WT_DIR_NAME" in os.environ:
        return os.environ["WT_DIR_NAME"]
    data = _read_config_file()
    if "wt_dir_name" in data:
        return data["wt_dir_name"]
    return None


def save_wt_dir_name(name: str) -> None:
    data = _read_config_file()
    data["wt_dir_name"] = name
    _write_config_file(data)


def load_config() -> Config:
    data = _read_config_file()
    return Config(
        wt_dir_name=os.environ.get("WT_DIR_NAME", data.get("wt_dir_name", "wt")),
        projects_dir=Path(
            os.environ.get(
                "WT_PROJECTS_DIR",
                data.get("projects_dir", str(Path.home() / "Development")),
            )
        ).expanduser(),
        agent_cmd=os.environ.get("WT_AGENT_CMD", data.get("agent_cmd", "claude")),
    )
