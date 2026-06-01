"""FastAPI entrypoint for PPT Master microservice mode."""

import os
import re
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from agent.config import AgentConfig

from .schemas import ConfirmJobResponse, ConfirmRequest, CreateJobResponse, JobStatusResponse
from .service import PPTService


def _default_storage_dir() -> Path:
    return Path(os.environ.get("PPT_API_STORAGE_DIR", AgentConfig.from_env().repo_root / "api_storage"))


app = FastAPI(title="PPT Master API", version="0.1.0")
service = PPTService(_default_storage_dir())


@app.post("/api/ppt/jobs", response_model=CreateJobResponse)
async def create_job(
    source_file: UploadFile = File(...),
    user_text: str | None = Form(None),
    canvas_format: str = Form("ppt169"),
):
    upload_path = await _save_upload(source_file)
    job = service.create_job_record(upload_path)
    try:
        job = await service.prepare_eight_confirmation(job, user_text, canvas_format)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return CreateJobResponse(
        job_id=job.job_id,
        status=job.status,
        eight_confirmation=job.eight_confirmation or "",
    )


@app.post("/api/ppt/jobs/{job_id}/confirm", response_model=ConfirmJobResponse)
async def confirm_job(
    job_id: str,
    payload: ConfirmRequest,
    background_tasks: BackgroundTasks,
):
    job = service.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "awaiting_confirmation":
        raise HTTPException(status_code=409, detail=f"Job is not awaiting confirmation. Current status: {job.status}")

    service.jobs.update_status(job, "queued")
    background_tasks.add_task(service.run_confirmed_pipeline, job_id, payload.confirmation_text)
    return ConfirmJobResponse(job_id=job.job_id, status=job.status)


@app.get("/api/ppt/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str):
    job = service.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        eight_confirmation=job.eight_confirmation,
        error=job.error,
        artifacts=service.artifact_links(job),
    )


@app.get("/api/ppt/jobs/{job_id}/artifacts/{filename}")
async def download_artifact(job_id: str, filename: str):
    job = service.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job is not completed. Current status: {job.status}")

    requested = Path(filename).name
    for path in job.artifacts.values():
        if path.name == requested and path.exists():
            return FileResponse(path, filename=path.name)

    raise HTTPException(status_code=404, detail="Artifact not found.")


async def _save_upload(source_file: UploadFile) -> Path:
    filename = _safe_filename(source_file.filename or "source")
    upload_dir = service.uploads_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / filename

    counter = 1
    while upload_path.exists():
        stem = upload_path.stem
        suffix = upload_path.suffix
        upload_path = upload_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    with upload_path.open("wb") as buffer:
        while chunk := await source_file.read(1024 * 1024):
            buffer.write(chunk)

    return upload_path


def _safe_filename(filename: str) -> str:
    path_name = Path(filename).name
    stem = Path(path_name).stem or "source"
    suffix = Path(path_name).suffix
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "source"
    safe_suffix = re.sub(r"[^A-Za-z0-9.]+", "", suffix)
    return f"{safe_stem}{safe_suffix}"
