import { describe, expect, it } from "vitest";

import { buildPath, buildSentimentPath } from "@/lib/trend-path";

const GEOM = { W: 720, PAD: 8 };

describe("buildPath", () => {
  it("0 點 → 空字串（不崩、不存取 pts[-1]）", () => {
    expect(buildPath([], 120, 1, GEOM)).toEqual({ area: "", line: "" });
  });

  it("1 點 → 單點線（dx=0，line 以 M 起頭），area 收合不崩", () => {
    const { line, area } = buildPath([5], 120, 5, GEOM);
    expect(line.startsWith("M")).toBe(true);
    // 單點 line 只有一個 M 指令、無 L。
    expect(line).not.toContain("L");
    // area 仍是封閉路徑（含 Z）。
    expect(area.endsWith("Z")).toBe(true);
  });

  it("max=0（值全為 0）→ 不除以 0，所有點貼底線", () => {
    const { line } = buildPath([0, 0, 0], 120, 0, GEOM);
    const bottomY = (120 - GEOM.PAD).toFixed(1);
    // 每個座標的 y 都應等於底線。
    const ys = line.match(/,(\d+\.\d)/g)?.map((s) => s.slice(1));
    expect(ys).toEqual([bottomY, bottomY, bottomY]);
  });

  it("多點：line 含 M 與 L、area 封閉", () => {
    const { line, area } = buildPath([1, 2, 3], 120, 3, GEOM);
    expect(line.startsWith("M")).toBe(true);
    expect(line).toContain("L");
    expect(area.endsWith("Z")).toBe(true);
  });
});

describe("buildSentimentPath", () => {
  it("全 null（無情緒資料）→ 空字串", () => {
    expect(buildSentimentPath([null, null, null], 80, GEOM)).toBe("");
  });

  it("空陣列 → 空字串", () => {
    expect(buildSentimentPath([], 80, GEOM)).toBe("");
  });

  it("只連有資料的點：第一個非 null 以 M 起頭", () => {
    const path = buildSentimentPath([null, 50, null, -20], 80, GEOM);
    expect(path.startsWith("M")).toBe(true);
    // 兩個有效點 → 一個 M + 一個 L。
    expect((path.match(/M/g) ?? []).length).toBe(1);
    expect((path.match(/L/g) ?? []).length).toBe(1);
  });

  it("0（中性）也是有效資料點，不被當成缺值", () => {
    const path = buildSentimentPath([0], 80, GEOM);
    expect(path.startsWith("M")).toBe(true);
  });
});
