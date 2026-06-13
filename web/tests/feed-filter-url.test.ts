import { describe, expect, it } from "vitest";

import { buildFilterParams } from "@/lib/feed-filter-url";

describe("buildFilterParams", () => {
  it("空 query 設值 → 寫入該參數", () => {
    expect(buildFilterParams("", "model", "claude")).toBe("model=claude");
  });

  it("設空字串 → 移除該參數（回到「全部」）", () => {
    expect(buildFilterParams("model=claude", "model", "")).toBe("");
  });

  it("不影響其他既有參數", () => {
    const out = buildFilterParams("sentiment=positive&days=7", "model", "gpt");
    const p = new URLSearchParams(out);
    expect(p.get("sentiment")).toBe("positive");
    expect(p.get("days")).toBe("7");
    expect(p.get("model")).toBe("gpt");
  });

  it("覆蓋既有同名參數（非附加）", () => {
    const out = buildFilterParams("model=gpt", "model", "gemini");
    const p = new URLSearchParams(out);
    expect(p.getAll("model")).toEqual(["gemini"]);
  });

  it("移除一個參數時其他參數保留", () => {
    const out = buildFilterParams("model=gpt&source=ptt", "model", "");
    const p = new URLSearchParams(out);
    expect(p.has("model")).toBe(false);
    expect(p.get("source")).toBe("ptt");
  });

  it("接受 URLSearchParams 物件作為輸入", () => {
    const cur = new URLSearchParams("days=30");
    const out = buildFilterParams(cur, "source", "threads");
    const p = new URLSearchParams(out);
    expect(p.get("days")).toBe("30");
    expect(p.get("source")).toBe("threads");
  });
});
