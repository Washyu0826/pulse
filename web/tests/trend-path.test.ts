import { describe, expect, it } from "vitest";

import {
  buildPath,
  buildSentimentPath,
  buildSparkline,
  buildStackedAreas,
} from "@/lib/trend-path";

const GEOM = { W: 720, PAD: 8 };

describe("buildPath", () => {
  it("0 點 → 空字串（不崩、不存取 pts[-1]）", () => {
    expect(buildPath([], 120, 1, GEOM)).toEqual({ area: "", line: "" });
  });

  it("1 點（days=1）→ 橫跨整寬等高帶（非收斂同點），area 有正寬度且封閉", () => {
    const { line, area } = buildPath([5], 120, 5, GEOM);
    expect(line.startsWith("M")).toBe(true);
    // 單點應畫成一條橫線（M…L…），而非只有 M（後者寬度 0 圖空白）。
    expect(line).toContain("L");
    // 線的左右 x 應分別貼到內距與右緣 → 有正寬度（不收斂同點）。
    const xs = (line.match(/[ML](\d+\.\d)/g) ?? []).map((s) => Number(s.slice(1)));
    expect(xs).toHaveLength(2);
    expect(xs[1] - xs[0]).toBeGreaterThan(0);
    expect(xs[0]).toBeCloseTo(GEOM.PAD, 1);
    expect(xs[1]).toBeCloseTo(GEOM.W - GEOM.PAD, 1);
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

  it("僅單一有效點（days=1）→ 橫跨整寬等高線（非只有 M 的不可見點）", () => {
    const path = buildSentimentPath([42], 80, GEOM);
    expect(path.startsWith("M")).toBe(true);
    // 單點需畫成可見橫線（M…L…），而非只有一個 M。
    expect(path).toContain("L");
    const xs = (path.match(/[ML](\d+\.\d)/g) ?? []).map((s) => Number(s.slice(1)));
    expect(xs).toHaveLength(2);
    expect(xs[0]).toBeCloseTo(GEOM.PAD, 1);
    expect(xs[1]).toBeCloseTo(GEOM.W - GEOM.PAD, 1);
  });

  it("散落點中僅一個非 null（其餘 null）→ 仍畫成橫跨整寬等高線", () => {
    const path = buildSentimentPath([null, 30, null], 80, GEOM);
    expect(path).toContain("L");
    const xs = (path.match(/[ML](\d+\.\d)/g) ?? []).map((s) => Number(s.slice(1)));
    expect(xs[0]).toBeCloseTo(GEOM.PAD, 1);
    expect(xs[1]).toBeCloseTo(GEOM.W - GEOM.PAD, 1);
  });
});

describe("buildSparkline", () => {
  const SPARK = { width: 240, height: 36, pad: 3 };

  it("空陣列 → 無折線、無端點", () => {
    expect(buildSparkline([], SPARK)).toEqual({ line: "", points: [] });
  });

  it("單點 → 置中、無折線（只有一個端點圓點）", () => {
    const { line, points } = buildSparkline([5], SPARK);
    expect(line).toBe(""); // n<2 無兩點可連
    expect(points).toHaveLength(1);
    expect(points[0].x).toBeCloseTo(SPARK.width / 2, 5); // 置中（與舊 VolumeSparkline 等價）
  });

  it("全零 → max 防 0：所有點貼底線、不除以 0", () => {
    const { points } = buildSparkline([0, 0, 0], SPARK);
    const bottomY = SPARK.pad + (SPARK.height - SPARK.pad * 2); // = height - pad
    points.forEach((p) => expect(p.y).toBeCloseTo(bottomY, 5));
    expect(points.map((p) => p.y).every((y) => Number.isFinite(y))).toBe(true);
  });

  it("一般多點 → x 均分左右貼內距、line 與 points 數學一致", () => {
    const vols = [1, 3, 2];
    const { line, points } = buildSparkline(vols, SPARK);
    expect(points).toHaveLength(3);
    // 端點 x 貼到內距與右緣，中間點均分。
    expect(points[0].x).toBeCloseTo(SPARK.pad, 5);
    expect(points[2].x).toBeCloseTo(SPARK.width - SPARK.pad, 5);
    expect(points[1].x).toBeCloseTo((SPARK.pad + (SPARK.width - SPARK.pad)) / 2, 5);
    // 較大值 → y 較小（較高）。
    expect(points[1].y).toBeLessThan(points[0].y);
    // line 字串等同 points 串接（折線與端點用同一份座標）。
    expect(line).toBe(points.map((p) => `${p.x},${p.y}`).join(" "));
  });
});

describe("buildStackedAreas", () => {
  it("0 序列 → 空陣列", () => {
    expect(buildStackedAreas([], 160, GEOM)).toEqual([]);
  });

  it("序列存在但 0 點 → 每序列回空字串", () => {
    expect(buildStackedAreas([[], []], 160, GEOM)).toEqual(["", ""]);
  });

  it("全為 0（總和 0）→ 不除以 0，每帶仍是封閉路徑（高度 0）", () => {
    const areas = buildStackedAreas([[0, 0], [0, 0]], 160, GEOM);
    expect(areas).toHaveLength(2);
    areas.forEach((d) => {
      expect(d.startsWith("M")).toBe(true);
      expect(d.endsWith("Z")).toBe(true);
    });
  });

  it("回傳數量 = 序列數，每帶為封閉路徑", () => {
    const areas = buildStackedAreas([[1, 2, 3], [3, 2, 1], [0, 1, 0]], 160, GEOM);
    expect(areas).toHaveLength(3);
    areas.forEach((d) => {
      expect(d.startsWith("M")).toBe(true);
      expect(d.endsWith("Z")).toBe(true);
    });
  });

  it("單點（days=1）→ 各帶橫跨整寬（有正寬度），不收斂同點成空白圖", () => {
    const areas = buildStackedAreas([[2], [3]], 160, GEOM);
    expect(areas).toHaveLength(2);
    areas.forEach((d) => {
      expect(d.startsWith("M")).toBe(true);
      expect(d.endsWith("Z")).toBe(true);
      const xs = (d.match(/[ML](\d+\.\d)/g) ?? []).map((s) => Number(s.slice(1)));
      // 至少有左右兩個相異 x → 面積有正寬度。
      expect(Math.max(...xs) - Math.min(...xs)).toBeGreaterThan(0);
      expect(Math.min(...xs)).toBeCloseTo(GEOM.PAD, 1);
      expect(Math.max(...xs)).toBeCloseTo(GEOM.W - GEOM.PAD, 1);
    });
  });

  it("單點且全為 0（days=1 且當日無資料）→ 仍是封閉路徑、不除以 0", () => {
    const areas = buildStackedAreas([[0], [0]], 160, GEOM);
    expect(areas).toHaveLength(2);
    areas.forEach((d) => {
      expect(d.startsWith("M")).toBe(true);
      expect(d.endsWith("Z")).toBe(true);
    });
  });

  it("堆疊：第二條序列的下緣 = 第一條序列的上緣（共享邊界 y 不重疊穿底）", () => {
    // 單點、單位寬，便於比對 y 值。max 總和 = 1+3 = 4。
    const areas = buildStackedAreas([[1], [3]], 160, GEOM);
    // 取每條 path 內所有 y 值。
    const ysOf = (d: string) => (d.match(/,(\d+\.\d)/g) ?? []).map((s) => Number(s.slice(1)));
    const ys0 = ysOf(areas[0]);
    const ys1 = ysOf(areas[1]);
    // 第一條的上緣 y（最小 = 最高處）應等於第二條的下緣 y（最大 = 最低處）。
    expect(Math.min(...ys0)).toBeCloseTo(Math.max(...ys1), 1);
  });
});
