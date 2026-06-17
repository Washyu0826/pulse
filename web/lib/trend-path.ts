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

/**
 * 堆疊面積圖 path 計算 —— 純函式（無 DOM），供 dashboard 主題/情緒時序共用。
 *
 * @param series 多條序列，每條為逐點數值（如各主題逐日貼文數）。所有序列長度需一致（= 天數）。
 * @param h 圖高（viewBox 單位）。
 * @returns 與 series 同序的每條「帶狀面積」path d 字串；各帶為「該序列在堆疊中的上緣 → 下緣 → 閉合」。
 *
 * 邊界：0 序列 / 0 點 → 回空陣列；某天總和為 0（max 取整體單日最高總和）→ 該天各帶高度 0（平貼），不除以 0。
 */
export function buildStackedAreas(
  series: number[][],
  h: number,
  geom: ChartGeometry,
): string[] {
  const { W, PAD } = geom;
  const s = series.length;
  if (s === 0) return [];
  const n = series[0]?.length ?? 0;
  if (n === 0) return series.map(() => "");

  // y 軸最大值 = 整段期間「單日各序列總和」的最大者（堆疊高度上限）。
  let maxTotal = 0;
  for (let i = 0; i < n; i++) {
    let total = 0;
    for (let k = 0; k < s; k++) total += series[k][i] ?? 0;
    if (total > maxTotal) maxTotal = total;
  }

  const dx = n > 1 ? (W - PAD * 2) / (n - 1) : 0;
  const x = (i: number) => PAD + i * dx;
  // value → 高度（像素），再由 baseline 累加得到 y。
  const scale = (v: number) =>
    maxTotal > 0 ? (v / maxTotal) * (h - PAD * 2) : 0;

  // 逐點累計各序列的下緣堆疊高度。
  const baselineHeights = new Array<number>(n).fill(0);
  return series.map((vals) => {
    // 上緣（左→右）：baseline + 本序列高度。
    const top: string[] = [];
    // 下緣（右→左）：目前 baseline。
    const bottom: string[] = [];
    const newBaseline = new Array<number>(n);
    for (let i = 0; i < n; i++) {
      const base = baselineHeights[i];
      const top_h = base + scale(vals[i] ?? 0);
      newBaseline[i] = top_h;
      const px = x(i);
      top.push(`${i === 0 ? "M" : "L"}${px.toFixed(1)},${(h - PAD - top_h).toFixed(1)}`);
    }
    for (let i = n - 1; i >= 0; i--) {
      const px = x(i);
      bottom.push(`L${px.toFixed(1)},${(h - PAD - baselineHeights[i]).toFixed(1)}`);
    }
    // 推進 baseline 供下一條序列堆疊其上。
    for (let i = 0; i < n; i++) baselineHeights[i] = newBaseline[i];
    return `${top.join(" ")} ${bottom.join(" ")} Z`;
  });
}
