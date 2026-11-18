import type { HintStatus } from "@/store/hint-store";

export interface HintViewProps {
  status: HintStatus;
  text: string;
}

export function HintView({ status, text }: HintViewProps) {
  if (status === "idle") return null;
  return (
    <div className="text-sm leading-relaxed" data-testid="hint-view">
      <div aria-live="polite" aria-atomic="false" className="whitespace-pre-wrap">
        {text}
      </div>
      {status === "streaming" && text === "" && (
        <p className="text-muted-foreground" role="status">
          Thinking…
        </p>
      )}
      {status === "streaming" && text !== "" && (
        <span aria-hidden="true" className="inline-block animate-pulse">
          ▍
        </span>
      )}
    </div>
  );
}
