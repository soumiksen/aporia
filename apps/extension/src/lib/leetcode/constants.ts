// All LeetCode-specific selectors, URLs and GraphQL queries live here (see CLAUDE.md).
// Every value below is an assumption about leetcode.com. Each is marked "verify on live site".

/** Match pattern for problem pages. Verify on live site. */
export const PROBLEM_MATCH_PATTERN = "https://leetcode.com/problems/*";

/** Extracts the problem slug from a pathname. Verify on live site. */
export const SLUG_FROM_PATH_REGEX = /^\/problems\/([a-z0-9-]+)(?:\/|$)/i;

/** GraphQL endpoint used with the user's own session. Verify on live site. */
export const GRAPHQL_ENDPOINT = "https://leetcode.com/graphql";

/** GraphQL query for problem metadata. Verify on live site. */
export const QUESTION_QUERY = `query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    title
    difficulty
    content
    topicTags { name slug }
    exampleTestcases
    metaData
  }
}`;

/** URL patterns for run / submit / poll-check requests. Verify on live site. */
export const RUN_URL_REGEX = /\/problems\/[^/]+\/interpret_solution\/?(?:\?|$)/;
export const SUBMIT_URL_REGEX = /\/problems\/[^/]+\/submit\/?(?:\?|$)/;
export const CHECK_URL_REGEX = /\/submissions\/detail\/[^/]+\/check\/?(?:\?|$)/;

/** Fallback description container selector, used only if GraphQL fails. Verify on live site. */
export const DESCRIPTION_SELECTOR = '[data-track-load="description_content"]';

/** Bridge handshake tag shared by the MAIN-world and isolated content scripts. */
export const BRIDGE_SOURCE = "aporia-bridge";

/** Monaco polling cadence and budget. */
export const MONACO_POLL_INTERVAL_MS = 250;
export const MONACO_POLL_TIMEOUT_MS = 20_000;
export const CODE_DEBOUNCE_MS = 300;
