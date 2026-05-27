"""
Strategist agent definition.

Responsible for receiving source content, performing content analysis/design planning,
and outputting the design_spec.md and spec_lock.md files.
"""

from agents import Agent

from ..prompts.loader import PromptLoader
from ..tools.file_tools import read_file, write_file, list_directory, search_icons
from ..tools.image_tools import analyze_images


def create_strategist_agent(loader: PromptLoader, output_type=None) -> Agent:
    """Create a new Strategist agent instance."""
    return Agent(
        name="Strategist",
        instructions=loader.strategist(),
        tools=[],
        output_type=output_type,
    )
