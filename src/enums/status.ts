export const ProcessingStatus = {
  Idle: "idle",
  Processing: "processing",
  Completed: "completed",
  Failed: "failed",
} as const;

export type ProcessingStatusValue = (typeof ProcessingStatus)[keyof typeof ProcessingStatus];

