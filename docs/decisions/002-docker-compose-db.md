# ADR-002：用 Docker Compose 起 DB

**狀態**：Accepted
**日期**：2026-05-08

## 背景

開發環境要跑 Postgres。後續還會加 Prefect、MLflow、Prometheus、Grafana 等 5+ 個服務。

## 選項

1. **Docker Compose**：一個 yaml 起所有服務
2. **WSL 內裝 Postgres**：原生安裝
3. **雲端託管**（Supabase、Neon）：免本機 DB

## 決定

選 **Docker Compose**。

## 理由

1. **多服務管理**：之後 6+ 個服務一個指令啟動
2. **環境一致性**：跟 production / CI / 隊友都用一樣的 image 版本
3. **砍掉重練容易**：`docker compose down -v`
4. **跟 Railway 部署環境一致**：Railway 也是容器化
5. **業界標準**：你以後進公司一定會用

## 後果

**好處**
- 一個 yaml 管全部
- 環境一致
- CI/CD 用同一份

**代價**
- 啟動稍慢（5-10s）
- Docker Desktop 吃 1-2GB RAM

**之後可能要重新考慮的情境**
- 開發機 RAM 不夠
- Docker Desktop 授權變動
