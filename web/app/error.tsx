"use client";

/**
 * 路由層錯誤邊界（Server Component 拋錯 / 資料抓取失敗時觸發）。
 * 友善退場 + 重試（reset 重新渲染該段），不讓使用者看到白屏或堆疊。
 * 自我包含（不引入會抓資料的 Server Component），避免錯誤頁本身又連鎖出錯。
 */
import { useEffect } from "react";
import Link from "next/link";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 上報到 console（部署時可接 Sentry 等）。
    console.error("[route-error]", error);
  }, [error]);

  return (
    <main className="mx-auto flex max-w-xl flex-col items-center px-6 py-28 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-primary/10 text-2xl">
        ⚠️
      </span>
      <h1 className="mt-5 text-lg font-semibold text-ink">這個區塊暫時載入失敗</h1>
      <p className="mt-2 text-sm leading-relaxed text-ink/70">
        可能是資料來源正在更新，或暫時連不上。你可以重試，或先回首頁看看其他情報。
      </p>
      {error.digest && (
        <p className="mt-2 font-mono text-[11px] text-ink/35">錯誤代碼：{error.digest}</p>
      )}
      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={reset}
          className="rounded-md bg-accent-primary px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-primary/90"
        >
          重試
        </button>
        <Link
          href="/"
          className="rounded-md border border-border px-4 py-1.5 text-sm font-medium text-ink/70 transition-colors hover:bg-bg-cardLight"
        >
          回首頁
        </Link>
      </div>
    </main>
  );
}
