/**
 * 趨勢圖 SVG path 計算 —— 純函式（無 DOM），抽出供單元測試鎖住邊界情況：
 * 0 點（回空字串）、1 點（dx=0、單點線）、max=0（值全為 0 → 平貼底線，不除以 0）。
 */

export interface ChartGeometry {
  /** 圖寬（viewBox 單位）。 */
  W: number;
  /** 內距。 */
  PAD: number;
}

/**
 * 把一串數值轉成面積圖 + 折線的 SVG path d 字串。
 * @param values 逐點數值（如每日討論量）。
 * @param h 圖高。
 * @param max y 軸最大值（呼叫端需保證 > 0 才會有高度；<=0 時所有點貼底線）。
 */
export function buildPath(
  values: number[],
  h: number,
  max: number,
  geom: ChartGeometry,
): { area: string; line: string } {
  const { W, PAD } = geom;
  const n = values.length;
  if (n === 0) return { area: "", line: "" };
  const dx = n > 1 ? (W - PAD * 2) / (n - 1) : 0;
  const y = (v: number) => h - PAD - (max > 0 ? (v / max) * (h - PAD * 2) : 0);
  const pts = values.map((v, i) => [PAD + i * dx, y(v)] as const);
  const line = pts
    .map(([px, py], i) => `${i === 0 ? "M" : "L"}${px.toFixed(1)},${py.toFixed(1)}`)
    .join(" ");
  const area = `${line} L${pts[n - 1][0].toFixed(1)},${h - PAD} L${pts[0][0].toFixed(1)},${h - PAD} Z`;
  return { area, line };
}

/**
 * 口碑折線（-100..100 → y）的 path，只連有資料（非 null）的點。
 * 全 null 時回空字串（呼叫端會改顯示「尚無情緒資料」）。
 */
export function buildSentimentPath(
  values: (number | null)[],
  sentH: number,
  geom: ChartGeometry,
): string {
  const { W, PAD } = geom;
  const n = values.length;
  const dx = n > 1 ? (W - PAD * 2) / (n - 1) : 0;
  const sentY = (v: number) => sentH / 2 - (v / 100) * (sentH / 2 - PAD);
  const parts: string[] = [];
  values.forEach((v, i) => {
    if (v == null) return;
    const px = PAD + i * dx;
    const py = sentY(v);
    parts.push(`${parts.length === 0 ? "M" : "L"}${px.toFixed(1)},${py.toFixed(1)}`);
  });
  return parts.join(" ");
}
