import Link from "next/link";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

/** 查無此模型 slug 時顯示。 */
export default function NotFound() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex max-w-4xl flex-col items-center px-6 py-24 text-center">
        <h1 className="text-lg font-semibold text-ink">找不到這個模型</h1>
        <p className="mt-2 text-sm text-ink/55">
          目前 Pulse 監測 6 個模型：GPT、Claude、Gemini、Grok、Llama、DeepSeek。
        </p>
        <Link
          href="/"
          className="mt-6 rounded-md bg-accent-primary px-4 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-accent-primary/90"
        >
          回儀表板
        </Link>
      </main>
      <SiteFooter />
    </>
  );
}
