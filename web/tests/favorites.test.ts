import { describe, expect, it } from "vitest";

import { eventToFavoritePost } from "@/lib/favorites";
import type { EventSummary } from "@/lib/types";

function makeEvent(over: Partial<EventSummary> = {}): EventSummary {
  return {
    id: "evt-001",
    title: "GPT-5 釋出",
    summary: "重點摘要 [1] 與更多細節 [2]。",
    citations: [
      { n: 1, url: "https://example.com/a" },
      { n: 2, url: "https://example.com/b" },
    ],
    memberCount: 7,
    theme: "模型動態",
    ...over,
  };
}

describe("eventToFavoritePost", () => {
  it("FNV-1a 雜湊：相同 id 穩定產生相同負數 id", () => {
    const a = eventToFavoritePost(makeEvent({ id: "evt-x" }));
    const b = eventToFavoritePost(makeEvent({ id: "evt-x" }));
    expect(a.id).toBe(b.id);
  });

  it("事件 id 永遠是負數（與貼文正數 id 不相撞）", () => {
    expect(eventToFavoritePost(makeEvent({ id: "a" })).id).toBeLessThan(0);
    expect(eventToFavoritePost(makeEvent({ id: "" })).id).toBeLessThan(0);
    expect(eventToFavoritePost(makeEvent({ id: "x".repeat(50) })).id).toBeLessThan(0);
  });

  it("不同 id → 不同雜湊（避免碰撞）", () => {
    const ids = ["a", "b", "c", "evt-001", "evt-002"].map(
      (id) => eventToFavoritePost(makeEvent({ id })).id,
    );
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("帶 url 的 citation → snippet 含出處清單", () => {
    const post = eventToFavoritePost(makeEvent());
    expect(post.snippet).toContain("出處：");
    expect(post.snippet).toContain("[1] https://example.com/a");
    expect(post.url).toBe("https://example.com/a");
  });

  it("無 url 的 citation → snippet 不加出處段、url 為 null", () => {
    const post = eventToFavoritePost(
      makeEvent({ citations: [{ n: 1 }], summary: "純摘要" }),
    );
    expect(post.snippet).toBe("純摘要");
    expect(post.url).toBeNull();
  });

  it("形狀正確：source / theme / score 對應", () => {
    const post = eventToFavoritePost(makeEvent({ memberCount: 9, theme: "風險限制" }));
    expect(post.source).toBe("今日事件");
    expect(post.theme).toBe("風險限制");
    expect(post.score).toBe(9);
    expect(post.posted_at).toBeNull();
    expect(post.theme_confidence).toBe(1);
  });
});
