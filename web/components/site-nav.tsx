"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "儀表板" },
  { href: "/favorites", label: "我的最愛" },
  { href: "/decide", label: "決策報告" },
  { href: "/newsletter", label: "電子報" },
];

/** 主導覽（含 active 高亮）—— 讓新訪客一眼看到有哪些頁面可去。 */
export function SiteNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 text-[13px]">
      {LINKS.map((l) => {
        // 「儀表板」在首頁、/models/* 詳情頁與 /theme/* 主題列表頁都算 active（同一條探索動線）。
        const active =
          l.href === "/"
            ? pathname === "/" || pathname.startsWith("/models") || pathname.startsWith("/theme")
            : pathname.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-2.5 py-1 transition-colors",
              active ? "bg-ink/[0.06] text-ink" : "text-ink/70 hover:text-ink",
            )}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
