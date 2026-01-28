from __future__ import annotations

from pathlib import Path
import array
import logging
import math
import os
import re
import subprocess
import sys
import wave
from typing import TypedDict, List, Tuple, Optional

import requests
import whisper
from openai import OpenAI
from pydantic import BaseModel

LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DIR = BASE_DIR / "tmp"


def ensure_temp_dir() -> Path:
    """Ensure the temporary directory for intermediate files exists."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR


def download_video_from_dropbox(url: str, filename: str = "input.mp4") -> Path:
    """
    Download a video from a Dropbox share link into our temp directory.

    We normalise the URL to a direct-download link (`dl=1`) so requests can fetch it.
    """
    temp_dir = ensure_temp_dir()
    target_path = temp_dir / filename

    # Normalise Dropbox URL to a direct-download link
    if "dl=0" in url:
        url = url.replace("dl=0", "dl=1")
    elif "dl=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}dl=1"

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    with target_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return target_path


def extract_audio(video_path: Path, filename: str = "audio.wav") -> Path:
    """
    Extract a mono 16kHz WAV track from the video using ffmpeg.

    This keeps the audio in a speech-friendly format for both transcription
    and simple energy analysis.
    """
    temp_dir = ensure_temp_dir()
    audio_path = temp_dir / filename

    cmd = [
        "ffmpeg",
        "-y",  # overwrite output if it exists
        "-i",
        str(video_path),
        "-vn",  # no video
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",  # 16 kHz
        "-ac",
        "1",  # mono
        str(audio_path),
    ]

    # We intentionally ignore stdout/stderr here to keep logs clean.
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return audio_path


def transcribe_with_whisper(audio_path: Path, model_name: str = "base") -> List["TranscriptSegment"]:
    """
    Transcribe audio using OpenAI Whisper. Returns segments with start, end, and text.
    """
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), fp16=False)
    segments: List[TranscriptSegment] = []
    for seg in result.get("segments", []):
        start = float(seg.get("start", 0))
        end = float(seg.get("end", 0))
        text = (seg.get("text") or "").strip()
        if text:
            segments.append({"start": start, "end": end, "text": text})
    return segments


class TranscriptSegment(TypedDict):
    start: float
    end: float
    text: str


class LLMSegment(TypedDict):
    start: float
    end: float
    reason: str


# Pydantic models for OpenAI structured output (LLM: exactly 3 viral segments)
class LLMSegmentOutput(BaseModel):
    start: float
    end: float
    reason: str


class LLMHighLevelResponse(BaseModel):
    segments: List[LLMSegmentOutput]


def llm_identify_high_level_segments(
    transcript_segments: List[TranscriptSegment],
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
    top_n: int = 3,
) -> List[LLMSegment]:
    """
    Ask an LLM to screen the transcript and identify exactly the top_n most viral segments.
    Returns list of { start, end, reason }. Uses OPENAI_API_KEY if api_key not passed.
    """
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key or not transcript_segments:
        return []

    lines = []
    for seg in transcript_segments:
        lines.append(f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")
    transcript_text = "\n".join(lines)

    system = (
        "You are an expert at identifying viral short-form video moments. "
        "Screen the transcript below and identify exactly the 3 most viral segments. "
        "Use the timestamps (start and end in seconds) from the transcript for each segment. "
        "For each segment output: start (seconds), end (seconds), and a short rationale explaining why that segment is viral (e.g. hook, key insight, emotional peak, punchline). "
        "Output exactly 3 segments."
    )
    user = f"Transcript:\n{transcript_text}"

    try:
        client = OpenAI(api_key=api_key)
        completion = client.beta.chat.completions.parse(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=LLMHighLevelResponse,
            temperature=0.3,
        )
        message = completion.choices[0].message
        if getattr(message, "refusal", None):
            LOGGER.warning("LLM refused: %s", message.refusal)
            return []
        parsed = message.parsed
        if parsed is None:
            return []
        segments = [{"start": seg.start, "end": seg.end, "reason": seg.reason} for seg in parsed.segments]
        return segments[:top_n]
    except Exception as e:
        LOGGER.warning("LLM step failed: %s", e)
        return []


def get_video_fps(video_path: Path) -> float:
    """
    Return the video frame rate (fps) using ffprobe.
    Falls back to 30.0 if ffprobe fails or output is unparseable.
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
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10)
        rate_str = (result.stdout or "").strip()
        if "/" in rate_str:
            num_str, den_str = rate_str.split("/", 1)
            num, den = float(num_str.strip()), float(den_str.strip())
            if den and den != 0:
                return num / den
        return float(rate_str) if rate_str else 30.0
    except Exception as e:
        LOGGER.warning("get_video_fps failed (%s), using 30.0", e)
        return 30.0


class ClipWithFrames(TypedDict):
    start: float
    end: float
    reason: str
    start_frame: int
    end_frame: int


def segments_to_clips_with_frames(
    segments: List[LLMSegment],
    fps: float,
) -> List[ClipWithFrames]:
    """
    Convert time-based segments (seconds) to clips with frame indices.
    Frames are 0-based; end_frame is exclusive (last frame of the segment is end_frame - 1).
    """
    result: List[ClipWithFrames] = []
    for seg in segments:
        start_s, end_s = seg["start"], seg["end"]
        start_frame = int(start_s * fps)
        end_frame = int(math.ceil(end_s * fps))
        result.append({
            "start": start_s,
            "end": end_s,
            "reason": seg["reason"],
            "start_frame": start_frame,
            "end_frame": end_frame,
        })
    return result


def llm_top_three_viral_clips(
    transcript_segments: List[TranscriptSegment],
    video_path: Optional[Path] = None,
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
) -> List[ClipWithFrames]:
    """
    LLM as primary: screen transcript, get exactly 3 viral segments with rationale,
    then attach frame indices (if video_path is provided).
    Returns list of { start, end, reason, start_frame, end_frame }.
    """
    segments = llm_identify_high_level_segments(
        transcript_segments, api_key=api_key, model=model, top_n=3
    )
    if not segments:
        return []
    fps = get_video_fps(video_path) if video_path and video_path.exists() else 30.0
    return segments_to_clips_with_frames(segments, fps)


def detect_speech_segments(audio_path: Path, noise_db: int = -30, min_silence: float = 0.4) -> List[TranscriptSegment]:
    """
    Approximate speech segments using ffmpeg's silencedetect filter.

    This does not generate text, but it detects regions of non-silence which we
    treat as "speech-like" segments for ranking.
    """
    duration = _get_audio_duration_seconds(audio_path)
    cmd = [
        "ffmpeg",
        "-i",
        str(audio_path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f",
        "null",
        "-",
    ]

    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or "")[-500:] if isinstance(getattr(exc, "stderr", None), str) else str(exc)
        LOGGER.warning("silencedetect failed: %s", stderr_tail)
        return []

    silence_intervals = _parse_silence_intervals(result.stderr)
    non_silence_intervals = _invert_intervals(silence_intervals, 0.0, duration)

    segments: List[TranscriptSegment] = []
    for start, end in non_silence_intervals:
        if end - start <= 0.2:
            continue
        segments.append({"start": float(start), "end": float(end), "text": "Speech detected"})
    return segments


class EnergySegment(TypedDict):
    start: float
    end: float
    energy: float


def compute_energy_segments(audio_path: Path, window_s: float = 0.5) -> List[EnergySegment]:
    """
    Compute windowed RMS energy over the waveform using the standard library.
    """
    segments: List[EnergySegment] = []
    with wave.open(str(audio_path), "rb") as wf:
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        channels = wf.getnchannels()

        if sample_width != 2:
            raise ValueError(f"Expected 16-bit PCM WAV, got sample width {sample_width}")

        if channels != 1:
            raise ValueError(f"Expected mono WAV, got {channels} channels")

        window_frames = max(1, int(sample_rate * window_s))
        window_bytes = window_frames * sample_width * channels
        max_rms = float(2 ** (sample_width * 8 - 1))

        start_time = 0.0
        while True:
            data = wf.readframes(window_frames)
            if not data:
                break
            samples = array.array("h")
            samples.frombytes(data)
            if sys.byteorder != "little":
                samples.byteswap()
            if samples:
                mean_square = sum(sample * sample for sample in samples) / float(len(samples))
                rms = math.sqrt(mean_square)
            else:
                rms = 0.0
            energy = min(1.0, rms / max_rms) if rms else 0.0
            end_time = start_time + (len(data) / (sample_rate * sample_width * channels))
            segments.append({"start": start_time, "end": end_time, "energy": energy})
            start_time = end_time

    return segments


class ClipCandidate(TypedDict):
    start: float
    end: float
    score: float
    reason: str


def _llm_overlap_score(start: float, end: float, llm_segments: List[LLMSegment]) -> Tuple[float, Optional[str]]:
    """Return (0-1 score, best matching LLM reason or None)."""
    if not llm_segments:
        return 0.0, None
    best_score = 0.0
    best_reason: Optional[str] = None
    clip_len = end - start
    if clip_len <= 0:
        return 0.0, None
    for seg in llm_segments:
        overlap = _overlap_seconds(start, end, seg["start"], seg["end"])
        frac = overlap / clip_len
        if frac > best_score:
            best_score = min(1.0, frac)
            best_reason = seg.get("reason") or None
    return best_score, best_reason


def select_top_clips(
    energy_segments: List[EnergySegment],
    speech_segments: List[TranscriptSegment],
    top_n: int = 3,
    clip_duration: float = 8.0,
    llm_segments: Optional[List[LLMSegment]] = None,
) -> List[ClipCandidate]:
    """
    Pick top clips using a mix of audio energy, speech coverage, and LLM-identified high-level segments.
    When llm_segments is provided, scoring weights: 0.25 energy + 0.25 speech + 0.5 LLM overlap.
    Otherwise: 0.7 energy + 0.3 speech (backward compatible).
    """
    if not energy_segments:
        return []

    duration = energy_segments[-1]["end"]
    use_llm = bool(llm_segments)
    candidates: List[Tuple[float, float, float, float, Optional[str]]] = []

    for segment in energy_segments:
        center = (segment["start"] + segment["end"]) / 2.0
        start = max(0.0, center - clip_duration / 2.0)
        end = min(duration, start + clip_duration)
        start = max(0.0, end - clip_duration)

        speech_coverage = _overlap_fraction(start, end, speech_segments)
        llm_score, llm_reason = _llm_overlap_score(start, end, llm_segments or [])

        if use_llm:
            score = (segment["energy"] * 0.25) + (speech_coverage * 0.25) + (llm_score * 0.5)
        else:
            score = (segment["energy"] * 0.7) + (speech_coverage * 0.3)
        candidates.append((start, end, score, segment["energy"], llm_reason))

    # Sort by score, then energy
    candidates.sort(key=lambda c: (c[2], c[3]), reverse=True)

    selected: List[ClipCandidate] = []
    for start, end, score, energy, llm_reason in candidates:
        if _overlaps_existing(start, end, selected):
            continue
        if llm_reason:
            reason = llm_reason
        else:
            speech_pct = int(round(_overlap_fraction(start, end, speech_segments) * 100))
            reason = (
                f"High audio energy (RMS {energy:.2f}) with speech present ~{speech_pct}% of the clip."
            )
        selected.append({"start": start, "end": end, "score": score, "reason": reason})
        if len(selected) >= top_n:
            break

    return selected


def _get_audio_duration_seconds(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as wf:
        frames = wf.getnframes()
        return frames / float(wf.getframerate())


def _parse_silence_intervals(stderr: str) -> List[Tuple[float, float]]:
    starts: List[float] = []
    ends: List[float] = []
    for line in stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            starts.append(float(start_match.group(1)))
            continue
        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match:
            ends.append(float(end_match.group(1)))

    intervals: List[Tuple[float, float]] = []
    for idx, start in enumerate(starts):
        if idx < len(ends):
            intervals.append((start, ends[idx]))
    return intervals


def _invert_intervals(intervals: List[Tuple[float, float]], start: float, end: float) -> List[Tuple[float, float]]:
    if not intervals:
        return [(start, end)]

    intervals = sorted(intervals, key=lambda item: item[0])
    result: List[Tuple[float, float]] = []
    current = start
    for interval_start, interval_end in intervals:
        if interval_start > current:
            result.append((current, min(interval_start, end)))
        current = max(current, interval_end)
        if current >= end:
            break
    if current < end:
        result.append((current, end))
    return result


def _overlap_fraction(start: float, end: float, segments: List[TranscriptSegment]) -> float:
    if end <= start:
        return 0.0
    total = end - start
    overlap = 0.0
    for seg in segments:
        overlap += _overlap_seconds(start, end, seg["start"], seg["end"])
    return min(1.0, overlap / total)


def _overlap_seconds(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _overlaps_existing(start: float, end: float, selected: List[ClipCandidate]) -> bool:
    for clip in selected:
        if _overlap_seconds(start, end, clip["start"], clip["end"]) > 0.5:
            return True
    return False
