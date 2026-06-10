# 繁中短文 Semantic Embedding + Event Clustering 研究

> 範圍：為 Faithful Event Summarizer 的「embed → cluster → MMR 抽句 → summarize」管線挑選 **embedding model** 與 **clustering recipe**。
> 硬體：RTX 4060 Laptop 8GB、local-first、open weights、**不打雲端 embedding API**。
> 資料：短貼文（title + body），繁中 / English 混雜，corpus ~60k，每日 event batch 數百篇。
> 撰寫日：2026-06-10。技術名詞保留英文。

---

## TL;DR 結論（先看這段）

1. **首選 embedding model：`BAAI/bge-m3`**，但**改用 `sentence-transformers` 載入（取 dense vector），不要用 FlagEmbedding，也不要走 Ollama**。
   - 理由：MIT 授權可商用、1024-dim dense、繁中表現穩、zh+en 混合天生支援、8192 token 夠長、fp16 下 8GB VRAM 綽綽有餘、安裝路徑單純（只要 `pip install sentence-transformers`）。
2. **替代 1：`Qwen/Qwen3-Embedding-0.6B`** —— 若要追 C-MTEB 分數天花板又想保持小體積（0.6B、1024-dim、跑 8GB 無壓力，C-MTEB ~66、multilingual MTEB ~70.7）。
3. **替代 2：`Alibaba-NLP/gte-multilingual-base`** —— 最省（305M、768-dim、最快、VRAM 最低），但要 `trust_remote_code=True`，是「速度優先」選項。
4. **Clustering recipe**：每日數百篇的小批次 →**先不要急著上 UMAP**；先用你現有的 `cluster_by_threshold`（normalized 餘弦 single-link，threshold≈0.78–0.82 起跳）。當批次變大或雜訊多，再切到 **UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric='cosine') → HDBSCAN(min_cluster_size=3~5, min_samples=1, metric='euclidean', cluster_selection_method='eom')**。
5. **繁簡問題**：多數中文 benchmark（C-MTEB）是 **Simplified**；BGE-M3 / e5 / gte 對繁中堪用，但建議在 **embedding 前用 OpenCC 做 `t2s`（繁→簡）正規化**當作低成本保險（embedding 用；**顯示給使用者的原文仍保留繁中**）。此為可選最佳化，需用你的資料抽樣驗證（標記為不確定，見下文）。

---

## 1. Embedding model 比較與選擇

### 1.1 C-MTEB / MTEB(zh) 現況（2025–2026）

C-MTEB（Chinese Massive Text Embedding Benchmark）是 MTEB 的中文延伸，涵蓋 classification / clustering / retrieval / STS 等任務。2025–2026 的 leaderboard 頂端被**大模型**佔據：`Qwen3-Embedding-8B`（C-MTEB mean ~73.84）、`gte-Qwen2-7B-instruct`（~71.62）、Conan / Seed 系列等（[QZhou-Embedding Technical Report, arXiv 2508.21632](https://arxiv.org/pdf/2508.21632)；[C-Pack / BGE, arXiv 2309.07597](https://arxiv.org/html/2309.07597v3)）。**這些 7B/8B 模型在 8GB VRAM 上不實際**（即便 fp16 也吃 15GB+），故本專案應在「**1B 以下、能上 8GB**」的區間裡挑，犧牲約 5% 分數換取 local 可行性是合理取捨（[Best Embedding Model for RAG 2026, Milvus](https://milvus.io/blog/choose-embedding-model-rag-2026.md)）。

### 1.2 候選對照表（聚焦 8GB 可跑的開源模型）

| Model | Params | Dim | Max tok | 授權 | 安裝路徑 | 繁中 / 多語 | 備註 |
|---|---|---|---|---|---|---|---|
| **BAAI/bge-m3** ✅首選 | ~568M | 1024 | 8192 | **MIT** | `sentence-transformers`（dense）或 FlagEmbedding | 多語＋中文強，dense/sparse/multi-vec 三模 | 不需 trust_remote_code；fp16 約 1.2–1.5GB VRAM |
| **Qwen/Qwen3-Embedding-0.6B** 替代1 | ~0.6B | 1024 | 32k | Apache-2.0 | `sentence-transformers≥2.7` | C-MTEB ~66、mMTEB ~70.7 | instruction-aware，分數最高的小模型 |
| **Alibaba-NLP/gte-multilingual-base** 替代2 | **305M** | 768 | 8192 | Apache-2.0 | `sentence-transformers` + `trust_remote_code=True` | 70+ 語、中文佳 | 最快最省，速度優先 |
| intfloat/multilingual-e5-large | ~560M | 1024 | 512 | MIT | `sentence-transformers` | C-MTEB ~58（e5-large-instruct） | 需加 `query:`/`passage:` prefix；512 token 偏短，對長 body 不利 |
| multilingual-e5-base/small | 278M/118M | 768/384 | 512 | MIT | `sentence-transformers` | 較弱 | 極省，但短 max-len + 較低分 |
| jinaai/jina-embeddings-v3 | ~570M | 1024 | 8192 | **CC BY-NC** ⚠ | `sentence-transformers`+trust_remote_code | task-LoRA（含 clustering adapter） | **非商用授權** → portfolio 可、商用要授權/API |
| Conan-embedding / QZhou 等 | 大多 ≥1.5B | — | — | 視模型 | 多走 FlagEmbedding | C-MTEB 高 | 體積/安裝較重，不適合 8GB+「避開 FlagEmbedding」目標 |

來源：[jina-embeddings-v3, arXiv 2409.10173](https://arxiv.org/html/2409.10173)、[Jina v3 release](https://jina.ai/news/jina-embeddings-v3-a-frontier-multilingual-embedding-model/)、[gte-multilingual model card](https://huggingface.co/Alibaba-NLP/gte-multilingual-base)、[Qwen3-Embedding-0.6B model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)、[BGE-M3 model card / Shitao/bge-m3](https://huggingface.co/Shitao/bge-m3)、[Open-Source Embedding Models 2026, BentoML](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)、[OpenAI vs BGE vs E5 vs GTE vs Jina 比較](https://knightli.com/en/2026/04/23/compare-openai-bge-e5-gte-jina-embedding-models/)。

### 1.3 為什麼首選 BGE-M3（而非更高分的選項）

- **授權無風險**：MIT，可自由 self-host 商用；jina-v3 雖然 clustering adapter 誘人，但 **CC BY-NC** 對「作品集→未來可能商用」有授權雷區，故不選為首選（[Jina v3 release](https://jina.ai/news/jina-embeddings-v3-a-frontier-multilingual-embedding-model/)）。
- **與現有 code 對齊**：`event_cluster.py` 的 `build_bge_m3_embedder` 本來就鎖定 BGE-M3，向量也假設 **L2-normalized**（dense vec 預設正規化），下游 `cosine`/MMR/centroid 邏輯**完全不用改**。
- **長文容忍**：8192 token，貼文 title+body 再長都不會被 512 截斷（e5 的弱點）。
- **混合語言**：BGE-M3 原生多語，zh+en 同空間，免分流。

> ⚠ **不確定點（需用你資料驗證）**：在「**繁中短文 event clustering**」這個具體任務上，BGE-M3 vs Qwen3-0.6B vs gte-base 的實際差距，沒有公開 zh-Hant 短文 benchmark 可直接引用。建議做一次 10–20 分鐘的小驗證（見 §4）再定案。

### 1.4 繁體中文（zh-Hant）注意事項 + OpenCC

C-MTEB 與多數中文 evaluation **以 Simplified 為主**；上述模型多在簡體語料訓練/評測，對繁中是「遷移」而非「原生」。實務常見做法：**在送進 embedder 前用 OpenCC 做繁→簡正規化**，讓 token 分佈更靠近模型訓練分佈（[BYVoid/OpenCC](https://github.com/BYVoid/OpenCC)；[zhconv](https://github.com/gumblex/zhconv)）。

建議：
- **顯示層**：永遠保留使用者原始繁中（電子報、citation 都用原文）。
- **embedding 層（可選）**：`opencc OpenCC('t2s')` 轉簡 → embed。純 Python：`pip install opencc-python-reimplemented` 或 `zhconv`。
- 這是**低成本保險**，BGE-M3 本身對繁中已堪用；是否真的提升 cluster 純度，**請用 §4 抽樣比較**（標記為不確定）。台灣用語（如「程式」vs「程序」、「資料」vs「數據」）OpenCC 的 `t2s`/`tw2sp` 詞表可處理一部分。

---

## 2. Clustering recipe（事件偵測）

### 2.1 演算法選擇

| 方法 | 適用 | 對本專案 |
|---|---|---|
| **single-link threshold（你現有的 `cluster_by_threshold`）** | 小批次、要可重現、要鏈式合併 | ✅ **每日數百篇的預設**：免依賴、確定性、O(n²) 在數百篇可接受 |
| **HDBSCAN（+UMAP）** | 較大批次、密度不均、要自動標雜訊 | ✅ **batch 變大/雜訊多時的升級路徑**（你已有 `hdbscan_cluster`） |
| Agglomerative（average/ward, distance_threshold） | 想要 dendrogram、可調 linkage | 替代 single-link 的穩健版（sklearn，無需 hdbscan） |
| BERTopic | 一站式 topic modeling + 視覺化 | 整套太重，但其 UMAP→HDBSCAN→c-TF-IDF 的 **參數預設值**值得抄（見下） |
| Community detection（如 graph + Louvain，sentence-transformers `util.community_detection`） | 大量近重複文本快速去重/聚合 | 可考慮，但 single-link 已涵蓋鏈式合併需求 |

關鍵實證：**短文 + 小 corpus 用 clustering 套件的 default 參數，大多數點會被丟成 noise**；word embedding + UMAP 能顯著改善 HDBSCAN 在短文上的表現（[Improving HDBSCAN on Short Text Clustering using Word Embedding and UMAP](https://www.researchgate.net/publication/357109700_Improving_the_Performance_of_HDBSCAN_on_Short_Text_Clustering_by_Using_Word_Embedding_and_UMAP)；[Clustering sentence embeddings to identify intents, TDS](https://towardsdatascience.com/clustering-sentence-embeddings-to-identify-intents-in-short-text-48d22d3bf02e/)）。

### 2.2 餘弦 vs 歐氏 / 是否要 UMAP

- **向量先 L2-normalize**（BGE-M3 dense 預設已正規化）。正規化後 **歐氏距離與餘弦單調對應**，所以 HDBSCAN 可直接用 `metric='euclidean'`（hdbscan 對 euclidean 有最佳化的 tree，速度較好；你 code 的 docstring 已正確記載這點）。
- single-link fallback 直接用 cosine（你的 `cluster_by_threshold` 已是）。
- **UMAP 用 `metric='cosine'`**，降到 5 維給 HDBSCAN（[BERTopic Best Practices](https://maartengr.github.io/BERTopic/getting_started/best_practices/best_practices.html)；[Clustering with OpenAI embeddings + HDBSCAN + UMAP, Dylan Castillo](https://dylancastillo.co/posts/clustering-documents-with-openai-langchain-hdbscan.html)）。

### 2.3 參數起點（直接抄用）

**每日小批次（數百篇）→ 用 single-link（你現有路徑）：**
```
cluster_by_threshold(vectors, threshold=0.80, min_size=2)
# threshold 起跳 0.78~0.82；越高群越緊、越多單例被丟。
# 對「同一事件多人轉發/改寫」這種高相似場景，0.80 通常能把一事件聚起來又不過度合併。
```
> 注意：single-link 的鏈式特性可能造成 **chaining**（A~B~C 串成一大群）。若發現大群被串接，**調高 threshold** 或改走 §2.4 的 HDBSCAN。

**批次變大 / 噪點多 → UMAP + HDBSCAN：**
```
UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric='cosine', random_state=42)
HDBSCAN(min_cluster_size=3, min_samples=1, metric='euclidean',
        cluster_selection_method='eom', cluster_selection_epsilon=0.0)
```
- `min_cluster_size`：**事件的最小貼文數**。BERTopic 預設 150 是給大語料的；**短文小批次請用 3~5**（你要的是「幾篇就算一個事件」）。
- `min_samples`：設**小（1~2）以減少 noise**。預設 = min_cluster_size 會把太多點丟成雜訊；對短文要刻意調低（[short text clustering 文獻同此結論](https://www.researchgate.net/publication/357109700_Improving_the_Performance_of_HDBSCAN_on_Short_Text_Clustering_by_Using_Word_Embedding_and_UMAP)）。
- `cluster_selection_epsilon`：預設 0.0；若想**合併過度切碎的鄰近小群**，設一個小正值（如 0.1~0.2，在 5 維 UMAP 空間試）。
- `cluster_selection_method='eom'`（excess of mass，BERTopic 預設）通常比 `'leaf'` 給更穩定的大群。
- `random_state=42`：UMAP 有隨機性，**務必固定**以維持你 code 一貫的 determinism 原則。

**雜訊回收（可選）**：HDBSCAN 會把離群點標 -1；若想「每篇都歸一個事件」，可用「離群點 → 最近群 centroid（cosine）」回收（BERTopic 的 `reduce_outliers` 同概念）。但對「事件偵測」而言，**保留 noise = 過濾掉雜談/單篇**反而是好事，建議**預設不回收**。

### 2.4 何時加 UMAP？（直接判斷準則）

- 每日 batch **≤ ~300 篇**：**不必 UMAP**，single-link 即可，省一個重依賴、且確定性更好。
- batch **≥ ~500 篇 或** 出現「大量點被丟成 noise / 群品質差」：**加 UMAP 降到 5 維再 HDBSCAN**。1024-dim 直接餵 HDBSCAN 會吃到 curse of dimensionality，UMAP 降維對短文聚類有實證增益。
- 對 60k 全量重跑（非每日）：一定走 UMAP+HDBSCAN。

---

## 3. Local-install pragmatics（避開壞掉的 Ollama 與未裝的 FlagEmbedding）

### 3.1 最可靠路徑：`sentence-transformers`（不碰 Ollama、不碰 FlagEmbedding）

Ollama 目前在這張 4060 上 CUDA kernel mismatch（driver 太舊）→ **放棄 Ollama embedder 路徑**。FlagEmbedding 未裝且依賴較重 → **改用 sentence-transformers 直接載 BGE-M3 的 dense 向量**，功能等價（dense 1024-dim + L2 normalize），安裝最單純：

```python
# pip install sentence-transformers   (會帶 torch；裝 CUDA 版 torch 才會用 GPU)
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-m3", device="cuda")  # fp32 載入後可 model.half()
# 取 dense、L2 normalize（與現有 cosine/MMR 對齊）
def embed(text: str) -> list[float]:
    v = model.encode(text or " ", normalize_embeddings=True, convert_to_numpy=True)
    return v.tolist()
```
- BGE-M3 可用標準 `SentenceTransformer(...)` 載入並 `normalize_embeddings=True`，**不需 FlagEmbedding**（[Shitao/bge-m3 model card 的 ST 用法](https://huggingface.co/Shitao/bge-m3)；[BGE 官方文件](https://bge-model.com/bge/bge_m3.html)）。
- 這正好可改寫現有的 `build_bge_m3_embedder`（把 FlagEmbedding 換成 sentence-transformers），其餘 pipeline 不動。**（本文不改 code，僅建議。）**

### 3.2 VRAM / 吞吐（4060 8GB 估算）

- BGE-M3 / Qwen3-0.6B（~0.5–0.6B、fp16）：權重約 **1.1–1.3GB**，inference activation 視 batch/seq，**8GB 綽綽有餘**。可開 `model.half()` 或 `torch_dtype=float16`，並用 **batch encode**（如 `model.encode(list_of_texts, batch_size=32~64, normalize_embeddings=True)`）大幅加速。
- gte-multilingual-base（305M）：權重 ~0.6GB，**最省最快**，適合 60k 全量重嵌或追求低延遲。
- 60k 全量在 4060 上用 batch=64、fp16，大約數分鐘級可跑完一次（**估算，未實測 → 不確定**）。每日數百篇是秒級。
- 提醒：sentence-transformers 走 GPU 需安裝 **CUDA 版 torch**；若 torch 是 CPU-only，會在 CPU 上跑（仍可用，只是慢）。Ollama 的 CUDA 問題與 PyTorch 無關，PyTorch 通常能正常用 4060（標記為不確定，依實機 driver/torch 版本而定）。

### 3.3 trust_remote_code 注意

- BGE-M3、e5 系列：**不需** trust_remote_code。
- gte-multilingual-base、jina-v3：**需 `trust_remote_code=True`**（[gte model card](https://huggingface.co/Alibaba-NLP/gte-multilingual-base)）。這在受限環境可能是阻礙，也是「首選 BGE-M3」的另一個理由。

---

## 4. 建議的 10–20 分鐘驗證（定案前做一次）

公開 benchmark 沒有「繁中短文 event clustering」這條，故**用你自己 50–100 篇已知同事件/不同事件的貼文**跑一次小實驗，比三件事：
1. **embedder**：BGE-M3 vs Qwen3-0.6B vs gte-base（各嵌一次）。
2. **OpenCC**：embed 前做 / 不做 `t2s`，看 cluster 是否更乾淨。
3. **threshold**：single-link 在 0.76 / 0.80 / 0.84 的群數與群純度。

評估用你已有的 ground truth（或人工掃一眼），看哪組「一事件一群、不串接、不過碎」。這比任何外部 benchmark 都準。

---

## 5. 對 `ml/ml/event_cluster.py` 的具體落地建議（不改 code，僅指引）

1. **`build_bge_m3_embedder`**：把底層從 `FlagEmbedding.BGEM3FlagModel` 換成 `sentence_transformers.SentenceTransformer("BAAI/bge-m3")` + `encode(..., normalize_embeddings=True)`。介面（`str -> list[float]`、已正規化）不變，下游零改動。
2. **每日 batch**：維持用 `cluster_events(...)`（內部 `cluster_by_threshold`），把 `threshold` 預設由 `0.6` **調高到 ~0.80**（0.6 對 normalized BGE-M3 偏鬆，易過度合併）。
3. **升級鉤子**：當每日量 > ~500 或品質下降，改呼叫 `hdbscan_cluster(vectors, min_cluster_size=3, min_samples=1, metric='euclidean')`；並在嵌入後、分群前插一段 UMAP 降維（新增 lazy import，沿用現有「重依賴函式內延遲載入」慣例）。記得固定 `random_state=42`。
4. **OpenCC（可選）**：在 `_post_text` → embed 之間插一個 `t2s` 正規化（只影響 embedding，不影響顯示/citation 的原文）。
5. **metric 一致性**：HDBSCAN 路徑維持 `metric='euclidean'` + 正規化向量（你的 docstring 已正確），UMAP 用 `metric='cosine'`。

---

## 來源清單

- [QZhou-Embedding Technical Report (C-MTEB 比較基準, 2025), arXiv 2508.21632](https://arxiv.org/pdf/2508.21632)
- [C-Pack / BGE: Packed Resources for General Chinese Embeddings, arXiv 2309.07597](https://arxiv.org/html/2309.07597v3)
- [Qwen3 Embedding Technical Report, arXiv 2506.05176](https://arxiv.org/pdf/2506.05176)
- [Best Embedding Model for RAG 2026, Milvus](https://milvus.io/blog/choose-embedding-model-rag-2026.md)
- [jina-embeddings-v3 (task-LoRA, clustering adapter), arXiv 2409.10173](https://arxiv.org/html/2409.10173)
- [Jina Embeddings v3 release（授權 CC BY-NC 說明）](https://jina.ai/news/jina-embeddings-v3-a-frontier-multilingual-embedding-model/)
- [Alibaba-NLP/gte-multilingual-base model card（305M/768d/8192/trust_remote_code）](https://huggingface.co/Alibaba-NLP/gte-multilingual-base)
- [Qwen/Qwen3-Embedding-0.6B model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- [Shitao/bge-m3 model card（sentence-transformers 用法）](https://huggingface.co/Shitao/bge-m3)
- [BGE-M3 官方文件](https://bge-model.com/bge/bge_m3.html)
- [Open-Source Embedding Models 2026, BentoML](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)
- [OpenAI vs BGE vs E5 vs GTE vs Jina 比較](https://knightli.com/en/2026/04/23/compare-openai-bge-e5-gte-jina-embedding-models/)
- [BERTopic Best Practices（UMAP/HDBSCAN 參數）](https://maartengr.github.io/BERTopic/getting_started/best_practices/best_practices.html)
- [Clustering Documents with OpenAI embeddings, HDBSCAN and UMAP, Dylan Castillo](https://dylancastillo.co/posts/clustering-documents-with-openai-langchain-hdbscan.html)
- [Improving HDBSCAN on Short Text Clustering using Word Embedding and UMAP](https://www.researchgate.net/publication/357109700_Improving_the_Performance_of_HDBSCAN_on_Short_Text_Clustering_by_Using_Word_Embedding_and_UMAP)
- [Clustering sentence embeddings to identify intents in short text, TDS](https://towardsdatascience.com/clustering-sentence-embeddings-to-identify-intents-in-short-text-48d22d3bf02e/)
- [BYVoid/OpenCC（繁簡轉換）](https://github.com/BYVoid/OpenCC)
- [gumblex/zhconv（繁簡轉換, 純 Python）](https://github.com/gumblex/zhconv)
