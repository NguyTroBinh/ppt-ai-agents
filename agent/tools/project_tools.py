"""
Project management tools -- init, import-sources, validate.

Wraps skills/ppt-master/scripts/project_manager.py.

Each operation is exposed twice:
- Plain function (e.g. run_init_project) for orchestrator to call directly.
- @function_tool wrapper (e.g. init_project) for agents to call via tool calling.
"""

import subprocess
from pathlib import Path

from agents import function_tool

# Resolve scripts dir once
_SCRIPTS_DIR = (
    Path(__file__).parent.parent.parent / "skills" / "ppt-master" / "scripts"
)
_PROJECT_MANAGER = str(_SCRIPTS_DIR / "project_manager.py")


def _run(args: list[str]) -> str:
    """Run a command and return combined stdout+stderr."""
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=120,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or "(no output)"


# --- Plain functions (called by orchestrator) ---

def run_init_project(project_name: str, canvas_format: str = "ppt169") -> str:
    """Initialize a new PPT Master project."""
    return _run([
        "python3", _PROJECT_MANAGER,
        "init", project_name, "--format", canvas_format,
    ])


def run_import_sources(project_path: str, source_files: list[str]) -> str:
    """Import source files into a project's sources/ directory."""
    return _run([
        "python3", _PROJECT_MANAGER,
        "import-sources", project_path, *source_files, "--move",
    ])


def run_validate_project(project_path: str) -> str:
    """Validate project structure and completeness."""
    return _run([
        "python3", _PROJECT_MANAGER,
        "validate", project_path,
    ])


# --- Agent tool wrappers (called by LLM via tool calling) ---

@function_tool
def init_project(project_name: str, canvas_format: str = "ppt169") -> str:
    """Initialize a new PPT Master project.

    Args:
        project_name: Name for the project (used in directory name).
        canvas_format: Canvas format -- ppt169, ppt43, xhs, story, etc.

    Returns:
        Command output including the created project path.
    """
    return run_init_project(project_name, canvas_format)


@function_tool
def import_sources(project_path: str, source_files: list[str]) -> str:
    """Import source files into a project's sources/ directory.

    Args:
        project_path: Path to the project directory.
        source_files: List of file paths to import.

    Returns:
        Command output.
    """
    return run_import_sources(project_path, source_files)


@function_tool
def validate_project(project_path: str) -> str:
    """Validate project structure and completeness.

    Args:
        project_path: Path to the project directory.

    Returns:
        Validation result.
    """
    return run_validate_project(project_path)

