
from __future__ import annotations

import base64
import logging
import math
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

import requests
import whisper
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from pydantic import BaseModel, Field


# ----------------------------
# Config / logging
# ----------------------------

LOGGER = logging.getLogger("videotto")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
TEMP_DIR = BASE_DIR / "tmp"
load_dotenv(BASE_DIR / ".env")  # OPENAI_API_KEY


# ----------------------------
# Types / models
# ----------------------------

class TranscriptSegment(TypedDict):
    start: float
    end: float
    text: str


class ClipWithFrames(TypedDict):
    start: float
    end: float
    reason: str
    start_frame: int
    end_frame: int


class ClipOut(BaseModel):
    start: float
    end: float
    reason: str
    start_frame: int
    end_frame: int


class CreateJobRequest(BaseModel):
    videoUrl: str


class JobResponse(BaseModel):
    jobId: str
    status: str


class JobStatusResponse(BaseModel):
    jobId: str
    status: str
    statusMessage: Optional[str] = None
    clips: Optional[List[ClipOut]] = None
    error: Optional[str] = None


# Agent structured submission (LLM tool args)
class SubmittedClip(BaseModel):
    start: float = Field(..., description="start time in seconds")
    end: float = Field(..., description="end time in seconds")
    reason: str = Field(..., description="why this segment is viral; mention BOTH transcript and visual frames")


class SubmittedClips(BaseModel):
    clips: List[SubmittedClip] = Field(..., min_length=3, max_length=3, description="exactly 3 clips")


# Structured output from vision LLM (get_frames)
class VisionFrameAnalysis(BaseModel):
    """Analysis of video frames for a time segment."""

    analysis: str = Field(..., description="What is happening in the frames: people, expressions, text on screen, composition, energy.")
    evaluation: str = Field(..., description="Overall assessment of the visual content and quality.")
    virality_rationale: str = Field(..., description="Why this segment could or could not be viral: hook, punchline, visual surprise, shareability.")


# Structured output from analysis LLM (get_transcript)
class TranscriptSegmentAnalysis(BaseModel):
    """Analysis of a transcript segment."""

    summary: str = Field(..., description="What is said in this segment; key points and content.")
    evaluation: str = Field(..., description="Overall assessment of the transcript content and quality.")
    virality_rationale: str = Field(..., description="Why this segment could or could not work as a viral clip.")


# ----------------------------
# IO helpers
# ----------------------------

def ensure_temp_dir() -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR


def download_video_from_dropbox(url: str, filename: str = "input.mp4") -> Path:
    """
    Download a video from a Dropbox share link into our temp directory.
    Normalize to direct-download link (dl=1).
    """
    temp_dir = ensure_temp_dir()
    target_path = temp_dir / filename

    if "dl=0" in url:
        url = url.replace("dl=0", "dl=1")
    elif "dl=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}dl=1"

    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    with target_path.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return target_path


def extract_audio(video_path: Path, filename: str = "audio.wav") -> Path:
    """
    Extract mono 16kHz WAV using ffmpeg.
    """
    temp_dir = ensure_temp_dir()
    audio_path = temp_dir / filename

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return audio_path


def transcribe_with_whisper(audio_path: Path, model_name: str = "base") -> List[TranscriptSegment]:
    """
    Whisper local transcription -> list of segments.
    """
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), fp16=False)

    segments: List[TranscriptSegment] = []
    for seg in result.get("segments", []):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))
        text = (seg.get("text") or "").strip()
        if text:
            segments.append({"start": start, "end": end, "text": text})

    # optional debug dump
    transcript_path = ensure_temp_dir() / "transcript.txt"
    with transcript_path.open("w", encoding="utf-8") as f:
        for s in segments:
            f.write(f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}\n")

    return segments


def get_video_fps(video_path: Path) -> float:
    """
    Return fps using ffprobe. Fallback 30.0
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=r_frame_rate",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10)
        rate_str = (r.stdout or "").strip()
        if "/" in rate_str:
            num_s, den_s = rate_str.split("/", 1)
            num, den = float(num_s.strip()), float(den_s.strip())
            return num / den if den else 30.0
        return float(rate_str) if rate_str else 30.0
    except Exception as e:
        LOGGER.warning("get_video_fps failed (%s), fallback 30.0", e)
        return 30.0


def get_video_duration(video_path: Path) -> float:
    """
    Return video duration in seconds using ffprobe. Fallback 0.0 on failure.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10)
        s = (r.stdout or "").strip()
        return float(s) if s else 0.0
    except Exception as e:
        LOGGER.warning("get_video_duration failed (%s), fallback 0.0", e)
        return 0.0


def get_transcript_for_range(start_s: float, end_s: float, transcript_segments: List[TranscriptSegment]) -> str:
    """
    Transcript slice that overlaps [start_s,end_s]
    """
    lines: List[str] = []
    for seg in transcript_segments:
        if seg["end"] <= start_s or seg["start"] >= end_s:
            continue
        lines.append(f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")
    return "\n".join(lines) if lines else "(No transcript in this range.)"


def extract_frames_as_base64(video_path: Path, start_s: float, end_s: float, num_frames: int = 8) -> List[str]:
    """
    Extract frames as base64 JPEG payloads (no prefix).
    One-call strategy for multi-frame (writes temp files then reads).
    Clamps the requested range to the actual video duration to avoid ffmpeg errors.
    """
    if not video_path.exists():
        return []
    if start_s >= end_s:
        return []
    video_duration_s = get_video_duration(video_path)
    if video_duration_s <= 0:
        return []
    # Clamp to valid range so we never seek past end of file (avoids ffmpeg exit 234)
    start_s = max(0.0, min(start_s, video_duration_s - 0.5))
    end_s = min(end_s, video_duration_s)
    if start_s >= end_s:
        return []
    duration = end_s - start_s
    num_frames = max(1, min(24, int(num_frames)))
    out: List[str] = []

    if num_frames == 1:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(start_s),
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-f",
            "image2",
            "-c:v",
            "mjpeg",
            "pipe:1",
        ]
        try:
            r = subprocess.run(cmd, check=True, capture_output=True, timeout=20)
            if r.stdout:
                out.append(base64.b64encode(r.stdout).decode("ascii"))
        except Exception as e:
            LOGGER.warning("extract_frames_as_base64(single) failed: %s", e)
        return out

    frames_dir = ensure_temp_dir() / "agent_frames"
    frames_dir.mkdir(exist_ok=True)
    token = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
    pattern = frames_dir / f"frm_{token}_%04d.jpg"

    fps_val = num_frames / duration if duration > 0 else 1.0
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(start_s),
        "-i",
        str(video_path),
        "-t",
        str(duration),
        "-vf",
        f"fps={fps_val:.6f}",
        "-vframes",
        str(num_frames),
        "-q:v",
        "3",
        str(pattern),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=45)
        for p in sorted(frames_dir.glob(f"frm_{token}_*.jpg")):
            try:
                data = p.read_bytes()
                if data:
                    out.append(base64.b64encode(data).decode("ascii"))
            finally:
                try:
                    p.unlink()
                except OSError:
                    pass
    except Exception as e:
        LOGGER.warning("extract_frames_as_base64(multi) failed: %s", e)

    return out


def segments_to_clips_with_frames(segments: List[Dict[str, Any]], fps: float) -> List[ClipWithFrames]:
    """
    seconds -> frame indices
    end_frame is exclusive.
    """
    res: List[ClipWithFrames] = []
    for seg in segments:
        start_s = float(seg["start"])
        end_s = float(seg["end"])
        res.append(
            {
                "start": start_s,
                "end": end_s,
                "reason": str(seg.get("reason", "")),
                "start_frame": int(start_s * fps),
                "end_frame": int(math.ceil(end_s * fps)),
            }
        )
    return res


# ----------------------------
# Agent (two analysis tools + finalizer)
# ----------------------------

VISION_FRAME_PROMPT = """You are analyzing video frames from a short segment (start to end in seconds). Describe what is happening visually, evaluate the content, and explain why this segment could or could not go viral. Be concise and specific."""

TRANSCRIPT_ANALYSIS_PROMPT = """You are analyzing a transcript segment for viral short-form potential. Summarize what is said, highlight key moments and rationale, and explain why this segment could or could not work as a viral clip. Be concise and specific."""

SYSTEM_PROMPT = """You are a viral clip analyst. Your job is to watch a full video, build a visual and textual understanding of it, and pick exactly 3 clips that have the highest viral potential for short-form (e.g. TikTok, Reels).

You have three tools:
- get_frames(start, end, num_frames): returns a textual analysis of the visuals for a time range. Use this to build a sequential visual picture of the whole video.
- get_transcript(start, end): returns a textual analysis of the transcript for a time range. Use this to get more context on segments that look interesting from the frames.
- submit_top_clips(payload): call once when you are done; pass exactly 3 clips.

Process:
1) Scan the video visually first: call get_frames in sequence (e.g. in chunks over the full duration) to get a visual imaging of the whole video from the frame analyses.
2) For any segments that look interesting or viral from the visual analysis, call get_transcript for those ranges to get more information (what is said, key moments).
3) Using the combined information from the visual analysis and the transcript analysis, choose the best 3 clips and call submit_top_clips EXACTLY ONCE with exactly 3 clips.

Viral scoring (use both visuals and transcript in your reasoning):
- Strong hook in the first 1 - 2 seconds
- Emotional punch (surprise, humor, tension, awe)
- Clear without heavy context
- Visual novelty / compelling visuals
- Quick payoff

Constraints:
- Each clip should usually be about 2 - 3 seconds (viral short-form length); only go longer if the content strongly justifies it.
- For each clip, the reason MUST cite what you gathered from both the visual (frame) analysis and the transcript analysis, and why you think it has virality.
- You will be told the video duration in seconds; you must only call get_frames and get_transcript with start and end within [0, that duration]. Submitted clips must also fall within that range.
"""


def run_viral_clips_agent(
    transcript_segments: List[TranscriptSegment],
    video_path: Path,
    api_key: Optional[str] = None,
    model: str = "gpt-4o",
    max_rounds: int = 25,
) -> List[ClipWithFrames]:
    """
    Agent uses get_frames + get_transcript repeatedly, then submits exactly 3 clips.
    Returns clips with frame indices.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key or not transcript_segments or not video_path.exists():
        return []

    video_duration_s = get_video_duration(video_path)
    if video_duration_s <= 0:
        LOGGER.warning("get_video_duration returned %s; agent may request out-of-range times", video_duration_s)
    duration_note = (
        f"This video is {video_duration_s:.1f} seconds long. "
        "You must only call get_frames and get_transcript with start and end within [0, {:.1f}]. "
        "Submitted clips must have start and end within that range.".format(video_duration_s)
    )

    submitted: Dict[str, Any] = {"clips": None}

    def make_tools() -> List[Any]:
        vision_llm = ChatOpenAI(api_key=key, model=model, temperature=0).with_structured_output(VisionFrameAnalysis)
        analysis_llm = ChatOpenAI(api_key=key, model=model, temperature=0).with_structured_output(TranscriptSegmentAnalysis)

        @tool
        def get_frames(start: float, end: float, num_frames: int = 8) -> str:
            """Use this tool to get a visual analysis of frames in a time range. Pass start and end in seconds; optionally num_frames (default 8). You receive a textual analysis of what is visible and viral potential. Call this sequentially over the video to build a visual overview first; then use get_transcript for segments that look interesting."""
            b64_list = extract_frames_as_base64(video_path, start, end, num_frames=num_frames)
            if not b64_list:
                return "No frames extracted (ffmpeg failed or range invalid)."
            content: List[Dict[str, Any]] = [
                {"type": "text", "text": f"{VISION_FRAME_PROMPT}\n\nSegment: {start:.2f}s to {end:.2f}s ({len(b64_list)} frames)."}
            ]
            for b64 in b64_list:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
            msg = HumanMessage(content=content)
            out = vision_llm.invoke([msg])
            return f"Analysis: {out.analysis}\nEvaluation: {out.evaluation}\nVirality: {out.virality_rationale}"

        @tool
        def get_transcript(start: float, end: float) -> str:
            """Use this tool to get a textual analysis of the transcript for a time range. Pass start and end in seconds. You receive summary, evaluation, and virality rationale. Call it for segments that look interesting from your frame analysis to get more context before choosing your top 3 clips."""
            # Clamp to video duration so we never request beyond the file
            start_clamped = max(0.0, min(start, video_duration_s))
            end_clamped = min(end, video_duration_s)
            if start_clamped >= end_clamped:
                return "(No transcript in this range; requested range is outside or past the video duration.)"
            raw = get_transcript_for_range(start_clamped, end_clamped, transcript_segments)
            if not raw or raw.strip() == "(No transcript in this range.)":
                return raw
            prompt = f"""{TRANSCRIPT_ANALYSIS_PROMPT}

            Segment: {start_clamped:.1f}s–{end_clamped:.1f}s

            Transcript:
            {raw}"""

            out = analysis_llm.invoke([HumanMessage(content=prompt)])
            return f"Summary: {out.summary}\nEvaluation: {out.evaluation}\nVirality: {out.virality_rationale}"

        @tool
        def submit_top_clips(payload: SubmittedClips) -> str:
            """Call this only when you have finished analyzing the video and are ready to submit your final answer. You must provide exactly 3 clips. Each clip must have: start (seconds), end (seconds), and reason (a short explanation of why it is viral—you must mention both what is said in the transcript and what is seen in the frames). Call this tool exactly once with your top 3 clips."""
            # Validate additional sanity and duration bounds
            clips = payload.clips
            for i, c in enumerate(clips):
                if c.end <= c.start:
                    return f"Clip {i} invalid: end <= start."
                if c.start < 0 or c.end > video_duration_s:
                    return f"Clip {i} out of range: start/end must be within [0, {video_duration_s:.1f}] (video duration)."
                if c.end - c.start > 120:
                    return f"Clip {i} too long ({c.end - c.start:.1f}s). Keep it short-form."
                if not c.reason.strip():
                    return f"Clip {i} reason empty."
            submitted["clips"] = [c.model_dump() for c in clips]
            return "Submitted. Analysis complete."

        return [get_frames, get_transcript, submit_top_clips]

    tools = make_tools()
    llm = ChatOpenAI(api_key=key, model=model, temperature=0)
    system_prompt_with_duration = SYSTEM_PROMPT + "\n\n" + duration_note
    agent = create_agent(llm, tools=tools, system_prompt=system_prompt_with_duration)

    initial = {
        "messages": [
            HumanMessage(
                content=(
                    f"The video is ready and is {video_duration_s:.1f} seconds long. "
                    f"Only use start and end within [0, {video_duration_s:.1f}] when calling get_frames or get_transcript. "
                    "First, scan the whole video by calling get_frames in sequence to build a visual overview from the frame analyses. "
                    "For any segments that look interesting, call get_transcript to get more context. "
                    "Then, using the combined visual and transcript information, submit exactly 3 viral clips (typically 2 - 3 seconds each) with submit_top_clips, "
                    "and in each clip's reason explain what you saw and heard and why it has viral potential."
                )
            )
        ]
    }

    agent.invoke(initial, config={"recursion_limit": max_rounds})

    clips = submitted.get("clips")
    if not clips or len(clips) != 3:
        return []

    fps = get_video_fps(video_path)
    return segments_to_clips_with_frames(clips, fps)