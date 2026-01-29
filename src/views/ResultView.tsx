import React from "react";
import type { Clip } from "../types";

export type ResultViewProps = {
  error: string | null;
  clips: Clip[];
  onBack: () => void;
  formatTime: (seconds: number) => string;
};

export function ResultView({ error, clips, onBack, formatTime }: ResultViewProps) {
  const containerStyle: React.CSSProperties = {
    maxWidth: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    margin: "40px auto",
    fontFamily: "system-ui",
    textAlign: "center",
  };

  return (
    <div style={containerStyle}>
      {error ? (
        <div style={{ marginBottom: 24 }}>
          <p style={{ color: "red", marginBottom: 16 }}>{error}</p>
          <button
            type="button"
            className="analyze-button"
            onClick={onBack}
            style={{ padding: "8px 16px" }}
          >
            Back
          </button>
        </div>
      ) : (
        <>
          <h2 style={{ fontSize: 18, marginBottom: 16 }}>Top 3 clips</h2>
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              width: "100%",
              maxWidth: 600,
              textAlign: "left",
            }}
          >
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
                <strong>Clip {i + 1}</strong> {formatTime(clip.start)} –{" "}
                {formatTime(clip.end)}
                <p style={{ margin: "8px 0 0", fontSize: 14, color: "#aaa" }}>
                  {clip.reason}
                </p>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="analyze-button"
            onClick={onBack}
            style={{ padding: "8px 16px", marginTop: 24 }}
          >
            Back
          </button>
        </>
      )}
    </div>
  );
}
