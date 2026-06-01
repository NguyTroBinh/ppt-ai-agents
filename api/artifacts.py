"""Artifact collection helpers for API jobs."""

import shutil
import re
from pathlib import Path
from typing import Dict


def collect_artifacts(project_path: Path, artifacts_dir: Path, source_name: str | None = None) -> Dict[str, Path]:
    """Create API-facing <source>_result.pptx and <source>_speaker_note.md artifacts."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_prefix = _artifact_prefix(source_name or project_path.name)

    pptx_path = _latest_pptx(project_path / "exports")
    if not pptx_path:
        raise FileNotFoundError("No PPTX file found in project exports directory.")

    result_pptx = artifacts_dir / f"{artifact_prefix}_result.pptx"
    shutil.copy2(pptx_path, result_pptx)

    speaker_note = artifacts_dir / f"{artifact_prefix}_speaker_note.md"
    speaker_note.write_text(_merge_speaker_notes(project_path / "notes"), encoding="utf-8")

    return {
        "pptx": result_pptx,
        "speaker_notes": speaker_note,
    }


def _latest_pptx(exports_dir: Path) -> Path | None:
    if not exports_dir.exists():
        return None
    pptx_files = [path for path in exports_dir.glob("*.pptx") if path.is_file()]
    if not pptx_files:
        return None
    return max(pptx_files, key=lambda path: path.stat().st_mtime)


def _artifact_prefix(source_name: str) -> str:
    stem = Path(source_name).stem or "presentation"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "presentation"


def _merge_speaker_notes(notes_dir: Path) -> str:
    note_files = sorted(notes_dir.glob("*.md")) if notes_dir.exists() else []
    if not note_files:
        return "# Speaker Notes\n\nNo speaker notes were generated.\n"

    sections = ["# Speaker Notes"]
    for note_path in note_files:
        content = note_path.read_text(encoding="utf-8").strip()
        sections.append(f"## {note_path.stem}\n\n{content}")

    return "\n\n---\n\n".join(sections).rstrip() + "\n"
