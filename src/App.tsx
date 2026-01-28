import React, { useState } from "react";
import "./App.css";
import { ProcessingStatus } from "./enums/status";
import type { ProcessingStatusValue } from "./enums/status";

type JobResponse = {
  jobId: string;
  status: string;
};

function App() {
  const [videoUrl, setVideoUrl] = useState("");
  const [status, setStatus] = useState<ProcessingStatusValue>(ProcessingStatus.Idle);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (!videoUrl.trim()) {
      setError("Please enter a video URL.");
      return;
    }

    // Call backend to create a processing job
    setStatus(ProcessingStatus.Processing);
    try {
      const response = await fetch("http://localhost:8000/api/jobs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ videoUrl }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data: JobResponse = await response.json();
      // For now we only care that the backend accepted the job.
      // Later we can store data.jobId and poll for real status.
      if (data.status.toLowerCase() === "ok") {
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
        >
          Analyze Video
        </button>
      </form>

      <div style={{ marginTop: 24, fontSize: 14 }}>
        <strong>Status: </strong>
        {status === ProcessingStatus.Idle && "Waiting for input"}
        {status === ProcessingStatus.Processing && "Processing video..."}
        {status === ProcessingStatus.Completed && "Analysis completed (mocked for now)."}
        {status === ProcessingStatus.Failed && "Analysis failed."}
      </div>
    </div>
  );
}

export default App;
