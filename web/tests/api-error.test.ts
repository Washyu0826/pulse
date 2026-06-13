import { describe, expect, it } from "vitest";

import { friendlyError, isNotFound } from "@/lib/api";

describe("friendlyError", () => {
  it("HTTP 404 → 找不到", () => {
    expect(friendlyError("HTTP 404")).toBe("找不到這項資料。");
  });

  it("HTTP 429 → 太頻繁", () => {
    expect(friendlyError("HTTP 429")).toBe("查詢太頻繁，請稍候再試。");
  });

  it("HTTP 5xx → 伺服器忙線", () => {
    expect(friendlyError("HTTP 500")).toBe("伺服器忙線中，稍後再試。");
    expect(friendlyError("HTTP 503")).toBe("伺服器忙線中，稍後再試。");
  });

  it("其他 4xx → 通用無法處理", () => {
    expect(friendlyError("HTTP 400")).toBe("這次請求無法處理，稍後再試。");
    expect(friendlyError("HTTP 422")).toBe("這次請求無法處理，稍後再試。");
  });

  it("malformed response → 格式異常", () => {
    expect(friendlyError("malformed response")).toBe("資料格式異常，稍後再試。");
  });

  it("逾時（TimeoutError 字串）→ 連線逾時", () => {
    expect(friendlyError("TimeoutError: signal timed out")).toBe("連線逾時，稍後再試。");
  });

  it("未知錯誤 → 預設 fallback", () => {
    expect(friendlyError("something weird")).toBe("內容暫時載入不了，稍後再試。");
  });

  it("可帶區塊專屬 fallback", () => {
    expect(friendlyError("something weird", "今日事件暫時載入不了，稍後再試。")).toBe(
      "今日事件暫時載入不了，稍後再試。",
    );
    // 已知代碼仍走在地化映射，不被 fallback 蓋掉。
    expect(friendlyError("HTTP 404", "區塊文案")).toBe("找不到這項資料。");
  });
});

describe("isNotFound", () => {
  it("HTTP 404 → true", () => {
    expect(isNotFound("HTTP 404")).toBe(true);
  });
  it("其他 → false", () => {
    expect(isNotFound("HTTP 500")).toBe(false);
    expect(isNotFound("malformed response")).toBe(false);
  });
});
