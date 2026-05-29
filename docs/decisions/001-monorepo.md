# ADR-001：用 Monorepo

**狀態**：Accepted
**日期**：2026-05-08

## 背景

Pulse 包含 API、前端、Workers、ML 四個元件，要決定放在一個 repo 還是分開。

## 選項

1. **Monorepo**：一個 GitHub repo，用資料夾分開
2. **多 Repo**：每個服務獨立 repo（pulse-api、pulse-web 等）

## 決定

選 **Monorepo**。

## 理由

1. **AI coding 工具友善**：Claude Code 在一個資料夾看得到所有程式碼，跨服務改動一次完成
2. **個人專案規模**：流量、團隊都不到要拆 repo 的等級
3. **改動跨服務的 feature 一次搞定**：例如「加新欄位」只要一個 PR，不用四個 PR 同步
4. **部署、CI/CD、文件集中管理**：一個 docker-compose、一份 README
5. **業界趨勢**：Vercel、Anthropic、Stripe 都是 monorepo

## 後果

**好處**
- 開發體驗順
- 文件集中
- 跨服務改動容易

**代價**
- Repo 變大（不是問題：個人專案規模）
- Git history 多服務交錯（用 GitHub path filter 解決）

**之後可能要重新考慮的情境**
- 某個元件想開源獨立（例如 ml/ 變成獨立套件）
- 加入多人協作後權限分割需求
