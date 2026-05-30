import { Activity, GitCompare, MessagesSquare } from "lucide-react";

/** 首頁開場：一句價值主張 + 它跟 HN 差在哪 + 三項能力（5 秒看懂這是什麼、為何有用）。 */
export function HeroIntro() {
  return (
    <section className="border-b border-border/60 pb-8">
      <h1 className="text-xl font-semibold tracking-tight text-white sm:text-2xl">
        AI 模型的即時口碑與動態，一眼掌握
      </h1>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/65">
        Pulse 自動爬梳技術社群（HackerNews、Dev.to、HuggingFace、GitHub）對 6 大模型的討論，
        做<span className="text-white/85">品質過濾 → 情緒分析 → 事件偵測</span>，
        每天 5 分鐘掌握 AI 圈，不用自己一個個網站翻。
      </p>
      <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-white/45">
        和 HackerNews 只有「讚數」不同，Pulse 多給你
        <span className="text-white/60">口碑指數、自動偵測的事件、跨來源彙總、可比較的決策報告</span>。
      </p>

      <ul className="mt-5 grid gap-3 sm:grid-cols-3">
        <FeatureItem icon={<MessagesSquare className="h-4 w-4 text-accent-primary" />} title="口碑指數">
          每篇討論做情緒分析，聚合成各模型 -100..100 的好評/負評淨值。
        </FeatureItem>
        <FeatureItem icon={<Activity className="h-4 w-4 text-sentiment-neutral" />} title="自動偵測事件">
          討論突增、新版發布、口碑翻轉——值得注意的變化幫你挑出來。
        </FeatureItem>
        <FeatureItem icon={<GitCompare className="h-4 w-4 text-accent-cyan" />} title="資料驅動決策">
          選型猶豫時，用真實討論數據比較模型、給有證據的建議。
        </FeatureItem>
      </ul>

      <p className="mt-5 font-mono text-xs text-white/40">
        追蹤 6 個模型 · 5 個來源 · 約 5,000 篇討論 · 過去 30 天
      </p>
    </section>
  );
}

function FeatureItem({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="rounded-lg border border-border/50 bg-bg-card/50 p-3">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-[13px] font-medium text-white/90">{title}</span>
      </div>
      <p className="mt-1.5 text-[12px] leading-relaxed text-white/50">{children}</p>
    </li>
  );
}
