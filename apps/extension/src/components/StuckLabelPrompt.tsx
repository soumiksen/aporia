import { Button } from "@/components/ui/button";

export interface StuckLabelPromptProps {
  onAnswer: (wasStuck: boolean) => void;
}

/** Shown occasionally after a dismissal to label data for a future learned detector. */
export function StuckLabelPrompt({ onAnswer }: StuckLabelPromptProps) {
  return (
    <div
      role="dialog"
      aria-label="Quick question"
      data-testid="stuck-label"
      className="w-64 max-w-[90vw] rounded-xl border border-border bg-background p-3 text-sm shadow-lg"
    >
      <p className="mb-2 font-medium">Were you actually stuck?</p>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onAnswer(true)}>
          Yes
        </Button>
        <Button size="sm" variant="outline" onClick={() => onAnswer(false)}>
          No
        </Button>
      </div>
    </div>
  );
}
