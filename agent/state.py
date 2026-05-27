"""
Shared project state passed between pipeline phases.

All inter-phase communication goes through this dataclass — agents read/write
to the filesystem, and the orchestrator tracks paths here.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProjectState:
    """Tracks project artifacts across pipeline phases."""

    # --- Input ---
    source_files: list[str] = field(default_factory=list)
    user_text: Optional[str] = None
    canvas_format: str = "ppt169"
    template_name: Optional[str] = None

    # --- Paths (set during Phase 2) ---
    project_path: Optional[Path] = None

    # --- Phase tracking ---
    current_phase: str = "init"

    # Convenience accessors — all derived from project_path.

    @property
    def sources_dir(self) -> Optional[Path]:
        return self.project_path / "sources" if self.project_path else None

    @property
    def images_dir(self) -> Optional[Path]:
        return self.project_path / "images" if self.project_path else None

    @property
    def svg_output_dir(self) -> Optional[Path]:
        return self.project_path / "svg_output" if self.project_path else None

    @property
    def notes_dir(self) -> Optional[Path]:
        return self.project_path / "notes" if self.project_path else None

    @property
    def design_spec_path(self) -> Optional[Path]:
        return self.project_path / "design_spec.md" if self.project_path else None

    @property
    def spec_lock_path(self) -> Optional[Path]:
        return self.project_path / "spec_lock.md" if self.project_path else None
