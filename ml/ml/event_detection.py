"""
事件偵測核心演算法 —— 純函式、只用 stdlib `statistics`，可單元測試（不碰 DB / 網路）。

討論量突增用穩健的 **modified z-score（median / MAD）**，比 mean/std 抗離群值：
- 過去的突增不會灌大 std 而遮蔽下一次突增（mean/std 的 masking 問題）。
- zero-inflated（很多 0 天）資料下 median/MAD 更穩。
參數預設來自研究（Iglewicz–Hoaglin）：window=14、min_count=5、threshold=3.5。
"""
from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

# ---- 預設參數（低量、zero-inflated 每日序列）----
WINDOW = 14  # 滾動 baseline 長度（天）
MIN_BASELINE_DAYS = 5  # 暖身：baseline 不足此天數不發事件
MIN_COUNT = 5  # 絕對門檻：當日數量需達此值才算事件（擋 0→2 雜訊）
MZ_THRESHOLD = 3.5  # modified z-score 門檻
SEVERITY_CAP = 10.0  # severity 上限（也馴服 MAD=0 的無限大）
MAD_FLOOR = 1.0  # MAD 下限（1 篇 = 整數計數的最小有意義單位）


@dataclass
class Spike:
    day: date
    count: int
    modified_z: float
    severity: float
    median: float


@dataclass
class Launch:
    model_slug: str | None
    day: date
    count: int
    titles: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)  # model_upload / github_release


def daily_counts(days: Iterable[date]) -> dict[date, int]:
    """把一串日期（每篇貼文一個）聚合成 {日期: 數量}。"""
    out: dict[date, int] = {}
    for d in days:
        out[d] = out.get(d, 0) + 1
    return out


def fill_daily_gaps(counts: dict[date, int]) -> list[tuple[date, int]]:
    """
    把稀疏的 {日期:數量} 補成從 min 到 max 連續的 [(日期,數量)]，缺的日子補 0。

    zero-inflated 資料中，0 是訊號（安靜的一天）—— 不補 0 會壓縮時間軸、毀掉 baseline。
    """
    if not counts:
        return []
    start, end = min(counts), max(counts)
    out: list[tuple[date, int]] = []
    d = start
    while d <= end:
        out.append((d, counts.get(d, 0)))
        d += timedelta(days=1)
    return out


def _modified_z(x: float, baseline: Sequence[float]) -> tuple[float, float]:
    """回傳 (modified z-score, baseline median)。MAD=0 以 MAD_FLOOR 防除以零。"""
    med = statistics.median(baseline)
    mad = statistics.median([abs(v - med) for v in baseline])
    madn = max(mad, MAD_FLOOR)
    return 0.6745 * (x - med) / madn, med


def detect_spikes(
    series: Sequence[tuple[date, int]],
    *,
    window: int = WINDOW,
    min_baseline: int = MIN_BASELINE_DAYS,
    min_count: int = MIN_COUNT,
    threshold: float = MZ_THRESHOLD,
) -> list[Spike]:
    """
    對「連續每日數量」序列偵測突增（series 須已補 0、依日期排序）。

    每天用「前 window 天（不含當天）」當 baseline 算 modified z；
    當日 >= min_count 且 z >= threshold 且 > baseline median → spike。
    """
    if window < min_baseline:
        raise ValueError("window 必須 >= min_baseline，否則永遠湊不滿 baseline")
    counts = [c for _, c in series]
    spikes: list[Spike] = []
    for t in range(len(series)):
        x = counts[t]
        baseline = counts[max(0, t - window):t]  # trailing，排除當天
        if len(baseline) < min_baseline:
            continue  # 暖身期
        if x < min_count:
            continue  # 絕對門檻
        mz, med = _modified_z(x, baseline)
        if mz >= threshold and x > med:
            spikes.append(
                Spike(
                    day=series[t][0],
                    count=x,
                    modified_z=round(mz, 2),
                    severity=round(min(mz, SEVERITY_CAP), 2),
                    median=med,
                )
            )
    return spikes


def group_launches(releases: Iterable[dict]) -> list[Launch]:
    """
    把 release 事件依 (模型 slug, 日) 聚合成發布事件。

    releases 每筆需含 {"model": slug|None, "day": date, "title": str, "kind"?: str}。
    同模型同日多個發布 → 聚成一筆（count = 當日發布數，kinds = 該日出現的來源類型）。
    """
    groups: dict[tuple[str | None, date], list[dict]] = {}
    for r in releases:
        key = (r.get("model"), r["day"])
        groups.setdefault(key, []).append(r)
    out: list[Launch] = []
    for (slug, day), items in groups.items():
        titles = [it.get("title") or "" for it in items]
        kinds = sorted({it["kind"] for it in items if it.get("kind")})
        out.append(Launch(model_slug=slug, day=day, count=len(items), titles=titles[:5], kinds=kinds))
    return out
