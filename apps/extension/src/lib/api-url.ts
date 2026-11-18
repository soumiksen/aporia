/** Build-time API base URL (`VITE_API_URL`), default for local development. */
export const API_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
