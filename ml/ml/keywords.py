"""
熱詞抽取 —— 中英混雜 AI 貼文的「本週 vs 基線」趨勢關鍵字（全地端、輕量、無模型）。

設計依 docs/keyword-extraction.md 的研究結論：
- 斷詞：OpenCC 繁→簡（jieba 字典是簡體訓練，繁體直餵會切爛）→ jieba 精確模式 → 中英停用詞過濾。
  jieba 會把英文/數字整塊保留（Claude / RAG / GPT-4 不被拆）。顯示時再轉回繁體給台灣讀者。
- 熱度：log-odds ratio（Monroe "Fightin' Words" 簡化版，對稱 prior）比較近期 vs 基線語料，
  每詞得一個 z 分數；配合最低計數門檻殺稀有噪音。z 越高 = 近期異常變多 = 熱詞。

純函式（tokenize / log_odds_trending）不需 DB、可單元測試（與 sentiment.py / theme.py 同風格）。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

import jieba
from opencc import OpenCC

__all__ = ["tokenize", "log_odds_trending", "compute_trending", "to_traditional"]

_t2s = OpenCC("t2s")  # 繁→簡（給 jieba 斷詞）
_s2tw = OpenCC("s2tw")  # 簡→繁（顯示回台灣讀者）

_HAN = re.compile(r"[一-鿿]")
_LATIN_NUM = re.compile(r"^[a-z0-9][a-z0-9+#._-]*$")
_KEEP_SHORT = {"ai", "ml", "ui", "ux", "os", "db", "mcp", "rag", "llm", "sdk", "api", "gpt"}

# AI 術語：加進 jieba 詞典（高 freq 避免被拆）。注意要用簡體（與 t2s 後文字對齊）。
_AI_TERMS = ["提示词", "智能体", "智能体", "大模型", "多模态", "微调", "向量", "agent", "claude code"]
for _t in _AI_TERMS:
    jieba.add_word(_t, freq=10000)

# 停用詞（簡體）：中文功能詞 + 英文 + AI 場域 filler。保護 acronym 不被誤濾。
_STOPWORDS: frozenset[str] = frozenset(
    # 中文功能詞 / 代詞 / 常見
    "的 了 是 在 我 你 他 她 它 们 也 和 与 及 就 都 而 但 不 没 很 更 最 这 那 个 些 "
    "有 会 能 要 把 被 让 给 对 从 向 还 又 再 已 才 只 等 啊 吧 呢 吗 嘛 哦 喔 啦 "
    "我们 你们 他们 自己 什么 怎么 这个 那个 一个 一些 现在 可以 这样 那样 因为 所以 "
    "如果 但是 而且 然后 还有 觉得 真的 应该 可能 问题 一下 一直 已经 之后 之前 "
    "就是 或是 像是 还是 大概 目前 这种 那种 一样 一点 一些 一种 比较 处理 提供 需要 使用 "
    # AI 社群泛詞 filler（解掉爬蟲 chrome 後仍會冒出的中性高頻詞，非 AI 訊號；見 backlog #5）
    # 注意：須用簡體（t2s 後比對）。保留 演算法/agent/prompt 等真術語不入列。
    "讨论 工程师 分钟 小时 请益 软体 程式 学习 开发 专案 公司 工作 经验 事情 面试 职缺 "
    "请问 想问 请教 推荐 分享 感觉 时候 介绍 了解 经历 觉得 知道 希望 大家 各位 最近 今天 "
    "简单 相关 兴趣 详细 的话 东西 之类 任何 等等 其实 想法 毕竟 帮助 机会 过程 修改 最后 名称 "
    "有没有 这些 当然 方式 其他 疑问 要求 符合 目标 这边 那边 其中 之外 之类 而已 而言 "
    # 求職板噪音（AI feed 不需要 年薪/履歷/面試 之類稀釋訊號）
    "年薪 履历 "
    # PTT/JPTT 轉錄樣板殘渣（※ 引述 ... 之銘言、Re: 回文、jptt/imgur app 與圖床、xd 顏文字、自稱小弟）
    "引述 之铭言 铭言 引言 imgur jptt re sent xd 小弟 "
    # 英文常見 + AI filler
    "the a an and or but for to of in on at is are be was were this that with as it "
    "you your we our they i my me from by not no so if then than will can just use using "
    "ai model models llm llms use used data new like get make how why what".split()
)


def tokenize(text: str) -> list[str]:
    """中英混雜斷詞：繁→簡 + 小寫 + jieba 精確模式 + 過濾停用詞/單字噪音。純函式。"""
    text = _t2s.convert((text or "").lower())
    out: list[str] = []
    for tok in jieba.lcut(text, HMM=True):
        tok = tok.strip()
        if not tok:
            continue
        if _HAN.search(tok):
            if len(tok) < 2:  # 丟單字中文（的了是界用…噪音）
                continue
        elif _LATIN_NUM.match(tok):
            # 需 >=2 個英文字母（殺版本碎片 4.8 / 965b / 28），acronym 白名單例外
            if tok not in _KEEP_SHORT and sum(c.isalpha() for c in tok) < 2:
                continue
        else:
            continue  # 純標點/符號
        if tok in _STOPWORDS:
            continue
        out.append(tok)
    return out


def _counts(texts: Iterable[str]) -> Counter:
    """文章頻率（document frequency）：每篇貼文每個詞只計一次。

    用 DF 而非 term frequency → 殺「單篇貼文把專案名刷 12 次」的假熱詞；
    真熱詞是「很多篇貼文都在提」。
    """
    c: Counter = Counter()
    for t in texts:
        c.update(set(tokenize(t)))
    return c


def log_odds_trending(
    recent: Counter,
    baseline: Counter,
    *,
    prior: float = 0.01,
    min_recent: int = 3,
) -> list[tuple[str, float, int]]:
    """
    log-odds ratio（對稱 Dirichlet prior）比較 recent vs baseline。純函式、可測。

    回傳 [(term, z, recent_count), ...] 依 z 由大到小（z>0 = 近期過度出現 = 熱）。
    只看 recent_count >= min_recent 的詞（殺稀有噪音）。
    """
    vocab = set(recent) | set(baseline)
    n1 = sum(recent.values())
    n2 = sum(baseline.values())
    nprior = prior * len(vocab)
    a_tot1 = n1 + nprior
    a_tot2 = n2 + nprior

    scored: list[tuple[str, float, int]] = []
    for w in vocab:
        rc = recent.get(w, 0)
        if rc < min_recent:
            continue
        a1 = rc + prior
        a2 = baseline.get(w, 0) + prior
        # 防 log 內非正（理論上不會，因 a_tot > a）
        d1 = a_tot1 - a1
        d2 = a_tot2 - a2
        if d1 <= 0 or d2 <= 0:
            continue
        delta = math.log(a1 / d1) - math.log(a2 / d2)
        var = 1.0 / a1 + 1.0 / a2
        z = delta / math.sqrt(var)
        scored.append((w, z, rc))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def to_traditional(term: str) -> str:
    """簡體 term 轉回繁體供顯示（英文不受影響）。"""
    return _s2tw.convert(term)


def compute_trending(
    recent_texts: Iterable[str],
    baseline_texts: Iterable[str],
    *,
    top_n: int = 20,
    min_recent: int = 5,
) -> list[dict]:
    """
    端到端：兩組文字 → 熱詞榜。回傳 [{term(繁體顯示), z, recent_count}]，top_n 個。
    baseline 應為「含 recent 在內」的較大基線窗（趨勢 = 近期相對基線的躍升）。
    """
    recent = _counts(recent_texts)
    baseline = _counts(baseline_texts)
    ranked = log_odds_trending(recent, baseline, min_recent=min_recent)[:top_n]
    return [
        {"term": to_traditional(term), "z": round(z, 3), "recent_count": rc}
        for term, z, rc in ranked
    ]


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    recent_demo = [
        "大家都在用 Claude Code 寫程式，MCP 真的好用",
        "MCP server 越來越多，agent 生態起來了",
        "試了 Claude 的 skills，prompt 工作流變很順",
        "MCP 接 RAG 超方便",
    ]
    baseline_demo = recent_demo + [
        "ChatGPT 還是最多人用",
        "Gemini 的圖片生成不錯",
        "今天天氣很好，吃了披薩",
        "DeepSeek 便宜又好用",
        "llama 本地部署教學",
    ]
    print("=== 熱詞（近期 vs 基線）===")
    for kw in compute_trending(recent_demo, baseline_demo, top_n=8):
        print(f"  {kw['term']:12} z={kw['z']:.2f}  (近期 {kw['recent_count']} 次)")
