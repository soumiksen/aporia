import { Button } from "@/components/ui/button";
import { MAX_LEVEL, type HintStatus } from "@/store/hint-store";

export interface HintActionsProps {
  status: HintStatus;
  level: number;
  rated: boolean;
  onBigger: () => void;
  onNotHelpful: () => void;
}

export function HintActions({ status, level, rated, onBigger, onNotHelpful }: HintActionsProps) {
  if (status !== "done") return null;
  const atTop = level >= MAX_LEVEL;
  return (
    <div className="flex items-center justify-between gap-2">
      <Button size="sm" variant="outline" onClick={onBigger} disabled={atTop}>
        Need a bigger hint
      </Button>
      {rated ? (
        <span className="text-xs text-muted-foreground" role="status">
          Thanks for the feedback
        </span>
      ) : (
        <button
          type="button"
          onClick={onNotHelpful}
          className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          Not helpful
        </button>
      )}
    </div>
  );
}
