import { Button } from "@/components/ui/button";

export interface ConsentCardProps {
  onChoose: (enabled: boolean) => void;
}

/** First-run card. Telemetry stays off until the student presses Allow. */
export function ConsentCard({ onChoose }: ConsentCardProps) {
  return (
    <section
      aria-label="Usage data"
      data-testid="consent-card"
      className="mb-2 space-y-2 rounded-lg bg-muted p-3 text-sm"
    >
      <p className="font-medium">Share anonymous usage events to improve Aporia?</p>
      <p className="text-xs text-muted-foreground">
        Only event names, problem ids and hint levels. Never your code or the problem text. You can
        change this any time in the extension options.
      </p>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onChoose(true)}>
          Allow
        </Button>
        <Button size="sm" variant="outline" onClick={() => onChoose(false)}>
          No thanks
        </Button>
      </div>
    </section>
  );
}
