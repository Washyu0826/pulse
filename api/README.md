# Pulse API

FastAPI 後端，跑情緒分析 + 提供 RESTful API。

## 開發

```bash
# 安裝依賴（推薦 uv）
uv sync

# 跑 migration
uv run alembic upgrade head

# 啟動
uv run uvicorn api.main:app --reload
```

## 架構

```
api/
├── api/
│   ├── main.py         FastAPI app + lifespan
│   ├── config.py       設定（pydantic-settings）
│   ├── database.py     SQLAlchemy 2.x async
│   ├── routers/        API endpoints
│   ├── models/         SQLAlchemy DB models
│   ├── schemas/        Pydantic API schemas
│   └── services/       商業邏輯（含 ML inference）
├── alembic/            DB migrations
└── tests/
```

## 重要原則

- **SQLAlchemy 2.x async style**（不要寫 1.x 的 `session.query(...)`）
- **Models 跟 Schemas 分開**（DB 用 SQLAlchemy、API 用 Pydantic）
- **服務層放 services/**（router 只處理 HTTP，邏輯放 service class）
- **每次改 model 都要跑 alembic revision**

## 加新 model 流程

1. 在 `api/models/xxx.py` 寫 SQLAlchemy model
2. 在 `alembic/env.py` import 它（讓 Alembic 偵測得到）
3. `uv run alembic revision --autogenerate -m "add xxx"`
4. 檢查產生的 migration 檔
5. `uv run alembic upgrade head`

## 測試

```bash
uv run pytest
uv run pytest --cov=api  # 含覆蓋率
```
