import json
import os
from pathlib import Path
from unittest.mock import patch

from wt_tool.config import load_config, save_agent_cmd


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

    def test_file_config_agent_cmd(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"agent_cmd": "aider"}))
        with patch("wt_tool.config.CONFIG_FILE", config_file):
            with patch.dict(os.environ, {}, clear=False):
                env = {k: v for k, v in os.environ.items() if k != "WT_AGENT_CMD"}
                with patch.dict(os.environ, env, clear=True):
                    cfg = load_config()
        assert cfg.agent_cmd == "aider"

    def test_env_takes_precedence_over_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"agent_cmd": "aider"}))
        with patch("wt_tool.config.CONFIG_FILE", config_file):
            with patch.dict(os.environ, {"WT_AGENT_CMD": "cursor"}):
                cfg = load_config()
        assert cfg.agent_cmd == "cursor"


class TestSaveAgentCmd:
    def test_saves_to_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("wt_tool.config.CONFIG_FILE", config_file):
            save_agent_cmd("claude --model claude-opus-4-7")
        data = json.loads(config_file.read_text())
        assert data["agent_cmd"] == "claude --model claude-opus-4-7"

    def test_preserves_existing_keys(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"projects_dir": "/tmp/work"}))
        with patch("wt_tool.config.CONFIG_FILE", config_file):
            save_agent_cmd("aider")
        data = json.loads(config_file.read_text())
        assert data["projects_dir"] == "/tmp/work"
        assert data["agent_cmd"] == "aider"
