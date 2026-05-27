"""
SVG tools -- writing and quality verification.

Wraps basic SVG file operations and skills/ppt-master/scripts/svg_quality_checker.py.

Each operation is exposed twice:
- Plain function (run_write_svg / run_quality_check) for orchestrator to call directly.
- @function_tool wrapper (write_svg / quality_check) for agents to call via tool calling.
"""

import subprocess
from pathlib import Path

from agents import function_tool

_SCRIPTS_DIR = (
    Path(__file__).parent.parent.parent / "skills" / "ppt-master" / "scripts"
)
_QUALITY_CHECKER = str(_SCRIPTS_DIR / "svg_quality_checker.py")


# --- Plain functions (called by orchestrator) ---

def run_write_svg(filename: str, svg_content: str, project_path: str) -> str:
    """Write SVG content to a file in the project's svg_output directory."""
    proj_dir = Path(project_path)
    output_dir = proj_dir / "svg_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = Path(filename).name
    if not safe_filename.endswith(".svg"):
        safe_filename += ".svg"

    svg_filepath = output_dir / safe_filename
    temp_filepath = output_dir / f"{safe_filename}.txt"

    try:
        temp_filepath.write_text(svg_content, encoding="utf-8")
        if svg_filepath.exists():
            svg_filepath.unlink()
        temp_filepath.rename(svg_filepath)
        return f"Successfully wrote SVG to: {svg_filepath} ({len(svg_content)} characters)"
    except Exception as e:
        if temp_filepath.exists():
            try:
                temp_filepath.unlink()
            except Exception:
                pass
        return f"ERROR: Failed to write SVG file {filename}: {e}"


def run_quality_check(project_path: str) -> str:
    """Run the quality checker on the project's svg_output directory."""
    proj_dir = Path(project_path)
    svg_output = proj_dir / "svg_output"

    if not svg_output.exists() or not list(svg_output.glob("*.svg")):
        return f"No SVG files found in {svg_output} to check."

    result = subprocess.run(
        ["python3", _QUALITY_CHECKER, str(svg_output)],
        capture_output=True, text=True, timeout=120,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or "(no quality checker output)"


# --- Agent tool wrappers (called by LLM via tool calling) ---

@function_tool
def write_svg(filename: str, svg_content: str, project_path: str) -> str:
    """Write SVG content to a file in the project's svg_output directory.

    Strictly implements the two-step writing safety rule (writing to .txt first,
    then renaming to .svg) to avoid editor crashes or filesystem sync hangs.

    Args:
        filename: Name of the SVG file (e.g. '01_cover.svg' or '02_agenda.svg').
        svg_content: Full well-formed SVG XML content.
        project_path: Path to the project root directory.

    Returns:
        Status message.
    """
    return run_write_svg(filename, svg_content, project_path)


@function_tool
def quality_check(project_path: str) -> str:
    """Run the quality checker on the project's svg_output directory.

    Checks viewports, fonts, XML well-formedness, forbidden tags, spec_lock drift,
    and image attributions.

    Args:
        project_path: Path to the project root directory.

    Returns:
        Verification report from the quality checker.
    """
    return run_quality_check(project_path)
