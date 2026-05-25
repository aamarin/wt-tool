import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    wt_dir_name: str
    projects_dir: Path
    agent_cmd: str


def load_config() -> Config:
    return Config(
        wt_dir_name=os.environ.get("WT_DIR_NAME", "wt"),
        projects_dir=Path(os.environ.get("WT_PROJECTS_DIR", str(Path.home() / "Development"))),
        agent_cmd=os.environ.get("WT_AGENT_CMD", "claude"),
    )
