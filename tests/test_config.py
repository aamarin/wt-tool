import os
from pathlib import Path
from unittest.mock import patch

from wt.config import load_config


class TestLoadConfig:
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=False):
            env = {k: v for k, v in os.environ.items()
                   if k not in ("WT_DIR_NAME", "WT_PROJECTS_DIR", "WT_AGENT_CMD")}
            with patch.dict(os.environ, env, clear=True):
                cfg = load_config()
        assert cfg.wt_dir_name == "wt"
        assert cfg.projects_dir == Path.home() / "Development"
        assert cfg.agent_cmd == "claude"

    def test_env_overrides(self):
        with patch.dict(os.environ, {
            "WT_DIR_NAME": "worktrees",
            "WT_PROJECTS_DIR": "/tmp/projects",
            "WT_AGENT_CMD": "aider",
        }):
            cfg = load_config()
        assert cfg.wt_dir_name == "worktrees"
        assert cfg.projects_dir == Path("/tmp/projects")
        assert cfg.agent_cmd == "aider"

    def test_immutable(self):
        cfg = load_config()
        try:
            cfg.wt_dir_name = "other"  # type: ignore[misc]
            assert False, "Should have raised"
        except Exception:
            pass
