"""
File system tools — read, write, list, search.

Used by Strategist and Executor agents to interact with project files.
"""

import subprocess
from pathlib import Path

from agents import function_tool


@function_tool
def read_file(file_path: str) -> str:
    """Read the contents of a file.

    Args:
        file_path: Absolute or relative path to the file.

    Returns:
        File contents as a string, or an error message.
    """
    p = Path(file_path)
    if not p.exists():
        return f"ERROR: File not found: {file_path}"
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR reading {file_path}: {e}"


@function_tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.

    Args:
        file_path: Absolute or relative path to the file.
        content: Full file content to write.

    Returns:
        Confirmation message.
    """
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written: {file_path} ({len(content)} chars)"


@function_tool
def list_directory(dir_path: str) -> str:
    """List files and directories in a path.

    Args:
        dir_path: Path to the directory to list.

    Returns:
        Newline-separated list of entries.
    """
    p = Path(dir_path)
    if not p.is_dir():
        return f"ERROR: Not a directory: {dir_path}"
    entries = sorted(p.iterdir())
    lines = []
    for e in entries:
        suffix = "/" if e.is_dir() else ""
        lines.append(f"{e.name}{suffix}")
    return "\n".join(lines) if lines else "(empty directory)"


@function_tool
def search_icons(library: str, keyword: str) -> str:
    """Search for icon filenames in a built-in icon library.

    Args:
        library: Icon library name (e.g. 'chunk-filled', 'tabler-outline',
                 'phosphor-duotone', 'tabler-filled', 'simple-icons').
        keyword: Keyword to grep for in filenames.

    Returns:
        Matching icon filenames, one per line.
    """
    # Resolve icon dir relative to the skill
    icon_dir = (
        Path(__file__).parent.parent.parent
        / "skills" / "ppt-master" / "templates" / "icons" / library
    )
    if not icon_dir.is_dir():
        return f"ERROR: Icon library not found: {library}"

    matches = [
        f.stem for f in sorted(icon_dir.glob("*.svg"))
        if keyword.lower() in f.stem.lower()
    ]
    if not matches:
        return f"No icons matching '{keyword}' in {library}"
    return "\n".join(matches)
