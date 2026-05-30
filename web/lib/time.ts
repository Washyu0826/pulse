/**
 * 相對時間（zh-TW），用內建 Intl，不加依賴。
 * 注意：在 server render 時計算，靜態頁面下會凍結至下次 revalidate（此處 60s，可接受）。
 */
const _rtf = new Intl.RelativeTimeFormat("zh-TW", { numeric: "auto" });

export function relativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return ""; // 壞的時間字串 → 不顯示，避免 "NaN 天前"
  const diffSec = Math.round((t - Date.now()) / 1000);
  const rtf = _rtf;
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
    ["second", 1],
  ];
  for (const [unit, secs] of units) {
    if (Math.abs(diffSec) >= secs || unit === "second") {
      return rtf.format(Math.round(diffSec / secs), unit);
    }
  }
  return "";
}
