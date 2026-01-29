import React from "react";

const PROCESSING_STEPS = [
  "Starting...",
  "Downloading video...",
  "Extracting audio...",
  "Transcribing speech...",
  "Identifying viral clips...",
] as const;

export type ProcessingViewProps = {
  stepMessage: string;
};

export function ProcessingView({ stepMessage }: ProcessingViewProps) {
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
      <div style={{ marginBottom: 16, fontSize: 14 }}>
        <strong>Status: </strong>
        <span>{stepMessage || "Processing video..."}</span>
      </div>
      <div className="processing-loader" style={{ marginTop: 8 }}>
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
    </div>
  );
}
