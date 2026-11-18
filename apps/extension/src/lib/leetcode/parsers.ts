import { CHECK_URL_REGEX } from "./constants";
import type { VerdictMessage } from "../messages";

type Verdict = Omit<VerdictMessage, "source" | "type">;

function str(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return null;
}

/** First string in an array, or the string itself (LeetCode returns arrays for outputs). */
function strOrFirst(value: unknown): string | null {
  if (Array.isArray(value)) return value.length > 0 ? str(value[0]) : null;
  return str(value);
}

/**
 * Parses a "check" response into a verdict. Returns null when the response is not a finished
 * verdict (still pending, wrong URL, or malformed). Never throws.
 * Assumption (verify on live site): run ids contain "runcode"; the rest are submissions.
 */
export function parseVerdict(url: string, json: unknown): Verdict | null {
  try {
    if (!CHECK_URL_REGEX.test(url)) return null;
    if (typeof json !== "object" || json === null) return null;
    const body = json as Record<string, unknown>;
    if (body.state !== "SUCCESS") return null;
    const phase: Verdict["phase"] = /runcode/i.test(url) ? "run" : "submit";
    return {
      phase,
      status: str(body.status_code),
      statusMessage: str(body.status_msg),
      runtime: str(body.status_runtime),
      lastTestcase: str(body.last_testcase),
      expectedOutput: strOrFirst(body.expected_code_answer ?? body.expected_output),
      actualOutput: strOrFirst(body.code_answer ?? body.code_output),
    };
  } catch {
    return null;
  }
}

/** Minimal structural types for the parts of Monaco we use. */
export interface MonacoModelLike {
  getValue(): string;
  getLanguageId?(): string;
  getModeId?(): string;
  onDidChangeContent?(listener: () => void): { dispose(): void };
}
export interface MonacoEditorLike {
  getModel(): MonacoModelLike | null;
  hasTextFocus?(): boolean;
}
export interface MonacoLike {
  editor: {
    getEditors?(): MonacoEditorLike[];
    getModels?(): MonacoModelLike[];
  };
}

function safeValue(model: MonacoModelLike): string {
  try {
    return model.getValue();
  } catch {
    return "";
  }
}

/**
 * Chooses the student's code model: the focused editor's model, else the first editor with a
 * model, else the model with the most content.
 */
export function pickModel(monaco: MonacoLike | undefined | null): MonacoModelLike | null {
  const api = monaco?.editor;
  if (!api) return null;
  try {
    const editors = api.getEditors?.() ?? [];
    const withModels = editors.filter((e) => e.getModel() !== null);
    const focused = withModels.find((e) => e.hasTextFocus?.() === true);
    const chosen = focused ?? withModels[0];
    if (chosen) return chosen.getModel();
    const models = api.getModels?.() ?? [];
    let best: MonacoModelLike | null = null;
    let bestLen = -1;
    for (const m of models) {
      const len = safeValue(m).length;
      if (len > bestLen) {
        best = m;
        bestLen = len;
      }
    }
    return best;
  } catch {
    return null;
  }
}

export function modelLanguage(model: MonacoModelLike): string {
  try {
    return model.getLanguageId?.() ?? model.getModeId?.() ?? "unknown";
  } catch {
    return "unknown";
  }
}
