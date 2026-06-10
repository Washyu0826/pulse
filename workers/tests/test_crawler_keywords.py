"""爬蟲關鍵字純函式測試 —— match_models / is_ai_related / looks_simplified。"""
from crawlers.keywords import is_ai_related, looks_simplified, match_models


# ---- match_models（既有，補強）----
def test_match_models_basic_and_word_boundary():
    assert sorted(match_models("Claude beats GPT")) == ["claude", "gpt"]
    assert match_models("grokking the codebase") == []  # \b 詞界：grok 不命中 grokking
    assert match_models("天氣很好") == []


# ---- is_ai_related：中文（主力，不點名模型也要過）----
def test_is_ai_related_chinese_without_model_name():
    assert is_ai_related("分享我的提示詞工作流") is True       # 提示詞
    assert is_ai_related("用 AI工具 自動生成貼文") is True      # AI（與中文相鄰）
    assert is_ai_related("最近在玩 AI繪圖 跟文生圖") is True     # 生圖
    assert is_ai_related("生成式AI 真的改變工作流") is True     # 生成式
    assert is_ai_related("人工智慧會取代設計師嗎") is True       # 人工智慧


def test_is_ai_related_english_tokens():
    assert is_ai_related("new prompts for ChatGPT") is True   # loose 容許 prompts
    assert is_ai_related("building AI agents with MCP") is True
    assert is_ai_related("fine-tuning a small model") is True  # fine-tun


def test_is_ai_related_avoids_false_positives():
    assert is_ai_related("I sent you an email about the rain") is False  # 'ai' 在 email/rain 內不算
    assert is_ai_related("grokking algorithms again") is False           # grok 嚴格邊界
    assert is_ai_related("今天午餐吃披薩，天氣很好") is False
    assert is_ai_related("") is False


def test_is_ai_related_ai_token_adjacency():
    assert is_ai_related("用AI寫程式") is True      # 中文緊鄰 ai
    assert is_ai_related("AI") is True
    assert is_ai_related("maintain the chain") is False  # 'ai' 在英文字中不算


# ---- looks_simplified：擋簡體（中國）內容 ----
def test_looks_simplified_detects_china_content():
    assert looks_simplified("这个软件的网络功能很实用") is True   # 这/软/网/实… 多個 marker
    assert looks_simplified("我们正在开发新的对话机器人") is True


def test_looks_simplified_keeps_traditional():
    assert looks_simplified("這個軟體的網路功能很實用") is False  # 全繁體
    assert looks_simplified("分享我的提示詞與 AI 工具") is False
    assert looks_simplified("") is False


def test_looks_simplified_tolerates_single_marker():
    # 繁中貼文偶爾夾一個簡體字（如引用）→ 不誤殺（門檻預設 2）
    assert looks_simplified("這篇文章寫得很好") is False
    assert looks_simplified("引用了一个简体词但其餘都是繁體內容的貼文", min_markers=2) is True
