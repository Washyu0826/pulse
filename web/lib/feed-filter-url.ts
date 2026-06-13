/**
 * 篩選列 URL 參數計算 —— 純函式（不碰 router），抽出供單元測試：
 * 設值寫入、設空字串移除、不影響其他既有參數。
 */

/**
 * 在現有 query 上設定 / 清除單一篩選參數，回傳新的 query 字串。
 * @param current 現有的 searchParams（任何 URLSearchParams 可接受的初始值，含字串）。
 * @param key   要動的參數名（model / sentiment / source / days）。
 * @param value 新值；空字串 = 刪除該參數（回到「全部」）。
 */
export function buildFilterParams(
  current: string | URLSearchParams,
  key: string,
  value: string,
): string {
  const next = new URLSearchParams(typeof current === "string" ? current : current.toString());
  if (value) next.set(key, value);
  else next.delete(key);
  return next.toString();
}
