"""
DQC 下游品質門檻 —— 給「計入統計」的查詢共用的過濾條件。

事件偵測 / 看板彙總應只看**高品質、非重複**的貼文，避免 bot/垃圾/跨來源重複的 burst
被誤判成事件或灌水討論量（ADR-009 的核心動機）。DQC 已把分數/標記寫進 posts，這裡據此過濾。
"""
from api.models.posts import Post

# ADR-009：>=30 為「可分析」門檻，< 30 視為低品質丟棄。
QUALITY_MIN = 30


def quality_post_filter():
    """
    回傳要 AND 進查詢的 WHERE 條件（針對 posts）：
    - quality_score >= QUALITY_MIN；NULL（尚未 DQC）暫放行，避免新貼文在檢核前被丟。
    - 非跨來源重複（quality_flags 不含 DUPLICATE）—— 重複只計 canonical 一篇。
    """
    return (
        (Post.quality_score.is_(None)) | (Post.quality_score >= QUALITY_MIN),
        ~Post.quality_flags.contains(["DUPLICATE"]),
    )
