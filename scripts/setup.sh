#!/usr/bin/env bash
# 一鍵設定本機開發環境。
# 用法: bash scripts/setup.sh

set -e

echo "🌊 Pulse setup starting..."

# 檢查必要工具
command -v docker >/dev/null 2>&1 || { echo "❌ 需要 Docker"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ 需要 Node.js 20+"; exit 1; }
command -v uv >/dev/null 2>&1 || { echo "⚠️  推薦安裝 uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; }

# 1. .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✅ 已建立 .env，請填入 API keys"
else
  echo "ℹ️  .env 已存在，跳過"
fi

# 2. Postgres
echo "🐘 啟動 Postgres..."
docker compose up -d db

# 等 DB 就緒
echo "⏳ 等待 DB 健康..."
until docker compose exec -T db pg_isready -U pulse -d pulse > /dev/null 2>&1; do
  sleep 1
done
echo "✅ DB 就緒"

# 3. API 依賴 + migration
echo "🐍 安裝 API 依賴..."
cd api
if command -v uv >/dev/null 2>&1; then
  uv sync
  uv run alembic upgrade head
else
  pip install -e ".[dev]"
  alembic upgrade head
fi
cd ..

# 4. Web 依賴
echo "📦 安裝 Web 依賴..."
cd web
npm install
cd ..

echo ""
echo "🎉 設定完成！"
echo ""
echo "下一步："
echo "  1. 編輯 .env 填入 Reddit / Anthropic API keys"
echo "  2. 啟動 API:  cd api && uv run uvicorn api.main:app --reload"
echo "  3. 啟動 Web:  cd web && npm run dev"
echo ""
