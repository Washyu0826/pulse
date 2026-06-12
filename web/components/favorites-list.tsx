"use client";

import { useEffect, useMemo, useState } from "react";

import { FeedCard } from "@/components/feed-card";
import { FAVORITES_EVENT, getFavorites } from "@/lib/favorites";
import { downloadText, generateCollectionPack, type CollectionPack } from "@/lib/pack";
import type { FeedPost } from "@/lib/types";

/**
 * 我的最愛清單（client，讀 localStorage）+ 「選取 → 生成知識材料包」。
 * 勾選若干收藏 → 送後端依主題蒸成可重用材料（做 skill/agent 的素材）→ 下載 .md + sources.jsonl。
 */
export function FavoritesList() {
  const [favs, setFavs] = useState<FeedPost[]>([]);
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [distill, setDistill] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pack, setPack] = useState<CollectionPack | null>(null);

  useEffect(() => {
    const sync = () => setFavs(getFavorites());
    sync();
    setReady(true);
    window.addEventListener(FAVORITES_EVENT, sync);
    return () => window.removeEventListener(FAVORITES_EVENT, sync);
  }, []);

  // 收藏變動時，清掉已不存在的選取。
  useEffect(() => {
    setSelected((prev) => {
      const ids = new Set(favs.map((f) => f.id));
      const next = new Set([...prev].filter((id) => ids.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [favs]);

  const selectedPosts = useMemo(() => favs.filter((f) => selected.has(f.id)), [favs, selected]);
  const allSelected = favs.length > 0 && selected.size === favs.length;

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onGenerate() {
    setBusy(true);
    setError(null);
    setPack(null);
    try {
      const result = await generateCollectionPack(selectedPosts, distill);
      setPack(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失敗，請確認後端是否啟動。");
    } finally {
      setBusy(false);
    }
  }

  if (!ready) return null; // 避免 SSR/CSR 不一致閃爍
  if (favs.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-6 py-10 text-center text-sm text-ink/40">
        還沒有最愛 —— 在情報卡片右上角點 ♥ 收藏，這裡會留著（每週清空不影響）。
      </p>
    );
  }

  return (
    <div>
      {/* 工具列：選取數 / 全選 / 蒸餾開關 / 生成 */}
      <div className="sticky top-16 z-20 mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-bg-card/90 px-4 py-3 shadow-sm shadow-ink/[0.03] backdrop-blur">
        <button
          onClick={() => setSelected(allSelected ? new Set() : new Set(favs.map((f) => f.id)))}
          className="rounded-md border border-border px-3 py-1 text-xs font-medium text-ink/70 transition-colors hover:bg-bg-cardLight"
        >
          {allSelected ? "取消全選" : "全選"}
        </button>
        <span className="text-xs text-ink/50">已選 {selected.size} / {favs.length}</span>

        <label className="ml-auto flex items-center gap-1.5 text-xs text-ink/60" title="用地端模型把收藏蒸成步驟/工具卡；關閉則只輸出條列與來源連結（較快）">
          <input
            type="checkbox"
            checked={distill}
            onChange={(e) => setDistill(e.target.checked)}
            className="h-3.5 w-3.5 accent-accent-primary"
          />
          AI 蒸餾
        </label>
        <button
          onClick={onGenerate}
          disabled={busy || selected.size === 0}
          className="rounded-md bg-accent-primary px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-primary/90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "生成中…" : "生成材料包"}
        </button>
      </div>

      {error && (
        <p className="mb-5 rounded-lg border border-sentiment-negative/30 bg-sentiment-negative/5 px-4 py-2.5 text-sm text-ink/70">
          ⚠️ {error}
        </p>
      )}

      {pack && <PackResult pack={pack} />}

      {/* 收藏卡片（含選取框，z 高於整卡連結） */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {favs.map((p) => (
          <div key={p.id} className="relative">
            <label className="absolute left-2 top-2 z-20 flex cursor-pointer items-center">
              <input
                type="checkbox"
                checked={selected.has(p.id)}
                onChange={() => toggle(p.id)}
                aria-label="選取此收藏"
                className="h-4 w-4 accent-accent-primary"
              />
            </label>
            <div className={selected.has(p.id) ? "rounded-xl ring-2 ring-accent-primary/60" : ""}>
              <FeedCard post={p} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 生成結果：摘要統計 + 下載 .md / sources.jsonl + 複製 + 預覽。 */
function PackResult({ pack }: { pack: CollectionPack }) {
  const [copied, setCopied] = useState(false);
  const distilledThemes = pack.themes.filter((t) => t.distilled).length;

  async function copyMd() {
    try {
      await navigator.clipboard.writeText(pack.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 忽略：剪貼簿不可用時不擋流程 */
    }
  }

  return (
    <div className="mb-6 rounded-xl border border-accent-primary/30 bg-bg-cardLight/60 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-ink">材料包已生成</span>
        <span className="text-xs text-ink/50">
          {pack.n_posts} 篇 · {pack.themes.length} 個主題
          {distilledThemes > 0 ? ` · ${distilledThemes} 個經 AI 蒸餾` : "（確定性條列）"}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => downloadText("collection-pack.md", pack.markdown, "text/markdown")}
          className="rounded-md bg-accent-primary px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-primary/90"
        >
          下載 .md
        </button>
        <button
          onClick={() => downloadText("sources.jsonl", pack.sources_jsonl, "application/x-ndjson")}
          className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-ink/70 transition-colors hover:bg-bg-card"
        >
          下載 sources.jsonl
        </button>
        <button
          onClick={copyMd}
          className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-ink/70 transition-colors hover:bg-bg-card"
        >
          {copied ? "已複製 ✓" : "複製 markdown"}
        </button>
      </div>
      <pre className="mt-4 max-h-72 overflow-auto rounded-lg border border-border bg-bg-card p-3 font-mono text-[11px] leading-relaxed text-ink/70">
        {pack.markdown}
      </pre>
    </div>
  );
}
