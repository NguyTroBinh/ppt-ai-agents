"""
Load skill markdown files and compose system prompts for agents.

Each agent gets a focused prompt assembled from the relevant reference files.
"""

from pathlib import Path


class PromptLoader:
    """Reads reference markdown files and assembles agent system prompts."""

    def __init__(self, skill_dir: Path):
        self.skill_dir = skill_dir
        self.repo_root = skill_dir.parent.parent
        self.agent_entrypoint = self.repo_root / "AGENTS.md"
        self.skill_workflow = skill_dir / "SKILL.md"
        self.refs = skill_dir / "references"
        self.templates = skill_dir / "templates"
        self.icon_guide = self.templates / "icons" / "README.md"
        self.charts_index = self.templates / "charts" / "charts_index.json"
        self.chart_style_guide = self.templates / "charts" / "CHART_STYLE_GUIDE.md"

    # --- Public API: one method per agent role ---

    def strategist(self) -> str:
        """System prompt for the Strategist agent."""
        return self._compose([
            self.refs / "strategist.md",
            self.refs / "canvas-formats.md",
        ]) + "\n\n---\n\n" + self._strategist_resource_guides()

    def executor(self, style: str = "general") -> str:
        """System prompt for the Executor agent.

        Args:
            style: One of 'general', 'consultant', 'consultant-top'.
        """
        return self._compose([
            self.refs / "executor-base.md",
            self.refs / "shared-standards.md",
            self.refs / f"executor-{style}.md",
        ]) + "\n\n---\n\n" + self._executor_resource_guides()

    def image_generator(self) -> str:
        """System prompt for the Image Generator agent."""
        return self._compose([
            self.refs / "image-base.md",
            self.refs / "image-generator.md",
        ])

    def image_searcher(self) -> str:
        """System prompt for the Image Searcher agent."""
        return self._compose([
            self.refs / "image-base.md",
            self.refs / "image-searcher.md",
        ])

    # --- Template references (read on demand by agents via tools) ---

    def design_spec_reference(self) -> str:
        return self._read(self.templates / "design_spec_reference.md")

    def spec_lock_reference(self) -> str:
        return self._read(self.templates / "spec_lock_reference.md")

    # --- Internal ---

    def _compose(self, role_paths: list[Path]) -> str:
        return "\n\n---\n\n".join([
            self._global_instructions(),
            *(self._read(p) for p in role_paths),
        ])

    def _global_instructions(self) -> str:
        """Project-level instructions applied to every pipeline role."""
        parts = [
            "# Repository Agent Instructions\n\n"
            "The following project entrypoint and workflow authority apply to this "
            "self-hosted agent pipeline. On conflicts, follow AGENTS.md and "
            "skills/ppt-master/SKILL.md over role-level defaults.",
            f"## AGENTS.md\n\n{self._read(self.agent_entrypoint)}",
            f"## skills/ppt-master/SKILL.md\n\n{self._read(self.skill_workflow)}",
        ]
        return "\n\n---\n\n".join(parts)

    def _strategist_resource_guides(self) -> str:
        """Asset-library references needed for selecting valid deck resources."""
        return "\n\n---\n\n".join([
            "# Runtime Asset Library References",
            (
                "## Icon Guide: templates/icons/README.md\n\n"
                "Use this guide when choosing the deck-wide icon library and writing "
                "the icon inventory in design_spec.md and spec_lock.md.\n\n"
                f"{self._read(self.icon_guide)}"
            ),
            (
                "## Visualization Catalog: templates/charts/charts_index.json\n\n"
                "Use this catalog when selecting chart / infographic / diagram "
                "templates for Design Spec section VII. Only use keys that appear "
                "in this JSON and have a matching templates/charts/<key>.svg file.\n\n"
                "```json\n"
                f"{self._read(self.charts_index)}\n"
                "```"
            ),
        ])

    def _executor_resource_guides(self) -> str:
        """Asset-library references needed for rendering valid SVG output."""
        return "\n\n---\n\n".join([
            "# Runtime Asset Rendering References",
            (
                "## Icon Guide: templates/icons/README.md\n\n"
                "Use this guide when emitting <use data-icon=\"library/name\" .../> "
                "placeholders. Use only the icon library and inventory from "
                "spec_lock.md unless a brand-logo exception is explicitly listed.\n\n"
                f"{self._read(self.icon_guide)}"
            ),
            (
                "## Chart SVG Style Guide: templates/charts/CHART_STYLE_GUIDE.md\n\n"
                "Use this guide for all chart, infographic, and diagram SVG work. "
                "It supplements shared-standards.md and applies when the orchestrator "
                "injects a templates/charts/<key>.svg reference for a slide.\n\n"
                f"{self._read(self.chart_style_guide)}"
            ),
        ])

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8")
