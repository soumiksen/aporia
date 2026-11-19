import { z } from "zod";
import { BRIDGE_SOURCE } from "./leetcode/constants";

export const codeMessageSchema = z.object({
  source: z.literal(BRIDGE_SOURCE),
  type: z.literal("code"),
  code: z.string(),
  language: z.string(),
});

export const verdictMessageSchema = z.object({
  source: z.literal(BRIDGE_SOURCE),
  type: z.literal("verdict"),
  phase: z.enum(["run", "submit"]),
  status: z.string().nullable(),
  statusMessage: z.string().nullable(),
  runtime: z.string().nullable(),
  lastTestcase: z.string().nullable(),
  expectedOutput: z.string().nullable(),
  actualOutput: z.string().nullable(),
});

export const bridgeMessageSchema = z.discriminatedUnion("type", [
  codeMessageSchema,
  verdictMessageSchema,
]);

export type CodeMessage = z.infer<typeof codeMessageSchema>;
export type VerdictMessage = z.infer<typeof verdictMessageSchema>;
export type BridgeMessage = z.infer<typeof bridgeMessageSchema>;

/** Returns a validated bridge message, or null for anything else (never throws). */
export function parseBridgeMessage(data: unknown): BridgeMessage | null {
  const result = bridgeMessageSchema.safeParse(data);
  return result.success ? result.data : null;
}

export const hintRequestSchema = z.object({
  problem: z.object({
    slug: z.string(),
    title: z.string(),
    difficulty: z.string(),
    tags: z.array(z.string()),
    content_text: z.string(),
    meta: z.record(z.string(), z.unknown()).nullable(),
  }),
  code: z.string().max(50_000),
  language: z.string(),
  level: z.number().int().min(1).max(4).default(1),
  student_message: z.string().max(300).nullable().optional(),
  failed_attempts: z.number().int().min(0).max(1000).default(0),
  last_verdict: z.string().nullable().optional(),
});

export type HintRequest = z.input<typeof hintRequestSchema>;

/** Events relayed from the service worker to the content script. */
export const hintEventSchema = z.discriminatedUnion("event", [
  z.object({ event: z.literal("token"), text: z.string() }),
  z.object({
    event: z.literal("done"),
    hint_id: z.string(),
    level: z.number(),
    sources: z.array(z.unknown()),
    // false: the API cannot run code for this problem, so hints are prompt-only
    supported: z.boolean().default(true),
  }),
  z.object({ event: z.literal("error"), code: z.string(), message: z.string() }),
]);

export type HintEvent = z.infer<typeof hintEventSchema>;
