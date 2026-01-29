from pathlib import Path
import uuid

from dotenv import load_dotenv

from .video import (
    download_video_from_dropbox,
    extract_audio,
    transcribe_with_whisper,
    llm_top_three_viral_clips,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional


app = FastAPI(title="Videotto Backend")

# Allow requests from the local React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- In-memory job store (id -> job dict) ---
jobs: dict[str, dict] = {}


class CreateJobRequest(BaseModel):
    videoUrl: str


class JobResponse(BaseModel):
    jobId: str
    status: str


class ClipOut(BaseModel):
    start: float
    end: float
    reason: str
    start_frame: int
    end_frame: int


class JobStatusResponse(BaseModel):
    jobId: str
    status: str
    statusMessage: Optional[str] = None
    clips: Optional[list[ClipOut]] = None
    error: Optional[str] = None


def run_pipeline_sync(job_id: str, video_url: str) -> None:
    """Run download -> extract audio -> transcribe -> LLM top 3 clips; update job step message at each stage."""
    job = jobs.get(job_id)
    if not job or job["status"] != "processing":
        return
    try:
        job["status_message"] = "Downloading video..."
        video_path = download_video_from_dropbox(video_url)

        job["status_message"] = "Extracting audio..."
        audio_path = extract_audio(video_path)

        job["status_message"] = "Transcribing speech..."
        transcript = transcribe_with_whisper(audio_path)
        if not transcript:
            job["status"] = "failed"
            job["error"] = "No transcript produced (empty or Whisper failed)."
            return

        job["status_message"] = "Identifying viral clips..."
        clips = llm_top_three_viral_clips(transcript, video_path=video_path)
        job["clips"] = [{"start": c["start"], "end": c["end"], "reason": c["reason"], "start_frame": c["start_frame"], "end_frame": c["end_frame"]} for c in clips]
        job["status"] = "completed"
        job["status_message"] = None
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["status_message"] = None


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs", response_model=JobResponse)
async def create_job(body: CreateJobRequest, background_tasks: BackgroundTasks) -> JobResponse:
    """Create a job and run the pipeline in the background."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "video_url": body.videoUrl,
        "status": "processing",
        "status_message": "Starting...",
        "clips": None,
        "error": None,
    }
    background_tasks.add_task(run_pipeline_sync, job_id, body.videoUrl)
    return JobResponse(jobId=job_id, status="processing")


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    """Return job status and clips (if completed) or error (if failed)."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    clips_out = None
    if job.get("clips"):
        clips_out = [ClipOut(**c) for c in job["clips"]]
    return JobStatusResponse(
        jobId=job["id"],
        status=job["status"],
        statusMessage=job.get("status_message"),
        clips=clips_out,
        error=job.get("error"),
    )

