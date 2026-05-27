"""
Export tools wrapping post-processing and PPTX conversion.

Wraps skills/ppt-master/scripts/finalize_svg.py and svg_to_pptx.py.

Each operation is exposed twice:
- Plain function (run_finalize_svg / run_svg_to_pptx) for orchestrator to call directly.
- @function_tool wrapper (finalize_svg / svg_to_pptx) for agents to call via tool calling.
"""

import subprocess
from pathlib import Path

from agents import function_tool

_SCRIPTS_DIR = (
    Path(__file__).parent.parent.parent / "skills" / "ppt-master" / "scripts"
)
_FINALIZE_SVG = str(_SCRIPTS_DIR / "finalize_svg.py")
_SVG_TO_PPTX = str(_SCRIPTS_DIR / "svg_to_pptx.py")


# --- Plain functions (called by orchestrator) ---

def run_finalize_svg(project_path: str) -> str:
    """Run the post-processing pipeline on generated SVGs."""
    result = subprocess.run(
        ["python3", _FINALIZE_SVG, project_path],
        capture_output=True, text=True, timeout=300,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or "(no output)"


def run_svg_to_pptx(project_path: str, source: str = "final") -> str:
    """Convert finalized SVGs into a natively editable PPTX presentation."""
    result = subprocess.run(
        ["python3", _SVG_TO_PPTX, project_path, "-s", source],
        capture_output=True, text=True, timeout=300,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or "(no output)"


# --- Agent tool wrappers (called by LLM via tool calling) ---

@function_tool
def finalize_svg(project_path: str) -> str:
    """Run the post-processing pipeline on generated SVGs.

    Copies SVGs from svg_output to svg_final and runs final alignment, image embedding,
    text flattening, and rounded corner transformations.

    Args:
        project_path: Path to the project root directory.

    Returns:
        Command output.
    """
    return run_finalize_svg(project_path)


@function_tool
def svg_to_pptx(project_path: str, source: str = "final") -> str:
    """Convert finalized SVGs into a natively editable PPTX presentation.

    Creates the presentation inside the exports/ directory of the project.

    Args:
        project_path: Path to the project root directory.
        source: SVG source directory (e.g. 'final' to read svg_final,
                'output' to read svg_output).

    Returns:
        Command output.
    """
    return run_svg_to_pptx(project_path, source)
