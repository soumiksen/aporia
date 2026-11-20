import { useEffect, useState } from "react";
import type { Consent } from "@/lib/consent";
import { sendMessage } from "@/lib/protocol";

export function OptionsPage() {
  const [consent, setConsent] = useState<Consent | null>(null);

  useEffect(() => {
    void sendMessage("getConsent")
      .then(setConsent)
      .catch(() => undefined);
  }, []);

  const toggle = (enabled: boolean) => {
    setConsent({ decided: true, enabled });
    void sendMessage("setConsent", { enabled }).catch(() => undefined);
  };

  return (
    <main className="mx-auto max-w-xl space-y-4 p-6 font-sans">
      <h1 className="text-xl font-semibold">Aporia options</h1>
      <label className="flex items-start gap-3">
        <input
          type="checkbox"
          className="mt-1"
          checked={consent?.enabled ?? false}
          disabled={consent === null}
          onChange={(e) => toggle(e.target.checked)}
        />
        <span>
          <span className="font-medium">Share anonymous usage events to improve Aporia</span>
          <span className="block text-sm text-gray-600">
            Off by default. Events contain only an event name, a problem id, a hint level or a
            rating. They never contain your code or the problem text. Turning this off discards any
            events that have not been sent yet.
          </span>
        </span>
      </label>
    </main>
  );
}
