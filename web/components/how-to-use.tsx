"use client";

import { useEffect, useState } from "react";
import { Compass, X } from "lucide-react";

const STORAGE_KEY = "pulse:howto-dismissed:v1";

const STEPS = [
  {
    n: "1",
    title: "看「事件動態」",
    body: "自動挑出值得注意的變化：討論爆量、新版發布、口碑翻轉。",
  },
  {
    n: "2",
    title: "掃「模型看板」",
    body: "六大模型熱度與口碑一覽。點卡片進詳情看趨勢圖。",
  },
  {
    n: "3",
    title: "用「決策報告」",
    body: "選型猶豫時（Claude 還是 GPT？），用真實數據給建議。",
  },
];

/**
 * 首次造訪的「怎麼用」引導條 —— 三步講清楚這頁能幹嘛、怎麼操作。
 * 可關閉，狀態存 localStorage（v1 命名以便日後改版重新顯示）。
 */
export function HowToUse() {
  // 預設不顯示，避免 SSR/CSR 不一致閃爍；mount 後讀 localStorage 決定。
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      setShow(localStorage.getItem(STORAGE_KEY) !== "1");
    } catch {
      setShow(true);
    }
  }, []);

  function dismiss() {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* 隱私模式等 → 忽略，至少這次 session 關掉 */
    }
    setShow(false);
  }

  if (!show) return null;

  return (
    <section className="relative rounded-lg border border-accent-primary/30 bg-accent-primary/[0.06] p-5">
      <button
        type="button"
        onClick={dismiss}
        aria-label="關閉使用說明"
        className="absolute right-3 top-3 rounded-md p-1 text-ink/40 transition-colors hover:bg-ink/10 hover:text-ink"
      >
        <X className="h-4 w-4" />
      </button>
      <div className="flex items-center gap-2">
        <Compass aria-hidden className="h-4 w-4 text-accent-primary" />
        <h2 className="text-sm font-semibold text-ink">第一次來？三步上手</h2>
      </div>
      <ol className="mt-4 grid gap-4 sm:grid-cols-3">
        {STEPS.map((s) => (
          <li key={s.n} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-primary/15 font-mono text-xs font-semibold text-accent-primary">
              {s.n}
            </span>
            <div>
              <div className="text-[13px] font-medium text-ink/90">{s.title}</div>
              <p className="mt-1 text-[13px] leading-relaxed text-ink/55">{s.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
