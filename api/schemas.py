"""Pydantic schemas for the PPT Master HTTP API."""

from typing import Dict, Optional

from pydantic import BaseModel, Field


class ConfirmRequest(BaseModel):
    """User response to the Eight Confirmations proposal."""

    confirmation_text: str = Field(
        default="accept",
        description="Use 'accept' to approve as-is, or provide revision instructions.",
    )


class ArtifactInfo(BaseModel):
    filename: str
    download_url: str


class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    eight_confirmation: str


class ConfirmJobResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    eight_confirmation: Optional[str] = None
    error: Optional[str] = None
    artifacts: Dict[str, ArtifactInfo] = Field(default_factory=dict)
