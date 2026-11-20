import { useState } from "react";
import { ErrorView } from "@/components/ErrorView";
import { HintActions } from "@/components/HintActions";
import { HintView } from "@/components/HintView";
import { LevelBadge } from "@/components/LevelBadge";
import type { MascotMood } from "@/components/Mascot";
import { Panel } from "@/components/Panel";
import { StudentMessageBox } from "@/components/StudentMessageBox";
import { UnsupportedBanner } from "@/components/UnsupportedBanner";
import { NudgeBubble } from "@/components/NudgeBubble";
import { StuckLabelPrompt } from "@/components/StuckLabelPrompt";
import { MAX_LEVEL, useHintStore } from "@/store/hint-store";
import { useHint } from "./useHint";
import { useStuckNudge } from "./useStuckNudge";

export function App() {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const { ask, cancel, rate, slug, codeKnown } = useHint();
  const status = useHintStore((s) => s.status);
  const text = useHintStore((s) => s.text);
  const level = useHintStore((s) => s.level);
  const supported = useHintStore((s) => s.supported);
  const rated = useHintStore((s) => s.rated);
  const errorMessage = useHintStore((s) => s.errorMessage);

  const nudge = useStuckNudge({
    slug,
    panelOpen: open,
    onAccept: () => {
      setOpen(true);
      ask({ level: 1 }); // "Yes" is the only thing that ever opens a hint
    },
  });

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) {
      if (status === "streaming") cancel();
      return;
    }
    if (slug && (status === "idle" || status === "error")) ask({ level: 1 });
  };

  const onBigger = () => {
    ask({ level: Math.min(MAX_LEVEL, level + 1), studentMessage: message });
    setMessage("");
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
    <Panel
      open={open}
      onOpenChange={onOpenChange}
      mood={nudge.bubbleVisible && !open ? "attentive" : mood}
      bubble={
        nudge.bubbleVisible ? (
          <NudgeBubble onYes={nudge.yes} onNotNow={nudge.notNow} onNever={nudge.never} />
        ) : nudge.labelVisible ? (
          <StuckLabelPrompt onAnswer={nudge.answerLabel} />
        ) : null
      }
    >
      {!slug ? (
        <p className="text-sm text-muted-foreground">Open a problem to get started.</p>
      ) : (
        <div className="space-y-2">
          {status !== "idle" && status !== "error" && <LevelBadge level={level} />}
          {!codeKnown && (
            <p className="text-xs text-muted-foreground" role="note">
              Aporia hasn&apos;t captured your code yet, so this hint uses only the problem.
            </p>
          )}
          {status === "done" && !supported && <UnsupportedBanner />}
          {status === "error" ? (
            <ErrorView
              message={errorMessage ?? "Something went wrong."}
              onRetry={() => ask({ level, studentMessage: message })}
            />
          ) : (
            <HintView status={status} text={text} />
          )}
          <HintActions
            status={status}
            level={level}
            rated={rated}
            onBigger={onBigger}
            onRate={rate}
          />
          <StudentMessageBox value={message} onChange={setMessage} />
        </div>
      )}
    </Panel>
  );
}
