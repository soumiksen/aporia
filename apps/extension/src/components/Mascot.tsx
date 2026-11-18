export type MascotMood = "idle" | "thinking" | "happy" | "error";

export interface MascotProps {
  mood?: MascotMood;
  size?: number;
  className?: string;
}

// Rive is not used: no `.riv` asset exists in src/assets/ (and none may be invented).
// This inline SVG rabbit is the fallback and keeps the same props a Rive version would take.
export function Mascot({ mood = "idle", size = 48, className }: MascotProps) {
  const eyeY = mood === "happy" ? 33 : 34;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label={`Aporia mascot, ${mood}`}
      className={className}
      data-mood={mood}
    >
      <ellipse cx="22" cy="14" rx="6" ry="14" fill="#f4f1ec" stroke="#4a4458" strokeWidth="2" />
      <ellipse cx="42" cy="14" rx="6" ry="14" fill="#f4f1ec" stroke="#4a4458" strokeWidth="2" />
      <ellipse cx="22" cy="15" rx="2.5" ry="9" fill="#f3b8c4" />
      <ellipse cx="42" cy="15" rx="2.5" ry="9" fill="#f3b8c4" />
      <circle cx="32" cy="40" r="20" fill="#f4f1ec" stroke="#4a4458" strokeWidth="2" />
      {mood === "happy" ? (
        <>
          <path d="M23 34 q3 -4 6 0" stroke="#4a4458" strokeWidth="2" fill="none" />
          <path d="M35 34 q3 -4 6 0" stroke="#4a4458" strokeWidth="2" fill="none" />
        </>
      ) : (
        <>
          <circle cx="26" cy={eyeY} r="2.5" fill="#4a4458" />
          <circle cx="38" cy={eyeY} r="2.5" fill="#4a4458" />
        </>
      )}
      <ellipse cx="32" cy="42" rx="2.5" ry="2" fill="#f3b8c4" />
      {mood === "error" ? (
        <path d="M27 50 q5 -4 10 0" stroke="#4a4458" strokeWidth="2" fill="none" />
      ) : mood === "thinking" ? (
        <circle cx="32" cy="50" r="2" fill="none" stroke="#4a4458" strokeWidth="2" />
      ) : (
        <path d="M27 48 q5 4 10 0" stroke="#4a4458" strokeWidth="2" fill="none" />
      )}
    </svg>
  );
}
