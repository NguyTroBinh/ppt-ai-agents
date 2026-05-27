"""
Agent configuration — LLM client setup and paths.

Reads from environment variables or .env file.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

# Resolve paths relative to this file
_AGENT_DIR = Path(__file__).parent
_REPO_ROOT = _AGENT_DIR.parent
_SKILL_DIR = _REPO_ROOT / "skills" / "ppt-master"


@dataclass
class AgentConfig:
    """Configuration for the agent system."""

    # LLM
    model: str = "openai/Qwen/Qwen3.6-27B"
    base_url: str = "http://100.75.29.73:8000/v1"
    api_key: str = "sk-dummy"
    temperature: float = 0.5
    max_tokens: int = 16384

    # Paths
    repo_root: Path = field(default_factory=lambda: _REPO_ROOT)
    skill_dir: Path = field(default_factory=lambda: _SKILL_DIR)
    scripts_dir: Path = field(default_factory=lambda: _SKILL_DIR / "scripts")
    templates_dir: Path = field(default_factory=lambda: _SKILL_DIR / "templates")
    references_dir: Path = field(default_factory=lambda: _SKILL_DIR / "references")
    projects_dir: Path = field(default_factory=lambda: _REPO_ROOT / "projects")

    # Runtime
    default_format: str = "ppt169"
    window_size: int = 1  # strict sequential executor generation per SKILL.md

    def build_client(self) -> AsyncOpenAI:
        """Create an AsyncOpenAI client pointing to the configured endpoint."""
        return AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Build config from environment variables, falling back to defaults."""
        kwargs = {}
        if v := os.environ.get("LLM_MODEL"):
            kwargs["model"] = v
        if v := os.environ.get("LLM_BASE_URL"):
            kwargs["base_url"] = v
        if v := os.environ.get("LLM_API_KEY"):
            kwargs["api_key"] = v
        if v := os.environ.get("LLM_TEMPERATURE"):
            kwargs["temperature"] = float(v)
        if v := os.environ.get("LLM_MAX_TOKENS"):
            kwargs["max_tokens"] = int(v)
        if v := os.environ.get("PPT_DEFAULT_FORMAT"):
            kwargs["default_format"] = v
        if v := os.environ.get("PPT_WINDOW_SIZE"):
            window_size = int(v)
            if window_size != 1:
                raise ValueError("PPT_WINDOW_SIZE must be 1 because SKILL.md requires sequential slide generation.")
            kwargs["window_size"] = window_size
        return cls(**kwargs)
