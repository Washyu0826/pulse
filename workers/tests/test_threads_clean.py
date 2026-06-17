"""
Threads 內文清洗純函式測試 —— 用真實髒樣本（DB 今日批次）當案例，確認 UI chrome 被剝乾淨
且真內文不被誤刪。不需瀏覽器 / 網路 / DB。
"""
from crawlers.threads_clean import clean_thread_text


def test_strips_handle_date_and_trailing_counts():
    """真實樣本 id=172903：handle + 短標題 + 日期 在前，分頁 + 多個計數在後。"""
    dirty = (
        "handsome_6_love\n"
        "暑假\n"
        "2025-7-21\n"
        "還在為大家放暑假都有附日本🇯🇵機票\n"
        "自己因為沒錢在家裡偷偷哭嗎\n"
        "大家可以趁暑假學投資！\n"
        "而這個 AI 就是幫大家練習投資的好工具\n"
        "沒有 AI 幻覺全憑公開資料庫搜索\n"
        "大家可以試試看ㄛ！\n"
        "這邊有幫大家整理往年暑假比較有上漲趨勢的股票\n"
        "可以去聊天室看看👀 \n"
        "1\n/\n2\n15\n1\n2\n20"
    )
    clean = clean_thread_text(dirty)
    # handle + 短標題 + 日期（到時間錨點為止）整塊被剝，內文從第一段真句子開始。
    assert clean.startswith("還在為大家放暑假")
    assert clean.endswith("可以去聊天室看看👀")
    # 明確 chrome 應消失
    assert "handsome_6_love" not in clean
    assert "2025-7-21" not in clean
    assert not clean.startswith("暑假")  # 開頭短標題「暑假」被剝（內文中段的「暑假」仍保留）
    assert "暑假" in clean  # 內文 "趁暑假學投資" 不受影響
    assert not clean.endswith("20")
    assert "/" not in clean.splitlines()


def test_strips_handle_and_single_trailing_count():
    """真實樣本 id=172896：handle + 短標題 + 日期 在前，結尾單一計數 '4'。"""
    dirty = (
        "albert.aka.aba\n"
        "AI幻覺\n"
        "2025-2-12\n"
        "你聽過AI幻覺 嗎？￼教你如何訓練 AI 誠實\n"
        "BBC 2/11 報導，指出 AI 生成新聞摘要內容錯誤率51%。確實，AI真的很會一本正經講幹話。\n"
        "4"
    )
    clean = clean_thread_text(dirty)
    # handle + 短標題「AI幻覺」+ 日期 整塊被剝（到時間錨點）。
    assert clean.startswith("你聽過AI幻覺")
    assert "BBC 2/11 報導" in clean  # 內文中的日期樣式 "2/11" 不可被誤刪
    assert clean.endswith("講幹話。")
    assert "albert.aka.aba" not in clean
    assert "2025-2-12" not in clean


def test_strips_relative_time_header():
    """真實樣本 id=172844：handle + 相對時間 '20小時' 在前，結尾計數 '1'。"""
    dirty = "therealtaipeijay\n20小時\n我覺得AI 就是黃山料\n1"
    clean = clean_thread_text(dirty)
    assert clean == "我覺得AI 就是黃山料"


def test_strips_thousands_separator_counts():
    """真實樣本 id=172879：結尾多個含千分位的計數行。"""
    dirty = (
        "tsai1519\n"
        "2025-5-28\n"
        "中國AI機器農場曝光\n"
        "數百個AI操控的機器人24小時不間斷地發出成千上萬的留言與貼文。\n"
        "3,761\n193\n730\n400"
    )
    clean = clean_thread_text(dirty)
    # 「中國AI機器農場曝光」是內文首行（非 chrome），必須保留。
    assert clean.startswith("中國AI機器農場曝光")
    assert clean.endswith("留言與貼文。")
    assert "3,761" not in clean
    assert "24小時" in clean  # 內文中的「24小時」是實質內容，不可被當相對時間剝掉


def test_pagination_and_xu_marker():
    """分頁 '1 / 3' 拆行 + '(續)' 標記應被剝。"""
    dirty = (
        "jeffery_2021\n"
        "2025-2-19\n"
        "心理師也是人，不可能一視同仁地接納所有人。\n"
        "（續） \n"
        "1\n/\n3\n23\n9\n2"
    )
    clean = clean_thread_text(dirty)
    assert clean == "心理師也是人，不可能一視同仁地接納所有人。"


def test_translate_button_stripped():
    dirty = "someuser\n2025-1-1\nThis is a real AI post about Claude.\nTranslate\n12"
    clean = clean_thread_text(dirty)
    assert clean == "This is a real AI post about Claude."


def test_does_not_strip_real_short_post():
    """純內文（無 chrome）：handle 行不存在時，第一行就是內文 → 不可被當 chrome 剝。"""
    clean = clean_thread_text("Claude is way better than GPT for refactoring")
    assert clean == "Claude is way better than GPT for refactoring"


def test_does_not_strip_numbers_in_body():
    """內文中段的數字行不可被剝（只剝尾端連續純數字）。"""
    dirty = (
        "user_x\n"
        "2025-3-1\n"
        "我的測試結果：\n"
        "100\n"
        "這個分數代表滿分。\n"
        "5"
    )
    clean = clean_thread_text(dirty)
    assert clean.startswith("我的測試結果：")
    assert "100" in clean  # 中段數字保留
    assert clean.endswith("這個分數代表滿分。")  # 尾端 '5' 被剝


def test_empty_input():
    assert clean_thread_text("") == ""
    assert clean_thread_text("   ") == ""


def test_english_relative_time_and_now():
    dirty = "dev_handle\n3h\nReal post body about GPT agents and prompts.\n42\n7"
    clean = clean_thread_text(dirty)
    assert clean == "Real post body about GPT agents and prompts."


def test_header_short_title_not_stripped_without_chrome():
    """沒有先出現明確 chrome（handle/日期）時，短行不可被當標題剝（保守）。"""
    clean = clean_thread_text("AI\n這是一段沒有 handle 開頭的內文。")
    assert clean.startswith("AI")


# ---------------------------------------------------------------------------
# Bug #7a 反向案例：真內文以「內容性數字」結尾（年份 / 型號 / 多位數），不可被當互動計數誤刪。
# ---------------------------------------------------------------------------

def test_does_not_strip_trailing_year_as_count():
    """真內文最後一行是落單年份 '2025'（≥4 位）→ 視為內容，不可被當讚數剝。"""
    dirty = (
        "tsai1519\n"
        "2025-5-28\n"
        "這款新模型的發表年份是\n"
        "2025"
    )
    clean = clean_thread_text(dirty)
    assert clean.endswith("2025")  # 結尾年份保留
    assert clean.startswith("這款新模型")
    assert "tsai1519" not in clean
    assert "2025-5-28" not in clean  # 開頭日期 chrome 仍被剝（不回歸）


def test_does_not_strip_trailing_model_number_as_count():
    """真內文最後一行是落單型號 '4090'（≥4 位）→ 視為內容，不可被當轉發數剝。"""
    dirty = (
        "dev_handle\n"
        "3h\n"
        "跑這個本地模型我用的顯卡是 RTX\n"
        "4090"
    )
    clean = clean_thread_text(dirty)
    assert clean.endswith("4090")  # 結尾型號保留
    assert "dev_handle" not in clean  # 開頭 handle + 相對時間仍被剝（不回歸）


def test_strips_thousands_count_even_when_lone():
    """落單但符合明確互動計數樣態（千分位 '3,761'）→ 仍當計數剝（不會是內文年份/型號）。"""
    dirty = "someuser\n2025-1-1\n這是一篇關於 AI 的真內文。\n3,761"
    clean = clean_thread_text(dirty)
    assert clean == "這是一篇關於 AI 的真內文。"


def test_year_preserved_but_count_cluster_after_body_stripped():
    """真內文以年份 '2025' 結尾（保留）；若年份之後另接互動計數群，計數仍被剝、年份留。"""
    dirty = (
        "someuser\n"
        "2025-1-1\n"
        "這個模型發表於 2025\n"   # 句中年份（不成行）本就不受影響
        "新版本是\n"
        "2025\n"                  # 落單成行的內容年份 → 保留
        "3,761\n12"               # 其後互動計數群 → 全剝
    )
    clean = clean_thread_text(dirty)
    assert clean.endswith("2025")           # 內容年份成行保留
    assert "3,761" not in clean              # 千分位計數剝
    assert not clean.endswith("12")          # 落單計數剝（其後其實沒有，但屬計數群）
    assert clean.startswith("這個模型發表於 2025")


# ---------------------------------------------------------------------------
# Bug #7b 反向案例：真內文以英文 AI 專名開頭（含大寫 / 在 allowlist），不可被當 handle 誤剝。
# ---------------------------------------------------------------------------

def test_does_not_strip_leading_proper_noun_with_uppercase():
    """真內文首行以含大寫的英文專名開頭（OpenAI），附近又有相對時間 → 不可被當 handle 剝。"""
    dirty = (
        "OpenAI\n"
        "3天\n"
        "今天發表了新的模型，效果很驚人。"
    )
    clean = clean_thread_text(dirty)
    assert clean.startswith("OpenAI")  # 英文專名首行保留（含大寫 → 非 handle）
    assert "3天" in clean  # 沒有 handle 開頭 → 不觸發開頭剝除，相對時間行也保留


def test_does_not_strip_leading_gpt4_proper_noun():
    """真內文首行 'GPT4'（含大寫）+ 後面有絕對日期樣行 → 不可被當 handle 剝。"""
    dirty = (
        "GPT4\n"
        "2025-6-1\n"
        "正式上線，支援更長的上下文。"
    )
    clean = clean_thread_text(dirty)
    assert clean.startswith("GPT4")  # 含大寫 → 非 handle，整段內文不被開頭剝除吃掉


def test_does_not_strip_leading_lowercase_ai_proper_noun():
    """首行恰為純小寫 AI 專名（openai，在 allowlist）+ 相對時間 → 仍不可當 handle 剝。"""
    dirty = (
        "openai\n"
        "3h\n"
        "正式發表了 o4 模型。"
    )
    clean = clean_thread_text(dirty)
    assert clean.startswith("openai")  # allowlist 命中 → 非 handle，首行內容保留


def test_real_lowercase_handle_still_stripped():
    """收緊後純小寫、非 AI 專名的真 handle（someuser）仍被正確剝（不回歸 Bug #7b）。"""
    dirty = "someuser\n2025-1-1\n這是真內文一段話。\n12"
    clean = clean_thread_text(dirty)
    assert clean == "這是真內文一段話。"
