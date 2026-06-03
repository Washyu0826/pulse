# 熱詞 / 關鍵字抽取 —— 方法研究與落地方案（2026-06-03）

> 目的：對中英混雜的 AI 社群貼文抽「熱詞」（最近異常變多的詞）。
> 多 agent 平行研究後的收斂結論。全地端、輕量、無雲端 API（對齊 [[prefer-local-llm]]）。

## 核心洞察

**「熱詞」不是關鍵字套件的工作，是「兩個時間段的統計比較」**——「最近 vs 平常，哪些詞異常變多」。
所以核心是 **好的中文斷詞 + 一個統計公式**，不是炫的模型。YAKE / RAKE / TextRank 都是「單篇講什麼」，
與「現在什麼異常熱」正交 → 不適用。KeyBERT（嵌入式）對「單篇語意關鍵字」較好，但對趨勢沒用 → 熱詞 v1 不需要。

## 推薦三層做法

### ① 斷詞（最關鍵、最易踩雷）

```
OpenCC 繁→簡  →  jieba 斷詞（accurate mode, lcut）  →  自訂 AI 詞典 + 中英停用詞過濾
```

- **務必先 OpenCC `t2s`（繁→簡）再 jieba**：jieba 字典是簡體訓練，直接吃繁體會把「軟體 / 提示詞 / 資料庫」切爛。
  顯示時再 `s2tw`（簡→繁）轉回給台灣讀者。← **最大的雷，必修**。
- jieba 會把英文/數字整塊保留（Claude、RAG、GPT-4、2025 不會被拆）；只在空白/標點/中英邊界斷。
- **自訂詞典**（`jieba.load_userdict`）加 AI 術語：MCP、智能體、提示詞、Agent…，給高 freq 避免被拆。
  注意：詞典與停用詞表都要先轉成簡體（與正規化後的文字對齊）。
- **停用詞**：中文用 goto456/stopwords（HIT+百度）或 stopwords-iso/stopwords-zh；英文用 sklearn `ENGLISH_STOP_WORDS`；
  外加 domain 停用詞（AI filler：model/ai/用/覺得/模型…）。保護 acronym 白名單（ai/mcp/rag 別被停用詞濾掉）。
- 過濾：丟單字中文（的了是界用）、純標點、長度 1 的英文（除 acronym 白名單）。

相依：`jieba` + `opencc-python-reimplemented`（都輕、純 Python、不用 torch）。
升級路徑（需要更高斷詞精度時）：**CKIP Transformers**（中研院，繁中最佳，但重、需 torch+模型）或 pkuseg（中等）。

### ② 熱度計算（真正的 trending）

**log-odds ratio + informative Dirichlet prior**（Monroe et al. "Fightin' Words"）比較「近 N 天 vs 基線窗」：

```
δ_w = log( (y_iw+α_w) / (n_i+α0−y_iw−α_w) ) − log( (y_jw+α_w) / (n_j+α0−y_jw−α_w) )
var ≈ 1/(y_iw+α_w) + 1/(y_jw+α_w)
z_w = δ_w / sqrt(var)        # 依 z_w 由大到小排序 = 熱詞
```

- `i` = 近期語料、`j` = 基線語料、`α_w` = 背景（全史）計數當 prior（馴服稀有詞噪音）。
- 純數學、跑在 Postgres `GROUP BY` 計數上、毫秒級、無模型。
- 優於「單純最常見」：找「**異常變多**」的詞（MCP 這週爆increase），不是天天都有的 model/AI。
- 過濾：`z_w > 1.96`（顯著）+ 近期最低計數門檻（≥5）殺噪。
- 參考實作：jmhessel/FightingWords（~40 行，可直接抄）。
- 次要訊號（畫趨勢圖用）：每日詞頻的 modified z-score（可複用 `ml/event_detection.py` 既有的 median/MAD 邏輯）。

### ③（選配）每篇關鍵字

KeyBERT（複用已有的 `sentence-transformers`，無新重相依）+ jieba 的 `CountVectorizer`（中文候選必修，否則整句變一個「詞」）。
推薦嵌入模型 `paraphrase-multilingual-MiniLM-L12-v2`（118M，中英對齊好）。**熱詞榜用不到，別過度設計。**

## 落地建議（Pulse 整合）

1. 新檔 `ml/ml/keywords.py`：仿 `theme.py` 結構——純函式（斷詞 + log-odds 聚合，可單元測試）+ 視需要的模型載入。
2. Postgres 維護 `term_daily_counts(term, day, count)` rollup，或即時窗口查詢；Python 只收兩個小計數 dict。
3. 前端「🔥 熱詞」區（填右側空間，呼應「每日情報」定位）。
4. 相依：`ml/pyproject.toml` 加 `jieba` + `opencc-python-reimplemented`（KeyBERT 走選配再加 `keybert`）。
5. 先驗證：寫 script 跑真實 DB 資料，肉眼看熱詞漂不漂亮，再產品化。

**最大失敗模式**：忘了 OpenCC 繁→簡（或 KeyBERT 忘了 jieba vectorizer）→ 中文斷詞變垃圾。先做這步。

## 來源（節錄）

- jieba: https://github.com/fxsjy/jieba ；繁中斷詞評估: https://aclanthology.org/2022.rocling-1.24/
- OpenCC 繁簡: https://github.com/BYVoid/OpenCC ；CKIP（繁中最佳）: https://github.com/ckiplab/ckip-transformers
- Monroe "Fightin' Words": https://languagelog.ldc.upenn.edu/myl/Monroe.pdf ；實作: https://github.com/jmhessel/FightingWords
- KeyBERT: https://maartengr.github.io/KeyBERT/ ；中文停用詞: https://github.com/goto456/stopwords
