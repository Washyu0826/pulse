"""
共用熱度排序（hotness）—— 貼文 / 事件 / 議題鏈（storyline）三層的熱度與狀態判定。

全部寫成**純函式**：無 DB / 網路 / 隨機，確定性、可離線測（與 ml/ml/event_cluster.py、
ml/ml/theme.py 同套路）。給三處共用：
- scripts/build_storylines.py：算 storyline 每日聲量 / velocity / 升溫退燒狀態。
- scripts/build_today_events.py（可選接入）：事件熱度排序。
- ml/ml/newsletter.py / 前端：一致的「熱度」定義（避免各處各自硬算）。

三個概念分層（由小到大）：
- 貼文熱度 post_hotness：單篇互動 × 時間衰減 × per-source 正規化。
- 事件熱度 event_hotness：成員熱度總和 × 廣度（跨來源越多越可信）。
- 議題鏈熱度 storyline_hotness + 狀態：以「每日聲量序列」算 velocity 與 升溫/高峰/退燒。

互動分數約定（與既有 _engagement / build_today_events 對齊但加權）：
    engagement = like + 2*comment + 3*repost
留言比讚更費力（權重 2），轉發是最強的擴散訊號（權重 3）。缺欄位當 0。
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import median

# ---------------------------------------------------------------------------
# 調參常數（集中於此，附依據）
# ---------------------------------------------------------------------------
# HN 式時間衰減的「重力」指數：分母 (age_hours + 2)^GRAVITY。越大→舊內容掉越快。
# 1.5 介於 HN 經典 0.8（偏慢）與 1.8（偏快）之間，給每日情報「今天的事最重要、
# 三五天內仍可見、一週外幾乎沉底」的衰減曲線。
DEFAULT_GRAVITY = 1.5

# 互動加權（like / comment / repost）。
W_LIKE = 1
W_COMMENT = 2
W_REPOST = 3


# ---------------------------------------------------------------------------
# 互動分數
# ---------------------------------------------------------------------------
def engagement(post: dict) -> float:
    """
    單篇互動分數 = like + 2*comment + 3*repost。純函式、缺欄位當 0。

    容忍多種欄位命名（不同來源/管線）：
    - like:    likes / score / num_likes / like_count
    - comment: comments / num_comments / comment_count / replies
    - repost:  reposts / shares / num_reposts / repost_count / retweets
    """
    like = _first_num(post, ("likes", "score", "num_likes", "like_count"))
    comment = _first_num(post, ("comments", "num_comments", "comment_count", "replies"))
    repost = _first_num(post, ("reposts", "shares", "num_reposts", "repost_count", "retweets"))
    return W_LIKE * like + W_COMMENT * comment + W_REPOST * repost


def _first_num(post: dict, keys: tuple[str, ...]) -> float:
    """取第一個有值的欄位轉 float（None / 非數字 → 0），用於容忍不同來源欄位命名。"""
    for k in keys:
        v = post.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


# ---------------------------------------------------------------------------
# 貼文熱度：互動 × 時間衰減 × per-source 正規化
# ---------------------------------------------------------------------------
def _log_compress(value: float) -> float:
    """log 壓縮：log1p(max(0, value))。把長尾互動數壓進可比範圍，避免少數爆文吃掉排序。"""
    return math.log1p(max(0.0, value))


def post_hotness(
    post: dict,
    *,
    age_hours: float,
    gravity: float = DEFAULT_GRAVITY,
    source_baseline: float | None = None,
) -> float:
    """
    單篇貼文熱度 = 正規化互動 × HN 式時間衰減。純函式、確定性。

    步驟：
    1. engagement(post) 取加權互動。
    2. per-source 正規化：
       - 給 source_baseline（該來源互動的基準，如中位數/某百分位）→ 除以基準（再 +1 防 0）；
         讓「devto 的 50 讚」與「hackernews 的 500 分」可比。
       - 不給 → 退而用 log 壓縮（log1p），同樣壓長尾、無需跨來源統計。
    3. 時間衰減（HN 公式變體）：(e_norm + 1) / (age_hours + 2)^gravity。
       +1 讓零互動仍有微小新鮮度分；+2 避免剛發布（age≈0）時分母過小爆衝。

    age_hours 為負（時鐘誤差/未來時間）時夾為 0。
    """
    e = engagement(post)
    if source_baseline is not None and source_baseline > 0:
        e_norm = e / source_baseline
    else:
        e_norm = _log_compress(e)
    age = max(0.0, age_hours)
    return (e_norm + 1.0) / math.pow(age + 2.0, gravity)


# ---------------------------------------------------------------------------
# per-source 平衡排序：各來源依正規化熱度排序，再 round-robin 跨來源取
#
# 共用給：ml/ml/newsletter.py（精選 / 口碑挑選）、api/api/services/feed.py（主題 feed），
# 讓低互動量級的主力來源（Threads）能與高量級來源（HN）在同尺度上公平競爭、不被洗版。
# 純函式、確定性、無 DB。
# ---------------------------------------------------------------------------
def source_baselines(
    posts: Sequence[dict], *, source_key: str = "source"
) -> dict[str, float]:
    """
    算各來源的互動「基準」= 該來源所有貼文 engagement 的中位數（純函式、確定性）。

    為何用中位數而非平均/最大：HN 偶有爆文（points 上千），平均/最大會被單篇拉高，
    讓正常 HN 貼文反而「相對不熱」；中位數代表該來源的典型量級，最能公平正規化。
    只納入互動 > 0 的貼文算中位數（全 0 或無正互動的來源 → 不給基準，post_hotness
    會退回 log 壓縮）。回傳 {source: baseline>0}。
    """
    by_src: dict[str, list[float]] = {}
    for p in posts:
        e = engagement(p)
        if e > 0:
            src = str(p.get(source_key) or "unknown")
            by_src.setdefault(src, []).append(e)
    return {src: median(vals) for src, vals in by_src.items() if vals}


def _balanced_key(
    post: dict,
    baselines: dict[str, float],
    *,
    source_key: str,
    id_key: str,
):
    """
    排序鍵：per-source 正規化熱度，同分以 id 決勝（確定性）。

    age_hours=0：在固定時間視窗內時間衰減對所有貼文一致（分母同為定值），不影響相對排序；
    重點是用該來源基準正規化互動，讓 Threads 讚數與 HN points 在「同量級尺度」上競爭。
    來源無基準時 source_baseline=None → post_hotness 退回 log 壓縮（仍可比、不爆長尾）。
    """
    baseline = baselines.get(str(post.get(source_key) or "unknown"))
    h = post_hotness(post, age_hours=0, source_baseline=baseline)
    return (h, post.get(id_key, 0))


def rank_balanced(
    posts: Sequence[dict],
    *,
    k: int,
    source_key: str = "source",
    id_key: str = "id",
    baselines: dict[str, float] | None = None,
) -> list[dict]:
    """
    取前 k 篇，但做「同來源至少露出」的輕量平衡（純函式、確定性）。

    各來源內先依 per-source 正規化熱度排序，再以 round-robin 跨來源輪流取（每輪各來源出
    最熱的一篇），來源順序依「該來源當前最熱貼文的熱度」由高到低。效果：高量級來源（HN）
    不會因原始互動大就洗版整個區塊，主力來源 Threads 能穩定露出；同時最熱的仍排前面。

    baselines 可預先用 source_baselines 算好傳入（多次呼叫共用同一組基準時）；不傳則由
    posts 內部自行算（自洽、無需 DB）。k<=0 回 []。
    """
    if k <= 0:
        return []
    if baselines is None:
        baselines = source_baselines(posts, source_key=source_key)
    by_src: dict[str, list[dict]] = {}
    for p in posts:
        by_src.setdefault(str(p.get(source_key) or "unknown"), []).append(p)
    queues = {
        src: sorted(
            items,
            key=lambda p: _balanced_key(p, baselines, source_key=source_key, id_key=id_key),
            reverse=True,
        )
        for src, items in by_src.items()
    }
    out: list[dict] = []
    while len(out) < k and any(queues.values()):
        # 每輪：依各來源「下一篇待選」的熱度排來源序，輪流各取一篇（同來源至少露出）。
        ready = [src for src, q in queues.items() if q]
        ready.sort(
            key=lambda s: _balanced_key(
                queues[s][0], baselines, source_key=source_key, id_key=id_key
            ),
            reverse=True,
        )
        for src in ready:
            if len(out) >= k:
                break
            out.append(queues[src].pop(0))
    return out


# ---------------------------------------------------------------------------
# 事件熱度：成員熱度總和 × 廣度
# ---------------------------------------------------------------------------
def breadth_factor(num_sources: int) -> float:
    """
    廣度因子 = 1 + log(來源數)。跨越越多來源 → 事件越「真」（非單一平台炒作）。

    來源數 <= 1 → 因子 1.0（log1 = 0）。確定性、純算術。
    """
    n = max(1, num_sources)
    return 1.0 + math.log(n)


def event_hotness(member_hotnesses: Sequence[float], *, num_sources: int) -> float:
    """
    事件熱度 = 成員貼文熱度總和 × 廣度因子(來源數)。純函式。

    成員熱度建議用 post_hotness 算好後傳入；空事件回 0.0。
    """
    total = math.fsum(h for h in member_hotnesses if h > 0)
    return total * breadth_factor(num_sources)


# ---------------------------------------------------------------------------
# 議題鏈（storyline）熱度 + 狀態
# ---------------------------------------------------------------------------
def day_volume(member_count: int, interaction: float) -> float:
    """
    某一天的「聲量」= 成員數 + log(1 + 互動)。

    比原型純互動總和穩：成員數（多少篇在談）給穩定基底，log(互動) 收斂避免單篇爆文
    主導；兩者相加 → 一篇千讚的孤文不會贏過十篇穩定討論。純函式、確定性。
    """
    return max(0, member_count) + math.log1p(max(0.0, interaction))


def storyline_hotness(daily_volumes: Sequence[float]) -> float:
    """
    議題鏈整體熱度 = 各日聲量總和。純函式；空序列回 0.0。

    用於 storyline 之間排序（最熱在前）。聲量本身已用 day_volume 壓過長尾。
    """
    return math.fsum(v for v in daily_volumes if v > 0)


def velocity(daily_volumes: Sequence[float]) -> float:
    """
    最新一日的 velocity = 末日聲量 − 前一日聲量（Δvolume）。

    少於 2 日 → 0.0（無從比較）。> 0 升溫、< 0 退燒、= 0 持平。純函式。
    """
    if len(daily_volumes) < 2:
        return 0.0
    return float(daily_volumes[-1] - daily_volumes[-2])


# 狀態標籤（與前端徽章對齊；用穩定的中文字串，前端再映射顏色）。
STATE_RISING = "升溫"
STATE_PEAK = "高峰"
STATE_COOLING = "退燒"
STATE_FLAT = "持平"


def storyline_state(daily_volumes: Sequence[float]) -> str:
    """
    依「每日聲量序列」判議題鏈的當前狀態。純函式、確定性。

    規則（看最後一格相對於前一格與全局高峰）：
    - 空 / 單日：升溫（議題剛出現）。
    - 末日 == 全局最高 且 仍在上升（或與高峰同值）→ 高峰。
    - 末日 velocity > 0 → 升溫。
    - 末日 velocity < 0 → 退燒。
    - 末日 velocity == 0 → 持平。

    「高峰」優先於單純的升溫/退燒：當天就是這條議題目前最熱的一天時，標高峰更貼切。
    """
    vols = list(daily_volumes)
    if len(vols) <= 1:
        return STATE_RISING

    last = vols[-1]
    vel = velocity(vols)
    peak = max(vols)

    # 末日就是全局高峰（且非單調下滑造成的假高峰）→ 高峰。
    # 條件：末日值等於全局最大，且相對前一日未下降。
    if last >= peak and vel >= 0:
        return STATE_PEAK
    if vel > 0:
        return STATE_RISING
    if vel < 0:
        return STATE_COOLING
    return STATE_FLAT
