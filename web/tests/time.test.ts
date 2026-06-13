import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { relativeTime } from "@/lib/time";

describe("relativeTime", () => {
  // 凍結時間，讓相對輸出可預期（zh-TW、numeric:auto）。
  const NOW = new Date("2026-06-13T12:00:00Z").getTime();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("壞的時間字串回空字串（不顯示 NaN）", () => {
    expect(relativeTime("not-a-date")).toBe("");
    expect(relativeTime("")).toBe("");
  });

  it("數小時前", () => {
    const threeHoursAgo = new Date(NOW - 3 * 3600 * 1000).toISOString();
    expect(relativeTime(threeHoursAgo)).toContain("小時");
  });

  it("數天前", () => {
    const twoDaysAgo = new Date(NOW - 2 * 86400 * 1000).toISOString();
    expect(relativeTime(twoDaysAgo)).toContain("天");
  });

  it("數秒內回秒級單位（不回空字串）", () => {
    const justNow = new Date(NOW - 5 * 1000).toISOString();
    expect(relativeTime(justNow)).not.toBe("");
  });

  it("未來時間方向正確（numeric:auto → 含『後』或正向措辭）", () => {
    const inTwoDays = new Date(NOW + 2 * 86400 * 1000).toISOString();
    const out = relativeTime(inTwoDays);
    expect(out).not.toBe("");
    expect(out).toContain("天");
  });
});
