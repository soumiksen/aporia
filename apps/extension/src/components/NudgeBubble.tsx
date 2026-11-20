import { Button } from "@/components/ui/button";

export interface NudgeBubbleProps {
  onYes: () => void;
  onNotNow: () => void;
  onNever: () => void;
}

/** The proactive offer. It never opens a hint by itself: "Yes" is an explicit choice. */
export function NudgeBubble({ onYes, onNotNow, onNever }: NudgeBubbleProps) {
  return (
    <div
      role="dialog"
      aria-label="Aporia nudge"
      data-testid="nudge-bubble"
      className="w-64 max-w-[90vw] rounded-xl border border-border bg-background p-3 text-sm shadow-lg"
    >
      <p className="mb-2 font-medium">Stuck? Want a nudge?</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={onYes}>
          Yes
        </Button>
        <Button size="sm" variant="outline" onClick={onNotNow}>
          Not now
        </Button>
        <Button size="sm" variant="ghost" onClick={onNever}>
          Never on this problem
        </Button>
      </div>
    </div>
  );
}
