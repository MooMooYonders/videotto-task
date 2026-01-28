from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid


app = FastAPI(title="Videotto Backend")

# Allow requests from the local React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateJobRequest(BaseModel):
    videoUrl: str


class JobResponse(BaseModel):
    jobId: str
    status: str


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs", response_model=JobResponse)
async def create_job(body: CreateJobRequest) -> JobResponse:
    """
    Create a new video processing job.

    For now, this just echoes back a generated job ID and a simple 'ok' status.
    Later, this is where we'll kick off the agentic pipeline and track real progress.
    """
    job_id = str(uuid.uuid4())
    return JobResponse(jobId=job_id, status="ok")

