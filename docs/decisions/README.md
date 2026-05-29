# Architecture Decision Records (ADR)

每個重大技術決策一篇短文，記錄：
- **背景**：為什麼要做決定
- **選項**：考慮過哪些
- **決定**：選了什麼
- **後果**：好處與代價

## 紀錄

### v3 基礎決策
- [001 — 用 Monorepo](./001-monorepo.md)
- [002 — 用 Docker Compose 起 DB](./002-docker-compose-db.md)
- [003 — 用 SQLAlchemy 2.x + Alembic](./003-sqlalchemy.md)
- [004 — 模型放 FastAPI 內（不獨立 service）](./004-inline-model.md)
- [005 — Next.js Server Components 為主](./005-server-components.md)
- [006 — 不做使用者登入](./006-no-auth.md)

### v4 採納 Mentor Review 後新增
- [007 — 從 Prefect 改用 Apache Airflow](./007-airflow.md)
- [008 — 採用 Offline Evaluation 取代 A/B Test 術語](./008-offline-evaluation.md)
- [009 — Data Quality Check 5 層過濾器設計](./009-data-quality-check.md)

## 範本

新增 ADR 用 [TEMPLATE.md](./TEMPLATE.md) 複製。
