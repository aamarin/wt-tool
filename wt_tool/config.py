import json
import os
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
            pass
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


def load_config() -> Config:
    return Config(
        wt_dir_name=os.environ.get("WT_DIR_NAME", "wt"),
        projects_dir=Path(os.environ.get("WT_PROJECTS_DIR", str(Path.home() / "Development"))).expanduser(),
        agent_cmd=os.environ.get("WT_AGENT_CMD", "claude"),
    )
