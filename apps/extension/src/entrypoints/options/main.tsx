import React from "react";
import ReactDOM from "react-dom/client";
import { initSentry } from "@/lib/sentry";
import { OptionsPage } from "./OptionsPage";
import "./style.css";

void initSentry(import.meta.env.VITE_SENTRY_DSN);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <OptionsPage />
  </React.StrictMode>,
);
