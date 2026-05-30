/**
 * 決策報告頁（F3/F4）—— 選模型 + 議題，用真實討論數據給選型建議。
 * Server Component；用原生 GET form（無 client JS）。
 */
import { Badge } from "@/components/ui/badge";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { getDecideReport } from "@/lib/api";
import type { DecideModel } from "@/lib/types";

const MODELS = [
  { slug: "gpt", name: "GPT" },
  { slug: "claude", name: "Claude" },
  { slug: "gemini", name: "Gemini" },
  { slug: "grok", name: "Grok" },
  { slug: "llama", name: "Llama" },
  { slug: "deepseek", name: "DeepSeek" },
];

function sentClass(idx: number | null): string {
  if (idx == null) return "text-white/45";
  return idx > 10 ? "text-sentiment-positive" : idx < -10 ? "text-sentiment-negative" : "text-white/60";
}

function ModelRow({ m, winner }: { m: DecideModel; winner: string | null }) {
  return (
    <div className={`card ${m.slug === winner ? "border-accent-primary/50" : ""}`}>
      <div className="flex items-center gap-2">
        <span className="font-medium text-white">{m.name}</span>
        {m.slug === winner && <Badge variant="accent">推薦</Badge>}
        <span className={`ml-auto font-mono text-sm ${sentClass(m.sentiment_index)}`}>
          口碑 {m.sentiment_index == null ? "—" : m.sentiment_index > 0 ? `+${m.sentiment_index}` : m.sentiment_index}
        </span>
      </div>
      <div className="mt-1 font-mono text-xs text-white/45">
        累計討論 {m.posts_total.toLocaleString()} · 近 7 天 {m.posts_recent}
      </div>
      {m.top_discussions.length > 0 && (
        <ul className="mt-2 space-y-1">
          {m.top_discussions.map((d, i) => (
            <li key={i} className="truncate text-[13px] text-white/60">
              {d.url ? (
                <a href={d.url} target="_blank" rel="noopener noreferrer" className="hover:text-white">
                  {d.title}
                </a>
              ) : (
                d.title
              )}
              <span className="ml-1 font-mono text-white/35">({d.score})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default async function DecidePage({
  searchParams,
}: {
  searchParams: { models?: string | string[]; topic?: string };
}) {
  const raw = searchParams.models;
  const modelsParam = Array.isArray(raw) ? raw.join(",") : (raw ?? "");
  const selected = modelsParam.split(",").filter(Boolean);
  const topic = searchParams.topic ?? "";
  const report = modelsParam ? await getDecideReport(modelsParam, topic || undefined) : null;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl space-y-8 px-6 py-10">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-white sm:text-2xl">決策報告</h1>
          <p className="mt-2 text-sm leading-relaxed text-white/60">
            選要比較的模型 + 議題，Pulse 用<span className="text-white/85">真實討論數據</span>
            （口碑、討論量、熱門討論）給你有證據的選型建議 —— 不是 LLM 空想。
          </p>
        </div>

        <form method="get" className="card space-y-4">
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {MODELS.map((m) => (
              <label key={m.slug} className="flex items-center gap-1.5 text-sm text-white/70">
                <input
                  type="checkbox"
                  name="models"
                  value={m.slug}
                  defaultChecked={selected.includes(m.slug)}
                  className="accent-accent-primary"
                />
                {m.name}
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              name="topic"
              defaultValue={topic}
              placeholder="議題關鍵字（選填），例：coding agent"
              className="flex-1 rounded-md border border-border bg-bg px-3 py-1.5 text-sm text-white placeholder:text-white/30"
            />
            <button
              type="submit"
              className="rounded-md bg-accent-primary px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-primary/90"
            >
              比較
            </button>
          </div>
        </form>

        {report &&
          (!report.ok ? (
            <div className="card text-center text-sm text-sentiment-negative">
              無法產生報告，請確認 API 是否啟動。
            </div>
          ) : report.data.models.length === 0 ? (
            <div className="card text-center text-sm text-white/55">查無指定的模型。</div>
          ) : (
            <div className="space-y-3">
              <div className="rounded-lg border border-accent-primary/40 bg-accent-primary/5 p-4">
                <div className="mb-1 font-mono text-xs uppercase tracking-widest text-accent-primary">
                  建議
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/85">
                  {report.data.generated_by === "llm"
                    ? report.data.summary
                    : report.data.recommendation.reason}
                </p>
                <p className="mt-2 font-mono text-[11px] text-white/40">
                  來源：{report.data.generated_by === "llm" ? "LLM 合成" : "資料驅動"} ·{" "}
                  {report.data.models.length} 模型比較
                </p>
              </div>
              {report.data.models.map((m) => (
                <ModelRow key={m.slug} m={m} winner={report.data.recommendation.winner} />
              ))}
            </div>
          ))}
      </main>
      <SiteFooter />
    </>
  );
}
