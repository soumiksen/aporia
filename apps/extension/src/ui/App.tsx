import { useState } from "react";
import { Panel } from "@/components/Panel";

export function App() {
  const [open, setOpen] = useState(false);
  return (
    <Panel open={open} onOpenChange={setOpen}>
      <p className="text-sm text-muted-foreground">Open a problem to get started.</p>
    </Panel>
  );
}
