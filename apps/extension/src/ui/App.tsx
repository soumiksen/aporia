import { useState } from "react";
import { ErrorView } from "@/components/ErrorView";
import { HintView } from "@/components/HintView";
import type { MascotMood } from "@/components/Mascot";
import { Panel } from "@/components/Panel";
import { useHintStore } from "@/store/hint-store";
import { useHint } from "./useHint";

export function App() {
  const [open, setOpen] = useState(false);
  const { ask, cancel, slug, codeKnown } = useHint();
  const status = useHintStore((s) => s.status);
  const text = useHintStore((s) => s.text);
  const errorMessage = useHintStore((s) => s.errorMessage);

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) {
      if (status === "streaming") cancel();
      return;
    }
    if (slug && (status === "idle" || status === "error")) ask();
  };

  const mood: MascotMood =
    status === "streaming"
      ? "thinking"
      : status === "done"
        ? "happy"
        : status === "error"
          ? "error"
          : "idle";

  return (
    <Panel open={open} onOpenChange={onOpenChange} mood={mood}>
      {!slug ? (
        <p className="text-sm text-muted-foreground">Open a problem to get started.</p>
      ) : (
        <div className="space-y-2">
          {!codeKnown && (
            <p className="text-xs text-muted-foreground" role="note">
              Aporia hasn&apos;t captured your code yet, so this hint uses only the problem.
            </p>
          )}
          {status === "error" ? (
            <ErrorView message={errorMessage ?? "Something went wrong."} onRetry={ask} />
          ) : (
            <HintView status={status} text={text} />
          )}
        </div>
      )}
    </Panel>
  );
}
