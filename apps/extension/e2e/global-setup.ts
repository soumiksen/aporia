import { execSync } from "node:child_process";

// Builds the extension in development mode pointing at the mock API (host permission included).
export default function globalSetup(): void {
  execSync("pnpm build:dev", {
    stdio: "inherit",
    env: { ...process.env, VITE_API_URL: "http://127.0.0.1:8765" },
  });
}
