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
