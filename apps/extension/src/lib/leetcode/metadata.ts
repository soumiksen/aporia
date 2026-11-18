import { z } from "zod";
import {
  DESCRIPTION_SELECTOR,
  GRAPHQL_ENDPOINT,
  QUESTION_QUERY,
  SLUG_FROM_PATH_REGEX,
} from "./constants";
import type { HintRequest } from "../messages";

export type ProblemInfo = HintRequest["problem"];

export function slugFromPath(pathname: string): string | null {
  const match = SLUG_FROM_PATH_REGEX.exec(pathname);
  return match?.[1] ? match[1].toLowerCase() : null;
}

/** Strips tags with DOMParser and collapses whitespace. Never executes scripts. */
export function htmlToText(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("script,style").forEach((el) => el.remove());
  return (doc.body.textContent ?? "").replace(/\s+/g, " ").trim();
}

const questionResponseSchema = z.object({
  data: z.object({
    question: z.object({
      title: z.string(),
      difficulty: z.string(),
      content: z.string().nullable(),
      topicTags: z.array(z.object({ name: z.string(), slug: z.string() })),
      metaData: z.string().nullable().optional(),
    }),
  }),
});

function parseMetaData(raw: string | null | undefined): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** Converts a GraphQL response body into ProblemInfo, or null if it has an unexpected shape. */
export function problemFromGraphql(slug: string, body: unknown): ProblemInfo | null {
  const parsed = questionResponseSchema.safeParse(body);
  if (!parsed.success) return null;
  const q = parsed.data.data.question;
  return {
    slug,
    title: q.title,
    difficulty: q.difficulty,
    tags: q.topicTags.map((t) => t.name),
    content_text: htmlToText(q.content ?? ""),
    meta: parseMetaData(q.metaData),
  };
}

/** Fallback from the visible page when GraphQL fails. `meta` is null. */
export function problemFromPage(slug: string, doc: Document): ProblemInfo {
  const description = doc.querySelector(DESCRIPTION_SELECTOR)?.textContent ?? "";
  return {
    slug,
    title: doc.title.replace(/\s*-\s*LeetCode.*$/i, "").trim() || slug,
    difficulty: "unknown",
    tags: [],
    content_text: description.replace(/\s+/g, " ").trim(),
    meta: null,
  };
}

const cache = new Map<string, ProblemInfo>();

export function clearProblemCache(): void {
  cache.clear();
}

/** Fetches problem metadata with the user's session; cached in memory per slug. */
export async function fetchProblem(
  slug: string,
  doc: Document = document,
  fetchFn: typeof fetch = fetch,
): Promise<{ problem: ProblemInfo; fromFallback: boolean }> {
  const cached = cache.get(slug);
  if (cached)
    return { problem: cached, fromFallback: cached.meta === null && cached.tags.length === 0 };
  try {
    const res = await fetchFn(GRAPHQL_ENDPOINT, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: QUESTION_QUERY, variables: { titleSlug: slug } }),
    });
    if (!res.ok) throw new Error(`graphql ${res.status}`);
    const problem = problemFromGraphql(slug, await res.json());
    if (!problem) throw new Error("unexpected graphql shape");
    cache.set(slug, problem);
    return { problem, fromFallback: false };
  } catch {
    return { problem: problemFromPage(slug, doc), fromFallback: true };
  }
}
