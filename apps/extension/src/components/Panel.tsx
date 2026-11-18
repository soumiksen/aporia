import type { ReactNode } from "react";
import { Mascot, type MascotMood } from "./Mascot";

export interface PanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mood?: MascotMood;
  children?: ReactNode;
}

/** Floating, collapsible panel anchored bottom-right. The mascot button toggles it. */
export function Panel({ open, onOpenChange, mood = "idle", children }: PanelProps) {
  return (
    <div className="aporia-root fixed right-4 bottom-4 z-[2147483000] flex flex-col items-end gap-2">
      {open && (
        <section
          aria-label="Aporia hint panel"
          className="w-80 max-w-[90vw] rounded-xl border border-border bg-background p-4 shadow-lg"
        >
          <header className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Aporia</h2>
            <button
              type="button"
              aria-label="Close panel"
              className="rounded px-1 text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => onOpenChange(false)}
            >
              ×
            </button>
          </header>
          {children}
        </section>
      )}
      <button
        type="button"
        aria-label={open ? "Collapse Aporia" : "Ask Aporia for a hint"}
        aria-expanded={open}
        className="rounded-full bg-background shadow-lg ring-1 ring-border focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => onOpenChange(!open)}
      >
        <Mascot mood={mood} size={56} />
      </button>
    </div>
  );
}
