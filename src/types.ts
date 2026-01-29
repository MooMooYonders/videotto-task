export type Clip = {
  start: number;
  end: number;
  reason: string;
  start_frame: number;
  end_frame: number;
  thumbnail?: string | null;  // The first frame as base64 JPEG for card preview in the UI
};
