FROM python:3.11-slim

WORKDIR /app

# 系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 用 uv 安裝（比 pip 快很多）
RUN pip install --no-cache-dir uv

# 複製 dependency 檔
COPY pyproject.toml ./

# 安裝依賴
RUN uv pip install --system --no-cache .

# 複製程式碼
COPY api/ ./api/
COPY alembic/ ./alembic/
COPY alembic.ini ./

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
