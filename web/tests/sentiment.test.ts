import { describe, expect, it } from "vitest";

import { sentimentClass, sentimentWord } from "@/lib/sentiment";

describe("sentimentClass", () => {
  it("null → 淡灰", () => {
    expect(sentimentClass(null)).toBe("text-ink/45");
  });

  it("> 10 → 正面色", () => {
    expect(sentimentClass(11)).toBe("text-sentiment-positive");
    expect(sentimentClass(100)).toBe("text-sentiment-positive");
  });

  it("< -10 → 負面色", () => {
    expect(sentimentClass(-11)).toBe("text-sentiment-negative");
    expect(sentimentClass(-100)).toBe("text-sentiment-negative");
  });

  it("邊界 [-10, 10] → 中性色（門檻為嚴格大於/小於）", () => {
    expect(sentimentClass(10)).toBe("text-ink/60");
    expect(sentimentClass(-10)).toBe("text-ink/60");
    expect(sentimentClass(0)).toBe("text-ink/60");
  });
});

describe("sentimentWord", () => {
  it("null → 尚無資料", () => {
    expect(sentimentWord(null)).toBe("尚無資料");
  });

  it("分檔門檻 ±30 / ±10", () => {
    expect(sentimentWord(31)).toBe("口碑很好");
    expect(sentimentWord(30)).toBe("偏正面"); // 30 非 >30
    expect(sentimentWord(11)).toBe("偏正面");
    expect(sentimentWord(10)).toBe("中性"); // 10 非 >10
    expect(sentimentWord(0)).toBe("中性");
    expect(sentimentWord(-10)).toBe("中性");
    expect(sentimentWord(-11)).toBe("偏負面");
    expect(sentimentWord(-30)).toBe("偏負面"); // -30 非 <-30
    expect(sentimentWord(-31)).toBe("口碑不佳");
  });
});
