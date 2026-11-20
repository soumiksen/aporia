import { Button } from "@/components/ui/button";
import { MAX_LEVEL, type HintStatus } from "@/store/hint-store";

export interface HintActionsProps {
  status: HintStatus;
  level: number;
  rated: boolean;
  onBigger: () => void;
  /** 5 for thumbs up, 1 for thumbs down. */
  onRate: (rating: number) => void;
}

export function HintActions({ status, level, rated, onBigger, onRate }: HintActionsProps) {
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
        <span className="flex gap-1">
          <button
            type="button"
            aria-label="Helpful"
            onClick={() => onRate(5)}
            className="rounded px-1 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span aria-hidden="true">👍</span>
          </button>
          <button
            type="button"
            aria-label="Not helpful"
            onClick={() => onRate(1)}
            className="rounded px-1 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span aria-hidden="true">👎</span>
          </button>
        </span>
      )}
    </div>
  );
}
