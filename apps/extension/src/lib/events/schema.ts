import { z } from "zod";
import { EVENT_TYPES, type AporiaEvent } from "./types";

/**
 * Strict allowlist, mirrored by the API. `.strict()` rejects any extra field, so code or problem
 * text can never ride along on an event object.
 */
export const eventSchema = z
  .object({
    type: z.enum(EVENT_TYPES),
    ts: z.number().int().positive(),
    slug: z
      .string()
      .regex(/^[a-z0-9][a-z0-9-]{0,99}$/)
      .optional(),
    level: z.number().int().min(1).max(4).optional(),
    reason: z
      .enum(["consecutive_failures", "repeated_failure", "inactivity", "low_progress"])
      .optional(),
    rating: z.number().int().min(1).max(5).optional(),
    was_stuck: z.boolean().optional(),
  })
  .strict();

/** Returns a clean event, or null if the input has any unknown field or invalid value. */
export function parseEvent(input: unknown): AporiaEvent | null {
  const result = eventSchema.safeParse(input);
  return result.success ? (result.data as AporiaEvent) : null;
}
