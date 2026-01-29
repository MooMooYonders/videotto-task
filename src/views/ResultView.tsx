import React from "react";
import type { Clip } from "../types";

export type ResultViewProps = {
  error: string | null;
  clips: Clip[];
  onBack: () => void;
  formatTime: (seconds: number) => string;
};

const cardStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid rgba(0,0,0,0.08)",
  borderRadius: 12,
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
  textAlign: "left",
  boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
};

const imageWrapStyle: React.CSSProperties = {
  width: "100%",
  aspectRatio: "16/9",
  background: "#111",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  overflow: "hidden",
  flexShrink: 0,
};

const bodyStyle: React.CSSProperties = {
  padding: "16px 18px",
  flex: 1,
  background: "#f8f9fa",
};

export function ResultView({ error, clips, onBack, formatTime }: ResultViewProps) {
  const containerStyle: React.CSSProperties = {
    maxWidth: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    margin: "40px auto",
    fontFamily: "system-ui",
  };

  return (
    <div style={containerStyle}>
      {error ? (
        <div style={{ marginBottom: 24, textAlign: "center" }}>
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
          <h2 style={{ fontSize: 20, marginBottom: 24, fontWeight: 600 }}>
            Top 3 clips
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 24,
              width: "100%",
              maxWidth: 960,
            }}
          >
            {clips.map((clip, i) => (
              <article key={i} style={cardStyle}>
                <div style={imageWrapStyle}>
                  {clip.thumbnail ? (
                    <img
                      src={`data:image/jpeg;base64,${clip.thumbnail}`}
                      alt={`Clip ${i + 1}: ${formatTime(clip.start)} – ${formatTime(clip.end)}`}
                      style={{
                        display: "block",
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                        verticalAlign: "bottom",
                        filter: "contrast(1.12) brightness(0.98)",
                      }}
                    />
                  ) : (
                    <span style={{ color: "#666", fontSize: 14 }}>
                      No preview
                    </span>
                  )}
                </div>
                <div style={bodyStyle}>
                  <p
                    style={{
                      margin: "0 0 8px",
                      fontSize: 13,
                      color: "#1a1a1a",
                      fontWeight: 600,
                    }}
                  >
                    Clip {i + 1} · {formatTime(clip.start)} – {formatTime(clip.end)}
                  </p>
                  <p
                    style={{
                      margin: 0,
                      fontSize: 14,
                      color: "#333",
                      lineHeight: 1.45,
                    }}
                  >
                    {clip.reason}
                  </p>
                </div>
              </article>
            ))}
          </div>
          <button
            type="button"
            className="analyze-button"
            onClick={onBack}
            style={{ padding: "10px 20px", marginTop: 32 }}
          >
            Back
          </button>
        </>
      )}
    </div>
  );
}
