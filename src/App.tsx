import React, { useState, useEffect, useRef } from "react";
import "./App.css";
import { ProcessingStatus } from "./enums/status";
import type { ProcessingStatusValue } from "./enums/status";
import type { Clip } from "./types";
import { InputView, ProcessingView, ResultView } from "./views";

const API_BASE = "http://localhost:8000";

type JobResponse = {
  jobId: string;
  status: string;
};

type JobStatusResponse = {
  jobId: string;
  status: string;
  statusMessage?: string;
  clips?: Clip[];
  error?: string;
};

type View = "input" | "processing" | "result";

function App() {
  const [view, setView] = useState<View>("input");
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
          setView("result");
        } else if (data.status === "failed") {
          stopPolling();
          setError(data.error ?? "Analysis failed.");
          setStepMessage("");
          setStatus(ProcessingStatus.Failed);
          setView("result");
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
      setView("processing");
      if (data.status === "completed") {
        setStatus(ProcessingStatus.Completed);
        setView("result");
      } else if (data.status === "failed") {
        setStatus(ProcessingStatus.Failed);
      }
    } catch (err) {
      console.error(err);
      setError("Failed to start video analysis. Please try again.");
      setStatus(ProcessingStatus.Failed);
    }
  };

  const handleBack = () => {
    setView("input");
    setJobId(null);
    setClips([]);
    setError(null);
    setStepMessage("");
    setStatus(ProcessingStatus.Idle);
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  if (view === "input") {
    return (
      <InputView
        videoUrl={videoUrl}
        setVideoUrl={setVideoUrl}
        error={error}
        onSubmit={handleSubmit}
      />
    );
  }

  if (view === "processing") {
    return <ProcessingView stepMessage={stepMessage} />;
  }

  return (
    <ResultView
      error={error}
      clips={clips}
      onBack={handleBack}
      formatTime={formatTime}
    />
  );
}

export default App;
