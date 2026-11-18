import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearProblemCache,
  fetchProblem,
  htmlToText,
  problemFromGraphql,
  problemFromPage,
  slugFromPath,
} from "./metadata";

describe("slugFromPath", () => {
  it("extracts slugs", () => {
    expect(slugFromPath("/problems/two-sum/")).toBe("two-sum");
    expect(slugFromPath("/problems/two-sum/description/")).toBe("two-sum");
    expect(slugFromPath("/problems/Two-Sum")).toBe("two-sum");
  });
  it("rejects non-problem paths", () => {
    expect(slugFromPath("/problemset/")).toBeNull();
    expect(slugFromPath("/")).toBeNull();
    expect(slugFromPath("/problems/")).toBeNull();
  });
});

describe("htmlToText", () => {
  it("strips tags and collapses whitespace", () => {
    expect(htmlToText("<p>Given  an <code>array</code>.</p>\n\n<ul><li>one</li></ul>")).toBe(
      "Given an array. one",
    );
  });
  it("drops scripts and styles", () => {
    expect(htmlToText("<p>hi</p><script>alert(1)</script><style>p{}</style>")).toBe("hi");
  });
  it("handles empty input", () => {
    expect(htmlToText("")).toBe("");
  });
});

const body = {
  data: {
    question: {
      title: "Synthetic Sum",
      difficulty: "Easy",
      content: "<p>Add two numbers.</p>",
      topicTags: [{ name: "Array", slug: "array" }],
      metaData: '{"name":"add","params":[]}',
    },
  },
};

describe("problemFromGraphql", () => {
  it("maps a valid response", () => {
    expect(problemFromGraphql("s", body)).toEqual({
      slug: "s",
      title: "Synthetic Sum",
      difficulty: "Easy",
      tags: ["Array"],
      content_text: "Add two numbers.",
      meta: { name: "add", params: [] },
    });
  });
  it("tolerates bad metaData and rejects bad shapes", () => {
    const bad = structuredClone(body);
    bad.data.question.metaData = "{oops";
    expect(problemFromGraphql("s", bad)?.meta).toBeNull();
    expect(problemFromGraphql("s", { data: null })).toBeNull();
  });
});

describe("fetchProblem", () => {
  beforeEach(() => clearProblemCache());
  it("caches per slug", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify(body)));
    await fetchProblem("s", document, f as unknown as typeof fetch);
    const second = await fetchProblem("s", document, f as unknown as typeof fetch);
    expect(f).toHaveBeenCalledTimes(1);
    expect(second.fromFallback).toBe(false);
  });
  it("falls back to the page with meta null on failure", async () => {
    document.title = "Fake Problem - LeetCode";
    document.body.innerHTML = '<div data-track-load="description_content">Desc  here</div>';
    const f = vi.fn(async () => new Response("no", { status: 500 }));
    const r = await fetchProblem("fake", document, f as unknown as typeof fetch);
    expect(r.fromFallback).toBe(true);
    expect(r.problem).toMatchObject({
      title: "Fake Problem",
      content_text: "Desc here",
      meta: null,
    });
  });
  it("problemFromPage uses slug when title is empty", () => {
    document.title = "";
    expect(problemFromPage("abc", document).title).toBe("abc");
  });
});
