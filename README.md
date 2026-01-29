# Videotto Clip Finder

A small system that takes a video (via Dropbox link), analyzes it, and returns the **top 3 clips** with start/end times and a short explanation for each. Built for the Videotto Engineering Internship Exercise.

## What it does

- **Input:** A video file provided via Dropbox share link (direct-download).
- **Processing:** Download → extract audio → transcribe (Whisper) → run an LLM agent that views frames and transcript to pick the best 3 clips.
- **Output:** For each clip: **start time**, **end time**, and a **short explanation** of why it was selected.
- **Status / progress:** Backend exposes `processing`, `completed`, and `failed` with step messages (e.g. "Downloading video...", "Transcribing speech...", "Identifying viral clips (agent)..."). The React UI polls the job and shows status and step message.
- **Web UI:** React app to paste a Dropbox URL, submit a job, watch progress, and view the 3 clips in a card layout (thumbnail, timestamps, rationale).

## How clip-ranking works

Clip selection is done by an **LLM agent** (LangGraph) with access to two tools:

1. **`get_frames(start, end, num_frames)`** – Extracts frames from the video for a time range and returns a **textual analysis** of what’s visible (scene, expressions, text on screen, composition) and viral potential. The agent is instructed to call this **first, in sequence**, to build a visual overview of the whole video.
2. **`get_transcript(start, end)`** – Returns a textual analysis of the transcript for a time range (summary, key moments, virality rationale). The agent calls this for **segments that look interesting** from the frame analysis.

The agent is prompted as a **viral clip analyst**: it scans the video visually, then uses the transcript where useful, and finally calls **`submit_top_clips`** once with exactly 3 clips. Each clip has:
- **Start / end** in seconds (typically **5–8 seconds** for short-form virality).
- **Reason** that must cite both what was **seen** (frames) and **heard** (transcript), and why the segment has viral potential.

Viral criteria used in the prompt include: strong hook in the first 1–2 seconds, emotional punch (surprise, humor, tension), clarity without heavy context, visual novelty, and quick payoff. The agent is also told the **video duration** so it only requests ranges within the file and submits clips within bounds.

So ranking is **AI-assisted**: the LLM acts as judge using zero-shot reasoning over frame and transcript analyses, with no custom training or transcript-only heuristics.

## Tradeoffs and decisions

- **Why an agent with vision + transcript instead of transcript-only?** Viral clips often rely on visuals (expressions, text on screen, cuts). Transcript-only would miss silent or low-speech moments and doesn’t capture “what makes it shareable” visually. Letting the LLM see both modalities and choose when to use each felt more aligned with how virality works.
- **Why frames-first, then transcript?** To avoid the agent scanning the whole transcript first and underusing visuals. By having it scan the video with `get_frames` first, it builds a visual map, then uses `get_transcript` only for segments it’s already interested in. That keeps tool use focused and reduces cost.
- **Why inner LLMs inside the tools?** The main agent can’t receive raw images in tool results (API constraints). So `get_frames` and `get_transcript` each call a separate LLM to turn frames/transcript into **text summaries** (analysis, evaluation, virality rationale). The main agent then reasons over these texts. Tradeoff: extra latency and cost for compatibility and a single agent loop.
- **Duration clamping:** The agent is told the video duration and must only request ranges within `[0, duration]`. Both `get_frames` and `get_transcript` clamp requested ranges to the actual duration so out-of-range requests don’t break ffmpeg or transcript lookup.
- **In-memory jobs:** Job state is stored in memory. Simple for the exercise; for production you’d use a DB or queue and persist job IDs and results.

## What I would improve with more time

- **RAG / viral context:** Give the agent access to examples or descriptions of what’s currently viral (e.g. via RAG over a curated set or live “trending” signals) so ranking isn’t purely zero-shot.
- **Evaluation loop:** Add an LLM (or human) judge that scores the 3 chosen clips and feeds back into the agent (e.g. “clip 2 is weak because …”) so it can refine or resubmit.
- **Human-in-the-loop:** Allow a human to mark good/bad clips and feed that into memory or fine-tuning so the system improves over time.
- **Memory / learning:** Persist which clips performed well (e.g. engagement metrics) and use that to bias future selections or to fine-tune a small ranker.
- **Export and encode:** Actually export the selected clips as MP4 (ffmpeg trim) and optionally offer download from the UI.

## Tech stack

- **Backend:** Python (FastAPI), Whisper (transcription), LangGraph + LangChain (agent), OpenAI (LLM + vision). Designed to run on **AWS** (e.g. EC2); runnable via Docker.
- **Frontend:** React + TypeScript + Vite. Polls backend for job status and displays results in a card-based UI.

## Setup and run

### Prerequisites

- Python 3.11+, Node.js 18+, ffmpeg on PATH (for local backend).
- `.env` at repo root (or `backend/.env`) with at least `OPENAI_API_KEY`.

### Backend (local)

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Run from **repo root** so the `backend` package is importable.

### Backend (Docker)

From repo root:

```bash
docker compose up --build
```

Backend will be at `http://localhost:8000`. Image is built for `linux/amd64` (e.g. for AWS x86).

### Frontend

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. The app is configured to call `http://localhost:8000` for the API; change `API_BASE` in `src/App.tsx` if the backend is elsewhere (e.g. your AWS URL).

### Environment

- `OPENAI_API_KEY` – required for the agent and inner analysis LLMs.
- Optional: `LANGCHAIN_TRACING_V2`, `LANGCHAIN_PROJECT`, `LANGCHAIN_API_KEY` for LangSmith tracing.

## Project structure

```
backend/
  main.py           # FastAPI app: POST /api/jobs, GET /api/jobs/{id}, health
  requirements.txt
  video/
    agent.py       # Download, transcribe, LangGraph agent (get_frames, get_transcript, submit_top_clips)
src/
  App.tsx           # Job flow: input URL → polling → result view
  views/
    InputView.tsx   # Dropbox URL input
    ProcessingView.tsx  # Status + step message
    ResultView.tsx  # Top 3 clips as cards (thumbnail, start/end, rationale)
Dockerfile          # Python 3.11, ffmpeg, backend only; amd64
docker-compose.yaml # Build + run backend with .env
```

## Deliverables

- **Web app:** Backend deployed on AWS (EC2); frontend can be run locally against that URL or hosted separately.
- **Source code:** This GitHub repo.
- **README:** This file – how clip-ranking works, tradeoffs and decisions, and what I’d improve with more time.
