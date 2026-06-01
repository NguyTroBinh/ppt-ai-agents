"""In-process job registry for the PPT Master API.

This is intentionally small and dependency-free. For production multi-worker
deployment, replace it with Redis/Postgres plus an external worker queue.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, Optional
from uuid import uuid4

from agent.orchestrator import PipelineOrchestrator
from agent.state import ProjectState


@dataclass
class PPTJob:
    job_id: str
    upload_path: Path
    status: str = "created"
    state: Optional[ProjectState] = None
    orchestrator: Optional[PipelineOrchestrator] = None
    eight_confirmation: Optional[str] = None
    error: Optional[str] = None
    artifacts: Dict[str, Path] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, PPTJob] = {}
        self._lock = Lock()

    def create(self, upload_path: Path) -> PPTJob:
        job = PPTJob(job_id=uuid4().hex, upload_path=upload_path)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Optional[PPTJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def update_status(self, job: PPTJob, status: str, error: Optional[str] = None) -> None:
        with self._lock:
            job.status = status
            job.error = error
            job.touch()
