"""Service layer connecting FastAPI routes to the PPT Master orchestrator."""

from pathlib import Path
from typing import Dict

from agent.config import AgentConfig
from agent.orchestrator import PipelineOrchestrator
from agent.state import ProjectState

from .artifacts import collect_artifacts
from .jobs import JobStore, PPTJob


class PPTService:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.uploads_dir = storage_dir / "uploads"
        self.artifacts_dir = storage_dir / "artifacts"
        self.jobs = JobStore()
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def create_job_record(self, upload_path: Path) -> PPTJob:
        return self.jobs.create(upload_path)

    async def prepare_eight_confirmation(
        self,
        job: PPTJob,
        user_text: str | None,
        canvas_format: str,
    ) -> PPTJob:
        self.jobs.update_status(job, "running_strategist")
        try:
            config = AgentConfig.from_env()
            state = ProjectState(
                source_files=[str(job.upload_path)],
                user_text=user_text,
                canvas_format=canvas_format,
            )
            orchestrator = PipelineOrchestrator(state, config)
            proposal = await orchestrator.run_to_eight_confirmations()
            if not proposal:
                raise RuntimeError("Strategist did not return Eight Confirmations.")

            job.state = state
            job.orchestrator = orchestrator
            job.eight_confirmation = proposal
            self.jobs.update_status(job, "awaiting_confirmation")
            return job
        except Exception as exc:
            self.jobs.update_status(job, "failed", str(exc))
            raise

    async def run_confirmed_pipeline(self, job_id: str, confirmation_text: str) -> None:
        job = self.jobs.get(job_id)
        if not job or not job.orchestrator or not job.state:
            return

        self.jobs.update_status(job, "running")
        try:
            strategist_ok = await job.orchestrator.confirm_eight_confirmations(confirmation_text)
            if not strategist_ok:
                raise RuntimeError("Strategist finalization failed.")

            executor_ok = await job.orchestrator.run_executor()
            if not executor_ok:
                raise RuntimeError("Executor phase failed.")

            export_ok = await job.orchestrator.run_post_processing_and_export()
            if not export_ok:
                raise RuntimeError("PPTX export failed.")

            job_artifacts_dir = self.artifacts_dir / job.job_id
            job.artifacts = collect_artifacts(job.state.project_path, job_artifacts_dir, job.upload_path.name)
            self.jobs.update_status(job, "completed")
        except Exception as exc:
            self.jobs.update_status(job, "failed", str(exc))

    def artifact_links(self, job: PPTJob) -> Dict[str, Dict[str, str]]:
        links = {}
        for key, path in job.artifacts.items():
            links[key] = {
                "filename": path.name,
                "download_url": f"/api/ppt/jobs/{job.job_id}/artifacts/{path.name}",
            }
        return links
