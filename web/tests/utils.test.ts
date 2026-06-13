import { describe, expect, it } from "vitest";

import { cn } from "@/lib/utils";

describe("cn", () => {
  it("合併多個 class", () => {
    expect(cn("p-4", "text-white")).toBe("p-4 text-white");
  });

  it("falsy 值被略過（條件式 class）", () => {
    expect(cn("p-4", false && "hidden", undefined, null, "text-ink")).toBe("p-4 text-ink");
  });

  it("tailwind-merge：後者覆蓋同屬性前者", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
    expect(cn("text-sm", "text-lg")).toBe("text-lg");
  });

  it("不同屬性都保留", () => {
    expect(cn("p-4", "m-2")).toBe("p-4 m-2");
  });
});
