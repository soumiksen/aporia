const LABELS = ["Nudge", "Hint", "Explanation", "Worked example"] as const;

export interface LevelBadgeProps {
  level: number;
}

export function LevelBadge({ level }: LevelBadgeProps) {
  const clamped = Math.max(1, Math.min(4, level));
  const label = LABELS[clamped - 1];
  return (
    <span
      data-testid="level-badge"
      aria-label={`Hint level ${clamped} of 4: ${label}`}
      className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground"
    >
      <span aria-hidden="true">L{clamped}</span>
      <span aria-hidden="true" className="text-muted-foreground">
        {label}
      </span>
    </span>
  );
}
