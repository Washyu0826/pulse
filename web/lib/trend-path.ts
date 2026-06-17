/**
 * 趨勢圖 SVG path 計算 —— 純函式（無 DOM），抽出供單元測試鎖住邊界情況：
 * 0 點（回空字串）、1 點（days=1：橫跨整寬畫等高帶，避免 dx=0 收斂同點 → 寬度 0 空白圖）、
 * max=0（值全為 0 → 平貼底線，不除以 0）。
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
  const y = (v: number) => h - PAD - (max > 0 ? (v / max) * (h - PAD * 2) : 0);

  // 單點（days=1）：dx=0 會讓所有 x 收斂同點 → 寬度 0 圖空白。
  // 改讓單點橫跨整個寬度（畫一條等高帶），days=1 仍渲染可見圖。
  if (n === 1) {
    const py = y(values[0]).toFixed(1);
    const left = PAD.toFixed(1);
    const right = (W - PAD).toFixed(1);
    const line = `M${left},${py} L${right},${py}`;
    const area = `${line} L${right},${(h - PAD).toFixed(1)} L${left},${(h - PAD).toFixed(1)} Z`;
    return { area, line };
  }

  const dx = (W - PAD * 2) / (n - 1);
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
  const sentY = (v: number) => sentH / 2 - (v / 100) * (sentH / 2 - PAD);

  // 只有一個有效（非 null）點時，單一 M 指令不會畫出任何可見筆觸；
  // 改畫一條橫跨整寬的等高線，days=1 或僅單日有資料時仍可見。
  const validIdx: number[] = [];
  values.forEach((v, i) => {
    if (v != null) validIdx.push(i);
  });
  if (validIdx.length === 0) return "";
  if (validIdx.length === 1) {
    const py = sentY(values[validIdx[0]] as number).toFixed(1);
    return `M${PAD.toFixed(1)},${py} L${(W - PAD).toFixed(1)},${py}`;
  }

  const dx = (W - PAD * 2) / (n - 1);
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
 * 邊界：0 序列 / 0 點 → 回空陣列；某天總和為 0（max 取整體單日最高總和）→ 該天各帶高度 0（平貼），不除以 0；
 * 單點（n===1，days=1）→ 讓唯一資料點橫跨整寬畫等高帶，避免 dx=0 收斂同點 → 寬度 0 空白圖。
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
  // 單點（days=1）：dx=0 會讓所有 x 收斂同點 → 面積寬度 0 圖空白。
  // 改讓唯一資料點橫跨整寬（左右各取一個同高樣點），days=1 仍渲染可見堆疊帶。
  const single = n === 1;
  const xs = single ? [PAD, W - PAD] : null;
  // 取第 i 點的所有 x 座標（單點時是 [left, right]，多點時是單一 x）。
  const colXs = (i: number): number[] => (single ? (xs as number[]) : [PAD + i * dx]);
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
    let started = false;
    for (let i = 0; i < n; i++) {
      const base = baselineHeights[i];
      const top_h = base + scale(vals[i] ?? 0);
      newBaseline[i] = top_h;
      for (const px of colXs(i)) {
        top.push(`${started ? "L" : "M"}${px.toFixed(1)},${(h - PAD - top_h).toFixed(1)}`);
        started = true;
      }
    }
    for (let i = n - 1; i >= 0; i--) {
      const baseY = (h - PAD - baselineHeights[i]).toFixed(1);
      // 下緣右→左：單點時也要把左右兩個樣點都帶上，圍出整寬的封閉帶。
      const xsForCol = colXs(i);
      for (let j = xsForCol.length - 1; j >= 0; j--) {
        bottom.push(`L${xsForCol[j].toFixed(1)},${baseY}`);
      }
    }
    // 推進 baseline 供下一條序列堆疊其上。
    for (let i = 0; i < n; i++) baselineHeights[i] = newBaseline[i];
    return `${top.join(" ")} ${bottom.join(" ")} Z`;
  });
}
