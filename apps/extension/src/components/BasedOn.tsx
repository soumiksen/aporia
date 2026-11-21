import type { Source } from "../lib/messages";

const label = (s: Source) => `${s.slug.replace(/-/g, " ")} · ${s.heading}`;

/** Small "Based on" chips for the study notes behind a hint. Renders nothing without sources. */
export function BasedOn({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1" aria-label="Based on">
      <span className="text-xs text-muted-foreground">Based on</span>
      {sources.map((s) => (
        <span
          key={`${s.slug}#${s.heading}`}
          className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
        >
          {label(s)}
        </span>
      ))}
    </div>
  );
}
