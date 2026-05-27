"""Structured LLM output contracts for the PPT pipeline."""

from typing import List, Optional

from pydantic import BaseModel, Field


class StrategistSlideSpec(BaseModel):
    """Canonical slide outline item emitted by the strategist."""

    slide_number: int = Field(description="1-based slide number")
    title: str = Field(description="Visible slide title in the deck output language")
    layout: str = Field(description="Recommended layout pattern for the slide")
    rhythm: str = Field(description="One of anchor, dense, or breathing")
    content_points: List[str] = Field(description="Slide content bullets in the deck output language")
    visualization: Optional[str] = Field(default=None, description="Visualization type or None")


class StrategistSpecOutput(BaseModel):
    """Final strategist payload written by the orchestrator."""

    design_spec_md: str = Field(description="Complete Markdown content for design_spec.md")
    spec_lock_md: str = Field(description="Complete Markdown content for spec_lock.md")
    slide_outline: List[StrategistSlideSpec] = Field(description="Canonical ordered slide outline for executor")


class ExecutorSlideOutput(BaseModel):
    """Single slide payload emitted by the executor."""

    slide_number: int = Field(description="1-based slide number from the current requested window")
    svg: str = Field(description="Complete SVG XML for this slide, beginning with <svg and ending with </svg>")
    speaker_notes_md: str = Field(description="Complete Markdown speaker notes for this slide")


class ExecutorWindowOutput(BaseModel):
    """Executor payload for one slide window."""

    slides: List[ExecutorSlideOutput] = Field(description="One output item for each requested slide")
