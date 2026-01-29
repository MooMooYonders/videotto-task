import React, { useState, useEffect, useRef } from "react";
import "./App.css";
import { ProcessingStatus } from "./enums/status";
import type { ProcessingStatusValue } from "./enums/status";

const API_BASE = "http://localhost:8000";

type JobResponse = {
  jobId: string;
  status: string;
};

type Clip = {
  start: number;
  end: number;
  reason: string;
  start_frame: number;
  end_frame: number;
};

type JobStatusResponse = {
  jobId: string;
  status: string;
  statusMessage?: string;
  clips?: Clip[];
  error?: string;
};

const PROCESSING_STEPS = [
  "Starting...",
  "Downloading video...",
  "Extracting audio...",
  "Transcribing speech...",
  "Identifying viral clips...",
] as const;

function App() {
  const [videoUrl, setVideoUrl] = useState("");
  const [status, setStatus] = useState<ProcessingStatusValue>(ProcessingStatus.Idle);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [stepMessage, setStepMessage] = useState<string>("");
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  useEffect(() => {
    return () => stopPolling();
  }, []);

  useEffect(() => {
    if (!jobId || status !== ProcessingStatus.Processing) return;

    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
        if (!res.ok) return;
        const data: JobStatusResponse = await res.json();
        if (data.statusMessage) setStepMessage(data.statusMessage);
        if (data.status === "completed") {
          stopPolling();
          setClips(data.clips ?? []);
          setStepMessage("");
          setStatus(ProcessingStatus.Completed);
        } else if (data.status === "failed") {
          stopPolling();
          setError(data.error ?? "Analysis failed.");
          setStepMessage("");
          setStatus(ProcessingStatus.Failed);
        }
      } catch {
        // keep polling on network error
      }
    };

    poll();
    pollIntervalRef.current = setInterval(poll, 2000);
    return () => stopPolling();
  }, [jobId, status]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setClips([]);
    setJobId(null);
    setStepMessage("Starting...");

    if (!videoUrl.trim()) {
      setError("Please enter a video URL.");
      return;
    }

    setStatus(ProcessingStatus.Processing);
    try {
      const response = await fetch(`${API_BASE}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ videoUrl }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data: JobResponse = await response.json();
      setJobId(data.jobId);
      if (data.status === "processing") {
        // polling started by useEffect
      } else if (data.status === "completed") {
        setStatus(ProcessingStatus.Completed);
      } else {
        setStatus(ProcessingStatus.Failed);
      }
    } catch (err) {
      console.error(err);
      setError("Failed to start video analysis. Please try again.");
      setStatus(ProcessingStatus.Failed);
    }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div
      style={{
        maxWidth: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        margin: "40px auto",
        fontFamily: "system-ui",
        textAlign: "center",
      }}
    >
      <h1>Videotto Clip Finder</h1>
      <p>Paste a video link to analyze its best clips.</p>

      <form
        onSubmit={handleSubmit}
        noValidate
        style={{ display: "flex", flexDirection: "column", gap: 12, width: "100%", justifyContent: "center", alignItems: "center" }}
      >
        <label style={{ width: "100%" }}>
          Video URL
          <input
            type="text"
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            placeholder="https://www.dropbox.com/..."
            style={{ width: "100%", padding: 8, marginTop: 4 }}
          />
        </label>

        {error && (
          <div style={{ color: "red", fontSize: 14 }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          className="analyze-button"
          style={{ padding: "8px 12px", width: "40%" }}
          disabled={status === ProcessingStatus.Processing}
        >
          Analyze Video
        </button>
      </form>

      <div style={{ marginTop: 24, fontSize: 14 }}>
        <strong>Status: </strong>
        {status === ProcessingStatus.Idle && "Waiting for input"}
        {status === ProcessingStatus.Processing && (
          <span>{stepMessage || "Processing video..."}</span>
        )}
        {status === ProcessingStatus.Completed && "Analysis completed."}
        {status === ProcessingStatus.Failed && "Analysis failed."}
      </div>

      {status === ProcessingStatus.Processing && (
        <div className="processing-loader" style={{ marginTop: 24 }}>
          <div className="processing-spinner" aria-hidden />
          <div className="processing-steps">
            {PROCESSING_STEPS.map((step) => (
              <div
                key={step}
                className={`processing-step ${stepMessage === step ? "processing-step--active" : ""}`}
              >
                <span className="processing-step-dot" />
                {step}
              </div>
            ))}
          </div>
        </div>
      )}

      {clips.length > 0 && (
        <div style={{ marginTop: 24, width: "100%", maxWidth: 600, textAlign: "left" }}>
          <h2 style={{ fontSize: 18 }}>Top 3 clips</h2>
          <ul style={{ listStyle: "none", padding: 0 }}>
            {clips.map((clip, i) => (
              <li
                key={i}
                style={{
                  marginBottom: 16,
                  padding: 12,
                  border: "1px solid #333",
                  borderRadius: 8,
                }}
              >
                <strong>Clip {i + 1}</strong> {formatTime(clip.start)} – {formatTime(clip.end)}
                <p style={{ margin: "8px 0 0", fontSize: 14, color: "#aaa" }}>{clip.reason}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default App;
