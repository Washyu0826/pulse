# Pulse 競品分析（2026-05-31）

> 目的：壓力測試產品定位。結論——Pulse 不該當「市場產品」定位（每條軸都有強勢對手），
> 而應定位為**作品集 + N=1 自用工具**，差異化靠**工程**與**自架可查詢多源儀表板**。

## 競品地圖

每個 Pulse 想做的價值主張，都有現成（常免費/巨量）對手：

| Pulse 想做 | 現成對手 | 對手強項 |
|------|---------|---------|
| 每日 AI 情報 | TLDR AI（125萬）、The Rundown（200萬）、Superhuman（150萬） | 編輯精選、巨量讀者、佔據心智 |
| 掃社群→每日 AI 趨勢 | **reddit-ai-trends**（開源免費） | 幾乎同概念，含中英雙語 |
| 模型口碑/選型 | LMSYS Arena（600萬盲測）、Artificial Analysis | 嚴謹方法論，勝過社群情緒 |
| HN/Reddit 監測+情緒+告警 | KWatch.io（$19/月）、Brandwatch（企業級） | 多平台、即時告警、現成 SaaS |
| 跨源趨勢彙整 | Trends Aggregator（免費；Reddit+HN+GitHub+PH） | 免 key、現成 |
| 發現新 AI 工具 | There's An AI For That（#1）、Futurepedia（1200+） | 工具目錄霸主 |
| 中文 AI 工具情報 | 知乎白皮書、johntool、各種懶人包 | 中文圈已飽和 |

## 最危險競品：reddit-ai-trends（同概念雙胞胎）

開源、免費。掃英文+中文 AI 子版、LLM（DeepSeek R1）分析、每日趨勢報告（今日/週/月演化）。
Python + MongoDB + Docker。

**它的弱點 = Pulse 唯一站得住的縫隙：**
- 只有 Markdown 報告，**無 Web UI**
- **只爬 Reddit**（Pulse 有 HN + Dev.to + Threads 多源）
- 線性報告，**不可查詢/篩選**

## 診斷：為什麼定位「怪」

用「市場產品」標準定位 → 每條軸都輸專門對手（情報輸 TLDR、口碑輸 Arena、新工具輸 TAAFT、監測輸 KWatch）。
這是一場不需要打的仗。

## 結論：定位往「作品集 + N=1 自用」收

- **差異化＝工程**：端到端自建管線（爬蟲 → 5 層 DQC → 地端 zero-shot 主題分類 + 情緒 → Airflow → Prometheus → 前端）。展示給雇主的是「我能獨力建一條 production 級資料/ML 管線」。
- **實用性＝贏在對手弱點**：自架 + 可查詢/篩選 + 多源（含中文 Threads）+ Web UI + 自己的 filter。只要對你一個人每天有用就成立。
- **不吹**：別宣稱「比電子報快」「選型決策」當頭號賣點——那是輸的比較。

## Sources
- https://github.com/liyedanpdx/reddit-ai-trends
- https://dupple.com/learn/best-ai-newsletters
- https://presenc.ai/research/lmsys-chatbot-arena-elo-rankings-may-2026
- https://kwatch.io/brandwatch-alternative-for-social-media-listening-on-reddit-linkedin-x-twitter-facebook
- https://apify.com/miccho27/trends-aggregator
- https://theresanaiforthat.com/
