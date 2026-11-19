import { MAX_MESSAGE_CHARS } from "@/store/hint-store";

export interface StudentMessageBoxProps {
  value: string;
  onChange: (value: string) => void;
}

export function StudentMessageBox({ value, onChange }: StudentMessageBoxProps) {
  return (
    <div className="space-y-1">
      <label htmlFor="aporia-student-message" className="text-xs text-muted-foreground">
        Tell Aporia what you are stuck on (optional)
      </label>
      <textarea
        id="aporia-student-message"
        rows={2}
        maxLength={MAX_MESSAGE_CHARS}
        value={value}
        onChange={(e) => onChange(e.target.value.slice(0, MAX_MESSAGE_CHARS))}
        className="w-full resize-none rounded-md border border-input bg-background px-2 py-1 text-sm focus-visible:ring-2 focus-visible:ring-ring"
      />
      <p className="text-right text-xs text-muted-foreground" aria-live="off">
        {value.length}/{MAX_MESSAGE_CHARS}
      </p>
    </div>
  );
}
