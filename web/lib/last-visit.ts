/**
 * 「上次看到這裡」基準（hckrnews 式 NEW 標記，02-patterns P0）。
 *
 * localStorage 記上次來訪時間戳（N=1，不用帳號）；sessionStorage 快取「本次瀏覽 session
 * 的基準」—— 同一個分頁 session 內重新整理 / 站內往返不會推進基準（NEW 不會看一眼就消失），
 * 關掉分頁再來才算下一次來訪。只在 client 呼叫（'use client' 元件的 effect 內）。
 */
const KEY = "pulse:last-visit";
const SESSION_KEY = "pulse:last-visit-baseline";

/**
 * 回傳本次 session 的「上次來訪」基準（epoch ms）。
 * 首次來訪（沒有歷史基準）回 null —— 呼叫端不標 NEW（無基準就不全亮）。
 * 第一次呼叫時順便把 localStorage 推進到現在（供下次來訪當基準）。
 */
export function getLastVisitBaseline(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const cached = sessionStorage.getItem(SESSION_KEY);
    if (cached !== null) return cached === "" ? null : Number(cached);

    const prev = Number(localStorage.getItem(KEY));
    const baseline = Number.isFinite(prev) && prev > 0 ? prev : null;
    sessionStorage.setItem(SESSION_KEY, baseline === null ? "" : String(baseline));
    localStorage.setItem(KEY, String(Date.now()));
    return baseline;
  } catch {
    return null; // 隱私模式等 storage 不可用 → 安靜退化成不標 NEW
  }
}
