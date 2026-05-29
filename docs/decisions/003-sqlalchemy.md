# ADR-003：用 SQLAlchemy 2.x + Alembic

**狀態**：Accepted
**日期**：2026-05-08

## 背景

需要一個 ORM 處理 PostgreSQL 操作。Pulse 會有時序聚合、全文搜尋、window function 等複雜 query。

## 選項

1. **SQLAlchemy 2.x + Alembic**：業界標準
2. **SQLModel**：FastAPI 作者寫的，整合 Pydantic
3. **Prisma Python**：beta，TypeScript 圈的紅人

## 決定

選 **SQLAlchemy 2.x + Alembic**，async 風格。

## 理由

1. **業界標準**：90% Python 後端工作用這個，履歷加分
2. **AI 寫程式品質高**：Claude Code 對 SQLAlchemy 最熟
3. **應付得了 Pulse 所有 query**：時序聚合、全文搜尋、window function 都行
4. **Alembic 是 production migration 標配**
5. **長期投資**：5 年內都有用

## 後果

**好處**
- 文件最齊全
- 功能最強大
- AI 寫程式品質高

**代價**
- Verbose（Models + Schemas 要分開寫）
- 1.x 跟 2.x 風格差異大，要堅持只用 2.x

## 重要實作原則

- **永遠用 2.x async style**：`select(...)`，不要 `session.query(...)`
- **driver 用 asyncpg**：`postgresql+asyncpg://`
- **Models 跟 Pydantic Schemas 分開**：`api/models/` vs `api/schemas/`
- **永遠用 Alembic 改 schema**：不要 `Base.metadata.create_all()`
- **每次改 model 要 alembic revision --autogenerate**
