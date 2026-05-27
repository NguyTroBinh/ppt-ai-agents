"""
Image tools -- analysis.

Wraps skills/ppt-master/scripts/analyze_images.py.

Each operation is exposed twice:
- Plain function (run_analyze_images) for orchestrator to call directly.
- @function_tool wrapper (analyze_images) for agents to call via tool calling.
"""

import subprocess
from pathlib import Path

from agents import function_tool

_SCRIPTS_DIR = (
    Path(__file__).parent.parent.parent / "skills" / "ppt-master" / "scripts"
)
_ANALYZE_IMAGES = str(_SCRIPTS_DIR / "analyze_images.py")


# --- Plain function (called by orchestrator) ---

def run_analyze_images(images_dir: str) -> str:
    """Analyze images in a directory."""
    result = subprocess.run(
        ["python3", _ANALYZE_IMAGES, images_dir],
        capture_output=True, text=True, timeout=120,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or "(no output)"


# --- Agent tool wrapper (called by LLM via tool calling) ---

@function_tool
def analyze_images(images_dir: str) -> str:
    """Analyze images in a directory.

    Args:
        images_dir: Path to the directory containing image files.

    Returns:
        Analysis output describing dimensions, colors, and content of each image.
    """
    return run_analyze_images(images_dir)
