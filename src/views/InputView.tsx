import React from "react";

export type InputViewProps = {
  videoUrl: string;
  setVideoUrl: (value: string) => void;
  error: string | null;
  onSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
};

export function InputView({ videoUrl, setVideoUrl, error, onSubmit }: InputViewProps) {
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
      <h1>Videotto Clip Finder</h1>
      <p>Paste a video link to analyze its best clips.</p>

      <form
        onSubmit={onSubmit}
        noValidate
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 12,
          width: "100%",
          justifyContent: "center",
          alignItems: "center",
        }}
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
          <div style={{ color: "red", fontSize: 14 }}>{error}</div>
        )}

        <button
          type="submit"
          className="analyze-button"
          style={{ padding: "8px 12px", width: "40%" }}
        >
          Analyze Video
        </button>
      </form>
    </div>
  );
}
