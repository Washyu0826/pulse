import { Activity, GitCompare, MessagesSquare } from "lucide-react";

/** 首頁開場：一句價值主張 + 它跟 HN 差在哪 + 三項能力（5 秒看懂這是什麼、為何有用）。 */
export function HeroIntro() {
  return (
    <section className="border-b border-border/60 pb-8">
      <h1 className="text-xl font-semibold tracking-tight text-white sm:text-2xl">
        AI 模型口碑與動態，一眼掌握
      </h1>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/65">
        自動爬梳技術社群對 6 大模型的討論，做
        <span className="text-white/85">品質過濾 → 情緒分析 → 事件偵測</span>。
      </p>
      <p className="mt-2 max-w-2xl text-[13px] text-white/45">
        不只讚數：<span className="text-white/60">口碑指數、自動事件、跨來源彙總、決策報告</span>。
      </p>

      <ul className="mt-5 grid gap-3 sm:grid-cols-3">
        <FeatureItem icon={<MessagesSquare className="h-4 w-4 text-accent-primary" />} title="口碑指數">
          情緒分析聚合成 −100~100 好評淨值。
        </FeatureItem>
        <FeatureItem icon={<Activity className="h-4 w-4 text-sentiment-neutral" />} title="自動偵測事件">
          討論突增、新版發布、口碑翻轉自動挑出。
        </FeatureItem>
        <FeatureItem icon={<GitCompare className="h-4 w-4 text-accent-cyan" />} title="資料驅動決策">
          用真實數據比較模型、給選型建議。
        </FeatureItem>
      </ul>

      <p className="mt-5 font-mono text-xs text-white/40">
        6 模型 · 5 來源 · 約 5,000 篇討論 · 近 30 天
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
