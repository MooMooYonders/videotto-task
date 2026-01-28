import React, { useState } from "react";
import { ProcessingStatus } from "./enums/status";
import type { ProcessingStatusValue } from "./enums/status";

function App() {
  const [videoUrl, setVideoUrl] = useState("");
  const [status, setStatus] = useState<ProcessingStatusValue>(ProcessingStatus.Idle);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (!videoUrl.trim()) {
      setError("Please enter a video URL.");
      return;
    }

    // For this minimum PR: simulate processing
    setStatus(ProcessingStatus.Processing);
    setTimeout(() => {
      setStatus(ProcessingStatus.Completed);
    }, 1500);
  };

  return (
    <div style={{ maxWidth: 600, margin: "40px auto", fontFamily: "system-ui" }}>
      <h1>Videotto Clip Finder</h1>
      <p>Paste a video link to analyze its best clips.</p>

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label>
          Video URL
          <input
            type="url"
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

        <button type="submit" style={{ padding: "8px 12px" }}>
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
