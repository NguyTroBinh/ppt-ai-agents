"""
Executor agent definition.

Responsible for receiving specs and outlines, generating SVG page layouts,
verifying their quality, and outputting spoken narration speaker notes.
"""

from agents import Agent

from ..prompts.loader import PromptLoader
from ..tools.file_tools import read_file, write_file, search_icons
from ..tools.svg_tools import write_svg, quality_check


def create_executor_agent(loader: PromptLoader, style: str = "general", output_type=None) -> Agent:
    """Create a new Executor agent instance.

    Args:
        loader: PromptLoader instance.
        style: Presentation design style ('general', 'consultant', 'consultant-top').
    """
    pure_text_override = """

## Runtime Compatibility Override

You are running in a pure-text generation mode with no callable tools.
The orchestrator injects the current `spec_lock.md`, slide briefs, and prior SVG context directly into the user message.
Treat the injected spec_lock content as the required per-page spec_lock re-read.

Do not output shell commands, Python code, tool-call XML, or instructions to read files.
When a structured output schema is provided, return exactly that schema:
`slides` must contain one item per requested slide, and each item must include
`slide_number`, `svg`, and `speaker_notes_md`.
When no structured output schema is provided, use independent ```xml and ```markdown code blocks.
Visible slide text and speaker notes must follow the output language specified by the orchestrator.
"""

    return Agent(
        name="Executor",
        instructions=loader.executor(style) + pure_text_override,
        tools=[],
        output_type=output_type,
    )
