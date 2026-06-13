/**
 * 口碑指數（sentiment_index，-100..100）的顯示輔助 —— 純函式，server/client 皆可，可單元測試。
 * 收斂自 decide / 模型詳情頁先前各自內聯的同義邏輯，避免文案/門檻飄移。
 */

/** 口碑值 → 文字色 class。null（尚無資料）走淡灰；門檻 ±10 分檔正/負/中性。 */
export function sentimentClass(idx: number | null): string {
  if (idx == null) return "text-ink/45";
  return idx > 10 ? "text-sentiment-positive" : idx < -10 ? "text-sentiment-negative" : "text-ink/60";
}

/** 口碑值 → 繁中描述詞。門檻：±30 為強、±10 為偏向、之間為中性。 */
export function sentimentWord(idx: number | null): string {
  if (idx == null) return "尚無資料";
  if (idx > 30) return "口碑很好";
  if (idx > 10) return "偏正面";
  if (idx < -30) return "口碑不佳";
  if (idx < -10) return "偏負面";
  return "中性";
}
