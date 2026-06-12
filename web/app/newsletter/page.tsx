/**
 * 電子報說明頁 `/newsletter` —— 給「每日電子報」一個前端落點（P1：目前 IA 完全沒有入口）。
 *
 * 照實寫：Pulse 是自架的 N=1 服務，電子報由後端排程寄送（scripts/send_newsletter.py +
 * PULSE_SMTP_* / PULSE_NEWSLETTER_TO 環境變數），沒有線上訂閱表單 —— 不假裝有。
 * 內容預覽用靜態示意（與實際信件同結構：精選摘要 + 繁中圖表 + 題圖）。
 */
import type { Metadata } from "next";
import { BarChart3, Image as ImageIcon, Mail } from "lucide-react";

import { Section } from "@/components/section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "每日電子報",
  description:
    "Pulse 每日電子報：把當天的 AI 實用情報精選、摘要、配上趨勢圖表，寄到你的信箱 —— 全程地端模型生成。",
};

export default function NewsletterPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-6 py-12">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-primary/10 ring-1 ring-accent-primary/20">
            <Mail className="h-5 w-5 text-accent-primary" aria-hidden />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">每日電子報</h1>
        </div>
        <p className="mt-3 max-w-prose text-sm leading-relaxed text-ink/70">
          不想每天開網站？Pulse 會把當天的 AI 實用情報整理成一封信：從資料庫挑出當日精選、
          用地端模型寫繁中摘要、配上討論趨勢圖表與一張題圖，每天定時寄到信箱 ——
          打開信箱五分鐘掃完，跟首頁同一套資料、同一個口味。
        </p>

        <div className="mt-10 space-y-10">
          <Section label="信裡有什麼" description="與首頁同源，但組成適合信箱掃讀的版型。">
            {/* 內容預覽示意（靜態結構示意，非即時資料） */}
            <div className="overflow-hidden rounded-xl border border-border bg-bg-card shadow-sm shadow-ink/[0.03]">
              <div className="border-b border-border/60 bg-bg-cardLight/60 px-5 py-3">
                <p className="font-mono text-[11px] uppercase tracking-widest text-accent-primary">
                  Pulse Daily
                </p>
                <p className="mt-0.5 text-sm font-semibold text-ink">今天的 AI 實用情報 · 6 月 12 日</p>
              </div>
              <div className="space-y-4 px-5 py-4">
                <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-border text-ink/35">
                  <ImageIcon className="mr-2 h-4 w-4" aria-hidden />
                  <span className="text-xs">每日題圖（本機 Stable Diffusion 生成）</span>
                </div>
                <div>
                  <p className="text-[13px] font-semibold text-ink">今日精選</p>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink/65">
                    當天最值得看的幾則討論，各配 1–2 句地端模型寫的繁中摘要，附原文連結
                    <span className="font-mono text-[11px] text-accent-primary"> →</span>
                  </p>
                </div>
                <div>
                  <p className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">
                    <BarChart3 className="h-3.5 w-3.5 text-accent-primary" aria-hidden />
                    討論趨勢圖
                  </p>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink/65">
                    各模型討論量與口碑的繁中圖表（matplotlib 生成、直接嵌進信件）。
                  </p>
                </div>
              </div>
            </div>
          </Section>

          <Section
            label="怎麼訂閱"
            description="Pulse 是自架的個人服務，目前沒有線上訂閱表單 —— 照實說。"
          >
            <div className="card space-y-3 text-sm leading-relaxed text-ink/70">
              <p>
                電子報由站台排程每天自動寄送，收件人手動設定。想收到這封信？
                <span className="text-ink">聯繫站長</span>，把你的信箱加進寄送名單就行。
              </p>
              <p className="border-t border-border/60 pt-3 text-[13px] text-ink/55">
                自己架 Pulse 的話：在 <code className="rounded bg-ink/[0.05] px-1 font-mono text-[12px]">.env</code> 填好{" "}
                <code className="rounded bg-ink/[0.05] px-1 font-mono text-[12px]">PULSE_SMTP_*</code> 與{" "}
                <code className="rounded bg-ink/[0.05] px-1 font-mono text-[12px]">PULSE_NEWSLETTER_TO</code>，跑{" "}
                <code className="rounded bg-ink/[0.05] px-1 font-mono text-[12px]">
                  python scripts/send_newsletter.py
                </code>
                （加 <code className="rounded bg-ink/[0.05] px-1 font-mono text-[12px]">--dry-run</code>{" "}
                只產生 HTML 預覽不寄信），再掛進每日排程即可。
              </p>
            </div>
          </Section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
