import { describe, expect, it } from "vitest";
import { modelLanguage, parseVerdict, pickModel, type MonacoLike } from "./parsers";

const model = (value: string, lang = "python") => ({
  getValue: () => value,
  getLanguageId: () => lang,
});

describe("parseVerdict", () => {
  const checkUrl = "https://leetcode.com/submissions/detail/123/check/";
  it("parses a finished submit verdict", () => {
    const v = parseVerdict(checkUrl, {
      state: "SUCCESS",
      status_code: 11,
      status_msg: "Wrong Answer",
      status_runtime: "N/A",
      last_testcase: "[1,2]\n3",
      expected_output: "[0,1]",
      code_output: "[]",
    });
    expect(v).toEqual({
      phase: "submit",
      status: "11",
      statusMessage: "Wrong Answer",
      runtime: "N/A",
      lastTestcase: "[1,2]\n3",
      expectedOutput: "[0,1]",
      actualOutput: "[]",
    });
  });
  it("detects run phase and array outputs", () => {
    const v = parseVerdict("https://leetcode.com/submissions/detail/runcode_1_2/check/", {
      state: "SUCCESS",
      status_msg: "Accepted",
      code_answer: ["[0,1]"],
      expected_code_answer: ["[0,1]"],
    });
    expect(v?.phase).toBe("run");
    expect(v?.actualOutput).toBe("[0,1]");
  });
  it("ignores pending, unrelated URLs and junk", () => {
    expect(parseVerdict(checkUrl, { state: "PENDING" })).toBeNull();
    expect(parseVerdict("https://leetcode.com/graphql", { state: "SUCCESS" })).toBeNull();
    expect(parseVerdict(checkUrl, null)).toBeNull();
    expect(parseVerdict(checkUrl, "nope")).toBeNull();
  });
});

describe("pickModel", () => {
  it("prefers the focused editor", () => {
    const a = model("a");
    const b = model("b");
    const monaco: MonacoLike = {
      editor: {
        getEditors: () => [
          { getModel: () => a, hasTextFocus: () => false },
          { getModel: () => b, hasTextFocus: () => true },
        ],
      },
    };
    expect(pickModel(monaco)).toBe(b);
  });
  it("falls back to the first editor", () => {
    const a = model("a");
    expect(pickModel({ editor: { getEditors: () => [{ getModel: () => a }] } })).toBe(a);
  });
  it("falls back to the longest model", () => {
    const small = model("x");
    const big = model("class Solution: pass");
    expect(pickModel({ editor: { getModels: () => [small, big] } })).toBe(big);
  });
  it("returns null without monaco", () => {
    expect(pickModel(undefined)).toBeNull();
    expect(pickModel({ editor: {} })).toBeNull();
  });
  it("reads the language id", () => {
    expect(modelLanguage(model("x", "cpp"))).toBe("cpp");
  });
});
